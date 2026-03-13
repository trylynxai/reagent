"""Tests for partial replay mode and step executors."""

import pytest

from reagent.client.reagent import ReAgent
from reagent.core.config import Config
from reagent.core.constants import ReplayMode, Status
from reagent.replay.engine import ReplayEngine, StepOverrides
from reagent.replay.executor import ExecutorRegistry, ExecutionResult, execute_step
from reagent.replay.session import ReplaySession
from reagent.schema.run import RunConfig
from reagent.schema.steps import LLMCallStep, ToolCallStep


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def client():
    """Create a ReAgent client with in-memory storage."""
    config = Config(
        storage={"type": "memory"},
        redaction={"enabled": False},
    )
    return ReAgent(config=config)


@pytest.fixture
def recorded_run(client):
    """Record a run with LLM and tool calls, return (client, run_id)."""
    with client.trace(RunConfig(name="replay-test", project="test")) as ctx:
        ctx.record_llm_call(
            model="gpt-4",
            prompt="Search for AI safety papers",
            response="I'll search for recent AI safety papers.",
            prompt_tokens=10,
            completion_tokens=8,
            duration_ms=200,
        )
        ctx.record_tool_call(
            tool_name="web_search",
            kwargs={"query": "AI safety papers 2024"},
            result={"results": ["paper1", "paper2", "paper3"]},
            duration_ms=500,
        )
        ctx.record_llm_call(
            model="gpt-4",
            prompt="Summarize: paper1, paper2, paper3",
            response="Here are three key AI safety papers from 2024...",
            prompt_tokens=20,
            completion_tokens=30,
            duration_ms=300,
        )
        ctx.record_tool_call(
            tool_name="calculator",
            kwargs={"expression": "3 * 100"},
            result=300,
            duration_ms=10,
        )
        ctx.set_output({"summary": "AI safety papers summary"})

    client.flush()
    runs = client.list_runs()
    return client, str(runs[0].run_id)


@pytest.fixture
def engine(client):
    """Create a replay engine."""
    return ReplayEngine(
        storage=client.storage,
        mode=ReplayMode.PARTIAL,
    )


# ── ExecutorRegistry tests ────────────────────────────────


class TestExecutorRegistry:

    def test_register_and_get_by_type(self):
        reg = ExecutorRegistry()
        fn = lambda step: "executed"
        reg.register("llm_call", fn)
        # Need an LLM step to test
        step = _make_llm_step(0)
        assert reg.get_executor(step) is fn

    def test_register_tool(self):
        reg = ExecutorRegistry()
        fn = lambda step: "tool output"
        reg.register_tool("web_search", fn)
        step = _make_tool_step(0, "web_search")
        assert reg.get_executor(step) is fn

    def test_register_tool_no_match(self):
        reg = ExecutorRegistry()
        fn = lambda step: "tool output"
        reg.register_tool("web_search", fn)
        step = _make_tool_step(0, "calculator")
        assert reg.get_executor(step) is None

    def test_register_llm_model(self):
        reg = ExecutorRegistry()
        fn = lambda step: "llm output"
        reg.register_llm("gpt-4", fn)
        step = _make_llm_step(0, model="gpt-4")
        assert reg.get_executor(step) is fn

    def test_register_step_number(self):
        reg = ExecutorRegistry()
        fn = lambda step: "step 2 output"
        reg.register_step(2, fn)
        step = _make_llm_step(2)
        assert reg.get_executor(step) is fn

    def test_step_number_priority_over_type(self):
        reg = ExecutorRegistry()
        type_fn = lambda step: "type"
        step_fn = lambda step: "step"
        reg.register("llm_call", type_fn)
        reg.register_step(0, step_fn)
        step = _make_llm_step(0)
        assert reg.get_executor(step) is step_fn

    def test_tool_name_priority_over_type(self):
        reg = ExecutorRegistry()
        type_fn = lambda step: "type"
        tool_fn = lambda step: "tool"
        reg.register("tool_call", type_fn)
        reg.register_tool("web_search", tool_fn)
        step = _make_tool_step(0, "web_search")
        assert reg.get_executor(step) is tool_fn

    def test_default_executor(self):
        reg = ExecutorRegistry()
        fn = lambda step: "default"
        reg.set_default(fn)
        step = _make_llm_step(0)
        assert reg.get_executor(step) is fn

    def test_has_executor(self):
        reg = ExecutorRegistry()
        step = _make_llm_step(0)
        assert not reg.has_executor(step)
        reg.register("llm_call", lambda s: None)
        assert reg.has_executor(step)

    def test_clear(self):
        reg = ExecutorRegistry()
        reg.register("llm_call", lambda s: None)
        reg.register_tool("x", lambda s: None)
        reg.register_llm("gpt-4", lambda s: None)
        reg.register_step(0, lambda s: None)
        reg.set_default(lambda s: None)
        reg.clear()
        assert reg.get_executor(_make_llm_step(0)) is None


