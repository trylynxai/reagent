"""Replay engine for deterministic agent execution replay."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator
from uuid import UUID

from reagent.core.constants import ReplayMode
from reagent.core.exceptions import ReplayError, TraceNotFoundError
from reagent.replay.determinism import DeterminismController
from reagent.replay.executor import ExecutorRegistry, ExecutionResult, execute_step
from reagent.replay.loader import TraceLoader
from reagent.replay.sandbox import Sandbox
from reagent.replay.session import ReplaySession, StepResult
from reagent.schema.run import Run
from reagent.schema.steps import AnyStep, LLMCallStep, ToolCallStep, ChainStep, AgentStep, RetrievalStep, CheckpointStep
from reagent.storage.base import StorageBackend


@dataclass
class StepOverrides:
    """Configuration for which steps to re-execute vs replay.

    In partial/hybrid replay modes, this controls which steps get
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

    # Custom function replacements: step_number -> replacement function
    patch_functions: dict[int, Callable[..., Any]] = field(default_factory=dict)

    # Custom function replacements by step type
    patch_by_type: dict[str, Callable[..., Any]] = field(default_factory=dict)

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

        # Check if a patch exists for this step
        if step.step_number in self.patch_functions:
            return True
        if step.step_type in self.patch_by_type:
            return True

        return False

    def get_patch(self, step: AnyStep) -> Callable[..., Any] | None:
        """Get patch function for a step.

        Priority: step number > step type.

        Args:
            step: Step to get patch for

        Returns:
            Patch function or None
        """
        # Step-number-specific patch
        if step.step_number in self.patch_functions:
            return self.patch_functions[step.step_number]

        # Type-level patch
        if step.step_type in self.patch_by_type:
            return self.patch_by_type[step.step_type]

        return None


