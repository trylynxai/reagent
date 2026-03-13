"""OpenAI Agents SDK adapter for automatic instrumentation.

Captures agent runs, tool calls, LLM calls, and handoffs by registering
a RunHooks implementation with the OpenAI Agents SDK runner.

Usage:
    from reagent.adapters.openai_agents import reagent_openai_agents_hooks

    with reagent.trace(RunConfig(name="multi-agent")) as ctx:
        hooks = reagent_openai_agents_hooks(ctx)
        result = Runner.run(agent, input="Hello", run_hooks=hooks)

Or wrap an entire agent for automatic tracing:

    from reagent.adapters.openai_agents import reagent_openai_agents_run

    with reagent.trace(RunConfig(name="multi-agent")) as ctx:
        result = await reagent_openai_agents_run(ctx, agent, input="Hello")
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from reagent.adapters.base import Adapter
from reagent.core.exceptions import AdapterError

if TYPE_CHECKING:
    from reagent.client.context import RunContext
    from reagent.client.reagent import ReAgent


class OpenAIAgentsAdapter(Adapter):
    """Adapter for OpenAI Agents SDK.

    Provides automatic instrumentation via the SDK's RunHooks system.
    """

    def __init__(self, client: ReAgent) -> None:
        super().__init__(client)

    @property
    def name(self) -> str:
        return "openai_agents"

    @property
    def framework(self) -> str:
        return "openai_agents"

    @classmethod
    def is_available(cls) -> bool:
        """Check if the OpenAI Agents SDK is installed."""
        try:
            import agents  # noqa: F401
            return True
        except ImportError:
            return False

    @classmethod
    def get_framework_version(cls) -> str | None:
        """Get the OpenAI Agents SDK version."""
        try:
            import agents
            return getattr(agents, "__version__", "unknown")
        except (ImportError, AttributeError):
            return None

    def install(self) -> None:
        """Install the adapter."""
        if not self.is_available():
            raise AdapterError(
                "OpenAI Agents SDK is not installed. "
                "Install with: pip install openai-agents"
            )
        self._installed = True

    def uninstall(self) -> None:
        """Uninstall the adapter."""
        self._installed = False


# ---------------------------------------------------------------------------
# Hook-based instrumentation
# ---------------------------------------------------------------------------


class ReAgentHooks:
    """RunHooks implementation that captures agent events to ReAgent.

    Implements the openai-agents RunHooks interface to record:
    - Agent start/end as AgentStep
    - Tool calls as ToolCallStep
    - Handoffs as AgentStep with action="handoff"
    - LLM responses (extracted from agent output) as LLMCallStep

    All steps maintain proper parent-child hierarchy:
    agent_start creates a parent, tool/llm calls within are children.
    """

    def __init__(self, context: RunContext) -> None:
        self._ctx = context
        self._ctx.set_framework("openai_agents")

        # Track active agent spans for nesting
        # Maps agent_name -> (AgentStep, start_time)
        self._agent_stack: list[_AgentFrame] = []

        # Track handoff chain
        self._handoff_chain: list[str] = []

        # Track tool call timings
        self._tool_start_times: dict[str, float] = {}

    # -- Agent lifecycle hooks --

    def on_agent_start(
        self,
        agent: Any,
        context: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when an agent starts executing."""
        agent_name = _get_agent_name(agent)
        agent_model = _get_agent_model(agent)

        step = self._ctx.record_agent_action(
            action="start",
            agent_name=agent_name,
            agent_type="openai_agents",
            action_input={
                "instructions": _get_agent_instructions(agent),
                "model": agent_model,
                "tools": _get_agent_tool_names(agent),
            },
            metadata={
                "handoff_chain": list(self._handoff_chain),
            },
        )

        # Push onto agent stack for nesting
        frame = _AgentFrame(
            agent_name=agent_name,
            step=step,
            start_time=time.time(),
        )
        self._agent_stack.append(frame)

        # Enter nesting context so child steps have this as parent
        self._ctx._step_stack.append(step.step_id)

        # Set model info if available
        if agent_model:
            self._ctx.set_model(agent_model)

    def on_agent_end(
        self,
        agent: Any,
        output: Any = None,
        context: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when an agent finishes executing."""
        agent_name = _get_agent_name(agent)

        # Pop nesting context
        if self._ctx._step_stack:
            self._ctx._step_stack.pop()

        # Pop agent frame
        frame = None
        if self._agent_stack:
            frame = self._agent_stack.pop()

        duration_ms = None
        if frame:
            duration_ms = int((time.time() - frame.start_time) * 1000)

        # Extract final answer
        final_answer = _extract_output(output)

        self._ctx.record_agent_finish(
            final_answer=final_answer,
            agent_name=agent_name,
            duration_ms=duration_ms,
            metadata={
                "handoff_chain": list(self._handoff_chain),
            },
        )

    # -- Tool call hooks --

    def on_tool_start(
        self,
        agent: Any,
        tool: Any,
        input: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool starts executing."""
        tool_name = _get_tool_name(tool)
        self._tool_start_times[tool_name] = time.time()

    def on_tool_end(
        self,
        agent: Any,
        tool: Any,
        input: Any = None,
        output: Any = None,
        error: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool finishes executing."""
        tool_name = _get_tool_name(tool)

        duration_ms = None
        start = self._tool_start_times.pop(tool_name, None)
        if start:
            duration_ms = int((time.time() - start) * 1000)

        tool_input = _normalize_tool_input(input)
        tool_output = _extract_output(output)

        self._ctx.record_tool_call(
            tool_name=tool_name,
            kwargs=tool_input if isinstance(tool_input, dict) else {"input": tool_input},
            result=tool_output,
            error=str(error) if error else None,
            error_type=type(error).__name__ if error else None,
            duration_ms=duration_ms,
            tool_description=_get_tool_description(tool),
        )

    # -- Handoff hooks --

    def on_handoff(
        self,
        from_agent: Any,
        to_agent: Any,
        context: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when one agent hands off to another.

        Records the handoff as an AgentStep with action="handoff" and
        tracks the handoff chain for observability.
        """
        from_name = _get_agent_name(from_agent)
        to_name = _get_agent_name(to_agent)

        self._handoff_chain.append(to_name)

        self._ctx.record_agent_action(
            action="handoff",
            agent_name=from_name,
            agent_type="openai_agents",
            action_input={
                "from_agent": from_name,
                "to_agent": to_name,
            },
            action_output=to_name,
            metadata={
                "handoff_chain": list(self._handoff_chain),
                "handoff_from": from_name,
                "handoff_to": to_name,
            },
        )

    # -- LLM response hooks --

    def on_llm_response(
        self,
        agent: Any,
        response: Any = None,
        **kwargs: Any,
    ) -> None:
        """Called when an LLM response is received (if supported by SDK version)."""
        model = _get_agent_model(agent) or "unknown"

        response_text = None
        prompt_tokens = None
        completion_tokens = None
        finish_reason = None

        if response is not None:
            response_text = _extract_llm_response_text(response)
            usage = _extract_usage(response)
            if usage:
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")
            finish_reason = _extract_finish_reason(response)

        self._ctx.record_llm_call(
            model=model,
            response=response_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            finish_reason=finish_reason,
            provider="openai",
        )


class _AgentFrame:
    """Tracks state for a currently executing agent."""

    __slots__ = ("agent_name", "step", "start_time")

    def __init__(self, agent_name: str, step: Any, start_time: float) -> None:
        self.agent_name = agent_name
        self.step = step
        self.start_time = start_time


# ---------------------------------------------------------------------------
# Attribute extraction helpers (defensive, never raise)
# ---------------------------------------------------------------------------


def _get_agent_name(agent: Any) -> str:
    """Extract agent name."""
    if agent is None:
        return "unknown"
    return getattr(agent, "name", None) or getattr(agent, "__class__", type(agent)).__name__


def _get_agent_model(agent: Any) -> str | None:
    """Extract model name from agent."""
    if agent is None:
        return None
    # OpenAI Agents SDK uses .model attribute
    model = getattr(agent, "model", None)
    if model:
        return str(model)
    # Some versions use model_settings
    settings = getattr(agent, "model_settings", None)
    if settings and hasattr(settings, "model"):
        return str(settings.model)
    return None


def _get_agent_instructions(agent: Any) -> str | None:
    """Extract agent instructions."""
    if agent is None:
        return None
    instructions = getattr(agent, "instructions", None)
    if isinstance(instructions, str):
        # Truncate long instructions
        return instructions[:500] if len(instructions) > 500 else instructions
    return None


def _get_agent_tool_names(agent: Any) -> list[str]:
    """Extract tool names from agent."""
    if agent is None:
        return []
    tools = getattr(agent, "tools", None) or []
    names = []
    for tool in tools:
        name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
        if name:
            names.append(str(name))
        else:
            names.append(type(tool).__name__)
    return names


def _get_tool_name(tool: Any) -> str:
    """Extract tool name."""
    if tool is None:
        return "unknown"
    return (
        getattr(tool, "name", None)
        or getattr(tool, "__name__", None)
        or type(tool).__name__
    )


def _get_tool_description(tool: Any) -> str | None:
    """Extract tool description."""
    if tool is None:
        return None
    return getattr(tool, "description", None)


def _normalize_tool_input(input: Any) -> Any:
    """Normalize tool input to a serializable form."""
    if input is None:
        return {}
    if isinstance(input, dict):
        return input
    if isinstance(input, str):
        return {"input": input}
    if hasattr(input, "model_dump"):
        return input.model_dump()
    if hasattr(input, "__dict__"):
        return {k: v for k, v in input.__dict__.items() if not k.startswith("_")}
    return {"input": str(input)}


def _extract_output(output: Any) -> Any:
    """Extract serializable output."""
    if output is None:
        return None
    if isinstance(output, (str, int, float, bool)):
        return output
    if isinstance(output, dict):
        return output
    if hasattr(output, "model_dump"):
        return output.model_dump()
    if hasattr(output, "final_output"):
        return _extract_output(output.final_output)
    return str(output)


def _extract_llm_response_text(response: Any) -> str | None:
    """Extract text from an LLM response."""
    if response is None:
        return None
    # OpenAI ChatCompletion style
    if hasattr(response, "choices") and response.choices:
        choice = response.choices[0]
        if hasattr(choice, "message") and hasattr(choice.message, "content"):
            return choice.message.content
    # Raw output attribute
    if hasattr(response, "output"):
        out = response.output
        if isinstance(out, str):
            return out
    return str(response)[:500]


def _extract_usage(response: Any) -> dict[str, int] | None:
    """Extract token usage from response."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
    }


def _extract_finish_reason(response: Any) -> str | None:
    """Extract finish reason from response."""
    if hasattr(response, "choices") and response.choices:
        return getattr(response.choices[0], "finish_reason", None)
    return None


# ---------------------------------------------------------------------------
# Public convenience functions
# ---------------------------------------------------------------------------


def reagent_openai_agents_hooks(context: RunContext) -> ReAgentHooks:
    """Create a ReAgentHooks instance for use with the OpenAI Agents SDK Runner.

    Usage:
        with reagent.trace(RunConfig(name="agent-run")) as ctx:
            hooks = reagent_openai_agents_hooks(ctx)
            result = await Runner.run(agent, input="Hello", run_hooks=hooks)

    Args:
        context: ReAgent run context

    Returns:
        ReAgentHooks instance to pass as run_hooks
    """
    return ReAgentHooks(context)


async def reagent_openai_agents_run(
    context: RunContext,
    agent: Any,
    input: str,
    **kwargs: Any,
) -> Any:
    """Run an OpenAI Agents SDK agent with automatic ReAgent tracing.

    Convenience wrapper that creates hooks and runs the agent.

    Usage:
        with reagent.trace(RunConfig(name="agent-run")) as ctx:
            result = await reagent_openai_agents_run(ctx, agent, "Hello")

    Args:
        context: ReAgent run context
        agent: OpenAI Agents SDK Agent instance
        input: Input string for the agent
        **kwargs: Additional kwargs passed to Runner.run()

    Returns:
        Runner result
    """
    try:
        from agents import Runner
    except ImportError:
        raise ImportError(
            "OpenAI Agents SDK is not installed. "
            "Install with: pip install openai-agents"
        )

    hooks = ReAgentHooks(context)
    result = await Runner.run(agent, input=input, run_hooks=hooks, **kwargs)

    # Record final output
    context.set_output(_extract_output(result))

    return result