class TestExecuteStep:

    def test_successful_execution(self):
        step = _make_llm_step(0)
        result = execute_step(step, lambda s: "new response")
        assert result.output == "new response"
        assert result.error is None
        assert result.duration_ms >= 0

    def test_execution_with_error(self):
        def failing_executor(step):
            raise ValueError("executor failed")

        step = _make_llm_step(0)
        result = execute_step(step, failing_executor)
        assert result.output is None
        assert result.error == "executor failed"


# ── StepOverrides tests ───────────────────────────────────


class TestStepOverrides:

    def test_rerun_by_step_number(self):
        overrides = StepOverrides(rerun_steps={2, 5})
        step = _make_llm_step(2)
        assert overrides.should_rerun(step)
        assert not overrides.should_rerun(_make_llm_step(3))

    def test_rerun_by_type(self):
        overrides = StepOverrides(rerun_types={"tool_call"})
        assert overrides.should_rerun(_make_tool_step(0, "x"))
        assert not overrides.should_rerun(_make_llm_step(0))

    def test_rerun_by_tool_name(self):
        overrides = StepOverrides(rerun_tools={"web_search"})
        assert overrides.should_rerun(_make_tool_step(0, "web_search"))
        assert not overrides.should_rerun(_make_tool_step(0, "calculator"))

    def test_rerun_by_model(self):
        overrides = StepOverrides(rerun_models={"gpt-4"})
        assert overrides.should_rerun(_make_llm_step(0, "gpt-4"))
        assert not overrides.should_rerun(_make_llm_step(0, "claude-3"))

    def test_patch_by_step_number(self):
        fn = lambda step: "patched"
        overrides = StepOverrides(patch_functions={3: fn})
        assert overrides.should_rerun(_make_llm_step(3))
        assert overrides.get_patch(_make_llm_step(3)) is fn

    def test_patch_by_type(self):
        fn = lambda step: "type patched"
        overrides = StepOverrides(patch_by_type={"llm_call": fn})
        step = _make_llm_step(0)
        assert overrides.should_rerun(step)
        assert overrides.get_patch(step) is fn

    def test_patch_step_number_priority(self):
        step_fn = lambda step: "step"
        type_fn = lambda step: "type"
        overrides = StepOverrides(
            patch_functions={0: step_fn},
            patch_by_type={"llm_call": type_fn},
        )
        assert overrides.get_patch(_make_llm_step(0)) is step_fn


# ── Partial Replay Integration ────────────────────────────


