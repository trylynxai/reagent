"""Tests for debugger command history."""

import pytest
from pathlib import Path

from reagent.cli.history import CommandHistory, DEFAULT_MAX_ENTRIES


# ============================================================
# CommandHistory — core operations
# ============================================================


class TestCommandHistoryBasic:
    def test_add_and_length(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist", max_entries=100)
        h.load()
        assert h.length == 0

        h.add("step")
        h.add("inspect 0")
        h.add("continue")
        assert h.length == 3

    def test_add_strips_whitespace(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist")
        h.load()
        h.add("  step  ")
        entries = h.get_all()
        assert entries[-1][1] == "step"

    def test_add_empty_ignored(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist")
        h.load()
        h.add("")
        h.add("   ")
        assert h.length == 0

    def test_get_all(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist")
        h.load()
        h.add("step")
        h.add("next")
        h.add("continue")

        entries = h.get_all()
        assert len(entries) == 3
        assert entries[0][1] == "step"
        assert entries[2][1] == "continue"

    def test_get_all_with_limit(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist")
        h.load()
        for i in range(10):
            h.add(f"cmd-{i}")

        entries = h.get_all(limit=3)
        assert len(entries) == 3
        assert entries[0][1] == "cmd-7"
        assert entries[2][1] == "cmd-9"

    def test_get_entry(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist")
        h.load()
        h.add("alpha")
        h.add("beta")
        h.add("gamma")

        assert h.get_entry(1) == "alpha"
        assert h.get_entry(2) == "beta"
        assert h.get_entry(3) == "gamma"

    def test_get_entry_out_of_range(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist")
        h.load()
        h.add("only")
        assert h.get_entry(0) is None
        assert h.get_entry(99) is None

    def test_search(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist")
        h.load()
        h.add("step")
        h.add("inspect 0")
        h.add("inspect 2")
        h.add("continue")
        h.add("breakpoint 3")

        results = h.search("inspect")
        assert len(results) == 2
        assert all("inspect" in cmd for _, cmd in results)

    def test_search_case_insensitive(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist")
        h.load()
        h.add("Step")
        h.add("STEP")
        h.add("step")
        h.add("next")

        results = h.search("step")
        assert len(results) == 3

    def test_search_no_matches(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist")
        h.load()
        h.add("step")
        results = h.search("foobar")
        assert len(results) == 0

    def test_session_count(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist")
        h.load()
        assert h.session_count == 0

        h.add("step")
        h.add("next")
        assert h.session_count == 2


# ============================================================
# Persistence — save and load
# ============================================================


class TestCommandHistoryPersistence:
    def test_save_and_load(self, tmp_path):
        path = tmp_path / "hist"

        # Session 1: add commands and save
        h1 = CommandHistory(history_path=path)
        h1.load()
        h1.add("step")
        h1.add("inspect 0")
        h1.add("continue")
        h1.save()

        assert path.exists()

        # Session 2: load and verify
        h2 = CommandHistory(history_path=path)
        h2.load()
        assert h2.length >= 3
        entries = h2.get_all()
        commands = [cmd for _, cmd in entries]
        assert "step" in commands
        assert "inspect 0" in commands
        assert "continue" in commands

    def test_session_start_index_after_reload(self, tmp_path):
        path = tmp_path / "hist"

        h1 = CommandHistory(history_path=path)
        h1.load()
        h1.add("old-cmd-1")
        h1.add("old-cmd-2")
        h1.save()

        h2 = CommandHistory(history_path=path)
        h2.load()
        # Session count should be 0 since no new commands added yet
        assert h2.session_count == 0

        h2.add("new-cmd")
        assert h2.session_count == 1

    def test_max_entries_limit(self, tmp_path):
        path = tmp_path / "hist"

        h = CommandHistory(history_path=path, max_entries=5)
        h.load()
        for i in range(10):
            h.add(f"cmd-{i}")
        h.save()

        h2 = CommandHistory(history_path=path, max_entries=5)
        h2.load()
        # Should have at most 5 entries
        assert h2.length <= 5

    def test_load_nonexistent_file(self, tmp_path):
        path = tmp_path / "nonexistent" / "hist"
        h = CommandHistory(history_path=path)
        h.load()  # Should not raise
        assert h.length == 0

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "hist"
        h = CommandHistory(history_path=path)
        h.load()
        h.add("test")
        h.save()
        assert path.parent.exists()


# ============================================================
# Debugger integration — history and ! commands
# ============================================================


class TestDebuggerHistoryCommand:
    """Test history/! commands within the ReplayDebugger."""

    @pytest.fixture
    def debugger_with_history(self, tmp_path):
        """Create a debugger with pre-populated history."""
        from unittest.mock import MagicMock
        from reagent.cli.debugger import ReplayDebugger
        from reagent.cli.history import CommandHistory

        history = CommandHistory(history_path=tmp_path / "hist")
        history.load()
        history.add("step")
        history.add("inspect 0")
        history.add("next")
        history.add("breakpoint 2")
        history.add("continue")

        # Create a mock-based debugger that doesn't need a real engine
        engine = MagicMock()
        dbg = ReplayDebugger(engine, "fake-id", history=history)
        # Set up minimal state so commands don't crash
        dbg._finished = False
        dbg._current_step = MagicMock()
        dbg._current_step.step_number = 0
        dbg._current_step.step_type = "llm_call"
        dbg._session = MagicMock()
        dbg._all_steps = []

        return dbg

    def test_history_shows_entries(self, debugger_with_history, capsys):
        debugger_with_history.execute_command("history")
        # Should not crash; output goes to Rich console (not captured by capsys)

    def test_history_with_limit(self, debugger_with_history):
        debugger_with_history.execute_command("history 2")

    def test_history_search(self, debugger_with_history):
        debugger_with_history.execute_command("history search inspect")

    def test_history_search_no_results(self, debugger_with_history):
        debugger_with_history.execute_command("history search zzzzz")

    def test_history_bad_arg(self, debugger_with_history):
        debugger_with_history.execute_command("history abc")

    def test_bang_executes_history_entry(self, debugger_with_history):
        # !1 should re-execute "step" (entry #1)
        dbg = debugger_with_history
        # Mock _cmd_step to track if it's called
        called = []
        original_step = dbg._cmd_step

        def mock_step(args):
            called.append(True)
            # Don't call original since iterator is mocked
        dbg._cmd_step = mock_step

        dbg.execute_command("!1")
        assert len(called) == 1

    def test_bang_invalid_index(self, debugger_with_history):
        debugger_with_history.execute_command("!999")

    def test_bang_non_numeric(self, debugger_with_history):
        debugger_with_history.execute_command("!abc")

    def test_history_empty(self, tmp_path):
        from unittest.mock import MagicMock
        from reagent.cli.debugger import ReplayDebugger
        from reagent.cli.history import CommandHistory

        history = CommandHistory(history_path=tmp_path / "empty_hist")
        history.load()

        engine = MagicMock()
        dbg = ReplayDebugger(engine, "fake-id", history=history)
        dbg._finished = False
        dbg._current_step = MagicMock()
        dbg._session = MagicMock()

        dbg.execute_command("history")


# ============================================================
# Fallback mode (no readline)
# ============================================================


class TestFallbackHistory:
    """Test the fallback path when readline is unavailable."""

    def test_fallback_add_and_get(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist")
        h._enabled = False
        h._fallback = []
        h._session_start_index = 0

        h.add("alpha")
        h.add("beta")
        assert h.length == 2
        assert h.get_entry(1) == "alpha"
        assert h.get_entry(2) == "beta"

    def test_fallback_search(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist")
        h._enabled = False
        h._fallback = ["step", "inspect 0", "inspect 2", "next"]
        results = h.search("inspect")
        assert len(results) == 2

    def test_fallback_max_entries(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist", max_entries=3)
        h._enabled = False
        h._fallback = []
        h._session_start_index = 0

        for i in range(5):
            h.add(f"cmd-{i}")
        assert h.length == 3

    def test_fallback_save_and_load(self, tmp_path):
        path = tmp_path / "hist"
        h1 = CommandHistory(history_path=path)
        h1._enabled = False
        h1._fallback = []
        h1._session_start_index = 0

        h1.add("one")
        h1.add("two")
        h1.save()

        h2 = CommandHistory(history_path=path)
        h2._enabled = False
        h2.load()
        assert h2.length == 2
        assert h2.get_entry(1) == "one"
        assert h2.get_entry(2) == "two"

    def test_fallback_session_count(self, tmp_path):
        path = tmp_path / "hist"

        # Save some history
        h1 = CommandHistory(history_path=path)
        h1._enabled = False
        h1._fallback = []
        h1._session_start_index = 0
        h1.add("old")
        h1.save()

        # Load into new session
        h2 = CommandHistory(history_path=path)
        h2._enabled = False
        h2.load()
        assert h2.session_count == 0

        h2.add("new")
        assert h2.session_count == 1

    def test_fallback_get_all_with_limit(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist")
        h._enabled = False
        h._fallback = [f"cmd-{i}" for i in range(10)]

        entries = h.get_all(limit=3)
        assert len(entries) == 3
        assert entries[0][1] == "cmd-7"

    def test_fallback_get_entry_out_of_range(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist")
        h._enabled = False
        h._fallback = ["only"]

        assert h.get_entry(0) is None
        assert h.get_entry(99) is None


# ============================================================
# Edge cases
# ============================================================


class TestHistoryEdgeCases:
    def test_enabled_property(self, tmp_path):
        h = CommandHistory(history_path=tmp_path / "hist")
        # Should reflect whether readline is available
        assert isinstance(h.enabled, bool)

    def test_default_max_entries(self):
        assert DEFAULT_MAX_ENTRIES == 1000

    def test_history_search_empty_query_shows_usage(self, tmp_path):
        from unittest.mock import MagicMock
        from reagent.cli.debugger import ReplayDebugger
        from reagent.cli.history import CommandHistory

        history = CommandHistory(history_path=tmp_path / "hist")
        history.load()

        engine = MagicMock()
        dbg = ReplayDebugger(engine, "fake-id", history=history)
        dbg._finished = False
        dbg._current_step = MagicMock()
        dbg._session = MagicMock()

        # "history search " with no query
        dbg.execute_command("history search ")

    def test_multiple_sessions_accumulate(self, tmp_path):
        path = tmp_path / "hist"

        for session_num in range(3):
            h = CommandHistory(history_path=path)
            h.load()
            h.add(f"session-{session_num}-cmd")
            h.save()

        h_final = CommandHistory(history_path=path)
        h_final.load()
        entries = h_final.get_all()
        commands = [cmd for _, cmd in entries]
        assert "session-0-cmd" in commands
        assert "session-1-cmd" in commands
        assert "session-2-cmd" in commands
