"""OTLP export - Convert ReAgent runs to OpenTelemetry protobuf JSON.

Two modes:
- File export (run_to_otlp_json): zero external deps, outputs standard OTLP JSON
- Live export (export_otlp_live): sends spans to an OTLP collector endpoint
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from reagent.schema.run import Run, RunMetadata
from reagent.schema.steps import (
    AgentStep,
    AnyStep,
    ChainStep,
    CheckpointStep,
    CustomStep,
    ErrorStep,
    LLMCallStep,
    ReasoningStep,
    RetrievalStep,
    ToolCallStep,
)

# OTLP span kind constants
_SPAN_KIND_INTERNAL = 1
_SPAN_KIND_CLIENT = 3

# OTLP status codes
_STATUS_UNSET = 0
_STATUS_OK = 1
_STATUS_ERROR = 2


def run_to_otlp_json(run: Run) -> dict[str, Any]:
    """Convert a Run to an OTLP protobuf JSON dict.

    Zero external dependencies. The output conforms to the OTLP JSON encoding
    and can be imported by any OTLP-compatible backend (Jaeger, Grafana Tempo, etc.).
    """
    meta = run.metadata
    trace_id = _uuid_to_trace_id(meta.run_id)
    root_span_id = _uuid_to_span_id(meta.run_id)

    # Build step_id -> span_id mapping for parent references
    step_id_map: dict[str, str] = {}
    for step in run.steps:
        step_id_map[str(step.step_id)] = _uuid_to_span_id(step.step_id)

    spans: list[dict[str, Any]] = []

    # Root span from run metadata
    spans.append(_run_to_root_span(meta, trace_id, root_span_id))

    # Child spans from steps
    for step in run.steps:
        spans.append(
            _step_to_span(step, trace_id, root_span_id, step_id_map)
        )

    # Resource attributes
    resource_attrs = [
        _make_attribute("service.name", "reagent"),
    ]
    if meta.project:
        resource_attrs.append(_make_attribute("reagent.project", meta.project))

    return {
        "resourceSpans": [
            {
                "resource": {"attributes": resource_attrs},
                "scopeSpans": [
                    {
                        "scope": {"name": "reagent", "version": "0.1.0"},
                        "spans": spans,
                    }
                ],
            }
        ]
    }


def export_otlp_live(
    run: Run,
    endpoint: str,
    headers: dict[str, str] | None = None,
) -> None:
    """Send spans to an OTLP collector endpoint.

    Requires ``opentelemetry-sdk`` and ``opentelemetry-exporter-otlp-proto-http``.
    Install with: ``pip install reagent[otlp]``
    """
    try:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
    except ImportError:
        raise ImportError(
            "Live OTLP export requires the OpenTelemetry SDK. "
            "Install with: pip install reagent[otlp]"
        )

    resource_attrs = {"service.name": "reagent"}
    if run.metadata.project:
        resource_attrs["reagent.project"] = run.metadata.project

    resource = Resource.create(resource_attrs)
    provider = TracerProvider(resource=resource)

    exporter_kwargs: dict[str, Any] = {"endpoint": endpoint}
    if headers:
        exporter_kwargs["headers"] = headers

    exporter = OTLPSpanExporter(**exporter_kwargs)
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    tracer = provider.get_tracer("reagent", "0.1.0")

    meta = run.metadata

    # Create root span
    with tracer.start_as_current_span(
        f"run: {meta.name or str(meta.run_id)[:8]}",
    ) as root_span:
        _set_root_span_attributes(root_span, meta)

        # Create child spans for each step
        for step in run.steps:
            name, kind, attrs = _step_span_info(step)
            with tracer.start_as_current_span(name) as child_span:
                for key, value in attrs:
                    if value is not None:
                        child_span.set_attribute(key, value)

    provider.shutdown()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _run_to_root_span(
    meta: RunMetadata,
    trace_id: str,
    span_id: str,
) -> dict[str, Any]:
    """Build the root span dict from run metadata."""
    name = f"run: {meta.name or str(meta.run_id)[:8]}"

    attrs = [
        _make_attribute("reagent.run.id", str(meta.run_id)),
    ]
    if meta.project:
        attrs.append(_make_attribute("reagent.run.project", meta.project))
    attrs.append(_make_attribute("reagent.run.status", meta.status.value))
    if meta.framework:
        attrs.append(_make_attribute("gen_ai.system", meta.framework))
    if meta.model:
        attrs.append(_make_attribute("gen_ai.request.model", meta.model))
    if meta.tokens.total_tokens:
        attrs.append(
            _make_attribute("reagent.run.total_tokens", meta.tokens.total_tokens)
        )
    if meta.cost.total_usd:
        attrs.append(
            _make_attribute("reagent.run.total_cost_usd", meta.cost.total_usd)
        )

    has_error = meta.status.value == "failed"
    span: dict[str, Any] = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "kind": _SPAN_KIND_INTERNAL,
        "startTimeUnixNano": _timestamp_to_nanos(meta.start_time),
        "endTimeUnixNano": _timestamp_to_nanos(meta.end_time) if meta.end_time else _timestamp_to_nanos(meta.start_time),
        "attributes": attrs,
        "status": _status_to_otlp(meta.status.value, has_error),
    }
    return span


def _step_to_span(
    step: AnyStep,
    trace_id: str,
    root_span_id: str,
    step_id_map: dict[str, str],
) -> dict[str, Any]:
    """Build a child span dict from a step."""
    name, kind, step_attrs = _step_span_info(step)

    # Common attributes on all step spans
    attrs = [
        _make_attribute("reagent.step.number", step.step_number),
        _make_attribute("reagent.step.type", step.step_type),
    ]
    if step.duration_ms is not None:
        attrs.append(_make_attribute("reagent.step.duration_ms", step.duration_ms))

    # Type-specific attributes
    for key, value in step_attrs:
        if value is not None:
            attrs.append(_make_attribute(key, value))

    # Determine parent span
    parent_span_id = root_span_id
    if step.parent_step_id:
        parent_key = str(step.parent_step_id)
        if parent_key in step_id_map:
            parent_span_id = step_id_map[parent_key]

    span_id = _uuid_to_span_id(step.step_id)

    # Determine status
    has_error = isinstance(step, ErrorStep) or _step_has_error(step)

    end_time = step.timestamp_end or step.timestamp_start
    span: dict[str, Any] = {
        "traceId": trace_id,
        "spanId": span_id,
        "parentSpanId": parent_span_id,
        "name": name,
        "kind": kind,
        "startTimeUnixNano": _timestamp_to_nanos(step.timestamp_start),
        "endTimeUnixNano": _timestamp_to_nanos(end_time),
        "attributes": attrs,
        "status": _status_to_otlp("error" if has_error else "ok", has_error),
    }
    return span


def _step_span_info(
    step: AnyStep,
) -> tuple[str, int, list[tuple[str, Any]]]:
    """Return (span_name, span_kind, [(attr_key, attr_value), ...]) for a step."""
    if isinstance(step, LLMCallStep):
        return (
            f"llm_call: {step.model}",
            _SPAN_KIND_CLIENT,
            [
                ("gen_ai.request.model", step.model),
                ("gen_ai.request.temperature", step.temperature),
                (
                    "gen_ai.usage.input_tokens",
                    step.token_usage.prompt_tokens if step.token_usage else None,
                ),
                (
                    "gen_ai.usage.output_tokens",
                    step.token_usage.completion_tokens if step.token_usage else None,
                ),
                ("gen_ai.response.finish_reasons", step.finish_reason),
            ],
        )

    if isinstance(step, ToolCallStep):
        return (
            f"tool_call: {step.tool_name}",
            _SPAN_KIND_CLIENT,
            [
                ("reagent.tool.name", step.tool_name),
                ("reagent.tool.success", step.success),
            ],
        )

    if isinstance(step, RetrievalStep):
        result_count = None
        if step.results and step.results.documents:
            result_count = len(step.results.documents)
        return (
            f"retrieval: {step.index_name or 'default'}",
            _SPAN_KIND_CLIENT,
            [
                ("reagent.retrieval.query", step.query),
                ("reagent.retrieval.top_k", step.top_k),
                ("reagent.retrieval.result_count", result_count),
            ],
        )

    if isinstance(step, ChainStep):
        return (
            f"chain: {step.chain_name}",
            _SPAN_KIND_INTERNAL,
            [
                ("reagent.chain.name", step.chain_name),
                ("reagent.chain.type", step.chain_type),
            ],
        )

    if isinstance(step, AgentStep):
        return (
            f"agent: {step.agent_name or 'unnamed'}",
            _SPAN_KIND_INTERNAL,
            [
                ("reagent.agent.name", step.agent_name),
                ("reagent.agent.action", step.action),
            ],
        )

    if isinstance(step, ErrorStep):
        return (
            f"error: {step.error_type}",
            _SPAN_KIND_INTERNAL,
            [
                ("exception.type", step.error_type),
                ("exception.message", step.error_message),
            ],
        )

    if isinstance(step, ReasoningStep):
        return (
            f"reasoning: {step.reasoning_type or 'thinking'}",
            _SPAN_KIND_INTERNAL,
            [
                ("reagent.reasoning.type", step.reasoning_type),
            ],
        )

    if isinstance(step, CheckpointStep):
        return (
            f"checkpoint: {step.checkpoint_name or 'unnamed'}",
            _SPAN_KIND_INTERNAL,
            [
                ("reagent.checkpoint.name", step.checkpoint_name),
                ("reagent.checkpoint.state_size_bytes", step.state_size_bytes),
            ],
        )

    if isinstance(step, CustomStep):
        return (
            f"custom: {step.event_name}",
            _SPAN_KIND_INTERNAL,
            [
                ("reagent.custom.event_name", step.event_name),
            ],
        )

    # Fallback for unknown step types
    step_type = getattr(step, "step_type", "unknown")
    return (f"{step_type}: step", _SPAN_KIND_INTERNAL, [])


def _step_has_error(step: AnyStep) -> bool:
    """Check if a step has an error field set."""
    error = getattr(step, "error", None)
    if error:
        return True
    # ToolCallStep uses success field
    if isinstance(step, ToolCallStep) and not step.success:
        return True
    return False


def _make_attribute(key: str, value: Any) -> dict[str, Any]:
    """Create an OTLP attribute dict with proper type mapping."""
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    # Default to string
    return {"key": key, "value": {"stringValue": str(value)}}


def _timestamp_to_nanos(dt: datetime) -> str:
    """Convert a datetime to nanosecond epoch string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    epoch_seconds = dt.timestamp()
    return str(int(epoch_seconds * 1_000_000_000))


