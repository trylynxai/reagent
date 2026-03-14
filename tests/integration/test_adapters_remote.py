"""Integration tests: adapter recording pipeline works end-to-end in remote mode.

The CrewAI and LlamaIndex adapters record events via RunContext.record_*
methods.  RunContext delegates to ReAgent._record_step / _start_run / _end_run,
which go through the Transport layer.  In remote mode the transport is
RemoteTransport, which POSTs JSON batches to /api/v1/ingest.

These tests verify:
1. The JSON that RemoteTransport *would* produce is accepted by the server
   and queryable afterwards (simulated via TestClient).
2. ReAgent(server_url=...) creates RemoteTransport and RemoteStorage.
3. Adapters are transport-agnostic: they only touch RunContext / self._client,
   never reference a specific transport.
"""

from __future__ import annotations

import inspect
import os
import textwrap
from datetime import datetime
from uuid import uuid4

import pytest

from reagent.core.constants import Status
from reagent.schema.run import RunMetadata, CostSummary, TokenSummary, StepSummary
from reagent.schema.steps import (
    LLMCallStep,
    ToolCallStep,
    ChainStep,
    CustomStep,
    RetrievalStep,
    AgentStep,
    ErrorStep,
    ToolInput,
    ToolOutput,
    TokenUsage,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def _server_deps():
    """Skip the entire test if fastapi / httpx are not installed."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")


# ---------------------------------------------------------------------------
# Integration tests — adapter ➜ context ➜ transport ➜ server pipeline
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.usefixtures("_server_deps")
class TestAdapterRemotePipeline:
    """Prove that the event types produced by adapters survive a full
    remote round-trip: serialize ➜ POST /ingest ➜ query back."""

    @pytest.fixture(autouse=True)
    def setup_server(self, tmp_path):
        os.environ["REAGENT_SERVER_DB"] = str(tmp_path / "test.db")
        os.environ.pop("REAGENT_API_KEYS", None)

        from reagent.server import config as server_config_mod
        server_config_mod.server_config = server_config_mod.ServerAppConfig()

        from fastapi.testclient import TestClient
        from reagent.server.app import app

        with TestClient(app) as client:
            self.client = client
            yield

    # -- helpers ----------------------------------------------------------

    def _make_metadata(self, run_id, *, name="adapter-test", project="adapter-project"):
        return RunMetadata(
            run_id=run_id,
            name=name,
            project=project,
            start_time=datetime.utcnow(),
            status=Status.COMPLETED,
            end_time=datetime.utcnow(),
            duration_ms=500,
            framework="crewai",
            framework_version="0.30.0",
            cost=CostSummary(total_usd=0.01),
            tokens=TokenSummary(total_tokens=100, prompt_tokens=60, completion_tokens=40),
            steps=StepSummary(total=4, llm_calls=1, tool_calls=1),
        )

    def _ingest(self, events: list[dict]) -> dict:
        resp = self.client.post("/api/v1/ingest", json={"events": events})
        assert resp.status_code == 200, resp.text
        return resp.json()

    # -- tests ------------------------------------------------------------

    def test_llm_call_step_round_trip(self):
        """An LLMCallStep (the kind crewai/llamaindex adapters record) is
        accepted by ingest and queryable."""
        run_id = uuid4()
        meta = self._make_metadata(run_id)
        step = LLMCallStep(
            run_id=run_id,
            step_number=0,
            timestamp_start=datetime.utcnow(),
            timestamp_end=datetime.utcnow(),
            duration_ms=120,
            model="gpt-4o",
            provider="llamaindex",
            prompt="What is the meaning of life?",
            response="42",
            token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            metadata={"event_type": "llm"},
        )

        result = self._ingest([
            {"type": "metadata", "run_id": str(run_id), "data": meta.model_dump(mode="json")},
            {"type": "step", "run_id": str(run_id), "step_type": "llm_call",
             "data": step.model_dump(mode="json")},
        ])
        assert result["events_received"] == 2

        # Query back
        resp = self.client.get(f"/api/v1/runs/{run_id}/steps?step_type=llm_call")
        assert resp.status_code == 200
        steps = resp.json()
        assert len(steps) == 1
        assert steps[0]["model"] == "gpt-4o"

    def test_tool_call_step_round_trip(self):
        """A ToolCallStep (recorded by crewai _ToolProxy) survives ingest."""
        run_id = uuid4()
        meta = self._make_metadata(run_id)
        step = ToolCallStep(
            run_id=run_id,
            step_number=0,
            timestamp_start=datetime.utcnow(),
            timestamp_end=datetime.utcnow(),
            duration_ms=30,
            tool_name="web_search",
            tool_description="Search the web",
            input=ToolInput(args=("query",), kwargs={"engine": "google"}),
            output=ToolOutput(result="some results"),
            success=True,
        )

        self._ingest([
            {"type": "metadata", "run_id": str(run_id), "data": meta.model_dump(mode="json")},
            {"type": "step", "run_id": str(run_id), "step_type": "tool_call",
             "data": step.model_dump(mode="json")},
        ])

        resp = self.client.get(f"/api/v1/runs/{run_id}/steps?step_type=tool_call")
        assert resp.status_code == 200
        steps = resp.json()
        assert len(steps) == 1
        assert steps[0]["tool_name"] == "web_search"

    def test_chain_step_round_trip(self):
        """A ChainStep (start_chain/end_chain used by both adapters) survives."""
        run_id = uuid4()
        meta = self._make_metadata(run_id)
        step = ChainStep(
            run_id=run_id,
            step_number=0,
            timestamp_start=datetime.utcnow(),
            timestamp_end=datetime.utcnow(),
            duration_ms=200,
            chain_name="CrewExecution",
            chain_type="sequential",
            input={"task": "do stuff"},
            output={"result": "done"},
        )

        self._ingest([
            {"type": "metadata", "run_id": str(run_id), "data": meta.model_dump(mode="json")},
            {"type": "step", "run_id": str(run_id), "step_type": "chain",
             "data": step.model_dump(mode="json")},
        ])

        resp = self.client.get(f"/api/v1/runs/{run_id}/steps?step_type=chain")
        assert resp.status_code == 200
        steps = resp.json()
        assert len(steps) == 1
        assert steps[0]["chain_name"] == "CrewExecution"

    def test_custom_step_round_trip(self):
        """CustomStep (used by LlamaIndex handler for synthesis/query/embedding)."""
        run_id = uuid4()
        meta = self._make_metadata(run_id)
        step = CustomStep(
            run_id=run_id,
            step_number=0,
            timestamp_start=datetime.utcnow(),
            timestamp_end=datetime.utcnow(),
            event_name="synthesis",
            data={"query": "What is AI?", "response": "AI is ...", "duration_ms": 50},
            metadata={"event_type": "synthesis"},
        )

        self._ingest([
            {"type": "metadata", "run_id": str(run_id), "data": meta.model_dump(mode="json")},
            {"type": "step", "run_id": str(run_id), "step_type": "custom",
             "data": step.model_dump(mode="json")},
        ])

        resp = self.client.get(f"/api/v1/runs/{run_id}/steps?step_type=custom")
        assert resp.status_code == 200
        steps = resp.json()
        assert len(steps) == 1
        assert steps[0]["event_name"] == "synthesis"

    def test_retrieval_step_round_trip(self):
        """RetrievalStep (used by LlamaIndex handler _record_retrieval_event)."""
        run_id = uuid4()
        meta = self._make_metadata(run_id)
        step = RetrievalStep(
            run_id=run_id,
            step_number=0,
            timestamp_start=datetime.utcnow(),
            timestamp_end=datetime.utcnow(),
            duration_ms=45,
            query="search query",
            metadata={"event_type": "retrieval"},
        )

        self._ingest([
            {"type": "metadata", "run_id": str(run_id), "data": meta.model_dump(mode="json")},
            {"type": "step", "run_id": str(run_id), "step_type": "retrieval",
             "data": step.model_dump(mode="json")},
        ])

        resp = self.client.get(f"/api/v1/runs/{run_id}/steps?step_type=retrieval")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_agent_step_round_trip(self):
        """AgentStep (used by CrewAI AgentWrapper.execute_task)."""
        run_id = uuid4()
        meta = self._make_metadata(run_id)
        step = AgentStep(
            run_id=run_id,
            step_number=0,
            timestamp_start=datetime.utcnow(),
            timestamp_end=datetime.utcnow(),
            duration_ms=80,
            agent_name="researcher",
            agent_type="crewai",
            action="execute_task",
            action_input={"task": "research AI trends"},
        )

        self._ingest([
            {"type": "metadata", "run_id": str(run_id), "data": meta.model_dump(mode="json")},
            {"type": "step", "run_id": str(run_id), "step_type": "agent",
             "data": step.model_dump(mode="json")},
        ])

        resp = self.client.get(f"/api/v1/runs/{run_id}/steps?step_type=agent")
        assert resp.status_code == 200
        steps = resp.json()
        assert len(steps) == 1
        assert steps[0]["agent_name"] == "researcher"

    def test_error_step_round_trip(self):
        """ErrorStep (used by both adapters via ctx.record_error)."""
        run_id = uuid4()
        meta = self._make_metadata(run_id)
        step = ErrorStep(
            run_id=run_id,
            step_number=0,
            timestamp_start=datetime.utcnow(),
            timestamp_end=datetime.utcnow(),
            error_message="Something went wrong",
            error_type="RuntimeError",
            error_traceback="Traceback ...",
        )

        self._ingest([
            {"type": "metadata", "run_id": str(run_id), "data": meta.model_dump(mode="json")},
            {"type": "step", "run_id": str(run_id), "step_type": "error",
             "data": step.model_dump(mode="json")},
        ])

        resp = self.client.get(f"/api/v1/runs/{run_id}/steps?step_type=error")
        assert resp.status_code == 200
        steps = resp.json()
        assert len(steps) == 1
        assert steps[0]["error_message"] == "Something went wrong"

    def test_mixed_adapter_events_single_run(self):
        """A realistic adapter run that mixes metadata + llm + tool + chain +
        custom + agent steps in one ingest batch."""
        run_id = uuid4()
        now = datetime.utcnow()
        meta = self._make_metadata(run_id)

        events = [
            {"type": "metadata", "run_id": str(run_id),
             "data": meta.model_dump(mode="json")},
            # Chain (crew execution)
            {"type": "step", "run_id": str(run_id), "step_type": "chain",
             "data": ChainStep(
                 run_id=run_id, step_number=0, timestamp_start=now,
                 chain_name="CrewExecution", chain_type="sequential",
                 input={"tasks": 2},
             ).model_dump(mode="json")},
            # Agent action
            {"type": "step", "run_id": str(run_id), "step_type": "agent",
             "data": AgentStep(
                 run_id=run_id, step_number=1, timestamp_start=now,
                 agent_name="writer", action="execute_task",
                 action_input={"task": "write blog post"},
             ).model_dump(mode="json")},
            # LLM call
            {"type": "step", "run_id": str(run_id), "step_type": "llm_call",
             "data": LLMCallStep(
                 run_id=run_id, step_number=2, timestamp_start=now,
                 model="gpt-4o", prompt="Write a blog post",
                 response="Here is your post...",
             ).model_dump(mode="json")},
            # Tool call
            {"type": "step", "run_id": str(run_id), "step_type": "tool_call",
             "data": ToolCallStep(
                 run_id=run_id, step_number=3, timestamp_start=now,
                 tool_name="web_search",
                 input=ToolInput(args=(), kwargs={"q": "AI"}),
                 output=ToolOutput(result="results"),
             ).model_dump(mode="json")},
            # Custom (synthesis from llamaindex handler)
            {"type": "step", "run_id": str(run_id), "step_type": "custom",
             "data": CustomStep(
                 run_id=run_id, step_number=4, timestamp_start=now,
                 event_name="synthesis",
                 data={"query": "summarize", "response": "summary"},
             ).model_dump(mode="json")},
        ]

        result = self._ingest(events)
        assert result["events_received"] == 6

        # Full run query
        resp = self.client.get(f"/api/v1/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["steps"]) == 5

    def test_adapter_metadata_round_trip(self):
        """Core metadata fields (name, project, model, tags) survive the trip
        through the server, proving adapters' metadata will be preserved."""
        run_id = uuid4()
        meta = self._make_metadata(run_id)
        meta.name = "crewai-run"
        meta.model = "gpt-4o"
        meta.tags = ["crewai", "production"]

        self._ingest([
            {"type": "metadata", "run_id": str(run_id),
             "data": meta.model_dump(mode="json")},
        ])

        resp = self.client.get(f"/api/v1/runs/{run_id}/metadata")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "crewai-run"
        assert body["model"] == "gpt-4o"
        assert "crewai" in body["tags"]


# ---------------------------------------------------------------------------
# Unit test — ReAgent(server_url=...) creates remote transport & storage
# ---------------------------------------------------------------------------

class TestReAgentRemoteConstruction:
    """Verify that passing server_url to ReAgent produces RemoteTransport
    and RemoteStorage without actually connecting anywhere."""

    def test_remote_transport_and_storage_created(self):
        from reagent.client.reagent import ReAgent
        from reagent.client.transport import RemoteTransport
        from reagent.storage.remote import RemoteStorage

        client = ReAgent(server_url="http://localhost:9999")
        try:
            assert isinstance(client._transport, RemoteTransport)
            assert isinstance(client._storage, RemoteStorage)
            assert client._is_remote_mode() is True
        finally:
            # Shut down background threads without hitting the network
            client._transport._running = False
            client._transport._flush_thread.join(timeout=2)

    def test_local_mode_does_not_create_remote(self):
        from reagent.client.reagent import ReAgent
        from reagent.client.transport import RemoteTransport
        from reagent.storage.remote import RemoteStorage

        client = ReAgent()
        try:
            assert not isinstance(client._transport, RemoteTransport)
            assert not isinstance(client._storage, RemoteStorage)
            assert client._is_remote_mode() is False
        finally:
            client.close()


# ---------------------------------------------------------------------------
# Unit test — adapters are transport-agnostic
# ---------------------------------------------------------------------------

class TestAdaptersTransportAgnostic:
    """Adapters must never reference a concrete transport class.  They should
    only call self._context.record_* / self._client.* methods."""

    @staticmethod
    def _read_source(module) -> str:
        return inspect.getsource(module)

    def test_crewai_adapter_does_not_reference_transport(self):
        import reagent.adapters.crewai as mod
        source = self._read_source(mod)
        assert "RemoteTransport" not in source
        assert "SyncTransport" not in source
        assert "AsyncTransport" not in source
        assert "BufferedTransport" not in source
        assert "OfflineTransport" not in source
        # Should only talk through context
        assert "_context.record_" in source or "_context.start_chain" in source

    def test_llamaindex_adapter_does_not_reference_transport(self):
        import reagent.adapters.llamaindex as mod
        source = self._read_source(mod)
        assert "RemoteTransport" not in source
        assert "SyncTransport" not in source
        assert "AsyncTransport" not in source
        assert "BufferedTransport" not in source
        assert "OfflineTransport" not in source
        assert "_context.record_" in source or "_context.start_chain" in source

    def test_base_adapter_does_not_reference_transport(self):
        import reagent.adapters.base as mod
        source = self._read_source(mod)
        assert "RemoteTransport" not in source
        assert "SyncTransport" not in source
        assert "AsyncTransport" not in source
        assert "BufferedTransport" not in source
        assert "OfflineTransport" not in source
        # Base adapter only stores _client
        assert "_client" in source

    def test_run_context_does_not_reference_transport(self):
        import reagent.client.context as mod
        source = self._read_source(mod)
        assert "RemoteTransport" not in source
        assert "SyncTransport" not in source
        assert "AsyncTransport" not in source
        # Context only calls self._client._record_step / _start_run / _end_run
        assert "_client._record_step" in source
        assert "_client._start_run" in source
        assert "_client._end_run" in source
