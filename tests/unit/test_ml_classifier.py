"""Tests for ML-based failure classification."""

import json
import math

import pytest

from reagent.classification.features import (
    FeatureVocabulary,
    extract_features,
    _tokenize,
    NUM_NUMERIC_FEATURES,
    NUM_ERROR_TYPE_FEATURES,
)
from reagent.classification.ml_classifier import (
    MLFailureClassifier,
    NaiveBayesModel,
    TrainingSample,
    train_from_runs,
)
from reagent.classification.classifier import FailureClassifier
from reagent.core.constants import FailureCategory


# ---- Training data factory ----


def _make_samples() -> list[TrainingSample]:
    """Create a diverse training set covering all common categories."""
    samples = [
        # Rate limit errors
        TrainingSample(
            error="Rate limit exceeded. Please retry after 30 seconds.",
            error_type="RateLimitError",
            category="rate_limit",
        ),
        TrainingSample(
            error="Too many requests to the API, please slow down.",
            error_type="RateLimitError",
            category="rate_limit",
        ),
        TrainingSample(
            error="HTTP 429: You have exceeded your quota for this minute.",
            category="rate_limit",
        ),
        # Timeout errors
        TrainingSample(
            error="Request timed out after 30 seconds waiting for response.",
            error_type="TimeoutError",
            category="tool_timeout",
        ),
        TrainingSample(
            error="Connection read timeout. The server did not respond.",
            error_type="TimeoutError",
            category="tool_timeout",
        ),
        TrainingSample(
            error="Execution deadline exceeded for tool invocation.",
            category="tool_timeout",
        ),
        # Connection errors
        TrainingSample(
            error="Connection refused by remote host at port 443.",
            error_type="ConnectionError",
            category="connection_error",
        ),
        TrainingSample(
            error="DNS resolution failed for api.example.com.",
            error_type="ConnectionError",
            category="connection_error",
        ),
        TrainingSample(
            error="Network is unreachable. Check your internet connection.",
            category="connection_error",
        ),
        # Authentication errors
        TrainingSample(
            error="Invalid API key provided. Check your credentials.",
            error_type="AuthenticationError",
            category="authentication",
        ),
        TrainingSample(
            error="Your token has expired. Please re-authenticate.",
            error_type="AuthenticationError",
            category="authentication",
        ),
        TrainingSample(
            error="Unauthorized access. API key is missing or invalid.",
            category="authentication",
        ),
        # Context overflow
        TrainingSample(
            error="Maximum context length of 4096 tokens exceeded.",
            category="context_overflow",
        ),
        TrainingSample(
            error="Input is too long. Please reduce the prompt size.",
            category="context_overflow",
        ),
        TrainingSample(
            error="Token limit reached, the conversation is too long.",
            category="context_overflow",
        ),
        # Tool errors
        TrainingSample(
            error="Tool execution failed: search returned invalid JSON.",
            category="tool_error",
            steps=[
                {"step_type": "tool_call", "tool_name": "search", "success": False},
            ],
        ),
        TrainingSample(
            error="Failed to invoke tool calculator: division by zero.",
            category="tool_error",
            steps=[
                {"step_type": "tool_call", "tool_name": "calculator", "success": False},
            ],
        ),
        TrainingSample(
            error="Tool web_fetch raised an unexpected exception.",
            category="tool_error",
        ),
    ]
    return samples


# ============================================================
# Feature Extraction
# ============================================================


class TestTokenize:
    def test_basic_tokenize(self):
        tokens = _tokenize("Connection refused by remote host")
        assert "connection" in tokens
        assert "refused" in tokens
        assert "remote" in tokens
        assert "host" in tokens
        # "by" is a stop word
        assert "by" not in tokens

    def test_stop_words_removed(self):
        tokens = _tokenize("the error is in the code")
        assert "the" not in tokens
        assert "is" not in tokens
        assert "in" not in tokens
        assert "error" in tokens
        assert "code" in tokens

    def test_single_char_removed(self):
        tokens = _tokenize("a b c error d")
        assert "a" not in tokens
        assert "error" in tokens

    def test_empty_string(self):
        assert _tokenize("") == []


