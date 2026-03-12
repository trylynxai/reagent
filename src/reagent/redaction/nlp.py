"""Optional NLP-based PII detection using Presidio."""

from __future__ import annotations

from typing import Any

from reagent.core.exceptions import RedactionError


class NLPDetector:
    """NLP-based PII detection using Microsoft Presidio.

    This is an optional component that provides more advanced
    PII detection using named entity recognition.

    Requires: pip install presidio-analyzer presidio-anonymizer spacy
    Also requires downloading a spaCy model: python -m spacy download en_core_web_lg
    """

    def __init__(
        self,
        entities: list[str] | None = None,
        language: str = "en",
    ) -> None:
        """Initialize the NLP detector.

        Args:
            entities: List of entity types to detect (None = all)
            language: Language for analysis
        """
        self._entities = entities
        self._language = language
        self._analyzer = None
        self._anonymizer = None
        self._initialized = False

    def _lazy_init(self) -> None:
        """Lazily initialize Presidio components."""
        if self._initialized:
            return

        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine

            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()
            self._initialized = True

        except ImportError as e:
            raise RedactionError(
                "Presidio is required for NLP-based PII detection. "
                "Install with: pip install 'reagent[nlp]' or "
                "pip install presidio-analyzer presidio-anonymizer",
                {"import_error": str(e)},
            )

    def detect(self, text: str) -> list[dict[str, Any]]:
        """Detect PII entities in text.

        Args:
            text: Text to analyze

        Returns:
            List of detected entities with metadata
        """
        self._lazy_init()

        results = self._analyzer.analyze(
            text=text,
            entities=self._entities,
            language=self._language,
        )

        return [
            {
                "entity_type": result.entity_type,
                "start": result.start,
                "end": result.end,
                "score": result.score,
                "text": text[result.start:result.end],
            }
            for result in results
        ]

    def anonymize(
        self,
        text: str,
        operator: str = "replace",
        replacement: str | None = None,
    ) -> str:
        """Anonymize PII in text.

        Args:
            text: Text to anonymize
            operator: Anonymization operator ("replace", "hash", "mask", "redact")
            replacement: Custom replacement text for "replace" operator

        Returns:
            Anonymized text
        """
        self._lazy_init()

        from presidio_anonymizer.entities import OperatorConfig

        # Analyze first
        results = self._analyzer.analyze(
            text=text,
            entities=self._entities,
            language=self._language,
        )

        if not results:
            return text

        # Build operator config
        if operator == "replace" and replacement:
            operators = {"DEFAULT": OperatorConfig("replace", {"new_value": replacement})}
        elif operator == "hash":
            operators = {"DEFAULT": OperatorConfig("hash", {"hash_type": "sha256"})}
        elif operator == "mask":
            operators = {"DEFAULT": OperatorConfig("mask", {"chars_to_mask": 100, "masking_char": "*"})}
        elif operator == "redact":
            operators = {"DEFAULT": OperatorConfig("redact", {})}
        else:
            operators = {"DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"})}

        # Anonymize
        anonymized = self._anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators,
        )

        return anonymized.text

    @property
    def available_entities(self) -> list[str]:
        """Get list of available entity types."""
        self._lazy_init()
        return self._analyzer.get_supported_entities(language=self._language)

    @classmethod
    def is_available(cls) -> bool:
        """Check if Presidio is available."""
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
            return True
        except ImportError:
            return False


# Default entity types for PII detection
DEFAULT_ENTITIES = [
    "CREDIT_CARD",
    "CRYPTO",
    "DATE_TIME",
    "EMAIL_ADDRESS",
    "IBAN_CODE",
    "IP_ADDRESS",
    "NRP",  # Nationality, religious or political group
    "LOCATION",
    "PERSON",
    "PHONE_NUMBER",
    "MEDICAL_LICENSE",
    "URL",
    "US_BANK_NUMBER",
    "US_DRIVER_LICENSE",
    "US_ITIN",
    "US_PASSPORT",
    "US_SSN",
    "UK_NHS",
    "SG_NRIC_FIN",
    "AU_ABN",
    "AU_ACN",
    "AU_TFN",
    "AU_MEDICARE",
]
