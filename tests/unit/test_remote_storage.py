"""Unit tests for RemoteStorage."""

import json
import urllib.error
from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from reagent.core.exceptions import TraceNotFoundError, StorageError
from reagent.schema.run import Run, RunMetadata, RunSummary
from reagent.storage.remote import RemoteStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(body: dict | list, status: int = 200):
    """Return a mock that behaves like the object returned by urlopen()."""
    data = json.dumps(body).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = data
    resp.status = status
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _run_summary_dict(run_id=None, status="completed"):
    """Return a dict matching the RunSummary schema."""
    return {
        "run_id": str(run_id or uuid4()),
        "name": "test-run",
        "project": "my-project",
        "tags": ["ci"],
        "start_time": "2026-01-15T12:00:00",
        "end_time": "2026-01-15T12:01:00",
        "duration_ms": 60000,
        "status": status,
        "model": "gpt-4",
        "step_count": 3,
        "total_tokens": 1500,
        "total_cost_usd": 0.05,
        "error": None,
        "failure_category": None,
    }


def _run_metadata_dict(run_id=None):
    """Return a dict matching the RunMetadata schema."""
    rid = str(run_id or uuid4())
    return {
        "run_id": rid,
        "name": "test-run",
        "project": "my-project",
        "tags": ["ci"],
        "start_time": "2026-01-15T12:00:00",
        "end_time": "2026-01-15T12:01:00",
        "duration_ms": 60000,
        "status": "completed",
        "model": "gpt-4",
        "models_used": ["gpt-4"],
        "cost": {"total_usd": 0.05},
        "tokens": {"total_tokens": 1500, "prompt_tokens": 1000, "completion_tokens": 500},
        "steps": {"total": 3},
        "error": None,
        "error_type": None,
        "failure_category": None,
        "input": None,
        "output": None,
        "custom": {},
        "schema_version": "1.0",
    }


