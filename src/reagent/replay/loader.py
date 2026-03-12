"""Trace loader for streaming and partial loading."""

from __future__ import annotations

from typing import Iterator
from uuid import UUID

from reagent.core.exceptions import TraceNotFoundError
from reagent.schema.run import Run, RunMetadata
from reagent.schema.steps import AnyStep
from reagent.storage.base import StorageBackend


class TraceLoader:
    """Loader for trace data with streaming support.

    Supports:
    - Lazy loading of steps (don't load all into memory)
    - Partial loading (step ranges)
    - Step type filtering
    """

    def __init__(self, storage: StorageBackend) -> None:
        """Initialize the trace loader.

        Args:
            storage: Storage backend to load from
        """
        self._storage = storage

    def load_full(self, run_id: UUID) -> Run:
        """Load a complete run with all steps.

        Args:
            run_id: Run to load

        Returns:
            Complete run

        Raises:
            TraceNotFoundError: If run doesn't exist
        """
        return self._storage.load_run(run_id)

    def load_metadata(self, run_id: UUID) -> RunMetadata:
        """Load only run metadata.

        Args:
            run_id: Run to load

        Returns:
            Run metadata

        Raises:
            TraceNotFoundError: If run doesn't exist
        """
        return self._storage.load_metadata(run_id)

    def load_steps_streaming(
        self,
        run_id: UUID,
        start: int | None = None,
        end: int | None = None,
        step_type: str | None = None,
    ) -> Iterator[AnyStep]:
        """Load steps with streaming (lazy loading).

        Args:
            run_id: Run to load steps from
            start: Starting step number (inclusive)
            end: Ending step number (exclusive)
            step_type: Filter by step type

        Yields:
            Steps matching criteria

        Raises:
            TraceNotFoundError: If run doesn't exist
        """
        yield from self._storage.load_steps(
            run_id,
            start=start,
            end=end,
            step_type=step_type,
        )

    def load_steps_range(
        self,
        run_id: UUID,
        start: int,
        end: int,
    ) -> list[AnyStep]:
        """Load a specific range of steps.

        Args:
            run_id: Run to load steps from
            start: Starting step number (inclusive)
            end: Ending step number (exclusive)

        Returns:
            List of steps in range

        Raises:
            TraceNotFoundError: If run doesn't exist
        """
        return list(self._storage.load_steps(run_id, start=start, end=end))

    def load_step(self, run_id: UUID, step_number: int) -> AnyStep | None:
        """Load a single step by number.

        Args:
            run_id: Run to load step from
            step_number: Step number to load

        Returns:
            Step or None if not found

        Raises:
            TraceNotFoundError: If run doesn't exist
        """
        steps = list(self._storage.load_steps(
            run_id,
            start=step_number,
            end=step_number + 1,
        ))
        return steps[0] if steps else None

    def get_step_count(self, run_id: UUID) -> int:
        """Get the total number of steps in a run.

        Args:
            run_id: Run to count

        Returns:
            Number of steps

        Raises:
            TraceNotFoundError: If run doesn't exist
        """
        metadata = self.load_metadata(run_id)
        return metadata.steps.total

    def exists(self, run_id: UUID) -> bool:
        """Check if a run exists.

        Args:
            run_id: Run to check

        Returns:
            True if exists
        """
        return self._storage.exists(run_id)
