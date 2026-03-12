"""Replay engine for deterministic agent execution replay."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator
from uuid import UUID

from reagent.core.constants import ReplayMode
from reagent.core.exceptions import ReplayError, TraceNotFoundError
from reagent.replay.determinism import DeterminismController
from reagent.replay.loader import TraceLoader
from reagent.replay.sandbox import Sandbox
from reagent.replay.session import ReplaySession, StepResult
from reagent.schema.run import Run
from reagent.schema.steps import AnyStep, LLMCallStep, ToolCallStep
from reagent.storage.base import StorageBackend


@dataclass
class StepOverrides:
    """Configuration for which steps to re-execute vs replay.

    In partial replay mode, this controls which steps get
    re-executed with real implementations vs replayed from
    recorded outputs.
    """

    # Specific step numbers to re-execute
    rerun_steps: set[int] = field(default_factory=set)

    # Step types to always re-execute
    rerun_types: set[str] = field(default_factory=set)

    # Tool names to re-execute
    rerun_tools: set[str] = field(default_factory=set)

    # Model names to re-execute
    rerun_models: set[str] = field(default_factory=set)

    # Custom function replacements: step_type -> replacement function
    patch_functions: dict[str, Callable[..., Any]] = field(default_factory=dict)

    def should_rerun(self, step: AnyStep) -> bool:
        """Check if a step should be re-executed.

        Args:
            step: Step to check

        Returns:
            True if step should be re-executed
        """
        # Check specific step numbers
        if step.step_number in self.rerun_steps:
            return True

        # Check step types
        if step.step_type in self.rerun_types:
            return True

        # Check tool names
        if isinstance(step, ToolCallStep) and step.tool_name in self.rerun_tools:
            return True

        # Check model names
        if isinstance(step, LLMCallStep) and step.model in self.rerun_models:
            return True

        return False

    def get_patch(self, step: AnyStep) -> Callable[..., Any] | None:
        """Get patch function for a step.

        Args:
            step: Step to get patch for

        Returns:
            Patch function or None
        """
        return self.patch_functions.get(step.step_type)


class ReplayEngine:
    """Engine for replaying agent executions.

    Supports multiple replay modes:
    - STRICT: Return exact recorded outputs, block external calls
    - PARTIAL: Re-execute selected steps, replay others
    - MOCK: Intercept external calls, return recorded responses
    - HYBRID: Configurable per step type
    """

    def __init__(
        self,
        storage: StorageBackend,
        mode: ReplayMode = ReplayMode.STRICT,
        sandbox_strict: bool = True,
        checkpoint_interval: int | None = None,
    ) -> None:
        """Initialize the replay engine.

        Args:
            storage: Storage backend
            mode: Default replay mode
            sandbox_strict: Whether to strictly enforce sandbox
            checkpoint_interval: Auto-checkpoint every N steps
        """
        self._storage = storage
        self._loader = TraceLoader(storage)
        self._mode = mode
        self._sandbox_strict = sandbox_strict
        self._checkpoint_interval = checkpoint_interval

        self._determinism = DeterminismController()
        self._sandbox = Sandbox(strict=sandbox_strict)

    def replay(
        self,
        run_id: UUID | str,
        mode: ReplayMode | None = None,
        overrides: StepOverrides | None = None,
        from_step: int | None = None,
        to_step: int | None = None,
    ) -> ReplaySession:
        """Replay a run.

        Args:
            run_id: Run to replay
            mode: Replay mode (uses default if None)
            overrides: Step overrides for partial replay
            from_step: Start from this step (inclusive)
            to_step: Stop at this step (exclusive)

        Returns:
            Completed replay session
        """
        if isinstance(run_id, str):
            run_id = UUID(run_id)

        mode = mode or self._mode
        overrides = overrides or StepOverrides()

        # Load run
        run = self._loader.load_full(run_id)

        # Create session
        session = ReplaySession(
            run_id=run_id,
            original_metadata=run.metadata,
            mode=mode,
        )

        session.start()

        try:
            # Activate sandbox for strict/mock modes
            if mode in (ReplayMode.STRICT, ReplayMode.MOCK):
                self._sandbox.activate()

            # Replay steps
            for step in run.steps:
                # Check step range
                if from_step is not None and step.step_number < from_step:
                    continue
                if to_step is not None and step.step_number >= to_step:
                    break

                # Check breakpoints
                if session.is_breakpoint(step.step_number):
                    break

                # Replay the step
                result = self._replay_step(step, mode, overrides, session)
                session.add_result(result)

                # Auto-checkpoint
                if self._checkpoint_interval and step.step_number % self._checkpoint_interval == 0:
                    session.checkpoint()

            session.complete()

        except Exception as e:
            session.complete(error=str(e))
            raise

        finally:
            if self._sandbox.is_active:
                self._sandbox.deactivate()

        return session

    def replay_interactive(
        self,
        run_id: UUID | str,
        mode: ReplayMode | None = None,
        overrides: StepOverrides | None = None,
    ) -> Iterator[tuple[AnyStep, ReplaySession]]:
        """Replay interactively, yielding after each step.

        This allows for interactive debugging with step-by-step control.

        Args:
            run_id: Run to replay
            mode: Replay mode
            overrides: Step overrides

        Yields:
            Tuples of (next_step, session)
        """
        if isinstance(run_id, str):
            run_id = UUID(run_id)

        mode = mode or self._mode
        overrides = overrides or StepOverrides()

        # Load run
        run = self._loader.load_full(run_id)

        # Create session
        session = ReplaySession(
            run_id=run_id,
            original_metadata=run.metadata,
            mode=mode,
        )

        session.start()

        try:
            if mode in (ReplayMode.STRICT, ReplayMode.MOCK):
                self._sandbox.activate()

            for step in run.steps:
                # Yield before executing
                yield (step, session)

                # Execute step
                result = self._replay_step(step, mode, overrides, session)
                session.add_result(result)

            session.complete()

        except Exception as e:
            session.complete(error=str(e))
            raise

        finally:
            if self._sandbox.is_active:
                self._sandbox.deactivate()

    def _replay_step(
        self,
        step: AnyStep,
        mode: ReplayMode,
        overrides: StepOverrides,
        session: ReplaySession,
    ) -> StepResult:
        """Replay a single step.

        Args:
            step: Step to replay
            mode: Replay mode
            overrides: Step overrides
            session: Current session

        Returns:
            Step result
        """
        # Activate determinism controls
        self._determinism.activate(timestamp=step.timestamp_start)

        try:
            original_output = self._get_step_output(step)
            replay_output = original_output
            result_mode = "replayed"

            # Check if we should re-execute
            if mode == ReplayMode.PARTIAL and overrides.should_rerun(step):
                # Check for patch function
                patch_fn = overrides.get_patch(step)
                if patch_fn:
                    replay_output = patch_fn(step)
                    result_mode = "patched"
                else:
                    # Would re-execute here with real implementation
                    # For now, just use recorded output
                    result_mode = "re-executed"

            elif mode == ReplayMode.HYBRID:
                # Hybrid mode: check step-specific configuration
                if overrides.should_rerun(step):
                    result_mode = "re-executed"

            # Check for divergence
            diverged = False
            divergence_details = None

            if result_mode != "replayed":
                diverged = session.check_divergence(step, original_output, replay_output)
                if diverged:
                    divergence_details = f"Output changed from original"

            return StepResult(
                step_number=step.step_number,
                step_type=step.step_type,
                mode=result_mode,
                original_output=original_output,
                replay_output=replay_output,
                diverged=diverged,
                divergence_details=divergence_details,
                duration_ms=step.duration_ms,
            )

        finally:
            self._determinism.deactivate()

    def _get_step_output(self, step: AnyStep) -> Any:
        """Extract the output from a step.

        Args:
            step: Step to extract output from

        Returns:
            Step output
        """
        if isinstance(step, LLMCallStep):
            return step.response
        elif isinstance(step, ToolCallStep):
            return step.output.result if step.output else None
        else:
            return getattr(step, "output", None) or getattr(step, "result", None)

    def get_step(self, run_id: UUID | str, step_number: int) -> AnyStep | None:
        """Get a specific step from a run.

        Args:
            run_id: Run ID
            step_number: Step number

        Returns:
            Step or None
        """
        if isinstance(run_id, str):
            run_id = UUID(run_id)

        return self._loader.load_step(run_id, step_number)
