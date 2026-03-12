"""ExecutionEvent - The canonical event model for ReAgent.

All events captured during agent execution are normalized to this schema.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_serializer

from reagent.core.constants import EventType


class ExecutionEvent(BaseModel):
    """Base event model for all execution events.

    This is the canonical schema that all framework-specific events
    are normalized to before storage and analysis.
    """

    # Unique identifier for this event
    event_id: UUID = Field(default_factory=uuid4)

    # Run this event belongs to
    run_id: UUID

    # Parent step for hierarchical relationships (e.g., tool call within chain)
    parent_step_id: UUID | None = None

    # Type of event
    event_type: EventType

    # When the event occurred
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Sequential number within the run (for ordering)
    sequence_number: int = Field(ge=0)

    # Event-specific payload data
    payload: dict[str, Any] = Field(default_factory=dict)

    # Additional metadata (tags, labels, framework info)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Duration in milliseconds (for end events)
    duration_ms: int | None = None

    # Associated cost (if applicable)
    cost_usd: float | None = None

    # Error information (for error events)
    error: str | None = None
    error_type: str | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "event_id": "550e8400-e29b-41d4-a716-446655440000",
                    "run_id": "550e8400-e29b-41d4-a716-446655440001",
                    "event_type": "llm_call_end",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "sequence_number": 5,
                    "payload": {
                        "model": "gpt-4",
                        "prompt": "What is 2+2?",
                        "response": "4",
                        "prompt_tokens": 10,
                        "completion_tokens": 1,
                    },
                    "duration_ms": 1500,
                    "cost_usd": 0.0015,
                }
            ]
        }
    }

    @field_serializer("event_id", "run_id", "parent_step_id")
    def serialize_uuid(self, v: UUID | None) -> str | None:
        """Serialize UUIDs to strings for JSON compatibility."""
        return str(v) if v else None

    @field_serializer("timestamp")
    def serialize_timestamp(self, v: datetime) -> str:
        """Serialize timestamp to ISO format."""
        return v.isoformat()

    @classmethod
    def create_run_start(
        cls,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionEvent:
        """Create a RUN_START event."""
        return cls(
            run_id=run_id,
            event_type=EventType.RUN_START,
            sequence_number=0,
            metadata=metadata or {},
        )

    @classmethod
    def create_run_end(
        cls,
        run_id: UUID,
        sequence_number: int,
        duration_ms: int,
        total_cost_usd: float | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionEvent:
        """Create a RUN_END event."""
        return cls(
            run_id=run_id,
            event_type=EventType.RUN_END,
            sequence_number=sequence_number,
            duration_ms=duration_ms,
            cost_usd=total_cost_usd,
            error=error,
            metadata=metadata or {},
        )

    def is_start_event(self) -> bool:
        """Check if this is a start event."""
        return self.event_type.value.endswith("_start") or self.event_type == EventType.RUN_START

    def is_end_event(self) -> bool:
        """Check if this is an end event."""
        return self.event_type.value.endswith("_end") or self.event_type == EventType.RUN_END

    def is_error_event(self) -> bool:
        """Check if this is an error event."""
        return self.event_type == EventType.ERROR or self.error is not None

    def get_step_type(self) -> str:
        """Get the base step type (without _start/_end suffix)."""
        type_str = self.event_type.value
        for suffix in ("_start", "_end"):
            if type_str.endswith(suffix):
                return type_str[: -len(suffix)]
        return type_str
