"""Inspect command - View run details."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

console = Console()
err_console = Console(stderr=True)


def inspect_run(
    ctx: typer.Context,
    run_id: str = typer.Argument(..., help="Run ID to inspect"),
    steps: Optional[str] = typer.Option(None, "--steps", "-s", help="Step range (e.g., 0-10, 5)"),
    show_payload: bool = typer.Option(False, "--payload", help="Show full payloads"),
    cost: bool = typer.Option(False, "--cost", help="Show cost breakdown"),
) -> None:
    """Inspect a run's details.

    Examples:
        reagent inspect abc123
        reagent inspect abc123 --steps 0-5
        reagent inspect abc123 --cost
    """
    from reagent.cli.formatters import get_formatter
    from reagent.client.reagent import ReAgent

    try:
        client = ReAgent(config_path=ctx.obj.config_path)

        # Parse step range
        start_step = None
        end_step = None
        if steps:
            if "-" in steps:
                parts = steps.split("-")
                start_step = int(parts[0]) if parts[0] else None
                end_step = int(parts[1]) if parts[1] else None
            else:
                start_step = int(steps)
                end_step = start_step + 1

        run = client.load_run(run_id)

        # Filter steps if range specified
        if start_step is not None or end_step is not None:
            filtered_steps = [
                s for s in run.steps
                if (start_step is None or s.step_number >= start_step)
                and (end_step is None or s.step_number < end_step)
            ]
            run.steps = filtered_steps

        formatter = get_formatter(ctx.obj.format)
        formatter.format_run(run, console)

        # Show cost breakdown if requested
        if cost:
            from reagent.analysis.cost import CostAnalyzer
            analyzer = CostAnalyzer()
            report = analyzer.analyze_run(run)

            console.print()
            console.print("[bold]Cost Breakdown:[/bold]")
            console.print(f"  Total: ${report.total_cost_usd:.4f}")
            console.print(f"  LLM: ${report.cost_breakdown.llm_cost_usd:.4f}")
            console.print(f"  Tools: ${report.cost_breakdown.tool_cost_usd:.4f}")

            if report.cost_breakdown.by_model:
                console.print("  By model:")
                for model, cost in report.cost_breakdown.by_model.items():
                    console.print(f"    {model}: ${cost:.4f}")

    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        if ctx.obj.verbose:
            import traceback
            err_console.print(traceback.format_exc())
        raise typer.Exit(1)
