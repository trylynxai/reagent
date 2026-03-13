"""Redaction engine for PII and secrets filtering."""

from __future__ import annotations

import signal
import threading
from dataclasses import dataclass
from typing import Any

from reagent.core.constants import REDACTION_TIMEOUT_MS
from reagent.core.exceptions import RedactionError
from reagent.redaction.patterns import Pattern, DEFAULT_PATTERNS
from reagent.redaction.rules import RedactionRuleSet


@dataclass
class RedactionResult:
    """Result of redacting a value."""

    redacted_value: str
    redactions: list[dict[str, Any]]  # List of {pattern, start, end, original, replacement}
    had_redactions: bool


class TimeoutError(Exception):
    """Raised when redaction times out."""
    pass


class RedactionEngine:
    """Engine for detecting and redacting sensitive data.

    Supports:
    - Regex-based pattern matching with timeout (ReDoS prevention)
    - Field-level redaction rules
    - Multiple redaction modes (remove, hash, mask, encrypt)
    - Optional NLP-based PII detection (via Presidio)
    """

    def __init__(
        self,
        patterns: list[Pattern] | None = None,
        rules: RedactionRuleSet | None = None,
        timeout_ms: int = REDACTION_TIMEOUT_MS,
        use_nlp: bool = False,
        nlp_entities: list[str] | None = None,
        nlp_language: str = "en",
        nlp_score_threshold: float = 0.0,
    ) -> None:
        """Initialize the redaction engine.

        Args:
            patterns: List of patterns to match (defaults to DEFAULT_PATTERNS)
            rules: Redaction rules to apply
            timeout_ms: Timeout per field in milliseconds (ReDoS prevention)
            use_nlp: Whether to use NLP-based detection (requires presidio)
            nlp_entities: Entity types to detect (None = all supported)
            nlp_language: Language for NLP analysis
            nlp_score_threshold: Minimum confidence score for NLP detections
        """
        self._patterns = patterns or DEFAULT_PATTERNS
        self._rules = rules or RedactionRuleSet()
        self._timeout_ms = timeout_ms
        self._use_nlp = use_nlp
        self._nlp_detector = None
        self._nlp_score_threshold = nlp_score_threshold

        if use_nlp:
            self._init_nlp(
                entities=nlp_entities,
                language=nlp_language,
                score_threshold=nlp_score_threshold,
            )

    def _init_nlp(
        self,
        entities: list[str] | None = None,
        language: str = "en",
        score_threshold: float = 0.0,
    ) -> None:
        """Initialize NLP-based PII detection using NLPDetector.

        Args:
            entities: Entity types to detect (None = all).
            language: Language for analysis.
            score_threshold: Minimum confidence score for detections.
        """
        from reagent.redaction.nlp import NLPDetector

        self._nlp_detector = NLPDetector(
            entities=entities,
            language=language,
        )
        self._nlp_score_threshold = score_threshold
        # Trigger lazy init to fail fast if Presidio is missing
        self._nlp_detector._lazy_init()

    def redact(self, text: str, field_name: str | None = None) -> RedactionResult:
        """Redact sensitive data from text.

        Args:
            text: Text to redact
            field_name: Optional field name for field-level rules

        Returns:
            RedactionResult with redacted text and metadata
        """
        if not self._rules.enabled:
            return RedactionResult(
                redacted_value=text,
                redactions=[],
                had_redactions=False,
            )

        # Check field-level rules
        if field_name:
            field_rule = self._rules.should_redact_field(field_name)
            if field_rule is False:
                return RedactionResult(
                    redacted_value=text,
                    redactions=[],
                    had_redactions=False,
                )
            elif field_rule is True:
                # Redact entire field
                rule = self._rules.get_rule("*")
                replacement = rule.get_replacement(text, "field")
                return RedactionResult(
                    redacted_value=replacement,
                    redactions=[{
                        "pattern": "field_name_match",
                        "field_name": field_name,
                        "start": 0,
                        "end": len(text),
                        "original_length": len(text),
                        "replacement": replacement,
                    }],
                    had_redactions=True,
                )

        redactions: list[dict[str, Any]] = []
        redacted_text = text

        # Apply regex patterns
        for pattern in self._patterns:
            try:
                matches = self._match_with_timeout(pattern, redacted_text)
            except TimeoutError:
                # Pattern timed out, skip it
                continue

            # Process matches in reverse order to preserve positions
            for start, end, matched in reversed(matches):
                rule = self._rules.get_rule(pattern.name)
                replacement = rule.get_replacement(matched, pattern.name)

                redacted_text = redacted_text[:start] + replacement + redacted_text[end:]
                redactions.append({
                    "pattern": pattern.name,
                    "category": pattern.category,
                    "start": start,
                    "end": end,
                    "original_length": len(matched),
                    "replacement": replacement,
                })

        # Apply NLP-based detection if enabled
        if self._use_nlp and self._nlp_detector:
            nlp_text, nlp_redactions = self._apply_nlp_detection(redacted_text)
            if nlp_redactions:
                redacted_text = nlp_text
                redactions.extend(nlp_redactions)

        return RedactionResult(
            redacted_value=redacted_text,
            redactions=redactions,
            had_redactions=len(redactions) > 0,
        )

    def _match_with_timeout(
        self,
        pattern: Pattern,
        text: str,
    ) -> list[tuple[int, int, str]]:
        """Match pattern with timeout to prevent ReDoS.

        Args:
            pattern: Pattern to match
            text: Text to search

        Returns:
            List of (start, end, matched_text) tuples

        Raises:
            TimeoutError: If matching exceeds timeout
        """
        # Use threading for timeout (works on all platforms)
        result: list[tuple[int, int, str]] = []
        exception: Exception | None = None

        def match_thread() -> None:
            nonlocal result, exception
            try:
                result = pattern.find_all(text)
            except Exception as e:
                exception = e

        thread = threading.Thread(target=match_thread)
        thread.start()
        thread.join(timeout=self._timeout_ms / 1000.0)

        if thread.is_alive():
            # Thread is still running, timeout exceeded
            raise TimeoutError(f"Pattern {pattern.name} timed out")

        if exception:
            raise exception

        return result

    def _apply_nlp_detection(self, text: str) -> tuple[str, list[dict[str, Any]]]:
        """Apply NLP-based PII detection using NLPDetector.

        Args:
            text: Text to analyze

        Returns:
            Tuple of (redacted_text, list of redaction metadata dicts).
        """
        if not self._nlp_detector:
            return text, []

        try:
            detections = self._nlp_detector.detect(text)

            # Filter by score threshold
            if self._nlp_score_threshold > 0:
                detections = [
                    d for d in detections
                    if d["score"] >= self._nlp_score_threshold
                ]

            if not detections:
                return text, []

            nlp_redactions: list[dict[str, Any]] = []
            redacted_text = text

            # Sort by start position in reverse to preserve offsets
            detections = sorted(detections, key=lambda x: x["start"], reverse=True)

            for detection in detections:
                entity_type = detection["entity_type"].lower()
                original = detection["text"]
                start = detection["start"]
                end = detection["end"]

                rule = self._rules.get_rule(entity_type)
                replacement = rule.get_replacement(original, entity_type)

                redacted_text = (
                    redacted_text[:start]
                    + replacement
                    + redacted_text[end:]
                )

                nlp_redactions.append({
                    "pattern": f"nlp:{entity_type}",
                    "category": "pii",
                    "start": start,
                    "end": end,
                    "original_length": len(original),
                    "replacement": replacement,
                    "confidence": detection["score"],
                })

            return redacted_text, nlp_redactions

        except Exception:
            # NLP detection failed, return unchanged
            return text, []

    def redact_dict(
        self,
        data: dict[str, Any],
        recursive: bool = True,
    ) -> dict[str, Any]:
        """Redact sensitive data from a dictionary.

        Args:
            data: Dictionary to redact
            recursive: Whether to recurse into nested dicts/lists

        Returns:
            Redacted copy of the dictionary
        """
        result = {}

        for key, value in data.items():
            if isinstance(value, str):
                redacted = self.redact(value, field_name=key)
                result[key] = redacted.redacted_value
            elif isinstance(value, dict) and recursive:
                result[key] = self.redact_dict(value, recursive=True)
            elif isinstance(value, list) and recursive:
                result[key] = self._redact_list(value, parent_field=key)
            else:
                result[key] = value

        return result

    def _redact_list(
        self,
        data: list[Any],
        parent_field: str | None = None,
    ) -> list[Any]:
        """Redact sensitive data from a list."""
        result = []

        for item in data:
            if isinstance(item, str):
                redacted = self.redact(item, field_name=parent_field)
                result.append(redacted.redacted_value)
            elif isinstance(item, dict):
                result.append(self.redact_dict(item, recursive=True))
            elif isinstance(item, list):
                result.append(self._redact_list(item, parent_field=parent_field))
            else:
                result.append(item)

        return result

    def add_pattern(self, pattern: Pattern) -> None:
        """Add a custom pattern."""
        self._patterns.append(pattern)

    def remove_pattern(self, name: str) -> bool:
        """Remove a pattern by name.

        Returns:
            True if pattern was removed
        """
        for i, pattern in enumerate(self._patterns):
            if pattern.name == name:
                del self._patterns[i]
                return True
        return False

    @property
    def patterns(self) -> list[Pattern]:
        """Get the list of patterns."""
        return self._patterns.copy()

    @property
    def rules(self) -> RedactionRuleSet:
        """Get the redaction rules."""
        return self._rules
