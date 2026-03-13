"""Tests for OTLP export functionality."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from reagent.core.constants import Status
from reagent.export.otlp import (
    _make_attribute,
    _status_to_otlp,
    _timestamp_to_nanos,
    _uuid_to_span_id,
    _uuid_to_trace_id,
    run_to_otlp_json,
)
from reagent.schema.run import CostSummary, Run, RunMetadata, StepSummary, TokenSummary
from reagent.schema.steps import (
    AgentStep,
    ChainStep,
    CheckpointStep,
    CustomStep,
    ErrorStep,
    LLMCallStep,
    ReasoningStep,
    RetrievalStep,
    RetrievalResult,
    TokenUsage,
    ToolCallStep,
    ToolInput,
    ToolOutput,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

RUN_ID = UUID("12345678-1234-5678-1234-567812345678")
STEP_ID_1 = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
STEP_ID_2 = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
STEP_ID_3 = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
START_TIME = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
END_TIME = datetime(2025, 1, 15, 10, 0, 5, tzinfo=timezone.utc)


def _make_metadata(
    status: Status = Status.COMPLETED,
    **kwargs,
) -> RunMetadata:
    defaults = dict(
        run_id=RUN_ID,
        name="test-run",
        project="my-project",
        start_time=START_TIME,
        end_time=END_TIME,
        duration_ms=5000,
        status=status,
        model="gpt-4",
        framework="langchain",
        tokens=TokenSummary(total_tokens=1500, prompt_tokens=1000, completion_tokens=500),
        cost=CostSummary(total_usd=0.05),
        steps=StepSummary(total=2, llm_calls=1, tool_calls=1),
    )
    defaults.update(kwargs)
    return RunMetadata(**defaults)


def _make_llm_step(**kwargs) -> LLMCallStep:
    defaults = dict(
        step_id=STEP_ID_1,
        run_id=RUN_ID,
        step_number=0,
        timestamp_start=START_TIME,
        timestamp_end=datetime(2025, 1, 15, 10, 0, 2, tzinfo=timezone.utc),
        duration_ms=2000,
        model="gpt-4",
        temperature=0.7,
        token_usage=TokenUsage(prompt_tokens=800, completion_tokens=200, total_tokens=1000),
        finish_reason="stop",
        response="Hello!",
    )
    defaults.update(kwargs)
    return LLMCallStep(**defaults)


def _make_tool_step(**kwargs) -> ToolCallStep:
    defaults = dict(
        step_id=STEP_ID_2,
        run_id=RUN_ID,
        step_number=1,
        timestamp_start=datetime(2025, 1, 15, 10, 0, 2, tzinfo=timezone.utc),
        timestamp_end=datetime(2025, 1, 15, 10, 0, 3, tzinfo=timezone.utc),
        duration_ms=1000,
        tool_name="search",
        input=ToolInput(args=(), kwargs={"query": "test"}),
        output=ToolOutput(result="found it"),
        success=True,
    )
    defaults.update(kwargs)
    return ToolCallStep(**defaults)


def _make_run(
    status: Status = Status.COMPLETED,
    steps: list | None = None,
) -> Run:
    meta = _make_metadata(status=status)
    if steps is None:
        steps = [_make_llm_step(), _make_tool_step()]
    return Run(metadata=meta, steps=steps)


# ---------------------------------------------------------------------------
# TestRunToOtlpJson
# ---------------------------------------------------------------------------


class TestRunToOtlpJson:
    def test_basic_structure(self):
        run = _make_run()
        result = run_to_otlp_json(run)

        assert "resourceSpans" in result
        assert len(result["resourceSpans"]) == 1

        rs = result["resourceSpans"][0]
        assert "resource" in rs
        assert "scopeSpans" in rs
        assert len(rs["scopeSpans"]) == 1

        ss = rs["scopeSpans"][0]
        assert "scope" in ss
        assert ss["scope"]["name"] == "reagent"
        assert ss["scope"]["version"] == "0.1.0"
        assert "spans" in ss

    def test_trace_id_consistency(self):
        run = _make_run()
        result = run_to_otlp_json(run)
        spans = result["resourceSpans"][0]["scopeSpans"][0]["spans"]

        trace_ids = {s["traceId"] for s in spans}
        assert len(trace_ids) == 1, "All spans must share the same traceId"

    def test_root_span_attributes(self):
        run = _make_run()
        result = run_to_otlp_json(run)
        root_span = result["resourceSpans"][0]["scopeSpans"][0]["spans"][0]

        attr_map = {a["key"]: a["value"] for a in root_span["attributes"]}
        assert attr_map["reagent.run.id"]["stringValue"] == str(RUN_ID)
        assert attr_map["reagent.run.project"]["stringValue"] == "my-project"
        assert attr_map["reagent.run.status"]["stringValue"] == "completed"
        assert attr_map["gen_ai.system"]["stringValue"] == "langchain"
        assert attr_map["gen_ai.request.model"]["stringValue"] == "gpt-4"
        assert attr_map["reagent.run.total_tokens"]["intValue"] == "1500"

    def test_span_count(self):
        run = _make_run()
        result = run_to_otlp_json(run)
        spans = result["resourceSpans"][0]["scopeSpans"][0]["spans"]

        # 2 steps + 1 root = 3 spans
        assert len(spans) == 3

    def test_parent_child_hierarchy(self):
        run = _make_run()
        result = run_to_otlp_json(run)
        spans = result["resourceSpans"][0]["scopeSpans"][0]["spans"]

        root_span = spans[0]
        child_spans = spans[1:]

        # Root span has no parentSpanId
        assert "parentSpanId" not in root_span

        # Children point to root
        for child in child_spans:
            assert child["parentSpanId"] == root_span["spanId"]

    def test_parent_child_with_nested_steps(self):
        """Steps with parent_step_id should point to the parent step's span."""
        parent_step = _make_llm_step(step_id=STEP_ID_1, step_number=0)
        child_step = _make_tool_step(
            step_id=STEP_ID_2,
            step_number=1,
            parent_step_id=STEP_ID_1,
        )

        run = _make_run(steps=[parent_step, child_step])
        result = run_to_otlp_json(run)
        spans = result["resourceSpans"][0]["scopeSpans"][0]["spans"]

        parent_span = spans[1]  # first step span
        child_span = spans[2]  # second step span

        assert child_span["parentSpanId"] == parent_span["spanId"]

    def test_timestamps_nanoseconds(self):
        run = _make_run()
        result = run_to_otlp_json(run)
        root_span = result["resourceSpans"][0]["scopeSpans"][0]["spans"][0]

        start_nanos = root_span["startTimeUnixNano"]
        end_nanos = root_span["endTimeUnixNano"]

        # Should be strings
        assert isinstance(start_nanos, str)
        assert isinstance(end_nanos, str)

        # Should be valid integers
        assert int(start_nanos) > 0
        assert int(end_nanos) > int(start_nanos)

    def test_status_completed_ok(self):
        run = _make_run(status=Status.COMPLETED)
        result = run_to_otlp_json(run)
        root_span = result["resourceSpans"][0]["scopeSpans"][0]["spans"][0]

        assert root_span["status"]["code"] == 1  # OK

    def test_status_failed_error(self):
        run = _make_run(status=Status.FAILED)
        result = run_to_otlp_json(run)
        root_span = result["resourceSpans"][0]["scopeSpans"][0]["spans"][0]

        assert root_span["status"]["code"] == 2  # ERROR


