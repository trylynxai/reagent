"""End-to-end integration test for remote mode (SDK → Server → Query)."""

from __future__ import annotations

import json
import pytest
from datetime import datetime
from uuid import uuid4

from reagent.core.constants import Status
from reagent.schema.run import RunMetadata, RunSummary, CostSummary, TokenSummary, StepSummary
from reagent.schema.steps import LLMCallStep, ToolCallStep, ToolInput, ToolOutput, TokenUsage
from reagent.storage.base import RunFilter, Pagination
from reagent.storage.sqlite import SQLiteStorage, STEP_TYPE_MAP


@pytest.fixture()
def _server_deps():
    """Skip if fastapi/httpx are not installed."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")


@pytest.mark.integration
@pytest.mark.usefixtures("_server_deps")
class TestRemoteMode:
    """Full round-trip: ingest via HTTP → query via HTTP."""

    @pytest.fixture(autouse=True)
    def setup_client(self, tmp_path):
        """Set up a TestClient backed by a temporary SQLite database."""
        import os
        os.environ["REAGENT_SERVER_DB"] = str(tmp_path / "test.db")
        os.environ.pop("REAGENT_API_KEYS", None)  # no auth for tests

        # Reload server config so it picks up the new DB path
        from reagent.server import config as server_config_mod
        server_config_mod.server_config = server_config_mod.ServerAppConfig()

        from fastapi.testclient import TestClient
        from reagent.server.app import app

        with TestClient(app) as client:
            self.client = client
            self.db_path = str(tmp_path / "test.db")
            yield

    # ── Helpers ────────────────────────────────────────────────

    def _make_metadata(self, run_id, name="test-run", project="test-project"):
        return RunMetadata(
            run_id=run_id,
            name=name,
            project=project,
            start_time=datetime.utcnow(),
            status=Status.COMPLETED,
            end_time=datetime.utcnow(),
            duration_ms=1234,
            cost=CostSummary(total_usd=0.05),
            tokens=TokenSummary(total_tokens=500, prompt_tokens=300, completion_tokens=200),
            steps=StepSummary(total=2, llm_calls=1, tool_calls=1),
        )

    def _make_llm_step(self, run_id):
        return LLMCallStep(
            step_id=uuid4(),
            run_id=run_id,
            step_number=0,
            step_type="llm_call",
            timestamp_start=datetime.utcnow(),
            timestamp_end=datetime.utcnow(),
            duration_ms=100,
            model="gpt-4o",
            prompt="hi",
            response="hello",
            token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    def _make_tool_step(self, run_id):
        return ToolCallStep(
            step_id=uuid4(),
            run_id=run_id,
            step_number=1,
            step_type="tool_call",
            timestamp_start=datetime.utcnow(),
            timestamp_end=datetime.utcnow(),
            duration_ms=50,
            tool_name="web_search",
            input=ToolInput(kwargs={"query": "test"}),
            output=ToolOutput(result="ok"),
        )

    # ── Tests ─────────────────────────────────────────────────

    def test_health(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_ingest_and_query_run(self):
        run_id = uuid4()
        metadata = self._make_metadata(run_id)
        llm_step = self._make_llm_step(run_id)
        tool_step = self._make_tool_step(run_id)

        # Ingest batch
        batch = {
            "events": [
                {"type": "metadata", "run_id": str(run_id), "data": metadata.model_dump(mode="json")},
                {"type": "step", "run_id": str(run_id), "step_type": "llm_call", "data": llm_step.model_dump(mode="json")},
                {"type": "step", "run_id": str(run_id), "step_type": "tool_call", "data": tool_step.model_dump(mode="json")},
            ]
        }
        resp = self.client.post("/api/v1/ingest", json=batch)
        assert resp.status_code == 200
        assert resp.json()["events_received"] == 3

        # Query full run
        resp = self.client.get(f"/api/v1/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["metadata"]["name"] == "test-run"
        assert len(data["steps"]) == 2

        # Query metadata only
        resp = self.client.get(f"/api/v1/runs/{run_id}/metadata")
        assert resp.status_code == 200
        assert resp.json()["project"] == "test-project"

        # Query steps
        resp = self.client.get(f"/api/v1/runs/{run_id}/steps")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

        # Query steps by type
        resp = self.client.get(f"/api/v1/runs/{run_id}/steps?step_type=llm_call")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["step_type"] == "llm_call"

    def test_list_runs(self):
        # Ingest two runs
        for i in range(2):
            run_id = uuid4()
            metadata = self._make_metadata(run_id, name=f"run-{i}", project="list-test")
            batch = {
                "events": [
                    {"type": "metadata", "run_id": str(run_id), "data": metadata.model_dump(mode="json")},
                ]
            }
            self.client.post("/api/v1/ingest", json=batch)

        resp = self.client.get("/api/v1/runs?project=list-test")
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) == 2

    def test_count_runs(self):
        run_id = uuid4()
        metadata = self._make_metadata(run_id, project="count-test")
        batch = {"events": [{"type": "metadata", "run_id": str(run_id), "data": metadata.model_dump(mode="json")}]}
        self.client.post("/api/v1/ingest", json=batch)

        resp = self.client.get("/api/v1/runs/count?project=count-test")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_delete_run(self):
        run_id = uuid4()
        metadata = self._make_metadata(run_id)
        batch = {"events": [{"type": "metadata", "run_id": str(run_id), "data": metadata.model_dump(mode="json")}]}
        self.client.post("/api/v1/ingest", json=batch)

        resp = self.client.delete(f"/api/v1/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        resp = self.client.get(f"/api/v1/runs/{run_id}")
        assert resp.status_code == 404

    def test_search(self):
        run_id = uuid4()
        metadata = self._make_metadata(run_id, name="searchable-agent")
        batch = {"events": [{"type": "metadata", "run_id": str(run_id), "data": metadata.model_dump(mode="json")}]}
        self.client.post("/api/v1/ingest", json=batch)

        resp = self.client.get("/api/v1/search?q=searchable")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) >= 1
        assert any(r["name"] == "searchable-agent" for r in results)

    def test_failures_endpoint(self):
        run_id = uuid4()
        metadata = self._make_metadata(run_id, name="failed-run")
        metadata.status = Status.FAILED
        metadata.error = "something broke"
        metadata.failure_category = "tool_error"
        batch = {"events": [{"type": "metadata", "run_id": str(run_id), "data": metadata.model_dump(mode="json")}]}
        self.client.post("/api/v1/ingest", json=batch)

        resp = self.client.get("/api/v1/failures")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

        resp = self.client.get("/api/v1/failures/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_failures"] >= 1
        assert "tool_error" in data["by_category"]

    def test_stats_endpoint(self):
        run_id = uuid4()
        metadata = self._make_metadata(run_id, project="stats-test")
        batch = {"events": [{"type": "metadata", "run_id": str(run_id), "data": metadata.model_dump(mode="json")}]}
        self.client.post("/api/v1/ingest", json=batch)

        resp = self.client.get("/api/v1/stats?project=stats-test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_runs"] == 1
        assert data["completed"] == 1
        assert data["total_tokens"] == 500

    def test_auth_required_when_keys_configured(self):
        """When API keys are configured, requests without a valid key are rejected."""
        import os
        os.environ["REAGENT_API_KEYS"] = "test-key-1,test-key-2"
        from reagent.server import config as server_config_mod
        server_config_mod.server_config = server_config_mod.ServerAppConfig()

        # No auth header → 401
        resp = self.client.get("/api/v1/runs")
        assert resp.status_code == 401

        # Wrong key → 403
        resp = self.client.get("/api/v1/runs", headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 403

        # Valid key → 200
        resp = self.client.get("/api/v1/runs", headers={"Authorization": "Bearer test-key-1"})
        assert resp.status_code == 200

        # Clean up
        os.environ.pop("REAGENT_API_KEYS", None)
        server_config_mod.server_config = server_config_mod.ServerAppConfig()
