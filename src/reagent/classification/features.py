"""Feature extraction for ML-based failure classification.

Converts error information and run metadata into numeric feature
vectors suitable for classification. Uses only stdlib — no numpy
or sklearn required.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


# Common English stop words to exclude from text features
_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "and", "but", "or", "nor", "not", "so", "if",
    "then", "than", "that", "this", "it", "its", "i", "we", "they",
    "he", "she", "you", "my", "your", "his", "her", "our", "their",
})

# Regex for tokenizing error messages
_TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


@dataclass
class FeatureVocabulary:
    """Vocabulary mapping words to feature indices.

    Built from training data; used to convert text to fixed-size vectors.
    """

    word_to_index: dict[str, int] = field(default_factory=dict)
    max_features: int = 200

    @property
    def size(self) -> int:
        return len(self.word_to_index)

    def build(self, texts: list[str]) -> None:
        """Build vocabulary from a list of texts.

        Selects the top `max_features` most frequent non-stop words.
        """
        counter: Counter[str] = Counter()
        for text in texts:
            tokens = _tokenize(text)
            counter.update(tokens)

        # Select top N most common
        most_common = counter.most_common(self.max_features)
        self.word_to_index = {word: i for i, (word, _) in enumerate(most_common)}

    def to_dict(self) -> dict[str, Any]:
        return {
            "word_to_index": self.word_to_index,
            "max_features": self.max_features,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureVocabulary:
        return cls(
            word_to_index=data["word_to_index"],
            max_features=data.get("max_features", 200),
        )


# Number of numeric (non-text) features
NUM_NUMERIC_FEATURES = 10

# Error type vocabulary (common Python exception names)
_ERROR_TYPE_MAP = {
    "timeouterror": 0, "asyncio.timeouterror": 0, "timeout": 0,
    "ratelimiterror": 1,
    "connectionerror": 2, "connectionrefusederror": 2, "connectionreseterror": 2,
    "authenticationerror": 3, "autherror": 3, "unauthorizederror": 3,
    "validationerror": 4, "valueerror": 4, "typeerror": 4,
    "permissionerror": 5,
    "memoryerror": 6, "resourceexhaustederror": 6,
    "keyerror": 7, "attributeerror": 7, "indexerror": 7,
    "runtimeerror": 8,
    "oserror": 9, "ioerror": 9,
}
NUM_ERROR_TYPE_FEATURES = 10


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase words, excluding stop words."""
    words = _TOKEN_RE.findall(text.lower())
    return [w for w in words if w not in _STOP_WORDS and len(w) > 1]


def extract_features(
    error: str | None = None,
    error_type: str | None = None,
    traceback_str: str | None = None,
    steps: list[dict[str, Any]] | None = None,
    run_metadata: dict[str, Any] | None = None,
    vocabulary: FeatureVocabulary | None = None,
) -> list[float]:
    """Extract a feature vector from error information and run context.

    Feature layout:
    - [0..vocab_size): Bag-of-words from error message + traceback
    - [vocab_size..vocab_size+10): Error type one-hot encoding
    - [vocab_size+10..vocab_size+20): Numeric run features

    Args:
        error: Error message string.
        error_type: Exception type name.
        traceback_str: Full traceback string.
        steps: List of step dicts for context features.
        run_metadata: Run metadata dict for numeric features.
        vocabulary: Word vocabulary for text features.

    Returns:
        Feature vector as a list of floats.
    """
    vocab_size = vocabulary.size if vocabulary else 0
    total_size = vocab_size + NUM_ERROR_TYPE_FEATURES + NUM_NUMERIC_FEATURES
    features = [0.0] * total_size

    # ── Text features (bag-of-words) ──
    if vocabulary and vocabulary.size > 0:
        text_parts = []
        if error:
            text_parts.append(error)
        if traceback_str:
            text_parts.append(traceback_str)
        combined = " ".join(text_parts)
        tokens = _tokenize(combined)
        token_counts = Counter(tokens)

        for word, count in token_counts.items():
            idx = vocabulary.word_to_index.get(word)
            if idx is not None:
                # TF: log(1 + count) for dampening
                features[idx] = math.log1p(count)

    # ── Error type features (one-hot) ──
    offset = vocab_size
    if error_type:
        et_lower = error_type.lower()
        et_idx = _ERROR_TYPE_MAP.get(et_lower)
        if et_idx is not None:
            features[offset + et_idx] = 1.0

    # ── Numeric run features ──
    offset = vocab_size + NUM_ERROR_TYPE_FEATURES
    _fill_numeric_features(features, offset, steps, run_metadata)

    return features


def _fill_numeric_features(
    features: list[float],
    offset: int,
    steps: list[dict[str, Any]] | None,
    run_metadata: dict[str, Any] | None,
) -> None:
    """Fill numeric features from step context and run metadata.

    Features (10 total):
    [0] total_steps
    [1] llm_call_count
    [2] tool_call_count
    [3] error_count
    [4] total_tokens (log-scaled)
    [5] total_cost_usd (log-scaled)
    [6] duration_ms (log-scaled)
    [7] error_position_ratio (where in the run the error occurred)
    [8] tool_error_ratio (fraction of tool calls that failed)
    [9] unique_tool_count
    """
    if steps:
        total = len(steps)
        features[offset] = math.log1p(total)

        llm_count = sum(1 for s in steps if _step_type(s) == "llm_call")
        tool_count = sum(1 for s in steps if _step_type(s) == "tool_call")
        error_count = sum(1 for s in steps if _step_type(s) == "error")

        features[offset + 1] = math.log1p(llm_count)
        features[offset + 2] = math.log1p(tool_count)
        features[offset + 3] = math.log1p(error_count)

        # Error position ratio
        error_positions = [
            i for i, s in enumerate(steps) if _step_type(s) == "error"
        ]
        if error_positions and total > 0:
            features[offset + 7] = error_positions[-1] / total

        # Tool error ratio
        tool_steps = [s for s in steps if _step_type(s) == "tool_call"]
        if tool_steps:
            failed = sum(
                1 for s in tool_steps
                if not _step_success(s)
            )
            features[offset + 8] = failed / len(tool_steps)

        # Unique tools
        tool_names = {
            _step_field(s, "tool_name")
            for s in steps
            if _step_type(s) == "tool_call" and _step_field(s, "tool_name")
        }
        features[offset + 9] = math.log1p(len(tool_names))

    if run_metadata:
        tokens = run_metadata.get("tokens", {})
        if isinstance(tokens, dict):
            total_tok = tokens.get("total_tokens", 0)
        else:
            total_tok = getattr(tokens, "total_tokens", 0)
        features[offset + 4] = math.log1p(total_tok)

        cost = run_metadata.get("cost", {})
        if isinstance(cost, dict):
            total_cost = cost.get("total_usd", 0)
        else:
            total_cost = getattr(cost, "total_usd", 0)
        features[offset + 5] = math.log1p(total_cost * 1000)  # Scale to millidollars

        duration = run_metadata.get("duration_ms", 0) or 0
        features[offset + 6] = math.log1p(duration)


def _step_type(step: Any) -> str:
    """Get step type from a step dict or object."""
    if isinstance(step, dict):
        return step.get("step_type", "")
    return getattr(step, "step_type", "")


def _step_field(step: Any, field_name: str) -> Any:
    """Get a field from a step dict or object."""
    if isinstance(step, dict):
        return step.get(field_name)
    return getattr(step, field_name, None)


def _step_success(step: Any) -> bool:
    """Check if a tool step succeeded."""
    if isinstance(step, dict):
        return step.get("success", True)
    return getattr(step, "success", True)
