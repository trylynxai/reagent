"""Run models - Configuration, metadata, and summary for agent runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterator
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_serializer, field_validator

from reagent.core.constants import Status
from reagent.schema.steps import AnyStep


class CostSummary(BaseModel):
    """Cost breakdown for a run."""

    total_usd: float = 0.0
    llm_cost_usd: float = 0.0
    tool_cost_usd: float = 0.0
    by_model: dict[str, float] = Field(default_factory=dict)


class TokenSummary(BaseModel):
    """Token usage breakdown for a run."""

    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    by_model: dict[str, dict[str, int]] = Field(default_factory=dict)


class StepSummary(BaseModel):
    """Step count breakdown for a run."""

    total: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    retrievals: int = 0
    errors: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)


class RunConfig(BaseModel):
    """Configuration for a new run.

    Passed to ReAgent.trace() to configure the recording session.
    """

    # Optional name/identifier for this run
    name: str | None = None

    # Project this run belongs to
    project: str | None = None

    # Tags for categorization
    tags: list[str] = Field(default_factory=list)

    # Custom metadata to attach to the run
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Input data that triggered this run
    input: dict[str, Any] | None = None

    # Sampling rate (1.0 = record everything, 0.5 = record 50%)
    sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)

    # Maximum number of steps to record (None = unlimited)
    max_steps: int | None = None

    # Maximum trace size in MB (None = unlimited)
    max_size_mb: float | None = None

    @field_validator("tags")
    @classmethod
    def dedupe_tags(cls, v: list[str]) -> list[str]:
        """Remove duplicate tags while preserving order."""
        seen: set[str] = set()
        result: list[str] = []
        for tag in v:
            if tag not in seen:
                seen.add(tag)
                result.append(tag)
        return result


class RunMetadata(BaseModel):
    """Metadata collected during run execution."""

    run_id: UUID
    name: str | None = None
    project: str | None = None
    tags: list[str] = Field(default_factory=list)

    # Timestamps
    start_time: datetime
    end_time: datetime | None = None
    duration_ms: int | None = None

    # Status
    status: Status = Status.RUNNING

    # Framework information
    framework: str | None = None  # e.g., "langchain", "crewai"
    framework_version: str | None = None
    agent_type: str | None = None

    # Model information (primary model used)
    model: str | None = None
    models_used: list[str] = Field(default_factory=list)

    # Summaries
    cost: CostSummary = Field(default_factory=CostSummary)
    tokens: TokenSummary = Field(default_factory=TokenSummary)
    steps: StepSummary = Field(default_factory=StepSummary)

    # Input/Output
    input: dict[str, Any] | None = None
    output: Any | None = None

    # Error information (if failed)
    error: str | None = None
    error_type: str | None = None
    failure_category: str | None = None

    # Custom metadata
    custom: dict[str, Any] = Field(default_factory=dict)

    # Schema version for migration
    schema_version: str = "1.0"

    @field_serializer("run_id")
    def serialize_run_id(self, v: UUID) -> str:
        """Serialize run ID to string."""
        return str(v)

    @field_serializer("start_time", "end_time")
    def serialize_timestamp(self, v: datetime | None) -> str | None:
        """Serialize timestamps to ISO format."""
        return v.isoformat() if v else None

    def complete(
        self,
        output: Any = None,
        error: str | None = None,
        error_type: str | None = None,
    ) -> None:
        """Mark the run as complete.

        If the run failed and no failure_category was manually set,
        auto-classifies the failure using the rule-based classifier.
        """
        self.end_time = datetime.utcnow()
        if self.start_time:
            delta = self.end_time - self.start_time
            self.duration_ms = int(delta.total_seconds() * 1000)

        if error:
            self.status = Status.FAILED
            self.error = error
            self.error_type = error_type

            # Auto-classify if not manually set
            if not self.failure_category:
                from reagent.classification.classifier import classify_failure

                result = classify_failure(
                    error=error,
                    error_type=error_type,
                )
                self.failure_category = result.category.value
        else:
            self.status = Status.COMPLETED
            # Only set output if provided, preserving any previously set output
            if output is not None:
                self.output = output


class RunSummary(BaseModel):
    """Lightweight summary of a run for listing/search results."""

    run_id: UUID
    name: str | None = None
    project: str | None = None
    tags: list[str] = Field(default_factory=list)

    start_time: datetime
    end_time: datetime | None = None
    duration_ms: int | None = None

    status: Status
    model: str | None = None

    step_count: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0

    error: str | None = None
    failure_category: str | None = None

    @field_serializer("run_id")
    def serialize_run_id(self, v: UUID) -> str:
        """Serialize run ID to string."""
        return str(v)

    @field_serializer("start_time", "end_time")
    def serialize_timestamp(self, v: datetime | None) -> str | None:
        """Serialize timestamps to ISO format."""
        return v.isoformat() if v else None

    @classmethod
    def from_metadata(cls, metadata: RunMetadata) -> RunSummary:
        """Create summary from full metadata."""
        return cls(
            run_id=metadata.run_id,
            name=metadata.name,
            project=metadata.project,
            tags=metadata.tags,
            start_time=metadata.start_time,
            end_time=metadata.end_time,
            duration_ms=metadata.duration_ms,
            status=metadata.status,
            model=metadata.model,
            step_count=metadata.steps.total,
            total_tokens=metadata.tokens.total_tokens,
            total_cost_usd=metadata.cost.total_usd,
            error=metadata.error,
            failure_category=metadata.failure_category,
        )


class Run(BaseModel):
    """Complete run with metadata and steps."""

    metadata: RunMetadata
    steps: list[AnyStep] = Field(default_factory=list)

    @property
    def run_id(self) -> UUID:
        """Get the run ID."""
        return self.metadata.run_id

    @property
    def status(self) -> Status:
        """Get the run status."""
        return self.metadata.status

    @property
    def step_count(self) -> int:
        """Get the number of steps."""
        return len(self.steps)

    def iter_steps(self, step_type: str | None = None) -> Iterator[AnyStep]:
        """Iterate over steps, optionally filtered by type."""
        for step in self.steps:
            if step_type is None or step.step_type == step_type:
                yield step

    def get_step(self, step_number: int) -> AnyStep | None:
        """Get a step by its number."""
        for step in self.steps:
            if step.step_number == step_number:
                return step
        return None

    def get_step_by_id(self, step_id: UUID) -> AnyStep | None:
        """Get a step by its ID."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def to_summary(self) -> RunSummary:
        """Convert to a lightweight summary."""
        return RunSummary.from_metadata(self.metadata)

    @classmethod
    def create(
        cls,
        config: RunConfig | None = None,
        run_id: UUID | None = None,
    ) -> Run:
        """Create a new run."""
        config = config or RunConfig()
        run_id = run_id or uuid4()

        metadata = RunMetadata(
            run_id=run_id,
            name=config.name,
            project=config.project,
            tags=config.tags,
            start_time=datetime.utcnow(),
            input=config.input,
            custom=config.metadata,
        )

        return cls(metadata=metadata, steps=[])
