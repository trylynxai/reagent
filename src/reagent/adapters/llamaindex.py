"""LlamaIndex adapter for automatic instrumentation."""

from __future__ import annotations

import functools
import time
import traceback
from typing import TYPE_CHECKING, Any, Callable
from uuid import UUID, uuid4

from reagent.adapters.base import Adapter
from reagent.core.exceptions import AdapterError

if TYPE_CHECKING:
    from reagent.client.reagent import ReAgent
    from reagent.client.context import RunContext


class LlamaIndexAdapter(Adapter):
    """Adapter for LlamaIndex framework.

    Provides automatic instrumentation via LlamaIndex's callback system.
    Captures query engine calls, retrieval, synthesis, and LLM interactions.
    """

    def __init__(self, client: ReAgent) -> None:
        super().__init__(client)

    @property
    def name(self) -> str:
        return "llamaindex"

    @property
    def framework(self) -> str:
        return "llamaindex"

    @classmethod
    def is_available(cls) -> bool:
        """Check if LlamaIndex is installed."""
        try:
            import llama_index
            return True
        except ImportError:
            try:
                import llama_index.core
                return True
            except ImportError:
                return False

    @classmethod
    def get_framework_version(cls) -> str | None:
        """Get LlamaIndex version."""
        try:
            import llama_index.core
            return getattr(llama_index.core, "__version__", None)
        except (ImportError, AttributeError):
            try:
                import llama_index
                return getattr(llama_index, "__version__", None)
            except (ImportError, AttributeError):
                return None

    def install(self) -> None:
        """Install the adapter."""
        if not self.is_available():
            raise AdapterError("LlamaIndex is not installed")
        self._installed = True

    def uninstall(self) -> None:
        """Uninstall the adapter."""
        self._installed = False

    def reagent_llamaindex_handler(self, context: RunContext) -> ReAgentCallbackHandler:
        """Get a LlamaIndex callback handler for the given context.

        Args:
            context: Run context to record events to

        Returns:
            ReAgentCallbackHandler instance compatible with LlamaIndex's
            CallbackManager.

        Usage:
            from llama_index.core import Settings
            from llama_index.core.callbacks import CallbackManager

            handler = adapter.reagent_llamaindex_handler(context)
            Settings.callback_manager = CallbackManager([handler])
        """
        return ReAgentCallbackHandler(context)

    def reagent_llamaindex_query_engine(
        self, query_engine: Any, context: RunContext
    ) -> Any:
        """Instrument a LlamaIndex query engine.

        Wraps the query engine to capture query, retrieval, and synthesis steps.

        Args:
            query_engine: LlamaIndex query engine instance
            context: Run context to record events to

        Returns:
            Instrumented query engine wrapper
        """
        return QueryEngineWrapper(query_engine, context)

    def reagent_llamaindex_index(self, index: Any, context: RunContext) -> Any:
        """Instrument a LlamaIndex index.

        Wraps the index to capture query operations.

        Args:
            index: LlamaIndex index instance
            context: Run context to record events to

        Returns:
            Instrumented index wrapper
        """
        return IndexWrapper(index, context)