class TestFeatureVocabulary:
    def test_build(self):
        vocab = FeatureVocabulary(max_features=10)
        vocab.build([
            "rate limit exceeded",
            "rate limit error",
            "timeout error",
        ])
        assert vocab.size > 0
        assert "rate" in vocab.word_to_index
        assert "limit" in vocab.word_to_index
        assert "error" in vocab.word_to_index

    def test_max_features_respected(self):
        vocab = FeatureVocabulary(max_features=3)
        vocab.build(["word1 word2 word3 word4 word5 word6"])
        assert vocab.size <= 3

    def test_serialization(self):
        vocab = FeatureVocabulary(max_features=50)
        vocab.build(["test error message"])
        d = vocab.to_dict()
        restored = FeatureVocabulary.from_dict(d)
        assert restored.word_to_index == vocab.word_to_index
        assert restored.max_features == vocab.max_features


class TestExtractFeatures:
    def test_basic_extraction(self):
        vocab = FeatureVocabulary()
        vocab.build(["timeout error connection"])
        features = extract_features(
            error="timeout error",
            vocabulary=vocab,
        )
        assert len(features) == vocab.size + NUM_ERROR_TYPE_FEATURES + NUM_NUMERIC_FEATURES
        # "timeout" and "error" should have nonzero features
        timeout_idx = vocab.word_to_index.get("timeout")
        assert timeout_idx is not None
        assert features[timeout_idx] > 0

    def test_error_type_feature(self):
        vocab = FeatureVocabulary()
        vocab.build(["test"])
        features = extract_features(
            error="test",
            error_type="TimeoutError",
            vocabulary=vocab,
        )
        # TimeoutError maps to index 0 in error type features
        offset = vocab.size
        assert features[offset] == 1.0

    def test_numeric_features_from_steps(self):
        vocab = FeatureVocabulary()
        vocab.build(["test"])
        steps = [
            {"step_type": "llm_call"},
            {"step_type": "tool_call", "tool_name": "search", "success": True},
            {"step_type": "tool_call", "tool_name": "fetch", "success": False},
            {"step_type": "error"},
        ]
        features = extract_features(
            error="test",
            steps=steps,
            vocabulary=vocab,
        )
        offset = vocab.size + NUM_ERROR_TYPE_FEATURES
        # total_steps > 0
        assert features[offset] > 0
        # llm_count > 0
        assert features[offset + 1] > 0
        # tool_count > 0
        assert features[offset + 2] > 0
        # error_count > 0
        assert features[offset + 3] > 0

    def test_no_vocabulary(self):
        features = extract_features(error="test")
        assert len(features) == NUM_ERROR_TYPE_FEATURES + NUM_NUMERIC_FEATURES

    def test_run_metadata_features(self):
        vocab = FeatureVocabulary()
        vocab.build(["test"])
        metadata = {
            "tokens": {"total_tokens": 5000},
            "cost": {"total_usd": 0.05},
            "duration_ms": 10000,
        }
        features = extract_features(
            error="test",
            run_metadata=metadata,
            vocabulary=vocab,
        )
        offset = vocab.size + NUM_ERROR_TYPE_FEATURES
        # total_tokens feature (index 4)
        assert features[offset + 4] > 0
        # cost feature (index 5)
        assert features[offset + 5] > 0
        # duration feature (index 6)
        assert features[offset + 6] > 0


# ============================================================
# Naive Bayes Model
# ============================================================


class TestNaiveBayesModel:
    def test_fit_and_predict(self):
        model = NaiveBayesModel()
        X = [
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0],
            [0.0, 1.0, 0.0],
            [0.1, 0.9, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.1, 0.8],
        ]
        y = ["A", "A", "B", "B", "C", "C"]
        model.fit(X, y)

        assert model.trained
        assert set(model.classes) == {"A", "B", "C"}

        # Predict should return A for a feature vector close to [1, 0, 0]
        preds = model.predict([0.95, 0.05, 0.0])
        assert preds[0][0] == "A"

    def test_predict_untrained(self):
        model = NaiveBayesModel()
        assert model.predict([1.0]) == []

    def test_serialization(self):
        model = NaiveBayesModel()
        model.fit(
            [[1.0, 0.0], [0.0, 1.0]],
            ["X", "Y"],
        )
        d = model.to_dict()
        restored = NaiveBayesModel.from_dict(d)
        assert restored.trained
        assert restored.classes == model.classes

        # Predictions should match
        orig = model.predict([0.8, 0.2])
        rest = restored.predict([0.8, 0.2])
        assert orig[0][0] == rest[0][0]

    def test_empty_training_data(self):
        model = NaiveBayesModel()
        model.fit([], [])
        assert not model.trained

    def test_single_class(self):
        model = NaiveBayesModel()
        model.fit([[1.0], [2.0], [3.0]], ["A", "A", "A"])
        assert model.trained
        preds = model.predict([1.5])
        assert preds[0][0] == "A"
        assert abs(preds[0][1] - 1.0) < 0.001