class TestPartialReplay:
    """Test partial replay with the full engine."""

    def test_replay_all_replayed(self, recorded_run):
        """With no overrides, all steps are replayed from recording."""
        client, run_id = recorded_run
        engine = ReplayEngine(storage=client.storage, mode=ReplayMode.PARTIAL)

        session = engine.replay(run_id)

        assert session.status == Status.COMPLETED
        assert len(session.results) == 4
        for r in session.results:
            assert r.mode == "replayed"
            assert not r.diverged

    def test_replay_with_patch_function(self, recorded_run):
        """Patch a specific step with a custom function."""
        client, run_id = recorded_run
        engine = ReplayEngine(storage=client.storage, mode=ReplayMode.PARTIAL)

        overrides = StepOverrides(
            rerun_steps={1},
            patch_functions={
                1: lambda step: {"results": ["new_paper1", "new_paper2"]},
            },
        )

        session = engine.replay(run_id, overrides=overrides)

        assert session.status == Status.COMPLETED
        results = session.results

        # Step 0: replayed (LLM)
        assert results[0].mode == "replayed"

        # Step 1: patched (tool - web_search)
        assert results[1].mode == "patched"
        assert results[1].replay_output == {"results": ["new_paper1", "new_paper2"]}
        assert results[1].diverged  # Different from original

        # Step 2, 3: replayed
        assert results[2].mode == "replayed"
        assert results[3].mode == "replayed"

    def test_replay_with_registered_tool_executor(self, recorded_run):
        """Register a tool executor and re-run matching steps."""
        client, run_id = recorded_run
        engine = ReplayEngine(storage=client.storage, mode=ReplayMode.PARTIAL)

        call_log = []

        def mock_search(step):
            call_log.append(step.tool_name)
            return {"results": ["live_result"]}

        engine.executors.register_tool("web_search", mock_search)

        overrides = StepOverrides(rerun_tools={"web_search"})
        session = engine.replay(run_id, overrides=overrides)

        assert len(call_log) == 1
        assert call_log[0] == "web_search"

        results = session.results
        assert results[1].mode == "re-executed"
        assert results[1].replay_output == {"results": ["live_result"]}
        assert results[1].diverged

    def test_replay_with_registered_llm_executor(self, recorded_run):
        """Register an LLM executor and re-run matching steps."""
        client, run_id = recorded_run
        engine = ReplayEngine(storage=client.storage, mode=ReplayMode.PARTIAL)

        def mock_llm(step):
            return f"New response for: {step.prompt[:20]}"

        engine.executors.register_llm("gpt-4", mock_llm)

        overrides = StepOverrides(rerun_models={"gpt-4"})
        session = engine.replay(run_id, overrides=overrides)

        results = session.results
        # Both LLM steps (0, 2) should be re-executed
        assert results[0].mode == "re-executed"
        assert results[0].diverged
        assert results[2].mode == "re-executed"
        assert results[2].diverged

        # Tool steps (1, 3) should be replayed
        assert results[1].mode == "replayed"
        assert results[3].mode == "replayed"

    def test_replay_executor_error_captured(self, recorded_run):
        """Executor errors are captured in the result."""
        client, run_id = recorded_run
        engine = ReplayEngine(storage=client.storage, mode=ReplayMode.PARTIAL)

        def failing_executor(step):
            raise RuntimeError("API is down")

        engine.executors.register_tool("web_search", failing_executor)

        overrides = StepOverrides(rerun_tools={"web_search"})
        session = engine.replay(run_id, overrides=overrides)

        results = session.results
        assert results[1].mode == "re-executed"
        assert results[1].replay_output is None
        assert results[1].diverged

    def test_replay_no_executor_falls_back(self, recorded_run):
        """Steps marked for rerun but with no executor fall back to recorded."""
        client, run_id = recorded_run
        engine = ReplayEngine(storage=client.storage, mode=ReplayMode.PARTIAL)

        # Mark for rerun but don't register any executor
        overrides = StepOverrides(rerun_tools={"web_search"})
        session = engine.replay(run_id, overrides=overrides)

        results = session.results
        # Should fall back to "replayed" since no executor found
        assert results[1].mode == "replayed"
        assert not results[1].diverged

    def test_replay_patch_by_type(self, recorded_run):
        """Patch all steps of a type."""
        client, run_id = recorded_run
        engine = ReplayEngine(storage=client.storage, mode=ReplayMode.PARTIAL)

        overrides = StepOverrides(
            patch_by_type={
                "tool_call": lambda step: f"patched_{step.tool_name}",
            },
        )

        session = engine.replay(run_id, overrides=overrides)

        results = session.results
        assert results[1].mode == "patched"
        assert results[1].replay_output == "patched_web_search"
        assert results[3].mode == "patched"
        assert results[3].replay_output == "patched_calculator"

    def test_replay_with_step_range(self, recorded_run):
        """Partial replay with from_step and to_step."""
        client, run_id = recorded_run
        engine = ReplayEngine(storage=client.storage, mode=ReplayMode.PARTIAL)

        session = engine.replay(run_id, from_step=1, to_step=3)

        results = session.results
        assert len(results) == 2  # Steps 1 and 2
        assert results[0].step_number == 1
        assert results[1].step_number == 2

    def test_divergence_details(self, recorded_run):
        """Divergence details show original vs new values."""
        client, run_id = recorded_run
        engine = ReplayEngine(storage=client.storage, mode=ReplayMode.PARTIAL)

        overrides = StepOverrides(
            patch_functions={0: lambda step: "COMPLETELY DIFFERENT"},
        )

        session = engine.replay(run_id, overrides=overrides)

        result = session.results[0]
        assert result.diverged
        assert result.divergence_details is not None
        assert "original" in result.divergence_details.lower() or "new" in result.divergence_details.lower()


