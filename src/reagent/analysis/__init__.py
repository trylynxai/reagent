"""Analysis module - Tools for trace comparison and analytics."""

from reagent.analysis.diff import TraceDiff, StepDiff, DiffResult
from reagent.analysis.cost import CostAnalyzer, CostReport, ModelPricing
from reagent.analysis.search import SearchQuery, QueryParser, SearchEngine
from reagent.analysis.loop_detector import (
    LoopDetector,
    LoopConfig,
    LoopPattern,
    LoopDetectionResult,
)

__all__ = [
    "TraceDiff",
    "StepDiff",
    "DiffResult",
    "CostAnalyzer",
    "CostReport",
    "ModelPricing",
    "SearchQuery",
    "QueryParser",
    "SearchEngine",
    "LoopDetector",
    "LoopConfig",
    "LoopPattern",
    "LoopDetectionResult",
]
