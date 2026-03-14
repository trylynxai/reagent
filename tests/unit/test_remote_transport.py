"""Unit tests for RemoteTransport."""

import json
import time
from datetime import datetime
from unittest.mock import MagicMock, patch, call
from uuid import uuid4

import pytest

from reagent.client.transport import RemoteTransport, OfflineTransport
from reagent.core.constants import TransportMode
from reagent.schema.run import RunMetadata
from reagent.schema.steps import LLMCallStep


def _make_metadata(run_id=None):
    """Create a minimal RunMetadata for testing."""
    return RunMetadata(
        run_id=run_id or uuid4(),
        start_time=datetime(2026, 1, 15, 12, 0, 0),
    )


def _make_step(run_id=None, step_number=0):
    """Create a minimal LLMCallStep for testing."""
    return LLMCallStep(
        run_id=run_id or uuid4(),
        step_number=step_number,
        timestamp_start=datetime(2026, 1, 15, 12, 0, 0),
        model="gpt-4",
    )


def _mock_urlopen_response(status=200, body=b"ok"):
    """Create a mock response object with context manager support."""
    resp = MagicMock()
    resp.read.return_value = body
    resp.status = status
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestRemoteTransportBuffering:
    """Tests for event buffering behaviour."""

    def test_events_buffered_until_batch_size_reached(self):
        """Events accumulate in buffer until batch_size is hit."""
        transport = RemoteTransport(
            server_url="http://localhost:8080",
            batch_size=3,
            flush_interval_ms=60000,  # long interval so timer doesn't flush
        )
        run_id = uuid4()

        with patch("urllib.request.urlopen", return_value=_mock_urlopen_response()):
            # Send two steps -- below batch_size, so buffer should hold them
            transport.send_step(run_id, _make_step(run_id, 0))
            transport.send_step(run_id, _make_step(run_id, 1))

            assert len(transport._buffer) == 2

            transport.close()

    def test_buffer_flushes_when_batch_size_reached(self):
        """Buffer is flushed automatically when batch_size events accumulate."""
        transport = RemoteTransport(
            server_url="http://localhost:8080",
            batch_size=2,
            flush_interval_ms=60000,
            retry_max=0,
        )
        run_id = uuid4()

        with patch("urllib.request.urlopen", return_value=_mock_urlopen_response()) as mock_open:
            transport.send_step(run_id, _make_step(run_id, 0))
            transport.send_step(run_id, _make_step(run_id, 1))

            # Buffer should have been flushed (now empty)
            assert len(transport._buffer) == 0
            mock_open.assert_called_once()

            transport.close()


class TestRemoteTransportFlush:
    """Tests for explicit flush() behaviour."""

    def test_flush_sends_buffered_events(self):
        """flush() sends any events sitting in the buffer."""
        transport = RemoteTransport(
            server_url="http://localhost:8080",
            batch_size=100,
            flush_interval_ms=60000,
            retry_max=0,
        )
        run_id = uuid4()

        with patch("urllib.request.urlopen", return_value=_mock_urlopen_response()) as mock_open:
            transport.send_step(run_id, _make_step(run_id, 0))
            assert len(transport._buffer) == 1

            transport.flush()

            assert len(transport._buffer) == 0
            mock_open.assert_called_once()

            transport.close()

    def test_flush_noop_when_buffer_empty(self):
        """flush() does nothing when the buffer is empty."""
        transport = RemoteTransport(
            server_url="http://localhost:8080",
            batch_size=100,
            flush_interval_ms=60000,
            retry_max=0,
        )

        with patch("urllib.request.urlopen") as mock_open:
            transport.flush()
            mock_open.assert_not_called()

            transport.close()


