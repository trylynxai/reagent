"""ReAgent constants and enumerations."""

from enum import Enum


class EventType(str, Enum):
    """Types of events that can be captured during agent execution."""

    # Run lifecycle events
    RUN_START = "run_start"
    RUN_END = "run_end"

    # LLM events
    LLM_CALL_START = "llm_call_start"
    LLM_CALL_END = "llm_call_end"

    # Tool events
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"

    # Retrieval events (RAG)
    RETRIEVAL_START = "retrieval_start"
    RETRIEVAL_END = "retrieval_end"

    # Chain/Agent events
    CHAIN_START = "chain_start"
    CHAIN_END = "chain_end"
    AGENT_ACTION = "agent_action"
    AGENT_FINISH = "agent_finish"

    # Reasoning events
    REASONING_START = "reasoning_start"
    REASONING_END = "reasoning_end"

    # Error events
    ERROR = "error"

    # Checkpoint events
    CHECKPOINT = "checkpoint"

    # Custom events
    CUSTOM = "custom"


class TransportMode(str, Enum):
    """Transport modes for event delivery."""

    # Blocking writes - guaranteed delivery, higher latency
    SYNC = "sync"

    # Non-blocking writes via background thread
    ASYNC = "async"

    # Batch writes - collects events and flushes periodically
    BUFFERED = "buffered"

    # Queue to disk for offline/air-gapped environments
    OFFLINE = "offline"


class Status(str, Enum):
    """Status of a run or step."""

    # Run is currently executing
    RUNNING = "running"

    # Run completed successfully
    COMPLETED = "completed"

    # Run failed with an error
    FAILED = "failed"

    # Run was partially recorded (e.g., due to crash)
    PARTIAL = "partial"

    # Run was cancelled
    CANCELLED = "cancelled"


class FailureCategory(str, Enum):
    """Categories for classifying agent failures."""

    TOOL_TIMEOUT = "tool_timeout"
    TOOL_ERROR = "tool_error"
    RATE_LIMIT = "rate_limit"
    CONTEXT_OVERFLOW = "context_overflow"
    AUTHENTICATION = "authentication"
    VALIDATION_ERROR = "validation_error"
    CHAIN_ERROR = "chain_error"
    CONNECTION_ERROR = "connection_error"
    PERMISSION_ERROR = "permission_error"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    REASONING_LOOP = "reasoning_loop"
    UNKNOWN = "unknown"


class AlertSeverity(str, Enum):
    """Severity levels for alerts."""

    WARNING = "warning"
    CRITICAL = "critical"


class BackpressurePolicy(str, Enum):
    """Policy for handling buffer overflow."""

    # Drop oldest events when buffer is full
    DROP_OLDEST = "drop_oldest"

    # Drop newest events when buffer is full
    DROP_NEWEST = "drop_newest"

    # Block until buffer has space
    BLOCK = "block"

    # Raise BufferError when buffer is full
    RAISE = "raise"


class ReplayMode(str, Enum):
    """Replay engine modes."""

    # Return exact recorded outputs, no external calls
    STRICT = "strict"

    # Re-execute selected steps, replay others
    PARTIAL = "partial"

    # Intercept external calls, return recorded responses
    MOCK = "mock"

    # Mix of strict and partial, configurable per step type
    HYBRID = "hybrid"


class RedactionMode(str, Enum):
    """Redaction modes for sensitive data."""

    # Replace with [REDACTED]
    REMOVE = "remove"

    # Replace with hash:<sha256>
    HASH = "hash"

    # Partial masking (e.g., sk-...last4)
    MASK = "mask"

    # Replace with enc:<ciphertext> (enterprise feature)
    ENCRYPT = "encrypt"


class StorageType(str, Enum):
    """Storage backend types."""

    # In-memory storage for testing
    MEMORY = "memory"

    # JSONL file storage (default)
    JSONL = "jsonl"

    # SQLite storage with indexing and search
    SQLITE = "sqlite"


class OutputFormat(str, Enum):
    """Output formats for CLI and export."""

    # Human-readable, colorized output
    HUMAN = "human"

    # Machine-readable JSON
    JSON = "json"

    # Documentation-friendly Markdown
    MARKDOWN = "markdown"

    # Self-contained HTML report
    HTML = "html"

    # OpenTelemetry (OTLP) protobuf JSON
    OTLP = "otlp"

    # Langfuse trace JSON
    LANGFUSE = "langfuse"


# Default values
DEFAULT_BUFFER_SIZE = 10_000
DEFAULT_FLUSH_INTERVAL_MS = 100
DEFAULT_STORAGE_PATH = ".reagent/traces"
DEFAULT_TRANSPORT_MODE = TransportMode.BUFFERED
DEFAULT_BACKPRESSURE_POLICY = BackpressurePolicy.DROP_OLDEST
DEFAULT_REDACTION_MODE = RedactionMode.REMOVE
DEFAULT_REPLAY_MODE = ReplayMode.STRICT
DEFAULT_OUTPUT_FORMAT = OutputFormat.HUMAN

# Limits
MAX_TRACE_SIZE_MB = 100
MAX_STEP_PAYLOAD_SIZE_KB = 512
REDACTION_TIMEOUT_MS = 10
