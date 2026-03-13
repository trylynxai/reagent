"""Tests for the OpenAI Agents SDK adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from reagent.adapters.openai_agents import (
    OpenAIAgentsAdapter,
    ReAgentHooks,
    _extract_output,
    _get_agent_instructions,
    _get_agent_model,
    _get_agent_name,
    _get_agent_tool_names,
    _get_tool_name,
    _normalize_tool_input,
    reagent_openai_agents_hooks,
)
from reagent.client.context import RunContext
from reagent.core.constants import Status
from reagent.schema.run import RunConfig, RunMetadata
from reagent.schema.steps import AgentStep, ToolCallStep, LLMCallStep
from reagent.storage.memory import MemoryStorage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_context() -> tuple[RunContext, MemoryStorage]:
    """Create a RunContext backed by MemoryStorage for testing."""
    storage = MemoryStorage()

    # Create a minimal mock client that records to MemoryStorage
    client = MagicMock()
    client.config = MagicMock()
    client.config.project = "test"

    def start_run(run_id, metadata):
        storage.save_run(run_id, metadata)

    def end_run(run_id, metadata):
        storage.save_run(run_id, metadata)

    def record_step(run_id, step):
        storage.save_step(run_id, step)

    client._start_run = start_run
    client._end_run = end_run
    client._record_step = record_step

    ctx = RunContext(client, config=RunConfig(name="test-run", project="test"))
    ctx._start()
    return ctx, storage


def _mock_agent(
    name: str = "TestAgent",
    model: str = "gpt-4o",
    instructions: str = "You are helpful.",
    tools: list[Any] | None = None,
) -> MagicMock:
    """Create a mock OpenAI Agents SDK Agent."""
    agent = MagicMock()
    agent.name = name
    agent.model = model
    agent.instructions = instructions
    agent.tools = tools or []
    return agent


def _mock_tool(name: str = "search", description: str = "Search the web") -> MagicMock:
    """Create a mock tool."""
    tool = MagicMock()
    tool.name = name
    tool.description = description
    return tool


# ---------------------------------------------------------------------------
# TestOpenAIAgentsAdapter
# ---------------------------------------------------------------------------


class TestOpenAIAgentsAdapter:
    def test_name(self):
        adapter = OpenAIAgentsAdapter.__new__(OpenAIAgentsAdapter)
        assert adapter.name == "openai_agents"

    def test_framework(self):
        adapter = OpenAIAgentsAdapter.__new__(OpenAIAgentsAdapter)
        assert adapter.framework == "openai_agents"

    def test_is_available_false_when_not_installed(self):
        with patch.dict("sys.modules", {"agents": None}):
            assert OpenAIAgentsAdapter.is_available() is False

    def test_get_framework_version_none_when_not_installed(self):
        with patch.dict("sys.modules", {"agents": None}):
            assert OpenAIAgentsAdapter.get_framework_version() is None


# ---------------------------------------------------------------------------
# TestReAgentHooks
# ---------------------------------------------------------------------------


class TestReAgentHooks:
    def setup_method(self):
        self.ctx, self.storage = _make_context()
        self.hooks = ReAgentHooks(self.ctx)

    def test_framework_set(self):
        assert self.ctx.metadata.framework == "openai_agents"

    def test_agent_start_records_step(self):
        agent = _mock_agent(name="MyAgent", model="gpt-4o")
        self.hooks.on_agent_start(agent)

        steps = list(self.storage.load_steps(self.ctx.run_id))
        assert len(steps) == 1
        step = steps[0]
        assert isinstance(step, AgentStep)
        assert step.agent_name == "MyAgent"
        assert step.agent_type == "openai_agents"
        assert step.action == "start"
        assert step.action_input["model"] == "gpt-4o"

    def test_agent_start_sets_model(self):
        agent = _mock_agent(model="gpt-4o-mini")
        self.hooks.on_agent_start(agent)
        assert self.ctx.metadata.model == "gpt-4o-mini"

    def test_agent_end_records_finish(self):
        agent = _mock_agent(name="MyAgent")
        self.hooks.on_agent_start(agent)
        self.hooks.on_agent_end(agent, output="Done!")

        steps = list(self.storage.load_steps(self.ctx.run_id))
        assert len(steps) == 2
        finish_step = steps[1]
        assert isinstance(finish_step, AgentStep)
        assert finish_step.action == "finish"
        assert finish_step.final_answer == "Done!"

    def test_agent_nesting(self):
        """Steps recorded between agent_start and agent_end should be children."""
        agent = _mock_agent(name="Parent")
        self.hooks.on_agent_start(agent)

        # The start step's ID should be on the nesting stack
        start_step_id = self.ctx._step_stack[-1]

        # Record a tool call inside the agent
        tool = _mock_tool(name="calculator")
        self.hooks.on_tool_start(agent, tool, input={"expr": "1+1"})
        self.hooks.on_tool_end(agent, tool, input={"expr": "1+1"}, output="2")

        steps = list(self.storage.load_steps(self.ctx.run_id))
        tool_step = steps[1]
        assert isinstance(tool_step, ToolCallStep)
        assert tool_step.parent_step_id == start_step_id

        self.hooks.on_agent_end(agent, output="2")

    def test_tool_call_records_step(self):
        agent = _mock_agent()
        tool = _mock_tool(name="web_search", description="Search the web")

        self.hooks.on_tool_start(agent, tool, input={"query": "weather"})
        self.hooks.on_tool_end(
            agent, tool,
            input={"query": "weather"},
            output="Sunny, 72F",
        )

        steps = list(self.storage.load_steps(self.ctx.run_id))
        assert len(steps) == 1
        step = steps[0]
        assert isinstance(step, ToolCallStep)
        assert step.tool_name == "web_search"
        assert step.output.result == "Sunny, 72F"
        assert step.success is True
        assert step.duration_ms is not None

    def test_tool_call_with_error(self):
        agent = _mock_agent()
        tool = _mock_tool(name="web_search")

        self.hooks.on_tool_start(agent, tool)
        self.hooks.on_tool_end(
            agent, tool,
            error=RuntimeError("Network timeout"),
        )

        steps = list(self.storage.load_steps(self.ctx.run_id))
        step = steps[0]
        assert isinstance(step, ToolCallStep)
        assert step.success is False
        assert "Network timeout" in step.output.error

    def test_handoff_records_step(self):
        triage = _mock_agent(name="TriageAgent")
        billing = _mock_agent(name="BillingAgent")

        self.hooks.on_handoff(triage, billing)

        steps = list(self.storage.load_steps(self.ctx.run_id))
        assert len(steps) == 1
        step = steps[0]
        assert isinstance(step, AgentStep)
        assert step.action == "handoff"
        assert step.agent_name == "TriageAgent"
        assert step.action_input["from_agent"] == "TriageAgent"
        assert step.action_input["to_agent"] == "BillingAgent"
        assert step.action_output == "BillingAgent"

    def test_handoff_chain_tracking(self):
        triage = _mock_agent(name="Triage")
        billing = _mock_agent(name="Billing")
        refund = _mock_agent(name="Refund")

        self.hooks.on_handoff(triage, billing)
        self.hooks.on_handoff(billing, refund)

        assert self.hooks._handoff_chain == ["Billing", "Refund"]

        steps = list(self.storage.load_steps(self.ctx.run_id))
        second_handoff = steps[1]
        assert second_handoff.metadata["handoff_chain"] == ["Billing", "Refund"]

    def test_llm_response_records_step(self):
        agent = _mock_agent(model="gpt-4o")

        # Mock a response with usage
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = "Hello there!"
        response.choices[0].finish_reason = "stop"
        response.usage.prompt_tokens = 50
        response.usage.completion_tokens = 10

        self.hooks.on_llm_response(agent, response)

        steps = list(self.storage.load_steps(self.ctx.run_id))
        assert len(steps) == 1
        step = steps[0]
        assert isinstance(step, LLMCallStep)
        assert step.model == "gpt-4o"
        assert step.response == "Hello there!"
        assert step.token_usage.prompt_tokens == 50
        assert step.token_usage.completion_tokens == 10
        assert step.finish_reason == "stop"

    def test_full_multi_agent_flow(self):
        """Simulate a full multi-agent conversation: triage → billing."""
        triage = _mock_agent(name="Triage", model="gpt-4o-mini")
        billing = _mock_agent(name="Billing", model="gpt-4o")
        tool = _mock_tool(name="lookup_account")

        # Triage starts
        self.hooks.on_agent_start(triage)

        # Triage hands off to billing
        self.hooks.on_handoff(triage, billing)

        # Triage ends
        self.hooks.on_agent_end(triage)

        # Billing starts
        self.hooks.on_agent_start(billing)

        # Billing calls a tool
        self.hooks.on_tool_start(billing, tool, input={"user_id": "123"})
        self.hooks.on_tool_end(billing, tool, input={"user_id": "123"}, output={"balance": 42.0})

        # Billing ends
        self.hooks.on_agent_end(billing, output="Your balance is $42.00")

        steps = list(self.storage.load_steps(self.ctx.run_id))
        step_types = [(type(s).__name__, getattr(s, "action", None)) for s in steps]

        # Expected: agent_start, handoff, agent_finish, agent_start, tool_call, agent_finish
        assert len(steps) == 6
        assert step_types[0] == ("AgentStep", "start")      # triage start
        assert step_types[1] == ("AgentStep", "handoff")     # handoff
        assert step_types[2] == ("AgentStep", "finish")      # triage finish
        assert step_types[3] == ("AgentStep", "start")       # billing start
        assert step_types[4] == ("ToolCallStep", None)       # tool call
        assert step_types[5] == ("AgentStep", "finish")      # billing finish


# ---------------------------------------------------------------------------
# TestHelpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_get_agent_name_with_name(self):
        agent = MagicMock()
        agent.name = "MyAgent"
        assert _get_agent_name(agent) == "MyAgent"

    def test_get_agent_name_none(self):
        assert _get_agent_name(None) == "unknown"

    def test_get_agent_name_fallback_to_class(self):
        agent = MagicMock(spec=[])  # No 'name' attribute
        del agent.name
        result = _get_agent_name(agent)
        assert isinstance(result, str)

    def test_get_agent_model(self):
        agent = MagicMock()
        agent.model = "gpt-4o"
        assert _get_agent_model(agent) == "gpt-4o"

    def test_get_agent_model_none(self):
        assert _get_agent_model(None) is None

    def test_get_agent_instructions(self):
        agent = MagicMock()
        agent.instructions = "Be helpful"
        assert _get_agent_instructions(agent) == "Be helpful"

    def test_get_agent_instructions_truncated(self):
        agent = MagicMock()
        agent.instructions = "x" * 1000
        result = _get_agent_instructions(agent)
        assert len(result) == 500

    def test_get_agent_tool_names(self):
        t1 = MagicMock()
        t1.name = "search"
        t2 = MagicMock()
        t2.name = "calculator"
        agent = MagicMock()
        agent.tools = [t1, t2]
        assert _get_agent_tool_names(agent) == ["search", "calculator"]

    def test_get_tool_name(self):
        tool = MagicMock()
        tool.name = "web_search"
        assert _get_tool_name(tool) == "web_search"

    def test_get_tool_name_none(self):
        assert _get_tool_name(None) == "unknown"

    def test_normalize_tool_input_dict(self):
        assert _normalize_tool_input({"key": "val"}) == {"key": "val"}

    def test_normalize_tool_input_string(self):
        assert _normalize_tool_input("hello") == {"input": "hello"}

    def test_normalize_tool_input_none(self):
        assert _normalize_tool_input(None) == {}

    def test_normalize_tool_input_pydantic(self):
        obj = MagicMock()
        obj.model_dump.return_value = {"x": 1}
        assert _normalize_tool_input(obj) == {"x": 1}

    def test_extract_output_string(self):
        assert _extract_output("hello") == "hello"

    def test_extract_output_none(self):
        assert _extract_output(None) is None

    def test_extract_output_dict(self):
        assert _extract_output({"key": "val"}) == {"key": "val"}

    def test_extract_output_pydantic(self):
        obj = MagicMock()
        obj.model_dump.return_value = {"result": 42}
        assert _extract_output(obj) == {"result": 42}

    def test_extract_output_final_output(self):
        obj = MagicMock(spec=[])
        del obj.model_dump
        obj.final_output = "the answer"
        assert _extract_output(obj) == "the answer"


# ---------------------------------------------------------------------------
# TestConvenienceFunction
# ---------------------------------------------------------------------------


class TestConvenienceFunction:
    def test_reagent_openai_agents_hooks_returns_hooks(self):
        ctx, _ = _make_context()
        hooks = reagent_openai_agents_hooks(ctx)
        assert isinstance(hooks, ReAgentHooks)
        assert ctx.metadata.framework == "openai_agents"

    def test_reagent_openai_agents_run_import_error(self):
        """Should raise ImportError when SDK is not installed."""
        import asyncio
        from reagent.adapters.openai_agents import reagent_openai_agents_run

        ctx, _ = _make_context()
        agent = _mock_agent()

        with patch.dict("sys.modules", {"agents": None}):
            with pytest.raises(ImportError, match="openai-agents"):
                asyncio.get_event_loop().run_until_complete(
                    reagent_openai_agents_run(ctx, agent, "hello")
                )
