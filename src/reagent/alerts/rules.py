"""Alert rule definitions for budget and failure monitoring.

Each rule evaluates an AlertContext and returns an AlertResult if triggered.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from reagent.core.constants import AlertSeverity, FailureCategory, Status
from reagent.schema.run import RunMetadata, RunSummary


class AlertContext(BaseModel):
    """Snapshot of current state passed to rule evaluation."""

    run_metadata: RunMetadata
    latest_step: Any | None = None
    recent_run_summaries: list[RunSummary] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AlertResult(BaseModel):
    """Result of an alert rule being triggered."""

    rule_name: str
    alert_type: str  # "budget" or "failure"
    severity: AlertSeverity
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    run_id: UUID
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AlertRule(ABC, BaseModel):
    """Base class for all alert rules."""

    name: str
    enabled: bool = True
    cooldown_seconds: float = 0

    @abstractmethod
    def evaluate(self, context: AlertContext) -> AlertResult | None:
        """Evaluate the rule against the given context."""


# ============================================================
# Budget Rules
# ============================================================


class CostThresholdRule(AlertRule):
    """Alert when run cost exceeds a threshold."""

    max_cost_usd: float
    severity: AlertSeverity = AlertSeverity.WARNING

    def evaluate(self, context: AlertContext) -> AlertResult | None:
        cost = context.run_metadata.cost.total_usd
        if cost > self.max_cost_usd:
            return AlertResult(
                rule_name=self.name,
                alert_type="budget",
                severity=self.severity,
                message=(
                    f"Run cost ${cost:.4f} exceeds "
                    f"threshold ${self.max_cost_usd:.4f}"
                ),
                details={"cost_usd": cost, "threshold_usd": self.max_cost_usd},
                run_id=context.run_metadata.run_id,
            )
        return None


class TokenThresholdRule(AlertRule):
    """Alert when token usage exceeds a threshold."""

    max_tokens: int
    severity: AlertSeverity = AlertSeverity.WARNING

    def evaluate(self, context: AlertContext) -> AlertResult | None:
        tokens = context.run_metadata.tokens.total_tokens
        if tokens > self.max_tokens:
            return AlertResult(
                rule_name=self.name,
                alert_type="budget",
                severity=self.severity,
                message=(
                    f"Token usage {tokens} exceeds "
                    f"threshold {self.max_tokens}"
                ),
                details={"total_tokens": tokens, "threshold": self.max_tokens},
                run_id=context.run_metadata.run_id,
            )
        return None


class ModelSpendCapRule(AlertRule):
    """Alert when spending on a specific model exceeds a cap."""

    model: str
    max_cost_usd: float
    severity: AlertSeverity = AlertSeverity.WARNING

    def evaluate(self, context: AlertContext) -> AlertResult | None:
        cost = context.run_metadata.cost.by_model.get(self.model, 0.0)
        if cost > self.max_cost_usd:
            return AlertResult(
                rule_name=self.name,
                alert_type="budget",
                severity=self.severity,
                message=(
                    f"Model '{self.model}' cost ${cost:.4f} exceeds "
                    f"cap ${self.max_cost_usd:.4f}"
                ),
                details={
                    "model": self.model,
                    "cost_usd": cost,
                    "cap_usd": self.max_cost_usd,
                },
                run_id=context.run_metadata.run_id,
            )
        return None


# ============================================================
# Failure Rules
# ============================================================


class ErrorRateRule(AlertRule):
    """Alert when error rate exceeds a threshold within a time window."""

    max_failures: int
    window_minutes: int
    severity: AlertSeverity = AlertSeverity.CRITICAL

    def evaluate(self, context: AlertContext) -> AlertResult | None:
        cutoff = context.timestamp - timedelta(minutes=self.window_minutes)
        failures = [
            s for s in context.recent_run_summaries
            if s.status == Status.FAILED
            and s.start_time >= cutoff
        ]
        if len(failures) >= self.max_failures:
            return AlertResult(
                rule_name=self.name,
                alert_type="failure",
                severity=self.severity,
                message=(
                    f"{len(failures)} failures in last "
                    f"{self.window_minutes} minutes "
                    f"(threshold: {self.max_failures})"
                ),
                details={
                    "failure_count": len(failures),
                    "window_minutes": self.window_minutes,
                    "threshold": self.max_failures,
                },
                run_id=context.run_metadata.run_id,
            )
        return None


class FailureCategoryRule(AlertRule):
    """Alert when a run fails with a specific failure category."""

    categories: list[str]  # FailureCategory values as strings
    severity: AlertSeverity = AlertSeverity.CRITICAL

    def evaluate(self, context: AlertContext) -> AlertResult | None:
        cat = context.run_metadata.failure_category
        if cat and cat in self.categories:
            return AlertResult(
                rule_name=self.name,
                alert_type="failure",
                severity=self.severity,
                message=f"Run failed with category: {cat}",
                details={
                    "failure_category": cat,
                    "watched_categories": self.categories,
                },
                run_id=context.run_metadata.run_id,
            )
        return None


class ConsecutiveFailureRule(AlertRule):
    """Alert when there are N consecutive run failures."""

    max_consecutive: int
    severity: AlertSeverity = AlertSeverity.CRITICAL

    def evaluate(self, context: AlertContext) -> AlertResult | None:
        # Count consecutive failures from most recent
        consecutive = 0
        for summary in context.recent_run_summaries:
            if summary.status == Status.FAILED:
                consecutive += 1
            else:
                break

        if consecutive >= self.max_consecutive:
            return AlertResult(
                rule_name=self.name,
                alert_type="failure",
                severity=self.severity,
                message=(
                    f"{consecutive} consecutive run failures "
                    f"(threshold: {self.max_consecutive})"
                ),
                details={
                    "consecutive_failures": consecutive,
                    "threshold": self.max_consecutive,
                },
                run_id=context.run_metadata.run_id,
            )
        return None
