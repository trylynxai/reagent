"""Classification module - Automatic failure categorization."""

from reagent.classification.classifier import FailureClassifier, classify_failure
from reagent.classification.ml_classifier import (
    MLFailureClassifier,
    NaiveBayesModel,
    TrainingSample,
    train_from_runs,
)

__all__ = [
    "FailureClassifier",
    "classify_failure",
    "MLFailureClassifier",
    "NaiveBayesModel",
    "TrainingSample",
    "train_from_runs",
]