# ---------------------------------------------------------------------------
# TestStepAttributes
# ---------------------------------------------------------------------------


class TestStepAttributes:
    def test_llm_call_genai_semconv(self):
        run = _make_run(steps=[_make_llm_step()])
        result = run_to_otlp_json(run)
        llm_span = result["resourceSpans"][0]["scopeSpans"][0]["spans"][1]

        attr_map = {a["key"]: a["value"] for a in llm_span["attributes"]}
        assert attr_map["gen_ai.request.model"]["stringValue"] == "gpt-4"
        assert attr_map["gen_ai.request.temperature"]["doubleValue"] == 0.7
        assert attr_map["gen_ai.usage.input_tokens"]["intValue"] == "800"
        assert attr_map["gen_ai.usage.output_tokens"]["intValue"] == "200"
        assert attr_map["gen_ai.response.finish_reasons"]["stringValue"] == "stop"

    def test_tool_call_attributes(self):
        run = _make_run(steps=[_make_tool_step()])
        result = run_to_otlp_json(run)
        tool_span = result["resourceSpans"][0]["scopeSpans"][0]["spans"][1]

        attr_map = {a["key"]: a["value"] for a in tool_span["attributes"]}
        assert attr_map["reagent.tool.name"]["stringValue"] == "search"
        assert attr_map["reagent.tool.success"]["boolValue"] is True

    def test_error_step_always_error(self):
        error_step = ErrorStep(
            step_id=STEP_ID_1,
            run_id=RUN_ID,
            step_number=0,
            timestamp_start=START_TIME,
            timestamp_end=END_TIME,
            error_message="Something went wrong",
            error_type="ValueError",
        )
        run = _make_run(steps=[error_step])
        result = run_to_otlp_json(run)
        error_span = result["resourceSpans"][0]["scopeSpans"][0]["spans"][1]

        assert error_span["status"]["code"] == 2  # ERROR

        attr_map = {a["key"]: a["value"] for a in error_span["attributes"]}
        assert attr_map["exception.type"]["stringValue"] == "ValueError"
        assert attr_map["exception.message"]["stringValue"] == "Something went wrong"

    def test_retrieval_attributes(self):
        retrieval_step = RetrievalStep(
            step_id=STEP_ID_1,
            run_id=RUN_ID,
            step_number=0,
            timestamp_start=START_TIME,
            timestamp_end=END_TIME,
            query="what is reagent?",
            index_name="docs",
            top_k=5,
            results=RetrievalResult(
                documents=[{"text": "doc1"}, {"text": "doc2"}, {"text": "doc3"}],
            ),
        )
        run = _make_run(steps=[retrieval_step])
        result = run_to_otlp_json(run)
        span = result["resourceSpans"][0]["scopeSpans"][0]["spans"][1]

        attr_map = {a["key"]: a["value"] for a in span["attributes"]}
        assert attr_map["reagent.retrieval.query"]["stringValue"] == "what is reagent?"
        assert attr_map["reagent.retrieval.top_k"]["intValue"] == "5"
        assert attr_map["reagent.retrieval.result_count"]["intValue"] == "3"

    def test_null_fields_omitted(self):
        """None values should not produce attributes."""
        llm_step = _make_llm_step(temperature=None, finish_reason=None, token_usage=None)
        run = _make_run(steps=[llm_step])
        result = run_to_otlp_json(run)
        span = result["resourceSpans"][0]["scopeSpans"][0]["spans"][1]

        attr_keys = {a["key"] for a in span["attributes"]}
        assert "gen_ai.request.temperature" not in attr_keys
        assert "gen_ai.response.finish_reasons" not in attr_keys
        assert "gen_ai.usage.input_tokens" not in attr_keys

    def test_all_step_types_no_crash(self):
        """Converting a run with all 9 step types should not crash."""
        steps = [
            _make_llm_step(step_id=uuid4(), step_number=0),
            _make_tool_step(step_id=uuid4(), step_number=1),
            RetrievalStep(
                step_id=uuid4(), run_id=RUN_ID, step_number=2,
                timestamp_start=START_TIME, query="test",
            ),
            ChainStep(
                step_id=uuid4(), run_id=RUN_ID, step_number=3,
                timestamp_start=START_TIME, chain_name="my-chain",
            ),
            AgentStep(
                step_id=uuid4(), run_id=RUN_ID, step_number=4,
                timestamp_start=START_TIME, agent_name="my-agent",
            ),
            ReasoningStep(
                step_id=uuid4(), run_id=RUN_ID, step_number=5,
                timestamp_start=START_TIME, thought="thinking...",
            ),
            ErrorStep(
                step_id=uuid4(), run_id=RUN_ID, step_number=6,
                timestamp_start=START_TIME,
                error_message="oops", error_type="RuntimeError",
            ),
            CheckpointStep(
                step_id=uuid4(), run_id=RUN_ID, step_number=7,
                timestamp_start=START_TIME, state_hash="abc123",
            ),
            CustomStep(
                step_id=uuid4(), run_id=RUN_ID, step_number=8,
                timestamp_start=START_TIME, event_name="custom-event",
            ),
        ]
        run = _make_run(steps=steps)
        result = run_to_otlp_json(run)

        spans = result["resourceSpans"][0]["scopeSpans"][0]["spans"]
        # 9 steps + 1 root = 10 spans
        assert len(spans) == 10