def _run_dict(run_id=None):
    """Return a dict matching the Run schema (metadata + steps)."""
    rid = run_id or uuid4()
    return {
        "metadata": _run_metadata_dict(rid),
        "steps": [
            {
                "step_type": "llm_call",
                "step_id": str(uuid4()),
                "run_id": str(rid),
                "step_number": 0,
                "timestamp_start": "2026-01-15T12:00:00",
                "model": "gpt-4",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRemoteStorageListRuns:
    """Tests for list_runs()."""

    def test_list_runs_returns_run_summaries(self):
        """list_runs() parses JSON array into list of RunSummary."""
        storage = RemoteStorage(server_url="http://localhost:8080")
        summaries = [_run_summary_dict(), _run_summary_dict()]

        with patch("urllib.request.urlopen", return_value=_mock_response(summaries)):
            result = storage.list_runs()

        assert len(result) == 2
        assert all(isinstance(r, RunSummary) for r in result)

    def test_list_runs_empty(self):
        """list_runs() returns empty list for empty JSON array."""
        storage = RemoteStorage(server_url="http://localhost:8080")

        with patch("urllib.request.urlopen", return_value=_mock_response([])):
            result = storage.list_runs()

        assert result == []


class TestRemoteStorageLoadRun:
    """Tests for load_run()."""

    def test_load_run_returns_run(self):
        """load_run() parses JSON into a Run object."""
        run_id = uuid4()
        storage = RemoteStorage(server_url="http://localhost:8080")

        with patch("urllib.request.urlopen", return_value=_mock_response(_run_dict(run_id))):
            result = storage.load_run(run_id)

        assert isinstance(result, Run)
        assert result.metadata.run_id == run_id


class TestRemoteStorageLoadMetadata:
    """Tests for load_metadata()."""

    def test_load_metadata_returns_run_metadata(self):
        """load_metadata() parses JSON into RunMetadata."""
        run_id = uuid4()
        storage = RemoteStorage(server_url="http://localhost:8080")

        with patch("urllib.request.urlopen", return_value=_mock_response(_run_metadata_dict(run_id))):
            result = storage.load_metadata(run_id)

        assert isinstance(result, RunMetadata)
        assert result.run_id == run_id
        assert result.project == "my-project"


class TestRemoteStorageSearch:
    """Tests for search()."""

    def test_search_returns_run_summaries(self):
        """search() parses JSON array into list of RunSummary."""
        storage = RemoteStorage(server_url="http://localhost:8080")
        summaries = [_run_summary_dict()]

        with patch("urllib.request.urlopen", return_value=_mock_response(summaries)):
            result = storage.search("gpt-4")

        assert len(result) == 1
        assert isinstance(result[0], RunSummary)


class TestRemoteStorageCountRuns:
    """Tests for count_runs()."""

    def test_count_runs_returns_integer(self):
        """count_runs() returns the integer from the 'count' key."""
        storage = RemoteStorage(server_url="http://localhost:8080")

        with patch("urllib.request.urlopen", return_value=_mock_response({"count": 42})):
            result = storage.count_runs()

        assert result == 42

    def test_count_runs_defaults_to_zero(self):
        """count_runs() returns 0 when 'count' key is absent."""
        storage = RemoteStorage(server_url="http://localhost:8080")

        with patch("urllib.request.urlopen", return_value=_mock_response({})):
            result = storage.count_runs()

        assert result == 0


class TestRemoteStorageDeleteRun:
    """Tests for delete_run()."""

    def test_delete_run_returns_true(self):
        """delete_run() returns True when server confirms deletion."""
        run_id = uuid4()
        storage = RemoteStorage(server_url="http://localhost:8080")

        with patch("urllib.request.urlopen", return_value=_mock_response({"deleted": True})):
            assert storage.delete_run(run_id) is True

    def test_delete_run_returns_false(self):
        """delete_run() returns False when server reports not deleted."""
        run_id = uuid4()
        storage = RemoteStorage(server_url="http://localhost:8080")

        with patch("urllib.request.urlopen", return_value=_mock_response({"deleted": False})):
            assert storage.delete_run(run_id) is False


class TestRemoteStorageExists:
    """Tests for exists()."""

    def test_exists_returns_true_for_known_run(self):
        """exists() returns True when the server responds with metadata."""
        run_id = uuid4()
        storage = RemoteStorage(server_url="http://localhost:8080")

        with patch("urllib.request.urlopen", return_value=_mock_response(_run_metadata_dict(run_id))):
            assert storage.exists(run_id) is True

    def test_exists_returns_false_for_404(self):
        """exists() returns False when the server returns 404."""
        run_id = uuid4()
        storage = RemoteStorage(server_url="http://localhost:8080")
        http_error = urllib.error.HTTPError(
            url="http://localhost:8080",
            code=404,
            msg="Not Found",
            hdrs=MagicMock(),
            fp=None,
        )

        with patch("urllib.request.urlopen", side_effect=http_error):
            assert storage.exists(run_id) is False


class TestRemoteStorageWriteOps:
    """Tests that write operations raise NotImplementedError."""

    def test_save_run_raises(self):
        """save_run() raises NotImplementedError."""
        storage = RemoteStorage(server_url="http://localhost:8080")
        run_id = uuid4()
        metadata = RunMetadata(run_id=run_id, start_time=datetime(2026, 1, 15, 12, 0, 0))

        with pytest.raises(NotImplementedError):
            storage.save_run(run_id, metadata)

    def test_save_step_raises(self):
        """save_step() raises NotImplementedError."""
        from reagent.schema.steps import LLMCallStep

        storage = RemoteStorage(server_url="http://localhost:8080")
        run_id = uuid4()
        step = LLMCallStep(
            run_id=run_id,
            step_number=0,
            timestamp_start=datetime(2026, 1, 15, 12, 0, 0),
            model="gpt-4",
        )

        with pytest.raises(NotImplementedError):
            storage.save_step(run_id, step)


class TestRemoteStorage404:
    """Tests for 404 → TraceNotFoundError mapping."""

    def test_load_run_404_raises_trace_not_found(self):
        """load_run() raises TraceNotFoundError on HTTP 404."""
        run_id = uuid4()
        storage = RemoteStorage(server_url="http://localhost:8080")
        http_error = urllib.error.HTTPError(
            url="http://localhost:8080",
            code=404,
            msg="Not Found",
            hdrs=MagicMock(),
            fp=None,
        )

        with patch("urllib.request.urlopen", side_effect=http_error):
            with pytest.raises(TraceNotFoundError):
                storage.load_run(run_id)

    def test_load_metadata_404_raises_trace_not_found(self):
        """load_metadata() raises TraceNotFoundError on HTTP 404."""
        run_id = uuid4()
        storage = RemoteStorage(server_url="http://localhost:8080")
        http_error = urllib.error.HTTPError(
            url="http://localhost:8080",
            code=404,
            msg="Not Found",
            hdrs=MagicMock(),
            fp=None,
        )

        with patch("urllib.request.urlopen", side_effect=http_error):
            with pytest.raises(TraceNotFoundError):
                storage.load_metadata(run_id)


class TestRemoteStorageAuth:
    """Tests for Authorization header."""

    def test_authorization_header_sent_when_api_key_provided(self):
        """Bearer token is included when api_key is set."""
        storage = RemoteStorage(
            server_url="http://localhost:8080",
            api_key="my-secret-key",
        )

        with patch("urllib.request.urlopen", return_value=_mock_response([])) as mock_open:
            storage.list_runs()

            req = mock_open.call_args[0][0]
            assert req.get_header("Authorization") == "Bearer my-secret-key"

    def test_no_authorization_header_when_api_key_is_none(self):
        """No Authorization header when api_key is omitted."""
        storage = RemoteStorage(server_url="http://localhost:8080")

        with patch("urllib.request.urlopen", return_value=_mock_response([])) as mock_open:
            storage.list_runs()

            req = mock_open.call_args[0][0]
            assert req.get_header("Authorization") is None


class TestRemoteStorageQueryParams:
    """Tests for query parameter construction."""

    def test_list_runs_passes_project_filter(self):
        """list_runs() includes project in query params."""
        from reagent.storage.base import RunFilter

        storage = RemoteStorage(server_url="http://localhost:8080")
        filters = RunFilter(project="my-proj")

        with patch("urllib.request.urlopen", return_value=_mock_response([])) as mock_open:
            storage.list_runs(filters=filters)

            req = mock_open.call_args[0][0]
            assert "project=my-proj" in req.full_url

    def test_list_runs_passes_status_filter(self):
        """list_runs() includes status in query params."""
        from reagent.core.constants import Status
        from reagent.storage.base import RunFilter

        storage = RemoteStorage(server_url="http://localhost:8080")
        filters = RunFilter(status=Status.COMPLETED)

        with patch("urllib.request.urlopen", return_value=_mock_response([])) as mock_open:
            storage.list_runs(filters=filters)

            req = mock_open.call_args[0][0]
            assert "status=completed" in req.full_url

    def test_list_runs_passes_pagination(self):
        """list_runs() includes limit and offset from Pagination."""
        from reagent.storage.base import Pagination

        storage = RemoteStorage(server_url="http://localhost:8080")
        pagination = Pagination(limit=10, offset=20)

        with patch("urllib.request.urlopen", return_value=_mock_response([])) as mock_open:
            storage.list_runs(pagination=pagination)

            req = mock_open.call_args[0][0]
            assert "limit=10" in req.full_url
            assert "offset=20" in req.full_url

    def test_count_runs_passes_project_filter(self):
        """count_runs() includes project in query params."""
        from reagent.storage.base import RunFilter

        storage = RemoteStorage(server_url="http://localhost:8080")
        filters = RunFilter(project="my-proj")

        with patch("urllib.request.urlopen", return_value=_mock_response({"count": 5})) as mock_open:
            storage.count_runs(filters=filters)

            req = mock_open.call_args[0][0]
            assert "project=my-proj" in req.full_url
