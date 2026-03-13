"""Alert engine — evaluates rules and dispatches alerts."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from reagent.alerts.delivery import AlertDeliveryBackend
from reagent.alerts.rules import AlertContext, AlertResult, AlertRule
from reagent.schema.run import RunMetadata, RunSummary
from reagent.schema.steps import AnyStep

if TYPE_CHECKING:
    from reagent.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class AlertEngine:
    """Evaluates alert rules and dispatches results to delivery backends."""

    def __init__(
        self,
        rules: list[AlertRule] | None = None,
        delivery_backends: list[AlertDeliveryBackend] | None = None,
        storage: StorageBackend | None = None,
        recent_runs_limit: int = 50,
    ) -> None:
        self._rules = list(rules or [])
        self._delivery_backends = list(delivery_backends or [])
        self._storage = storage
        self._recent_runs_limit = recent_runs_limit
        self._last_triggered: dict[str, datetime] = {}

    @property
    def rules(self) -> list[AlertRule]:
        """Get all registered rules."""
        return list(self._rules)

    def add_rule(self, rule: AlertRule) -> None:
        """Add an alert rule."""
        self._rules.append(rule)

    def add_delivery(self, backend: AlertDeliveryBackend) -> None:
        """Add a delivery backend."""
        self._delivery_backends.append(backend)

    def check_step(
        self,
        run_metadata: RunMetadata,
        step: AnyStep,
    ) -> list[AlertResult]:
        """Check budget rules after a step is recorded.

        Only evaluates budget-type rules (cost/token thresholds)
        since failure rules need run-end context.
        """
        context = AlertContext(
            run_metadata=run_metadata,
            latest_step=step,
        )
        return self._evaluate_rules(context, alert_types={"budget"})

    def check_run_end(
        self,
        run_metadata: RunMetadata,
    ) -> list[AlertResult]:
        """Check all rules at run completion.

        Loads recent run summaries from storage for cross-run rules.
        """
        recent = self._load_recent_runs()
        context = AlertContext(
            run_metadata=run_metadata,
            recent_run_summaries=recent,
        )
        return self._evaluate_rules(context)

    def _evaluate_rules(
        self,
        context: AlertContext,
        alert_types: set[str] | None = None,
    ) -> list[AlertResult]:
        """Evaluate rules and deliver any triggered alerts."""
        results: list[AlertResult] = []

        for rule in self._rules:
            if not rule.enabled:
                continue

            # Check cooldown
            if rule.cooldown_seconds > 0:
                last = self._last_triggered.get(rule.name)
                if last is not None:
                    elapsed = (context.timestamp - last).total_seconds()
                    if elapsed < rule.cooldown_seconds:
                        continue

            try:
                result = rule.evaluate(context)
            except Exception:
                logger.warning(
                    "Alert rule '%s' evaluation failed",
                    rule.name,
                    exc_info=True,
                )
                continue

            if result is None:
                continue

            # Filter by alert type if specified
            if alert_types and result.alert_type not in alert_types:
                continue

            self._last_triggered[rule.name] = context.timestamp
            results.append(result)

            # Deliver
            for backend in self._delivery_backends:
                try:
                    backend.deliver(result)
                except Exception:
                    logger.warning(
                        "Alert delivery failed for '%s'",
                        result.rule_name,
                        exc_info=True,
                    )

        return results

    def _load_recent_runs(self) -> list[RunSummary]:
        """Load recent run summaries from storage."""
        if self._storage is None:
            return []

        try:
            from reagent.storage.base import Pagination

            return self._storage.list_runs(
                pagination=Pagination(
                    limit=self._recent_runs_limit,
                    sort_by="start_time",
                    sort_order="desc",
                ),
            )
        except Exception:
            logger.warning("Failed to load recent runs for alert evaluation", exc_info=True)
            return []
