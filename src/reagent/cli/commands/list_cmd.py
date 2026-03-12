"""List command - List recorded runs."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

console = Console()
err_console = Console(stderr=True)


def list_runs(
    ctx: typer.Context,
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Filter by model"),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum results"),
    sort: str = typer.Option("start_time", "--sort", help="Sort by: start_time, duration, cost, steps"),
    order: str = typer.Option("desc", "--order", help="Sort order: asc, desc"),
) -> None:
    """List recorded runs.

    Examples:
        reagent list
        reagent list --project myproject
        reagent list --status failed --limit 10
        reagent list --model gpt-4 --sort cost
    """
    from reagent.cli.formatters import get_formatter
    from reagent.client.reagent import ReAgent

    try:
        client = ReAgent(config_path=ctx.obj.config_path)

        runs = client.list_runs(
            project=project or ctx.obj.project,
            status=status,
            model=model,
            limit=limit,
            sort_by=sort,
            sort_order=order,
        )

        formatter = get_formatter(ctx.obj.format)
        formatter.format_run_list(runs, console)

    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        if ctx.obj.verbose:
            import traceback
            err_console.print(traceback.format_exc())
        raise typer.Exit(1)
