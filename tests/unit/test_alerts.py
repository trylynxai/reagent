"""Tests for the budget and failure alert system."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from reagent.alerts.delivery import (
    CallbackDelivery,
    LogDelivery,
    WebhookDelivery,
)
from reagent.alerts.engine import AlertEngine
from reagent.alerts.rules import (
    AlertContext,
    AlertResult,
    ConsecutiveFailureRule,
    CostThresholdRule,
    ErrorRateRule,
    FailureCategoryRule,
    ModelSpendCapRule,
    TokenThresholdRule,
)
from reagent.core.constants import AlertSeverity, FailureCategory, Status
from reagent.schema.run import CostSummary, RunMetadata, RunSummary, TokenSummary


# ---- Helpers ----


def _make_metadata(
    cost_usd: float = 0.0,
    total_tokens: int = 0,
    by_model: dict | None = None,
    failure_category: str | None = None,
    status: Status = Status.RUNNING,
) -> RunMetadata:
    run_id = uuid4()
    return RunMetadata(
        run_id=run_id,
        start_time=datetime.utcnow(),
        status=status,
        cost=CostSummary(
            total_usd=cost_usd,
            by_model=by_model or {},
        ),
        tokens=TokenSummary(total_tokens=total_tokens),
        failure_category=failure_category,
    )


def _make_summary(
    status: Status = Status.COMPLETED,
    start_time: datetime | None = None,
    failure_category: str | None = None,
) -> RunSummary:
    return RunSummary(
        run_id=uuid4(),
        start_time=start_time or datetime.utcnow(),
        status=status,
        failure_category=failure_category,
    )


def _make_context(
    metadata: RunMetadata | None = None,
    recent: list[RunSummary] | None = None,
) -> AlertContext:
    return AlertContext(
        run_metadata=metadata or _make_metadata(),
        recent_run_summaries=recent or [],
    )


# ============================================================
# Rule Tests
# ============================================================


class TestCostThresholdRule:
    def test_not_triggered_under_threshold(self):
        rule = CostThresholdRule(name="cost", max_cost_usd=5.0)
        ctx = _make_context(_make_metadata(cost_usd=2.0))
        assert rule.evaluate(ctx) is None

    def test_triggered_over_threshold(self):
        rule = CostThresholdRule(name="cost", max_cost_usd=5.0)
        ctx = _make_context(_make_metadata(cost_usd=7.50))
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.alert_type == "budget"
        assert result.rule_name == "cost"
        assert result.details["cost_usd"] == 7.50

    def test_exact_threshold_not_triggered(self):
        rule = CostThresholdRule(name="cost", max_cost_usd=5.0)
        ctx = _make_context(_make_metadata(cost_usd=5.0))
        assert rule.evaluate(ctx) is None

    def test_severity_configurable(self):
        rule = CostThresholdRule(
            name="cost", max_cost_usd=1.0, severity=AlertSeverity.CRITICAL
        )
        ctx = _make_context(_make_metadata(cost_usd=2.0))
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.severity == AlertSeverity.CRITICAL


class TestTokenThresholdRule:
    def test_not_triggered(self):
        rule = TokenThresholdRule(name="tokens", max_tokens=10000)
        ctx = _make_context(_make_metadata(total_tokens=5000))
        assert rule.evaluate(ctx) is None

    def test_triggered(self):
        rule = TokenThresholdRule(name="tokens", max_tokens=10000)
        ctx = _make_context(_make_metadata(total_tokens=15000))
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.details["total_tokens"] == 15000


class TestModelSpendCapRule:
    def test_triggered(self):
        rule = ModelSpendCapRule(name="gpt4-cap", model="gpt-4", max_cost_usd=1.0)
        ctx = _make_context(_make_metadata(by_model={"gpt-4": 1.50}))
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.details["model"] == "gpt-4"

    def test_model_not_present(self):
        rule = ModelSpendCapRule(name="gpt4-cap", model="gpt-4", max_cost_usd=1.0)
        ctx = _make_context(_make_metadata(by_model={"claude-3": 5.0}))
        assert rule.evaluate(ctx) is None

    def test_under_cap(self):
        rule = ModelSpendCapRule(name="gpt4-cap", model="gpt-4", max_cost_usd=10.0)
        ctx = _make_context(_make_metadata(by_model={"gpt-4": 3.0}))
        assert rule.evaluate(ctx) is None


class TestErrorRateRule:
    def test_triggered_within_window(self):
        rule = ErrorRateRule(name="err-rate", max_failures=3, window_minutes=10)
        now = datetime.utcnow()
        recent = [
            _make_summary(Status.FAILED, start_time=now - timedelta(minutes=i))
            for i in range(4)
        ]
        ctx = _make_context(recent=recent)
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.details["failure_count"] == 4

    def test_old_failures_outside_window(self):
        rule = ErrorRateRule(name="err-rate", max_failures=3, window_minutes=10)
        old = datetime.utcnow() - timedelta(minutes=30)
        recent = [_make_summary(Status.FAILED, start_time=old) for _ in range(5)]
        ctx = _make_context(recent=recent)
        assert rule.evaluate(ctx) is None

    def test_mixed_statuses(self):
        rule = ErrorRateRule(name="err-rate", max_failures=3, window_minutes=10)
        now = datetime.utcnow()
        recent = [
            _make_summary(Status.FAILED, start_time=now - timedelta(minutes=1)),
            _make_summary(Status.COMPLETED, start_time=now - timedelta(minutes=2)),
            _make_summary(Status.FAILED, start_time=now - timedelta(minutes=3)),
        ]
        ctx = _make_context(recent=recent)
        assert rule.evaluate(ctx) is None  # only 2 failures < 3


class TestFailureCategoryRule:
    def test_match(self):
        rule = FailureCategoryRule(
            name="loop-alert",
            categories=[FailureCategory.REASONING_LOOP.value],
        )
        meta = _make_metadata(failure_category="reasoning_loop")
        ctx = _make_context(meta)
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.alert_type == "failure"

    def test_no_match(self):
        rule = FailureCategoryRule(
            name="loop-alert",
            categories=[FailureCategory.REASONING_LOOP.value],
        )
        meta = _make_metadata(failure_category="tool_timeout")
        ctx = _make_context(meta)
        assert rule.evaluate(ctx) is None

    def test_no_failure_category(self):
        rule = FailureCategoryRule(
            name="loop-alert",
            categories=[FailureCategory.REASONING_LOOP.value],
        )
        ctx = _make_context(_make_metadata())
        assert rule.evaluate(ctx) is None


class TestConsecutiveFailureRule:
    def test_triggered(self):
        rule = ConsecutiveFailureRule(name="consec", max_consecutive=3)
        recent = [_make_summary(Status.FAILED) for _ in range(4)]
        ctx = _make_context(recent=recent)
        result = rule.evaluate(ctx)
        assert result is not None
        assert result.details["consecutive_failures"] == 4

    def test_broken_by_success(self):
        rule = ConsecutiveFailureRule(name="consec", max_consecutive=3)
        recent = [
            _make_summary(Status.FAILED),
            _make_summary(Status.FAILED),
            _make_summary(Status.COMPLETED),  # breaks the streak
            _make_summary(Status.FAILED),
            _make_summary(Status.FAILED),
        ]
        ctx = _make_context(recent=recent)
        assert rule.evaluate(ctx) is None  # only 2 consecutive

    def test_under_threshold(self):
        rule = ConsecutiveFailureRule(name="consec", max_consecutive=5)
        recent = [_make_summary(Status.FAILED) for _ in range(3)]
        ctx = _make_context(recent=recent)
        assert rule.evaluate(ctx) is None

    def test_empty_history(self):
        rule = ConsecutiveFailureRule(name="consec", max_consecutive=3)
        ctx = _make_context(recent=[])
        assert rule.evaluate(ctx) is None


class TestDisabledRule:
    def test_disabled_rule_skipped_by_engine(self):
        rule = CostThresholdRule(name="cost", max_cost_usd=1.0, enabled=False)
        engine = AlertEngine(rules=[rule])
        meta = _make_metadata(cost_usd=100.0)
        results = engine.check_step(meta, MagicMock())
        assert len(results) == 0


# ============================================================
# Engine Tests
# ============================================================


class TestAlertEngine:
    def test_check_step_triggers_budget_alert(self):
        rule = CostThresholdRule(name="cost", max_cost_usd=1.0)
        received = []
        delivery = CallbackDelivery(callback=received.append)
        engine = AlertEngine(rules=[rule], delivery_backends=[delivery])

        meta = _make_metadata(cost_usd=5.0)
        results = engine.check_step(meta, MagicMock())

        assert len(results) == 1
        assert results[0].rule_name == "cost"
        assert len(received) == 1

    def test_check_step_no_alert_under_threshold(self):
        rule = CostThresholdRule(name="cost", max_cost_usd=10.0)
        engine = AlertEngine(rules=[rule])

        meta = _make_metadata(cost_usd=2.0)
        results = engine.check_step(meta, MagicMock())
        assert len(results) == 0

    def test_check_run_end_triggers_failure_alert(self):
        rule = FailureCategoryRule(
            name="loop",
            categories=["reasoning_loop"],
        )
        received = []
        delivery = CallbackDelivery(callback=received.append)
        engine = AlertEngine(rules=[rule], delivery_backends=[delivery])

        meta = _make_metadata(failure_category="reasoning_loop")
        results = engine.check_run_end(meta)

        assert len(results) == 1
        assert received[0].alert_type == "failure"

    def test_cooldown_prevents_duplicate(self):
        rule = CostThresholdRule(
            name="cost", max_cost_usd=1.0, cooldown_seconds=60
        )
        engine = AlertEngine(rules=[rule])

        meta = _make_metadata(cost_usd=5.0)
        results1 = engine.check_step(meta, MagicMock())
        results2 = engine.check_step(meta, MagicMock())

        assert len(results1) == 1
        assert len(results2) == 0  # Cooled down

    def test_multiple_rules_multiple_results(self):
        rules = [
            CostThresholdRule(name="cost", max_cost_usd=1.0),
            TokenThresholdRule(name="tokens", max_tokens=100),
        ]
        engine = AlertEngine(rules=rules)

        meta = _make_metadata(cost_usd=5.0, total_tokens=500)
        results = engine.check_step(meta, MagicMock())
        assert len(results) == 2

    def test_failure_rule_not_triggered_by_check_step(self):
        """check_step only evaluates budget rules, not failure rules."""
        rule = FailureCategoryRule(
            name="loop", categories=["reasoning_loop"]
        )
        engine = AlertEngine(rules=[rule])

        meta = _make_metadata(failure_category="reasoning_loop")
        results = engine.check_step(meta, MagicMock())
        assert len(results) == 0  # Filtered out (not budget type)

    def test_add_rule_and_delivery(self):
        engine = AlertEngine()
        received = []

        engine.add_rule(CostThresholdRule(name="cost", max_cost_usd=1.0))
        engine.add_delivery(CallbackDelivery(callback=received.append))

        meta = _make_metadata(cost_usd=5.0)
        engine.check_step(meta, MagicMock())
        assert len(received) == 1


# ============================================================
# Delivery Tests
# ============================================================


class TestCallbackDelivery:
    def test_callback_invoked(self):
        received = []
        delivery = CallbackDelivery(callback=received.append)
        result = AlertResult(
            rule_name="test",
            alert_type="budget",
            severity=AlertSeverity.WARNING,
            message="test alert",
            run_id=uuid4(),
        )
        delivery.deliver(result)
        assert len(received) == 1
        assert received[0].rule_name == "test"

    def test_callback_exception_does_not_raise(self):
        def bad_callback(r):
            raise ValueError("boom")

        delivery = CallbackDelivery(callback=bad_callback)
        result = AlertResult(
            rule_name="test",
            alert_type="budget",
            severity=AlertSeverity.WARNING,
            message="test",
            run_id=uuid4(),
        )
        # Should not raise
        delivery.deliver(result)


class TestWebhookDelivery:
    def test_sends_post(self):
        delivery = WebhookDelivery(
            url="http://example.com/hook",
            headers={"X-Token": "secret"},
        )
        result = AlertResult(
            rule_name="test",
            alert_type="budget",
            severity=AlertSeverity.WARNING,
            message="test",
            run_id=uuid4(),
        )

        with patch("reagent.alerts.delivery.urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__ = MagicMock()
            mock_open.return_value.__exit__ = MagicMock()
            delivery._send(result)  # Test sync path directly

            mock_open.assert_called_once()
            req = mock_open.call_args[0][0]
            assert req.full_url == "http://example.com/hook"
            assert req.get_header("Content-type") == "application/json"
            assert req.get_header("X-token") == "secret"

    def test_failure_does_not_raise(self):
        delivery = WebhookDelivery(url="http://bad-url.invalid/hook")
        result = AlertResult(
            rule_name="test",
            alert_type="budget",
            severity=AlertSeverity.WARNING,
            message="test",
            run_id=uuid4(),
        )
        # Should not raise even with bad URL
        delivery._send(result)


class TestLogDelivery:
    def test_log_delivery(self, caplog):
        import logging

        delivery = LogDelivery()
        result = AlertResult(
            rule_name="test",
            alert_type="budget",
            severity=AlertSeverity.WARNING,
            message="cost exceeded",
            run_id=uuid4(),
        )

        with caplog.at_level(logging.WARNING, logger="reagent.alerts"):
            delivery.deliver(result)

        assert "cost exceeded" in caplog.text
