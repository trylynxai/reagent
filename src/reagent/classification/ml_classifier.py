"""ML-based failure classification.

A lightweight Naive Bayes classifier that learns from previously
labeled failure runs to classify novel errors. Works alongside
the existing regex-based FailureClassifier in a fallback chain:

1. Regex rules (high confidence, exact patterns)
2. ML classifier (medium confidence, generalized patterns)
3. Context heuristics (low confidence, fallback)

Pure Python implementation — no sklearn, numpy, or scipy required.
Model state can be serialized to JSON for persistence.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reagent.classification.classifier import (
    ClassificationResult,
    FailureClassifier,
)
from reagent.classification.features import (
    FeatureVocabulary,
    extract_features,
)
from reagent.core.constants import FailureCategory


# ============================================================
# Pure-Python Naive Bayes
# ============================================================


@dataclass
class NaiveBayesModel:
    """Gaussian Naive Bayes classifier.

    For each class (FailureCategory) and each feature dimension,
    stores the mean and variance observed in training data.
    Prediction uses log-probabilities with Laplace smoothing.
    """

    classes: list[str] = field(default_factory=list)
    class_log_priors: dict[str, float] = field(default_factory=dict)
    feature_means: dict[str, list[float]] = field(default_factory=dict)
    feature_vars: dict[str, list[float]] = field(default_factory=dict)
    n_features: int = 0
    trained: bool = False

    # Smoothing to avoid zero variance
    _var_smoothing: float = 1e-9

    def fit(
        self,
        X: list[list[float]],
        y: list[str],
    ) -> None:
        """Train the model on feature vectors and labels.

        Args:
            X: List of feature vectors (same length each).
            y: List of category labels (same length as X).
        """
        if not X or not y or len(X) != len(y):
            return

        self.n_features = len(X[0])
        total = len(y)

        # Group samples by class
        by_class: dict[str, list[list[float]]] = defaultdict(list)
        for features, label in zip(X, y):
            by_class[label].append(features)

        self.classes = sorted(by_class.keys())

        for cls in self.classes:
            samples = by_class[cls]
            n = len(samples)

            # Log prior
            self.class_log_priors[cls] = math.log(n / total)

            # Compute mean and variance per feature
            means = [0.0] * self.n_features
            for sample in samples:
                for i, val in enumerate(sample):
                    means[i] += val
            means = [m / n for m in means]

            variances = [0.0] * self.n_features
            for sample in samples:
                for i, val in enumerate(sample):
                    variances[i] += (val - means[i]) ** 2
            variances = [v / n + self._var_smoothing for v in variances]

            self.feature_means[cls] = means
            self.feature_vars[cls] = variances

        self.trained = True

    def predict(self, features: list[float]) -> list[tuple[str, float]]:
        """Predict class probabilities for a feature vector.

        Returns:
            List of (class_name, probability) sorted by probability descending.
        """
        if not self.trained:
            return []

        log_probs: dict[str, float] = {}

        for cls in self.classes:
            log_prob = self.class_log_priors[cls]
            means = self.feature_means[cls]
            variances = self.feature_vars[cls]

            for i, val in enumerate(features):
                if i >= len(means):
                    break
                mean = means[i]
                var = variances[i]
                # Gaussian log-likelihood
                log_prob += -0.5 * math.log(2 * math.pi * var)
                log_prob += -0.5 * ((val - mean) ** 2) / var

            log_probs[cls] = log_prob

        # Convert to probabilities via log-sum-exp
        max_log = max(log_probs.values())
        exp_sum = sum(math.exp(lp - max_log) for lp in log_probs.values())
        log_norm = max_log + math.log(exp_sum)

        probs = {
            cls: math.exp(lp - log_norm)
            for cls, lp in log_probs.items()
        }

        return sorted(probs.items(), key=lambda x: x[1], reverse=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "classes": self.classes,
            "class_log_priors": self.class_log_priors,
            "feature_means": self.feature_means,
            "feature_vars": self.feature_vars,
            "n_features": self.n_features,
            "trained": self.trained,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NaiveBayesModel:
        return cls(
            classes=data["classes"],
            class_log_priors=data["class_log_priors"],
            feature_means=data["feature_means"],
            feature_vars=data["feature_vars"],
            n_features=data["n_features"],
            trained=data["trained"],
        )


# ============================================================
# Training sample
# ============================================================


@dataclass
class TrainingSample:
    """A labeled training example for the ML classifier."""

    error: str | None = None
    error_type: str | None = None
    traceback_str: str | None = None
    steps: list[dict[str, Any]] | None = None
    run_metadata: dict[str, Any] | None = None
    category: str = ""  # FailureCategory value

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.error,
            "error_type": self.error_type,
            "traceback_str": self.traceback_str,
            "steps": self.steps,
            "run_metadata": self.run_metadata,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrainingSample:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ============================================================
# ML Failure Classifier
# ============================================================


class MLFailureClassifier:
    """ML-based failure classifier with regex fallback.

    Combines the existing regex-based FailureClassifier with a
    trained Naive Bayes model. Classification flow:

    1. Try regex rules first (high confidence)
    2. If regex returns UNKNOWN, try ML prediction
    3. If both regex and ML agree, boost confidence
    4. Fall back to context heuristics

    The ML model is trained from previously classified runs
    and can be saved/loaded for persistence.
    """

    def __init__(
        self,
        rule_classifier: FailureClassifier | None = None,
        confidence_threshold: float = 0.5,
    ) -> None:
        """Initialize the ML classifier.

        Args:
            rule_classifier: Existing regex-based classifier.
                Defaults to a new FailureClassifier instance.
            confidence_threshold: Minimum ML confidence to accept
                a prediction (0.0 to 1.0). Default 0.5.
        """
        self._rule_classifier = rule_classifier or FailureClassifier()
        self._confidence_threshold = confidence_threshold
        self._model = NaiveBayesModel()
        self._vocabulary = FeatureVocabulary()
        self._trained = False

    @property
    def is_trained(self) -> bool:
        """Whether the ML model has been trained."""
        return self._trained and self._model.trained

    @property
    def vocabulary_size(self) -> int:
        return self._vocabulary.size

    @property
    def classes(self) -> list[str]:
        """The failure categories the model knows about."""
        return self._model.classes if self._model.trained else []

    def train(self, samples: list[TrainingSample]) -> dict[str, Any]:
        """Train the ML model from labeled samples.

        Args:
            samples: List of TrainingSample with category labels.

        Returns:
            Training summary dict with stats.
        """
        if not samples:
            return {"error": "No training samples provided", "trained": False}

        # Filter out samples without category
        labeled = [s for s in samples if s.category and s.category != "unknown"]
        if len(labeled) < 2:
            return {
                "error": "Need at least 2 labeled samples",
                "trained": False,
                "sample_count": len(labeled),
            }

        # Build vocabulary from error messages and tracebacks
        texts: list[str] = []
        for sample in labeled:
            if sample.error:
                texts.append(sample.error)
            if sample.traceback_str:
                texts.append(sample.traceback_str)
        self._vocabulary.build(texts)

        # Extract features
        X: list[list[float]] = []
        y: list[str] = []

        for sample in labeled:
            features = extract_features(
                error=sample.error,
                error_type=sample.error_type,
                traceback_str=sample.traceback_str,
                steps=sample.steps,
                run_metadata=sample.run_metadata,
                vocabulary=self._vocabulary,
            )
            X.append(features)
            y.append(sample.category)

        # Train model
        self._model.fit(X, y)
        self._trained = True

        # Compute training stats
        from collections import Counter
        class_dist = Counter(y)

        return {
            "trained": True,
            "sample_count": len(labeled),
            "vocabulary_size": self._vocabulary.size,
            "feature_count": self._model.n_features,
            "class_count": len(self._model.classes),
            "class_distribution": dict(class_dist),
        }

    def classify(
        self,
        error: str | None = None,
        error_type: str | None = None,
        traceback_str: str | None = None,
        steps: list[dict[str, Any]] | None = None,
        run_metadata: dict[str, Any] | None = None,
    ) -> ClassificationResult:
        """Classify a failure using rules + ML.

        Args:
            error: Error message string.
            error_type: Exception type name.
            traceback_str: Full traceback string.
            steps: Step dicts for context.
            run_metadata: Run metadata dict.

        Returns:
            ClassificationResult with category and confidence.
        """
        # Step 1: Try regex rules
        rule_result = self._rule_classifier.classify(
            error=error,
            error_type=error_type,
            traceback_str=traceback_str,
            steps=steps,
        )

        # Step 2: Try ML if trained and we have some error info
        ml_result: ClassificationResult | None = None
        has_error_info = bool(error and error.strip()) or bool(error_type)
        if self.is_trained and has_error_info:
            ml_result = self._ml_predict(
                error=error,
                error_type=error_type,
                traceback_str=traceback_str,
                steps=steps,
                run_metadata=run_metadata,
            )

        # Step 3: Combine results
        return self._combine_results(rule_result, ml_result)

    def predict(
        self,
        error: str | None = None,
        error_type: str | None = None,
        traceback_str: str | None = None,
        steps: list[dict[str, Any]] | None = None,
        run_metadata: dict[str, Any] | None = None,
    ) -> ClassificationResult:
        """ML-only prediction (no regex rules).

        Useful for evaluating the ML model independently.
        """
        if not self.is_trained:
            return ClassificationResult(
                category=FailureCategory.UNKNOWN,
                confidence=0.0,
                rule_name="ml_not_trained",
                details="ML model has not been trained",
            )

        return self._ml_predict(
            error=error,
            error_type=error_type,
            traceback_str=traceback_str,
            steps=steps,
            run_metadata=run_metadata,
        )

    def _ml_predict(
        self,
        error: str | None,
        error_type: str | None,
        traceback_str: str | None,
        steps: list[dict[str, Any]] | None,
        run_metadata: dict[str, Any] | None,
    ) -> ClassificationResult:
        """Run ML prediction only."""
        features = extract_features(
            error=error,
            error_type=error_type,
            traceback_str=traceback_str,
            steps=steps,
            run_metadata=run_metadata,
            vocabulary=self._vocabulary,
        )

        predictions = self._model.predict(features)
        if not predictions:
            return ClassificationResult(
                category=FailureCategory.UNKNOWN,
                confidence=0.0,
                rule_name="ml_no_prediction",
            )

        top_class, top_prob = predictions[0]

        try:
            category = FailureCategory(top_class)
        except ValueError:
            category = FailureCategory.UNKNOWN

        return ClassificationResult(
            category=category,
            confidence=round(top_prob, 4),
            rule_name="ml_naive_bayes",
            details=f"ML prediction: {top_class} ({top_prob:.2%})",
        )

    def _combine_results(
        self,
        rule_result: ClassificationResult,
        ml_result: ClassificationResult | None,
    ) -> ClassificationResult:
        """Combine regex and ML results.

        Strategy:
        - If regex matched (not UNKNOWN): use it, boost if ML agrees
        - If regex is UNKNOWN and ML passes threshold: use ML
        - Otherwise: return regex result (may be UNKNOWN)
        """
        rule_matched = rule_result.category != FailureCategory.UNKNOWN

        if ml_result is None:
            return rule_result

        ml_passes = (
            ml_result.category != FailureCategory.UNKNOWN
            and ml_result.confidence >= self._confidence_threshold
        )

        if rule_matched and ml_passes:
            if rule_result.category == ml_result.category:
                # Both agree: boost confidence
                boosted = min(1.0, rule_result.confidence * 1.1)
                return ClassificationResult(
                    category=rule_result.category,
                    confidence=round(boosted, 4),
                    rule_name=f"{rule_result.rule_name}+ml",
                    details=(
                        f"Rule and ML agree: {rule_result.category.value} "
                        f"(rule={rule_result.confidence:.2f}, ml={ml_result.confidence:.2f})"
                    ),
                )
            else:
                # Disagree: trust the higher confidence
                if rule_result.confidence >= ml_result.confidence:
                    return rule_result
                return ml_result

        if rule_matched:
            return rule_result

        if ml_passes:
            return ml_result

        return rule_result

    # ── Persistence ───────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        """Save the trained model to a JSON file.

        Args:
            path: File path to write to.
        """
        data = {
            "model": self._model.to_dict(),
            "vocabulary": self._vocabulary.to_dict(),
            "confidence_threshold": self._confidence_threshold,
            "version": "1.0",
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))

    def load(self, path: str | Path) -> None:
        """Load a trained model from a JSON file.

        Args:
            path: File path to read from.
        """
        path = Path(path)
        data = json.loads(path.read_text())
        self._model = NaiveBayesModel.from_dict(data["model"])
        self._vocabulary = FeatureVocabulary.from_dict(data["vocabulary"])
        self._confidence_threshold = data.get("confidence_threshold", 0.5)
        self._trained = self._model.trained

    def to_dict(self) -> dict[str, Any]:
        """Serialize classifier state to a dict."""
        return {
            "model": self._model.to_dict(),
            "vocabulary": self._vocabulary.to_dict(),
            "confidence_threshold": self._confidence_threshold,
            "is_trained": self.is_trained,
        }


def train_from_runs(
    runs: list[dict[str, Any]],
) -> list[TrainingSample]:
    """Convert classified run metadata dicts to training samples.

    Extracts runs that have a failure_category set (by regex or human)
    and converts them into TrainingSample objects.

    Args:
        runs: List of run metadata dicts (from RunMetadata.model_dump()).

    Returns:
        List of TrainingSample objects for training.
    """
    samples: list[TrainingSample] = []

    for run in runs:
        category = run.get("failure_category")
        if not category or category == "unknown":
            continue

        error = run.get("error")
        error_type = run.get("error_type")
        if not error and not error_type:
            continue

        samples.append(TrainingSample(
            error=error,
            error_type=error_type,
            run_metadata=run,
            category=category,
        ))

    return samples
