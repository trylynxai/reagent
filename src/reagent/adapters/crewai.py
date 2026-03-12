"""CrewAI adapter for automatic instrumentation."""

from __future__ import annotations

import functools
import time
import traceback
from typing import TYPE_CHECKING, Any, Callable

from reagent.adapters.base import Adapter
from reagent.core.exceptions import AdapterError

if TYPE_CHECKING:
    from reagent.client.reagent import ReAgent
    from reagent.client.context import RunContext


class CrewAIAdapter(Adapter):
    """Adapter for CrewAI framework.

    Provides automatic instrumentation by wrapping CrewAI's
    Crew, Agent, and Task objects to capture execution events.
    """

    def __init__(self, client: ReAgent) -> None:
        super().__init__(client)

    @property
    def name(self) -> str:
        return "crewai"

    @property
    def framework(self) -> str:
        return "crewai"

    @classmethod
    def is_available(cls) -> bool:
        """Check if CrewAI is installed."""
        try:
            import crewai
            return True
        except ImportError:
            return False

    @classmethod
    def get_framework_version(cls) -> str | None:
        """Get CrewAI version."""
        try:
            import crewai
            return getattr(crewai, "__version__", None)
        except (ImportError, AttributeError):
            return None

    def install(self) -> None:
        """Install the adapter."""
        if not self.is_available():
            raise AdapterError("CrewAI is not installed")
        self._installed = True

    def uninstall(self) -> None:
        """Uninstall the adapter."""
        self._installed = False

    def reagent_crewai_crew(self, crew: Any, context: RunContext) -> Any:
        """Instrument a CrewAI Crew to capture execution.

        Wraps the crew's kickoff method to record all task executions,
        agent actions, tool calls, and LLM interactions.

        Args:
            crew: CrewAI Crew instance
            context: Run context to record events to

        Returns:
            Instrumented Crew instance
        """
        return CrewWrapper(crew, context)

    def reagent_crewai_agent(self, agent: Any, context: RunContext) -> Any:
        """Instrument a single CrewAI Agent.

        Args:
            agent: CrewAI Agent instance
            context: Run context to record events to

        Returns:
            Instrumented Agent wrapper
        """
        return AgentWrapper(agent, context)

    def reagent_crewai_task(self, task: Any, context: RunContext) -> Any:
        """Instrument a single CrewAI Task.

        Args:
            task: CrewAI Task instance
            context: Run context to record events to

        Returns:
            Instrumented Task wrapper
        """
        return TaskWrapper(task, context)


class CrewWrapper:
    """Wrapper for CrewAI Crew that captures execution events.

    Usage:
        from crewai import Crew, Agent, Task
        crew = Crew(agents=[...], tasks=[...])
        wrapped = CrewWrapper(crew, context)
        result = wrapped.kickoff()
    """

    def __init__(self, crew: Any, context: RunContext) -> None:
        self._crew = crew
        self._context = context

    def __getattr__(self, name: str) -> Any:
        """Proxy attribute access to the underlying crew."""
        return getattr(self._crew, name)

    def kickoff(self, inputs: dict[str, Any] | None = None) -> Any:
        """Instrumented kickoff that records the full crew execution."""
        self._context.set_framework("crewai", self._get_version())

        # Record crew-level metadata
        agents = getattr(self._crew, "agents", [])
        tasks = getattr(self._crew, "tasks", [])
        process = getattr(self._crew, "process", None)

        self._context.set_metadata("crew_agents", [
            getattr(a, "role", str(a)) for a in agents
        ])
        self._context.set_metadata("crew_tasks", [
            getattr(t, "description", str(t))[:100] for t in tasks
        ])
        if process:
            self._context.set_metadata("crew_process", str(process))

        # Start a chain for the full crew execution
        chain = self._context.start_chain(
            chain_name="CrewExecution",
            chain_type=str(process) if process else "sequential",
            input=inputs or {},
        )

        start_time = time.time()
        error_occurred = None
        result = None

        try:
            # Wrap agents' tools to capture tool calls
            self._instrument_agents(agents)

            # Execute the crew
            if inputs:
                result = self._crew.kickoff(inputs=inputs)
            else:
                result = self._crew.kickoff()

            return result
        except Exception as e:
            error_occurred = e
            self._context.record_error(
                error_message=str(e),
                error_type=type(e).__name__,
                error_traceback=traceback.format_exc(),
            )
            raise
        finally:
            duration_ms = int((time.time() - start_time) * 1000)

            # Record result
            output = None
            if result is not None:
                if hasattr(result, "raw"):
                    output = {"raw": result.raw}
                elif isinstance(result, str):
                    output = {"result": result}
                else:
                    output = {"result": str(result)}

            self._context.end_chain(
                chain,
                output=output,
                error=str(error_occurred) if error_occurred else None,
            )

            if output and not error_occurred:
                self._context.set_output(output)

    def _instrument_agents(self, agents: list[Any]) -> None:
        """Wrap agent tools to capture tool executions."""
        for agent in agents:
            tools = getattr(agent, "tools", None)
            if not tools:
                continue

            wrapped_tools = []
            for tool_obj in tools:
                wrapped_tools.append(
                    _wrap_crewai_tool(tool_obj, self._context)
                )
            agent.tools = wrapped_tools

    def _get_version(self) -> str | None:
        """Get CrewAI version."""
        try:
            import crewai
            return getattr(crewai, "__version__", None)
        except ImportError:
            return None


