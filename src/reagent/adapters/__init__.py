"""Adapters module - Framework integrations for automatic instrumentation."""

from reagent.adapters.base import Adapter, AdapterRegistry
from reagent.adapters.manual import tool, llm_call, chain, agent_action

__all__ = [
    "Adapter",
    "AdapterRegistry",
    "tool",
    "llm_call",
    "chain",
    "agent_action",
]

# Lazy imports for framework-specific adapters
def get_langchain_adapter() -> type:
    """Get the LangChain adapter (lazy import)."""
    from reagent.adapters.langchain import LangChainAdapter
    return LangChainAdapter


def get_openai_adapter() -> type:
    """Get the OpenAI adapter (lazy import)."""
    from reagent.adapters.openai import OpenAIAdapter
    return OpenAIAdapter
