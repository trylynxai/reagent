"""Langfuse export - Convert ReAgent runs to Langfuse-compatible format.

Langfuse is an open-source LLM observability platform. This module converts
ReAgent Run objects to Langfuse's trace/observation JSON format, enabling:

- File export: Write Langfuse JSON that can be imported via their API
- Live export: Send traces directly to a Langfuse instance (requires langfuse SDK)

Mapping:
    Run         → Trace (top-level)
    LLMCallStep → Generation (with model, usage, cost)
    ToolCallStep → Span (with tool metadata)
    AgentStep   → Span (with agent metadata)
    ChainStep   → Span (with chain metadata)
    ErrorStep   → Event (error event)
    Other steps → Span (generic)

See: https://langfuse.com/docs/tracing
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from reagent.schema.run import Run, RunMetadata
from reagent.schema.steps import (
    AnyStep,
    AgentStep,
    ChainStep,
    CustomStep,
    ErrorStep,
    LLMCallStep,
    ReasoningStep,
    RetrievalStep,
    ToolCallStep,
)


def run_to_langfuse_json(run: Run) -> dict[str, Any]:
    """Convert a ReAgent Run to Langfuse trace JSON format.

    Returns a dict with:
        - "trace": The top-level trace object
        - "observations": List of observation objects (generations, spans, events)

    This format can be sent to the Langfuse API or written to a file.

    Args:
        run: The ReAgent Run to convert

    Returns:
        Dict with "trace" and "observations" keys
    """
    trace = _run_to_trace(run.metadata)
    observations = [
        _step_to_observation(step, run.metadata.run_id)
        for step in run.steps
    ]

    return {
        "trace": trace,
        "observations": observations,
    }


def export_langfuse_live(
    run: Run,
    public_key: str,
    secret_key: str,
    host: str = "https://cloud.langfuse.com",
) -> None:
    """Export a run directly to a Langfuse instance.

    Requires the `langfuse` package: pip install langfuse

    Args:
        run: The ReAgent Run to export
        public_key: Langfuse public key
        secret_key: Langfuse secret key
        host: Langfuse host URL
    """
    try:
        from langfuse import Langfuse
    except ImportError:
        raise ImportError(
            "langfuse package is required for live export. "
            "Install with: pip install langfuse"
        )

    client = Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        host=host,
    )

    meta = run.metadata

    # Create the trace
    trace = client.trace(
        id=str(meta.run_id),
        name=meta.name or str(meta.run_id),
        input=meta.input,
        output=meta.output,
        metadata=_trace_metadata(meta),
        tags=meta.tags,
    )

    # Add observations
    for step in run.steps:
        _add_live_observation(trace, step, meta.run_id)

    # Flush
    client.flush()


# ---------------------------------------------------------------------------
# Internal: Trace conversion
# ---------------------------------------------------------------------------


def _run_to_trace(meta: RunMetadata) -> dict[str, Any]:
    """Convert RunMetadata to a Langfuse trace dict."""
    trace: dict[str, Any] = {
        "id": str(meta.run_id),
        "name": meta.name or str(meta.run_id),
        "input": meta.input,
        "output": meta.output,
        "metadata": _trace_metadata(meta),
        "tags": meta.tags,
        "timestamp": _format_timestamp(meta.start_time),
    }

    if meta.status.value == "completed":
        trace["level"] = "DEFAULT"
    elif meta.status.value == "failed":
        trace["level"] = "ERROR"
        trace["statusMessage"] = meta.error
    else:
        trace["level"] = "DEBUG"

    return trace


def _trace_metadata(meta: RunMetadata) -> dict[str, Any]:
    """Build metadata dict for a trace."""
    md: dict[str, Any] = {
        "reagent_run_id": str(meta.run_id),
        "status": meta.status.value,
    }
    if meta.project:
        md["project"] = meta.project
    if meta.framework:
        md["framework"] = meta.framework
    if meta.framework_version:
        md["framework_version"] = meta.framework_version
    if meta.model:
        md["primary_model"] = meta.model
    if meta.duration_ms is not None:
        md["duration_ms"] = meta.duration_ms
    if meta.cost.total_usd:
        md["total_cost_usd"] = meta.cost.total_usd
    if meta.tokens.total_tokens:
        md["total_tokens"] = meta.tokens.total_tokens
    if meta.error:
        md["error"] = meta.error
    if meta.error_type:
        md["error_type"] = meta.error_type
    if meta.failure_category:
        md["failure_category"] = meta.failure_category
    if meta.custom:
        md["custom"] = meta.custom
    return md


# ---------------------------------------------------------------------------
# Internal: Step → Observation
# ---------------------------------------------------------------------------


def _step_to_observation(step: AnyStep, run_id: UUID) -> dict[str, Any]:
    """Convert a step to a Langfuse observation dict."""
    if isinstance(step, LLMCallStep):
        return _llm_to_generation(step, run_id)
    elif isinstance(step, ErrorStep):
        return _error_to_event(step, run_id)
    elif isinstance(step, ToolCallStep):
        return _tool_to_span(step, run_id)
    elif isinstance(step, AgentStep):
        return _agent_to_span(step, run_id)
    elif isinstance(step, ChainStep):
        return _chain_to_span(step, run_id)
    elif isinstance(step, RetrievalStep):
        return _retrieval_to_span(step, run_id)
    elif isinstance(step, ReasoningStep):
        return _reasoning_to_span(step, run_id)
    elif isinstance(step, CustomStep):
        return _custom_to_event(step, run_id)
    else:
        return _generic_span(step, run_id)


def _base_observation(step: AnyStep, run_id: UUID) -> dict[str, Any]:
    """Build common observation fields."""
    obs: dict[str, Any] = {
        "id": str(step.step_id),
        "traceId": str(run_id),
        "startTime": _format_timestamp(step.timestamp_start),
    }
    if step.timestamp_end:
        obs["endTime"] = _format_timestamp(step.timestamp_end)
    if step.parent_step_id:
        obs["parentObservationId"] = str(step.parent_step_id)
    if step.metadata:
        obs["metadata"] = step.metadata
    return obs


def _llm_to_generation(step: LLMCallStep, run_id: UUID) -> dict[str, Any]:
    """Convert LLMCallStep → Langfuse Generation."""
    obs = _base_observation(step, run_id)
    obs["type"] = "GENERATION"
    obs["name"] = f"llm_call: {step.model}"
    obs["model"] = step.model

    # Input
    if step.messages:
        obs["input"] = step.messages
    elif step.prompt:
        obs["input"] = step.prompt

    # Output
    if step.response_messages:
        obs["output"] = step.response_messages
    elif step.response:
        obs["output"] = step.response

    # Model parameters
    model_params: dict[str, Any] = {}
    if step.temperature is not None:
        model_params["temperature"] = step.temperature
    if step.max_tokens is not None:
        model_params["max_tokens"] = step.max_tokens
    if model_params:
        obs["modelParameters"] = model_params

    # Usage (Langfuse format)
    if step.token_usage:
        obs["usage"] = {
            "input": step.token_usage.prompt_tokens,
            "output": step.token_usage.completion_tokens,
            "total": step.token_usage.total_tokens,
        }

    # Cost
    if step.cost_usd:
        obs["costDetails"] = {"total": step.cost_usd}

    # Completion metadata
    completion_start_time = None
    if step.finish_reason:
        obs.setdefault("metadata", {})["finish_reason"] = step.finish_reason

    # Level
    if step.error:
        obs["level"] = "ERROR"
        obs["statusMessage"] = step.error
    else:
        obs["level"] = "DEFAULT"

    return obs


def _tool_to_span(step: ToolCallStep, run_id: UUID) -> dict[str, Any]:
    """Convert ToolCallStep → Langfuse Span."""
    obs = _base_observation(step, run_id)
    obs["type"] = "SPAN"
    obs["name"] = f"tool_call: {step.tool_name}"

    obs["input"] = step.input.kwargs if step.input.kwargs else None
    obs["output"] = step.output.result if step.output else None

    if step.output and step.output.error:
        obs["level"] = "ERROR"
        obs["statusMessage"] = step.output.error
    else:
        obs["level"] = "DEFAULT"

    obs.setdefault("metadata", {})["tool_name"] = step.tool_name
    obs["metadata"]["success"] = step.success

    return obs


def _agent_to_span(step: AgentStep, run_id: UUID) -> dict[str, Any]:
    """Convert AgentStep → Langfuse Span."""
    obs = _base_observation(step, run_id)
    obs["type"] = "SPAN"
    obs["name"] = f"agent: {step.agent_name or 'unknown'} ({step.action})"

    obs["input"] = step.action_input
    obs["output"] = step.final_answer if step.action == "finish" else step.action_output

    if step.error:
        obs["level"] = "ERROR"
        obs["statusMessage"] = step.error
    else:
        obs["level"] = "DEFAULT"

    md = obs.setdefault("metadata", {})
    if step.agent_name:
        md["agent_name"] = step.agent_name
    if step.agent_type:
        md["agent_type"] = step.agent_type
    md["action"] = step.action
    if step.thought:
        md["thought"] = step.thought

    return obs


def _chain_to_span(step: ChainStep, run_id: UUID) -> dict[str, Any]:
    """Convert ChainStep → Langfuse Span."""
    obs = _base_observation(step, run_id)
    obs["type"] = "SPAN"
    obs["name"] = f"chain: {step.chain_name}"

    obs["input"] = step.input if step.input else None
    obs["output"] = step.output if step.output else None

    if step.error:
        obs["level"] = "ERROR"
        obs["statusMessage"] = step.error
    else:
        obs["level"] = "DEFAULT"

    md = obs.setdefault("metadata", {})
    md["chain_name"] = step.chain_name
    if step.chain_type:
        md["chain_type"] = step.chain_type

    return obs


def _retrieval_to_span(step: RetrievalStep, run_id: UUID) -> dict[str, Any]:
    """Convert RetrievalStep → Langfuse Span."""
    obs = _base_observation(step, run_id)
    obs["type"] = "SPAN"
    obs["name"] = f"retrieval: {step.index_name or 'default'}"

    obs["input"] = {"query": step.query}
    if step.results:
        obs["output"] = {
            "documents": step.results.documents,
            "scores": step.results.scores,
        }

    if step.error:
        obs["level"] = "ERROR"
        obs["statusMessage"] = step.error
    else:
        obs["level"] = "DEFAULT"

    md = obs.setdefault("metadata", {})
    if step.index_name:
        md["index_name"] = step.index_name
    if step.top_k is not None:
        md["top_k"] = step.top_k
    if step.results:
        md["result_count"] = len(step.results.documents)

    return obs


def _reasoning_to_span(step: ReasoningStep, run_id: UUID) -> dict[str, Any]:
    """Convert ReasoningStep → Langfuse Span."""
    obs = _base_observation(step, run_id)
    obs["type"] = "SPAN"
    obs["name"] = f"reasoning: {step.reasoning_type or 'thought'}"

    obs["input"] = step.context
    obs["output"] = step.thought

    obs["level"] = "DEFAULT"

    md = obs.setdefault("metadata", {})
    if step.reasoning_type:
        md["reasoning_type"] = step.reasoning_type
    if step.conclusions:
        md["conclusions"] = step.conclusions

    return obs


def _error_to_event(step: ErrorStep, run_id: UUID) -> dict[str, Any]:
    """Convert ErrorStep → Langfuse Event."""
    obs = _base_observation(step, run_id)
    obs["type"] = "EVENT"
    obs["name"] = f"error: {step.error_type}"
    obs["level"] = "ERROR"
    obs["statusMessage"] = step.error_message

    obs["input"] = {
        "error_type": step.error_type,
        "error_message": step.error_message,
    }
    if step.error_traceback:
        obs["input"]["traceback"] = step.error_traceback

    obs["output"] = None
    if step.recovered:
        obs["output"] = {"recovered": True, "recovery_action": step.recovery_action}

    return obs


def _custom_to_event(step: CustomStep, run_id: UUID) -> dict[str, Any]:
    """Convert CustomStep → Langfuse Event."""
    obs = _base_observation(step, run_id)
    obs["type"] = "EVENT"
    obs["name"] = f"custom: {step.event_name}"
    obs["level"] = "DEFAULT"
    obs["input"] = step.data if step.data else None
    return obs


def _generic_span(step: AnyStep, run_id: UUID) -> dict[str, Any]:
    """Fallback: convert unknown step type to a Langfuse Span."""
    obs = _base_observation(step, run_id)
    obs["type"] = "SPAN"
    obs["name"] = f"{step.step_type}: step_{step.step_number}"
    obs["level"] = "DEFAULT"
    return obs


# ---------------------------------------------------------------------------
# Live export helpers
# ---------------------------------------------------------------------------


def _add_live_observation(trace: Any, step: AnyStep, run_id: UUID) -> None:
    """Add a step as an observation to a live Langfuse trace."""
    if isinstance(step, LLMCallStep):
        kwargs: dict[str, Any] = {
            "id": str(step.step_id),
            "name": f"llm_call: {step.model}",
            "model": step.model,
            "start_time": step.timestamp_start,
            "end_time": step.timestamp_end,
        }
        if step.messages:
            kwargs["input"] = step.messages
        elif step.prompt:
            kwargs["input"] = step.prompt
        if step.response_messages:
            kwargs["output"] = step.response_messages
        elif step.response:
            kwargs["output"] = step.response
        if step.token_usage:
            kwargs["usage"] = {
                "input": step.token_usage.prompt_tokens,
                "output": step.token_usage.completion_tokens,
                "total": step.token_usage.total_tokens,
            }
        model_params: dict[str, Any] = {}
        if step.temperature is not None:
            model_params["temperature"] = step.temperature
        if step.max_tokens is not None:
            model_params["max_tokens"] = step.max_tokens
        if model_params:
            kwargs["model_parameters"] = model_params
        if step.parent_step_id:
            kwargs["parent_observation_id"] = str(step.parent_step_id)
        if step.error:
            kwargs["level"] = "ERROR"
            kwargs["status_message"] = step.error
        trace.generation(**kwargs)
    elif isinstance(step, ErrorStep):
        trace.event(
            id=str(step.step_id),
            name=f"error: {step.error_type}",
            start_time=step.timestamp_start,
            input={"error_type": step.error_type, "error_message": step.error_message},
            level="ERROR",
            status_message=step.error_message,
            parent_observation_id=str(step.parent_step_id) if step.parent_step_id else None,
        )
    else:
        # All other types become spans
        name = _span_name_for_step(step)
        input_data = _span_input_for_step(step)
        output_data = _span_output_for_step(step)
        trace.span(
            id=str(step.step_id),
            name=name,
            start_time=step.timestamp_start,
            end_time=step.timestamp_end,
            input=input_data,
            output=output_data,
            parent_observation_id=str(step.parent_step_id) if step.parent_step_id else None,
        )


def _span_name_for_step(step: AnyStep) -> str:
    """Get span name for non-LLM, non-error steps."""
    if isinstance(step, ToolCallStep):
        return f"tool_call: {step.tool_name}"
    elif isinstance(step, AgentStep):
        return f"agent: {step.agent_name or 'unknown'} ({step.action})"
    elif isinstance(step, ChainStep):
        return f"chain: {step.chain_name}"
    elif isinstance(step, RetrievalStep):
        return f"retrieval: {step.index_name or 'default'}"
    elif isinstance(step, CustomStep):
        return f"custom: {step.event_name}"
    return f"{step.step_type}: step_{step.step_number}"


def _span_input_for_step(step: AnyStep) -> Any:
    """Get input data for a span."""
    if isinstance(step, ToolCallStep):
        return step.input.kwargs if step.input.kwargs else None
    elif isinstance(step, AgentStep):
        return step.action_input
    elif isinstance(step, ChainStep):
        return step.input if step.input else None
    elif isinstance(step, RetrievalStep):
        return {"query": step.query}
    return None


def _span_output_for_step(step: AnyStep) -> Any:
    """Get output data for a span."""
    if isinstance(step, ToolCallStep):
        return step.output.result if step.output else None
    elif isinstance(step, AgentStep):
        return step.final_answer if step.action == "finish" else step.action_output
    elif isinstance(step, ChainStep):
        return step.output if step.output else None
    elif isinstance(step, RetrievalStep) and step.results:
        return {"documents": step.results.documents, "scores": step.results.scores}
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_timestamp(dt: datetime | None) -> str | None:
    """Format datetime to ISO 8601 string."""
    if dt is None:
        return None
    # Langfuse expects ISO 8601 with timezone
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
