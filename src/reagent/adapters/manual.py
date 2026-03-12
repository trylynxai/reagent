"""Manual instrumentation decorators for custom agents."""

from __future__ import annotations

import functools
import time
import traceback
from typing import TYPE_CHECKING, Any, Callable, TypeVar, ParamSpec, overload

if TYPE_CHECKING:
    from reagent.client.context import RunContext

P = ParamSpec("P")
R = TypeVar("R")


def tool(
    context: RunContext,
    name: str | None = None,
    description: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to instrument a tool function.

    Usage:
        @tool(context, name="web_search")
        def search(query: str) -> list[str]:
            return search_engine.search(query)

    Args:
        context: Run context to record to
        name: Tool name (defaults to function name)
        description: Tool description

    Returns:
        Decorated function
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        tool_name = name or func.__name__
        tool_description = description or func.__doc__

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start_time = time.time()
            error = None
            error_type = None
            result = None

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error = str(e)
                error_type = type(e).__name__
                raise
            finally:
                duration_ms = int((time.time() - start_time) * 1000)
                context.record_tool_call(
                    tool_name=tool_name,
                    tool_description=tool_description,
                    args=args,
                    kwargs=kwargs,
                    result=result,
                    error=error,
                    error_type=error_type,
                    duration_ms=duration_ms,
                )

        return wrapper

    return decorator


def llm_call(
    context: RunContext,
    model: str | None = None,
    provider: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to instrument an LLM call function.

    Use this when you have a function that wraps LLM calls
    and you want to record them.

    Usage:
        @llm_call(context, model="gpt-4")
        def generate_text(prompt: str) -> str:
            return openai.chat.completions.create(...)

    The decorated function should return a dict with:
    - response: The LLM response text
    - prompt_tokens: (optional) Input token count
    - completion_tokens: (optional) Output token count
    - cost_usd: (optional) Cost estimate

    Or just the response text.

    Args:
        context: Run context to record to
        model: Model name
        provider: Provider name

    Returns:
        Decorated function
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start_time = time.time()
            error = None
            result = None

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                duration_ms = int((time.time() - start_time) * 1000)

                # Extract result details
                response = None
                prompt_tokens = None
                completion_tokens = None
                cost_usd = None
                actual_model = model

                if isinstance(result, dict):
                    response = result.get("response")
                    prompt_tokens = result.get("prompt_tokens")
                    completion_tokens = result.get("completion_tokens")
                    cost_usd = result.get("cost_usd")
                    actual_model = result.get("model", model)
                elif result is not None:
                    response = str(result)

                # Try to extract prompt from args
                prompt = None
                if args:
                    prompt = str(args[0])
                elif "prompt" in kwargs:
                    prompt = str(kwargs["prompt"])
                elif "messages" in kwargs:
                    prompt = str(kwargs["messages"])

                context.record_llm_call(
                    model=actual_model or "unknown",
                    provider=provider,
                    prompt=prompt,
                    response=response,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=cost_usd,
                    duration_ms=duration_ms,
                    error=error,
                )

        return wrapper

    return decorator


def chain(
    context: RunContext,
    name: str | None = None,
    chain_type: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to instrument a chain/pipeline function.

    Usage:
        @chain(context, name="qa_chain")
        def answer_question(question: str) -> str:
            # Chain steps here
            return answer

    Args:
        context: Run context to record to
        name: Chain name (defaults to function name)
        chain_type: Type of chain

    Returns:
        Decorated function
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        chain_name = name or func.__name__

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # Start chain
            step = context.start_chain(
                chain_name=chain_name,
                chain_type=chain_type,
                input={"args": args, "kwargs": kwargs},
            )

            error = None
            result = None

            try:
                # Run with nesting
                with context.nest(step.step_id):
                    result = func(*args, **kwargs)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                # End chain
                output = {"result": result} if result is not None else None
                context.end_chain(step, output=output, error=error)

        return wrapper

    return decorator


def agent_action(
    context: RunContext,
    agent_name: str | None = None,
    agent_type: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to instrument an agent action function.

    Usage:
        @agent_action(context, agent_name="researcher")
        def research(topic: str) -> dict:
            # Agent action here
            return {"result": findings, "thought": reasoning}

    The decorated function can return:
    - A dict with "result", "thought", and/or "action" keys
    - Or just the result value

    Args:
        context: Run context to record to
        agent_name: Name of the agent
        agent_type: Type of agent

    Returns:
        Decorated function
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        action_name = func.__name__

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start_time = time.time()
            error = None
            result = None

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                duration_ms = int((time.time() - start_time) * 1000)

                # Extract result details
                action_output = None
                thought = None

                if isinstance(result, dict):
                    action_output = result.get("result", result)
                    thought = result.get("thought")
                else:
                    action_output = result

                context.record_agent_action(
                    action=action_name,
                    action_input={"args": args, "kwargs": kwargs},
                    action_output=action_output,
                    thought=thought,
                    agent_name=agent_name,
                    agent_type=agent_type,
                    duration_ms=duration_ms,
                    error=error,
                )

        return wrapper

    return decorator


def custom_event(
    context: RunContext,
    event_name: str,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to record a custom event.

    Usage:
        @custom_event(context, "preprocessing")
        def preprocess(data: dict) -> dict:
            # Processing here
            return processed_data

    Args:
        context: Run context to record to
        event_name: Name of the custom event

    Returns:
        Decorated function
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start_time = time.time()
            error = None
            result = None

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                duration_ms = int((time.time() - start_time) * 1000)

                context.record_custom(
                    event_name=event_name,
                    data={
                        "args": str(args),
                        "kwargs": str(kwargs),
                        "result": str(result) if result is not None else None,
                        "error": error,
                        "duration_ms": duration_ms,
                    },
                )

        return wrapper

    return decorator
