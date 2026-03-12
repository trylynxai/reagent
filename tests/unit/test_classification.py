"""Tests for the failure classification engine."""

import pytest

from reagent.classification.classifier import (
    ClassificationResult,
    ClassificationRule,
    FailureClassifier,
    classify_failure,
)
from reagent.core.constants import FailureCategory


class TestClassificationRule:
    """Tests for individual classification rules."""

    def test_match_by_error_type(self):
        rule = ClassificationRule(
            name="test",
            category=FailureCategory.TOOL_TIMEOUT,
            confidence=0.9,
            error_types=["TimeoutError"],
        )
        assert rule.matches(error=None, error_type="TimeoutError")
        assert not rule.matches(error=None, error_type="ValueError")

    def test_match_by_error_type_case_insensitive(self):
        rule = ClassificationRule(
            name="test",
            category=FailureCategory.RATE_LIMIT,
            confidence=0.9,
            error_types=["RateLimitError"],
        )
        assert rule.matches(error=None, error_type="ratelimiterror")

    def test_match_by_error_type_substring(self):
        rule = ClassificationRule(
            name="test",
            category=FailureCategory.TOOL_TIMEOUT,
            confidence=0.9,
            error_types=["Timeout"],
        )
        assert rule.matches(error=None, error_type="asyncio.TimeoutError")

    def test_match_by_error_pattern(self):
        rule = ClassificationRule(
            name="test",
            category=FailureCategory.RATE_LIMIT,
            confidence=0.8,
            error_patterns=[r"rate\s*limit", r"429"],
        )
        assert rule.matches(error="Rate limit exceeded", error_type=None)
        assert rule.matches(error="HTTP 429 Too Many Requests", error_type=None)
        assert not rule.matches(error="Connection failed", error_type=None)

    def test_match_by_traceback_pattern(self):
        rule = ClassificationRule(
            name="test",
            category=FailureCategory.TOOL_ERROR,
            confidence=0.7,
            traceback_patterns=[r"tool.*error"],
        )
        tb = "Traceback:\n  File tool_runner.py\n  ToolExecutionError"
        assert rule.matches(error=None, error_type=None, traceback_str=tb)

    def test_no_match(self):
        rule = ClassificationRule(
            name="test",
            category=FailureCategory.RATE_LIMIT,
            confidence=0.9,
            error_types=["RateLimitError"],
            error_patterns=[r"rate\s*limit"],
        )
        assert not rule.matches(error="disk full", error_type="OSError")

    def test_none_inputs(self):
        rule = ClassificationRule(
            name="test",
            category=FailureCategory.RATE_LIMIT,
            confidence=0.9,
            error_types=["RateLimitError"],
        )
        assert not rule.matches(error=None, error_type=None)


