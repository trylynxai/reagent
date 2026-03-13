"""Step executors for partial replay mode.

Executors provide real implementations for re-executing recorded steps.
During partial replay, steps marked for re-execution are passed to their
registered executor instead of returning the recorded output.

Users register executors to control which steps run live vs replayed:

    engine = ReplayEngine(storage=storage, mode=ReplayMode.PARTIAL)

    # Register a tool executor
    engine.executors.register_tool("web_search", my_search_function)

    # Register an LLM executor (e.g. call OpenAI with a new prompt)
    engine.executors.register_llm("gpt-4", my_llm_function)

    # Register a generic executor by step type
    engine.executors.register("tool_call", my_tool_dispatcher)

    session = engine.replay(run_id, overrides=StepOverrides(rerun_tools={"web_search"}))
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from reagent.schema.steps import (
    AnyStep,
    LLMCallStep,
    ToolCallStep,
    RetrievalStep,
    ChainStep,
    AgentStep,
)


class StepExecutorFn(Protocol):
    """Protocol for step executor functions.

    An executor receives the original step and returns the new output.
    The step contains all the original inputs needed for re-execution.
    """

    def __call__(self, step: AnyStep) -> Any: ...


@dataclass
class ExecutionResult:
    """Result from executing a step."""

    output: Any
    duration_ms: int = 0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutorRegistry:
    """Registry for step executors.

    Maps step types, tool names, and model names to executor functions.
    Lookup priority: step-number > tool/model name > step type > default.
    """

    def __init__(self) -> None:
        # Executors by step type (e.g. "llm_call", "tool_call")
        self._type_executors: dict[str, StepExecutorFn] = {}

        # Executors by tool name (for ToolCallStep)
        self._tool_executors: dict[str, StepExecutorFn] = {}

        # Executors by model name (for LLMCallStep)
        self._model_executors: dict[str, StepExecutorFn] = {}

        # Executors by specific step number
        self._step_executors: dict[int, StepExecutorFn] = {}

        # Default executor (fallback for all step types)
        self._default_executor: StepExecutorFn | None = None

    def register(self, step_type: str, executor: StepExecutorFn) -> None:
        """Register an executor for a step type.

        Args:
            step_type: Step type (e.g. "llm_call", "tool_call")
            executor: Function that takes a step and returns output
        """
        self._type_executors[step_type] = executor

    def register_tool(self, tool_name: str, executor: StepExecutorFn) -> None:
        """Register an executor for a specific tool.

        Args:
            tool_name: Tool name to match
            executor: Function that takes a ToolCallStep and returns output
        """
        self._tool_executors[tool_name] = executor

    def register_llm(self, model: str, executor: StepExecutorFn) -> None:
        """Register an executor for a specific LLM model.

        Args:
            model: Model name to match
            executor: Function that takes an LLMCallStep and returns output
        """
        self._model_executors[model] = executor

    def register_step(self, step_number: int, executor: StepExecutorFn) -> None:
        """Register an executor for a specific step number.

        Highest priority - overrides all other matching.

        Args:
            step_number: Step number to match
            executor: Function that takes a step and returns output
        """
        self._step_executors[step_number] = executor

    def set_default(self, executor: StepExecutorFn) -> None:
        """Set a default executor for all unmatched steps.

        Args:
            executor: Fallback executor function
        """
        self._default_executor = executor

    def get_executor(self, step: AnyStep) -> StepExecutorFn | None:
        """Find the best executor for a step.

        Priority: step number > tool/model name > step type > default.

        Args:
            step: Step to find executor for

        Returns:
            Executor function or None if no match
        """
        # 1. Specific step number
        if step.step_number in self._step_executors:
            return self._step_executors[step.step_number]

        # 2. Tool name (for ToolCallStep)
        if isinstance(step, ToolCallStep) and step.tool_name in self._tool_executors:
            return self._tool_executors[step.tool_name]

        # 3. Model name (for LLMCallStep)
        if isinstance(step, LLMCallStep) and step.model in self._model_executors:
            return self._model_executors[step.model]

        # 4. Step type
        if step.step_type in self._type_executors:
            return self._type_executors[step.step_type]

        # 5. Default
        return self._default_executor

    def has_executor(self, step: AnyStep) -> bool:
        """Check if an executor exists for a step."""
        return self.get_executor(step) is not None

    def clear(self) -> None:
        """Remove all registered executors."""
        self._type_executors.clear()
        self._tool_executors.clear()
        self._model_executors.clear()
        self._step_executors.clear()
        self._default_executor = None


def execute_step(step: AnyStep, executor: StepExecutorFn) -> ExecutionResult:
    """Execute a step using the given executor, capturing timing and errors.

    Args:
        step: Step to execute
        executor: Executor function

    Returns:
        ExecutionResult with output, timing, and error info
    """
    start = time.time()
    error = None
    output = None

    try:
        output = executor(step)
    except Exception as e:
        error = str(e)
        output = None

    duration_ms = int((time.time() - start) * 1000)

    return ExecutionResult(
        output=output,
        duration_ms=duration_ms,
        error=error,
    )
