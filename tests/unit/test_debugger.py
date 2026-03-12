"""Tests for the interactive replay debugger."""

import pytest
import tempfile
from unittest.mock import MagicMock, patch

from reagent.client.reagent import ReAgent
from reagent.core.config import Config
from reagent.core.constants import Status, ReplayMode
from reagent.schema.run import RunConfig
from reagent.replay.engine import ReplayEngine
from reagent.cli.debugger import (
    ReplayDebugger,
    _truncate,
    _format_duration,
    _resolve_field,
    STEP_STYLES,
)


@pytest.fixture
def client_with_run():
    """Create a ReAgent client with a recorded run and return (client, run_id)."""
    config = Config(
        storage={"type": "memory"},
        redaction={"enabled": False},
    )
    client = ReAgent(config=config)

    with client.trace(RunConfig(name="debugger-test", project="test")) as ctx:
        ctx.record_llm_call(
            model="gpt-4",
            prompt="What is the capital of France?",
            response="Paris",
            prompt_tokens=10,
            completion_tokens=1,
            cost_usd=0.001,
            duration_ms=200,
        )
        ctx.record_tool_call(
            tool_name="web_search",
            kwargs={"query": "Paris population"},
            result={"population": "2.1 million"},
            duration_ms=500,
        )
        ctx.record_llm_call(
            model="gpt-4",
            prompt="Summarize the results",
            response="Paris has a population of 2.1 million.",
            prompt_tokens=20,
            completion_tokens=10,
            duration_ms=300,
        )
        ctx.set_output({"answer": "Paris, population 2.1M"})

    client.flush()
    runs = client.list_runs()
    run_id = str(runs[0].run_id)

    return client, run_id


@pytest.fixture
def debugger(client_with_run):
    """Create a started ReplayDebugger."""
    client, run_id = client_with_run
    engine = ReplayEngine(
        storage=client.storage,
        mode=ReplayMode.STRICT,
    )
    dbg = ReplayDebugger(engine, run_id)
    dbg.start()
    return dbg


class TestReplayDebuggerInit:
    """Test debugger initialization."""

    def test_start(self, debugger):
        assert not debugger.is_finished
        assert debugger._current_step is not None
        assert debugger._session is not None
        assert len(debugger._all_steps) == 3

    def test_start_with_from_step(self, client_with_run):
        client, run_id = client_with_run
        engine = ReplayEngine(storage=client.storage, mode=ReplayMode.STRICT)
        dbg = ReplayDebugger(engine, run_id)
        dbg.start(from_step=1)
        # Should have advanced past step 0
        assert dbg._current_step is not None

    def test_get_prompt(self, debugger):
        prompt = debugger.get_prompt()
        assert "0/" in prompt or "LLM" in prompt


class TestStepCommands:
    """Test step execution commands."""

    def test_step(self, debugger):
        # Should be at step 0 (first LLM call)
        initial_step = debugger._current_step.step_number

        debugger.execute_command("step")
        assert debugger._current_step.step_number > initial_step

    def test_step_alias(self, debugger):
        debugger.execute_command("s")
        # Should have advanced
        assert len(debugger._executed_steps) > 0

    def test_next_skips_to_significant(self, debugger):
        debugger.execute_command("next")
        # Should land on an LLM, tool, or error step
        assert debugger._current_step.step_type in {"llm_call", "tool_call", "error"}

    def test_continue_to_end(self, debugger):
        debugger.execute_command("continue")
        assert debugger.is_finished

    def test_step_after_finished(self, debugger):
        debugger.execute_command("continue")
        assert debugger.is_finished
        # Should not crash
        debugger.execute_command("step")

    def test_continue_stops_at_breakpoint(self, debugger):
        debugger._session.set_breakpoint(2)
        debugger.execute_command("continue")
        # Should stop at step 2, not finish
        assert debugger._current_step.step_number == 2
        assert not debugger.is_finished


class TestInspectCommand:
    """Test step inspection."""

    def test_inspect_current(self, debugger):
        # Should not crash, prints to console
        debugger.execute_command("inspect")

    def test_inspect_specific_step(self, debugger):
        debugger.execute_command("inspect 1")

    def test_inspect_invalid_step(self, debugger):
        debugger.execute_command("inspect 999")

    def test_inspect_bad_arg(self, debugger):
        debugger.execute_command("inspect abc")


