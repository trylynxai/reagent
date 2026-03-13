"""Tests for CSV export functionality."""

import csv
import io
from datetime import datetime
from uuid import uuid4

import pytest

from reagent.export.csv import (
    RUN_COLUMNS,
    STEP_COLUMNS,
    export_csv,
    run_to_csv,
    runs_to_csv,
    steps_to_csv,
)
from reagent.schema.run import (
    CostSummary,
    Run,
    RunConfig,
    RunMetadata,
    StepSummary,
    TokenSummary,
)
from reagent.schema.steps import (
    AgentStep,
    ChainStep,
    ErrorStep,
    LLMCallStep,
    RetrievalStep,
    RetrievalResult,
    ToolCallStep,
    ToolInput,
    ToolOutput,
    TokenUsage,
)


# ---- Helpers ----

_RUN_ID = uuid4()


def _make_run(
    name: str = "test-run",
    steps: list | None = None,
    cost_usd: float = 0.0,
    total_tokens: int = 0,
    tags: list[str] | None = None,
) -> Run:
    run = Run.create(RunConfig(name=name, tags=tags or []))
    run.metadata.run_id = _RUN_ID
    run.metadata.cost = CostSummary(total_usd=cost_usd, llm_cost_usd=cost_usd)
    run.metadata.tokens = TokenSummary(total_tokens=total_tokens)
    run.metadata.model = "gpt-4"
    if steps:
        run.steps = steps
        run.metadata.steps = StepSummary(total=len(steps))
    return run


def _llm_step(step_number: int = 0) -> LLMCallStep:
    return LLMCallStep(
        run_id=_RUN_ID,
        step_number=step_number,
        timestamp_start=datetime.utcnow(),
        model="gpt-4",
        provider="openai",
        prompt="Hello",
        response="Hi there",
        token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        cost_usd=0.001,
        finish_reason="stop",
    )


def _tool_step(step_number: int = 0, tool_name: str = "search") -> ToolCallStep:
    return ToolCallStep(
        run_id=_RUN_ID,
        step_number=step_number,
        timestamp_start=datetime.utcnow(),
        tool_name=tool_name,
        input=ToolInput(kwargs={"query": "test"}),
        output=ToolOutput(result="found it"),
        success=True,
    )


def _agent_step(step_number: int = 0) -> AgentStep:
    return AgentStep(
        run_id=_RUN_ID,
        step_number=step_number,
        timestamp_start=datetime.utcnow(),
        agent_name="researcher",
        action="search",
        action_input={"q": "test"},
    )


def _error_step(step_number: int = 0) -> ErrorStep:
    return ErrorStep(
        run_id=_RUN_ID,
        step_number=step_number,
        timestamp_start=datetime.utcnow(),
        error_message="something broke",
        error_type="RuntimeError",
    )


def _chain_step(step_number: int = 0) -> ChainStep:
    return ChainStep(
        run_id=_RUN_ID,
        step_number=step_number,
        timestamp_start=datetime.utcnow(),
        chain_name="qa_chain",
    )


def _retrieval_step(step_number: int = 0) -> RetrievalStep:
    return RetrievalStep(
        run_id=_RUN_ID,
        step_number=step_number,
        timestamp_start=datetime.utcnow(),
        query="what is AI?",
        results=RetrievalResult(documents=[{"text": "AI is..."}, {"text": "ML is..."}]),
    )


def _parse_csv(csv_string: str) -> list[dict[str, str]]:
    """Parse a CSV string into a list of dicts."""
    reader = csv.DictReader(io.StringIO(csv_string))
    return list(reader)


# ============================================================
# Run Summary CSV
# ============================================================