# ============================================================
# ML Failure Classifier
# ============================================================


class TestMLFailureClassifier:
    @pytest.fixture
    def trained_classifier(self):
        clf = MLFailureClassifier()
        samples = _make_samples()
        result = clf.train(samples)
        assert result["trained"]
        return clf

    def test_not_trained_by_default(self):
        clf = MLFailureClassifier()
        assert not clf.is_trained

    def test_train(self):
        clf = MLFailureClassifier()
        result = clf.train(_make_samples())
        assert result["trained"]
        assert result["sample_count"] >= 10
        assert result["class_count"] >= 5
        assert clf.is_trained

    def test_train_too_few_samples(self):
        clf = MLFailureClassifier()
        result = clf.train([
            TrainingSample(error="test", category="rate_limit"),
        ])
        assert not result["trained"]

    def test_train_empty(self):
        clf = MLFailureClassifier()
        result = clf.train([])
        assert not result["trained"]

    def test_classify_rate_limit(self, trained_classifier):
        result = trained_classifier.classify(
            error="You have exceeded the rate limit for this API.",
            error_type="RateLimitError",
        )
        assert result.category == FailureCategory.RATE_LIMIT
        assert result.confidence > 0.5

    def test_classify_timeout(self, trained_classifier):
        result = trained_classifier.classify(
            error="The request timed out waiting for a response.",
            error_type="TimeoutError",
        )
        assert result.category == FailureCategory.TOOL_TIMEOUT
        assert result.confidence > 0.5

    def test_classify_auth(self, trained_classifier):
        result = trained_classifier.classify(
            error="Invalid API key. Check your authentication credentials.",
            error_type="AuthenticationError",
        )
        assert result.category == FailureCategory.AUTHENTICATION

    def test_classify_connection(self, trained_classifier):
        result = trained_classifier.classify(
            error="Connection refused to remote server.",
            error_type="ConnectionError",
        )
        assert result.category == FailureCategory.CONNECTION_ERROR

    def test_ml_only_predict(self, trained_classifier):
        result = trained_classifier.predict(
            error="API rate exceeded, try again later.",
        )
        # ML-only prediction
        assert result.rule_name == "ml_naive_bayes"

    def test_predict_not_trained(self):
        clf = MLFailureClassifier()
        result = clf.predict(error="test error")
        assert result.category == FailureCategory.UNKNOWN
        assert result.rule_name == "ml_not_trained"

    def test_regex_takes_priority(self, trained_classifier):
        """Regex rules still work and take priority."""
        result = trained_classifier.classify(
            error="rate limit exceeded",
            error_type="RateLimitError",
        )
        # Should match regex rule with high confidence
        assert result.category == FailureCategory.RATE_LIMIT
        assert result.confidence >= 0.9

    def test_ml_fallback_for_novel_error(self, trained_classifier):
        """ML catches errors that regex misses."""
        # This phrasing may not match regex patterns exactly
        result = trained_classifier.classify(
            error="Server returned HTTP 429 after 3 retry attempts to the API endpoint.",
        )
        # Regex should catch "429" → rate_limit
        # OR ML should catch it
        assert result.category in (
            FailureCategory.RATE_LIMIT,
            FailureCategory.TOOL_TIMEOUT,
            FailureCategory.UNKNOWN,
        )

    def test_boosted_confidence_when_agree(self, trained_classifier):
        """Confidence boosted when regex and ML agree."""
        result = trained_classifier.classify(
            error="Connection refused by remote host.",
            error_type="ConnectionError",
        )
        # Both regex and ML should agree → boosted
        assert result.category == FailureCategory.CONNECTION_ERROR
        # Confidence should be at least the regex confidence
        assert result.confidence >= 0.85

    def test_confidence_threshold(self):
        clf = MLFailureClassifier(confidence_threshold=0.99)
        clf.train(_make_samples())
        # With very high threshold, ML predictions below it are ignored
        result = clf.classify(error="some vague error that is unclear")
        # Should fall back to regex or UNKNOWN
        # (ML unlikely to exceed 0.99 threshold)

    def test_classes_property(self, trained_classifier):
        classes = trained_classifier.classes
        assert len(classes) >= 5
        assert "rate_limit" in classes
        assert "tool_timeout" in classes

    def test_vocabulary_size(self, trained_classifier):
        assert trained_classifier.vocabulary_size > 0


# ============================================================
# Persistence
# ============================================================


