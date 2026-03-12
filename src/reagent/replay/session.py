"""Replay session for tracking replay state and progress."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from reagent.core.constants import ReplayMode, Status
from reagent.core.exceptions import ReplayDivergenceError
from reagent.schema.run import RunMetadata
from reagent.schema.steps import AnyStep


@dataclass
class StepResult:
    """Result of replaying a single step."""

    step_number: int
    step_type: str
    mode: str  # "replayed", "re-executed", "skipped"
    original_output: Any
    replay_output: Any
    diverged: bool
    divergence_details: str | None = None
    duration_ms: int | None = None


@dataclass
class Checkpoint:
    """Checkpoint for resumable replay."""

    step_number: int
    state_hash: str
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


class ReplaySession:
    """Session for tracking replay state and progress.

    Provides:
    - Step-by-step progress tracking
    - Checkpointing for resumption
    - Divergence detection
    - Breakpoint management
    """

    def __init__(
        self,
        run_id: UUID,
        original_metadata: RunMetadata,
        mode: ReplayMode = ReplayMode.STRICT,
    ) -> None:
        """Initialize the replay session.

        Args:
            run_id: Run being replayed
            original_metadata: Original run metadata
            mode: Replay mode
        """
        self.run_id = run_id
        self.original_metadata = original_metadata
        self.mode = mode

        self._current_step = 0
        self._total_steps = original_metadata.steps.total
        self._results: list[StepResult] = []
        self._checkpoints: list[Checkpoint] = []
        self._breakpoints: set[int] = set()
        self._state: dict[str, Any] = {}

        self._started_at: datetime | None = None
        self._ended_at: datetime | None = None
        self._status = Status.RUNNING
        self._error: str | None = None

    @property
    def current_step(self) -> int:
        """Get current step number."""
        return self._current_step

    @property
    def total_steps(self) -> int:
        """Get total number of steps."""
        return self._total_steps

    @property
    def progress(self) -> float:
        """Get replay progress (0-1)."""
        if self._total_steps == 0:
            return 1.0
        return self._current_step / self._total_steps

    @property
    def is_complete(self) -> bool:
        """Check if replay is complete."""
        return self._current_step >= self._total_steps

    @property
    def status(self) -> Status:
        """Get session status."""
        return self._status

    @property
    def results(self) -> list[StepResult]:
        """Get step results."""
        return self._results.copy()

    def start(self) -> None:
        """Start the replay session."""
        self._started_at = datetime.utcnow()
        self._status = Status.RUNNING

    def complete(self, error: str | None = None) -> None:
        """Complete the replay session.

        Args:
            error: Error message if failed
        """
        self._ended_at = datetime.utcnow()
        if error:
            self._status = Status.FAILED
            self._error = error
        else:
            self._status = Status.COMPLETED

    def add_result(self, result: StepResult) -> None:
        """Add a step result.

        Args:
            result: Step result to add
        """
        self._results.append(result)
        self._current_step = result.step_number + 1

    def checkpoint(self, metadata: dict[str, Any] | None = None) -> Checkpoint:
        """Create a checkpoint at the current position.

        Args:
            metadata: Optional checkpoint metadata

        Returns:
            Created checkpoint
        """
        state_hash = self._compute_state_hash()

        checkpoint = Checkpoint(
            step_number=self._current_step,
            state_hash=state_hash,
            timestamp=datetime.utcnow(),
            metadata=metadata or {},
        )

        self._checkpoints.append(checkpoint)
        return checkpoint

    def restore_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Restore session to a checkpoint.

        Args:
            checkpoint: Checkpoint to restore to
        """
        self._current_step = checkpoint.step_number
        # Truncate results after checkpoint
        self._results = [r for r in self._results if r.step_number < checkpoint.step_number]

    def set_breakpoint(self, step_number: int) -> None:
        """Set a breakpoint at a step.

        Args:
            step_number: Step to break at
        """
        self._breakpoints.add(step_number)

    def clear_breakpoint(self, step_number: int) -> None:
        """Clear a breakpoint.

        Args:
            step_number: Step to clear breakpoint from
        """
        self._breakpoints.discard(step_number)

    def clear_all_breakpoints(self) -> None:
        """Clear all breakpoints."""
        self._breakpoints.clear()

    def is_breakpoint(self, step_number: int) -> bool:
        """Check if there's a breakpoint at a step.

        Args:
            step_number: Step to check

        Returns:
            True if breakpoint is set
        """
        return step_number in self._breakpoints

    def set_state(self, key: str, value: Any) -> None:
        """Set a state value.

        Args:
            key: State key
            value: State value
        """
        self._state[key] = value

    def get_state(self, key: str, default: Any = None) -> Any:
        """Get a state value.

        Args:
            key: State key
            default: Default value

        Returns:
            State value or default
        """
        return self._state.get(key, default)

    def check_divergence(
        self,
        step: AnyStep,
        original_output: Any,
        replay_output: Any,
        tolerance: float = 0.0,
    ) -> bool:
        """Check for divergence between original and replay output.

        Args:
            step: Step being checked
            original_output: Original recorded output
            replay_output: New replay output
            tolerance: Similarity tolerance (0 = exact match required)

        Returns:
            True if diverged

        Raises:
            ReplayDivergenceError: If in strict mode and diverged
        """
        # Simple equality check
        original_hash = self._hash_value(original_output)
        replay_hash = self._hash_value(replay_output)

        if original_hash != replay_hash:
            if self.mode == ReplayMode.STRICT:
                raise ReplayDivergenceError(
                    f"Divergence detected at step {step.step_number}",
                    step_number=step.step_number,
                    expected_hash=original_hash,
                    actual_hash=replay_hash,
                    details={"step_type": step.step_type},
                )
            return True

        return False

    def _compute_state_hash(self) -> str:
        """Compute hash of current state."""
        state_str = json.dumps(
            {
                "step": self._current_step,
                "state": str(self._state),
                "results_count": len(self._results),
            },
            sort_keys=True,
        )
        return hashlib.sha256(state_str.encode()).hexdigest()[:16]

    def _hash_value(self, value: Any) -> str:
        """Hash a value for comparison."""
        if value is None:
            return "null"

        try:
            if hasattr(value, "model_dump"):
                value = value.model_dump()
            value_str = json.dumps(value, sort_keys=True, default=str)
        except (TypeError, ValueError):
            value_str = str(value)

        return hashlib.sha256(value_str.encode()).hexdigest()[:16]

    def to_summary(self) -> dict[str, Any]:
        """Get session summary.

        Returns:
            Summary dictionary
        """
        diverged_steps = [r.step_number for r in self._results if r.diverged]

        return {
            "run_id": str(self.run_id),
            "mode": self.mode.value,
            "status": self._status.value,
            "progress": self.progress,
            "current_step": self._current_step,
            "total_steps": self._total_steps,
            "steps_completed": len(self._results),
            "steps_diverged": len(diverged_steps),
            "diverged_at": diverged_steps,
            "checkpoints": len(self._checkpoints),
            "breakpoints": sorted(self._breakpoints),
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "ended_at": self._ended_at.isoformat() if self._ended_at else None,
            "error": self._error,
        }
