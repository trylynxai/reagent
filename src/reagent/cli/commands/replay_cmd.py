"""Replay command - Replay recorded runs."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Prompt

console = Console()
err_console = Console(stderr=True)


def replay_run(
    ctx: typer.Context,
    run_id: str = typer.Argument(..., help="Run ID to replay"),
    mode: str = typer.Option(
        "strict",
        "--mode",
        "-m",
        help="Replay mode: strict, partial, mock, hybrid",
    ),
    from_step: Optional[int] = typer.Option(None, "--from", help="Start from step"),
    to_step: Optional[int] = typer.Option(None, "--to", help="Stop at step"),
    headless: bool = typer.Option(False, "--headless", help="Non-interactive mode"),
) -> None:
    """Replay a recorded run.

    Modes:
    - strict: Return exact recorded outputs, no external calls
    - partial: Re-execute selected steps, replay others
    - mock: Intercept external calls, return recorded responses
    - hybrid: Configurable per step type

    Examples:
        reagent replay abc123
        reagent replay abc123 --mode partial
        reagent replay abc123 --from 5 --to 10
        reagent replay abc123 --headless
    """
    from reagent.client.reagent import ReAgent
    from reagent.replay.engine import ReplayEngine
    from reagent.core.constants import ReplayMode

    try:
        client = ReAgent(config_path=ctx.obj.config_path)

        # Parse mode
        replay_mode = ReplayMode(mode)

        # Create replay engine
        engine = ReplayEngine(
            storage=client.storage,
            mode=replay_mode,
        )

        if headless:
            # Non-interactive replay
            session = engine.replay(
                run_id=run_id,
                from_step=from_step,
                to_step=to_step,
            )

            console.print(f"[green]Replay completed[/green]")
            console.print(f"  Steps: {session.current_step}/{session.total_steps}")
            console.print(f"  Status: {session.status.value}")
            console.print(f"  Divergences: {len([r for r in session.results if r.diverged])}")

        else:
            # Interactive replay
            _interactive_replay(engine, run_id, from_step, to_step)

    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        if ctx.obj.verbose:
            import traceback
            err_console.print(traceback.format_exc())
        raise typer.Exit(1)


def _interactive_replay(
    engine: "ReplayEngine",
    run_id: str,
    from_step: Optional[int],
    to_step: Optional[int],
) -> None:
    """Run interactive replay debugger."""
    from reagent.cli.debugger import ReplayDebugger

    debugger = ReplayDebugger(engine, run_id)

    console.print("[bold]ReAgent Interactive Replay Debugger[/bold]")
    console.print("Type 'help' for available commands.")
    console.print()

    # Start replay
    debugger.start(from_step=from_step, to_step=to_step)

    # Enter REPL
    while not debugger.is_finished:
        try:
            prompt = debugger.get_prompt()
            cmd = Prompt.ask(prompt)

            if not cmd:
                continue

            result = debugger.execute_command(cmd)
            if result:
                console.print(result)

        except KeyboardInterrupt:
            console.print("\n[yellow]Use 'exit' to quit[/yellow]")
        except EOFError:
            break

    console.print("[green]Replay session ended[/green]")