class ReAgentCallbackHandler:
    """LlamaIndex callback handler for ReAgent.

    Implements the LlamaIndex callback interface to capture events
    during query engine execution (LLM calls, retrievals, etc.).

    Compatible with both LlamaIndex v0.9.x and v0.10.x callback systems.

    Usage:
        from llama_index.core.callbacks import CallbackManager

        handler = ReAgentCallbackHandler(context)
        callback_manager = CallbackManager([handler])
    """

    def __init__(self, context: RunContext) -> None:
        self._context = context
        self._event_map: dict[str, dict[str, Any]] = {}
        self._trace_stack: list[str] = []

    def on_event_start(
        self,
        event_type: Any,
        payload: dict[str, Any] | None = None,
        event_id: str = "",
        parent_id: str = "",
        **kwargs: Any,
    ) -> str:
        """Called when an event starts.

        Args:
            event_type: The type of event (CBEventType enum or string)
            payload: Event payload data
            event_id: Unique event identifier
            parent_id: Parent event identifier

        Returns:
            The event_id
        """
        if not event_id:
            event_id = str(uuid4())

        event_type_str = str(event_type)

        self._event_map[event_id] = {
            "type": event_type_str,
            "start_time": time.time(),
            "payload": payload or {},
            "parent_id": parent_id,
        }

        return event_id

    def on_event_end(
        self,
        event_type: Any,
        payload: dict[str, Any] | None = None,
        event_id: str = "",
        **kwargs: Any,
    ) -> None:
        """Called when an event ends."""
        event_info = self._event_map.pop(event_id, None)
        if not event_info:
            return

        event_type_str = str(event_type)
        start_time = event_info.get("start_time", time.time())
        duration_ms = int((time.time() - start_time) * 1000)
        start_payload = event_info.get("payload", {})
        end_payload = payload or {}

        # Route to appropriate handler based on event type
        type_lower = event_type_str.lower()

        if "llm" in type_lower:
            self._record_llm_event(start_payload, end_payload, duration_ms)
        elif "retriev" in type_lower:
            self._record_retrieval_event(start_payload, end_payload, duration_ms)
        elif "synthe" in type_lower:
            self._record_synthesis_event(start_payload, end_payload, duration_ms)
        elif "query" in type_lower:
            self._record_query_event(start_payload, end_payload, duration_ms)
        elif "embedding" in type_lower:
            self._record_embedding_event(start_payload, end_payload, duration_ms)

    def start_trace(self, trace_id: str | None = None) -> None:
        """Called when a trace starts (top-level query)."""
        trace_id = trace_id or str(uuid4())
        self._trace_stack.append(trace_id)

    def end_trace(
        self,
        trace_id: str | None = None,
        trace_map: dict[str, list[str]] | None = None,
    ) -> None:
        """Called when a trace ends."""
        if self._trace_stack:
            self._trace_stack.pop()

    def _record_llm_event(
        self,
        start_payload: dict[str, Any],
        end_payload: dict[str, Any],
        duration_ms: int,
    ) -> None:
        """Record an LLM call event."""
        # Extract model info
        model = "unknown"
        serialized = start_payload.get("serialized", {})
        if serialized:
            model = serialized.get("model", serialized.get("model_name", "unknown"))

        # Extract messages/prompt
        messages = start_payload.get("messages", None)
        prompt = None
        messages_list = None

        if messages:
            if isinstance(messages, list):
                messages_list = []
                for msg in messages:
                    if hasattr(msg, "content"):
                        messages_list.append({
                            "role": getattr(msg, "role", "unknown"),
                            "content": msg.content,
                        })
                    elif isinstance(msg, dict):
                        messages_list.append(msg)
                    else:
                        messages_list.append({"role": "unknown", "content": str(msg)})

        template = start_payload.get("template", None)
        if template and not prompt:
            prompt = str(template)

        # Extract response
        response_text = None
        response_obj = end_payload.get("response", None)
        if response_obj:
            if hasattr(response_obj, "message"):
                msg = response_obj.message
                response_text = getattr(msg, "content", str(msg))
            elif hasattr(response_obj, "text"):
                response_text = response_obj.text
            elif isinstance(response_obj, str):
                response_text = response_obj

        # Extract token counts
        prompt_tokens = None
        completion_tokens = None
        raw = end_payload.get("raw", None)
        if raw and hasattr(raw, "usage"):
            usage = raw.usage
            prompt_tokens = getattr(usage, "prompt_tokens", None)
            completion_tokens = getattr(usage, "completion_tokens", None)

        # Also check for token counts in additional_kwargs
        additional = end_payload.get("additional_kwargs", {})
        if additional:
            if not prompt_tokens:
                prompt_tokens = additional.get("prompt_tokens")
            if not completion_tokens:
                completion_tokens = additional.get("completion_tokens")

        self._context.record_llm_call(
            model=model,
            prompt=prompt,
            messages=messages_list,
            response=response_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=duration_ms,
            provider="llamaindex",
            metadata={"event_type": "llm"},
        )

    def _record_retrieval_event(
        self,
        start_payload: dict[str, Any],
        end_payload: dict[str, Any],
        duration_ms: int,
    ) -> None:
        """Record a retrieval event."""
        query = start_payload.get("query_str", "")

        # Extract nodes/documents from response
        nodes = end_payload.get("nodes", [])
        documents = []
        scores = []

        for node in nodes:
            score = None
            doc = {}

            if hasattr(node, "node"):
                inner = node.node
                doc["page_content"] = getattr(inner, "text", str(inner))
                doc["metadata"] = getattr(inner, "metadata", {})
                score = getattr(node, "score", None)
            elif hasattr(node, "text"):
                doc["page_content"] = node.text
                doc["metadata"] = getattr(node, "metadata", {})
                score = getattr(node, "score", None)
            elif isinstance(node, dict):
                doc = node
                score = node.get("score")
            else:
                doc["page_content"] = str(node)

            documents.append(doc)
            if score is not None:
                scores.append(float(score))

        self._context.record_retrieval(
            query=query,
            documents=documents if documents else None,
            scores=scores if scores else None,
            duration_ms=duration_ms,
            metadata={"event_type": "retrieval"},
        )

    def _record_synthesis_event(
        self,
        start_payload: dict[str, Any],
        end_payload: dict[str, Any],
        duration_ms: int,
    ) -> None:
        """Record a synthesis/response generation event."""
        query = start_payload.get("query_str", "")

        response = end_payload.get("response", None)
        response_text = None
        if response:
            if hasattr(response, "response"):
                response_text = response.response
            elif isinstance(response, str):
                response_text = response
            else:
                response_text = str(response)

        self._context.record_custom(
            event_name="synthesis",
            data={
                "query": query,
                "response": response_text,
                "duration_ms": duration_ms,
            },
            metadata={"event_type": "synthesis"},
        )

    def _record_query_event(
        self,
        start_payload: dict[str, Any],
        end_payload: dict[str, Any],
        duration_ms: int,
    ) -> None:
        """Record a top-level query event."""
        query = start_payload.get("query_str", "")

        response = end_payload.get("response", None)
        response_text = None
        if response:
            if hasattr(response, "response"):
                response_text = response.response
            elif isinstance(response, str):
                response_text = response
            else:
                response_text = str(response)

        self._context.record_custom(
            event_name="query",
            data={
                "query": query,
                "response": response_text,
                "duration_ms": duration_ms,
            },
            metadata={"event_type": "query"},
        )

    def _record_embedding_event(
        self,
        start_payload: dict[str, Any],
        end_payload: dict[str, Any],
        duration_ms: int,
    ) -> None:
        """Record an embedding event."""
        chunks = start_payload.get("chunks", [])
        serialized = start_payload.get("serialized", {})
        model = serialized.get("model_name", "unknown")

        self._context.record_custom(
            event_name="embedding",
            data={
                "model": model,
                "num_chunks": len(chunks),
                "duration_ms": duration_ms,
            },
            metadata={"event_type": "embedding"},
        )