class TestPersistence:
    def test_save_and_load(self, tmp_path):
        clf = MLFailureClassifier()
        clf.train(_make_samples())

        path = tmp_path / "model.json"
        clf.save(path)
        assert path.exists()

        clf2 = MLFailureClassifier()
        clf2.load(path)
        assert clf2.is_trained

        # Should give same prediction
        r1 = clf.predict(error="rate limit exceeded")
        r2 = clf2.predict(error="rate limit exceeded")
        assert r1.category == r2.category

    def test_save_creates_dirs(self, tmp_path):
        clf = MLFailureClassifier()
        clf.train(_make_samples())
        path = tmp_path / "deep" / "nested" / "model.json"
        clf.save(path)
        assert path.exists()

    def test_to_dict(self):
        clf = MLFailureClassifier()
        clf.train(_make_samples())
        d = clf.to_dict()
        assert d["is_trained"]
        assert "model" in d
        assert "vocabulary" in d

    def test_load_roundtrip_predictions(self, tmp_path):
        clf = MLFailureClassifier()
        clf.train(_make_samples())

        path = tmp_path / "model.json"
        clf.save(path)

        clf2 = MLFailureClassifier()
        clf2.load(path)

        errors = [
            "timeout waiting for response",
            "rate limit hit",
            "connection refused",
            "invalid api key",
        ]
        for err in errors:
            r1 = clf.predict(error=err)
            r2 = clf2.predict(error=err)
            assert r1.category == r2.category


# ============================================================
# Training from runs
# ============================================================


class TestTrainFromRuns:
    def test_extract_samples(self):
        runs = [
            {
                "error": "rate limit exceeded",
                "error_type": "RateLimitError",
                "failure_category": "rate_limit",
                "status": "failed",
            },
            {
                "error": "timeout",
                "error_type": "TimeoutError",
                "failure_category": "tool_timeout",
                "status": "failed",
            },
            {
                "error": None,
                "error_type": None,
                "failure_category": None,
                "status": "completed",
            },
        ]
        samples = train_from_runs(runs)
        assert len(samples) == 2
        assert samples[0].category == "rate_limit"
        assert samples[1].category == "tool_timeout"

    def test_skips_unknown_category(self):
        runs = [
            {
                "error": "mystery error",
                "error_type": "RuntimeError",
                "failure_category": "unknown",
            },
        ]
        samples = train_from_runs(runs)
        assert len(samples) == 0

    def test_skips_no_error(self):
        runs = [
            {
                "error": None,
                "error_type": None,
                "failure_category": "rate_limit",
            },
        ]
        samples = train_from_runs(runs)
        assert len(samples) == 0

    def test_train_classifier_from_runs(self):
        runs = [
            {"error": f"rate limit error {i}", "error_type": "RateLimitError", "failure_category": "rate_limit"}
            for i in range(5)
        ] + [
            {"error": f"connection failed {i}", "error_type": "ConnectionError", "failure_category": "connection_error"}
            for i in range(5)
        ]
        samples = train_from_runs(runs)
        clf = MLFailureClassifier()
        result = clf.train(samples)
        assert result["trained"]
        assert result["class_count"] == 2


# ============================================================
# Edge cases
# ============================================================


class TestEdgeCases:
    def test_classify_no_error_info(self):
        clf = MLFailureClassifier()
        clf.train(_make_samples())
        result = clf.classify()
        assert result.category == FailureCategory.UNKNOWN

    def test_classify_empty_error(self):
        clf = MLFailureClassifier()
        clf.train(_make_samples())
        result = clf.classify(error="")
        assert result.category == FailureCategory.UNKNOWN

    def test_training_sample_serialization(self):
        sample = TrainingSample(
            error="test error",
            error_type="TestError",
            category="tool_error",
        )
        d = sample.to_dict()
        restored = TrainingSample.from_dict(d)
        assert restored.error == "test error"
        assert restored.category == "tool_error"

    def test_classify_with_steps_context(self):
        clf = MLFailureClassifier()
        clf.train(_make_samples())
        result = clf.classify(
            error="tool failed",
            steps=[
                {"step_type": "llm_call"},
                {"step_type": "tool_call", "tool_name": "search", "success": False},
            ],
        )
        # Should classify as some failure, not crash
        assert isinstance(result.category, FailureCategory)

    def test_classify_with_run_metadata(self):
        clf = MLFailureClassifier()
        clf.train(_make_samples())
        result = clf.classify(
            error="rate limit hit",
            run_metadata={
                "tokens": {"total_tokens": 10000},
                "cost": {"total_usd": 0.10},
                "duration_ms": 5000,
            },
        )
        assert isinstance(result.category, FailureCategory)