def _uuid_to_trace_id(uuid: UUID) -> str:
    """Convert a UUID to a 32 hex char trace ID."""
    return uuid.hex[:32]


def _uuid_to_span_id(uuid: UUID) -> str:
    """Convert a UUID to a 16 hex char span ID."""
    return uuid.hex[:16]


def _status_to_otlp(status: str, has_error: bool) -> dict[str, int]:
    """Map a status string to an OTLP status dict."""
    if has_error:
        return {"code": _STATUS_ERROR}
    if status in ("completed", "ok"):
        return {"code": _STATUS_OK}
    return {"code": _STATUS_UNSET}


def _set_root_span_attributes(span: Any, meta: RunMetadata) -> None:
    """Set attributes on a live OTel root span object."""
    span.set_attribute("reagent.run.id", str(meta.run_id))
    if meta.project:
        span.set_attribute("reagent.run.project", meta.project)
    span.set_attribute("reagent.run.status", meta.status.value)
    if meta.framework:
        span.set_attribute("gen_ai.system", meta.framework)
    if meta.model:
        span.set_attribute("gen_ai.request.model", meta.model)
    if meta.tokens.total_tokens:
        span.set_attribute("reagent.run.total_tokens", meta.tokens.total_tokens)
    if meta.cost.total_usd:
        span.set_attribute("reagent.run.total_cost_usd", meta.cost.total_usd)
