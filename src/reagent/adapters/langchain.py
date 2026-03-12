"""LangChain adapter for automatic instrumentation."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from reagent.adapters.base import Adapter
from reagent.core.exceptions import AdapterError

if TYPE_CHECKING:
    from reagent.client.reagent import ReAgent
    from reagent.client.context import RunContext


class LangChainAdapter(Adapter):
    """Adapter for LangChain framework.

    Provides automatic instrumentation via LangChain's callback system.
    Supports chains, agents, LLM calls, and tool calls.
    """

    @property
    def name(self) -> str:
        return "langchain"

    @property
    def framework(self) -> str:
        return "langchain"

    @classmethod
    def is_available(cls) -> bool:
        """Check if LangChain is installed."""
        try:
            import langchain
            return True
        except ImportError:
            return False

    @classmethod
    def get_framework_version(cls) -> str | None:
        """Get LangChain version."""
        try:
            import langchain
            return langchain.__version__
        except (ImportError, AttributeError):
            return None

    def install(self) -> None:
        """Install the adapter (no-op, use get_callback_handler instead)."""
        self._installed = True

    def uninstall(self) -> None:
        """Uninstall the adapter."""
        self._installed = False

    def get_callback_handler(self, context: RunContext) -> Any:
        """Get a LangChain callback handler for the given context.

        Args:
            context: Run context to record events to

        Returns:
            LangChain BaseCallbackHandler instance
        """
        if not self.is_available():
            raise AdapterError("LangChain is not installed")

        return ReAgentCallbackHandler(context)


class ReAgentCallbackHandler:
    """LangChain callback handler for ReAgent.

    Implements the LangChain callback interface to capture
    all events during chain/agent execution.

    Usage:
        handler = ReAgentCallbackHandler(context)
        chain.run(query, callbacks=[handler])
    """

    def __init__(self, context: RunContext) -> None:
        """Initialize the callback handler.

        Args:
            context: Run context to record events to
        """
        self._context = context
        self._run_map: dict[UUID, dict[str, Any]] = {}

    # LLM Callbacks

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM starts running."""
        self._run_map[run_id] = {
            "type": "llm",
            "start_time": time.time(),
            "prompts": prompts,
            "serialized": serialized,
            "parent_run_id": parent_run_id,
            "tags": tags,
            "metadata": metadata,
        }

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM finishes running."""
        run_info = self._run_map.pop(run_id, {})
        start_time = run_info.get("start_time", time.time())
        duration_ms = int((time.time() - start_time) * 1000)

        # Extract model info
        serialized = run_info.get("serialized", {})
        model = serialized.get("kwargs", {}).get("model_name", "unknown")

        # Extract response
        generations = response.generations if hasattr(response, "generations") else []
        response_text = ""
        if generations and generations[0]:
            response_text = generations[0][0].text if hasattr(generations[0][0], "text") else str(generations[0][0])

        # Extract token usage
        llm_output = response.llm_output if hasattr(response, "llm_output") else {}
        token_usage = llm_output.get("token_usage", {}) if llm_output else {}
        prompt_tokens = token_usage.get("prompt_tokens", 0)
        completion_tokens = token_usage.get("completion_tokens", 0)

        # Record the LLM call
        prompts = run_info.get("prompts", [])
        prompt = prompts[0] if prompts else None

        self._context.record_llm_call(
            model=model,
            prompt=prompt,
            response=response_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=duration_ms,
            metadata={
                "langchain_run_id": str(run_id),
                "tags": run_info.get("tags"),
            },
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM errors."""
        run_info = self._run_map.pop(run_id, {})
        start_time = run_info.get("start_time", time.time())
        duration_ms = int((time.time() - start_time) * 1000)

        serialized = run_info.get("serialized", {})
        model = serialized.get("kwargs", {}).get("model_name", "unknown")

        self._context.record_llm_call(
            model=model,
            prompt=run_info.get("prompts", [None])[0],
            error=str(error),
            duration_ms=duration_ms,
            metadata={"langchain_run_id": str(run_id)},
        )

    # Chat Model Callbacks

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when chat model starts running."""
        # Convert messages to dicts
        messages_dicts = []
        for msg_list in messages:
            for msg in msg_list:
                if hasattr(msg, "dict"):
                    messages_dicts.append(msg.dict())
                elif hasattr(msg, "content"):
                    messages_dicts.append({
                        "role": getattr(msg, "type", "unknown"),
                        "content": msg.content,
                    })

        self._run_map[run_id] = {
            "type": "chat",
            "start_time": time.time(),
            "messages": messages_dicts,
            "serialized": serialized,
            "parent_run_id": parent_run_id,
            "tags": tags,
            "metadata": metadata,
        }

    # Tool Callbacks

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when tool starts running."""
        self._run_map[run_id] = {
            "type": "tool",
            "start_time": time.time(),
            "input": input_str,
            "serialized": serialized,
            "parent_run_id": parent_run_id,
            "tags": tags,
            "metadata": metadata,
        }

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when tool finishes running."""
        run_info = self._run_map.pop(run_id, {})
        start_time = run_info.get("start_time", time.time())
        duration_ms = int((time.time() - start_time) * 1000)

        serialized = run_info.get("serialized", {})
        tool_name = serialized.get("name", "unknown")

        self._context.record_tool_call(
            tool_name=tool_name,
            kwargs={"input": run_info.get("input")},
            result=output,
            duration_ms=duration_ms,
            metadata={
                "langchain_run_id": str(run_id),
                "tags": run_info.get("tags"),
            },
        )

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when tool errors."""
        run_info = self._run_map.pop(run_id, {})
        start_time = run_info.get("start_time", time.time())
        duration_ms = int((time.time() - start_time) * 1000)

        serialized = run_info.get("serialized", {})
        tool_name = serialized.get("name", "unknown")

        self._context.record_tool_call(
            tool_name=tool_name,
            kwargs={"input": run_info.get("input")},
            error=str(error),
            error_type=type(error).__name__,
            duration_ms=duration_ms,
            metadata={"langchain_run_id": str(run_id)},
        )

    # Chain Callbacks

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when chain starts running."""
        chain_name = serialized.get("name", serialized.get("id", ["unknown"])[-1])

        self._run_map[run_id] = {
            "type": "chain",
            "start_time": time.time(),
            "inputs": inputs,
            "serialized": serialized,
            "chain_name": chain_name,
            "parent_run_id": parent_run_id,
            "tags": tags,
            "metadata": metadata,
        }

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when chain finishes running."""
        run_info = self._run_map.pop(run_id, {})
        # Chains are tracked but not recorded as individual steps
        # to avoid noise - LLM and tool calls within are recorded

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when chain errors."""
        run_info = self._run_map.pop(run_id, {})

        self._context.record_error(
            error_message=str(error),
            error_type=type(error).__name__,
            metadata={
                "langchain_run_id": str(run_id),
                "chain_name": run_info.get("chain_name"),
            },
        )

    # Agent Callbacks

    def on_agent_action(
        self,
        action: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when agent takes an action."""
        tool = action.tool if hasattr(action, "tool") else str(action)
        tool_input = action.tool_input if hasattr(action, "tool_input") else None
        log = action.log if hasattr(action, "log") else None

        self._context.record_agent_action(
            action=tool,
            action_input={"input": tool_input} if tool_input else None,
            thought=log,
            metadata={"langchain_run_id": str(run_id)},
        )

    def on_agent_finish(
        self,
        finish: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when agent finishes."""
        return_values = finish.return_values if hasattr(finish, "return_values") else {}
        log = finish.log if hasattr(finish, "log") else None

        output = return_values.get("output") if isinstance(return_values, dict) else return_values

        self._context.record_agent_finish(
            final_answer=output,
            thought=log,
            metadata={"langchain_run_id": str(run_id)},
        )

    # Retriever Callbacks

    def on_retriever_start(
        self,
        serialized: dict[str, Any],
        query: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when retriever starts running."""
        self._run_map[run_id] = {
            "type": "retriever",
            "start_time": time.time(),
            "query": query,
            "serialized": serialized,
            "parent_run_id": parent_run_id,
            "tags": tags,
            "metadata": metadata,
        }

    def on_retriever_end(
        self,
        documents: list[Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when retriever finishes running."""
        run_info = self._run_map.pop(run_id, {})
        start_time = run_info.get("start_time", time.time())
        duration_ms = int((time.time() - start_time) * 1000)

        # Convert documents to dicts
        docs = []
        for doc in documents:
            if hasattr(doc, "dict"):
                docs.append(doc.dict())
            elif hasattr(doc, "page_content"):
                docs.append({
                    "page_content": doc.page_content,
                    "metadata": getattr(doc, "metadata", {}),
                })
            else:
                docs.append({"content": str(doc)})

        self._context.record_retrieval(
            query=run_info.get("query", ""),
            documents=docs,
            duration_ms=duration_ms,
            metadata={
                "langchain_run_id": str(run_id),
                "tags": run_info.get("tags"),
            },
        )

    def on_retriever_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when retriever errors."""
        run_info = self._run_map.pop(run_id, {})

        self._context.record_retrieval(
            query=run_info.get("query", ""),
            error=str(error),
            metadata={"langchain_run_id": str(run_id)},
        )
