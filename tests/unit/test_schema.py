"""Unit tests for schema models."""

import pytest
from datetime import datetime
from uuid import uuid4

from reagent.core.constants import EventType, Status
from reagent.schema.events import ExecutionEvent
from reagent.schema.steps import (
    LLMCallStep,
    ToolCallStep,
    RetrievalStep,
    ErrorStep,
    TokenUsage,
    ToolInput,
    ToolOutput,
)
from reagent.schema.run import RunConfig, RunMetadata, RunSummary, Run


class TestExecutionEvent:
    """Tests for ExecutionEvent model."""

    def test_create_event(self):
        """Test creating a basic event."""
        run_id = uuid4()
        event = ExecutionEvent(
            run_id=run_id,
            event_type=EventType.LLM_CALL_END,
            sequence_number=0,
        )

        assert event.run_id == run_id
        assert event.event_type == EventType.LLM_CALL_END
        assert event.sequence_number == 0
        assert event.event_id is not None

    def test_create_run_start_event(self):
        """Test creating a RUN_START event."""
        run_id = uuid4()
        event = ExecutionEvent.create_run_start(
            run_id=run_id,
            metadata={"key": "value"},
        )

        assert event.run_id == run_id
        assert event.event_type == EventType.RUN_START
        assert event.sequence_number == 0
        assert event.metadata == {"key": "value"}

    def test_is_start_event(self):
        """Test is_start_event method."""
        run_id = uuid4()

        start_event = ExecutionEvent(
            run_id=run_id,
            event_type=EventType.LLM_CALL_START,
            sequence_number=0,
        )
        assert start_event.is_start_event() is True

        end_event = ExecutionEvent(
            run_id=run_id,
            event_type=EventType.LLM_CALL_END,
            sequence_number=1,
        )
        assert end_event.is_start_event() is False

    def test_event_serialization(self):
        """Test event JSON serialization."""
        run_id = uuid4()
        event = ExecutionEvent(
            run_id=run_id,
            event_type=EventType.TOOL_CALL_END,
            sequence_number=5,
            payload={"tool": "calculator", "result": 42},
        )

        data = event.model_dump(mode="json")
        assert data["run_id"] == str(run_id)
        assert data["event_type"] == "tool_call_end"
        assert data["sequence_number"] == 5
        assert data["payload"]["result"] == 42


class TestLLMCallStep:
    """Tests for LLMCallStep model."""

    def test_create_llm_step(self):
        """Test creating an LLM call step."""
        run_id = uuid4()
        step = LLMCallStep(
            run_id=run_id,
            step_number=0,
            timestamp_start=datetime.utcnow(),
            model="gpt-4",
            prompt="Hello",
            response="Hi there!",
        )

        assert step.run_id == run_id
        assert step.model == "gpt-4"
        assert step.prompt == "Hello"
        assert step.response == "Hi there!"
        assert step.step_type == "llm_call"

    def test_llm_step_with_tokens(self):
        """Test LLM step with token usage."""
        run_id = uuid4()
        step = LLMCallStep(
            run_id=run_id,
            step_number=0,
            timestamp_start=datetime.utcnow(),
            model="gpt-4",
            token_usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            cost_usd=0.015,
        )

        assert step.token_usage.total_tokens == 150
        assert step.cost_usd == 0.015

    def test_token_usage_from_counts(self):
        """Test TokenUsage.from_counts factory method."""
        usage = TokenUsage.from_counts(prompt=100, completion=50)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150


class TestToolCallStep:
    """Tests for ToolCallStep model."""

    def test_create_tool_step(self):
        """Test creating a tool call step."""
        run_id = uuid4()
        step = ToolCallStep(
            run_id=run_id,
            step_number=1,
            timestamp_start=datetime.utcnow(),
            tool_name="web_search",
            input=ToolInput(kwargs={"query": "test"}),
            output=ToolOutput(result=["result1", "result2"]),
            success=True,
        )

        assert step.tool_name == "web_search"
        assert step.input.kwargs == {"query": "test"}
        assert step.output.result == ["result1", "result2"]
        assert step.success is True
        assert step.step_type == "tool_call"

    def test_tool_step_with_error(self):
        """Test tool step with error."""
        run_id = uuid4()
        step = ToolCallStep(
            run_id=run_id,
            step_number=1,
            timestamp_start=datetime.utcnow(),
            tool_name="web_search",
            input=ToolInput(kwargs={"query": "test"}),
            output=ToolOutput(error="Timeout", error_type="TimeoutError"),
            success=False,
        )

        assert step.success is False
        assert step.output.error == "Timeout"


class TestRunModels:
    """Tests for run-related models."""

    def test_run_config_defaults(self):
        """Test RunConfig default values."""
        config = RunConfig()
        assert config.sample_rate == 1.0
        assert config.tags == []

    def test_run_config_with_values(self):
        """Test RunConfig with custom values."""
        config = RunConfig(
            name="my-run",
            project="my-project",
            tags=["tag1", "tag2", "tag1"],  # Duplicate should be removed
        )
        assert config.name == "my-run"
        assert config.tags == ["tag1", "tag2"]  # Deduped

    def test_run_metadata_complete(self):
        """Test RunMetadata.complete method."""
        run_id = uuid4()
        metadata = RunMetadata(
            run_id=run_id,
            start_time=datetime.utcnow(),
            status=Status.RUNNING,
        )

        assert metadata.status == Status.RUNNING
        assert metadata.end_time is None

        metadata.complete(output={"result": "success"})

        assert metadata.status == Status.COMPLETED
        assert metadata.end_time is not None
        assert metadata.output == {"result": "success"}

    def test_run_metadata_complete_with_error(self):
        """Test RunMetadata.complete with error."""
        run_id = uuid4()
        metadata = RunMetadata(
            run_id=run_id,
            start_time=datetime.utcnow(),
            status=Status.RUNNING,
        )

        metadata.complete(error="Something went wrong", error_type="ValueError")

        assert metadata.status == Status.FAILED
        assert metadata.error == "Something went wrong"
        assert metadata.error_type == "ValueError"

    def test_run_summary_from_metadata(self):
        """Test RunSummary.from_metadata factory method."""
        run_id = uuid4()
        metadata = RunMetadata(
            run_id=run_id,
            name="test-run",
            start_time=datetime.utcnow(),
            status=Status.COMPLETED,
            model="gpt-4",
        )

        summary = RunSummary.from_metadata(metadata)

        assert summary.run_id == run_id
        assert summary.name == "test-run"
        assert summary.status == Status.COMPLETED
        assert summary.model == "gpt-4"

    def test_run_iter_steps(self):
        """Test Run.iter_steps method."""
        run_id = uuid4()
        run = Run(
            metadata=RunMetadata(
                run_id=run_id,
                start_time=datetime.utcnow(),
                status=Status.COMPLETED,
            ),
            steps=[
                LLMCallStep(run_id=run_id, step_number=0, timestamp_start=datetime.utcnow(), model="gpt-4"),
                ToolCallStep(run_id=run_id, step_number=1, timestamp_start=datetime.utcnow(), tool_name="calc", input=ToolInput()),
                LLMCallStep(run_id=run_id, step_number=2, timestamp_start=datetime.utcnow(), model="gpt-4"),
            ],
        )

        llm_steps = list(run.iter_steps(step_type="llm_call"))
        assert len(llm_steps) == 2

        tool_steps = list(run.iter_steps(step_type="tool_call"))
        assert len(tool_steps) == 1
