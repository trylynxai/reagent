"""Main CLI entry point using Typer."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from reagent import __version__

# Create main app
app = typer.Typer(
    name="reagent",
    help="ReAgent - AI Agent Debugging & Observability Platform",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Create console for rich output
console = Console()
err_console = Console(stderr=True)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"reagent version {__version__}")
        raise typer.Exit()


# Global options stored in context
class GlobalContext:
    def __init__(self) -> None:
        self.config_path: str | None = None
        self.format: str = "human"
        self.verbose: bool = False
        self.project: str | None = None


@app.callback()
def main(
    ctx: typer.Context,
    config: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
    ),
    format: str = typer.Option(
        "human",
        "--format",
        "-f",
        help="Output format: human, json, markdown",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output",
    ),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project to operate on",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit",
        is_eager=True,
        callback=version_callback,
    ),
) -> None:
    """ReAgent CLI - Debug and observe AI agent executions."""

    # Store global options in context
    ctx.ensure_object(GlobalContext)
    ctx.obj.config_path = config
    ctx.obj.format = format
    ctx.obj.verbose = verbose
    ctx.obj.project = project


# Import and register commands
from reagent.cli.commands import list_cmd, inspect_cmd, replay_cmd, diff_cmd, export_cmd, config_cmd, failures_cmd

app.command(name="list")(list_cmd.list_runs)
app.command(name="ls")(list_cmd.list_runs)  # Alias
app.command(name="inspect")(inspect_cmd.inspect_run)
app.command(name="show")(inspect_cmd.inspect_run)  # Alias
app.command(name="replay")(replay_cmd.replay_run)
app.command(name="diff")(diff_cmd.diff_runs)
app.command(name="export")(export_cmd.export_run)
app.command(name="config")(config_cmd.config_cmd)

# Register failures subcommand group
app.add_typer(failures_cmd.app, name="failures")


# Search command
@app.command()
def search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum results"),
) -> None:
    """Search runs by query.

    Query syntax:
    - model:gpt-4 - Filter by model
    - status:failed - Filter by status
    - cost>0.05 - Filter by cost
    - "error text" - Full-text search
    - project:myproject AND model:gpt-4 - Compound query
    """
    from reagent.cli.formatters import get_formatter
    from reagent.client.reagent import ReAgent
    from reagent.analysis.search import SearchEngine

    try:
        client = ReAgent(config_path=ctx.obj.config_path, project=ctx.obj.project)
        engine = SearchEngine(client.storage)
        results = engine.search(query, limit=limit)

        formatter = get_formatter(ctx.obj.format)
        formatter.format_run_list(results, console)

    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# Delete command
@app.command()
def delete(
    ctx: typer.Context,
    run_id: str = typer.Argument(..., help="Run ID to delete"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation",
    ),
) -> None:
    """Delete a run."""
    from reagent.client.reagent import ReAgent

    if not force:
        confirm = typer.confirm(f"Are you sure you want to delete run {run_id}?")
        if not confirm:
            raise typer.Exit()

    try:
        client = ReAgent(config_path=ctx.obj.config_path)
        deleted = client.delete_run(run_id)

        if deleted:
            console.print(f"[green]Deleted run {run_id}[/green]")
        else:
            console.print(f"[yellow]Run {run_id} not found[/yellow]")

    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# Stats command
@app.command()
def stats(
    ctx: typer.Context,
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
) -> None:
    """Show usage statistics."""
    from reagent.client.reagent import ReAgent

    try:
        client = ReAgent(config_path=ctx.obj.config_path)
        project = project or ctx.obj.project

        total = client.count_runs(project=project)
        runs = client.list_runs(project=project, limit=1000)

        # Calculate stats
        total_cost = sum(r.total_cost_usd for r in runs)
        total_tokens = sum(r.total_tokens for r in runs)

        completed = sum(1 for r in runs if r.status.value == "completed")
        failed = sum(1 for r in runs if r.status.value == "failed")

        console.print("[bold]ReAgent Statistics[/bold]")
        console.print()
        console.print(f"Total runs: {total}")
        console.print(f"Completed: {completed}")
        console.print(f"Failed: {failed}")
        console.print(f"Total tokens: {total_tokens:,}")
        console.print(f"Total cost: ${total_cost:.4f}")

    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
