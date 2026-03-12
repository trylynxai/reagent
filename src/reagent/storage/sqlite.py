"""SQLite storage backend with indexing and full-text search."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID

from reagent.core.constants import Status
from reagent.core.exceptions import TraceNotFoundError, StorageError
from reagent.schema.run import Run, RunMetadata, RunSummary
from reagent.schema.steps import (
    AnyStep,
    LLMCallStep,
    ToolCallStep,
    RetrievalStep,
    ChainStep,
    AgentStep,
    ReasoningStep,
    ErrorStep,
    CheckpointStep,
    CustomStep,
)
from reagent.storage.base import StorageBackend, RunFilter, Pagination


STEP_TYPE_MAP = {
    "llm_call": LLMCallStep,
    "tool_call": ToolCallStep,
    "retrieval": RetrievalStep,
    "chain": ChainStep,
    "agent": AgentStep,
    "reasoning": ReasoningStep,
    "error": ErrorStep,
    "checkpoint": CheckpointStep,
    "custom": CustomStep,
}


class SQLiteStorage(StorageBackend):
    """SQLite storage backend with indexing and FTS5 search.

    Provides fast queries and full-text search capabilities.
    """

    def __init__(self, db_path: str | Path = ".reagent/traces.db") -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize database schema."""
        with self._cursor() as cursor:
            # Runs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    name TEXT,
                    project TEXT,
                    tags TEXT,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    duration_ms INTEGER,
                    status TEXT NOT NULL,
                    model TEXT,
                    models_used TEXT,
                    total_tokens INTEGER DEFAULT 0,
                    prompt_tokens INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    total_cost_usd REAL DEFAULT 0,
                    step_count INTEGER DEFAULT 0,
                    error TEXT,
                    error_type TEXT,
                    failure_category TEXT,
                    input_data TEXT,
                    output_data TEXT,
                    custom_metadata TEXT,
                    schema_version TEXT DEFAULT '1.0'
                )
            """)

            # Steps table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS steps (
                    step_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    parent_step_id TEXT,
                    step_number INTEGER NOT NULL,
                    step_type TEXT NOT NULL,
                    timestamp_start TEXT NOT NULL,
                    timestamp_end TEXT,
                    duration_ms INTEGER,
                    data TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs (run_id) ON DELETE CASCADE
                )
            """)

            # Indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_project ON runs (project)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_status ON runs (status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_start_time ON runs (start_time DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_model ON runs (model)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_steps_run_id ON steps (run_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_steps_step_type ON steps (step_type)
            """)

            # Full-text search table
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS runs_fts USING fts5(
                    run_id,
                    name,
                    tags,
                    error,
                    content='runs',
                    content_rowid='rowid'
                )
            """)

            # FTS triggers
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS runs_ai AFTER INSERT ON runs BEGIN
                    INSERT INTO runs_fts(rowid, run_id, name, tags, error)
                    VALUES (NEW.rowid, NEW.run_id, NEW.name, NEW.tags, NEW.error);
                END
            """)

            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS runs_ad AFTER DELETE ON runs BEGIN
                    INSERT INTO runs_fts(runs_fts, rowid, run_id, name, tags, error)
                    VALUES('delete', OLD.rowid, OLD.run_id, OLD.name, OLD.tags, OLD.error);
                END
            """)

            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS runs_au AFTER UPDATE ON runs BEGIN
                    INSERT INTO runs_fts(runs_fts, rowid, run_id, name, tags, error)
                    VALUES('delete', OLD.rowid, OLD.run_id, OLD.name, OLD.tags, OLD.error);
                    INSERT INTO runs_fts(rowid, run_id, name, tags, error)
                    VALUES (NEW.rowid, NEW.run_id, NEW.name, NEW.tags, NEW.error);
                END
            """)

            self._conn.commit()

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        """Get a database cursor."""
        cursor = self._conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    def save_run(self, run_id: UUID, metadata: RunMetadata) -> None:
        """Save or update run metadata."""
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, name, project, tags, start_time, end_time, duration_ms,
                    status, model, models_used, total_tokens, prompt_tokens,
                    completion_tokens, total_cost_usd, step_count, error, error_type,
                    failure_category, input_data, output_data, custom_metadata, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(run_id),
                    metadata.name,
                    metadata.project,
                    json.dumps(metadata.tags),
                    metadata.start_time.isoformat(),
                    metadata.end_time.isoformat() if metadata.end_time else None,
                    metadata.duration_ms,
                    metadata.status.value,
                    metadata.model,
                    json.dumps(metadata.models_used),
                    metadata.tokens.total_tokens,
                    metadata.tokens.prompt_tokens,
                    metadata.tokens.completion_tokens,
                    metadata.cost.total_usd,
                    metadata.steps.total,
                    metadata.error,
                    metadata.error_type,
                    metadata.failure_category,
                    json.dumps(metadata.input) if metadata.input else None,
                    json.dumps(metadata.output) if metadata.output else None,
                    json.dumps(metadata.custom),
                    metadata.schema_version,
                ),
            )
            self._conn.commit()

    def save_step(self, run_id: UUID, step: AnyStep) -> None:
        """Save a step to the run."""
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO steps (
                    step_id, run_id, parent_step_id, step_number, step_type,
                    timestamp_start, timestamp_end, duration_ms, data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(step.step_id),
                    str(run_id),
                    str(step.parent_step_id) if step.parent_step_id else None,
                    step.step_number,
                    step.step_type,
                    step.timestamp_start.isoformat(),
                    step.timestamp_end.isoformat() if step.timestamp_end else None,
                    step.duration_ms,
                    json.dumps(step.model_dump(mode="json"), default=str),
                ),
            )
            self._conn.commit()

    def load_run(self, run_id: UUID) -> Run:
        """Load a complete run with all steps."""
        metadata = self.load_metadata(run_id)
        steps = list(self.load_steps(run_id))
        return Run(metadata=metadata, steps=steps)

    def load_metadata(self, run_id: UUID) -> RunMetadata:
        """Load only run metadata."""
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM runs WHERE run_id = ?", (str(run_id),))
            row = cursor.fetchone()

            if row is None:
                raise TraceNotFoundError(str(run_id))

            return self._row_to_metadata(row)

    def load_steps(
        self,
        run_id: UUID,
        start: int | None = None,
        end: int | None = None,
        step_type: str | None = None,
    ) -> Iterator[AnyStep]:
        """Load steps from a run with optional filtering."""
        # First check if run exists
        if not self.exists(run_id):
            raise TraceNotFoundError(str(run_id))

        query = "SELECT data FROM steps WHERE run_id = ?"
        params: list[Any] = [str(run_id)]

        if start is not None:
            query += " AND step_number >= ?"
            params.append(start)

        if end is not None:
            query += " AND step_number < ?"
            params.append(end)

        if step_type is not None:
            query += " AND step_type = ?"
            params.append(step_type)

        query += " ORDER BY step_number"

        with self._cursor() as cursor:
            cursor.execute(query, params)

            for row in cursor:
                data = json.loads(row["data"])
                step_class = STEP_TYPE_MAP.get(data.get("step_type", "custom"), CustomStep)
                yield step_class.model_validate(data)

    def list_runs(
        self,
        filters: RunFilter | None = None,
        pagination: Pagination | None = None,
    ) -> list[RunSummary]:
        """List runs matching the given criteria."""
        filters = filters or RunFilter()
        pagination = pagination or Pagination()

        query = "SELECT * FROM runs"
        params: list[Any] = []
        conditions: list[str] = []

        # Build WHERE clause
        if filters.project:
            conditions.append("project = ?")
            params.append(filters.project)

        if filters.status:
            if isinstance(filters.status, list):
                placeholders = ",".join("?" * len(filters.status))
                conditions.append(f"status IN ({placeholders})")
                params.extend(s.value for s in filters.status)
            else:
                conditions.append("status = ?")
                params.append(filters.status.value)

        if filters.model:
            conditions.append("model = ?")
            params.append(filters.model)

        if filters.since:
            conditions.append("start_time >= ?")
            params.append(filters.since.isoformat())

        if filters.until:
            conditions.append("start_time <= ?")
            params.append(filters.until.isoformat())

        if filters.min_cost_usd is not None:
            conditions.append("total_cost_usd >= ?")
            params.append(filters.min_cost_usd)

        if filters.max_cost_usd is not None:
            conditions.append("total_cost_usd <= ?")
            params.append(filters.max_cost_usd)

        if filters.min_duration_ms is not None:
            conditions.append("duration_ms >= ?")
            params.append(filters.min_duration_ms)

        if filters.max_duration_ms is not None:
            conditions.append("duration_ms <= ?")
            params.append(filters.max_duration_ms)

        if filters.has_error is True:
            conditions.append("error IS NOT NULL")
        elif filters.has_error is False:
            conditions.append("error IS NULL")

        if filters.failure_category:
            conditions.append("failure_category = ?")
            params.append(filters.failure_category)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        # Sorting
        sort_column = self._get_sort_column(pagination.sort_by)
        sort_order = "DESC" if pagination.sort_order == "desc" else "ASC"
        query += f" ORDER BY {sort_column} {sort_order}"

        # Pagination
        query += " LIMIT ? OFFSET ?"
        params.extend([pagination.limit, pagination.offset])

        with self._cursor() as cursor:
            cursor.execute(query, params)
            return [self._row_to_summary(row) for row in cursor]

    def search(
        self,
        query: str,
        filters: RunFilter | None = None,
        pagination: Pagination | None = None,
    ) -> list[RunSummary]:
        """Search runs by text query using FTS5."""
        filters = filters or RunFilter()
        pagination = pagination or Pagination()

        # Use FTS5 for text search
        sql = """
            SELECT runs.* FROM runs
            JOIN runs_fts ON runs.run_id = runs_fts.run_id
            WHERE runs_fts MATCH ?
        """
        params: list[Any] = [query]

        # Add filters
        if filters.project:
            sql += " AND runs.project = ?"
            params.append(filters.project)

        if filters.status:
            if isinstance(filters.status, list):
                placeholders = ",".join("?" * len(filters.status))
                sql += f" AND runs.status IN ({placeholders})"
                params.extend(s.value for s in filters.status)
            else:
                sql += " AND runs.status = ?"
                params.append(filters.status.value)

        # Sorting and pagination
        sort_column = self._get_sort_column(pagination.sort_by)
        sort_order = "DESC" if pagination.sort_order == "desc" else "ASC"
        sql += f" ORDER BY runs.{sort_column} {sort_order}"
        sql += " LIMIT ? OFFSET ?"
        params.extend([pagination.limit, pagination.offset])

        with self._cursor() as cursor:
            try:
                cursor.execute(sql, params)
                return [self._row_to_summary(row) for row in cursor]
            except sqlite3.OperationalError:
                # Fallback to LIKE search if FTS fails
                return self._fallback_search(query, filters, pagination)

    def _fallback_search(
        self,
        query: str,
        filters: RunFilter,
        pagination: Pagination,
    ) -> list[RunSummary]:
        """Fallback search using LIKE."""
        sql = """
            SELECT * FROM runs
            WHERE (name LIKE ? OR tags LIKE ? OR error LIKE ?)
        """
        like_pattern = f"%{query}%"
        params: list[Any] = [like_pattern, like_pattern, like_pattern]

        if filters.project:
            sql += " AND project = ?"
            params.append(filters.project)

        sort_column = self._get_sort_column(pagination.sort_by)
        sort_order = "DESC" if pagination.sort_order == "desc" else "ASC"
        sql += f" ORDER BY {sort_column} {sort_order}"
        sql += " LIMIT ? OFFSET ?"
        params.extend([pagination.limit, pagination.offset])

        with self._cursor() as cursor:
            cursor.execute(sql, params)
            return [self._row_to_summary(row) for row in cursor]

    def delete_run(self, run_id: UUID) -> bool:
        """Delete a run and all its steps."""
        with self._cursor() as cursor:
            cursor.execute("DELETE FROM steps WHERE run_id = ?", (str(run_id),))
            cursor.execute("DELETE FROM runs WHERE run_id = ?", (str(run_id),))
            self._conn.commit()
            return cursor.rowcount > 0

    def exists(self, run_id: UUID) -> bool:
        """Check if a run exists."""
        with self._cursor() as cursor:
            cursor.execute("SELECT 1 FROM runs WHERE run_id = ?", (str(run_id),))
            return cursor.fetchone() is not None

    def count_runs(self, filters: RunFilter | None = None) -> int:
        """Count runs matching the given criteria."""
        query = "SELECT COUNT(*) FROM runs"
        params: list[Any] = []
        conditions: list[str] = []

        if filters:
            if filters.project:
                conditions.append("project = ?")
                params.append(filters.project)

            if filters.status:
                if isinstance(filters.status, list):
                    placeholders = ",".join("?" * len(filters.status))
                    conditions.append(f"status IN ({placeholders})")
                    params.extend(s.value for s in filters.status)
                else:
                    conditions.append("status = ?")
                    params.append(filters.status.value)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        with self._cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()[0]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def _row_to_metadata(self, row: sqlite3.Row) -> RunMetadata:
        """Convert a database row to RunMetadata."""
        from reagent.schema.run import CostSummary, TokenSummary, StepSummary

        return RunMetadata(
            run_id=UUID(row["run_id"]),
            name=row["name"],
            project=row["project"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            start_time=datetime.fromisoformat(row["start_time"]),
            end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
            duration_ms=row["duration_ms"],
            status=Status(row["status"]),
            model=row["model"],
            models_used=json.loads(row["models_used"]) if row["models_used"] else [],
            cost=CostSummary(total_usd=row["total_cost_usd"] or 0),
            tokens=TokenSummary(
                total_tokens=row["total_tokens"] or 0,
                prompt_tokens=row["prompt_tokens"] or 0,
                completion_tokens=row["completion_tokens"] or 0,
            ),
            steps=StepSummary(total=row["step_count"] or 0),
            error=row["error"],
            error_type=row["error_type"],
            failure_category=row["failure_category"],
            input=json.loads(row["input_data"]) if row["input_data"] else None,
            output=json.loads(row["output_data"]) if row["output_data"] else None,
            custom=json.loads(row["custom_metadata"]) if row["custom_metadata"] else {},
            schema_version=row["schema_version"],
        )

    def _row_to_summary(self, row: sqlite3.Row) -> RunSummary:
        """Convert a database row to RunSummary."""
        return RunSummary(
            run_id=UUID(row["run_id"]),
            name=row["name"],
            project=row["project"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            start_time=datetime.fromisoformat(row["start_time"]),
            end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
            duration_ms=row["duration_ms"],
            status=Status(row["status"]),
            model=row["model"],
            step_count=row["step_count"] or 0,
            total_tokens=row["total_tokens"] or 0,
            total_cost_usd=row["total_cost_usd"] or 0,
            error=row["error"],
            failure_category=row["failure_category"],
        )

    @staticmethod
    def _get_sort_column(sort_by: str) -> str:
        """Get database column name for sorting."""
        mapping = {
            "start_time": "start_time",
            "duration": "duration_ms",
            "cost": "total_cost_usd",
            "steps": "step_count",
        }
        return mapping.get(sort_by, "start_time")
