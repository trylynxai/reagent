"""Unit tests for exceptions."""

import pytest

from reagent.core.exceptions import (
    ReAgentError,
    ConfigError,
    StorageError,
    ReplayError,
    ReplaySandboxError,
    ReplayDivergenceError,
    RedactionError,
    AdapterError,
    BufferError,
    TransportError,
    ValidationError,
    TraceNotFoundError,
    TraceCorruptedError,
)


class TestReAgentError:
    """Tests for base ReAgentError."""

    def test_basic_error(self):
        """Test creating a basic error."""
        error = ReAgentError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.details == {}

    def test_error_with_details(self):
        """Test error with details."""
        error = ReAgentError(
            "Something went wrong",
            details={"key": "value", "count": 42},
        )
        assert "details:" in str(error)
        assert error.details["key"] == "value"
        assert error.details["count"] == 42


class TestSpecificErrors:
    """Tests for specific error types."""

    def test_config_error(self):
        """Test ConfigError."""
        error = ConfigError("Invalid configuration")
        assert isinstance(error, ReAgentError)
        assert "Invalid configuration" in str(error)

    def test_storage_error(self):
        """Test StorageError."""
        error = StorageError("Failed to save")
        assert isinstance(error, ReAgentError)

    def test_replay_error(self):
        """Test ReplayError."""
        error = ReplayError("Replay failed")
        assert isinstance(error, ReAgentError)

    def test_replay_sandbox_error(self):
        """Test ReplaySandboxError."""
        error = ReplaySandboxError("Network call blocked")
        assert isinstance(error, ReplayError)
        assert isinstance(error, ReAgentError)

    def test_replay_divergence_error(self):
        """Test ReplayDivergenceError."""
        error = ReplayDivergenceError(
            "Divergence detected",
            step_number=5,
            expected_hash="abc123",
            actual_hash="def456",
        )
        assert isinstance(error, ReplayError)
        assert error.step_number == 5
        assert error.expected_hash == "abc123"
        assert error.actual_hash == "def456"


class TestTraceErrors:
    """Tests for trace-specific errors."""

    def test_trace_not_found(self):
        """Test TraceNotFoundError."""
        error = TraceNotFoundError("run-123")
        assert isinstance(error, StorageError)
        assert error.run_id == "run-123"
        assert "run-123" in str(error)

    def test_trace_corrupted(self):
        """Test TraceCorruptedError."""
        error = TraceCorruptedError("run-123", "Invalid JSON")
        assert isinstance(error, StorageError)
        assert error.run_id == "run-123"
        assert error.reason == "Invalid JSON"
        assert "run-123" in str(error)
        assert "Invalid JSON" in str(error)
