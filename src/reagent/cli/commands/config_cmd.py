"""Config command - Manage configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.syntax import Syntax

console = Console()
err_console = Console(stderr=True)


def config_cmd(
    ctx: typer.Context,
    show: bool = typer.Option(False, "--show", help="Display current configuration"),
    set_value: Optional[str] = typer.Option(None, "--set", help="Set a configuration value (KEY=VALUE)"),
    init: bool = typer.Option(False, "--init", help="Create default configuration file"),
    path: bool = typer.Option(False, "--path", help="Show configuration file path"),
) -> None:
    """Manage ReAgent configuration.

    Examples:
        reagent config --show
        reagent config --set storage.type=sqlite
        reagent config --init
        reagent config --path
    """
    import json
    from reagent.core.config import Config

    try:
        if init:
            _init_config()
            return

        if path:
            _show_config_path()
            return

        if set_value:
            _set_config_value(set_value)
            return

        if show or not any([init, set_value, path]):
            _show_config(ctx.obj.config_path)

    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def _show_config(config_path: Optional[str]) -> None:
    """Display current configuration."""
    from reagent.core.config import Config
    import json

    config = Config.load(config_path=config_path)
    config_dict = config.to_dict()

    console.print("[bold]Current Configuration:[/bold]")
    console.print()
    console.print(Syntax(json.dumps(config_dict, indent=2), "json"))


def _show_config_path() -> None:
    """Show configuration file paths."""
    home = Path.home()

    console.print("[bold]Configuration file locations (in order of precedence):[/bold]")
    console.print()
    console.print("1. CLI flags (--config)")
    console.print("2. Environment variables (REAGENT_*)")
    console.print()

    # Project config
    cwd = Path.cwd()
    console.print("3. Project configuration:")
    for name in [".reagent.yml", ".reagent.yaml", ".reagent.json", "reagent.yml"]:
        path = cwd / name
        status = "[green]found[/green]" if path.exists() else "[dim]not found[/dim]"
        console.print(f"   {path} - {status}")

    console.print()

    # User config
    console.print("4. User configuration:")
    user_dir = home / ".reagent"
    for name in ["config.yml", "config.yaml", "config.json"]:
        path = user_dir / name
        status = "[green]found[/green]" if path.exists() else "[dim]not found[/dim]"
        console.print(f"   {path} - {status}")

    console.print()
    console.print("5. SDK defaults (built-in)")


def _init_config() -> None:
    """Create a default configuration file."""
    import yaml

    # Default configuration
    default_config = {
        "project": None,
        "transport_mode": "buffered",
        "storage": {
            "type": "jsonl",
            "path": ".reagent/traces",
        },
        "buffer": {
            "size": 10000,
            "flush_interval_ms": 100,
        },
        "redaction": {
            "enabled": True,
            "mode": "remove",
        },
        "replay": {
            "default_mode": "strict",
        },
    }

    # Check for existing config
    config_path = Path.cwd() / ".reagent.yml"
    if config_path.exists():
        overwrite = typer.confirm(f"{config_path} already exists. Overwrite?")
        if not overwrite:
            raise typer.Exit()

    # Write config
    try:
        import yaml
        config_path.write_text(yaml.dump(default_config, default_flow_style=False))
        console.print(f"[green]Created {config_path}[/green]")
    except ImportError:
        # Fallback to JSON if yaml not available
        import json
        config_path = Path.cwd() / ".reagent.json"
        config_path.write_text(json.dumps(default_config, indent=2))
        console.print(f"[green]Created {config_path}[/green]")


def _set_config_value(key_value: str) -> None:
    """Set a configuration value."""
    import json

    if "=" not in key_value:
        err_console.print("[red]Invalid format. Use KEY=VALUE[/red]")
        raise typer.Exit(1)

    key, value = key_value.split("=", 1)

    # Try to parse value as JSON
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value

    # Find config file
    config_path = None
    for name in [".reagent.yml", ".reagent.yaml", ".reagent.json"]:
        path = Path.cwd() / name
        if path.exists():
            config_path = path
            break

    if not config_path:
        err_console.print("[yellow]No configuration file found. Run 'reagent config --init' first.[/yellow]")
        raise typer.Exit(1)

    # Load and update config
    if config_path.suffix in [".yml", ".yaml"]:
        import yaml
        config = yaml.safe_load(config_path.read_text()) or {}

        # Set nested value
        keys = key.split(".")
        current = config
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = parsed_value

        config_path.write_text(yaml.dump(config, default_flow_style=False))
    else:
        config = json.loads(config_path.read_text())

        # Set nested value
        keys = key.split(".")
        current = config
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = parsed_value

        config_path.write_text(json.dumps(config, indent=2))

    console.print(f"[green]Set {key}={value}[/green]")
