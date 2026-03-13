"""Tests for Langfuse export."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from reagent.export.langfuse import (
    _format_timestamp,
    _run_to_trace,
    _step_to_observation,
    _trace_metadata,
    export_langfuse_live,
    run_to_langfuse_json,
)
from reagent.core.constants import Status
from reagent.schema.run import Run, RunMetadata, CostSummary, TokenSummary, StepSummary
from reagent.schema.steps import (
    AgentStep,
    ChainStep,
    CustomStep,
    ErrorStep,
    LLMCallStep,
    ReasoningStep,
    RetrievalStep,
    RetrievalResult,
    ToolCallStep,
    TokenUsage,
    ToolInput,
    ToolOutput,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metadata(**kwargs) -> RunMetadata:
    defaults = {
        "run_id": uuid4(),
        "name": "test-run",
        "project": "test-project",
        "start_time": datetime(2025, 1, 15, 10, 0, 0),
        "status": Status.COMPLETED,
        "tags": ["test"],
    }
    defaults.update(kwargs)
    return RunMetadata(**defaults)


def _make_run(steps=None, **kwargs) -> Run:
    return Run(metadata=_make_metadata(**kwargs), steps=steps or [])


def _make_llm_step(**kwargs) -> LLMCallStep:
    defaults = {
        "run_id": uuid4(),
        "step_number": 0,
        "timestamp_start": datetime(2025, 1, 15, 10, 0, 1),
        "timestamp_end": datetime(2025, 1, 15, 10, 0, 2),
        "model": "gpt-4o",
    }
    defaults.update(kwargs)
    return LLMCallStep(**defaults)


def _make_tool_step(**kwargs) -> ToolCallStep:
    defaults = {
        "run_id": uuid4(),
        "step_number": 1,
        "timestamp_start": datetime(2025, 1, 15, 10, 0, 3),
        "timestamp_end": datetime(2025, 1, 15, 10, 0, 4),
        "tool_name": "web_search",
        "input": ToolInput(args=(), kwargs={"query": "weather"}),
        "output": ToolOutput(result="Sunny"),
        "success": True,
    }
    defaults.update(kwargs)
    return ToolCallStep(**defaults)


# ---------------------------------------------------------------------------
# TestRunToLangfuseJson
# ---------------------------------------------------------------------------


class TestRunToLangfuseJson:
    def test_basic_structure(self):
        run = _make_run()
        result = run_to_langfuse_json(run)
        assert "trace" in result
        assert "observations" in result
        assert isinstance(result["trace"], dict)
        assert isinstance(result["observations"], list)

    def test_trace_id(self):
        run_id = uuid4()
        run = _make_run(run_id=run_id)
        result = run_to_langfuse_json(run)
        assert result["trace"]["id"] == str(run_id)

    def test_trace_name(self):
        run = _make_run(name="my-agent-run")
        result = run_to_langfuse_json(run)
        assert result["trace"]["name"] == "my-agent-run"

    def test_trace_tags(self):
        run = _make_run(tags=["prod", "v2"])
        result = run_to_langfuse_json(run)
        assert result["trace"]["tags"] == ["prod", "v2"]

    def test_observation_count(self):
        steps = [_make_llm_step(), _make_tool_step()]
        run = _make_run(steps=steps)
        result = run_to_langfuse_json(run)
        assert len(result["observations"]) == 2

    def test_trace_level_completed(self):
        run = _make_run(status=Status.COMPLETED)
        result = run_to_langfuse_json(run)
        assert result["trace"]["level"] == "DEFAULT"

    def test_trace_level_failed(self):
        run = _make_run(status=Status.FAILED, error="boom")
        result = run_to_langfuse_json(run)
        assert result["trace"]["level"] == "ERROR"
        assert result["trace"]["statusMessage"] == "boom"

    def test_trace_metadata(self):
        run = _make_run(
            project="my-proj",
            framework="langchain",
            model="gpt-4o",
        )
        result = run_to_langfuse_json(run)
        md = result["trace"]["metadata"]
        assert md["project"] == "my-proj"
        assert md["framework"] == "langchain"
        assert md["primary_model"] == "gpt-4o"

    def test_observations_have_trace_id(self):
        run_id = uuid4()
        steps = [_make_llm_step(run_id=run_id)]
        run = _make_run(steps=steps, run_id=run_id)
        result = run_to_langfuse_json(run)
        for obs in result["observations"]:
            assert obs["traceId"] == str(run_id)


# ---------------------------------------------------------------------------
# TestLLMGeneration
# ---------------------------------------------------------------------------


class TestLLMGeneration:
    def test_type_is_generation(self):
        step = _make_llm_step()
        obs = _step_to_observation(step, uuid4())
        assert obs["type"] == "GENERATION"

    def test_model_set(self):
        step = _make_llm_step(model="claude-3-haiku")
        obs = _step_to_observation(step, uuid4())
        assert obs["model"] == "claude-3-haiku"

    def test_name(self):
        step = _make_llm_step(model="gpt-4o")
        obs = _step_to_observation(step, uuid4())
        assert obs["name"] == "llm_call: gpt-4o"

    def test_input_from_messages(self):
        msgs = [{"role": "user", "content": "hello"}]
        step = _make_llm_step(messages=msgs)
        obs = _step_to_observation(step, uuid4())
        assert obs["input"] == msgs

    def test_input_from_prompt(self):
        step = _make_llm_step(prompt="Hello world")
        obs = _step_to_observation(step, uuid4())
        assert obs["input"] == "Hello world"

    def test_output_from_response(self):
        step = _make_llm_step(response="Hi there!")
        obs = _step_to_observation(step, uuid4())
        assert obs["output"] == "Hi there!"

    def test_token_usage(self):
        step = _make_llm_step(
            token_usage=TokenUsage.from_counts(prompt=100, completion=50)
        )
        obs = _step_to_observation(step, uuid4())
        assert obs["usage"]["input"] == 100
        assert obs["usage"]["output"] == 50
        assert obs["usage"]["total"] == 150

    def test_cost(self):
        step = _make_llm_step(cost_usd=0.05)
        obs = _step_to_observation(step, uuid4())
        assert obs["costDetails"]["total"] == 0.05

    def test_model_parameters(self):
        step = _make_llm_step(temperature=0.7, max_tokens=1000)
        obs = _step_to_observation(step, uuid4())
        assert obs["modelParameters"]["temperature"] == 0.7
        assert obs["modelParameters"]["max_tokens"] == 1000

    def test_error_level(self):
        step = _make_llm_step(error="timeout")
        obs = _step_to_observation(step, uuid4())
        assert obs["level"] == "ERROR"
        assert obs["statusMessage"] == "timeout"

    def test_finish_reason_in_metadata(self):
        step = _make_llm_step(finish_reason="stop")
        obs = _step_to_observation(step, uuid4())
        assert obs["metadata"]["finish_reason"] == "stop"


# ---------------------------------------------------------------------------
# TestToolSpan
# ---------------------------------------------------------------------------


class TestToolSpan:
    def test_type_is_span(self):
        step = _make_tool_step()
        obs = _step_to_observation(step, uuid4())
        assert obs["type"] == "SPAN"

    def test_name(self):
        step = _make_tool_step(tool_name="calculator")
        obs = _step_to_observation(step, uuid4())
        assert obs["name"] == "tool_call: calculator"

    def test_input_output(self):
        step = _make_tool_step(
            input=ToolInput(args=(), kwargs={"x": 1}),
            output=ToolOutput(result="2"),
        )
        obs = _step_to_observation(step, uuid4())
        assert obs["input"] == {"x": 1}
        assert obs["output"] == "2"

    def test_error(self):
        step = _make_tool_step(
            output=ToolOutput(error="fail", error_type="RuntimeError"),
            success=False,
        )
        obs = _step_to_observation(step, uuid4())
        assert obs["level"] == "ERROR"
        assert obs["statusMessage"] == "fail"

    def test_metadata(self):
        step = _make_tool_step(tool_name="search", success=True)
        obs = _step_to_observation(step, uuid4())
        assert obs["metadata"]["tool_name"] == "search"
        assert obs["metadata"]["success"] is True


# ---------------------------------------------------------------------------
# TestAgentSpan
# ---------------------------------------------------------------------------


class TestAgentSpan:
    def test_type_is_span(self):
        step = AgentStep(
            run_id=uuid4(), step_number=0,
            timestamp_start=datetime(2025, 1, 15, 10, 0, 0),
            agent_name="MyAgent", action="start",
        )
        obs = _step_to_observation(step, uuid4())
        assert obs["type"] == "SPAN"
        assert "MyAgent" in obs["name"]
        assert "start" in obs["name"]

    def test_finish_output(self):
        step = AgentStep(
            run_id=uuid4(), step_number=0,
            timestamp_start=datetime(2025, 1, 15, 10, 0, 0),
            agent_name="Bot", action="finish", final_answer="done!",
        )
        obs = _step_to_observation(step, uuid4())
        assert obs["output"] == "done!"


# ---------------------------------------------------------------------------
# TestErrorEvent
# ---------------------------------------------------------------------------


class TestErrorEvent:
    def test_type_is_event(self):
        step = ErrorStep(
            run_id=uuid4(), step_number=0,
            timestamp_start=datetime(2025, 1, 15, 10, 0, 0),
            error_message="boom", error_type="RuntimeError",
        )
        obs = _step_to_observation(step, uuid4())
        assert obs["type"] == "EVENT"
        assert obs["level"] == "ERROR"
        assert obs["statusMessage"] == "boom"

    def test_traceback_in_input(self):
        step = ErrorStep(
            run_id=uuid4(), step_number=0,
            timestamp_start=datetime(2025, 1, 15, 10, 0, 0),
            error_message="fail", error_type="ValueError",
            error_traceback="Traceback...",
        )
        obs = _step_to_observation(step, uuid4())
        assert obs["input"]["traceback"] == "Traceback..."

    def test_recovery_in_output(self):
        step = ErrorStep(
            run_id=uuid4(), step_number=0,
            timestamp_start=datetime(2025, 1, 15, 10, 0, 0),
            error_message="fail", error_type="ValueError",
            recovered=True, recovery_action="retry",
        )
        obs = _step_to_observation(step, uuid4())
        assert obs["output"]["recovered"] is True
        assert obs["output"]["recovery_action"] == "retry"


# ---------------------------------------------------------------------------
# TestChainSpan
# ---------------------------------------------------------------------------


class TestChainSpan:
    def test_chain(self):
        step = ChainStep(
            run_id=uuid4(), step_number=0,
            timestamp_start=datetime(2025, 1, 15, 10, 0, 0),
            chain_name="rag_pipeline", chain_type="sequential",
            input={"query": "test"}, output={"answer": "42"},
        )
        obs = _step_to_observation(step, uuid4())
        assert obs["type"] == "SPAN"
        assert obs["name"] == "chain: rag_pipeline"
        assert obs["input"] == {"query": "test"}
        assert obs["output"] == {"answer": "42"}


# ---------------------------------------------------------------------------
# TestRetrievalSpan
# ---------------------------------------------------------------------------


class TestRetrievalSpan:
    def test_retrieval(self):
        step = RetrievalStep(
            run_id=uuid4(), step_number=0,
            timestamp_start=datetime(2025, 1, 15, 10, 0, 0),
            query="test query", index_name="docs", top_k=5,
            results=RetrievalResult(documents=[{"text": "doc1"}], scores=[0.9]),
        )
        obs = _step_to_observation(step, uuid4())
        assert obs["type"] == "SPAN"
        assert obs["name"] == "retrieval: docs"
        assert obs["input"] == {"query": "test query"}
        assert obs["metadata"]["top_k"] == 5
        assert obs["metadata"]["result_count"] == 1


# ---------------------------------------------------------------------------
# TestCustomEvent
# ---------------------------------------------------------------------------


class TestCustomEvent:
    def test_custom(self):
        step = CustomStep(
            run_id=uuid4(), step_number=0,
            timestamp_start=datetime(2025, 1, 15, 10, 0, 0),
            event_name="user_feedback", data={"rating": 5},
        )
        obs = _step_to_observation(step, uuid4())
        assert obs["type"] == "EVENT"
        assert obs["name"] == "custom: user_feedback"
        assert obs["input"] == {"rating": 5}


# ---------------------------------------------------------------------------
# TestParentChild
# ---------------------------------------------------------------------------


class TestParentChild:
    def test_parent_observation_id(self):
        parent_id = uuid4()
        step = _make_llm_step(parent_step_id=parent_id)
        obs = _step_to_observation(step, uuid4())
        assert obs["parentObservationId"] == str(parent_id)

    def test_no_parent(self):
        step = _make_llm_step()
        obs = _step_to_observation(step, uuid4())
        assert "parentObservationId" not in obs


# ---------------------------------------------------------------------------
# TestHelpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_format_timestamp_none(self):
        assert _format_timestamp(None) is None

    def test_format_timestamp_naive(self):
        dt = datetime(2025, 1, 15, 10, 0, 0)
        result = _format_timestamp(dt)
        assert "2025-01-15" in result
        assert "+00:00" in result

    def test_format_timestamp_aware(self):
        dt = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        result = _format_timestamp(dt)
        assert "2025-01-15T10:00:00" in result


# ---------------------------------------------------------------------------
# TestAllStepTypes
# ---------------------------------------------------------------------------


class TestAllStepTypes:
    """Ensure all step types convert without errors."""

    def test_all_types_no_crash(self):
        run_id = uuid4()
        steps = [
            _make_llm_step(run_id=run_id),
            _make_tool_step(run_id=run_id, step_number=1),
            AgentStep(
                run_id=run_id, step_number=2,
                timestamp_start=datetime(2025, 1, 15, 10, 0, 0),
                agent_name="Bot", action="start",
            ),
            ChainStep(
                run_id=run_id, step_number=3,
                timestamp_start=datetime(2025, 1, 15, 10, 0, 0),
                chain_name="pipeline",
            ),
            RetrievalStep(
                run_id=run_id, step_number=4,
                timestamp_start=datetime(2025, 1, 15, 10, 0, 0),
                query="test",
            ),
            ReasoningStep(
                run_id=run_id, step_number=5,
                timestamp_start=datetime(2025, 1, 15, 10, 0, 0),
                thought="thinking...",
            ),
            ErrorStep(
                run_id=run_id, step_number=6,
                timestamp_start=datetime(2025, 1, 15, 10, 0, 0),
                error_message="fail", error_type="RuntimeError",
            ),
            CustomStep(
                run_id=run_id, step_number=7,
                timestamp_start=datetime(2025, 1, 15, 10, 0, 0),
                event_name="custom",
            ),
        ]
        run = _make_run(steps=steps, run_id=run_id)
        result = run_to_langfuse_json(run)
        assert len(result["observations"]) == 8
        # All have required fields
        for obs in result["observations"]:
            assert "type" in obs
            assert "id" in obs
            assert "traceId" in obs
            assert obs["type"] in ("GENERATION", "SPAN", "EVENT")


# ---------------------------------------------------------------------------
# TestLiveExport
# ---------------------------------------------------------------------------


class TestLiveExport:
    def test_import_error_without_sdk(self):
        run = _make_run()
        with patch.dict("sys.modules", {"langfuse": None}):
            with pytest.raises(ImportError, match="langfuse"):
                export_langfuse_live(run, "pk-test", "sk-test")


# ---------------------------------------------------------------------------
# TestTraceMetadata
# ---------------------------------------------------------------------------


class TestTraceMetadata:
    def test_includes_cost(self):
        meta = _make_metadata()
        meta.cost.total_usd = 1.5
        md = _trace_metadata(meta)
        assert md["total_cost_usd"] == 1.5

    def test_includes_tokens(self):
        meta = _make_metadata()
        meta.tokens.total_tokens = 5000
        md = _trace_metadata(meta)
        assert md["total_tokens"] == 5000

    def test_includes_failure_category(self):
        meta = _make_metadata(
            status=Status.FAILED,
            error="boom",
            failure_category="rate_limit",
        )
        md = _trace_metadata(meta)
        assert md["failure_category"] == "rate_limit"

    def test_custom_metadata(self):
        meta = _make_metadata(custom={"env": "prod"})
        md = _trace_metadata(meta)
        assert md["custom"] == {"env": "prod"}
