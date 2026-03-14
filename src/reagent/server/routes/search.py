"""Search endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from reagent.server.auth import verify_api_key
from reagent.server.deps import get_storage
from reagent.storage.base import RunFilter, Pagination
from reagent.storage.sqlite import SQLiteStorage

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/api/v1/search")
async def search_runs(
    q: str = Query(..., description="Search query"),
    project: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    storage: SQLiteStorage = Depends(get_storage),
) -> list[dict[str, Any]]:
    filters = RunFilter(project=project) if project else None
    pagination = Pagination(limit=limit, offset=offset)

    results = storage.search(q, filters=filters, pagination=pagination)
    return [r.model_dump(mode="json") for r in results]
