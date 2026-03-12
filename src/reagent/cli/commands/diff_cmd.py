"""Diff command - Compare two runs."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

console = Console()
err_console = Console(stderr=True)


def diff_runs(
    ctx: typer.Context,
    run_id_a: str = typer.Argument(..., help="First run ID"),
    run_id_b: str = typer.Argument(..., help="Second run ID"),
    ignore: Optional[str] = typer.Option(None, "--ignore", help="Comma-separated fields to ignore"),
    step: Optional[int] = typer.Option(None, "--step", "-s", help="Compare specific step number"),
    side_by_side: bool = typer.Option(False, "--side-by-side", help="Side-by-side format"),
) -> None:
    """Compare two runs.

    Examples:
        reagent diff abc123 def456
        reagent diff abc123 def456 --ignore duration_ms,timestamp
        reagent diff abc123 def456 --step 5
    """
    from reagent.cli.formatters import get_formatter
    from reagent.client.reagent import ReAgent
    from reagent.analysis.diff import TraceDiff

    try:
        client = ReAgent(config_path=ctx.obj.config_path)

        # Load both runs
        run_a = client.load_run(run_id_a)
        run_b = client.load_run(run_id_b)

        # Parse ignore fields
        ignore_fields = None
        if ignore:
            ignore_fields = set(f.strip() for f in ignore.split(","))

        # Create differ
        differ = TraceDiff(ignore_fields=ignore_fields)

        if step is not None:
            # Compare specific step
            step_a = run_a.get_step(step)
            step_b = run_b.get_step(step)

            if not step_a:
                err_console.print(f"[red]Step {step} not found in run A[/red]")
                raise typer.Exit(1)
            if not step_b:
                err_console.print(f"[red]Step {step} not found in run B[/red]")
                raise typer.Exit(1)

            diffs = differ.diff_steps_only([step_a], [step_b])
            console.print(f"[bold]Step {step} comparison:[/bold]")
            for d in diffs:
                console.print(f"  Type: {d.step_type}")
                console.print(f"  Change: {d.change_type}")
                console.print(f"  Similarity: {d.similarity:.1%}")
                if d.field_diffs:
                    console.print("  Field differences:")
                    for field, (a, b) in d.field_diffs.items():
                        console.print(f"    {field}:")
                        console.print(f"      A: {a}")
                        console.print(f"      B: {b}")

        else:
            # Compare full runs
            result = differ.diff(run_a, run_b)

            formatter = get_formatter(ctx.obj.format)
            formatter.format_diff(result, console)

            # Show step-by-step if verbose
            if ctx.obj.verbose:
                console.print()
                console.print("[bold]Step-by-step differences:[/bold]")
                for d in result.step_diffs:
                    if d.change_type != "unchanged":
                        if d.change_type == "added":
                            console.print(f"  [green]+{d.step_number_b} ({d.step_type})[/green]")
                        elif d.change_type == "removed":
                            console.print(f"  [red]-{d.step_number_a} ({d.step_type})[/red]")
                        elif d.change_type == "modified":
                            console.print(f"  [yellow]~{d.step_number_a} ({d.step_type}) - {d.similarity:.1%} similar[/yellow]")

    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        if ctx.obj.verbose:
            import traceback
            err_console.print(traceback.format_exc())
        raise typer.Exit(1)