class AgentWrapper:
    """Wrapper for a single CrewAI Agent."""

    def __init__(self, agent: Any, context: RunContext) -> None:
        self._agent = agent
        self._context = context

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)

    def execute_task(self, task: Any, context: str | None = None, tools: list[Any] | None = None) -> Any:
        """Instrumented task execution."""
        agent_name = getattr(self._agent, "role", "unknown")
        agent_goal = getattr(self._agent, "goal", None)
        task_desc = getattr(task, "description", str(task))

        start_time = time.time()
        error_occurred = None
        result = None

        # Record agent action (starting task)
        self._context.record_agent_action(
            action="execute_task",
            action_input={"task": task_desc[:500], "context": context},
            agent_name=agent_name,
            agent_type="crewai",
            metadata={"goal": agent_goal} if agent_goal else None,
        )

        try:
            result = self._agent.execute_task(task, context=context, tools=tools)
            return result
        except Exception as e:
            error_occurred = e
            self._context.record_error(
                error_message=str(e),
                error_type=type(e).__name__,
                error_traceback=traceback.format_exc(),
                metadata={"agent": agent_name},
            )
            raise
        finally:
            duration_ms = int((time.time() - start_time) * 1000)

            if result is not None and not error_occurred:
                output = str(result)[:1000] if result else None
                self._context.record_agent_finish(
                    final_answer=output,
                    agent_name=agent_name,
                    duration_ms=duration_ms,
                )


class TaskWrapper:
    """Wrapper for a single CrewAI Task."""

    def __init__(self, task: Any, context: RunContext) -> None:
        self._task = task
        self._context = context

    def __getattr__(self, name: str) -> Any:
        return getattr(self._task, name)

    def execute(self, agent: Any = None, context: str | None = None, tools: list[Any] | None = None) -> Any:
        """Instrumented task execution."""
        task_desc = getattr(self._task, "description", str(self._task))
        expected_output = getattr(self._task, "expected_output", None)
        agent_name = getattr(agent, "role", "unknown") if agent else "unknown"

        chain = self._context.start_chain(
            chain_name=f"Task: {task_desc[:80]}",
            chain_type="crewai_task",
            input={
                "description": task_desc,
                "expected_output": expected_output,
                "agent": agent_name,
            },
        )

        start_time = time.time()
        error_occurred = None
        result = None

        try:
            result = self._task.execute(agent=agent, context=context, tools=tools)
            return result
        except Exception as e:
            error_occurred = e
            self._context.record_error(
                error_message=str(e),
                error_type=type(e).__name__,
                error_traceback=traceback.format_exc(),
            )
            raise
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            output = None
            if result is not None:
                output = {"result": str(result)[:1000]}

            self._context.end_chain(
                chain,
                output=output,
                error=str(error_occurred) if error_occurred else None,
            )


class _ToolProxy:
    """Proxy for a CrewAI tool that captures invocations."""

    def __init__(self, tool: Any, context: RunContext) -> None:
        self._tool = tool
        self._context = context

    def __getattr__(self, name: str) -> Any:
        return getattr(self._tool, name)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        """Instrumented tool._run()."""
        tool_name = getattr(self._tool, "name", type(self._tool).__name__)
        tool_desc = getattr(self._tool, "description", None)

        start_time = time.time()
        error_occurred = None
        result = None

        try:
            result = self._tool._run(*args, **kwargs)
            return result
        except Exception as e:
            error_occurred = e
            raise
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            self._context.record_tool_call(
                tool_name=tool_name,
                args=args if args else None,
                kwargs=kwargs if kwargs else None,
                result=str(result)[:2000] if result is not None else None,
                error=str(error_occurred) if error_occurred else None,
                error_type=type(error_occurred).__name__ if error_occurred else None,
                duration_ms=duration_ms,
                tool_description=tool_desc,
            )

    def run(self, *args: Any, **kwargs: Any) -> Any:
        """Instrumented tool.run()."""
        tool_name = getattr(self._tool, "name", type(self._tool).__name__)
        tool_desc = getattr(self._tool, "description", None)

        start_time = time.time()
        error_occurred = None
        result = None

        try:
            result = self._tool.run(*args, **kwargs)
            return result
        except Exception as e:
            error_occurred = e
            raise
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            self._context.record_tool_call(
                tool_name=tool_name,
                args=args if args else None,
                kwargs=kwargs if kwargs else None,
                result=str(result)[:2000] if result is not None else None,
                error=str(error_occurred) if error_occurred else None,
                error_type=type(error_occurred).__name__ if error_occurred else None,
                duration_ms=duration_ms,
                tool_description=tool_desc,
            )


def _wrap_crewai_tool(tool: Any, context: RunContext) -> Any:
    """Wrap a CrewAI tool to capture invocations.

    Handles both BaseTool subclasses and @tool decorated functions.
    """
    return _ToolProxy(tool, context)


def reagent_crewai_kickoff(context: RunContext) -> Callable[[Any], Any]:
    """Decorator to instrument a CrewAI Crew's kickoff.

    Usage:
        @reagent_crewai_kickoff(context)
        def get_crew():
            return Crew(agents=[...], tasks=[...])

        crew = get_crew()  # Returns instrumented CrewWrapper
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            crew = func(*args, **kwargs)
            return CrewWrapper(crew, context)

        return wrapper

    return decorator