class TestBreakpointCommands:
    """Test breakpoint management."""

    def test_set_breakpoint(self, debugger):
        debugger.execute_command("breakpoint 2")
        assert 2 in debugger._session._breakpoints

    def test_list_breakpoints(self, debugger):
        debugger._session.set_breakpoint(1)
        debugger._session.set_breakpoint(2)
        debugger.execute_command("breakpoint")

    def test_clear_breakpoint(self, debugger):
        debugger._session.set_breakpoint(2)
        debugger.execute_command("clear 2")
        assert 2 not in debugger._session._breakpoints

    def test_clear_all_breakpoints(self, debugger):
        debugger._session.set_breakpoint(1)
        debugger._session.set_breakpoint(2)
        debugger.execute_command("clear")
        assert len(debugger._session._breakpoints) == 0


class TestWatchCommand:
    """Test watch expressions."""

    def test_add_watch(self, debugger):
        debugger.execute_command("watch mymodel model")
        assert "mymodel" in debugger._watches

    def test_list_watches(self, debugger):
        debugger._watches["test"] = "model"
        debugger.execute_command("watch")

    def test_remove_watch(self, debugger):
        debugger._watches["test"] = "model"
        debugger.execute_command("watch -test")
        assert "test" not in debugger._watches

    def test_watch_prints_on_step(self, debugger):
        debugger.execute_command("watch m model")
        debugger.execute_command("step")


class TestNavigationCommands:
    """Test navigation and listing."""

    def test_list(self, debugger):
        debugger.execute_command("list")

    def test_goto(self, debugger):
        debugger.execute_command("goto 2")
        assert debugger._current_step.step_number == 2

    def test_goto_out_of_range(self, debugger):
        debugger.execute_command("goto 999")

    def test_goto_no_arg(self, debugger):
        debugger.execute_command("goto")

    def test_state(self, debugger):
        debugger.execute_command("state")

    def test_diff_no_divergences(self, debugger):
        debugger.execute_command("diff")


class TestOtherCommands:
    """Test utility commands."""

    def test_help(self, debugger):
        debugger.execute_command("help")

    def test_exit(self, debugger):
        debugger.execute_command("exit")
        assert debugger.is_finished

    def test_quit_alias(self, debugger):
        debugger.execute_command("q")
        assert debugger.is_finished

    def test_unknown_command(self, debugger):
        debugger.execute_command("foobar")

    def test_empty_command(self, debugger):
        debugger.execute_command("")


class TestHelperFunctions:
    """Test utility functions."""

    def test_truncate(self):
        assert _truncate("hello", 10) == "hello"
        assert _truncate("a" * 100, 10) == "a" * 7 + "..."
        assert _truncate(None) == ""
        assert _truncate("line1\nline2", 20) == "line1 line2"

    def test_format_duration(self):
        assert _format_duration(None) == ""
        assert _format_duration(50) == "50ms"
        assert _format_duration(1500) == "1.5s"
        assert _format_duration(90000) == "1.5m"

    def test_resolve_field(self):
        data = {"a": {"b": {"c": 42}}, "list": [1, 2, 3]}
        assert _resolve_field(data, "a.b.c") == 42
        assert _resolve_field(data, "a.b") == {"c": 42}
        assert _resolve_field(data, "missing") is None
        assert _resolve_field(data, "list.1") == 2

    def test_step_styles_coverage(self):
        expected = {
            "llm_call", "tool_call", "retrieval", "chain",
            "agent", "error", "reasoning", "checkpoint", "custom",
        }
        assert set(STEP_STYLES.keys()) == expected


class TestDebuggerWithFailedRun:
    """Test debugger with a failed run containing an error step."""

    def test_inspect_error_step(self):
        config = Config(
            storage={"type": "memory"},
            redaction={"enabled": False},
        )
        client = ReAgent(config=config)

        try:
            with client.trace(RunConfig(name="error-test")) as ctx:
                ctx.record_llm_call(
                    model="gpt-4",
                    prompt="Do something",
                    response="I'll try",
                    prompt_tokens=5,
                    completion_tokens=3,
                )
                ctx.record_error(
                    error_message="Connection failed",
                    error_type="ConnectionError",
                    error_traceback="Traceback:\n  File test.py\n  ConnectionError",
                )
                raise ConnectionError("Connection failed")
        except ConnectionError:
            pass

        client.flush()
        runs = client.list_runs()
        run_id = str(runs[0].run_id)

        engine = ReplayEngine(storage=client.storage, mode=ReplayMode.STRICT)
        dbg = ReplayDebugger(engine, run_id)
        dbg.start()

        # Step to the error
        dbg.execute_command("next")

        # Inspect the error step
        assert dbg._current_step.step_type == "error"
        dbg.execute_command("inspect")
