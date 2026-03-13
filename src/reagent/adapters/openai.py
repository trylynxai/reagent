"""OpenAI adapter for automatic instrumentation."""

from __future__ import annotations

import functools
import time
from typing import TYPE_CHECKING, Any, Callable

from reagent.adapters.base import Adapter
from reagent.core.exceptions import AdapterError

if TYPE_CHECKING:
    from reagent.client.reagent import ReAgent
    from reagent.client.context import RunContext


class OpenAIAdapter(Adapter):
    """Adapter for OpenAI SDK.

    Provides automatic instrumentation by wrapping the OpenAI client.
    """

    def __init__(self, client: ReAgent) -> None:
        super().__init__(client)
        self._original_create: Callable[..., Any] | None = None
        self._original_acreate: Callable[..., Any] | None = None
        self._openai_client: Any = None

    @property
    def name(self) -> str:
        return "openai"

    @property
    def framework(self) -> str:
        return "openai"

    @classmethod
    def is_available(cls) -> bool:
        """Check if OpenAI SDK is installed."""
        try:
            import openai
            return True
        except ImportError:
            return False

    @classmethod
    def get_framework_version(cls) -> str | None:
        """Get OpenAI SDK version."""
        try:
            import openai
            return openai.__version__
        except (ImportError, AttributeError):
            return None

    def install(self) -> None:
        """Install the adapter (patches OpenAI client)."""
        if not self.is_available():
            raise AdapterError("OpenAI SDK is not installed")

        # Note: In practice, you would patch at module level
        # Here we provide a wrapper approach instead
        self._installed = True

    def uninstall(self) -> None:
        """Uninstall the adapter."""
        self._installed = False

    def reagent_openai_client(self, openai_client: Any, context: RunContext) -> Any:
        """Instrument an OpenAI client to capture calls.

        Args:
            openai_client: OpenAI client instance
            context: Run context to record events to

        Returns:
            Instrumented client
        """
        return OpenAIClientWrapper(openai_client, context)


class OpenAIClientWrapper:
    """Wrapper for OpenAI client that captures calls.

    Usage:
        client = OpenAI()
        wrapped = OpenAIClientWrapper(client, context)
        response = wrapped.chat.completions.create(...)
    """

    def __init__(self, client: Any, context: RunContext) -> None:
        self._client = client
        self._context = context
        self.chat = ChatWrapper(client.chat, context)


class ChatWrapper:
    """Wrapper for client.chat namespace."""

    def __init__(self, chat: Any, context: RunContext) -> None:
        self._chat = chat
        self._context = context
        self.completions = CompletionsWrapper(chat.completions, context)


class CompletionsWrapper:
    """Wrapper for client.chat.completions namespace."""

    def __init__(self, completions: Any, context: RunContext) -> None:
        self._completions = completions
        self._context = context

    def create(self, **kwargs: Any) -> Any:
        """Wrapped chat.completions.create() method."""
        start_time = time.time()
        error = None
        response = None

        try:
            response = self._completions.create(**kwargs)
            return response
        except Exception as e:
            error = e
            raise
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            self._record_call(kwargs, response, error, duration_ms)

    async def acreate(self, **kwargs: Any) -> Any:
        """Wrapped async chat.completions.create() method."""
        start_time = time.time()
        error = None
        response = None

        try:
            response = await self._completions.acreate(**kwargs)
            return response
        except Exception as e:
            error = e
            raise
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            self._record_call(kwargs, response, error, duration_ms)

    def _record_call(
        self,
        request: dict[str, Any],
        response: Any,
        error: Exception | None,
        duration_ms: int,
    ) -> None:
        """Record the LLM call."""
        model = request.get("model", "unknown")
        messages = request.get("messages", [])
        temperature = request.get("temperature")
        max_tokens = request.get("max_tokens")

        # Build prompt from messages
        prompt = None
        if messages:
            prompt = "\n".join(
                f"{m.get('role', 'unknown')}: {m.get('content', '')}"
                for m in messages
            )

        # Extract response
        response_text = None
        prompt_tokens = None
        completion_tokens = None
        finish_reason = None

        if response and not error:
            if hasattr(response, "choices") and response.choices:
                choice = response.choices[0]
                if hasattr(choice, "message"):
                    response_text = choice.message.content
                finish_reason = getattr(choice, "finish_reason", None)

            if hasattr(response, "usage"):
                usage = response.usage
                prompt_tokens = getattr(usage, "prompt_tokens", None)
                completion_tokens = getattr(usage, "completion_tokens", None)

        # Calculate cost estimate
        cost_usd = None
        if prompt_tokens and completion_tokens:
            cost_usd = self._estimate_cost(model, prompt_tokens, completion_tokens)

        self._context.record_llm_call(
            model=model,
            prompt=prompt,
            messages=messages,
            response=response_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            provider="openai",
            temperature=temperature,
            max_tokens=max_tokens,
            finish_reason=finish_reason,
            error=str(error) if error else None,
            raw_request=request,
            raw_response=response.model_dump() if response and hasattr(response, "model_dump") else None,
        )

    def _estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost using the centralized pricing database."""
        from reagent.analysis.cost import estimate_cost

        return estimate_cost(model, prompt_tokens, completion_tokens)


def reagent_openai_call(context: RunContext) -> Callable[[Any], Any]:
    """Decorator to instrument an OpenAI client.

    Usage:
        @reagent_openai_call(context)
        def get_client():
            return OpenAI()

        client = get_client()
        # client is now instrumented with ReAgent
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            client = func(*args, **kwargs)
            return OpenAIClientWrapper(client, context)

        return wrapper

    return decorator
