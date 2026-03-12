"""Search query parsing and execution."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from reagent.core.constants import Status
from reagent.storage.base import RunFilter


@dataclass
class SearchClause:
    """A single clause in a search query."""

    field: str | None  # None for full-text search
    operator: str  # "=", "!=", ">", "<", ">=", "<=", "contains", "like"
    value: Any
    negated: bool = False


@dataclass
class SearchQuery:
    """Parsed search query."""

    clauses: list[SearchClause] = field(default_factory=list)
    full_text: str | None = None
    logic: str = "and"  # "and" or "or"

    def to_filter(self) -> RunFilter:
        """Convert to a RunFilter.

        Returns:
            RunFilter for storage backend
        """
        filter_kwargs: dict[str, Any] = {}

        for clause in self.clauses:
            if clause.field == "project":
                filter_kwargs["project"] = clause.value
            elif clause.field == "status":
                if isinstance(clause.value, str):
                    filter_kwargs["status"] = Status(clause.value)
                else:
                    filter_kwargs["status"] = [Status(v) for v in clause.value]
            elif clause.field == "model":
                filter_kwargs["model"] = clause.value
            elif clause.field == "tags":
                filter_kwargs["tags"] = clause.value if isinstance(clause.value, list) else [clause.value]
            elif clause.field == "since" or (clause.field == "date" and clause.operator == ">"):
                filter_kwargs["since"] = self._parse_date(clause.value)
            elif clause.field == "until" or (clause.field == "date" and clause.operator == "<"):
                filter_kwargs["until"] = self._parse_date(clause.value)
            elif clause.field == "cost":
                if clause.operator in (">", ">="):
                    filter_kwargs["min_cost_usd"] = float(clause.value)
                elif clause.operator in ("<", "<="):
                    filter_kwargs["max_cost_usd"] = float(clause.value)
            elif clause.field == "duration":
                duration_ms = self._parse_duration(clause.value)
                if clause.operator in (">", ">="):
                    filter_kwargs["min_duration_ms"] = duration_ms
                elif clause.operator in ("<", "<="):
                    filter_kwargs["max_duration_ms"] = duration_ms
            elif clause.field == "error":
                if clause.value.lower() in ("true", "yes", "1"):
                    filter_kwargs["has_error"] = True
                elif clause.value.lower() in ("false", "no", "0"):
                    filter_kwargs["has_error"] = False
            elif clause.field == "failure":
                filter_kwargs["failure_category"] = clause.value

        # Add full-text search
        if self.full_text:
            filter_kwargs["search_query"] = self.full_text

        return RunFilter(**filter_kwargs)

    def _parse_date(self, value: str) -> datetime:
        """Parse a date value."""
        # Handle relative dates
        if value.startswith("-"):
            # e.g., "-7d" for 7 days ago
            match = re.match(r"-(\d+)([dhms])", value)
            if match:
                amount = int(match.group(1))
                unit = match.group(2)
                delta = {
                    "d": timedelta(days=amount),
                    "h": timedelta(hours=amount),
                    "m": timedelta(minutes=amount),
                    "s": timedelta(seconds=amount),
                }[unit]
                return datetime.utcnow() - delta

        # Handle absolute dates
        for fmt in [
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d",
        ]:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue

        raise ValueError(f"Invalid date format: {value}")

    def _parse_duration(self, value: str) -> int:
        """Parse a duration value to milliseconds."""
        # Handle suffixed durations
        match = re.match(r"(\d+(?:\.\d+)?)(ms|s|m|h)?", value.lower())
        if match:
            amount = float(match.group(1))
            unit = match.group(2) or "ms"

            multipliers = {
                "ms": 1,
                "s": 1000,
                "m": 60000,
                "h": 3600000,
            }

            return int(amount * multipliers[unit])

        return int(value)


class QueryParser:
    """Parser for search query strings.

    Supports query syntax:
    - field:value - Exact match
    - field=value - Exact match (alternative)
    - field>value - Greater than
    - field<value - Less than
    - field>=value - Greater than or equal
    - field<=value - Less than or equal
    - field:*pattern* - Pattern match
    - -field:value - Negation
    - "phrase search" - Full-text phrase
    - term1 AND term2 - Boolean AND
    - term1 OR term2 - Boolean OR

    Examples:
    - model:gpt-4 AND cost>0.05
    - project:myproject status:failed
    - "error timeout" since:-7d
    - tool:web_search cost<0.01
    """

    # Field aliases
    FIELD_ALIASES = {
        "mod": "model",
        "proj": "project",
        "stat": "status",
        "err": "error",
        "dur": "duration",
    }

    def parse(self, query: str) -> SearchQuery:
        """Parse a query string.

        Args:
            query: Query string

        Returns:
            Parsed SearchQuery
        """
        result = SearchQuery()

        # Determine logic
        if " OR " in query:
            result.logic = "or"
            parts = query.split(" OR ")
        else:
            result.logic = "and"
            parts = query.replace(" AND ", " ").split()

        full_text_parts = []

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Try to parse as field:value
            clause = self._parse_clause(part)
            if clause:
                result.clauses.append(clause)
            elif part.startswith('"') and part.endswith('"'):
                # Quoted phrase
                full_text_parts.append(part[1:-1])
            else:
                # Plain text term
                full_text_parts.append(part)

        if full_text_parts:
            result.full_text = " ".join(full_text_parts)

        return result

    def _parse_clause(self, part: str) -> SearchClause | None:
        """Parse a single clause."""
        # Check for negation
        negated = part.startswith("-")
        if negated:
            part = part[1:]

        # Try various patterns
        patterns = [
            (r"(\w+)>=(.+)", ">="),
            (r"(\w+)<=(.+)", "<="),
            (r"(\w+)>(.+)", ">"),
            (r"(\w+)<(.+)", "<"),
            (r"(\w+)=(.+)", "="),
            (r"(\w+):(.+)", "="),
        ]

        for pattern, operator in patterns:
            match = re.match(pattern, part)
            if match:
                field = match.group(1).lower()
                value = match.group(2)

                # Handle aliases
                field = self.FIELD_ALIASES.get(field, field)

                # Handle list values
                if "," in value:
                    value = [v.strip() for v in value.split(",")]

                return SearchClause(
                    field=field,
                    operator=operator,
                    value=value,
                    negated=negated,
                )

        return None


class SearchEngine:
    """Engine for executing searches across storage."""

    def __init__(self, storage: Any) -> None:
        """Initialize the search engine.

        Args:
            storage: Storage backend
        """
        self._storage = storage
        self._parser = QueryParser()

    def search(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Any]:
        """Search for runs matching a query.

        Args:
            query: Search query string
            limit: Maximum results
            offset: Result offset

        Returns:
            List of matching run summaries
        """
        from reagent.storage.base import Pagination

        parsed = self._parser.parse(query)
        filter = parsed.to_filter()
        pagination = Pagination(limit=limit, offset=offset)

        # Use storage search if full-text is present
        if parsed.full_text:
            return self._storage.search(
                parsed.full_text,
                filters=filter,
                pagination=pagination,
            )
        else:
            return self._storage.list_runs(
                filters=filter,
                pagination=pagination,
            )

    def parse(self, query: str) -> SearchQuery:
        """Parse a query without executing.

        Args:
            query: Query string

        Returns:
            Parsed query
        """
        return self._parser.parse(query)