class TestRunsCsv:
    def test_single_run(self):
        run = _make_run(cost_usd=1.50, total_tokens=1000)
        result = runs_to_csv([run])
        rows = _parse_csv(result)
        assert len(rows) == 1
        assert rows[0]["name"] == "test-run"
        assert rows[0]["total_cost_usd"] == "1.5"
        assert rows[0]["total_tokens"] == "1000"
        assert rows[0]["model"] == "gpt-4"

    def test_multiple_runs(self):
        runs = [
            _make_run(name="run-1"),
            _make_run(name="run-2"),
            _make_run(name="run-3"),
        ]
        # Give each a unique run_id
        for i, run in enumerate(runs):
            run.metadata.run_id = uuid4()

        result = runs_to_csv(runs)
        rows = _parse_csv(result)
        assert len(rows) == 3
        assert rows[0]["name"] == "run-1"
        assert rows[2]["name"] == "run-3"

    def test_all_columns_present(self):
        run = _make_run()
        result = runs_to_csv([run])
        reader = csv.DictReader(io.StringIO(result))
        assert list(reader.fieldnames) == RUN_COLUMNS

    def test_custom_columns(self):
        run = _make_run()
        result = runs_to_csv([run], columns=["run_id", "name", "status"])
        reader = csv.DictReader(io.StringIO(result))
        assert list(reader.fieldnames) == ["run_id", "name", "status"]

    def test_tags_pipe_separated(self):
        run = _make_run(tags=["prod", "gpt4", "v2"])
        result = runs_to_csv([run])
        rows = _parse_csv(result)
        assert rows[0]["tags"] == "prod|gpt4|v2"

    def test_empty_runs(self):
        result = runs_to_csv([])
        rows = _parse_csv(result)
        assert len(rows) == 0

    def test_header_still_present_on_empty(self):
        result = runs_to_csv([])
        assert "run_id" in result
        assert "name" in result


# ============================================================
# Step Details CSV
# ============================================================


class TestStepsCsv:
    def test_llm_step(self):
        run = _make_run(steps=[_llm_step(0)])
        result = steps_to_csv([run])
        rows = _parse_csv(result)
        assert len(rows) == 1
        assert rows[0]["step_type"] == "llm_call"
        assert rows[0]["model"] == "gpt-4"
        assert rows[0]["provider"] == "openai"
        assert rows[0]["prompt_tokens"] == "10"
        assert rows[0]["completion_tokens"] == "5"
        assert rows[0]["total_tokens"] == "15"
        assert rows[0]["cost_usd"] == "0.001"
        assert rows[0]["finish_reason"] == "stop"

    def test_tool_step(self):
        run = _make_run(steps=[_tool_step(0, "web_search")])
        result = steps_to_csv([run])
        rows = _parse_csv(result)
        assert rows[0]["step_type"] == "tool_call"
        assert rows[0]["tool_name"] == "web_search"
        assert rows[0]["tool_success"] == "True"

    def test_agent_step(self):
        run = _make_run(steps=[_agent_step(0)])
        result = steps_to_csv([run])
        rows = _parse_csv(result)
        assert rows[0]["step_type"] == "agent"
        assert rows[0]["agent_name"] == "researcher"
        assert rows[0]["action"] == "search"

    def test_error_step(self):
        run = _make_run(steps=[_error_step(0)])
        result = steps_to_csv([run])
        rows = _parse_csv(result)
        assert rows[0]["step_type"] == "error"
        assert rows[0]["error"] == "something broke"
        assert rows[0]["error_type"] == "RuntimeError"

    def test_chain_step(self):
        run = _make_run(steps=[_chain_step(0)])
        result = steps_to_csv([run])
        rows = _parse_csv(result)
        assert rows[0]["chain_name"] == "qa_chain"

    def test_retrieval_step(self):
        run = _make_run(steps=[_retrieval_step(0)])
        result = steps_to_csv([run])
        rows = _parse_csv(result)
        assert rows[0]["query"] == "what is AI?"
        assert rows[0]["result_count"] == "2"

    def test_mixed_steps(self):
        steps = [_llm_step(0), _tool_step(1), _agent_step(2), _error_step(3)]
        run = _make_run(steps=steps)
        result = steps_to_csv([run])
        rows = _parse_csv(result)
        assert len(rows) == 4
        assert rows[0]["step_type"] == "llm_call"
        assert rows[1]["step_type"] == "tool_call"
        assert rows[2]["step_type"] == "agent"
        assert rows[3]["step_type"] == "error"

    def test_all_columns_present(self):
        run = _make_run(steps=[_llm_step(0)])
        result = steps_to_csv([run])
        reader = csv.DictReader(io.StringIO(result))
        assert list(reader.fieldnames) == STEP_COLUMNS

    def test_custom_columns(self):
        run = _make_run(steps=[_llm_step(0)])
        result = steps_to_csv([run], columns=["step_number", "step_type", "model"])
        reader = csv.DictReader(io.StringIO(result))
        assert list(reader.fieldnames) == ["step_number", "step_type", "model"]

    def test_run_metadata_on_each_row(self):
        steps = [_llm_step(0), _tool_step(1)]
        run = _make_run(name="my-run", steps=steps)
        result = steps_to_csv([run])
        rows = _parse_csv(result)
        assert all(r["run_name"] == "my-run" for r in rows)
        assert all(r["run_id"] == str(_RUN_ID) for r in rows)

    def test_multiple_runs_steps(self):
        run1 = _make_run(name="run-1", steps=[_llm_step(0)])
        run1.metadata.run_id = uuid4()
        run2 = _make_run(name="run-2", steps=[_tool_step(0), _tool_step(1)])
        run2.metadata.run_id = uuid4()
        result = steps_to_csv([run1, run2])
        rows = _parse_csv(result)
        assert len(rows) == 3


