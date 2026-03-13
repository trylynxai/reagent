"""Structured search query parsing and execution.

Supports compound queries with AND/OR/NOT operators, parentheses grouping,
range queries, and field-specific filters.

Query syntax:
    field:value              Exact match
    field=value              Exact match (alternative)
    field>value              Greater than
    field<value              Less than
    field>=value             Greater than or equal
    field<=value             Less than or equal
    -field:value             Negation
    NOT field:value          Negation
    "phrase search"          Full-text phrase
    expr1 AND expr2          Boolean AND (default)
    expr1 OR expr2           Boolean OR
    (expr1 OR expr2) AND ..  Parentheses grouping

Examples:
    model:gpt-4 AND cost>0.05
    tool:web_search AND error:timeout
    (status:failed OR status:cancelled) AND cost>0.01
    project:myproject duration>10s -model:gpt-3.5
    name:chatbot tokens>1000 steps>5
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from reagent.core.constants import Status
from reagent.storage.base import RunFilter


# ---------------------------------------------------------------------------
# AST nodes for compound expressions
# ---------------------------------------------------------------------------


@dataclass
class SearchClause:
    """A single clause in a search query."""

    field: str | None  # None for full-text search
    operator: str  # "=", "!=", ">", "<", ">=", "<=", "contains", "like"
    value: Any
    negated: bool = False


@dataclass
class AndExpr:
    """AND combination of sub-expressions."""

    children: list[Any]  # SearchClause | AndExpr | OrExpr | NotExpr


@dataclass
class OrExpr:
    """OR combination of sub-expressions."""

    children: list[Any]


@dataclass
class NotExpr:
    """Negation of a sub-expression."""

    child: Any


# Expression = SearchClause | AndExpr | OrExpr | NotExpr
Expression = SearchClause | AndExpr | OrExpr | NotExpr


@dataclass
class SearchQuery:
    """Parsed search query with expression tree."""

    expression: Expression | None = None
    full_text: str | None = None

    # Legacy compat: flat list of clauses (all AND, no negation)
    clauses: list[SearchClause] = field(default_factory=list)
    logic: str = "and"

    @property
    def is_simple(self) -> bool:
        """Check if this query can be served by a single RunFilter (all AND, no negation)."""
        if self.expression is None:
            return True
        return self._is_simple_expr(self.expression)

    def _is_simple_expr(self, expr: Expression) -> bool:
        if isinstance(expr, SearchClause):
            return not expr.negated
        if isinstance(expr, AndExpr):
            return all(self._is_simple_expr(c) for c in expr.children)
        return False

    def to_filter(self) -> RunFilter:
        """Convert to a RunFilter.

        Works for simple queries (all AND, no negation). For complex queries
        use SearchEngine which evaluates the expression tree in-memory.
        """
        clauses = self.clauses
        if not clauses and self.expression is not None:
            clauses = list(_flatten_and_clauses(self.expression))

        filter_kwargs: dict[str, Any] = {}

        for clause in clauses:
            if clause.negated:
                continue  # Skip negated clauses in simple filter

            _apply_clause_to_filter(clause, filter_kwargs)

        # Add full-text search
        if self.full_text:
            filter_kwargs["search_query"] = self.full_text

        return RunFilter(**filter_kwargs)


def _apply_clause_to_filter(clause: SearchClause, kwargs: dict[str, Any]) -> None:
    """Map a single clause to RunFilter kwargs."""
    f = clause.field
    op = clause.operator
    val = clause.value

    if f == "project":
        kwargs["project"] = val
    elif f == "name":
        kwargs["name"] = val
    elif f == "status":
        if isinstance(val, str):
            if "," in val:
                kwargs["status"] = [Status(v.strip()) for v in val.split(",")]
            else:
                kwargs["status"] = Status(val)
        elif isinstance(val, list):
            kwargs["status"] = [Status(v) for v in val]
    elif f == "model":
        kwargs["model"] = val
    elif f == "tags":
        kwargs["tags"] = val if isinstance(val, list) else [val]
    elif f == "framework":
        kwargs["framework"] = val
    elif f == "tool":
        kwargs["tool_name"] = val
    elif f == "since" or (f == "date" and op in (">", ">=")):
        kwargs["since"] = _parse_date(val)
    elif f == "until" or (f == "date" and op in ("<", "<=")):
        kwargs["until"] = _parse_date(val)
    elif f == "cost":
        if op in (">", ">="):
            kwargs["min_cost_usd"] = float(val)
        elif op in ("<", "<="):
            kwargs["max_cost_usd"] = float(val)
    elif f == "duration":
        duration_ms = _parse_duration(val)
        if op in (">", ">="):
            kwargs["min_duration_ms"] = duration_ms
        elif op in ("<", "<="):
            kwargs["max_duration_ms"] = duration_ms
    elif f == "tokens":
        if op in (">", ">="):
            kwargs["min_tokens"] = int(val)
        elif op in ("<", "<="):
            kwargs["max_tokens"] = int(val)
    elif f == "steps":
        if op in (">", ">="):
            kwargs["min_steps"] = int(val)
        elif op in ("<", "<="):
            kwargs["max_steps"] = int(val)
    elif f == "error":
        if isinstance(val, str) and val.lower() in ("true", "yes", "1"):
            kwargs["has_error"] = True
        elif isinstance(val, str) and val.lower() in ("false", "no", "0"):
            kwargs["has_error"] = False
    elif f == "failure":
        kwargs["failure_category"] = val


def _flatten_and_clauses(expr: Expression) -> list[SearchClause]:
    """Extract flat list of SearchClauses from an AND-only expression."""
    if isinstance(expr, SearchClause):
        return [expr]
    if isinstance(expr, AndExpr):
        result: list[SearchClause] = []
        for child in expr.children:
            result.extend(_flatten_and_clauses(child))
        return result
    return []


# ---------------------------------------------------------------------------
# Date / duration parsing helpers
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> datetime:
    """Parse a date value (relative or absolute)."""
    if value.startswith("-"):
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


def _parse_duration(value: str) -> int:
    """Parse a duration value to milliseconds."""
    match = re.match(r"(\d+(?:\.\d+)?)(ms|s|m|h)?", value.lower())
    if match:
        amount = float(match.group(1))
        unit = match.group(2) or "ms"
        multipliers = {"ms": 1, "s": 1000, "m": 60000, "h": 3600000}
        return int(amount * multipliers[unit])
    return int(value)


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

# Token types
_TOK_LPAREN = "LPAREN"
_TOK_RPAREN = "RPAREN"
_TOK_AND = "AND"
_TOK_OR = "OR"
_TOK_NOT = "NOT"
_TOK_QUOTED = "QUOTED"
_TOK_CLAUSE = "CLAUSE"  # field:value, field>value, etc.
_TOK_WORD = "WORD"  # plain text term


@dataclass
class _Token:
    type: str
    value: str


def _tokenize(query: str) -> list[_Token]:
    """Tokenize a query string into structured tokens."""
    tokens: list[_Token] = []
    i = 0
    n = len(query)

    while i < n:
        # Skip whitespace
        if query[i].isspace():
            i += 1
            continue

        # Parentheses
        if query[i] == "(":
            tokens.append(_Token(_TOK_LPAREN, "("))
            i += 1
            continue
        if query[i] == ")":
            tokens.append(_Token(_TOK_RPAREN, ")"))
            i += 1
            continue

        # Quoted string
        if query[i] == '"':
            end = query.find('"', i + 1)
            if end == -1:
                end = n  # unclosed quote: take rest of string
            tokens.append(_Token(_TOK_QUOTED, query[i + 1 : end]))
            i = end + 1
            continue

        # Read a word/clause (up to whitespace or paren)
        start = i
        while i < n and not query[i].isspace() and query[i] not in ("(", ")"):
            i += 1
        word = query[start:i]

        # Classify the word
        if word.upper() == "AND":
            tokens.append(_Token(_TOK_AND, "AND"))
        elif word.upper() == "OR":
            tokens.append(_Token(_TOK_OR, "OR"))
        elif word.upper() == "NOT":
            tokens.append(_Token(_TOK_NOT, "NOT"))
        elif _is_clause(word):
            tokens.append(_Token(_TOK_CLAUSE, word))
        else:
            tokens.append(_Token(_TOK_WORD, word))

    return tokens


# Pattern for field:value, field>=value, etc.
_CLAUSE_PATTERN = re.compile(r"^-?\w+(?:>=|<=|>|<|=|:).+")


def _is_clause(word: str) -> bool:
    """Check if a word is a field:value clause."""
    return bool(_CLAUSE_PATTERN.match(word))


# ---------------------------------------------------------------------------
# Recursive descent parser
# ---------------------------------------------------------------------------

# Field aliases
_FIELD_ALIASES: dict[str, str] = {
    "mod": "model",
    "proj": "project",
    "stat": "status",
    "err": "error",
    "dur": "duration",
    "tok": "tokens",
}

_CLAUSE_PATTERNS = [
    (re.compile(r"^(\w+)>=(.+)"), ">="),
    (re.compile(r"^(\w+)<=(.+)"), "<="),
    (re.compile(r"^(\w+)>(.+)"), ">"),
    (re.compile(r"^(\w+)<(.+)"), "<"),
    (re.compile(r"^(\w+)=(.+)"), "="),
    (re.compile(r"^(\w+):(.+)"), "="),
]


def _parse_clause_str(text: str) -> SearchClause | None:
    """Parse a clause string like 'field:value' or '-field>value'."""
    negated = text.startswith("-")
    if negated:
        text = text[1:]

    for pattern, operator in _CLAUSE_PATTERNS:
        m = pattern.match(text)
        if m:
            field_name = m.group(1).lower()
            value = m.group(2)
            field_name = _FIELD_ALIASES.get(field_name, field_name)

            # Handle comma-separated list values
            if "," in value and operator == "=":
                value = [v.strip() for v in value.split(",")]

            return SearchClause(
                field=field_name,
                operator=operator,
                value=value,
                negated=negated,
            )
    return None


class _Parser:
    """Recursive descent parser for search expressions.

    Grammar:
        query      -> or_expr
        or_expr    -> and_expr ( 'OR' and_expr )*
        and_expr   -> unary ( 'AND'? unary )*
        unary      -> 'NOT' unary | atom
        atom       -> '(' or_expr ')' | CLAUSE | QUOTED | WORD
    """

    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._pos = 0
        self._full_text_parts: list[str] = []

    def parse(self) -> tuple[Expression | None, str | None]:
        """Parse tokens into expression tree + full text."""
        expr = self._or_expr()
        full_text = " ".join(self._full_text_parts) if self._full_text_parts else None
        return expr, full_text

    def _peek(self) -> _Token | None:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _advance(self) -> _Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _or_expr(self) -> Expression | None:
        left = self._and_expr()
        children = [left] if left else []

        while self._peek() and self._peek().type == _TOK_OR:
            self._advance()  # consume OR
            right = self._and_expr()
            if right:
                children.append(right)

        if not children:
            return None
        if len(children) == 1:
            return children[0]
        return OrExpr(children=children)

    def _and_expr(self) -> Expression | None:
        left = self._unary()
        children = [left] if left else []

        while self._peek() and self._peek().type not in (_TOK_OR, _TOK_RPAREN, None):
            if self._peek().type == _TOK_AND:
                self._advance()  # consume AND
            right = self._unary()
            if right:
                children.append(right)
            if not right:
                break

        if not children:
            return None
        if len(children) == 1:
            return children[0]
        return AndExpr(children=children)

    def _unary(self) -> Expression | None:
        tok = self._peek()
        if tok and tok.type == _TOK_NOT:
            self._advance()  # consume NOT
            child = self._unary()
            if child:
                return NotExpr(child=child)
            return None
        return self._atom()

    def _atom(self) -> Expression | None:
        tok = self._peek()
        if tok is None:
            return None

        if tok.type == _TOK_LPAREN:
            self._advance()  # consume (
            expr = self._or_expr()
            # consume ) if present
            if self._peek() and self._peek().type == _TOK_RPAREN:
                self._advance()
            return expr

        if tok.type == _TOK_CLAUSE:
            self._advance()
            clause = _parse_clause_str(tok.value)
            if clause:
                # Handle negation prefix as NotExpr
                if clause.negated:
                    clause.negated = False
                    return NotExpr(child=clause)
                return clause
            # Fallback: treat as text
            self._full_text_parts.append(tok.value)
            return None

        if tok.type == _TOK_QUOTED:
            self._advance()
            self._full_text_parts.append(tok.value)
            return None

        if tok.type == _TOK_WORD:
            self._advance()
            self._full_text_parts.append(tok.value)
            return None

        return None


# ---------------------------------------------------------------------------
# Public QueryParser
# ---------------------------------------------------------------------------


class QueryParser:
    """Parser for search query strings.

    Supports:
    - field:value, field>value, field>=value, field<value, field<=value
    - -field:value (negation prefix) or NOT field:value
    - AND / OR boolean operators (AND is implicit)
    - Parentheses grouping: (status:failed OR status:cancelled) AND cost>0.05
    - "quoted phrases" for full-text search
    - Field aliases: mod->model, proj->project, stat->status, err->error, dur->duration, tok->tokens

    Field reference:
        project, name, status, model, tags, framework, tool
        cost (range), duration (range), tokens (range), steps (range)
        since, until, date, error, failure
    """

    # Kept for backward compat
    FIELD_ALIASES = _FIELD_ALIASES

    def parse(self, query: str) -> SearchQuery:
        """Parse a query string into a SearchQuery."""
        tokens = _tokenize(query)
        parser = _Parser(tokens)
        expression, full_text = parser.parse()

        # Build legacy clauses list for backward compat
        clauses = list(_flatten_and_clauses(expression)) if expression else []

        # Determine logic
        logic = "or" if isinstance(expression, OrExpr) else "and"

        return SearchQuery(
            expression=expression,
            full_text=full_text,
            clauses=clauses,
            logic=logic,
        )

    def _parse_clause(self, part: str) -> SearchClause | None:
        """Parse a single clause (backward compat)."""
        return _parse_clause_str(part)


# ---------------------------------------------------------------------------
# In-memory expression evaluator
# ---------------------------------------------------------------------------


def evaluate_expr(expr: Expression, metadata: Any) -> bool:
    """Evaluate an expression tree against run metadata.

    Args:
        expr: Expression tree node
        metadata: RunMetadata object

    Returns:
        True if the metadata matches the expression
    """
    if isinstance(expr, SearchClause):
        return _evaluate_clause(expr, metadata)
    if isinstance(expr, AndExpr):
        return all(evaluate_expr(c, metadata) for c in expr.children)
    if isinstance(expr, OrExpr):
        return any(evaluate_expr(c, metadata) for c in expr.children)
    if isinstance(expr, NotExpr):
        return not evaluate_expr(expr.child, metadata)
    return True


def _evaluate_clause(clause: SearchClause, metadata: Any) -> bool:
    """Evaluate a single clause against metadata."""
    f = clause.field
    op = clause.operator
    val = clause.value
    result = _match_field(f, op, val, metadata)

    if clause.negated:
        return not result
    return result


def _match_field(field: str | None, op: str, val: Any, meta: Any) -> bool:
    """Check if a metadata field matches a clause."""
    if field == "project":
        return _str_match(meta.project, val)
    if field == "name":
        return _str_contains(meta.name, val)
    if field == "status":
        if isinstance(val, list):
            return meta.status.value in val
        return meta.status.value == val
    if field == "model":
        return _str_match(meta.model, val)
    if field == "tags":
        tags = val if isinstance(val, list) else [val]
        return all(t in meta.tags for t in tags)
    if field == "framework":
        return _str_match(meta.framework, val)
    if field == "error":
        if isinstance(val, str) and val.lower() in ("true", "yes", "1"):
            return meta.error is not None
        if isinstance(val, str) and val.lower() in ("false", "no", "0"):
            return meta.error is None
        # error:text -> substring match
        return meta.error is not None and val.lower() in meta.error.lower()
    if field == "failure":
        return _str_match(meta.failure_category, val)
    if field == "cost":
        return _compare_numeric(meta.cost.total_usd, op, float(val))
    if field == "duration":
        if meta.duration_ms is None:
            return False
        return _compare_numeric(meta.duration_ms, op, _parse_duration(val))
    if field == "tokens":
        return _compare_numeric(meta.tokens.total_tokens, op, int(val))
    if field == "steps":
        return _compare_numeric(meta.steps.total, op, int(val))
    if field in ("since", "until", "date"):
        try:
            dt = _parse_date(val)
            if field == "since" or (field == "date" and op in (">", ">=")):
                return meta.start_time >= dt
            if field == "until" or (field == "date" and op in ("<", "<=")):
                return meta.start_time <= dt
        except ValueError:
            return False
    # tool: field requires step-level data, handled separately
    if field == "tool":
        return True  # Can't evaluate without step data; handled by storage filter
    return True


def _str_match(actual: str | None, expected: str) -> bool:
    if actual is None:
        return False
    return actual.lower() == expected.lower()


def _str_contains(actual: str | None, expected: str) -> bool:
    if actual is None:
        return False
    return expected.lower() in actual.lower()


def _compare_numeric(actual: float | int, op: str, expected: float | int) -> bool:
    if op == ">" or op == "=":
        # For field:value with "=", treat as equality for non-range fields
        # but for range fields called via > operator, use >
        if op == ">":
            return actual > expected
        return actual == expected
    if op == ">=":
        return actual >= expected
    if op == "<":
        return actual < expected
    if op == "<=":
        return actual <= expected
    return actual == expected


# ---------------------------------------------------------------------------
# SearchEngine
# ---------------------------------------------------------------------------


class SearchEngine:
    """Engine for executing searches across storage.

    For simple queries (all AND, no negation), delegates directly to storage.
    For compound queries (OR, NOT, parentheses), fetches candidates with a
    basic filter and evaluates the expression tree in-memory.
    """

    def __init__(self, storage: Any) -> None:
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

        # Fast path: simple AND-only queries → single RunFilter
        if parsed.is_simple:
            run_filter = parsed.to_filter()
            pagination = Pagination(limit=limit, offset=offset)

            if parsed.full_text:
                return self._storage.search(
                    parsed.full_text,
                    filters=run_filter,
                    pagination=pagination,
                )
            else:
                return self._storage.list_runs(
                    filters=run_filter,
                    pagination=pagination,
                )

        # Complex path: fetch more candidates, evaluate expression in-memory
        # Extract a base filter from AND-able clauses for initial narrowing
        base_filter = self._extract_base_filter(parsed)
        big_pagination = Pagination(limit=1000, offset=0)

        if parsed.full_text:
            candidates = self._storage.search(
                parsed.full_text,
                filters=base_filter,
                pagination=big_pagination,
            )
        else:
            candidates = self._storage.list_runs(
                filters=base_filter,
                pagination=big_pagination,
            )

        # Evaluate expression tree against each candidate
        if parsed.expression:
            # Load full metadata for evaluation
            results = []
            for summary in candidates:
                try:
                    metadata = self._storage.load_metadata(summary.run_id)
                    if evaluate_expr(parsed.expression, metadata):
                        results.append(summary)
                except Exception:
                    continue
        else:
            results = candidates

        # Apply pagination
        return results[offset : offset + limit]

    def _extract_base_filter(self, parsed: SearchQuery) -> RunFilter:
        """Extract a minimal RunFilter from the query for initial narrowing.

        Pulls out any AND-level clauses that can narrow the result set,
        even in compound queries.
        """
        kwargs: dict[str, Any] = {}

        if parsed.full_text:
            kwargs["search_query"] = parsed.full_text

        # For OR/NOT queries, we can't safely extract filters
        # (they might incorrectly narrow results)
        if parsed.expression and isinstance(parsed.expression, AndExpr):
            for child in parsed.expression.children:
                if isinstance(child, SearchClause) and not child.negated:
                    # Only extract non-range filters (safe to narrow)
                    if child.field in ("project", "model", "framework"):
                        _apply_clause_to_filter(child, kwargs)

        return RunFilter(**kwargs)

    def parse(self, query: str) -> SearchQuery:
        """Parse a query without executing."""
        return self._parser.parse(query)
