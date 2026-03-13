"""Persistent command history for the replay debugger.

Wraps Python's readline module to provide:
- Arrow key navigation through past commands
- Ctrl+R reverse incremental search
- Persistent history file on disk between sessions
- Programmatic search and retrieval
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    import readline

    HAS_READLINE = True
except ImportError:
    HAS_READLINE = False


DEFAULT_HISTORY_PATH = Path.home() / ".reagent" / "debugger_history"
DEFAULT_MAX_ENTRIES = 1000


class CommandHistory:
    """Manages persistent command history for the debugger REPL.

    Uses Python's readline module for arrow key navigation and
    Ctrl+R reverse search.  Falls back gracefully when readline
    is not available.
    """

    def __init__(
        self,
        history_path: Path | str | None = None,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        self._path = Path(history_path) if history_path else DEFAULT_HISTORY_PATH
        self._max_entries = max_entries
        self._session_start_index = 0
        # Fallback storage when readline is unavailable
        self._fallback: list[str] = []
        self._enabled = HAS_READLINE

    @property
    def enabled(self) -> bool:
        """Whether readline-based history is available."""
        return self._enabled

    def load(self) -> None:
        """Load history from disk and configure readline."""
        if not self._enabled:
            self._load_fallback()
            return

        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Clear any existing in-process history and load fresh from file
        readline.clear_history()
        readline.set_history_length(self._max_entries)

        if self._path.exists():
            try:
                readline.read_history_file(str(self._path))
            except (OSError, PermissionError):
                pass

        self._session_start_index = readline.get_current_history_length()

    def save(self) -> None:
        """Save history to disk."""
        if not self._enabled:
            self._save_fallback()
            return

        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            readline.write_history_file(str(self._path))
        except (OSError, PermissionError):
            pass

    def add(self, command: str) -> None:
        """Add a command to history (readline adds automatically via input(),
        but this is useful for programmatic additions)."""
        command = command.strip()
        if not command:
            return

        if self._enabled:
            readline.add_history(command)
        else:
            self._fallback.append(command)
            if len(self._fallback) > self._max_entries:
                self._fallback = self._fallback[-self._max_entries:]

    def get_all(self, limit: int | None = None) -> list[tuple[int, str]]:
        """Get history entries as (index, command) pairs.

        Args:
            limit: Maximum number of recent entries to return.
        """
        if not self._enabled:
            entries = list(enumerate(self._fallback, 1))
            if limit:
                entries = entries[-limit:]
            return entries

        total = readline.get_current_history_length()
        start = max(1, total - limit + 1) if limit else 1
        results = []
        for i in range(start, total + 1):
            item = readline.get_history_item(i)
            if item:
                results.append((i, item))
        return results

    def search(self, query: str) -> list[tuple[int, str]]:
        """Search history for commands containing query (case-insensitive)."""
        query_lower = query.lower()

        if not self._enabled:
            return [
                (i, cmd)
                for i, cmd in enumerate(self._fallback, 1)
                if query_lower in cmd.lower()
            ]

        total = readline.get_current_history_length()
        results = []
        for i in range(1, total + 1):
            item = readline.get_history_item(i)
            if item and query_lower in item.lower():
                results.append((i, item))
        return results

    def get_entry(self, index: int) -> str | None:
        """Get a specific history entry by 1-based index."""
        if not self._enabled:
            if 1 <= index <= len(self._fallback):
                return self._fallback[index - 1]
            return None

        return readline.get_history_item(index)

    @property
    def length(self) -> int:
        """Total number of history entries."""
        if not self._enabled:
            return len(self._fallback)
        return readline.get_current_history_length()

    @property
    def session_count(self) -> int:
        """Number of commands added in the current session."""
        if not self._enabled:
            return len(self._fallback) - self._session_start_index
        return readline.get_current_history_length() - self._session_start_index

    # -- Fallback file I/O (when readline is unavailable) --

    def _load_fallback(self) -> None:
        """Load history from file into fallback list."""
        if self._path.exists():
            try:
                lines = self._path.read_text().splitlines()
                self._fallback = lines[-self._max_entries:]
            except (OSError, PermissionError):
                pass
        self._session_start_index = len(self._fallback)

    def _save_fallback(self) -> None:
        """Save fallback list to file."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text("\n".join(self._fallback[-self._max_entries:]) + "\n")
        except (OSError, PermissionError):
            pass