# ============================================================
# run_to_csv convenience
# ============================================================


class TestRunToCsv:
    def test_steps_mode(self):
        run = _make_run(steps=[_llm_step(0), _tool_step(1)])
        result = run_to_csv(run, mode="steps")
        rows = _parse_csv(result)
        assert len(rows) == 2

    def test_runs_mode(self):
        run = _make_run()
        result = run_to_csv(run, mode="runs")
        rows = _parse_csv(result)
        assert len(rows) == 1
        assert rows[0]["name"] == "test-run"


# ============================================================
# File export
# ============================================================


class TestExportCsvFile:
    def test_export_to_file(self, tmp_path):
        run = _make_run(steps=[_llm_step(0)])
        path = tmp_path / "output.csv"
        result_path = export_csv([run], path, mode="steps")
        assert result_path.exists()
        content = result_path.read_text()
        rows = _parse_csv(content)
        assert len(rows) == 1

    def test_export_runs_mode(self, tmp_path):
        run = _make_run()
        path = tmp_path / "runs.csv"
        export_csv([run], path, mode="runs")
        content = path.read_text()
        rows = _parse_csv(content)
        assert len(rows) == 1
        assert rows[0]["name"] == "test-run"

    def test_export_with_custom_columns(self, tmp_path):
        run = _make_run()
        path = tmp_path / "custom.csv"
        export_csv([run], path, mode="runs", columns=["run_id", "name"])
        content = path.read_text()
        reader = csv.DictReader(io.StringIO(content))
        assert list(reader.fieldnames) == ["run_id", "name"]


# ============================================================
# Edge cases
# ============================================================


class TestEdgeCases:
    def test_tool_step_with_error(self):
        step = ToolCallStep(
            run_id=_RUN_ID,
            step_number=0,
            timestamp_start=datetime.utcnow(),
            tool_name="api_call",
            input=ToolInput(),
            output=ToolOutput(error="timeout", error_type="TimeoutError"),
            success=False,
        )
        run = _make_run(steps=[step])
        result = steps_to_csv([run])
        rows = _parse_csv(result)
        assert rows[0]["error"] == "timeout"
        assert rows[0]["error_type"] == "TimeoutError"
        assert rows[0]["tool_success"] == "False"

    def test_llm_step_without_tokens(self):
        step = LLMCallStep(
            run_id=_RUN_ID,
            step_number=0,
            timestamp_start=datetime.utcnow(),
            model="claude-3",
        )
        run = _make_run(steps=[step])
        result = steps_to_csv([run])
        rows = _parse_csv(result)
        assert rows[0]["prompt_tokens"] == ""
        assert rows[0]["model"] == "claude-3"

    def test_csv_special_characters(self):
        """Commas and quotes in values are handled by csv module."""
        run = _make_run(name='run with "quotes" and, commas')
        result = runs_to_csv([run])
        rows = _parse_csv(result)
        assert rows[0]["name"] == 'run with "quotes" and, commas'

    def test_retrieval_without_results(self):
        step = RetrievalStep(
            run_id=_RUN_ID,
            step_number=0,
            timestamp_start=datetime.utcnow(),
            query="test",
        )
        run = _make_run(steps=[step])
        result = steps_to_csv([run])
        rows = _parse_csv(result)
        assert rows[0]["result_count"] == ""
