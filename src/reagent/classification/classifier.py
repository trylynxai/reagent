"""Rule-based failure classification engine.

Classifies agent failures into categories based on error type,
error message patterns, and execution context. Uses a layered approach:

1. Exact error type matching (fastest, highest confidence)
2. Regex pattern matching on error messages
3. Context-based heuristics (error + step history)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from reagent.core.constants import FailureCategory


@dataclass
class ClassificationResult:
    """Result of a failure classification."""

    category: FailureCategory
    confidence: float  # 0.0 to 1.0
    rule_name: str  # Which rule matched
    details: str | None = None  # Human-readable explanation


@dataclass
class ClassificationRule:
    """A single classification rule."""

    name: str
    category: FailureCategory
    confidence: float

    # Match criteria (any combination)
    error_types: list[str] = field(default_factory=list)
    error_patterns: list[str] = field(default_factory=list)
    traceback_patterns: list[str] = field(default_factory=list)

    # Compiled regex patterns (populated at init)
    _compiled_error: list[re.Pattern[str]] = field(
        default_factory=list, repr=False
    )
    _compiled_traceback: list[re.Pattern[str]] = field(
        default_factory=list, repr=False
    )

    def __post_init__(self) -> None:
        self._compiled_error = [
            re.compile(p, re.IGNORECASE) for p in self.error_patterns
        ]
        self._compiled_traceback = [
            re.compile(p, re.IGNORECASE) for p in self.traceback_patterns
        ]

    def matches(
        self,
        error: str | None,
        error_type: str | None,
        traceback_str: str | None = None,
    ) -> bool:
        """Check if this rule matches the given error."""
        # Check error type
        if self.error_types and error_type:
            error_type_lower = error_type.lower()
            if any(et.lower() in error_type_lower for et in self.error_types):
                return True

        # Check error message patterns
        if self._compiled_error and error:
            if any(p.search(error) for p in self._compiled_error):
                return True

        # Check traceback patterns
        if self._compiled_traceback and traceback_str:
            if any(p.search(traceback_str) for p in self._compiled_traceback):
                return True

        return False


# ============================================================
# Built-in classification rules (ordered by priority)
# ============================================================

BUILTIN_RULES: list[ClassificationRule] = [
    # --- Timeout ---
    ClassificationRule(
        name="timeout_error_type",
        category=FailureCategory.TOOL_TIMEOUT,
        confidence=0.95,
        error_types=["TimeoutError", "asyncio.TimeoutError", "Timeout"],
    ),
    ClassificationRule(
        name="timeout_message",
        category=FailureCategory.TOOL_TIMEOUT,
        confidence=0.85,
        error_patterns=[
            r"timed?\s*out",
            r"deadline\s+exceeded",
            r"request\s+timeout",
            r"execution\s+timeout",
            r"read\s+timed?\s*out",
            r"connect\s+timed?\s*out",
        ],
    ),
    # --- Rate Limiting ---
    ClassificationRule(
        name="rate_limit_error_type",
        category=FailureCategory.RATE_LIMIT,
        confidence=0.95,
        error_types=["RateLimitError"],
    ),
    ClassificationRule(
        name="rate_limit_message",
        category=FailureCategory.RATE_LIMIT,
        confidence=0.90,
        error_patterns=[
            r"rate\s*limit",
            r"too\s+many\s+requests",
            r"429",
            r"quota\s+exceeded",
            r"throttl",
            r"requests?\s+per\s+(second|minute|hour)",
        ],
    ),
    # --- Context Overflow ---
    ClassificationRule(
        name="context_overflow_message",
        category=FailureCategory.CONTEXT_OVERFLOW,
        confidence=0.90,
        error_patterns=[
            r"(context|token)\s*(length|limit|window)\s*(exceed|overflow|too)",
            r"maximum\s+context\s+length",
            r"max(imum)?\s+tokens?\s+exceed",
            r"input\s+is\s+too\s+long",
            r"prompt\s+is\s+too\s+long",
            r"reduce.*(prompt|input|context|tokens)",
            r"token\s+limit",
        ],
    ),
    ClassificationRule(
        name="context_overflow_error_type",
        category=FailureCategory.CONTEXT_OVERFLOW,
        confidence=0.85,
        error_types=["InvalidRequestError", "BadRequestError"],
        error_patterns=[r"token"],
    ),
    # --- Authentication ---
    ClassificationRule(
        name="auth_error_type",
        category=FailureCategory.AUTHENTICATION,
        confidence=0.95,
        error_types=[
            "AuthenticationError",
            "AuthError",
            "UnauthorizedError",
        ],
    ),
    ClassificationRule(
        name="auth_message",
        category=FailureCategory.AUTHENTICATION,
        confidence=0.85,
        error_patterns=[
            r"(invalid|incorrect|expired|missing)\s+(api\s*key|token|credential|auth)",
            r"unauthorized",
            r"401",
            r"authentication\s+(failed|error|required)",
            r"access\s+denied",
            r"forbidden.*api",
            r"api\s*key.*invalid",
        ],
    ),
    # --- Validation ---
    ClassificationRule(
        name="validation_error_type",
        category=FailureCategory.VALIDATION_ERROR,
        confidence=0.90,
        error_types=[
            "ValidationError",
            "ValueError",
            "TypeError",
            "InvalidRequestError",
        ],
    ),
    ClassificationRule(
        name="validation_message",
        category=FailureCategory.VALIDATION_ERROR,
        confidence=0.80,
        error_patterns=[
            r"invalid\s+(argument|parameter|input|value|type|format)",
            r"required\s+(field|parameter|argument)\s+missing",
            r"validation\s+(failed|error)",
            r"unexpected\s+(argument|keyword|type)",
            r"schema\s+validation",
            r"must\s+be\s+(a|an|of\s+type)",
        ],
    ),
    # --- Connection Errors ---
    ClassificationRule(
        name="connection_error_type",
        category=FailureCategory.CONNECTION_ERROR,
        confidence=0.95,
        error_types=[
            "ConnectionError",
            "ConnectionRefusedError",
            "ConnectionResetError",
            "ConnectionAbortedError",
            "BrokenPipeError",
            "OSError",
        ],
    ),
    ClassificationRule(
        name="connection_message",
        category=FailureCategory.CONNECTION_ERROR,
        confidence=0.85,
        error_patterns=[
            r"connection\s+(refused|reset|aborted|closed|failed)",
            r"(could|cannot|unable)\s+(not\s+)?connect",
            r"network\s+(error|unreachable)",
            r"dns\s+(resolution|lookup)\s+failed",
            r"no\s+route\s+to\s+host",
            r"broken\s+pipe",
            r"ECONNREFUSED",
            r"ECONNRESET",
            r"ETIMEDOUT",
        ],
    ),
    # --- Permission Errors ---
    ClassificationRule(
        name="permission_error_type",
        category=FailureCategory.PERMISSION_ERROR,
        confidence=0.95,
        error_types=["PermissionError"],
    ),
    ClassificationRule(
        name="permission_message",
        category=FailureCategory.PERMISSION_ERROR,
        confidence=0.80,
        error_patterns=[
            r"permission\s+denied",
            r"403\s+forbidden",
            r"insufficient\s+permissions?",
            r"not\s+allowed",
            r"access\s+denied",
        ],
    ),
    # --- Resource Exhaustion ---
    ClassificationRule(
        name="resource_exhausted_message",
        category=FailureCategory.RESOURCE_EXHAUSTED,
        confidence=0.85,
        error_patterns=[
            r"out\s+of\s+memory",
            r"memory\s+(error|limit|exceeded)",
            r"disk\s+(full|space)",
            r"resource\s+exhausted",
            r"no\s+space\s+left",
            r"OOM",
            r"MemoryError",
        ],
    ),
    ClassificationRule(
        name="resource_exhausted_type",
        category=FailureCategory.RESOURCE_EXHAUSTED,
        confidence=0.90,
        error_types=["MemoryError", "ResourceExhaustedError"],
    ),
    # --- Tool Errors (broad, lower priority) ---
    ClassificationRule(
        name="tool_error_traceback",
        category=FailureCategory.TOOL_ERROR,
        confidence=0.70,
        traceback_patterns=[
            r"tool.*error",
            r"tool.*exception",
            r"tool.*failed",
        ],
    ),
    ClassificationRule(
        name="tool_error_message",
        category=FailureCategory.TOOL_ERROR,
        confidence=0.65,
        error_patterns=[
            r"tool\s+(execution|call|invocation)\s+(failed|error)",
            r"failed\s+to\s+(execute|run|invoke)\s+tool",
        ],
    ),
    # --- Chain Errors ---
    ClassificationRule(
        name="chain_error_message",
        category=FailureCategory.CHAIN_ERROR,
        confidence=0.65,
        error_patterns=[
            r"chain\s+(execution|step)\s+(failed|error)",
            r"pipeline\s+(failed|error)",
            r"workflow\s+(failed|error)",
        ],
    ),
    # --- Reasoning Loops ---
    ClassificationRule(
        name="reasoning_loop_message",
        category=FailureCategory.REASONING_LOOP,
        confidence=0.80,
        error_patterns=[
            r"(stuck|caught)\s+in\s+(a\s+)?loop",
            r"max(imum)?\s+(iterations?|retries|attempts)\s+(exceeded|reached)",
            r"repeated\s+action",
            r"infinite\s+loop",
            r"too\s+many\s+(iterations?|retries|attempts)",
        ],
    ),
]


class FailureClassifier:
    """Rule-based failure classifier.

    Classifies errors into FailureCategory values using a prioritized
    set of rules. Rules are evaluated in order; the first match with
    the highest confidence wins.

    Custom rules can be added and take priority over built-in rules.
    """

    def __init__(self, rules: list[ClassificationRule] | None = None) -> None:
        """Initialize the classifier.

        Args:
            rules: Optional custom rules (prepended to built-in rules).
        """
        self._custom_rules: list[ClassificationRule] = rules or []

    @property
    def rules(self) -> list[ClassificationRule]:
        """Get all rules (custom first, then built-in)."""
        return self._custom_rules + BUILTIN_RULES

    def add_rule(self, rule: ClassificationRule) -> None:
        """Add a custom classification rule (highest priority)."""
        self._custom_rules.insert(0, rule)

    def classify(
        self,
        error: str | None = None,
        error_type: str | None = None,
        traceback_str: str | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> ClassificationResult:
        """Classify a failure.

        Args:
            error: Error message string
            error_type: Python exception type name (e.g. "TimeoutError")
            traceback_str: Full traceback string
            steps: List of step dicts for context-based classification

        Returns:
            ClassificationResult with category and confidence
        """
        if not error and not error_type:
            return ClassificationResult(
                category=FailureCategory.UNKNOWN,
                confidence=0.0,
                rule_name="no_error_info",
                details="No error information provided",
            )

        best: ClassificationResult | None = None

        for rule in self.rules:
            if rule.matches(error, error_type, traceback_str):
                result = ClassificationResult(
                    category=rule.category,
                    confidence=rule.confidence,
                    rule_name=rule.name,
                    details=f"Matched rule: {rule.name}",
                )
                if best is None or result.confidence > best.confidence:
                    best = result

        if best is not None:
            return best

        # Step-sequence loop detection
        if steps:
            try:
                from reagent.analysis.loop_detector import LoopDetector
                from reagent.schema.steps import (
                    AgentStep,
                    LLMCallStep,
                    ToolCallStep,
                )

                typed_steps = [
                    s for s in steps
                    if isinstance(s, (ToolCallStep, LLMCallStep, AgentStep))
                ]
                if typed_steps:
                    result = LoopDetector().analyze(typed_steps)
                    if result.loop_detected and result.confidence > 0.7:
                        return ClassificationResult(
                            category=FailureCategory.REASONING_LOOP,
                            confidence=result.confidence,
                            rule_name="step_sequence_loop",
                            details=result.summary,
                        )
            except Exception:
                pass  # Don't let loop detection break classification

        # Context-based fallback: check if steps have tool errors
        if steps:
            tool_errors = [
                s for s in steps
                if s.get("step_type") == "tool_call"
                and s.get("output", {}).get("error")
            ]
            if tool_errors:
                return ClassificationResult(
                    category=FailureCategory.TOOL_ERROR,
                    confidence=0.50,
                    rule_name="context_tool_errors",
                    details=f"Found {len(tool_errors)} failed tool call(s) in execution",
                )

        return ClassificationResult(
            category=FailureCategory.UNKNOWN,
            confidence=0.0,
            rule_name="no_match",
            details="No classification rule matched",
        )


# Module-level singleton for convenience
_default_classifier = FailureClassifier()


def classify_failure(
    error: str | None = None,
    error_type: str | None = None,
    traceback_str: str | None = None,
    steps: list[dict[str, Any]] | None = None,
) -> ClassificationResult:
    """Classify a failure using the default classifier.

    Convenience function that uses the module-level classifier instance.
    """
    return _default_classifier.classify(
        error=error,
        error_type=error_type,
        traceback_str=traceback_str,
        steps=steps,
    )
