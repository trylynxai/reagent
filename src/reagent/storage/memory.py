"""In-memory storage backend for testing."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterator
from uuid import UUID

from reagent.core.constants import Status
from reagent.core.exceptions import TraceNotFoundError
from reagent.schema.run import Run, RunMetadata, RunSummary
from reagent.schema.steps import AnyStep
from reagent.storage.base import StorageBackend, RunFilter, Pagination


class MemoryStorage(StorageBackend):
    """In-memory storage backend.

    Useful for testing and ephemeral runs. Data is lost when
    the storage instance is garbage collected.
    """

    def __init__(self) -> None:
        self._metadata: dict[UUID, RunMetadata] = {}
        self._steps: dict[UUID, list[AnyStep]] = defaultdict(list)

    def save_run(self, run_id: UUID, metadata: RunMetadata) -> None:
        """Save or update run metadata."""
        self._metadata[run_id] = metadata

    def save_step(self, run_id: UUID, step: AnyStep) -> None:
        """Save a step to the run."""
        self._steps[run_id].append(step)

    def load_run(self, run_id: UUID) -> Run:
        """Load a complete run with all steps."""
        if run_id not in self._metadata:
            raise TraceNotFoundError(str(run_id))

        return Run(
            metadata=self._metadata[run_id],
            steps=list(self._steps[run_id]),
        )

    def load_metadata(self, run_id: UUID) -> RunMetadata:
        """Load only run metadata."""
        if run_id not in self._metadata:
            raise TraceNotFoundError(str(run_id))

        return self._metadata[run_id]

    def load_steps(
        self,
        run_id: UUID,
        start: int | None = None,
        end: int | None = None,
        step_type: str | None = None,
    ) -> Iterator[AnyStep]:
        """Load steps from a run with optional filtering."""
        if run_id not in self._metadata:
            raise TraceNotFoundError(str(run_id))

        for step in self._steps[run_id]:
            # Filter by step number range
            if start is not None and step.step_number < start:
                continue
            if end is not None and step.step_number >= end:
                continue

            # Filter by step type
            if step_type is not None and step.step_type != step_type:
                continue

            yield step

    def list_runs(
        self,
        filters: RunFilter | None = None,
        pagination: Pagination | None = None,
    ) -> list[RunSummary]:
        """List runs matching the given criteria."""
        filters = filters or RunFilter()
        pagination = pagination or Pagination()

        results: list[RunSummary] = []

        for run_id, metadata in self._metadata.items():
            if not self._matches_filter(metadata, filters):
                continue

            results.append(RunSummary.from_metadata(metadata))

        # Sort
        reverse = pagination.sort_order == "desc"
        sort_key = self._get_sort_key(pagination.sort_by)
        results.sort(key=sort_key, reverse=reverse)

        # Paginate
        start = pagination.offset
        end = start + pagination.limit
        return results[start:end]

    def search(
        self,
        query: str,
        filters: RunFilter | None = None,
        pagination: Pagination | None = None,
    ) -> list[RunSummary]:
        """Search runs by text query."""
        filters = filters or RunFilter()
        pagination = pagination or Pagination()
        query_lower = query.lower()

        results: list[RunSummary] = []

        for run_id, metadata in self._metadata.items():
            if not self._matches_filter(metadata, filters):
                continue

            # Search in name, tags, error message
            searchable = " ".join(
                [
                    metadata.name or "",
                    " ".join(metadata.tags),
                    metadata.error or "",
                    metadata.model or "",
                ]
            ).lower()

            if query_lower in searchable:
                results.append(RunSummary.from_metadata(metadata))
                continue

            # Search in step content
            for step in self._steps[run_id]:
                step_str = str(step.model_dump()).lower()
                if query_lower in step_str:
                    results.append(RunSummary.from_metadata(metadata))
                    break

        # Sort and paginate
        reverse = pagination.sort_order == "desc"
        sort_key = self._get_sort_key(pagination.sort_by)
        results.sort(key=sort_key, reverse=reverse)

        start = pagination.offset
        end = start + pagination.limit
        return results[start:end]

    def delete_run(self, run_id: UUID) -> bool:
        """Delete a run and all its steps."""
        if run_id not in self._metadata:
            return False

        del self._metadata[run_id]
        if run_id in self._steps:
            del self._steps[run_id]
        return True

    def exists(self, run_id: UUID) -> bool:
        """Check if a run exists."""
        return run_id in self._metadata

    def count_runs(self, filters: RunFilter | None = None) -> int:
        """Count runs matching the given criteria."""
        filters = filters or RunFilter()
        count = 0

        for metadata in self._metadata.values():
            if self._matches_filter(metadata, filters):
                count += 1

        return count

    def close(self) -> None:
        """Close the storage backend."""
        pass  # Nothing to close for in-memory storage

    def clear(self) -> None:
        """Clear all stored data."""
        self._metadata.clear()
        self._steps.clear()

    def _matches_filter(self, metadata: RunMetadata, filters: RunFilter) -> bool:
        """Check if metadata matches filter criteria."""
        # Project filter
        if filters.project and metadata.project != filters.project:
            return False

        # Status filter
        if filters.status:
            if isinstance(filters.status, list):
                if metadata.status not in filters.status:
                    return False
            elif metadata.status != filters.status:
                return False

        # Model filter
        if filters.model and metadata.model != filters.model:
            return False

        # Tags filter (all tags must be present)
        if filters.tags:
            if not all(tag in metadata.tags for tag in filters.tags):
                return False

        # Date filters
        if filters.since and metadata.start_time < filters.since:
            return False
        if filters.until and metadata.start_time > filters.until:
            return False

        # Cost filters
        if filters.min_cost_usd is not None:
            if metadata.cost.total_usd < filters.min_cost_usd:
                return False
        if filters.max_cost_usd is not None:
            if metadata.cost.total_usd > filters.max_cost_usd:
                return False

        # Duration filters
        if filters.min_duration_ms is not None:
            if metadata.duration_ms is None or metadata.duration_ms < filters.min_duration_ms:
                return False
        if filters.max_duration_ms is not None:
            if metadata.duration_ms is None or metadata.duration_ms > filters.max_duration_ms:
                return False

        # Token filters
        if filters.min_tokens is not None:
            if metadata.tokens.total_tokens < filters.min_tokens:
                return False
        if filters.max_tokens is not None:
            if metadata.tokens.total_tokens > filters.max_tokens:
                return False

        # Step count filters
        if filters.min_steps is not None:
            if metadata.steps.total < filters.min_steps:
                return False
        if filters.max_steps is not None:
            if metadata.steps.total > filters.max_steps:
                return False

        # Error filter
        if filters.has_error is not None:
            has_error = metadata.error is not None
            if has_error != filters.has_error:
                return False

        # Failure category filter
        if filters.failure_category:
            if metadata.failure_category != filters.failure_category:
                return False

        # Name filter (substring match)
        if filters.name:
            if not metadata.name or filters.name.lower() not in metadata.name.lower():
                return False

        # Framework filter
        if filters.framework:
            if metadata.framework != filters.framework:
                return False

        # Tool name filter (requires checking steps)
        if filters.tool_name:
            run_id = metadata.run_id
            tool_found = False
            for step in self._steps.get(run_id, []):
                if hasattr(step, "tool_name") and step.tool_name == filters.tool_name:
                    tool_found = True
                    break
            if not tool_found:
                return False

        return True

    @staticmethod
    def _get_sort_key(sort_by: str) -> callable:
        """Get sort key function for the given field."""
        if sort_by == "start_time":
            return lambda x: x.start_time or datetime.min
        elif sort_by == "duration":
            return lambda x: x.duration_ms or 0
        elif sort_by == "cost":
            return lambda x: x.total_cost_usd or 0
        elif sort_by == "steps":
            return lambda x: x.step_count or 0
        else:
            return lambda x: x.start_time or datetime.min
