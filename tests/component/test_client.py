"""Component tests for SDK client."""

import pytest
from datetime import datetime
from uuid import uuid4

from reagent.client.reagent import ReAgent
from reagent.client.context import RunContext
from reagent.core.config import Config
from reagent.core.constants import Status, StorageType
from reagent.schema.run import RunConfig
from reagent.storage.memory import MemoryStorage


class TestRunContext:
    """Tests for RunContext."""

    @pytest.fixture
    def client(self):
        """Create a ReAgent client with memory storage."""
        storage = MemoryStorage()
        config = Config(
            storage={"type": "memory"},
            redaction={"enabled": False},
        )
        return ReAgent(storage=storage, config=config)

    def test_context_manager(self, client):
        """Test using RunContext as context manager."""
        with client.trace(RunConfig(name="test-run")) as ctx:
            assert ctx.run_id is not None
            assert ctx.current_step_number == 0

        # Run should be completed
        runs = client.list_runs()
        assert len(runs) == 1
        assert runs[0].status == Status.COMPLETED

    def test_record_llm_call(self, client):
        """Test recording an LLM call."""
        with client.trace(RunConfig(name="test-run")) as ctx:
            step = ctx.record_llm_call(
                model="gpt-4",
                prompt="Hello",
                response="Hi there!",
                prompt_tokens=10,
                completion_tokens=5,
                cost_usd=0.001,
            )

            assert step.model == "gpt-4"
            assert step.prompt == "Hello"
            assert step.response == "Hi there!"

        # Check stored run
        run = client.load_run(ctx.run_id)
        assert len(run.steps) == 1
        assert run.metadata.tokens.total_tokens == 15
        assert run.metadata.cost.total_usd == 0.001

    def test_record_tool_call(self, client):
        """Test recording a tool call."""
        with client.trace(RunConfig(name="test-run")) as ctx:
            step = ctx.record_tool_call(
                tool_name="calculator",
                kwargs={"expression": "2+2"},
                result=4,
                duration_ms=100,
            )

            assert step.tool_name == "calculator"
            assert step.output.result == 4

        run = client.load_run(ctx.run_id)
        assert len(run.steps) == 1
        assert run.metadata.steps.tool_calls == 1

    def test_record_error(self, client):
        """Test recording an error."""
        with client.trace(RunConfig(name="test-run")) as ctx:
            step = ctx.record_error(
                error_message="Something went wrong",
                error_type="ValueError",
            )

            assert step.error_message == "Something went wrong"
            assert step.error_type == "ValueError"

        run = client.load_run(ctx.run_id)
        assert run.metadata.steps.errors == 1

    def test_context_with_exception(self, client):
        """Test context manager handles exceptions."""
        with pytest.raises(ValueError):
            with client.trace(RunConfig(name="test-run")) as ctx:
                raise ValueError("Test error")

        # Run should be marked as failed
        runs = client.list_runs()
        assert runs[0].status == Status.FAILED
        assert "Test error" in runs[0].error

    def test_step_nesting(self, client):
        """Test nesting steps under a parent."""
        with client.trace(RunConfig(name="test-run")) as ctx:
            chain = ctx.start_chain(chain_name="test-chain")

            with ctx.nest(chain.step_id):
                llm_step = ctx.record_llm_call(model="gpt-4", prompt="nested")
                assert llm_step.parent_step_id == chain.step_id

            ctx.end_chain(chain, output={"result": "done"})

    def test_metadata_updates(self, client):
        """Test metadata update methods."""
        with client.trace(RunConfig(name="test-run")) as ctx:
            ctx.set_model("gpt-4")
            ctx.set_framework("langchain", "0.1.0")
            ctx.add_tag("production")
            ctx.set_metadata("custom_key", "custom_value")
            ctx.set_output({"result": "success"})

        run = client.load_run(ctx.run_id)
        assert run.metadata.model == "gpt-4"
        assert run.metadata.framework == "langchain"
        assert "production" in run.metadata.tags
        assert run.metadata.custom["custom_key"] == "custom_value"
        assert run.metadata.output == {"result": "success"}


class TestReAgentClient:
    """Tests for ReAgent client."""

    @pytest.fixture
    def client(self):
        """Create a ReAgent client with memory storage."""
        storage = MemoryStorage()
        config = Config(
            storage={"type": "memory"},
            redaction={"enabled": False},
        )
        return ReAgent(storage=storage, config=config)

    def test_client_creation(self):
        """Test creating a client."""
        client = ReAgent()
        assert client is not None
        client.close()

    def test_client_context_manager(self):
        """Test using client as context manager."""
        with ReAgent() as client:
            assert client is not None

    def test_list_runs_empty(self, client):
        """Test listing runs when empty."""
        runs = client.list_runs()
        assert runs == []

    def test_list_runs_with_data(self, client):
        """Test listing runs with data."""
        # Create some runs
        for i in range(3):
            with client.trace(RunConfig(name=f"run-{i}")):
                pass

        runs = client.list_runs()
        assert len(runs) == 3

    def test_search_runs(self, client):
        """Test searching runs."""
        with client.trace(RunConfig(name="alpha-run")):
            pass
        with client.trace(RunConfig(name="beta-run")):
            pass

        results = client.search_runs("alpha")
        assert len(results) == 1
        assert results[0].name == "alpha-run"

    def test_delete_run(self, client):
        """Test deleting a run."""
        with client.trace(RunConfig(name="to-delete")) as ctx:
            pass

        assert client.count_runs() == 1
        client.delete_run(ctx.run_id)
        assert client.count_runs() == 0

    def test_count_runs(self, client):
        """Test counting runs."""
        assert client.count_runs() == 0

        with client.trace():
            pass
        with client.trace():
            pass

        assert client.count_runs() == 2
