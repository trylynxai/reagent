"""Failures command - View and analyze agent failures."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from reagent.client.reagent import ReAgent
from reagent.core.constants import Status
from reagent.storage.base import RunFilter, Pagination

app = typer.Typer(name="failures", help="View and analyze agent failures")
console = Console()
err_console = Console(stderr=True)


# Failure category colors
CATEGORY_COLORS = {
    "tool_timeout": "yellow",
    "rate_limit": "magenta",
    "context_overflow": "cyan",
    "tool_error": "red",
    "validation_error": "bright_red",
    "chain_error": "blue",
    "authentication": "bright_yellow",
    "connection_error": "red",
    "permission_error": "bright_yellow",
    "resource_exhausted": "bright_red",
    "unknown": "dim",
}


def _get_category_color(category: str | None) -> str:
    """Get color for a failure category."""
    if not category:
        return "dim"
    return CATEGORY_COLORS.get(category, "red")


def _format_duration(ms: int | None) -> str:
    """Format duration in human-readable form."""
    if ms is None:
        return "-"
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        return f"{ms / 1000:.1f}s"
    else:
        return f"{ms / 60000:.1f}m"


def _format_time_ago(dt: datetime) -> str:
    """Format datetime as relative time."""
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


def _truncate(text: str | None, max_len: int = 50) -> str:
    """Truncate text with ellipsis."""
    if not text:
        return "-"
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


@app.command("list")
def list_failures(
    ctx: typer.Context,
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by failure category"),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum results"),
    since: Optional[str] = typer.Option(None, "--since", "-s", help="Show failures since (e.g., '1d', '2h', '30m')"),
) -> None:
    """List failed runs.

    Examples:
        reagent failures list
        reagent failures list --project myproject
        reagent failures list --category tool_timeout --limit 10
        reagent failures list --since 24h
    """
    from reagent.cli.main import GlobalContext

    try:
        global_ctx: GlobalContext = ctx.obj
        client = ReAgent(config_path=global_ctx.config_path)

        # Build filter
        since_dt = None
        if since:
            since_dt = _parse_duration_ago(since)

        filters = RunFilter(
            project=project or global_ctx.project,
            status=Status.FAILED,
            failure_category=category,
            since=since_dt,
        )

        pagination = Pagination(
            limit=limit,
            sort_by="start_time",
            sort_order="desc",
        )

        runs = client.storage.list_runs(filters=filters, pagination=pagination)

        if not runs:
            console.print("[yellow]No failed runs found[/yellow]")
            return

        # Create table
        table = Table(title="Failed Runs", show_header=True, header_style="bold")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name")
        table.add_column("Category")
        table.add_column("Error Preview")
        table.add_column("Duration", justify="right")
        table.add_column("Time")

        for run in runs:
            category_color = _get_category_color(run.failure_category)
            category_text = run.failure_category or "unknown"

            table.add_row(
                str(run.run_id)[:8],
                run.name or "-",
                f"[{category_color}]{category_text}[/{category_color}]",
                _truncate(run.error, 40),
                _format_duration(run.duration_ms),
                _format_time_ago(run.start_time),
            )

        console.print(table)
        console.print(f"\n[dim]Showing {len(runs)} failed run(s)[/dim]")

    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        if ctx.obj and ctx.obj.verbose:
            import traceback
            err_console.print(traceback.format_exc())
        raise typer.Exit(1)


@app.command("inspect")
def inspect_failure(
    ctx: typer.Context,
    run_id: str = typer.Argument(..., help="Run ID to inspect"),
    show_traceback: bool = typer.Option(True, "--traceback/--no-traceback", help="Show full traceback"),
    show_steps: bool = typer.Option(True, "--steps/--no-steps", help="Show execution steps"),
) -> None:
    """Inspect a failed run with full details.

    Examples:
        reagent failures inspect abc123
        reagent failures inspect abc123 --no-traceback
        reagent failures inspect abc123 --no-steps
    """
    from reagent.cli.main import GlobalContext
    from reagent.schema.steps import ErrorStep, ToolCallStep, LLMCallStep

    try:
        global_ctx: GlobalContext = ctx.obj
        client = ReAgent(config_path=global_ctx.config_path)

        run = client.load_run(run_id)
        meta = run.metadata

        # Header panel
        category_color = _get_category_color(meta.failure_category)
        category = meta.failure_category or "unknown"

        header_text = Text()
        header_text.append("Run: ", style="bold")
        header_text.append(str(meta.run_id), style="cyan")
        header_text.append("\nName: ", style="bold")
        header_text.append(meta.name or "-")
        header_text.append("\nProject: ", style="bold")
        header_text.append(meta.project or "-")
        header_text.append("\nStatus: ", style="bold")
        header_text.append("FAILED", style="bold red")
        header_text.append("\nCategory: ", style="bold")
        header_text.append(category, style=f"bold {category_color}")
        header_text.append("\nDuration: ", style="bold")
        header_text.append(_format_duration(meta.duration_ms))
        header_text.append("\nTime: ", style="bold")
        header_text.append(meta.start_time.isoformat())

        console.print(Panel(header_text, title="[bold red]Failed Run[/bold red]", border_style="red"))

        # Error panel
        if meta.error:
            console.print()
            error_text = Text()
            error_text.append(meta.error_type or "Error", style="bold red")
            error_text.append(": ")
            error_text.append(meta.error)
            console.print(Panel(error_text, title="[bold]Error[/bold]", border_style="red"))

        # Find ErrorStep with traceback
        if show_traceback:
            for step in run.steps:
                if isinstance(step, ErrorStep) and step.error_traceback:
                    console.print()
                    console.print("[bold]Traceback:[/bold]")
                    console.print(Syntax(
                        step.error_traceback,
                        "python",
                        theme="monokai",
                        line_numbers=False,
                        word_wrap=True,
                    ))
                    break

        # Execution timeline
        if show_steps:
            console.print()
            console.print(f"[bold]Execution Steps ({len(run.steps)}):[/bold]")

            for step in run.steps:
                step_style = "dim"
                status_icon = "[green]OK[/green]"

                # Check for errors
                has_error = False
                if isinstance(step, ErrorStep):
                    has_error = True
                    step_style = "red"
                    status_icon = "[red]ERROR[/red]"
                elif isinstance(step, ToolCallStep) and not step.success:
                    has_error = True
                    step_style = "yellow"
                    status_icon = "[yellow]FAIL[/yellow]"
                elif isinstance(step, LLMCallStep) and step.error:
                    has_error = True
                    step_style = "yellow"
                    status_icon = "[yellow]FAIL[/yellow]"

                duration = _format_duration(step.duration_ms)

                # Build step summary
                if isinstance(step, LLMCallStep):
                    summary = f"LLM ({step.model})"
                    if step.error:
                        summary += f" - {_truncate(step.error, 30)}"
                elif isinstance(step, ToolCallStep):
                    summary = f"Tool ({step.tool_name})"
                    if step.output and step.output.error:
                        summary += f" - {_truncate(step.output.error, 30)}"
                elif isinstance(step, ErrorStep):
                    summary = f"Error: {_truncate(step.error_message, 40)}"
                else:
                    summary = step.step_type

                # Arrow indicator for error steps
                prefix = "  "
                if has_error:
                    prefix = "> "

                console.print(f"{prefix}[cyan]#{step.step_number}[/cyan] {status_icon} [{step_style}]{summary}[/{step_style}] ({duration})")

    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        if ctx.obj and ctx.obj.verbose:
            import traceback
            err_console.print(traceback.format_exc())
        raise typer.Exit(1)


@app.command("stats")
def failure_stats(
    ctx: typer.Context,
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
    since: Optional[str] = typer.Option(None, "--since", "-s", help="Stats since (e.g., '7d', '24h')"),
) -> None:
    """Show failure statistics.

    Examples:
        reagent failures stats
        reagent failures stats --project myproject
        reagent failures stats --since 7d
    """
    from reagent.cli.main import GlobalContext

    try:
        global_ctx: GlobalContext = ctx.obj
        client = ReAgent(config_path=global_ctx.config_path)

        project = project or global_ctx.project
        since_dt = _parse_duration_ago(since) if since else None

        # Get all runs for the period
        all_filter = RunFilter(project=project, since=since_dt)
        all_pagination = Pagination(limit=1000, sort_order="desc")
        all_runs = client.storage.list_runs(filters=all_filter, pagination=all_pagination)

        # Get failed runs
        failed_filter = RunFilter(project=project, status=Status.FAILED, since=since_dt)
        failed_runs = client.storage.list_runs(filters=failed_filter, pagination=all_pagination)

        total_count = len(all_runs)
        failed_count = len(failed_runs)

        if total_count == 0:
            console.print("[yellow]No runs found[/yellow]")
            return

        failure_rate = (failed_count / total_count) * 100 if total_count > 0 else 0

        # Header
        console.print(Panel(
            f"[bold]Total Runs:[/bold] {total_count}\n"
            f"[bold]Failed Runs:[/bold] [red]{failed_count}[/red]\n"
            f"[bold]Failure Rate:[/bold] [{'red' if failure_rate > 10 else 'yellow' if failure_rate > 5 else 'green'}]{failure_rate:.1f}%[/]",
            title="[bold]Failure Statistics[/bold]",
        ))

        if failed_count == 0:
            console.print("\n[green]No failures to analyze![/green]")
            return

        # Category breakdown
        category_counts: Counter[str] = Counter()
        tool_errors: Counter[str] = Counter()

        for run in failed_runs:
            category = run.failure_category or "unknown"
            category_counts[category] += 1

        console.print()
        console.print("[bold]Failures by Category:[/bold]")

        table = Table(show_header=True, header_style="bold")
        table.add_column("Category")
        table.add_column("Count", justify="right")
        table.add_column("Percentage", justify="right")
        table.add_column("Bar")

        max_count = max(category_counts.values()) if category_counts else 1

        for category, count in category_counts.most_common():
            color = _get_category_color(category)
            pct = (count / failed_count) * 100
            bar_width = int((count / max_count) * 20)
            bar = "[" + color + "]" + "█" * bar_width + "[/" + color + "]"

            table.add_row(
                f"[{color}]{category}[/{color}]",
                str(count),
                f"{pct:.1f}%",
                bar,
            )

        console.print(table)

        # Recent failures
        console.print()
        console.print("[bold]Recent Failures:[/bold]")

        recent_table = Table(show_header=True, header_style="bold")
        recent_table.add_column("Time")
        recent_table.add_column("Name")
        recent_table.add_column("Category")
        recent_table.add_column("Error")

        for run in failed_runs[:5]:
            color = _get_category_color(run.failure_category)
            recent_table.add_row(
                _format_time_ago(run.start_time),
                run.name or "-",
                f"[{color}]{run.failure_category or 'unknown'}[/{color}]",
                _truncate(run.error, 35),
            )

        console.print(recent_table)

    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        if ctx.obj and ctx.obj.verbose:
            import traceback
            err_console.print(traceback.format_exc())
        raise typer.Exit(1)


def _parse_duration_ago(duration: str) -> datetime:
    """Parse a duration string like '1d', '2h', '30m' into a datetime."""
    from datetime import timedelta

    now = datetime.utcnow()

    if not duration:
        return now

    unit = duration[-1].lower()
    try:
        value = int(duration[:-1])
    except ValueError:
        raise ValueError(f"Invalid duration format: {duration}")

    if unit == "d":
        return now - timedelta(days=value)
    elif unit == "h":
        return now - timedelta(hours=value)
    elif unit == "m":
        return now - timedelta(minutes=value)
    elif unit == "w":
        return now - timedelta(weeks=value)
    else:
        raise ValueError(f"Unknown duration unit: {unit}. Use d, h, m, or w.")


# For direct command registration (non-subapp)
list_cmd = list_failures
inspect_cmd = inspect_failure
stats_cmd = failure_stats
