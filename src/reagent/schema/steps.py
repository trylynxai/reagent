"""Step models - Specialized event types for different agent operations.

Each step type captures the specific data relevant to that operation type.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_serializer


class TokenUsage(BaseModel):
    """Token usage information for LLM calls."""

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)

    @classmethod
    def from_counts(cls, prompt: int, completion: int) -> TokenUsage:
        """Create TokenUsage from prompt and completion counts."""
        return cls(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        )


class ToolInput(BaseModel):
    """Input to a tool call."""

    args: tuple[Any, ...] = Field(default_factory=tuple)
    kwargs: dict[str, Any] = Field(default_factory=dict)

    @field_serializer("args")
    def serialize_args(self, v: tuple[Any, ...]) -> list[Any]:
        """Serialize tuple to list for JSON compatibility."""
        return list(v)


class ToolOutput(BaseModel):
    """Output from a tool call."""

    result: Any = None
    error: str | None = None
    error_type: str | None = None


class RetrievalResult(BaseModel):
    """Result from a retrieval operation."""

    documents: list[dict[str, Any]] = Field(default_factory=list)
    scores: list[float] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Step(BaseModel):
    """Base step model for all step types."""

    step_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    parent_step_id: UUID | None = None
    step_number: int = Field(ge=0)
    timestamp_start: datetime
    timestamp_end: datetime | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_serializer("step_id", "run_id", "parent_step_id")
    def serialize_uuid(self, v: UUID | None) -> str | None:
        """Serialize UUIDs to strings."""
        return str(v) if v else None

    @field_serializer("timestamp_start", "timestamp_end")
    def serialize_timestamp(self, v: datetime | None) -> str | None:
        """Serialize timestamp to ISO format."""
        return v.isoformat() if v else None

    def complete(self, timestamp_end: datetime | None = None) -> None:
        """Mark the step as complete."""
        self.timestamp_end = timestamp_end or datetime.utcnow()
        if self.timestamp_start:
            delta = self.timestamp_end - self.timestamp_start
            self.duration_ms = int(delta.total_seconds() * 1000)


class LLMCallStep(Step):
    """Step representing an LLM API call."""

    step_type: Literal["llm_call"] = "llm_call"

    # Model information
    model: str
    provider: str | None = None

    # Request data
    prompt: str | None = None
    messages: list[dict[str, Any]] | None = None
    system_prompt: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    stop_sequences: list[str] | None = None

    # Response data
    response: str | None = None
    response_messages: list[dict[str, Any]] | None = None
    finish_reason: str | None = None

    # Token usage
    token_usage: TokenUsage | None = None

    # Cost
    cost_usd: float | None = None

    # Raw request/response for debugging
    raw_request: dict[str, Any] | None = None
    raw_response: dict[str, Any] | None = None

    # Error information
    error: str | None = None
    error_type: str | None = None


class ToolCallStep(Step):
    """Step representing a tool/function call."""

    step_type: Literal["tool_call"] = "tool_call"

    # Tool information
    tool_name: str
    tool_description: str | None = None

    # Input/Output
    input: ToolInput
    output: ToolOutput | None = None

    # Execution status
    success: bool = True

    # Associated cost (for external APIs)
    cost_usd: float | None = None


class RetrievalStep(Step):
    """Step representing a retrieval/RAG operation."""

    step_type: Literal["retrieval"] = "retrieval"

    # Query information
    query: str
    query_embedding: list[float] | None = None

    # Retrieval configuration
    index_name: str | None = None
    top_k: int | None = None
    filters: dict[str, Any] | None = None

    # Results
    results: RetrievalResult | None = None

    # Error information
    error: str | None = None


class ChainStep(Step):
    """Step representing a chain/pipeline execution."""

    step_type: Literal["chain"] = "chain"

    # Chain information
    chain_name: str
    chain_type: str | None = None

    # Input/Output
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None

    # Nested steps count
    nested_step_count: int = 0

    # Error information
    error: str | None = None


class AgentStep(Step):
    """Step representing an agent action or decision."""

    step_type: Literal["agent"] = "agent"

    # Agent information
    agent_name: str | None = None
    agent_type: str | None = None

    # Action/Decision
    action: str | None = None
    action_input: dict[str, Any] | None = None
    action_output: Any | None = None

    # Thought/Reasoning (for CoT agents)
    thought: str | None = None

    # Final answer (for agent_finish events)
    final_answer: Any | None = None

    # Error information
    error: str | None = None


class ReasoningStep(Step):
    """Step representing an explicit reasoning/thinking step."""

    step_type: Literal["reasoning"] = "reasoning"

    # Reasoning content
    thought: str
    reasoning_type: str | None = None  # e.g., "analysis", "planning", "reflection"

    # Context used for reasoning
    context: dict[str, Any] | None = None

    # Conclusions drawn
    conclusions: list[str] | None = None


class ErrorStep(Step):
    """Step representing an error that occurred during execution."""

    step_type: Literal["error"] = "error"

    # Error information
    error_message: str
    error_type: str
    error_traceback: str | None = None

    # Context where error occurred
    source_step_id: UUID | None = None
    source_step_type: str | None = None

    # Recovery attempted
    recovered: bool = False
    recovery_action: str | None = None

    @field_serializer("source_step_id")
    def serialize_source_step_id(self, v: UUID | None) -> str | None:
        """Serialize source step UUID."""
        return str(v) if v else None


class CheckpointStep(Step):
    """Step representing a checkpoint in the execution."""

    step_type: Literal["checkpoint"] = "checkpoint"

    # Checkpoint data
    checkpoint_name: str | None = None
    state_hash: str
    state_size_bytes: int | None = None

    # Serialized state (optional, can be large)
    state_data: dict[str, Any] | None = None


class CustomStep(Step):
    """Step for user-defined custom events."""

    step_type: Literal["custom"] = "custom"

    # Custom event name
    event_name: str

    # Custom data
    data: dict[str, Any] = Field(default_factory=dict)


# Type alias for any step type
AnyStep = (
    LLMCallStep
    | ToolCallStep
    | RetrievalStep
    | ChainStep
    | AgentStep
    | ReasoningStep
    | ErrorStep
    | CheckpointStep
    | CustomStep
)
