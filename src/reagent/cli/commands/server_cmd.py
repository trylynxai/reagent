"""CLI command for starting the ReAgent server."""

from __future__ import annotations

import os

import typer

app = typer.Typer(
    name="server",
    help="Manage the ReAgent server",
    no_args_is_help=True,
)


@app.command("start")
def start(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind address"),
    port: int = typer.Option(8080, "--port", "-p", help="Bind port"),
    db: str = typer.Option("reagent_server.db", "--db", help="SQLite database path"),
) -> None:
    """Start the ReAgent server."""
    try:
        import uvicorn
    except ImportError:
        typer.echo(
            "Server dependencies not installed. "
            "Install them with: pip install reagent[server]",
            err=True,
        )
        raise typer.Exit(1)

    os.environ.setdefault("REAGENT_SERVER_HOST", host)
    os.environ.setdefault("REAGENT_SERVER_PORT", str(port))
    os.environ.setdefault("REAGENT_SERVER_DB", db)

    typer.echo(f"Starting ReAgent server on {host}:{port} (db: {db})")
    uvicorn.run("reagent.server.app:app", host=host, port=port)
