"""Storage backend abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Iterator
from uuid import UUID

from pydantic import BaseModel, Field

from reagent.core.constants import Status
from reagent.schema.run import Run, RunMetadata, RunSummary
from reagent.schema.steps import AnyStep


class RunFilter(BaseModel):
    """Filter criteria for listing runs."""

    project: str | None = None
    name: str | None = None
    status: Status | list[Status] | None = None
    model: str | None = None
    tags: list[str] | None = None
    since: datetime | None = None
    until: datetime | None = None
    min_cost_usd: float | None = None
    max_cost_usd: float | None = None
    min_duration_ms: int | None = None
    max_duration_ms: int | None = None
    min_tokens: int | None = None
    max_tokens: int | None = None
    min_steps: int | None = None
    max_steps: int | None = None
    has_error: bool | None = None
    failure_category: str | None = None
    framework: str | None = None
    tool_name: str | None = None
    search_query: str | None = None


class Pagination(BaseModel):
    """Pagination settings for list operations."""

    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = "start_time"
    sort_order: str = "desc"  # "asc" or "desc"


class StorageBackend(ABC):
    """Abstract base class for storage backends.

    All storage implementations must implement these methods
    to provide a consistent interface for trace persistence.
    """

    @abstractmethod
    def save_run(self, run_id: UUID, metadata: RunMetadata) -> None:
        """Save or update run metadata.

        Args:
            run_id: Unique identifier for the run
            metadata: Run metadata to save
        """
        pass

    @abstractmethod
    def save_step(self, run_id: UUID, step: AnyStep) -> None:
        """Save a step to the run.

        Args:
            run_id: Run this step belongs to
            step: Step data to save
        """
        pass

    @abstractmethod
    def load_run(self, run_id: UUID) -> Run:
        """Load a complete run with all steps.

        Args:
            run_id: Run to load

        Returns:
            Complete run with metadata and steps

        Raises:
            TraceNotFoundError: If run doesn't exist
        """
        pass

    @abstractmethod
    def load_metadata(self, run_id: UUID) -> RunMetadata:
        """Load only run metadata (without steps).

        Args:
            run_id: Run to load metadata for

        Returns:
            Run metadata

        Raises:
            TraceNotFoundError: If run doesn't exist
        """
        pass

    @abstractmethod
    def load_steps(
        self,
        run_id: UUID,
        start: int | None = None,
        end: int | None = None,
        step_type: str | None = None,
    ) -> Iterator[AnyStep]:
        """Load steps from a run with optional filtering.

        Args:
            run_id: Run to load steps from
            start: Starting step number (inclusive)
            end: Ending step number (exclusive)
            step_type: Filter by step type

        Yields:
            Steps matching the criteria

        Raises:
            TraceNotFoundError: If run doesn't exist
        """
        pass

    @abstractmethod
    def list_runs(
        self,
        filters: RunFilter | None = None,
        pagination: Pagination | None = None,
    ) -> list[RunSummary]:
        """List runs matching the given criteria.

        Args:
            filters: Filter criteria
            pagination: Pagination settings

        Returns:
            List of run summaries
        """
        pass

    @abstractmethod
    def search(
        self,
        query: str,
        filters: RunFilter | None = None,
        pagination: Pagination | None = None,
    ) -> list[RunSummary]:
        """Search runs by text query.

        Args:
            query: Search query string
            filters: Additional filter criteria
            pagination: Pagination settings

        Returns:
            List of matching run summaries
        """
        pass

    @abstractmethod
    def delete_run(self, run_id: UUID) -> bool:
        """Delete a run and all its steps.

        Args:
            run_id: Run to delete

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    def exists(self, run_id: UUID) -> bool:
        """Check if a run exists.

        Args:
            run_id: Run to check

        Returns:
            True if exists, False otherwise
        """
        pass

    @abstractmethod
    def count_runs(self, filters: RunFilter | None = None) -> int:
        """Count runs matching the given criteria.

        Args:
            filters: Filter criteria

        Returns:
            Number of matching runs
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the storage backend and release resources."""
        pass

    def __enter__(self) -> StorageBackend:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()
