"""Failure analysis endpoints."""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, Query

from reagent.server.auth import verify_api_key
from reagent.server.deps import get_storage
from reagent.storage.base import RunFilter, Pagination
from reagent.storage.sqlite import SQLiteStorage

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/api/v1/failures")
async def list_failures(
    project: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    storage: SQLiteStorage = Depends(get_storage),
) -> list[dict[str, Any]]:
    filters = RunFilter(project=project, has_error=True)
    pagination = Pagination(limit=limit, offset=offset)
    runs = storage.list_runs(filters=filters, pagination=pagination)
    return [r.model_dump(mode="json") for r in runs]


@router.get("/api/v1/failures/stats")
async def failure_stats(
    project: str | None = None,
    storage: SQLiteStorage = Depends(get_storage),
) -> dict[str, Any]:
    filters = RunFilter(project=project, has_error=True)
    pagination = Pagination(limit=1000)
    runs = storage.list_runs(filters=filters, pagination=pagination)

    categories: Counter[str] = Counter()
    for run in runs:
        cat = run.failure_category or "unknown"
        categories[cat] += 1

    return {
        "total_failures": len(runs),
        "by_category": dict(categories.most_common()),
    }
