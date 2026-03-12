"""Interactive replay debugger with Rich-formatted output."""

from __future__ import annotations

import json
from typing import Any, Iterator, Optional
from uuid import UUID

from rich.columns import Columns
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from reagent.replay.engine import ReplayEngine
from reagent.replay.session import ReplaySession
from reagent.schema.steps import (
    AnyStep,
    LLMCallStep,
    ToolCallStep,
    RetrievalStep,
    ChainStep,
    AgentStep,
    ErrorStep,
    CustomStep,
)


# Step type display config
STEP_STYLES = {
    "llm_call": ("bold cyan", "LLM"),
    "tool_call": ("bold green", "TOOL"),
    "retrieval": ("bold magenta", "RAG"),
    "chain": ("bold blue", "CHAIN"),
    "agent": ("bold yellow", "AGENT"),
    "error": ("bold red", "ERROR"),
    "reasoning": ("dim", "REASON"),
    "checkpoint": ("dim", "CHKPT"),
    "custom": ("dim", "CUSTOM"),
}


def _truncate(text: str | None, length: int = 80) -> str:
    """Truncate text with ellipsis."""
    if not text:
        return ""
    text = text.replace("\n", " ")
    if len(text) > length:
        return text[:length - 3] + "..."
    return text


class ReplayDebugger:
    """Interactive debugger for replay sessions.

    Provides a Rich-formatted REPL for stepping through agent executions
    with inspection, breakpoints, and divergence tracking.

    Commands:
    - step (s)          Execute next step
    - next (n)          Skip to next LLM/tool call
    - continue (c)      Run to completion or breakpoint
    - inspect (i) [N]   Show step details (current or step N)
    - breakpoint (b) N  Set breakpoint at step N
    - clear (cl) [N]    Clear breakpoint(s)
    - watch (w) [expr]  Watch a value across steps
    - state             Show session state summary
    - list (l)          List all steps with status
    - goto N            Jump to step N
    - diff              Show divergences from original
    - help (h)          Show help
    - exit (q)          Quit replay
    """

    def __init__(self, engine: ReplayEngine, run_id: str) -> None:
        self._engine = engine
        self._run_id = run_id
        self._console = Console()
        self._session: Optional[ReplaySession] = None
        self._iterator: Optional[Iterator[tuple[AnyStep, ReplaySession]]] = None
        self._current_step: Optional[AnyStep] = None
        self._all_steps: list[AnyStep] = []
        self._executed_steps: set[int] = set()
        self._finished = False
        self._watches: dict[str, str] = {}  # name -> jmespath-like expression
        self._run = None

    @property
    def is_finished(self) -> bool:
        return self._finished

    def start(
        self,
        from_step: Optional[int] = None,
        to_step: Optional[int] = None,
    ) -> None:
        """Start the replay session and display run info."""
        # Load the full run for reference
        run_id_uuid = UUID(self._run_id) if isinstance(self._run_id, str) else self._run_id
        self._run = self._engine._loader.load_full(run_id_uuid)
        self._all_steps = list(self._run.steps)

        self._iterator = self._engine.replay_interactive(
            run_id=self._run_id,
        )

        # Skip to from_step if specified
        if from_step:
            for _ in range(from_step):
                try:
                    self._current_step, self._session = next(self._iterator)
                    self._executed_steps.add(self._current_step.step_number)
                except StopIteration:
                    self._finished = True
                    return

        # Get first step
        try:
            self._current_step, self._session = next(self._iterator)
        except StopIteration:
            self._finished = True
            return

        # Display welcome banner
        self._print_banner()

    def get_prompt(self) -> str:
        """Get the current prompt string."""
        if self._current_step and self._session:
            step = self._current_step
            style, label = STEP_STYLES.get(step.step_type, ("dim", "?"))
            total = self._session.total_steps
            return f"[{step.step_number}/{total}] {label}"
        return "reagent-dbg"

    def execute_command(self, cmd: str) -> None:
        """Execute a debugger command and print output."""
        parts = cmd.strip().split(maxsplit=1)
        if not parts:
            return

        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

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
            "watch": self._cmd_watch,
            "w": self._cmd_watch,
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
            handler(args)
        else:
            self._console.print(
                f"[red]Unknown command:[/red] {command}. Type 'help' for available commands."
            )

    # ── Command handlers ──────────────────────────────────────

    def _cmd_step(self, args: str) -> None:
        """Execute one step."""
        if self._finished:
            self._console.print("[dim]Replay finished.[/dim]")
            return

        try:
            self._executed_steps.add(self._current_step.step_number)
            self._current_step, self._session = next(self._iterator)
            self._print_step_summary(self._current_step)
            self._print_watches()
        except StopIteration:
            self._finished = True
            self._print_completion()

    def _cmd_next(self, args: str) -> None:
        """Skip to next significant step (LLM, tool, or error)."""
        significant_types = {"llm_call", "tool_call", "error"}

        while not self._finished:
            try:
                self._executed_steps.add(self._current_step.step_number)
                self._current_step, self._session = next(self._iterator)
                if self._current_step.step_type in significant_types:
                    self._print_step_summary(self._current_step)
                    self._print_watches()
                    return
            except StopIteration:
                self._finished = True
                self._print_completion()
                return

    def _cmd_continue(self, args: str) -> None:
        """Run to completion or next breakpoint."""
        steps_run = 0

        while not self._finished:
            try:
                self._executed_steps.add(self._current_step.step_number)
                self._current_step, self._session = next(self._iterator)
                steps_run += 1

                # Check for breakpoint
                if self._session.is_breakpoint(self._current_step.step_number):
                    self._console.print(
                        f"\n[bold yellow]Breakpoint[/bold yellow] hit at step "
                        f"[bold]{self._current_step.step_number}[/bold]"
                    )
                    self._print_step_summary(self._current_step)
                    return

            except StopIteration:
                self._finished = True
                break

        self._print_completion()

    def _cmd_inspect(self, args: str) -> None:
        """Show detailed step info. Optional step number argument."""
        step = self._current_step

        if args.strip():
            try:
                step_num = int(args.strip())
                step = self._find_step(step_num)
                if not step:
                    self._console.print(f"[red]Step {step_num} not found.[/red]")
                    return
            except ValueError:
                self._console.print("[red]Usage: inspect [step_number][/red]")
                return

        if not step:
            self._console.print("[dim]No current step.[/dim]")
            return

        self._print_step_detail(step)

    def _cmd_breakpoint(self, args: str) -> None:
        """Set a breakpoint or list all breakpoints."""
        if not args.strip():
            bps = sorted(self._session._breakpoints) if self._session else []
            if bps:
                table = Table(title="Breakpoints", show_header=True, box=None)
                table.add_column("Step", style="bold")
                table.add_column("Type", style="dim")
                for bp in bps:
                    bp_step = self._find_step(bp)
                    stype = bp_step.step_type if bp_step else "?"
                    table.add_row(str(bp), stype)
                self._console.print(table)
            else:
                self._console.print("[dim]No breakpoints set.[/dim]")
            return

        try:
            step_num = int(args.strip())
            self._session.set_breakpoint(step_num)
            self._console.print(
                f"[green]Breakpoint set[/green] at step [bold]{step_num}[/bold]"
            )
        except ValueError:
            self._console.print("[red]Usage: breakpoint <step_number>[/red]")

    def _cmd_clear(self, args: str) -> None:
        """Clear breakpoint(s)."""
        if not args.strip():
            self._session.clear_all_breakpoints()
            self._console.print("[green]All breakpoints cleared.[/green]")
            return

        try:
            step_num = int(args.strip())
            self._session.clear_breakpoint(step_num)
            self._console.print(
                f"[green]Breakpoint cleared[/green] at step [bold]{step_num}[/bold]"
            )
        except ValueError:
            self._console.print("[red]Usage: clear [step_number][/red]")

    def _cmd_watch(self, args: str) -> None:
        """Add, list, or remove watches."""
        args = args.strip()

        if not args:
            if self._watches:
                table = Table(title="Watches", show_header=True, box=None)
                table.add_column("Name", style="bold")
                table.add_column("Expression", style="cyan")
                for name, expr in self._watches.items():
                    table.add_row(name, expr)
                self._console.print(table)
            else:
                self._console.print("[dim]No watches set. Usage: watch <name> <field>[/dim]")
            return

        parts = args.split(maxsplit=1)
        if len(parts) == 1:
            # Remove watch
            name = parts[0]
            if name.startswith("-"):
                name = name[1:]
                if name in self._watches:
                    del self._watches[name]
                    self._console.print(f"[green]Watch removed:[/green] {name}")
                else:
                    self._console.print(f"[red]Watch not found:[/red] {name}")
            else:
                self._console.print("[dim]Usage: watch <name> <field> | watch -<name>[/dim]")
            return

        name, field = parts
        self._watches[name] = field
        self._console.print(f"[green]Watch added:[/green] {name} = {field}")

    def _cmd_state(self, args: str) -> None:
        """Show session state summary."""
        if not self._session:
            self._console.print("[dim]No active session.[/dim]")
            return

        summary = self._session.to_summary()

        table = Table(title="Session State", show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="bold")
        table.add_column("Value")

        table.add_row("Run ID", str(summary["run_id"])[:8] + "...")
        table.add_row("Mode", summary["mode"])
        table.add_row("Status", summary["status"])
        table.add_row(
            "Progress",
            f"{summary['current_step']}/{summary['total_steps']} "
            f"({summary['progress']:.0%})",
        )
        table.add_row("Divergences", str(summary["steps_diverged"]))
        table.add_row("Checkpoints", str(summary["checkpoints"]))
        table.add_row(
            "Breakpoints",
            ", ".join(map(str, summary["breakpoints"])) or "none",
        )

        self._console.print(table)

    def _cmd_list(self, args: str) -> None:
        """List all steps with color-coded types and status."""
        if not self._all_steps:
            self._console.print("[dim]No steps.[/dim]")
            return

        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("", width=3)  # markers
        table.add_column("#", style="dim", width=4)
        table.add_column("Type", width=10)
        table.add_column("Details", ratio=1)
        table.add_column("Duration", justify="right", width=10)

        for step in self._all_steps:
            # Markers
            markers = ""
            is_current = (
                self._current_step
                and step.step_number == self._current_step.step_number
            )
            is_bp = self._session and self._session.is_breakpoint(step.step_number)
            is_executed = step.step_number in self._executed_steps

            if is_current:
                markers += "[bold yellow]>[/bold yellow]"
            else:
                markers += " "
            if is_bp:
                markers += "[red]*[/red]"
            else:
                markers += " "
            if is_executed:
                markers += "[green]v[/green]"
            else:
                markers += " "

            # Type label
            style, label = STEP_STYLES.get(step.step_type, ("dim", "?"))
            type_text = f"[{style}]{label}[/{style}]"

            # Details
            details = self._get_step_brief(step)

            # Duration
            dur = _format_duration(step.duration_ms)

            table.add_row(markers, str(step.step_number), type_text, details, dur)

        self._console.print(table)

    def _cmd_goto(self, args: str) -> None:
        """Jump to a specific step by restarting the iterator."""
        if not args.strip():
            self._console.print("[red]Usage: goto <step_number>[/red]")
            return

        try:
            target = int(args.strip())
        except ValueError:
            self._console.print("[red]Invalid step number.[/red]")
            return

        if target < 0 or target >= len(self._all_steps):
            self._console.print(
                f"[red]Step {target} out of range (0-{len(self._all_steps) - 1}).[/red]"
            )
            return

        # Restart the iterator from scratch
        self._iterator = self._engine.replay_interactive(
            run_id=self._run_id,
        )
        self._executed_steps.clear()

        # Advance to target step
        try:
            for _ in range(target + 1):
                self._current_step, self._session = next(self._iterator)
                self._executed_steps.add(self._current_step.step_number)
        except StopIteration:
            self._finished = True
            self._console.print("[dim]Replay finished before reaching target.[/dim]")
            return

        self._console.print(
            f"[green]Jumped to step {target}[/green]"
        )
        self._print_step_summary(self._current_step)

    def _cmd_diff(self, args: str) -> None:
        """Show divergences from original execution."""
        if not self._session:
            self._console.print("[dim]No active session.[/dim]")
            return

        diverged = [r for r in self._session.results if r.diverged]
        if not diverged:
            self._console.print("[green]No divergences detected.[/green]")
            return

        table = Table(title="Divergences", show_header=True, box=None)
        table.add_column("Step", style="bold")
        table.add_column("Type", style="dim")
        table.add_column("Details")

        for r in diverged:
            table.add_row(
                str(r.step_number),
                r.step_type,
                r.divergence_details or "Output changed",
            )

        self._console.print(table)

    def _cmd_help(self, args: str) -> None:
        """Show help."""
        help_table = Table(
            title="Debugger Commands",
            show_header=True,
            box=None,
            padding=(0, 2),
        )
        help_table.add_column("Command", style="bold cyan")
        help_table.add_column("Alias", style="dim")
        help_table.add_column("Description")

        commands = [
            ("step", "s", "Execute next step"),
            ("next", "n", "Skip to next LLM/tool/error step"),
            ("continue", "c", "Run to completion or breakpoint"),
            ("inspect [N]", "i", "Show step details (current or step N)"),
            ("breakpoint N", "b", "Set breakpoint at step N (no arg: list)"),
            ("clear [N]", "cl", "Clear breakpoint (no arg: clear all)"),
            ("watch <name> <field>", "w", "Watch a step field across execution"),
            ("watch -<name>", "", "Remove a watch"),
            ("state", "", "Show session state summary"),
            ("list", "l", "List all steps with status markers"),
            ("goto N", "", "Jump to step N (restarts replay)"),
            ("diff", "", "Show divergences from original"),
            ("help", "h", "Show this help"),
            ("exit", "q", "Quit debugger"),
        ]

        for cmd, alias, desc in commands:
            help_table.add_row(cmd, alias, desc)

        self._console.print(help_table)
        self._console.print()
        self._console.print("[dim]List markers: > current  * breakpoint  v executed[/dim]")

    def _cmd_exit(self, args: str) -> None:
        """Exit the debugger."""
        self._finished = True
        self._console.print("[dim]Exiting...[/dim]")

    # ── Formatting helpers ────────────────────────────────────

    def _print_banner(self) -> None:
        """Print welcome banner with run info."""
        if not self._run:
            return

        meta = self._run.metadata
        status_color = "green" if meta.status.value == "completed" else "red"

        info_lines = []
        info_lines.append(f"[bold]Run:[/bold] {str(meta.run_id)[:8]}...")
        if meta.name:
            info_lines.append(f"[bold]Name:[/bold] {meta.name}")
        if meta.project:
            info_lines.append(f"[bold]Project:[/bold] {meta.project}")
        info_lines.append(
            f"[bold]Status:[/bold] [{status_color}]{meta.status.value}[/{status_color}]"
        )
        info_lines.append(f"[bold]Steps:[/bold] {meta.steps.total}")
        if meta.model:
            info_lines.append(f"[bold]Model:[/bold] {meta.model}")
        if meta.error:
            info_lines.append(f"[bold]Error:[/bold] [red]{_truncate(meta.error, 60)}[/red]")

        panel = Panel(
            "\n".join(info_lines),
            title="[bold]ReAgent Replay Debugger[/bold]",
            border_style="cyan",
            padding=(1, 2),
        )
        self._console.print(panel)

        if self._current_step:
            self._console.print()
            self._print_step_summary(self._current_step)

    def _print_step_summary(self, step: AnyStep) -> None:
        """Print a concise step summary line."""
        style, label = STEP_STYLES.get(step.step_type, ("dim", "?"))
        brief = self._get_step_brief(step)
        dur = _format_duration(step.duration_ms)

        self._console.print(
            f"  [{style}]{label:>5}[/{style}] "
            f"[bold]#{step.step_number}[/bold]  "
            f"{brief}"
            f"  [dim]{dur}[/dim]"
        )

    def _print_step_detail(self, step: AnyStep) -> None:
        """Print detailed step inspection panel."""
        style, label = STEP_STYLES.get(step.step_type, ("dim", "?"))

        # Header info
        header = Text()
        header.append(f"Step #{step.step_number}", style="bold")
        header.append(f"  [{label}]", style=style)
        if step.duration_ms:
            header.append(f"  {_format_duration(step.duration_ms)}", style="dim")

        self._console.print(header)
        self._console.print()

        if isinstance(step, LLMCallStep):
            self._print_llm_detail(step)
        elif isinstance(step, ToolCallStep):
            self._print_tool_detail(step)
        elif isinstance(step, RetrievalStep):
            self._print_retrieval_detail(step)
        elif isinstance(step, ChainStep):
            self._print_chain_detail(step)
        elif isinstance(step, AgentStep):
            self._print_agent_detail(step)
        elif isinstance(step, ErrorStep):
            self._print_error_detail(step)
        else:
            # Generic: dump as JSON
            data = step.model_dump(mode="json", exclude_none=True)
            self._console.print(
                Syntax(
                    json.dumps(data, indent=2, default=str),
                    "json",
                    theme="monokai",
                )
            )

    def _print_llm_detail(self, step: LLMCallStep) -> None:
        """Print LLM call details."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="bold")
        table.add_column("Value")

        table.add_row("Model", step.model or "unknown")
        if step.provider:
            table.add_row("Provider", step.provider)
        if step.temperature is not None:
            table.add_row("Temperature", str(step.temperature))
        if step.token_usage:
            table.add_row(
                "Tokens",
                f"{step.token_usage.prompt_tokens} prompt + "
                f"{step.token_usage.completion_tokens} completion = "
                f"{step.token_usage.total_tokens} total",
            )
        if step.cost_usd:
            table.add_row("Cost", f"${step.cost_usd:.4f}")
        if step.finish_reason:
            table.add_row("Finish", step.finish_reason)

        self._console.print(table)

        if step.prompt:
            self._console.print()
            self._console.print(
                Panel(
                    escape(_truncate(step.prompt, 500)),
                    title="Prompt",
                    border_style="dim",
                )
            )

        if step.response:
            self._console.print(
                Panel(
                    escape(_truncate(step.response, 500)),
                    title="Response",
                    border_style="cyan",
                )
            )

        if step.error:
            self._console.print(
                Panel(escape(step.error), title="Error", border_style="red")
            )

    def _print_tool_detail(self, step: ToolCallStep) -> None:
        """Print tool call details."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="bold")
        table.add_column("Value")

        table.add_row("Tool", step.tool_name)
        if step.tool_description:
            table.add_row("Description", step.tool_description)
        table.add_row("Success", "[green]Yes[/green]" if step.success else "[red]No[/red]")

        self._console.print(table)

        if step.input and (step.input.args or step.input.kwargs):
            input_data = {}
            if step.input.args:
                input_data["args"] = list(step.input.args)
            if step.input.kwargs:
                input_data.update(step.input.kwargs)
            self._console.print()
            self._console.print(
                Panel(
                    Syntax(
                        json.dumps(input_data, indent=2, default=str)[:500],
                        "json",
                        theme="monokai",
                    ),
                    title="Input",
                    border_style="dim",
                )
            )

        if step.output:
            if step.output.error:
                self._console.print(
                    Panel(
                        f"[red]{escape(step.output.error)}[/red]"
                        + (f"\n[dim]{step.output.error_type}[/dim]" if step.output.error_type else ""),
                        title="Error",
                        border_style="red",
                    )
                )
            elif step.output.result is not None:
                result_str = str(step.output.result)[:500]
                self._console.print(
                    Panel(
                        escape(result_str),
                        title="Result",
                        border_style="green",
                    )
                )

    def _print_retrieval_detail(self, step: RetrievalStep) -> None:
        """Print retrieval details."""
        self._console.print(f"  [bold]Query:[/bold] {escape(step.query)}")
        if step.index_name:
            self._console.print(f"  [bold]Index:[/bold] {step.index_name}")
        if step.results and step.results.documents:
            self._console.print(
                f"  [bold]Documents:[/bold] {len(step.results.documents)} returned"
            )
            for i, doc in enumerate(step.results.documents[:3]):
                content = str(doc.get("page_content", doc))[:100]
                self._console.print(f"    [{i}] {escape(content)}")
        if step.error:
            self._console.print(f"  [red]Error:[/red] {escape(step.error)}")

    def _print_chain_detail(self, step: ChainStep) -> None:
        """Print chain details."""
        self._console.print(f"  [bold]Chain:[/bold] {step.chain_name}")
        if step.chain_type:
            self._console.print(f"  [bold]Type:[/bold] {step.chain_type}")
        if step.input:
            self._console.print(
                Panel(
                    Syntax(
                        json.dumps(step.input, indent=2, default=str)[:300],
                        "json",
                        theme="monokai",
                    ),
                    title="Input",
                    border_style="dim",
                )
            )
        if step.output:
            self._console.print(
                Panel(
                    Syntax(
                        json.dumps(step.output, indent=2, default=str)[:300],
                        "json",
                        theme="monokai",
                    ),
                    title="Output",
                    border_style="green",
                )
            )
        if step.error:
            self._console.print(
                Panel(escape(step.error), title="Error", border_style="red")
            )

    def _print_agent_detail(self, step: AgentStep) -> None:
        """Print agent action details."""
        if step.agent_name:
            self._console.print(f"  [bold]Agent:[/bold] {step.agent_name}")
        if step.agent_type:
            self._console.print(f"  [bold]Type:[/bold] {step.agent_type}")
        self._console.print(f"  [bold]Action:[/bold] {step.action}")
        if step.thought:
            self._console.print(
                Panel(
                    escape(_truncate(step.thought, 300)),
                    title="Thought",
                    border_style="yellow",
                )
            )
        if step.action_input:
            self._console.print(f"  [bold]Input:[/bold] {json.dumps(step.action_input, default=str)[:200]}")
        if step.action_output:
            self._console.print(f"  [bold]Output:[/bold] {str(step.action_output)[:200]}")
        if step.final_answer:
            self._console.print(
                Panel(
                    escape(str(step.final_answer)[:300]),
                    title="Final Answer",
                    border_style="green",
                )
            )

    def _print_error_detail(self, step: ErrorStep) -> None:
        """Print error details with traceback."""
        self._console.print(
            f"  [bold red]{step.error_type}:[/bold red] {escape(step.error_message)}"
        )
        if step.source_step_type:
            self._console.print(f"  [bold]Source:[/bold] {step.source_step_type}")
        if step.recovered:
            self._console.print(f"  [green]Recovered:[/green] {step.recovery_action or 'yes'}")

        if step.error_traceback:
            self._console.print()
            self._console.print(
                Panel(
                    Syntax(
                        step.error_traceback,
                        "pytb",
                        theme="monokai",
                        line_numbers=True,
                    ),
                    title="Traceback",
                    border_style="red",
                )
            )

    def _print_watches(self) -> None:
        """Print watch values for current step."""
        if not self._watches or not self._current_step:
            return

        step_data = self._current_step.model_dump(mode="json")

        for name, field in self._watches.items():
            value = _resolve_field(step_data, field)
            if value is not None:
                self._console.print(
                    f"  [dim]watch[/dim] [bold]{name}[/bold] = {_truncate(str(value), 60)}"
                )

    def _print_completion(self) -> None:
        """Print completion summary."""
        if not self._session:
            self._console.print("[dim]Replay finished.[/dim]")
            return

        diverged = [r for r in self._session.results if r.diverged]
        total = len(self._session.results)

        self._console.print()
        summary = Text()
        summary.append("Replay complete: ", style="bold green")
        summary.append(f"{total} steps executed")
        if diverged:
            summary.append(f", {len(diverged)} divergences", style="yellow")
        self._console.print(summary)

    def _get_step_brief(self, step: AnyStep) -> str:
        """Get a brief description string for a step."""
        if isinstance(step, LLMCallStep):
            model = step.model or "?"
            tokens = ""
            if step.token_usage:
                tokens = f" ({step.token_usage.total_tokens} tok)"
            prompt_preview = ""
            if step.prompt:
                prompt_preview = f"  {_truncate(step.prompt, 40)}"
            elif step.response:
                prompt_preview = f"  -> {_truncate(step.response, 40)}"
            return f"{model}{tokens}{prompt_preview}"

        elif isinstance(step, ToolCallStep):
            status = "[green]ok[/green]" if step.success else "[red]fail[/red]"
            return f"{step.tool_name} {status}"

        elif isinstance(step, RetrievalStep):
            n_docs = len(step.results.documents) if step.results else 0
            return f"query: {_truncate(step.query, 40)} ({n_docs} docs)"

        elif isinstance(step, ChainStep):
            return step.chain_name or "chain"

        elif isinstance(step, AgentStep):
            agent = step.agent_name or ""
            return f"{agent} -> {step.action}"

        elif isinstance(step, ErrorStep):
            return f"[red]{step.error_type}: {_truncate(step.error_message, 50)}[/red]"

        elif isinstance(step, CustomStep):
            return step.event_name

        return step.step_type

    def _find_step(self, step_number: int) -> AnyStep | None:
        """Find a step by number."""
        for step in self._all_steps:
            if step.step_number == step_number:
                return step
        return None


def _format_duration(ms: int | None) -> str:
    """Format duration in human-readable form."""
    if ms is None:
        return ""
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        return f"{ms / 1000:.1f}s"
    else:
        return f"{ms / 60000:.1f}m"


def _resolve_field(data: dict, field_path: str) -> Any:
    """Resolve a dotted field path in a dict."""
    parts = field_path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current
