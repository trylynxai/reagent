"""CSV export for run data.

Exports run summaries and step details as flat CSV rows suitable
for analysis in spreadsheets, pandas, or BI tools.

Two export modes:
- Run summary: one row per run with aggregated stats
- Step details: one row per step with run metadata columns

Uses only the stdlib csv module — no external dependencies.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from reagent.schema.run import Run
from reagent.schema.steps import (
    AgentStep,
    CheckpointStep,
    ChainStep,
    ErrorStep,
    LLMCallStep,
    RetrievalStep,
    ToolCallStep,
)

# ============================================================
# Column definitions
# ============================================================

RUN_COLUMNS = [
    "run_id",
    "name",
    "project",
    "status",
    "model",
    "framework",
    "start_time",
    "end_time",
    "duration_ms",
    "total_steps",
    "llm_calls",
    "tool_calls",
    "errors",
    "total_tokens",
    "prompt_tokens",
    "completion_tokens",
    "total_cost_usd",
    "llm_cost_usd",
    "tool_cost_usd",
    "error",
    "error_type",
    "failure_category",
    "tags",
]

STEP_COLUMNS = [
    "run_id",
    "run_name",
    "step_number",
    "step_type",
    "timestamp_start",
    "timestamp_end",
    "duration_ms",
    # LLM fields
    "model",
    "provider",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost_usd",
    "finish_reason",
    # Tool fields
    "tool_name",
    "tool_success",
    # Agent fields
    "agent_name",
    "action",
    # Chain fields
    "chain_name",
    # Retrieval fields
    "query",
    "result_count",
    # Error fields
    "error",
    "error_type",
]


# ============================================================
# Row builders
# ============================================================


def _run_to_row(run: Run) -> dict[str, Any]:
    """Convert a Run to a flat dict for the run summary CSV."""
    meta = run.metadata
    return {
        "run_id": str(meta.run_id),
        "name": meta.name or "",
        "project": meta.project or "",
        "status": meta.status.value,
        "model": meta.model or "",
        "framework": meta.framework or "",
        "start_time": meta.start_time.isoformat() if meta.start_time else "",
        "end_time": meta.end_time.isoformat() if meta.end_time else "",
        "duration_ms": meta.duration_ms or "",
        "total_steps": meta.steps.total,
        "llm_calls": meta.steps.llm_calls,
        "tool_calls": meta.steps.tool_calls,
        "errors": meta.steps.errors,
        "total_tokens": meta.tokens.total_tokens,
        "prompt_tokens": meta.tokens.prompt_tokens,
        "completion_tokens": meta.tokens.completion_tokens,
        "total_cost_usd": meta.cost.total_usd,
        "llm_cost_usd": meta.cost.llm_cost_usd,
        "tool_cost_usd": meta.cost.tool_cost_usd,
        "error": meta.error or "",
        "error_type": meta.error_type or "",
        "failure_category": meta.failure_category or "",
        "tags": "|".join(meta.tags) if meta.tags else "",
    }


def _step_to_row(step: Any, run: Run) -> dict[str, Any]:
    """Convert a step to a flat dict for the step details CSV."""
    row: dict[str, Any] = {
        "run_id": str(run.metadata.run_id),
        "run_name": run.metadata.name or "",
        "step_number": step.step_number,
        "step_type": step.step_type,
        "timestamp_start": step.timestamp_start.isoformat() if step.timestamp_start else "",
        "timestamp_end": step.timestamp_end.isoformat() if step.timestamp_end else "",
        "duration_ms": step.duration_ms or "",
        # Defaults
        "model": "",
        "provider": "",
        "prompt_tokens": "",
        "completion_tokens": "",
        "total_tokens": "",
        "cost_usd": "",
        "finish_reason": "",
        "tool_name": "",
        "tool_success": "",
        "agent_name": "",
        "action": "",
        "chain_name": "",
        "query": "",
        "result_count": "",
        "error": "",
        "error_type": "",
    }

    if isinstance(step, LLMCallStep):
        row["model"] = step.model
        row["provider"] = step.provider or ""
        row["cost_usd"] = step.cost_usd or ""
        row["finish_reason"] = step.finish_reason or ""
        row["error"] = step.error or ""
        if step.token_usage:
            row["prompt_tokens"] = step.token_usage.prompt_tokens
            row["completion_tokens"] = step.token_usage.completion_tokens
            row["total_tokens"] = step.token_usage.total_tokens

    elif isinstance(step, ToolCallStep):
        row["tool_name"] = step.tool_name
        row["tool_success"] = step.success
        row["cost_usd"] = step.cost_usd or ""
        if step.output:
            row["error"] = step.output.error or ""
            row["error_type"] = step.output.error_type or ""

    elif isinstance(step, AgentStep):
        row["agent_name"] = step.agent_name or ""
        row["action"] = step.action or ""
        row["error"] = step.error or ""

    elif isinstance(step, ChainStep):
        row["chain_name"] = step.chain_name
        row["error"] = step.error or ""

    elif isinstance(step, RetrievalStep):
        row["query"] = step.query
        if step.results:
            row["result_count"] = len(step.results.documents)
        row["error"] = step.error or ""

    elif isinstance(step, ErrorStep):
        row["error"] = step.error_message
        row["error_type"] = step.error_type

    return row


# ============================================================
# Public API
# ============================================================


def runs_to_csv(
    runs: list[Run],
    columns: list[str] | None = None,
) -> str:
    """Export multiple runs as a CSV string (one row per run).

    Args:
        runs: List of Run objects.
        columns: Column names to include (default: all RUN_COLUMNS).

    Returns:
        CSV formatted string.
    """
    cols = columns or RUN_COLUMNS
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for run in runs:
        writer.writerow(_run_to_row(run))
    return output.getvalue()


def steps_to_csv(
    runs: list[Run],
    columns: list[str] | None = None,
) -> str:
    """Export steps from runs as a CSV string (one row per step).

    Args:
        runs: List of Run objects.
        columns: Column names to include (default: all STEP_COLUMNS).

    Returns:
        CSV formatted string.
    """
    cols = columns or STEP_COLUMNS
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for run in runs:
        for step in run.steps:
            writer.writerow(_step_to_row(step, run))
    return output.getvalue()


def export_csv(
    runs: list[Run],
    output_path: str | Path,
    mode: str = "runs",
    columns: list[str] | None = None,
) -> Path:
    """Export runs to a CSV file.

    Args:
        runs: List of Run objects.
        output_path: File path to write to.
        mode: "runs" for summary rows, "steps" for step detail rows.
        columns: Column names to include (default: all for the mode).

    Returns:
        Path to the written file.
    """
    path = Path(output_path)
    if mode == "steps":
        content = steps_to_csv(runs, columns=columns)
    else:
        content = runs_to_csv(runs, columns=columns)
    path.write_text(content)
    return path


def run_to_csv(run: Run, mode: str = "steps") -> str:
    """Export a single run as CSV string.

    Args:
        run: Run to export.
        mode: "runs" for summary row, "steps" for step detail rows.

    Returns:
        CSV formatted string.
    """
    if mode == "runs":
        return runs_to_csv([run])
    return steps_to_csv([run])