class TestStrictReplay:
    """Verify strict mode still works correctly."""

    def test_strict_all_replayed(self, recorded_run):
        client, run_id = recorded_run
        engine = ReplayEngine(storage=client.storage, mode=ReplayMode.STRICT)

        session = engine.replay(run_id)

        assert session.status == Status.COMPLETED
        assert len(session.results) == 4
        for r in session.results:
            assert r.mode == "replayed"
            assert not r.diverged


class TestMockReplay:
    """Test mock replay mode."""

    def test_mock_uses_recorded_responses(self, recorded_run):
        client, run_id = recorded_run
        engine = ReplayEngine(
            storage=client.storage,
            mode=ReplayMode.MOCK,
            sandbox_strict=False,
        )

        session = engine.replay(run_id)

        assert session.status == Status.COMPLETED
        for r in session.results:
            assert r.mode == "mocked"


class TestHybridReplay:
    """Test hybrid replay mode."""

    def test_hybrid_selective_rerun(self, recorded_run):
        client, run_id = recorded_run
        engine = ReplayEngine(storage=client.storage, mode=ReplayMode.HYBRID)

        engine.executors.register_tool("calculator", lambda step: 999)

        overrides = StepOverrides(rerun_tools={"calculator"})
        session = engine.replay(run_id, overrides=overrides)

        results = session.results
        # calculator step is re-executed
        assert results[3].mode == "re-executed"
        assert results[3].replay_output == 999
        assert results[3].diverged

        # Other steps are replayed
        assert results[0].mode == "replayed"
        assert results[1].mode == "replayed"
        assert results[2].mode == "replayed"


# ── Helpers ───────────────────────────────────────────────


def _make_llm_step(step_number: int, model: str = "gpt-4") -> LLMCallStep:
    """Create a minimal LLMCallStep for testing."""
    from datetime import datetime
    from uuid import uuid4

    return LLMCallStep(
        run_id=uuid4(),
        step_number=step_number,
        timestamp_start=datetime.utcnow(),
        model=model,
        prompt="test prompt",
        response="test response",
    )


def _make_tool_step(step_number: int, tool_name: str) -> ToolCallStep:
    """Create a minimal ToolCallStep for testing."""
    from datetime import datetime
    from uuid import uuid4
    from reagent.schema.steps import ToolInput

    return ToolCallStep(
        run_id=uuid4(),
        step_number=step_number,
        timestamp_start=datetime.utcnow(),
        tool_name=tool_name,
        input=ToolInput(),
    )