class TestFailureClassifier:
    """Tests for the FailureClassifier."""

    def test_classify_timeout(self):
        classifier = FailureClassifier()
        result = classifier.classify(
            error="Tool execution timed out after 30s",
            error_type="TimeoutError",
        )
        assert result.category == FailureCategory.TOOL_TIMEOUT
        assert result.confidence >= 0.85

    def test_classify_rate_limit(self):
        classifier = FailureClassifier()
        result = classifier.classify(
            error="Rate limit exceeded. Please retry after 60s",
            error_type="RateLimitError",
        )
        assert result.category == FailureCategory.RATE_LIMIT
        assert result.confidence >= 0.90

    def test_classify_rate_limit_429(self):
        classifier = FailureClassifier()
        result = classifier.classify(error="HTTP 429 Too Many Requests")
        assert result.category == FailureCategory.RATE_LIMIT

    def test_classify_context_overflow(self):
        classifier = FailureClassifier()
        result = classifier.classify(
            error="This model's maximum context length is 8192 tokens. "
            "However, your messages resulted in 10500 tokens.",
        )
        assert result.category == FailureCategory.CONTEXT_OVERFLOW

    def test_classify_context_overflow_token_limit(self):
        classifier = FailureClassifier()
        result = classifier.classify(error="Token limit exceeded")
        assert result.category == FailureCategory.CONTEXT_OVERFLOW

    def test_classify_authentication(self):
        classifier = FailureClassifier()
        result = classifier.classify(
            error="Invalid API key provided",
            error_type="AuthenticationError",
        )
        assert result.category == FailureCategory.AUTHENTICATION
        assert result.confidence >= 0.85

    def test_classify_auth_401(self):
        classifier = FailureClassifier()
        result = classifier.classify(error="401 Unauthorized")
        assert result.category == FailureCategory.AUTHENTICATION

    def test_classify_validation(self):
        classifier = FailureClassifier()
        result = classifier.classify(
            error="Invalid argument: temperature must be between 0 and 2",
            error_type="ValidationError",
        )
        assert result.category == FailureCategory.VALIDATION_ERROR

    def test_classify_connection_error(self):
        classifier = FailureClassifier()
        result = classifier.classify(
            error="Connection refused: localhost:5432",
            error_type="ConnectionError",
        )
        assert result.category == FailureCategory.CONNECTION_ERROR
        assert result.confidence >= 0.85

    def test_classify_connection_reset(self):
        classifier = FailureClassifier()
        result = classifier.classify(
            error="Connection reset by peer",
            error_type="ConnectionResetError",
        )
        assert result.category == FailureCategory.CONNECTION_ERROR

    def test_classify_permission_error(self):
        classifier = FailureClassifier()
        result = classifier.classify(
            error="Permission denied: /etc/shadow",
            error_type="PermissionError",
        )
        assert result.category == FailureCategory.PERMISSION_ERROR

    def test_classify_resource_exhausted(self):
        classifier = FailureClassifier()
        result = classifier.classify(
            error="Out of memory",
            error_type="MemoryError",
        )
        assert result.category == FailureCategory.RESOURCE_EXHAUSTED

    def test_classify_unknown_no_info(self):
        classifier = FailureClassifier()
        result = classifier.classify()
        assert result.category == FailureCategory.UNKNOWN
        assert result.confidence == 0.0

    def test_classify_unknown_no_match(self):
        classifier = FailureClassifier()
        result = classifier.classify(
            error="Something completely unexpected happened",
            error_type="CustomWeirdError",
        )
        assert result.category == FailureCategory.UNKNOWN

    def test_classify_context_fallback_tool_errors(self):
        classifier = FailureClassifier()
        result = classifier.classify(
            error="Agent run failed",
            error_type="RuntimeError",
            steps=[
                {
                    "step_type": "tool_call",
                    "output": {"error": "tool broke"},
                },
            ],
        )
        assert result.category == FailureCategory.TOOL_ERROR
        assert result.confidence == 0.50

    def test_custom_rule_priority(self):
        custom_rule = ClassificationRule(
            name="custom_gpu",
            category=FailureCategory.RESOURCE_EXHAUSTED,
            confidence=0.99,
            error_patterns=[r"CUDA\s+out\s+of\s+memory"],
        )
        classifier = FailureClassifier(rules=[custom_rule])
        result = classifier.classify(error="CUDA out of memory")
        assert result.category == FailureCategory.RESOURCE_EXHAUSTED
        assert result.rule_name == "custom_gpu"
        assert result.confidence == 0.99

    def test_add_rule(self):
        classifier = FailureClassifier()
        classifier.add_rule(
            ClassificationRule(
                name="custom_db",
                category=FailureCategory.TOOL_ERROR,
                confidence=0.95,
                error_patterns=[r"deadlock\s+detected"],
            )
        )
        result = classifier.classify(error="Deadlock detected in transaction")
        assert result.category == FailureCategory.TOOL_ERROR
        assert result.rule_name == "custom_db"

    def test_highest_confidence_wins(self):
        classifier = FailureClassifier()
        # "Connection refused" matches both connection_error (0.95 type)
        # and connection_message (0.85) - type match should win
        result = classifier.classify(
            error="Connection refused",
            error_type="ConnectionError",
        )
        assert result.category == FailureCategory.CONNECTION_ERROR
        assert result.confidence >= 0.90


class TestClassifyFunction:
    """Tests for the module-level classify_failure function."""

    def test_classify_function(self):
        result = classify_failure(
            error="TimeoutError: Tool execution timed out",
            error_type="TimeoutError",
        )
        assert result.category == FailureCategory.TOOL_TIMEOUT

    def test_classify_function_returns_result(self):
        result = classify_failure(error="Rate limit exceeded")
        assert isinstance(result, ClassificationResult)
        assert result.rule_name is not None


class TestAutoClassificationIntegration:
    """Tests that auto-classification works in RunMetadata.complete()."""

    def test_auto_classify_on_complete(self):
        from datetime import datetime
        from uuid import uuid4
        from reagent.schema.run import RunMetadata

        meta = RunMetadata(
            run_id=uuid4(),
            start_time=datetime.utcnow(),
        )
        meta.complete(error="Connection refused", error_type="ConnectionError")

        assert meta.status.value == "failed"
        assert meta.failure_category == "connection_error"

    def test_auto_classify_timeout(self):
        from datetime import datetime
        from uuid import uuid4
        from reagent.schema.run import RunMetadata

        meta = RunMetadata(
            run_id=uuid4(),
            start_time=datetime.utcnow(),
        )
        meta.complete(error="Tool timed out after 30s", error_type="TimeoutError")

        assert meta.failure_category == "tool_timeout"

    def test_auto_classify_rate_limit(self):
        from datetime import datetime
        from uuid import uuid4
        from reagent.schema.run import RunMetadata

        meta = RunMetadata(
            run_id=uuid4(),
            start_time=datetime.utcnow(),
        )
        meta.complete(error="Rate limit exceeded", error_type="RateLimitError")

        assert meta.failure_category == "rate_limit"

    def test_manual_category_preserved(self):
        from datetime import datetime
        from uuid import uuid4
        from reagent.schema.run import RunMetadata

        meta = RunMetadata(
            run_id=uuid4(),
            start_time=datetime.utcnow(),
            failure_category="my_custom_category",
        )
        meta.complete(error="Some error", error_type="SomeError")

        # Manual category should NOT be overwritten
        assert meta.failure_category == "my_custom_category"

    def test_no_classify_on_success(self):
        from datetime import datetime
        from uuid import uuid4
        from reagent.schema.run import RunMetadata

        meta = RunMetadata(
            run_id=uuid4(),
            start_time=datetime.utcnow(),
        )
        meta.complete(output={"result": "done"})

        assert meta.status.value == "completed"
        assert meta.failure_category is None
