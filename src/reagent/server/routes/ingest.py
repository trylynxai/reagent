"""Batch ingest endpoint for receiving events from the SDK."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from reagent.schema.run import RunMetadata
from reagent.schema.steps import CustomStep
from reagent.server.auth import verify_api_key
from reagent.server.deps import get_storage
from reagent.storage.sqlite import STEP_TYPE_MAP, SQLiteStorage

router = APIRouter()


class IngestEvent(BaseModel):
    type: str  # "metadata" or "step"
    run_id: str
    step_type: str | None = None
    data: dict[str, Any]


class IngestBatch(BaseModel):
    events: list[IngestEvent]


@router.post("/api/v1/ingest", dependencies=[Depends(verify_api_key)])
async def ingest(
    batch: IngestBatch,
    storage: SQLiteStorage = Depends(get_storage),
) -> dict[str, Any]:
    for event in batch.events:
        run_id = UUID(event.run_id)
        if event.type == "metadata":
            metadata = RunMetadata.model_validate(event.data)
            storage.save_run(run_id, metadata)
        elif event.type == "step":
            step_cls = STEP_TYPE_MAP.get(event.step_type or "custom", CustomStep)
            step = step_cls.model_validate(event.data)
            storage.save_step(run_id, step)

    return {"status": "ok", "events_received": len(batch.events)}