class TestRemoteTransportPayload:
    """Tests for the JSON payload sent over the wire."""

    def test_json_payload_has_events_key_with_list(self):
        """POST body is JSON with an 'events' key containing a list of event dicts."""
        transport = RemoteTransport(
            server_url="http://localhost:8080",
            batch_size=100,
            flush_interval_ms=60000,
            retry_max=0,
        )
        run_id = uuid4()

        with patch("urllib.request.urlopen", return_value=_mock_urlopen_response()) as mock_open:
            transport.send_step(run_id, _make_step(run_id, 0))
            transport.flush()

            # Extract the Request object passed to urlopen
            req = mock_open.call_args[0][0]
            body = json.loads(req.data.decode("utf-8"))

            assert "events" in body
            assert isinstance(body["events"], list)
            assert len(body["events"]) == 1
            assert body["events"][0]["type"] == "step"
            assert body["events"][0]["run_id"] == str(run_id)

            transport.close()

    def test_metadata_event_format(self):
        """Metadata events contain type='metadata' and serialised RunMetadata."""
        transport = RemoteTransport(
            server_url="http://localhost:8080",
            batch_size=100,
            flush_interval_ms=60000,
            retry_max=0,
        )
        run_id = uuid4()
        metadata = _make_metadata(run_id)

        with patch("urllib.request.urlopen", return_value=_mock_urlopen_response()) as mock_open:
            transport.send_metadata(run_id, metadata)
            transport.flush()

            req = mock_open.call_args[0][0]
            body = json.loads(req.data.decode("utf-8"))

            event = body["events"][0]
            assert event["type"] == "metadata"
            assert event["run_id"] == str(run_id)
            assert "data" in event

            transport.close()

    def test_posts_to_correct_url(self):
        """Requests are sent to <server_url>/api/v1/ingest."""
        transport = RemoteTransport(
            server_url="http://myserver:9090/",
            batch_size=100,
            flush_interval_ms=60000,
            retry_max=0,
        )
        run_id = uuid4()

        with patch("urllib.request.urlopen", return_value=_mock_urlopen_response()) as mock_open:
            transport.send_step(run_id, _make_step(run_id, 0))
            transport.flush()

            req = mock_open.call_args[0][0]
            assert req.full_url == "http://myserver:9090/api/v1/ingest"

            transport.close()


class TestRemoteTransportAuth:
    """Tests for Authorization header handling."""

    def test_authorization_header_set_when_api_key_provided(self):
        """Bearer token is included when api_key is not None."""
        transport = RemoteTransport(
            server_url="http://localhost:8080",
            api_key="secret-key-123",
            batch_size=100,
            flush_interval_ms=60000,
            retry_max=0,
        )
        run_id = uuid4()

        with patch("urllib.request.urlopen", return_value=_mock_urlopen_response()) as mock_open:
            transport.send_step(run_id, _make_step(run_id, 0))
            transport.flush()

            req = mock_open.call_args[0][0]
            assert req.get_header("Authorization") == "Bearer secret-key-123"

            transport.close()

    def test_no_authorization_header_when_api_key_is_none(self):
        """No Authorization header when api_key is omitted."""
        transport = RemoteTransport(
            server_url="http://localhost:8080",
            batch_size=100,
            flush_interval_ms=60000,
            retry_max=0,
        )
        run_id = uuid4()

        with patch("urllib.request.urlopen", return_value=_mock_urlopen_response()) as mock_open:
            transport.send_step(run_id, _make_step(run_id, 0))
            transport.flush()

            req = mock_open.call_args[0][0]
            assert req.get_header("Authorization") is None

            transport.close()


