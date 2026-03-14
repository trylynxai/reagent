"""Run query endpoints."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from reagent.core.constants import Status
from reagent.core.exceptions import TraceNotFoundError
from reagent.server.auth import verify_api_key
from reagent.server.deps import get_storage
from reagent.storage.base import RunFilter, Pagination
from reagent.storage.sqlite import SQLiteStorage

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/api/v1/runs")
async def list_runs(
    project: str | None = None,
    status: str | None = None,
    model: str | None = None,
    has_error: str | None = None,
    failure_category: str | None = None,
    name: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = "start_time",
    sort_order: str = "desc",
    storage: SQLiteStorage = Depends(get_storage),
) -> list[dict[str, Any]]:
    status_filter = None
    if status:
        parts = status.split(",")
        if len(parts) == 1:
            status_filter = Status(parts[0])
        else:
            status_filter = [Status(s) for s in parts]

    has_error_val = None
    if has_error is not None:
        has_error_val = has_error.lower() == "true"

    filters = RunFilter(
        project=project,
        status=status_filter,
        model=model,
        has_error=has_error_val,
        failure_category=failure_category,
        name=name,
    )
    pagination = Pagination(limit=limit, offset=offset, sort_by=sort_by, sort_order=sort_order)

    runs = storage.list_runs(filters=filters, pagination=pagination)
    return [r.model_dump(mode="json") for r in runs]


@router.get("/api/v1/runs/count")
async def count_runs(
    project: str | None = None,
    status: str | None = None,
    storage: SQLiteStorage = Depends(get_storage),
) -> dict[str, int]:
    status_filter = None
    if status:
        parts = status.split(",")
        if len(parts) == 1:
            status_filter = Status(parts[0])
        else:
            status_filter = [Status(s) for s in parts]

    filters = RunFilter(project=project, status=status_filter) if project or status else None
    return {"count": storage.count_runs(filters)}


@router.get("/api/v1/runs/{run_id}")
async def get_run(
    run_id: str,
    storage: SQLiteStorage = Depends(get_storage),
) -> dict[str, Any]:
    try:
        run = storage.load_run(UUID(run_id))
        return run.model_dump(mode="json")
    except TraceNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")


@router.get("/api/v1/runs/{run_id}/metadata")
async def get_run_metadata(
    run_id: str,
    storage: SQLiteStorage = Depends(get_storage),
) -> dict[str, Any]:
    try:
        metadata = storage.load_metadata(UUID(run_id))
        return metadata.model_dump(mode="json")
    except TraceNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")


@router.get("/api/v1/runs/{run_id}/steps")
async def get_run_steps(
    run_id: str,
    step_type: str | None = None,
    start: int | None = None,
    end: int | None = None,
    storage: SQLiteStorage = Depends(get_storage),
) -> list[dict[str, Any]]:
    try:
        steps = list(storage.load_steps(UUID(run_id), start=start, end=end, step_type=step_type))
        return [s.model_dump(mode="json") for s in steps]
    except TraceNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")


@router.delete("/api/v1/runs/{run_id}")
async def delete_run(
    run_id: str,
    storage: SQLiteStorage = Depends(get_storage),
) -> dict[str, bool]:
    deleted = storage.delete_run(UUID(run_id))
    return {"deleted": deleted}