class QueryEngineWrapper:
    """Wrapper for LlamaIndex query engines that captures execution.

    Usage:
        query_engine = index.as_query_engine()
        wrapped = QueryEngineWrapper(query_engine, context)
        response = wrapped.query("What is...?")
    """

    def __init__(self, query_engine: Any, context: RunContext) -> None:
        self._engine = query_engine
        self._context = context

    def __getattr__(self, name: str) -> Any:
        return getattr(self._engine, name)

    def query(self, query: str, **kwargs: Any) -> Any:
        """Instrumented query method."""
        self._context.set_framework(
            "llamaindex",
            LlamaIndexAdapter.get_framework_version(),
        )

        chain = self._context.start_chain(
            chain_name="QueryEngine",
            chain_type="llamaindex_query",
            input={"query": query},
        )

        start_time = time.time()
        error_occurred = None
        result = None

        try:
            result = self._engine.query(query, **kwargs)
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
                if hasattr(result, "response"):
                    output = {"response": str(result.response)}
                else:
                    output = {"response": str(result)}

                # Extract source nodes if available
                source_nodes = getattr(result, "source_nodes", None)
                if source_nodes:
                    output["num_sources"] = len(source_nodes)

            self._context.end_chain(
                chain,
                output=output,
                error=str(error_occurred) if error_occurred else None,
            )

            if output and not error_occurred:
                self._context.set_output(output)

    async def aquery(self, query: str, **kwargs: Any) -> Any:
        """Instrumented async query method."""
        self._context.set_framework(
            "llamaindex",
            LlamaIndexAdapter.get_framework_version(),
        )

        chain = self._context.start_chain(
            chain_name="QueryEngine",
            chain_type="llamaindex_query_async",
            input={"query": query},
        )

        start_time = time.time()
        error_occurred = None
        result = None

        try:
            result = await self._engine.aquery(query, **kwargs)
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
                if hasattr(result, "response"):
                    output = {"response": str(result.response)}
                else:
                    output = {"response": str(result)}

            self._context.end_chain(
                chain,
                output=output,
                error=str(error_occurred) if error_occurred else None,
            )


class IndexWrapper:
    """Wrapper for LlamaIndex Index that captures query operations.

    Usage:
        index = VectorStoreIndex.from_documents(documents)
        wrapped = IndexWrapper(index, context)
        engine = wrapped.as_query_engine()
        response = engine.query("...")
    """

    def __init__(self, index: Any, context: RunContext) -> None:
        self._index = index
        self._context = context

    def __getattr__(self, name: str) -> Any:
        return getattr(self._index, name)

    def as_query_engine(self, **kwargs: Any) -> QueryEngineWrapper:
        """Create an instrumented query engine from this index."""
        engine = self._index.as_query_engine(**kwargs)
        return QueryEngineWrapper(engine, self._context)

    def as_retriever(self, **kwargs: Any) -> Any:
        """Create a retriever from this index (returns original)."""
        return self._index.as_retriever(**kwargs)


def reagent_llamaindex_query(context: RunContext) -> Callable[[Any], Any]:
    """Decorator to instrument a LlamaIndex query engine.

    Usage:
        @reagent_llamaindex_query(context)
        def get_engine():
            index = VectorStoreIndex.from_documents(docs)
            return index.as_query_engine()

        engine = get_engine()  # Returns instrumented QueryEngineWrapper
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            engine = func(*args, **kwargs)
            return QueryEngineWrapper(engine, context)

        return wrapper

    return decorator