# ---------------------------------------------------------------------------
# TestHelpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_timestamp_to_nanos(self):
        dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        nanos = _timestamp_to_nanos(dt)
        # 2025-01-01T00:00:00Z in seconds = 1735689600
        assert nanos == str(1735689600 * 1_000_000_000)

    def test_uuid_to_trace_id(self):
        uid = UUID("12345678-1234-5678-1234-567812345678")
        trace_id = _uuid_to_trace_id(uid)
        assert len(trace_id) == 32
        assert all(c in "0123456789abcdef" for c in trace_id)

    def test_uuid_to_span_id(self):
        uid = UUID("12345678-1234-5678-1234-567812345678")
        span_id = _uuid_to_span_id(uid)
        assert len(span_id) == 16
        assert all(c in "0123456789abcdef" for c in span_id)

    def test_make_attribute_string(self):
        attr = _make_attribute("key", "value")
        assert attr == {"key": "key", "value": {"stringValue": "value"}}

    def test_make_attribute_int(self):
        attr = _make_attribute("key", 42)
        assert attr == {"key": "key", "value": {"intValue": "42"}}

    def test_make_attribute_float(self):
        attr = _make_attribute("key", 3.14)
        assert attr == {"key": "key", "value": {"doubleValue": 3.14}}

    def test_make_attribute_bool(self):
        attr = _make_attribute("key", True)
        assert attr == {"key": "key", "value": {"boolValue": True}}


# ---------------------------------------------------------------------------
# TestExportOtlpLive
# ---------------------------------------------------------------------------


class TestExportOtlpLive:
    def test_import_error_without_sdk(self):
        """Should raise ImportError with helpful message when SDK is missing."""
        from reagent.export.otlp import export_otlp_live

        with patch.dict("sys.modules", {
            "opentelemetry.sdk.trace": None,
            "opentelemetry.sdk.trace.export": None,
            "opentelemetry.sdk.resources": None,
            "opentelemetry.exporter.otlp.proto.http.trace_exporter": None,
        }):
            run = _make_run()
            with pytest.raises(ImportError, match="reagent\\[otlp\\]"):
                export_otlp_live(run, "http://localhost:4318/v1/traces")
