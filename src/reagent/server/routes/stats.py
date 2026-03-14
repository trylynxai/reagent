"""Aggregate stats endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from reagent.server.auth import verify_api_key
from reagent.server.deps import get_storage
from reagent.storage.base import RunFilter, Pagination
from reagent.storage.sqlite import SQLiteStorage

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/api/v1/stats")
async def stats(
    project: str | None = None,
    storage: SQLiteStorage = Depends(get_storage),
) -> dict[str, Any]:
    filters = RunFilter(project=project) if project else None
    total = storage.count_runs(filters)

    pagination = Pagination(limit=1000)
    runs = storage.list_runs(filters=filters, pagination=pagination)

    total_cost = sum(r.total_cost_usd for r in runs)
    total_tokens = sum(r.total_tokens for r in runs)
    completed = sum(1 for r in runs if r.status.value == "completed")
    failed = sum(1 for r in runs if r.status.value == "failed")

    return {
        "total_runs": total,
        "completed": completed,
        "failed": failed,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "success_rate": completed / total if total > 0 else 0.0,
    }