class ReplayEngine:
    """Engine for replaying agent executions.

    Supports multiple replay modes:
    - STRICT: Return exact recorded outputs, block external calls
    - PARTIAL: Re-execute selected steps, replay others from recording
    - MOCK: Intercept external calls, return recorded responses
    - HYBRID: Configurable per step type

    Partial replay usage:
        engine = ReplayEngine(storage, mode=ReplayMode.PARTIAL)

        # Register executors for steps that should run live
        engine.executors.register_tool("web_search", my_search_fn)
        engine.executors.register_llm("gpt-4", my_llm_fn)

        # Specify which steps to re-run
        overrides = StepOverrides(rerun_tools={"web_search"})
        session = engine.replay(run_id, overrides=overrides)

        # Check for divergence
        for result in session.results:
            if result.diverged:
                print(f"Step {result.step_number} diverged: {result.divergence_details}")
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
        self.executors = ExecutorRegistry()

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
            # Partial mode does NOT activate sandbox (steps may need network)
            if mode in (ReplayMode.STRICT, ReplayMode.MOCK):
                self._sandbox.activate()

                # Pre-load recorded responses into sandbox for mock mode
                if mode == ReplayMode.MOCK:
                    for step in run.steps:
                        output = self._get_step_output(step)
                        self._sandbox.add_recorded_response(step.step_number, output)

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

                if mode == ReplayMode.MOCK:
                    for step in run.steps:
                        output = self._get_step_output(step)
                        self._sandbox.add_recorded_response(step.step_number, output)

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

        For STRICT mode: always returns recorded output.
        For PARTIAL mode: re-executes steps matching overrides, replays others.
        For MOCK mode: returns recorded responses via sandbox.
        For HYBRID mode: uses overrides to decide per-step.

        Args:
            step: Step to replay
            mode: Replay mode
            overrides: Step overrides
            session: Current session

        Returns:
            Step result with original and replay outputs
        """
        # Activate determinism controls
        self._determinism.activate(timestamp=step.timestamp_start)

        try:
            original_output = self._get_step_output(step)
            replay_output = original_output
            result_mode = "replayed"
            execution_duration_ms = step.duration_ms
            execution_error = None

            should_rerun = overrides.should_rerun(step)

            if mode == ReplayMode.STRICT:
                # Always return recorded output
                result_mode = "replayed"

            elif mode == ReplayMode.PARTIAL:
                if should_rerun:
                    replay_output, result_mode, execution_duration_ms, execution_error = (
                        self._execute_step(step, overrides)
                    )
                else:
                    result_mode = "replayed"

            elif mode == ReplayMode.MOCK:
                # Use sandbox recorded responses
                replay_output = self._sandbox.get_recorded_response(step.step_number)
                result_mode = "mocked"

            elif mode == ReplayMode.HYBRID:
                if should_rerun:
                    replay_output, result_mode, execution_duration_ms, execution_error = (
                        self._execute_step(step, overrides)
                    )
                else:
                    result_mode = "replayed"

            # Check for divergence (only for re-executed/patched steps)
            diverged = False
            divergence_details = None

            if result_mode not in ("replayed", "mocked"):
                diverged, divergence_details = self._check_divergence(
                    step, original_output, replay_output, session
                )

            # Record checkpoint state for drift analysis
            if isinstance(step, CheckpointStep):
                session.record_checkpoint_state(
                    step_number=step.step_number,
                    checkpoint_name=step.checkpoint_name,
                    state_hash=step.state_hash,
                    state_data=step.state_data,
                )

            return StepResult(
                step_number=step.step_number,
                step_type=step.step_type,
                mode=result_mode,
                original_output=original_output,
                replay_output=replay_output,
                diverged=diverged,
                divergence_details=divergence_details,
                duration_ms=execution_duration_ms,
            )

        finally:
            self._determinism.deactivate()

    def _execute_step(
        self,
        step: AnyStep,
        overrides: StepOverrides,
    ) -> tuple[Any, str, int | None, str | None]:
        """Execute a step using patch functions or registered executors.

        Returns:
            (output, mode_label, duration_ms, error)
        """
        # 1. Check for a patch function in overrides
        patch_fn = overrides.get_patch(step)
        if patch_fn is not None:
            exec_result = execute_step(step, patch_fn)
            return (
                exec_result.output,
                "patched",
                exec_result.duration_ms,
                exec_result.error,
            )

        # 2. Check registered executors
        executor = self.executors.get_executor(step)
        if executor is not None:
            exec_result = execute_step(step, executor)
            return (
                exec_result.output,
                "re-executed",
                exec_result.duration_ms,
                exec_result.error,
            )

        # 3. No executor found - return recorded output with warning
        return (
            self._get_step_output(step),
            "replayed",
            step.duration_ms,
            None,
        )

    def _check_divergence(
        self,
        step: AnyStep,
        original_output: Any,
        replay_output: Any,
        session: ReplaySession,
    ) -> tuple[bool, str | None]:
        """Check for divergence and build details string.

        Returns:
            (diverged, details)
        """
        try:
            diverged = session.check_divergence(step, original_output, replay_output)
        except Exception:
            # In non-strict modes, check_divergence may raise; treat as diverged
            diverged = True

        if not diverged:
            return False, None

        # Build divergence details
        details_parts = []

        orig_preview = _preview_value(original_output)
        new_preview = _preview_value(replay_output)

        if orig_preview != new_preview:
            details_parts.append(f"original: {orig_preview}")
            details_parts.append(f"new: {new_preview}")
        else:
            details_parts.append("Output hash changed")

        return True, " | ".join(details_parts)

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
        elif isinstance(step, ChainStep):
            return step.output
        elif isinstance(step, AgentStep):
            return step.action_output or step.final_answer
        elif isinstance(step, RetrievalStep):
            if step.results:
                return step.results.documents
            return None
        else:
            return getattr(step, "output", None) or getattr(step, "result", None)

    def replay_with_drift_detection(
        self,
        run_id: UUID | str,
        drift_config: Any | None = None,
        **replay_kwargs: Any,
    ) -> tuple[ReplaySession, Any]:
        """Replay a run and return both the session and a drift report.

        Args:
            run_id: Run to replay.
            drift_config: Optional DriftConfig for tolerance settings.
            **replay_kwargs: Additional arguments passed to replay().

        Returns:
            Tuple of (ReplaySession, DriftReport).
        """
        from reagent.analysis.drift import DriftDetector, DriftConfig

        if isinstance(run_id, str):
            run_id = UUID(run_id)

        session = self.replay(run_id, **replay_kwargs)
        original_run = self._loader.load_full(run_id)

        # Build replay CheckpointSteps from session data
        original_checkpoints = [
            s for s in original_run.steps
            if isinstance(s, CheckpointStep)
        ]

        replay_checkpoint_steps = []
        for cp_data in session.replay_checkpoints:
            replay_checkpoint_steps.append(
                CheckpointStep(
                    run_id=run_id,
                    step_number=cp_data["step_number"],
                    timestamp_start=original_run.metadata.start_time,
                    checkpoint_name=cp_data["checkpoint_name"],
                    state_hash=cp_data["state_hash"],
                    state_data=cp_data["state_data"],
                )
            )

        config = drift_config if isinstance(drift_config, DriftConfig) else DriftConfig()
        detector = DriftDetector(config)
        report = detector.analyze(
            original_checkpoints,
            replay_checkpoint_steps,
            original_run_id=run_id,
            replay_run_id=run_id,
        )
        return session, report

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


def _preview_value(value: Any, max_len: int = 80) -> str:
    """Create a short preview of a value for divergence details."""
    if value is None:
        return "None"
    s = str(value)
    if len(s) > max_len:
        return s[:max_len - 3] + "..."
    return s
