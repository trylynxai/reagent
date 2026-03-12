"""Output formatters for CLI."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.tree import Tree

from reagent.schema.run import Run, RunSummary
from reagent.schema.steps import AnyStep, LLMCallStep, ToolCallStep


class Formatter(ABC):
    """Base class for output formatters."""

    @abstractmethod
    def format_run_list(self, runs: list[RunSummary], console: Console) -> None:
        """Format a list of runs."""
        pass

    @abstractmethod
    def format_run(self, run: Run, console: Console) -> None:
        """Format a single run with details."""
        pass

    @abstractmethod
    def format_step(self, step: AnyStep, console: Console) -> None:
        """Format a single step."""
        pass

    @abstractmethod
    def format_diff(self, diff: Any, console: Console) -> None:
        """Format a diff result."""
        pass


class HumanFormatter(Formatter):
    """Human-readable, colorized output formatter."""

    def format_run_list(self, runs: list[RunSummary], console: Console) -> None:
        """Format a list of runs as a table."""
        if not runs:
            console.print("[yellow]No runs found[/yellow]")
            return

        table = Table(title="Runs", show_header=True, header_style="bold")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name")
        table.add_column("Status")
        table.add_column("Model")
        table.add_column("Steps", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Cost", justify="right")
        table.add_column("Duration", justify="right")
        table.add_column("Time")

        for run in runs:
            status_color = self._status_color(run.status.value)
            duration = self._format_duration(run.duration_ms)
            time_ago = self._format_time_ago(run.start_time)

            table.add_row(
                str(run.run_id)[:8],
                run.name or "-",
                f"[{status_color}]{run.status.value}[/{status_color}]",
                run.model or "-",
                str(run.step_count),
                f"{run.total_tokens:,}" if run.total_tokens else "-",
                f"${run.total_cost_usd:.4f}" if run.total_cost_usd else "-",
                duration,
                time_ago,
            )

        console.print(table)

    def format_run(self, run: Run, console: Console) -> None:
        """Format a single run with full details."""
        meta = run.metadata
        status_color = self._status_color(meta.status.value)

        # Header
        console.print(Panel(
            f"[bold]Run:[/bold] {meta.run_id}\n"
            f"[bold]Name:[/bold] {meta.name or '-'}\n"
            f"[bold]Project:[/bold] {meta.project or '-'}\n"
            f"[bold]Status:[/bold] [{status_color}]{meta.status.value}[/{status_color}]\n"
            f"[bold]Model:[/bold] {meta.model or '-'}",
            title="Run Details",
        ))

        # Stats
        console.print()
        console.print("[bold]Statistics:[/bold]")
        console.print(f"  Steps: {meta.steps.total}")
        console.print(f"  Tokens: {meta.tokens.total_tokens:,}")
        console.print(f"  Cost: ${meta.cost.total_usd:.4f}")
        console.print(f"  Duration: {self._format_duration(meta.duration_ms)}")

        if meta.error:
            console.print()
            console.print(f"[red][bold]Error:[/bold] {meta.error}[/red]")

        # Steps summary
        console.print()
        console.print(f"[bold]Steps ({len(run.steps)}):[/bold]")

        for step in run.steps[:20]:  # Limit to first 20
            self._format_step_summary(step, console)

        if len(run.steps) > 20:
            console.print(f"  ... and {len(run.steps) - 20} more steps")

    def format_step(self, step: AnyStep, console: Console) -> None:
        """Format a single step with full details."""
        console.print(Panel(
            f"[bold]Step #{step.step_number}[/bold] ({step.step_type})",
            expand=False,
        ))

        if isinstance(step, LLMCallStep):
            self._format_llm_step(step, console)
        elif isinstance(step, ToolCallStep):
            self._format_tool_step(step, console)
        else:
            self._format_generic_step(step, console)

    def format_diff(self, diff: Any, console: Console) -> None:
        """Format a diff result."""
        console.print(Panel(
            f"[bold]Comparing:[/bold]\n"
            f"  A: {diff.run_id_a}\n"
            f"  B: {diff.run_id_b}\n\n"
            f"[bold]Similarity:[/bold] {diff.overall_similarity:.1%}\n"
            f"[bold]Steps:[/bold] {diff.step_count_a} vs {diff.step_count_b}",
            title="Diff Result",
        ))

        console.print()
        console.print(f"  Added: [green]+{diff.steps_added}[/green]")
        console.print(f"  Removed: [red]-{diff.steps_removed}[/red]")
        console.print(f"  Modified: [yellow]~{diff.steps_modified}[/yellow]")
        console.print(f"  Unchanged: {diff.steps_unchanged}")

        if diff.metadata_diff:
            console.print()
            console.print("[bold]Metadata differences:[/bold]")
            for field, (a, b) in diff.metadata_diff.items():
                console.print(f"  {field}: [red]{a}[/red] -> [green]{b}[/green]")

    def _format_step_summary(self, step: AnyStep, console: Console) -> None:
        """Format a step summary line."""
        duration = self._format_duration(step.duration_ms) if step.duration_ms else "-"

        if isinstance(step, LLMCallStep):
            model = step.model or "?"
            tokens = step.token_usage.total_tokens if step.token_usage else 0
            console.print(f"  [cyan]#{step.step_number}[/cyan] LLM ({model}) - {tokens} tokens, {duration}")
        elif isinstance(step, ToolCallStep):
            status = "[green]ok[/green]" if step.success else "[red]error[/red]"
            console.print(f"  [cyan]#{step.step_number}[/cyan] Tool ({step.tool_name}) - {status}, {duration}")
        else:
            console.print(f"  [cyan]#{step.step_number}[/cyan] {step.step_type} - {duration}")

    def _format_llm_step(self, step: LLMCallStep, console: Console) -> None:
        """Format an LLM step with full details."""
        console.print(f"[bold]Model:[/bold] {step.model}")
        if step.provider:
            console.print(f"[bold]Provider:[/bold] {step.provider}")

        if step.token_usage:
            console.print(f"[bold]Tokens:[/bold] {step.token_usage.prompt_tokens} prompt + {step.token_usage.completion_tokens} completion = {step.token_usage.total_tokens} total")

        if step.cost_usd:
            console.print(f"[bold]Cost:[/bold] ${step.cost_usd:.4f}")

        if step.prompt:
            console.print()
            console.print("[bold]Prompt:[/bold]")
            console.print(Panel(step.prompt[:500] + ("..." if len(step.prompt) > 500 else ""), expand=False))

        if step.response:
            console.print()
            console.print("[bold]Response:[/bold]")
            console.print(Panel(step.response[:500] + ("..." if len(step.response) > 500 else ""), expand=False))

        if step.error:
            console.print()
            console.print(f"[red][bold]Error:[/bold] {step.error}[/red]")

    def _format_tool_step(self, step: ToolCallStep, console: Console) -> None:
        """Format a tool step with full details."""
        console.print(f"[bold]Tool:[/bold] {step.tool_name}")
        if step.tool_description:
            console.print(f"[bold]Description:[/bold] {step.tool_description}")

        status = "[green]Success[/green]" if step.success else "[red]Failed[/red]"
        console.print(f"[bold]Status:[/bold] {status}")

        if step.input.kwargs:
            console.print()
            console.print("[bold]Input:[/bold]")
            console.print(Syntax(json.dumps(step.input.kwargs, indent=2, default=str), "json"))

        if step.output:
            console.print()
            console.print("[bold]Output:[/bold]")
            if step.output.error:
                console.print(f"[red]{step.output.error}[/red]")
            else:
                output_str = json.dumps(step.output.result, indent=2, default=str)
                console.print(Syntax(output_str[:500], "json"))

    def _format_generic_step(self, step: AnyStep, console: Console) -> None:
        """Format a generic step."""
        data = step.model_dump(exclude={"step_id", "run_id", "parent_step_id"})
        console.print(Syntax(json.dumps(data, indent=2, default=str), "json"))

    def _status_color(self, status: str) -> str:
        """Get color for a status."""
        colors = {
            "running": "blue",
            "completed": "green",
            "failed": "red",
            "partial": "yellow",
            "cancelled": "dim",
        }
        return colors.get(status, "white")

    def _format_duration(self, ms: int | None) -> str:
        """Format duration in human-readable form."""
        if ms is None:
            return "-"
        if ms < 1000:
            return f"{ms}ms"
        elif ms < 60000:
            return f"{ms / 1000:.1f}s"
        else:
            return f"{ms / 60000:.1f}m"

    def _format_time_ago(self, dt: datetime) -> str:
        """Format datetime as time ago."""
        now = datetime.utcnow()
        delta = now - dt

        if delta.days > 365:
            return f"{delta.days // 365}y ago"
        elif delta.days > 30:
            return f"{delta.days // 30}mo ago"
        elif delta.days > 0:
            return f"{delta.days}d ago"
        elif delta.seconds > 3600:
            return f"{delta.seconds // 3600}h ago"
        elif delta.seconds > 60:
            return f"{delta.seconds // 60}m ago"
        else:
            return "just now"


class JSONFormatter(Formatter):
    """JSON output formatter."""

    def format_run_list(self, runs: list[RunSummary], console: Console) -> None:
        """Format runs as JSON array."""
        data = [run.model_dump(mode="json") for run in runs]
        console.print(json.dumps(data, indent=2, default=str))

    def format_run(self, run: Run, console: Console) -> None:
        """Format run as JSON."""
        data = {
            "metadata": run.metadata.model_dump(mode="json"),
            "steps": [step.model_dump(mode="json") for step in run.steps],
        }
        console.print(json.dumps(data, indent=2, default=str))

    def format_step(self, step: AnyStep, console: Console) -> None:
        """Format step as JSON."""
        console.print(json.dumps(step.model_dump(mode="json"), indent=2, default=str))

    def format_diff(self, diff: Any, console: Console) -> None:
        """Format diff as JSON."""
        console.print(json.dumps(diff.to_dict(), indent=2, default=str))


class MarkdownFormatter(Formatter):
    """Markdown output formatter."""

    def format_run_list(self, runs: list[RunSummary], console: Console) -> None:
        """Format runs as markdown table."""
        lines = [
            "| ID | Name | Status | Model | Steps | Cost |",
            "|---|---|---|---|---|---|",
        ]

        for run in runs:
            lines.append(
                f"| {str(run.run_id)[:8]} | {run.name or '-'} | {run.status.value} | "
                f"{run.model or '-'} | {run.step_count} | ${run.total_cost_usd:.4f} |"
            )

        console.print(Markdown("\n".join(lines)))

    def format_run(self, run: Run, console: Console) -> None:
        """Format run as markdown."""
        meta = run.metadata
        lines = [
            f"# Run: {meta.run_id}",
            "",
            f"**Name:** {meta.name or '-'}",
            f"**Project:** {meta.project or '-'}",
            f"**Status:** {meta.status.value}",
            f"**Model:** {meta.model or '-'}",
            "",
            "## Statistics",
            "",
            f"- Steps: {meta.steps.total}",
            f"- Tokens: {meta.tokens.total_tokens:,}",
            f"- Cost: ${meta.cost.total_usd:.4f}",
            "",
            "## Steps",
            "",
        ]

        for step in run.steps:
            lines.append(f"### Step #{step.step_number} ({step.step_type})")
            lines.append("")
            lines.append(f"```json\n{json.dumps(step.model_dump(mode='json'), indent=2, default=str)}\n```")
            lines.append("")

        console.print(Markdown("\n".join(lines)))

    def format_step(self, step: AnyStep, console: Console) -> None:
        """Format step as markdown."""
        lines = [
            f"## Step #{step.step_number} ({step.step_type})",
            "",
            f"```json\n{json.dumps(step.model_dump(mode='json'), indent=2, default=str)}\n```",
        ]
        console.print(Markdown("\n".join(lines)))

    def format_diff(self, diff: Any, console: Console) -> None:
        """Format diff as markdown."""
        lines = [
            "# Diff Result",
            "",
            f"- **Run A:** {diff.run_id_a}",
            f"- **Run B:** {diff.run_id_b}",
            f"- **Similarity:** {diff.overall_similarity:.1%}",
            "",
            "## Summary",
            "",
            f"- Added: {diff.steps_added}",
            f"- Removed: {diff.steps_removed}",
            f"- Modified: {diff.steps_modified}",
            f"- Unchanged: {diff.steps_unchanged}",
        ]
        console.print(Markdown("\n".join(lines)))


def get_formatter(format: str) -> Formatter:
    """Get formatter for the given format name.

    Args:
        format: Format name (human, json, markdown)

    Returns:
        Formatter instance
    """
    formatters = {
        "human": HumanFormatter,
        "json": JSONFormatter,
        "markdown": MarkdownFormatter,
        "md": MarkdownFormatter,
    }

    formatter_class = formatters.get(format.lower(), HumanFormatter)
    return formatter_class()
