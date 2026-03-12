"""JSONL file storage backend.

Stores each run as a JSONL file with:
- First line: Run metadata
- Subsequent lines: Steps (one per line)
- Last line (after completion): Updated metadata with final stats
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID

from pydantic import TypeAdapter

from reagent.core.exceptions import TraceNotFoundError, TraceCorruptedError, StorageError
from reagent.schema.run import Run, RunMetadata, RunSummary
from reagent.schema.steps import (
    AnyStep,
    LLMCallStep,
    ToolCallStep,
    RetrievalStep,
    ChainStep,
    AgentStep,
    ReasoningStep,
    ErrorStep,
    CheckpointStep,
    CustomStep,
)
from reagent.storage.base import StorageBackend, RunFilter, Pagination


# Type adapter for deserializing steps
STEP_TYPE_MAP = {
    "llm_call": LLMCallStep,
    "tool_call": ToolCallStep,
    "retrieval": RetrievalStep,
    "chain": ChainStep,
    "agent": AgentStep,
    "reasoning": ReasoningStep,
    "error": ErrorStep,
    "checkpoint": CheckpointStep,
    "custom": CustomStep,
}


class JSONLStorage(StorageBackend):
    """JSONL file-based storage backend.

    Default storage for development. Human-readable and git-friendly.
    Each run is stored as a separate .jsonl file.
    """

    def __init__(self, base_path: str | Path = ".reagent/traces") -> None:
        self.base_path = Path(base_path).expanduser().resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_run_path(self, run_id: UUID) -> Path:
        """Get the file path for a run."""
        return self.base_path / f"{run_id}.jsonl"

    def save_run(self, run_id: UUID, metadata: RunMetadata) -> None:
        """Save or update run metadata."""
        run_path = self._get_run_path(run_id)

        if run_path.exists():
            # Update existing file - rewrite metadata line
            self._update_metadata(run_path, metadata)
        else:
            # New file - write metadata as first line
            with open(run_path, "w") as f:
                f.write(self._serialize_metadata(metadata) + "\n")

    def save_step(self, run_id: UUID, step: AnyStep) -> None:
        """Save a step to the run."""
        run_path = self._get_run_path(run_id)

        if not run_path.exists():
            raise StorageError(f"Run not found: {run_id}. Call save_run first.")

        with open(run_path, "a") as f:
            f.write(self._serialize_step(step) + "\n")

    def load_run(self, run_id: UUID) -> Run:
        """Load a complete run with all steps."""
        run_path = self._get_run_path(run_id)

        if not run_path.exists():
            raise TraceNotFoundError(str(run_id))

        metadata = None
        steps: list[AnyStep] = []

        try:
            with open(run_path, "r") as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue

                    data = json.loads(line)

                    if i == 0 or data.get("_type") == "metadata":
                        metadata = self._deserialize_metadata(data)
                    elif data.get("_type") == "step":
                        steps.append(self._deserialize_step(data))
                    else:
                        # Legacy format or unknown
                        if "run_id" in data and "start_time" in data:
                            metadata = self._deserialize_metadata(data)
                        elif "step_type" in data:
                            steps.append(self._deserialize_step(data))

        except json.JSONDecodeError as e:
            raise TraceCorruptedError(str(run_id), f"JSON decode error: {e}")
        except Exception as e:
            raise TraceCorruptedError(str(run_id), str(e))

        if metadata is None:
            raise TraceCorruptedError(str(run_id), "No metadata found")

        return Run(metadata=metadata, steps=steps)

    def load_metadata(self, run_id: UUID) -> RunMetadata:
        """Load only run metadata."""
        run_path = self._get_run_path(run_id)

        if not run_path.exists():
            raise TraceNotFoundError(str(run_id))

        try:
            with open(run_path, "r") as f:
                first_line = f.readline().strip()
                if not first_line:
                    raise TraceCorruptedError(str(run_id), "Empty file")

                data = json.loads(first_line)
                return self._deserialize_metadata(data)

        except json.JSONDecodeError as e:
            raise TraceCorruptedError(str(run_id), f"JSON decode error: {e}")

    def load_steps(
        self,
        run_id: UUID,
        start: int | None = None,
        end: int | None = None,
        step_type: str | None = None,
    ) -> Iterator[AnyStep]:
        """Load steps from a run with optional filtering."""
        run_path = self._get_run_path(run_id)

        if not run_path.exists():
            raise TraceNotFoundError(str(run_id))

        try:
            with open(run_path, "r") as f:
                for i, line in enumerate(f):
                    # Skip first line (metadata)
                    if i == 0:
                        continue

                    line = line.strip()
                    if not line:
                        continue

                    data = json.loads(line)

                    if data.get("_type") == "metadata":
                        continue

                    step = self._deserialize_step(data)

                    # Filter by step number range
                    if start is not None and step.step_number < start:
                        continue
                    if end is not None and step.step_number >= end:
                        continue

                    # Filter by step type
                    if step_type is not None and step.step_type != step_type:
                        continue

                    yield step

        except json.JSONDecodeError as e:
            raise TraceCorruptedError(str(run_id), f"JSON decode error: {e}")

    def list_runs(
        self,
        filters: RunFilter | None = None,
        pagination: Pagination | None = None,
    ) -> list[RunSummary]:
        """List runs matching the given criteria."""
        filters = filters or RunFilter()
        pagination = pagination or Pagination()

        results: list[RunSummary] = []

        for jsonl_file in self.base_path.glob("*.jsonl"):
            try:
                run_id = UUID(jsonl_file.stem)
                metadata = self.load_metadata(run_id)

                if self._matches_filter(metadata, filters):
                    results.append(RunSummary.from_metadata(metadata))

            except (ValueError, TraceCorruptedError):
                # Skip invalid files
                continue

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

        for jsonl_file in self.base_path.glob("*.jsonl"):
            try:
                run_id = UUID(jsonl_file.stem)
                metadata = self.load_metadata(run_id)

                if not self._matches_filter(metadata, filters):
                    continue

                # Search in metadata
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

                # Search in file content
                content = jsonl_file.read_text().lower()
                if query_lower in content:
                    results.append(RunSummary.from_metadata(metadata))

            except (ValueError, TraceCorruptedError):
                continue

        # Sort and paginate
        reverse = pagination.sort_order == "desc"
        sort_key = self._get_sort_key(pagination.sort_by)
        results.sort(key=sort_key, reverse=reverse)

        start = pagination.offset
        end = start + pagination.limit
        return results[start:end]

    def delete_run(self, run_id: UUID) -> bool:
        """Delete a run and all its steps."""
        run_path = self._get_run_path(run_id)

        if not run_path.exists():
            return False

        run_path.unlink()
        return True

    def exists(self, run_id: UUID) -> bool:
        """Check if a run exists."""
        return self._get_run_path(run_id).exists()

    def count_runs(self, filters: RunFilter | None = None) -> int:
        """Count runs matching the given criteria."""
        if filters is None:
            return len(list(self.base_path.glob("*.jsonl")))

        count = 0
        for jsonl_file in self.base_path.glob("*.jsonl"):
            try:
                run_id = UUID(jsonl_file.stem)
                metadata = self.load_metadata(run_id)
                if self._matches_filter(metadata, filters):
                    count += 1
            except (ValueError, TraceCorruptedError):
                continue

        return count

    def close(self) -> None:
        """Close the storage backend."""
        pass  # Nothing to close for file-based storage

    def _update_metadata(self, run_path: Path, metadata: RunMetadata) -> None:
        """Update metadata in an existing file."""
        lines = run_path.read_text().splitlines()

        if not lines:
            lines = [self._serialize_metadata(metadata)]
        else:
            lines[0] = self._serialize_metadata(metadata)

        run_path.write_text("\n".join(lines) + "\n")

    def _serialize_metadata(self, metadata: RunMetadata) -> str:
        """Serialize metadata to JSON."""
        data = metadata.model_dump(mode="json")
        data["_type"] = "metadata"
        return json.dumps(data, default=str)

    def _serialize_step(self, step: AnyStep) -> str:
        """Serialize a step to JSON."""
        data = step.model_dump(mode="json")
        data["_type"] = "step"
        return json.dumps(data, default=str)

    def _deserialize_metadata(self, data: dict[str, Any]) -> RunMetadata:
        """Deserialize metadata from JSON."""
        data.pop("_type", None)
        return RunMetadata.model_validate(data)

    def _deserialize_step(self, data: dict[str, Any]) -> AnyStep:
        """Deserialize a step from JSON."""
        data.pop("_type", None)
        step_type = data.get("step_type", "custom")

        step_class = STEP_TYPE_MAP.get(step_type, CustomStep)
        return step_class.model_validate(data)

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

        # Tags filter
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

        # Error filter
        if filters.has_error is not None:
            has_error = metadata.error is not None
            if has_error != filters.has_error:
                return False

        # Failure category filter
        if filters.failure_category:
            if metadata.failure_category != filters.failure_category:
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
