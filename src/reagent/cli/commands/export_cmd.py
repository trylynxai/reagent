"""Export command - Export runs to various formats."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

console = Console()
err_console = Console(stderr=True)


def export_run(
    ctx: typer.Context,
    run_id: str = typer.Argument(..., help="Run ID to export"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Export format: json, markdown, html, otlp, langfuse, csv",
    ),
    csv_mode: str = typer.Option(
        "steps",
        "--csv-mode",
        help="CSV export mode: runs (summary) or steps (detail)",
    ),
    include_raw: bool = typer.Option(False, "--raw", help="Include raw request/response data"),
    endpoint: Optional[str] = typer.Option(
        None, "--endpoint", help="OTLP collector endpoint for live export"
    ),
    langfuse_public_key: Optional[str] = typer.Option(
        None, "--langfuse-public-key", help="Langfuse public key for live export"
    ),
    langfuse_secret_key: Optional[str] = typer.Option(
        None, "--langfuse-secret-key", help="Langfuse secret key for live export"
    ),
    langfuse_host: Optional[str] = typer.Option(
        None, "--langfuse-host", help="Langfuse host URL (default: https://cloud.langfuse.com)"
    ),
) -> None:
    """Export a run to a file.

    Formats:
    - json: Full JSON export
    - markdown: Markdown documentation
    - html: Self-contained HTML report
    - otlp: OpenTelemetry protobuf JSON (file or live export)
    - langfuse: Langfuse trace JSON (file or live export)
    - csv: Tabular CSV export (use --csv-mode for runs/steps)

    Examples:
        reagent export abc123 -o trace.json
        reagent export abc123 -f markdown -o trace.md
        reagent export abc123 -f html -o report.html
        reagent export abc123 -f otlp -o trace.otlp.json
        reagent export abc123 -f otlp --endpoint http://localhost:4318/v1/traces
        reagent export abc123 -f langfuse -o trace.langfuse.json
        reagent export abc123 -f langfuse --langfuse-public-key pk-... --langfuse-secret-key sk-...
        reagent export abc123 -f csv -o steps.csv
        reagent export abc123 -f csv --csv-mode runs -o summary.csv
    """
    import json
    from reagent.client.reagent import ReAgent

    try:
        client = ReAgent(config_path=ctx.obj.config_path)
        run = client.load_run(run_id)

        # Generate output
        if format == "json":
            content = _export_json(run, include_raw)
        elif format == "markdown":
            content = _export_markdown(run)
        elif format == "html":
            content = _export_html(run)
        elif format == "otlp":
            if endpoint:
                from reagent.export.otlp import export_otlp_live

                export_otlp_live(run, endpoint)
                console.print(f"[green]Exported to OTLP endpoint: {endpoint}[/green]")
                return
            content = _export_otlp(run)
        elif format == "langfuse":
            if langfuse_public_key and langfuse_secret_key:
                from reagent.export.langfuse import export_langfuse_live

                export_langfuse_live(
                    run,
                    public_key=langfuse_public_key,
                    secret_key=langfuse_secret_key,
                    host=langfuse_host or "https://cloud.langfuse.com",
                )
                console.print(f"[green]Exported to Langfuse: {langfuse_host or 'https://cloud.langfuse.com'}[/green]")
                return
            content = _export_langfuse(run)
        elif format == "csv":
            content = _export_csv(run, csv_mode)
        else:
            err_console.print(f"[red]Unknown format: {format}[/red]")
            raise typer.Exit(1)

        # Write output
        if output:
            output_path = Path(output)
            output_path.write_text(content)
            console.print(f"[green]Exported to {output_path}[/green]")
        else:
            console.print(content)

    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        if ctx.obj.verbose:
            import traceback
            err_console.print(traceback.format_exc())
        raise typer.Exit(1)


def _export_json(run: "Run", include_raw: bool) -> str:
    """Export run as JSON."""
    import json

    data = {
        "metadata": run.metadata.model_dump(mode="json"),
        "steps": [step.model_dump(mode="json") for step in run.steps],
    }

    if not include_raw:
        # Remove raw request/response data to reduce size
        for step in data["steps"]:
            step.pop("raw_request", None)
            step.pop("raw_response", None)

    return json.dumps(data, indent=2, default=str)


def _export_markdown(run: "Run") -> str:
    """Export run as Markdown."""
    meta = run.metadata
    lines = [
        f"# Run Report: {meta.name or meta.run_id}",
        "",
        "## Overview",
        "",
        f"- **Run ID:** `{meta.run_id}`",
        f"- **Project:** {meta.project or '-'}",
        f"- **Status:** {meta.status.value}",
        f"- **Model:** {meta.model or '-'}",
        f"- **Started:** {meta.start_time.isoformat()}",
        f"- **Duration:** {meta.duration_ms}ms" if meta.duration_ms else "",
        "",
        "## Statistics",
        "",
        f"- **Total Steps:** {meta.steps.total}",
        f"- **LLM Calls:** {meta.steps.llm_calls}",
        f"- **Tool Calls:** {meta.steps.tool_calls}",
        f"- **Total Tokens:** {meta.tokens.total_tokens:,}",
        f"- **Total Cost:** ${meta.cost.total_usd:.4f}",
        "",
    ]

    if meta.error:
        lines.extend([
            "## Error",
            "",
            f"```\n{meta.error}\n```",
            "",
        ])

    lines.extend([
        "## Execution Steps",
        "",
    ])

    for step in run.steps:
        lines.append(f"### Step {step.step_number}: {step.step_type}")
        lines.append("")

        if hasattr(step, "model"):
            lines.append(f"**Model:** {step.model}")
        if hasattr(step, "tool_name"):
            lines.append(f"**Tool:** {step.tool_name}")
        if step.duration_ms:
            lines.append(f"**Duration:** {step.duration_ms}ms")

        if hasattr(step, "prompt") and step.prompt:
            lines.extend([
                "",
                "**Prompt:**",
                "```",
                step.prompt[:500] + ("..." if len(step.prompt) > 500 else ""),
                "```",
            ])

        if hasattr(step, "response") and step.response:
            lines.extend([
                "",
                "**Response:**",
                "```",
                step.response[:500] + ("..." if len(step.response) > 500 else ""),
                "```",
            ])

        lines.append("")

    return "\n".join(lines)


def _export_html(run: "Run") -> str:
    """Export run as interactive HTML viewer."""
    import json
    from pathlib import Path

    meta = run.metadata

    # Prepare run data as JSON
    run_data = {
        "metadata": meta.model_dump(mode="json"),
        "steps": [step.model_dump(mode="json") for step in run.steps],
    }
    run_data_json = json.dumps(run_data, indent=2, default=str)

    # Try to load the interactive template
    template_path = Path(__file__).parent.parent / "templates" / "viewer.html"

    if template_path.exists():
        template = template_path.read_text()
        # Inject run data and name into template
        html = template.replace("{{ RUN_DATA_JSON }}", run_data_json)
        html = html.replace("{{ RUN_NAME }}", meta.name or str(meta.run_id)[:8])
        return html

    # Fallback to simple HTML if template not found
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Run Report: {meta.name or meta.run_id}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #333; }}
        .status-completed {{ color: green; }}
        .status-failed {{ color: red; }}
        .step {{ border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin: 16px 0; }}
        .step-header {{ font-weight: bold; margin-bottom: 8px; }}
        .step-type {{ background: #f0f0f0; padding: 2px 8px; border-radius: 4px; font-size: 12px; }}
        pre {{ background: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; }}
        .stat {{ background: #f9f9f9; padding: 12px; border-radius: 8px; }}
        .stat-value {{ font-size: 24px; font-weight: bold; }}
        .stat-label {{ color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <h1>Run Report</h1>

    <h2>Overview</h2>
    <ul>
        <li><strong>Run ID:</strong> <code>{meta.run_id}</code></li>
        <li><strong>Name:</strong> {meta.name or '-'}</li>
        <li><strong>Project:</strong> {meta.project or '-'}</li>
        <li><strong>Status:</strong> <span class="status-{meta.status.value}">{meta.status.value}</span></li>
        <li><strong>Model:</strong> {meta.model or '-'}</li>
        <li><strong>Started:</strong> {meta.start_time.isoformat()}</li>
    </ul>

    <h2>Statistics</h2>
    <div class="stats">
        <div class="stat">
            <div class="stat-value">{meta.steps.total}</div>
            <div class="stat-label">Total Steps</div>
        </div>
        <div class="stat">
            <div class="stat-value">{meta.tokens.total_tokens:,}</div>
            <div class="stat-label">Total Tokens</div>
        </div>
        <div class="stat">
            <div class="stat-value">${meta.cost.total_usd:.4f}</div>
            <div class="stat-label">Total Cost</div>
        </div>
        <div class="stat">
            <div class="stat-value">{meta.duration_ms or 0}ms</div>
            <div class="stat-label">Duration</div>
        </div>
    </div>

    <h2>Execution Steps</h2>
"""

    for step in run.steps:
        step_data = step.model_dump(mode="json")
        html += f"""
    <div class="step">
        <div class="step-header">
            Step {step.step_number} <span class="step-type">{step.step_type}</span>
        </div>
        <pre>{json.dumps(step_data, indent=2, default=str)[:2000]}</pre>
    </div>
"""

    html += """
</body>
</html>
"""
    return html


def _export_otlp(run: "Run") -> str:
    """Export run as OTLP protobuf JSON."""
    import json

    from reagent.export.otlp import run_to_otlp_json

    data = run_to_otlp_json(run)
    return json.dumps(data, indent=2)


def _export_langfuse(run: "Run") -> str:
    """Export run as Langfuse trace JSON."""
    import json

    from reagent.export.langfuse import run_to_langfuse_json

    data = run_to_langfuse_json(run)
    return json.dumps(data, indent=2, default=str)


def _export_csv(run: "Run", mode: str = "steps") -> str:
    """Export run as CSV."""
    from reagent.export.csv import run_to_csv

    return run_to_csv(run, mode=mode)
