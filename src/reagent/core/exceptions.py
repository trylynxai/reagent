"""ReAgent exception hierarchy.

All ReAgent-specific exceptions inherit from ReAgentError.
"""

from typing import Any


class ReAgentError(Exception):
    """Base exception for all ReAgent errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (details: {self.details})"
        return self.message


class ConfigError(ReAgentError):
    """Configuration-related errors.

    Raised when:
    - Configuration file is invalid or missing
    - Environment variable has invalid value
    - Required configuration is not provided
    - Configuration validation fails
    """

    pass


class StorageError(ReAgentError):
    """Storage backend errors.

    Raised when:
    - Storage backend initialization fails
    - Read/write operations fail
    - Storage quota exceeded
    - Corruption detected
    """

    pass


class ReplayError(ReAgentError):
    """Replay engine errors.

    Raised when:
    - Trace loading fails
    - Replay determinism violation
    - Sandbox escape attempted
    - Checkpoint restoration fails
    """

    pass


class ReplaySandboxError(ReplayError):
    """Sandbox violation during replay.

    Raised when code attempts to make external calls
    during strict replay mode.
    """

    pass


class ReplayDivergenceError(ReplayError):
    """State divergence detected during replay.

    Raised when the replayed state differs from the
    recorded state beyond acceptable thresholds.
    """

    def __init__(
        self,
        message: str,
        step_number: int,
        expected_hash: str,
        actual_hash: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.step_number = step_number
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash


class RedactionError(ReAgentError):
    """Redaction engine errors.

    Raised when:
    - Pattern compilation fails
    - Redaction timeout (ReDoS prevention)
    - NLP model loading fails
    """

    pass


class AdapterError(ReAgentError):
    """Framework adapter errors.

    Raised when:
    - Adapter installation fails
    - Framework version incompatible
    - Event normalization fails
    """

    pass


class BufferError(ReAgentError):
    """Event buffer errors.

    Raised when:
    - Buffer overflow with 'raise' policy
    - Invalid buffer configuration
    """

    pass


class TransportError(ReAgentError):
    """Transport layer errors.

    Raised when:
    - Transport initialization fails
    - Connection lost
    - Write timeout
    """

    pass


class ValidationError(ReAgentError):
    """Data validation errors.

    Raised when:
    - Event schema validation fails
    - Step data is malformed
    - Required fields missing
    """

    pass


class TraceNotFoundError(StorageError):
    """Trace not found in storage.

    Raised when attempting to load a trace that
    doesn't exist in the storage backend.
    """

    def __init__(self, run_id: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(f"Trace not found: {run_id}", details)
        self.run_id = run_id


class TraceCorruptedError(StorageError):
    """Trace data is corrupted.

    Raised when trace data cannot be parsed or
    fails integrity checks.
    """

    def __init__(
        self,
        run_id: str,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"Trace corrupted: {run_id} - {reason}", details)
        self.run_id = run_id
        self.reason = reason