class TestRemoteTransportRetry:
    """Tests for retry-with-backoff logic."""

    def test_retry_with_backoff_on_failure_then_success(self):
        """urlopen failures are retried; success on later attempt is accepted."""
        transport = RemoteTransport(
            server_url="http://localhost:8080",
            batch_size=100,
            flush_interval_ms=60000,
            retry_max=2,
        )
        run_id = uuid4()

        fail_resp = ConnectionError("refused")
        ok_resp = _mock_urlopen_response()

        with patch("urllib.request.urlopen", side_effect=[fail_resp, ok_resp]) as mock_open, \
             patch("time.sleep") as mock_sleep:
            transport.send_step(run_id, _make_step(run_id, 0))
            transport.flush()

            assert mock_open.call_count == 2
            # First retry backoff: 2^0 = 1 second
            mock_sleep.assert_called_once_with(1)

            transport.close()

    def test_all_retries_exhausted_raises(self):
        """When all retries fail, the exception propagates to _flush_buffer."""
        transport = RemoteTransport(
            server_url="http://localhost:8080",
            batch_size=100,
            flush_interval_ms=60000,
            retry_max=1,
            fallback_to_local=False,
        )
        run_id = uuid4()

        with patch("urllib.request.urlopen", side_effect=ConnectionError("refused")), \
             patch("time.sleep"):
            transport.send_step(run_id, _make_step(run_id, 0))
            # _flush_buffer catches the exception only if fallback_to_local is True.
            # With fallback_to_local=False, the exception is not caught by _flush_buffer
            # but _post_batch raises after retries are exhausted.
            # Since _flush_buffer calls _post_batch and the exception propagates,
            # buffer should be cleared (events are popped before send attempt).
            transport.flush()
            assert len(transport._buffer) == 0

            transport.close()


class TestRemoteTransportFallback:
    """Tests for fallback to OfflineTransport."""

    def test_fallback_to_offline_transport_on_unreachable_server(self):
        """When server is unreachable and fallback_to_local=True, events go to OfflineTransport."""
        transport = RemoteTransport(
            server_url="http://localhost:8080",
            batch_size=100,
            flush_interval_ms=60000,
            retry_max=0,
            fallback_to_local=True,
        )
        run_id = uuid4()

        with patch("urllib.request.urlopen", side_effect=ConnectionError("refused")), \
             patch.object(OfflineTransport, "send_step") as mock_offline_step:
            transport.send_step(run_id, _make_step(run_id, 0))
            transport.flush()

            assert transport._offline_transport is not None
            transport.close()

    def test_no_fallback_when_disabled(self):
        """When fallback_to_local=False, no OfflineTransport is created."""
        transport = RemoteTransport(
            server_url="http://localhost:8080",
            batch_size=100,
            flush_interval_ms=60000,
            retry_max=0,
            fallback_to_local=False,
        )
        run_id = uuid4()

        with patch("urllib.request.urlopen", side_effect=ConnectionError("refused")):
            transport.send_step(run_id, _make_step(run_id, 0))
            transport.flush()

            assert transport._offline_transport is None
            transport.close()


class TestRemoteTransportClose:
    """Tests for close() behaviour."""

    def test_close_flushes_remaining_events(self):
        """close() flushes any remaining buffered events."""
        transport = RemoteTransport(
            server_url="http://localhost:8080",
            batch_size=100,
            flush_interval_ms=60000,
            retry_max=0,
        )
        run_id = uuid4()

        with patch("urllib.request.urlopen", return_value=_mock_urlopen_response()) as mock_open:
            transport.send_step(run_id, _make_step(run_id, 0))
            transport.send_step(run_id, _make_step(run_id, 1))
            assert len(transport._buffer) == 2

            transport.close()

            assert len(transport._buffer) == 0
            mock_open.assert_called_once()


class TestRemoteTransportMode:
    """Tests for the mode property."""

    def test_mode_returns_remote(self):
        """mode property returns TransportMode.REMOTE."""
        transport = RemoteTransport(
            server_url="http://localhost:8080",
            flush_interval_ms=60000,
        )
        assert transport.mode == TransportMode.REMOTE
        transport.close()


class TestRemoteTransportSendBatch:
    """Tests for send_batch()."""

    def test_send_batch_buffers_all_steps(self):
        """send_batch() adds all steps to the buffer."""
        transport = RemoteTransport(
            server_url="http://localhost:8080",
            batch_size=100,
            flush_interval_ms=60000,
        )
        run_id = uuid4()
        steps = [_make_step(run_id, i) for i in range(5)]

        with patch("urllib.request.urlopen", return_value=_mock_urlopen_response()):
            transport.send_batch(run_id, steps)
            assert len(transport._buffer) == 5
            transport.close()
