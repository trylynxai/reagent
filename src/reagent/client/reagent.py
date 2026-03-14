"""ReAgent - Main SDK client for recording and replaying agent executions."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from reagent.alerts.engine import AlertEngine
from reagent.core.config import Config
from reagent.core.constants import TransportMode, StorageType
from reagent.core.exceptions import ReAgentError
from reagent.client.context import RunContext
from reagent.client.transport import Transport, create_transport
from reagent.redaction.engine import RedactionEngine
from reagent.redaction.rules import RedactionRuleSet
from reagent.schema.run import RunConfig, RunMetadata, Run, RunSummary
from reagent.schema.steps import AnyStep
from reagent.storage.base import StorageBackend, RunFilter, Pagination
from reagent.storage.memory import MemoryStorage
from reagent.storage.jsonl import JSONLStorage
from reagent.storage.sqlite import SQLiteStorage


class ReAgent:
    """Main ReAgent client for recording and replaying agent executions.

    Usage:
        # Initialize
        reagent = ReAgent()

        # Record a run
        with reagent.trace(RunConfig(name="my-run")) as ctx:
            ctx.record_llm_call(...)
            ctx.record_tool_call(...)

        # List runs
        runs = reagent.list_runs()

        # Load a run
        run = reagent.load_run(run_id)
    """

    def __init__(
        self,
        config: Config | None = None,
        config_path: str | Path | None = None,
        storage: StorageBackend | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the ReAgent client.

        Args:
            config: Configuration object
            config_path: Path to configuration file
            storage: Optional storage backend (auto-created from config if not provided)
            **kwargs: Runtime configuration overrides
        """
        # Handle server_url/api_key shorthand in kwargs
        server_url = kwargs.pop("server_url", None)
        api_key = kwargs.pop("api_key", None)
        if server_url:
            kwargs.setdefault("server", {})
            kwargs["server"]["url"] = server_url
        if api_key:
            kwargs.setdefault("server", {})
            kwargs["server"]["api_key"] = api_key

        # Load configuration
        self._config = config or Config.load(config_path=config_path, runtime_overrides=kwargs)

        # Initialize storage
        self._storage = storage or self._create_storage()

        # Initialize transport
        self._transport = self._create_transport()

        # Initialize redaction engine
        self._redaction_engine = self._create_redaction_engine()

        # Initialize alert engine (if configured)
        self._alert_engine: AlertEngine | None = None

        # Track active runs
        self._active_runs: dict[UUID, RunContext] = {}

    @property
    def config(self) -> Config:
        """Get the configuration."""
        return self._config

    @property
    def storage(self) -> StorageBackend:
        """Get the storage backend."""
        return self._storage

    @property
    def alert_engine(self) -> AlertEngine | None:
        """Get the alert engine (if configured)."""
        return self._alert_engine

    def set_alert_engine(self, engine: AlertEngine) -> None:
        """Set the alert engine for this client."""
        self._alert_engine = engine

    def _is_remote_mode(self) -> bool:
        """Check if the client should operate in remote mode."""
        return self._config.mode == "remote" or self._config.server.url is not None

    def _create_storage(self) -> StorageBackend:
        """Create storage backend from configuration."""
        if self._is_remote_mode():
            from reagent.storage.remote import RemoteStorage
            return RemoteStorage(
                server_url=self._config.server.url,
                api_key=self._config.server.api_key,
                timeout_seconds=self._config.server.timeout_seconds,
            )

        storage_config = self._config.storage

        if storage_config.type == StorageType.MEMORY:
            return MemoryStorage()
        elif storage_config.type == StorageType.JSONL:
            return JSONLStorage(base_path=storage_config.path)
        elif storage_config.type == StorageType.SQLITE:
            db_path = Path(storage_config.path)
            if db_path.is_dir():
                db_path = db_path / "traces.db"
            return SQLiteStorage(db_path=db_path)
        else:
            raise ReAgentError(f"Unknown storage type: {storage_config.type}")

    def _create_transport(self) -> Transport:
        """Create transport from configuration."""
        if self._is_remote_mode():
            from reagent.client.transport import RemoteTransport
            srv = self._config.server
            return RemoteTransport(
                server_url=srv.url,
                api_key=srv.api_key,
                batch_size=srv.batch_size,
                flush_interval_ms=srv.flush_interval_ms,
                timeout_seconds=srv.timeout_seconds,
                retry_max=srv.retry_max,
                fallback_to_local=srv.fallback_to_local,
            )

        return create_transport(
            mode=self._config.transport_mode,
            storage=self._storage,
            batch_size=self._config.buffer.size,
            flush_interval_ms=self._config.buffer.flush_interval_ms,
        )

    def _create_redaction_engine(self) -> RedactionEngine:
        """Create redaction engine from configuration."""
        redaction_config = self._config.redaction

        rules = RedactionRuleSet(
            enabled=redaction_config.enabled,
            default_mode=redaction_config.mode,
        )

        return RedactionEngine(
            rules=rules,
            timeout_ms=redaction_config.timeout_ms,
            use_nlp=redaction_config.use_nlp,
            nlp_entities=redaction_config.nlp_entities,
            nlp_language=redaction_config.nlp_language,
            nlp_score_threshold=redaction_config.nlp_score_threshold,
        )

    def trace(
        self,
        config: RunConfig | None = None,
        run_id: UUID | None = None,
    ) -> RunContext:
        """Create a new run context for recording.

        Args:
            config: Run configuration
            run_id: Optional run ID

        Returns:
            RunContext for recording the run
        """
        ctx = RunContext(client=self, config=config, run_id=run_id)
        self._active_runs[ctx.run_id] = ctx
        return ctx

    def _start_run(self, run_id: UUID, metadata: RunMetadata) -> None:
        """Internal: Start a run."""
        self._transport.send_metadata(run_id, metadata)

    def _end_run(self, run_id: UUID, metadata: RunMetadata) -> None:
        """Internal: End a run."""
        # Update final metadata
        self._transport.send_metadata(run_id, metadata)
        self._transport.flush()

        # Check alert rules at run end
        if self._alert_engine is not None:
            try:
                self._alert_engine.check_run_end(metadata)
            except Exception:
                pass  # Alert errors must not break the pipeline

        # Remove from active runs
        self._active_runs.pop(run_id, None)

    def _record_step(self, run_id: UUID, step: AnyStep) -> None:
        """Internal: Record a step."""
        # Apply redaction if enabled
        if self._redaction_engine.rules.enabled:
            step = self._redact_step(step)

        self._transport.send_step(run_id, step)

        # Check budget alert rules after recording
        if self._alert_engine is not None:
            ctx = self._active_runs.get(run_id)
            if ctx is not None:
                try:
                    self._alert_engine.check_step(ctx.metadata, step)
                except Exception:
                    pass  # Alert errors must not break the pipeline

    def _redact_step(self, step: AnyStep) -> AnyStep:
        """Apply redaction to a step."""
        # Convert to dict, redact, and convert back
        step_dict = step.model_dump()
        redacted_dict = self._redaction_engine.redact_dict(step_dict)

        # Reconstruct step
        step_class = type(step)
        return step_class.model_validate(redacted_dict)

    def flush(self) -> None:
        """Flush any pending events."""
        self._transport.flush()

    def close(self) -> None:
        """Close the client and release resources."""
        self.flush()
        self._transport.close()
        self._storage.close()

    # Storage operations

    def load_run(self, run_id: UUID | str) -> Run:
        """Load a complete run with all steps.

        Args:
            run_id: Run ID to load

        Returns:
            Complete run with metadata and steps
        """
        if isinstance(run_id, str):
            run_id = UUID(run_id)
        return self._storage.load_run(run_id)

    def load_metadata(self, run_id: UUID | str) -> RunMetadata:
        """Load only run metadata (faster for listings).

        Args:
            run_id: Run ID to load

        Returns:
            Run metadata
        """
        if isinstance(run_id, str):
            run_id = UUID(run_id)
        return self._storage.load_metadata(run_id)

    def list_runs(
        self,
        project: str | None = None,
        status: str | list[str] | None = None,
        model: str | None = None,
        tags: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "start_time",
        sort_order: str = "desc",
    ) -> list[RunSummary]:
        """List runs with optional filtering.

        Args:
            project: Filter by project
            status: Filter by status
            model: Filter by model
            tags: Filter by tags (all must match)
            limit: Maximum results
            offset: Skip first N results
            sort_by: Sort field (start_time, duration, cost, steps)
            sort_order: Sort order (asc, desc)

        Returns:
            List of run summaries
        """
        from reagent.core.constants import Status

        # Build filter
        status_filter = None
        if status:
            if isinstance(status, str):
                status_filter = Status(status)
            else:
                status_filter = [Status(s) for s in status]

        filters = RunFilter(
            project=project,
            status=status_filter,
            model=model,
            tags=tags,
        )

        pagination = Pagination(
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return self._storage.list_runs(filters=filters, pagination=pagination)

    def search_runs(
        self,
        query: str,
        project: str | None = None,
        limit: int = 50,
    ) -> list[RunSummary]:
        """Search runs by text query.

        Args:
            query: Search query
            project: Optional project filter
            limit: Maximum results

        Returns:
            List of matching run summaries
        """
        filters = RunFilter(project=project) if project else None
        pagination = Pagination(limit=limit)
        return self._storage.search(query, filters=filters, pagination=pagination)

    def delete_run(self, run_id: UUID | str) -> bool:
        """Delete a run.

        Args:
            run_id: Run ID to delete

        Returns:
            True if deleted, False if not found
        """
        if isinstance(run_id, str):
            run_id = UUID(run_id)
        return self._storage.delete_run(run_id)

    def count_runs(self, project: str | None = None) -> int:
        """Count runs.

        Args:
            project: Optional project filter

        Returns:
            Number of runs
        """
        filters = RunFilter(project=project) if project else None
        return self._storage.count_runs(filters)

    # Context manager support

    def __enter__(self) -> ReAgent:
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit."""
        self.close()


# Global client instance (optional convenience)
_global_client: ReAgent | None = None


def get_client() -> ReAgent:
    """Get the global ReAgent client instance.

    Creates one if it doesn't exist.
    """
    global _global_client
    if _global_client is None:
        _global_client = ReAgent()
    return _global_client


def set_client(client: ReAgent) -> None:
    """Set the global ReAgent client instance."""
    global _global_client
    _global_client = client


def trace(config: RunConfig | None = None, run_id: UUID | None = None) -> RunContext:
    """Convenience function to start a trace using the global client."""
    return get_client().trace(config=config, run_id=run_id)
