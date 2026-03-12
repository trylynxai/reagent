"""Interactive replay debugger."""

from __future__ import annotations

import json
from typing import Any, Iterator, Optional

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from reagent.replay.engine import ReplayEngine
from reagent.replay.session import ReplaySession
from reagent.schema.steps import AnyStep


class ReplayDebugger:
    """Interactive debugger for replay sessions.

    Commands:
    - step (s): Execute next step
    - next (n): Skip to next significant step (LLM/tool)
    - continue (c): Run to completion or breakpoint
    - inspect (i): Show current step details
    - breakpoint (b) <step>: Set breakpoint
    - clear (cl) <step>: Clear breakpoint
    - state: Show current virtual state
    - list (l): List steps
    - goto <step>: Jump to step
    - diff: Compare with original execution
    - help (h): Show help
    - exit (q): Quit replay
    """

    def __init__(self, engine: ReplayEngine, run_id: str) -> None:
        """Initialize the debugger.

        Args:
            engine: Replay engine
            run_id: Run to replay
        """
        self._engine = engine
        self._run_id = run_id
        self._console = Console()
        self._session: Optional[ReplaySession] = None
        self._iterator: Optional[Iterator[tuple[AnyStep, ReplaySession]]] = None
        self._current_step: Optional[AnyStep] = None
        self._finished = False

    @property
    def is_finished(self) -> bool:
        """Check if replay is finished."""
        return self._finished

    def start(
        self,
        from_step: Optional[int] = None,
        to_step: Optional[int] = None,
    ) -> None:
        """Start the replay session."""
        self._iterator = self._engine.replay_interactive(
            run_id=self._run_id,
        )

        # Skip to from_step if specified
        if from_step:
            for _ in range(from_step):
                try:
                    self._current_step, self._session = next(self._iterator)
                except StopIteration:
                    self._finished = True
                    return

        # Get first step
        try:
            self._current_step, self._session = next(self._iterator)
        except StopIteration:
            self._finished = True

    def get_prompt(self) -> str:
        """Get the current prompt string."""
        if self._current_step:
            return f"[{self._current_step.step_number}/{self._session.total_steps}] ({self._current_step.step_type})>"
        return ">"

    def execute_command(self, cmd: str) -> str:
        """Execute a debugger command.

        Args:
            cmd: Command string

        Returns:
            Output message
        """
        parts = cmd.strip().split()
        if not parts:
            return ""

        command = parts[0].lower()
        args = parts[1:]

        handlers = {
            "step": self._cmd_step,
            "s": self._cmd_step,
            "next": self._cmd_next,
            "n": self._cmd_next,
            "continue": self._cmd_continue,
            "c": self._cmd_continue,
            "inspect": self._cmd_inspect,
            "i": self._cmd_inspect,
            "breakpoint": self._cmd_breakpoint,
            "b": self._cmd_breakpoint,
            "clear": self._cmd_clear,
            "cl": self._cmd_clear,
            "state": self._cmd_state,
            "list": self._cmd_list,
            "l": self._cmd_list,
            "goto": self._cmd_goto,
            "diff": self._cmd_diff,
            "help": self._cmd_help,
            "h": self._cmd_help,
            "exit": self._cmd_exit,
            "quit": self._cmd_exit,
            "q": self._cmd_exit,
        }

        handler = handlers.get(command)
        if handler:
            return handler(args)
        else:
            return f"Unknown command: {command}. Type 'help' for available commands."

    def _cmd_step(self, args: list[str]) -> str:
        """Execute one step."""
        if self._finished:
            return "Replay finished."

        try:
            self._current_step, self._session = next(self._iterator)
            return self._format_step_summary(self._current_step)
        except StopIteration:
            self._finished = True
            return "Replay finished."

    def _cmd_next(self, args: list[str]) -> str:
        """Skip to next significant step (LLM or tool call)."""
        significant_types = {"llm_call", "tool_call", "error"}

        while not self._finished:
            try:
                self._current_step, self._session = next(self._iterator)
                if self._current_step.step_type in significant_types:
                    return self._format_step_summary(self._current_step)
            except StopIteration:
                self._finished = True
                return "Replay finished."

        return "Replay finished."

    def _cmd_continue(self, args: list[str]) -> str:
        """Run to completion or next breakpoint."""
        while not self._finished:
            try:
                self._current_step, self._session = next(self._iterator)

                # Check for breakpoint
                if self._session.is_breakpoint(self._current_step.step_number):
                    return f"Hit breakpoint at step {self._current_step.step_number}"

            except StopIteration:
                self._finished = True
                break

        return f"Replay completed. {len(self._session.results)} steps executed."

    def _cmd_inspect(self, args: list[str]) -> str:
        """Show current step details."""
        if not self._current_step:
            return "No current step."

        step_data = self._current_step.model_dump(mode="json")
        return json.dumps(step_data, indent=2, default=str)

    def _cmd_breakpoint(self, args: list[str]) -> str:
        """Set a breakpoint."""
        if not args:
            # List breakpoints
            bps = sorted(self._session._breakpoints)
            if bps:
                return f"Breakpoints: {', '.join(map(str, bps))}"
            return "No breakpoints set."

        try:
            step_num = int(args[0])
            self._session.set_breakpoint(step_num)
            return f"Breakpoint set at step {step_num}"
        except ValueError:
            return "Invalid step number."

    def _cmd_clear(self, args: list[str]) -> str:
        """Clear a breakpoint."""
        if not args:
            self._session.clear_all_breakpoints()
            return "All breakpoints cleared."

        try:
            step_num = int(args[0])
            self._session.clear_breakpoint(step_num)
            return f"Breakpoint cleared at step {step_num}"
        except ValueError:
            return "Invalid step number."

    def _cmd_state(self, args: list[str]) -> str:
        """Show current virtual state."""
        if not self._session:
            return "No active session."

        summary = self._session.to_summary()
        return json.dumps(summary, indent=2, default=str)

    def _cmd_list(self, args: list[str]) -> str:
        """List steps."""
        # Load run to get all steps
        run = self._engine._loader.load_full(self._run_id)

        lines = []
        for step in run.steps[:30]:  # Limit output
            marker = ">" if self._current_step and step.step_number == self._current_step.step_number else " "
            bp = "*" if self._session and self._session.is_breakpoint(step.step_number) else " "
            lines.append(f"{marker}{bp} {step.step_number:3d} {step.step_type}")

        if len(run.steps) > 30:
            lines.append(f"  ... and {len(run.steps) - 30} more steps")

        return "\n".join(lines)

    def _cmd_goto(self, args: list[str]) -> str:
        """Jump to a specific step."""
        if not args:
            return "Usage: goto <step_number>"

        try:
            step_num = int(args[0])
            # This would require restarting the iterator - simplified for now
            return f"Goto not fully implemented. Use 'step' to advance."
        except ValueError:
            return "Invalid step number."

    def _cmd_diff(self, args: list[str]) -> str:
        """Show differences from original."""
        if not self._session:
            return "No active session."

        diverged = [r for r in self._session.results if r.diverged]
        if not diverged:
            return "No divergences detected."

        lines = ["Diverged steps:"]
        for r in diverged:
            lines.append(f"  Step {r.step_number}: {r.divergence_details}")

        return "\n".join(lines)

    def _cmd_help(self, args: list[str]) -> str:
        """Show help."""
        return """
Available commands:
  step (s)          - Execute next step
  next (n)          - Skip to next LLM/tool call
  continue (c)      - Run to completion or breakpoint
  inspect (i)       - Show current step details
  breakpoint (b) N  - Set breakpoint at step N
  clear (cl) [N]    - Clear breakpoint(s)
  state             - Show session state
  list (l)          - List all steps
  goto N            - Jump to step N
  diff              - Show divergences
  help (h)          - Show this help
  exit (q)          - Quit replay
""".strip()

    def _cmd_exit(self, args: list[str]) -> str:
        """Exit the debugger."""
        self._finished = True
        return "Exiting..."

    def _format_step_summary(self, step: AnyStep) -> str:
        """Format a brief step summary."""
        if hasattr(step, "model"):
            return f"Step {step.step_number}: {step.step_type} ({step.model})"
        elif hasattr(step, "tool_name"):
            return f"Step {step.step_number}: {step.step_type} ({step.tool_name})"
        else:
            return f"Step {step.step_number}: {step.step_type}"
