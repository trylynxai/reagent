"""RunContext - Context manager for tracking a single run."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Any, Iterator
from uuid import UUID, uuid4

from reagent.core.constants import Status
from reagent.schema.run import RunConfig, RunMetadata, Run, CostSummary, TokenSummary, StepSummary
from reagent.schema.steps import (
    AnyStep,
    LLMCallStep,
    ToolCallStep,
    RetrievalStep,
    ChainStep,
    AgentStep,
    ReasoningStep,
    ErrorStep,
    CustomStep,
    TokenUsage,
    ToolInput,
    ToolOutput,
)

if TYPE_CHECKING:
    from reagent.client.reagent import ReAgent


class RunContext:
    """Context manager for tracking an agent execution run.

    Usage:
        with reagent.trace(RunConfig(name="my-run")) as ctx:
            # Agent execution happens here
            ctx.record_llm_call(...)
            ctx.record_tool_call(...)
    """

    def __init__(
        self,
        client: ReAgent,
        config: RunConfig | None = None,
        run_id: UUID | None = None,
    ) -> None:
        """Initialize the run context.

        Args:
            client: ReAgent client instance
            config: Run configuration
            run_id: Optional run ID (generated if not provided)
        """
        self._client = client
        self._config = config or RunConfig()
        self._run_id = run_id or uuid4()

        self._metadata = RunMetadata(
            run_id=self._run_id,
            name=self._config.name,
            project=self._config.project or self._client.config.project,
            tags=self._config.tags,
            start_time=datetime.utcnow(),
            input=self._config.input,
            custom=self._config.metadata,
        )

        self._step_number = 0
        self._step_stack: list[UUID] = []  # Stack of parent step IDs
        self._started = False
        self._ended = False

    @property
    def run_id(self) -> UUID:
        """Get the run ID."""
        return self._run_id

    @property
    def metadata(self) -> RunMetadata:
        """Get the run metadata."""
        return self._metadata

    @property
    def current_step_number(self) -> int:
        """Get the current step number."""
        return self._step_number

    @property
    def parent_step_id(self) -> UUID | None:
        """Get the current parent step ID (for nesting)."""
        return self._step_stack[-1] if self._step_stack else None

    def __enter__(self) -> RunContext:
        """Enter the run context."""
        self._start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit the run context."""
        if exc_type is not None:
            self._end(
                error=str(exc_val),
                error_type=exc_type.__name__ if exc_type else None,
            )
        else:
            self._end()

    def _start(self) -> None:
        """Start the run."""
        if self._started:
            return

        self._started = True
        self._client._start_run(self._run_id, self._metadata)

    def _end(
        self,
        output: Any = None,
        error: str | None = None,
        error_type: str | None = None,
    ) -> None:
        """End the run."""
        if self._ended:
            return

        self._ended = True
        self._metadata.complete(output=output, error=error, error_type=error_type)
        self._client._end_run(self._run_id, self._metadata)

    def _next_step_number(self) -> int:
        """Get the next step number."""
        num = self._step_number
        self._step_number += 1
        return num

    def _record_step(self, step: AnyStep) -> None:
        """Record a step."""
        # Update metadata stats
        self._metadata.steps.total += 1
        self._metadata.steps.by_type[step.step_type] = (
            self._metadata.steps.by_type.get(step.step_type, 0) + 1
        )

        if step.step_type == "llm_call":
            self._metadata.steps.llm_calls += 1
        elif step.step_type == "tool_call":
            self._metadata.steps.tool_calls += 1
        elif step.step_type == "retrieval":
            self._metadata.steps.retrievals += 1
        elif step.step_type == "error":
            self._metadata.steps.errors += 1

        # Record step
        self._client._record_step(self._run_id, step)

    @contextmanager
    def nest(self, step_id: UUID) -> Iterator[None]:
        """Context manager for nesting steps under a parent.

        Usage:
            step = ctx.start_chain_step(...)
            with ctx.nest(step.step_id):
                # Steps here will have step_id as parent
                ctx.record_llm_call(...)
        """
        self._step_stack.append(step_id)
        try:
            yield
        finally:
            self._step_stack.pop()

    # LLM Call methods
    def record_llm_call(
        self,
        model: str,
        prompt: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        response: str | None = None,
        response_messages: list[dict[str, Any]] | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        cost_usd: float | None = None,
        duration_ms: int | None = None,
        provider: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        finish_reason: str | None = None,
        error: str | None = None,
        raw_request: dict[str, Any] | None = None,
        raw_response: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LLMCallStep:
        """Record an LLM call."""
        now = datetime.utcnow()
        token_usage = None
        if prompt_tokens is not None or completion_tokens is not None:
            token_usage = TokenUsage.from_counts(
                prompt=prompt_tokens or 0,
                completion=completion_tokens or 0,
            )

        step = LLMCallStep(
            run_id=self._run_id,
            parent_step_id=self.parent_step_id,
            step_number=self._next_step_number(),
            timestamp_start=now,
            timestamp_end=now,
            duration_ms=duration_ms,
            model=model,
            provider=provider,
            prompt=prompt,
            messages=messages,
            response=response,
            response_messages=response_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            finish_reason=finish_reason,
            token_usage=token_usage,
            cost_usd=cost_usd,
            error=error,
            raw_request=raw_request,
            raw_response=raw_response,
            metadata=metadata or {},
        )

        # Update metadata
        if token_usage:
            self._metadata.tokens.total_tokens += token_usage.total_tokens
            self._metadata.tokens.prompt_tokens += token_usage.prompt_tokens
            self._metadata.tokens.completion_tokens += token_usage.completion_tokens

            if model not in self._metadata.tokens.by_model:
                self._metadata.tokens.by_model[model] = {
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                }
            self._metadata.tokens.by_model[model]["total_tokens"] += token_usage.total_tokens
            self._metadata.tokens.by_model[model]["prompt_tokens"] += token_usage.prompt_tokens
            self._metadata.tokens.by_model[model]["completion_tokens"] += token_usage.completion_tokens

        if cost_usd:
            self._metadata.cost.total_usd += cost_usd
            self._metadata.cost.llm_cost_usd += cost_usd
            self._metadata.cost.by_model[model] = (
                self._metadata.cost.by_model.get(model, 0) + cost_usd
            )
            if provider:
                self._metadata.cost.by_provider[provider] = (
                    self._metadata.cost.by_provider.get(provider, 0) + cost_usd
                )

        if model and model not in self._metadata.models_used:
            self._metadata.models_used.append(model)
            if not self._metadata.model:
                self._metadata.model = model

        self._record_step(step)
        return step

    # Tool Call methods
    def record_tool_call(
        self,
        tool_name: str,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        result: Any = None,
        error: str | None = None,
        error_type: str | None = None,
        duration_ms: int | None = None,
        cost_usd: float | None = None,
        tool_description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolCallStep:
        """Record a tool call."""
        now = datetime.utcnow()

        step = ToolCallStep(
            run_id=self._run_id,
            parent_step_id=self.parent_step_id,
            step_number=self._next_step_number(),
            timestamp_start=now,
            timestamp_end=now,
            duration_ms=duration_ms,
            tool_name=tool_name,
            tool_description=tool_description,
            input=ToolInput(args=args or (), kwargs=kwargs or {}),
            output=ToolOutput(result=result, error=error, error_type=error_type),
            success=error is None,
            cost_usd=cost_usd,
            metadata=metadata or {},
        )

        if cost_usd:
            self._metadata.cost.total_usd += cost_usd
            self._metadata.cost.tool_cost_usd += cost_usd

        self._record_step(step)
        return step

    # Retrieval methods
    def record_retrieval(
        self,
        query: str,
        documents: list[dict[str, Any]] | None = None,
        scores: list[float] | None = None,
        index_name: str | None = None,
        top_k: int | None = None,
        duration_ms: int | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RetrievalStep:
        """Record a retrieval/RAG operation."""
        from reagent.schema.steps import RetrievalResult

        now = datetime.utcnow()

        step = RetrievalStep(
            run_id=self._run_id,
            parent_step_id=self.parent_step_id,
            step_number=self._next_step_number(),
            timestamp_start=now,
            timestamp_end=now,
            duration_ms=duration_ms,
            query=query,
            index_name=index_name,
            top_k=top_k,
            results=RetrievalResult(
                documents=documents or [],
                scores=scores or [],
            ),
            error=error,
            metadata=metadata or {},
        )

        self._record_step(step)
        return step

    # Chain methods
    def start_chain(
        self,
        chain_name: str,
        chain_type: str | None = None,
        input: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChainStep:
        """Start a chain/pipeline step (returns uncompleted step)."""
        step = ChainStep(
            run_id=self._run_id,
            parent_step_id=self.parent_step_id,
            step_number=self._next_step_number(),
            timestamp_start=datetime.utcnow(),
            chain_name=chain_name,
            chain_type=chain_type,
            input=input or {},
            metadata=metadata or {},
        )
        return step

    def end_chain(
        self,
        step: ChainStep,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """End a chain step and record it."""
        step.output = output
        step.error = error
        step.complete()
        self._record_step(step)

    # Agent methods
    def record_agent_action(
        self,
        action: str,
        action_input: dict[str, Any] | None = None,
        action_output: Any = None,
        thought: str | None = None,
        agent_name: str | None = None,
        agent_type: str | None = None,
        duration_ms: int | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentStep:
        """Record an agent action."""
        now = datetime.utcnow()

        step = AgentStep(
            run_id=self._run_id,
            parent_step_id=self.parent_step_id,
            step_number=self._next_step_number(),
            timestamp_start=now,
            timestamp_end=now,
            duration_ms=duration_ms,
            agent_name=agent_name,
            agent_type=agent_type,
            action=action,
            action_input=action_input,
            action_output=action_output,
            thought=thought,
            error=error,
            metadata=metadata or {},
        )

        if agent_type and not self._metadata.agent_type:
            self._metadata.agent_type = agent_type

        self._record_step(step)
        return step

    def record_agent_finish(
        self,
        final_answer: Any,
        thought: str | None = None,
        agent_name: str | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentStep:
        """Record an agent finish event."""
        now = datetime.utcnow()

        step = AgentStep(
            run_id=self._run_id,
            parent_step_id=self.parent_step_id,
            step_number=self._next_step_number(),
            timestamp_start=now,
            timestamp_end=now,
            duration_ms=duration_ms,
            agent_name=agent_name,
            action="finish",
            final_answer=final_answer,
            thought=thought,
            metadata=metadata or {},
        )

        self._record_step(step)
        return step

    # Error methods
    def record_error(
        self,
        error_message: str,
        error_type: str,
        error_traceback: str | None = None,
        source_step_id: UUID | None = None,
        source_step_type: str | None = None,
        recovered: bool = False,
        recovery_action: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ErrorStep:
        """Record an error."""
        now = datetime.utcnow()

        step = ErrorStep(
            run_id=self._run_id,
            parent_step_id=self.parent_step_id,
            step_number=self._next_step_number(),
            timestamp_start=now,
            timestamp_end=now,
            error_message=error_message,
            error_type=error_type,
            error_traceback=error_traceback,
            source_step_id=source_step_id,
            source_step_type=source_step_type,
            recovered=recovered,
            recovery_action=recovery_action,
            metadata=metadata or {},
        )

        self._record_step(step)
        return step

    # Custom event methods
    def record_custom(
        self,
        event_name: str,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CustomStep:
        """Record a custom event."""
        now = datetime.utcnow()

        step = CustomStep(
            run_id=self._run_id,
            parent_step_id=self.parent_step_id,
            step_number=self._next_step_number(),
            timestamp_start=now,
            timestamp_end=now,
            event_name=event_name,
            data=data or {},
            metadata=metadata or {},
        )

        self._record_step(step)
        return step

    # Utility methods
    def set_output(self, output: Any) -> None:
        """Set the run output."""
        self._metadata.output = output

    def set_model(self, model: str) -> None:
        """Set the primary model for this run."""
        self._metadata.model = model

    def set_framework(self, framework: str, version: str | None = None) -> None:
        """Set the framework information."""
        self._metadata.framework = framework
        self._metadata.framework_version = version

    def add_tag(self, tag: str) -> None:
        """Add a tag to the run."""
        if tag not in self._metadata.tags:
            self._metadata.tags.append(tag)

    def set_metadata(self, key: str, value: Any) -> None:
        """Set a custom metadata field."""
        self._metadata.custom[key] = value
