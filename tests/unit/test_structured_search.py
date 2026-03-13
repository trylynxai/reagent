"""Tests for structured search query parsing and execution."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from reagent.analysis.search import (
    AndExpr,
    NotExpr,
    OrExpr,
    QueryParser,
    SearchClause,
    SearchEngine,
    SearchQuery,
    _parse_date,
    _parse_duration,
    _tokenize,
    evaluate_expr,
)
from reagent.core.constants import Status
from reagent.schema.run import (
    CostSummary,
    RunMetadata,
    StepSummary,
    TokenSummary,
)
from reagent.schema.steps import ToolCallStep, ToolInput, LLMCallStep
from reagent.storage.base import RunFilter
from reagent.storage.memory import MemoryStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_meta(
    name: str = "test-run",
    project: str = "proj",
    status: Status = Status.COMPLETED,
    model: str = "gpt-4",
    framework: str | None = None,
    cost: float = 0.05,
    duration_ms: int = 5000,
    total_tokens: int = 1000,
    total_steps: int = 3,
    error: str | None = None,
    failure_category: str | None = None,
    tags: list[str] | None = None,
) -> RunMetadata:
    return RunMetadata(
        run_id=uuid4(),
        name=name,
        project=project,
        status=status,
        model=model,
        framework=framework,
        start_time=datetime(2025, 1, 15, 10, 0, 0),
        end_time=datetime(2025, 1, 15, 10, 0, 5),
        duration_ms=duration_ms,
        cost=CostSummary(total_usd=cost),
        tokens=TokenSummary(total_tokens=total_tokens),
        steps=StepSummary(total=total_steps),
        error=error,
        error_type="RuntimeError" if error else None,
        failure_category=failure_category,
        tags=tags or [],
    )


# ---------------------------------------------------------------------------
# TestTokenizer
# ---------------------------------------------------------------------------


class TestTokenizer:
    def test_simple_clause(self):
        tokens = _tokenize("model:gpt-4")
        assert len(tokens) == 1
        assert tokens[0].type == "CLAUSE"
        assert tokens[0].value == "model:gpt-4"

    def test_and_operator(self):
        tokens = _tokenize("model:gpt-4 AND cost>0.05")
        assert len(tokens) == 3
        assert tokens[1].type == "AND"

    def test_or_operator(self):
        tokens = _tokenize("status:failed OR status:cancelled")
        assert len(tokens) == 3
        assert tokens[1].type == "OR"

    def test_not_operator(self):
        tokens = _tokenize("NOT model:gpt-3.5")
        assert len(tokens) == 2
        assert tokens[0].type == "NOT"

    def test_parentheses(self):
        tokens = _tokenize("(status:failed OR status:cancelled) AND cost>0.01")
        types = [t.type for t in tokens]
        assert "LPAREN" in types
        assert "RPAREN" in types

    def test_quoted_string(self):
        tokens = _tokenize('"error timeout"')
        assert len(tokens) == 1
        assert tokens[0].type == "QUOTED"
        assert tokens[0].value == "error timeout"

    def test_mixed_query(self):
        tokens = _tokenize('model:gpt-4 "timeout error" cost>0.05')
        assert len(tokens) == 3
        assert tokens[0].type == "CLAUSE"
        assert tokens[1].type == "QUOTED"
        assert tokens[2].type == "CLAUSE"

    def test_negation_prefix(self):
        tokens = _tokenize("-model:gpt-3.5")
        assert len(tokens) == 1
        assert tokens[0].type == "CLAUSE"
        assert tokens[0].value == "-model:gpt-3.5"

    def test_plain_words(self):
        tokens = _tokenize("hello world")
        assert len(tokens) == 2
        assert tokens[0].type == "WORD"
        assert tokens[1].type == "WORD"


# ---------------------------------------------------------------------------
# TestQueryParser
# ---------------------------------------------------------------------------


class TestQueryParser:
    def setup_method(self):
        self.parser = QueryParser()

    def test_simple_field_value(self):
        q = self.parser.parse("model:gpt-4")
        assert q.expression is not None
        assert isinstance(q.expression, SearchClause)
        assert q.expression.field == "model"
        assert q.expression.value == "gpt-4"

    def test_field_aliases(self):
        q = self.parser.parse("mod:gpt-4")
        clause = q.expression
        assert isinstance(clause, SearchClause)
        assert clause.field == "model"

        q2 = self.parser.parse("proj:myproject")
        clause2 = q2.expression
        assert isinstance(clause2, SearchClause)
        assert clause2.field == "project"

    def test_range_operator_gt(self):
        q = self.parser.parse("cost>0.05")
        clause = q.expression
        assert isinstance(clause, SearchClause)
        assert clause.field == "cost"
        assert clause.operator == ">"
        assert clause.value == "0.05"

    def test_range_operator_gte(self):
        q = self.parser.parse("tokens>=1000")
        clause = q.expression
        assert isinstance(clause, SearchClause)
        assert clause.field == "tokens"
        assert clause.operator == ">="

    def test_range_operator_lt(self):
        q = self.parser.parse("duration<5s")
        clause = q.expression
        assert isinstance(clause, SearchClause)
        assert clause.field == "duration"
        assert clause.operator == "<"
        assert clause.value == "5s"

    def test_implicit_and(self):
        q = self.parser.parse("model:gpt-4 cost>0.05")
        assert isinstance(q.expression, AndExpr)
        assert len(q.expression.children) == 2

    def test_explicit_and(self):
        q = self.parser.parse("model:gpt-4 AND cost>0.05")
        assert isinstance(q.expression, AndExpr)
        assert len(q.expression.children) == 2

    def test_or(self):
        q = self.parser.parse("status:failed OR status:cancelled")
        assert isinstance(q.expression, OrExpr)
        assert len(q.expression.children) == 2

    def test_not_operator(self):
        q = self.parser.parse("NOT model:gpt-3.5")
        assert isinstance(q.expression, NotExpr)
        inner = q.expression.child
        assert isinstance(inner, SearchClause)
        assert inner.field == "model"

    def test_negation_prefix(self):
        q = self.parser.parse("-model:gpt-3.5")
        assert isinstance(q.expression, NotExpr)
        inner = q.expression.child
        assert isinstance(inner, SearchClause)
        assert inner.field == "model"
        assert not inner.negated  # negated moved to NotExpr wrapper

    def test_parentheses_grouping(self):
        q = self.parser.parse("(status:failed OR status:cancelled) AND cost>0.01")
        assert isinstance(q.expression, AndExpr)
        assert len(q.expression.children) == 2
        # First child should be OrExpr
        assert isinstance(q.expression.children[0], OrExpr)
        # Second child should be SearchClause
        assert isinstance(q.expression.children[1], SearchClause)

    def test_nested_parentheses(self):
        q = self.parser.parse("(model:gpt-4 AND (status:failed OR status:cancelled))")
        assert isinstance(q.expression, AndExpr)

    def test_full_text(self):
        q = self.parser.parse('"timeout error"')
        assert q.full_text == "timeout error"

    def test_mixed_clause_and_fulltext(self):
        q = self.parser.parse('model:gpt-4 "timeout error"')
        assert q.full_text == "timeout error"
        assert q.expression is not None
        assert isinstance(q.expression, SearchClause)
        assert q.expression.field == "model"

    def test_comma_separated_values(self):
        q = self.parser.parse("status:failed,cancelled")
        clause = q.expression
        assert isinstance(clause, SearchClause)
        assert isinstance(clause.value, list)
        assert "failed" in clause.value
        assert "cancelled" in clause.value

    def test_new_field_tool(self):
        q = self.parser.parse("tool:web_search")
        clause = q.expression
        assert isinstance(clause, SearchClause)
        assert clause.field == "tool"
        assert clause.value == "web_search"

    def test_new_field_name(self):
        q = self.parser.parse("name:chatbot")
        clause = q.expression
        assert isinstance(clause, SearchClause)
        assert clause.field == "name"

    def test_new_field_framework(self):
        q = self.parser.parse("framework:langchain")
        clause = q.expression
        assert isinstance(clause, SearchClause)
        assert clause.field == "framework"

    def test_new_field_tokens(self):
        q = self.parser.parse("tokens>1000")
        clause = q.expression
        assert isinstance(clause, SearchClause)
        assert clause.field == "tokens"
        assert clause.operator == ">"

    def test_new_field_steps(self):
        q = self.parser.parse("steps>5")
        clause = q.expression
        assert isinstance(clause, SearchClause)
        assert clause.field == "steps"
        assert clause.operator == ">"

    def test_is_simple_all_and(self):
        q = self.parser.parse("model:gpt-4 cost>0.05")
        assert q.is_simple is True

    def test_is_simple_or_query(self):
        q = self.parser.parse("status:failed OR status:cancelled")
        assert q.is_simple is False

    def test_is_simple_not_query(self):
        q = self.parser.parse("NOT model:gpt-3.5")
        assert q.is_simple is False

    def test_is_simple_negation_prefix(self):
        q = self.parser.parse("-model:gpt-3.5")
        assert q.is_simple is False


# ---------------------------------------------------------------------------
# TestToFilter
# ---------------------------------------------------------------------------


class TestToFilter:
    def setup_method(self):
        self.parser = QueryParser()

    def test_basic_fields(self):
        q = self.parser.parse("project:myproject model:gpt-4")
        f = q.to_filter()
        assert f.project == "myproject"
        assert f.model == "gpt-4"

    def test_cost_range(self):
        q = self.parser.parse("cost>0.05 cost<1.00")
        f = q.to_filter()
        assert f.min_cost_usd == 0.05
        assert f.max_cost_usd == 1.00

    def test_duration_range(self):
        q = self.parser.parse("duration>5s duration<1m")
        f = q.to_filter()
        assert f.min_duration_ms == 5000
        assert f.max_duration_ms == 60000

    def test_tokens_range(self):
        q = self.parser.parse("tokens>1000 tokens<5000")
        f = q.to_filter()
        assert f.min_tokens == 1000
        assert f.max_tokens == 5000

    def test_steps_range(self):
        q = self.parser.parse("steps>5 steps<=20")
        f = q.to_filter()
        assert f.min_steps == 5
        assert f.max_steps == 20

    def test_name_filter(self):
        q = self.parser.parse("name:chatbot")
        f = q.to_filter()
        assert f.name == "chatbot"

    def test_tool_filter(self):
        q = self.parser.parse("tool:web_search")
        f = q.to_filter()
        assert f.tool_name == "web_search"

    def test_framework_filter(self):
        q = self.parser.parse("framework:langchain")
        f = q.to_filter()
        assert f.framework == "langchain"

    def test_status_filter(self):
        q = self.parser.parse("status:failed")
        f = q.to_filter()
        assert f.status == Status.FAILED

    def test_status_list(self):
        q = self.parser.parse("status:failed,cancelled")
        f = q.to_filter()
        assert isinstance(f.status, list)
        assert Status.FAILED in f.status
        assert Status.CANCELLED in f.status

    def test_error_filter(self):
        q = self.parser.parse("error:true")
        f = q.to_filter()
        assert f.has_error is True

    def test_full_text(self):
        q = self.parser.parse('"timeout error"')
        f = q.to_filter()
        assert f.search_query == "timeout error"

    def test_since_relative(self):
        q = self.parser.parse("since:-7d")
        f = q.to_filter()
        assert f.since is not None
        assert f.since > datetime.utcnow() - timedelta(days=8)


# ---------------------------------------------------------------------------
# TestExpressionEvaluator
# ---------------------------------------------------------------------------


class TestExpressionEvaluator:
    def test_single_clause_match(self):
        meta = _make_meta(model="gpt-4")
        clause = SearchClause(field="model", operator="=", value="gpt-4")
        assert evaluate_expr(clause, meta) is True

    def test_single_clause_no_match(self):
        meta = _make_meta(model="gpt-3.5")
        clause = SearchClause(field="model", operator="=", value="gpt-4")
        assert evaluate_expr(clause, meta) is False

    def test_and_both_match(self):
        meta = _make_meta(model="gpt-4", cost=0.10)
        expr = AndExpr(children=[
            SearchClause(field="model", operator="=", value="gpt-4"),
            SearchClause(field="cost", operator=">", value="0.05"),
        ])
        assert evaluate_expr(expr, meta) is True

    def test_and_one_fails(self):
        meta = _make_meta(model="gpt-4", cost=0.01)
        expr = AndExpr(children=[
            SearchClause(field="model", operator="=", value="gpt-4"),
            SearchClause(field="cost", operator=">", value="0.05"),
        ])
        assert evaluate_expr(expr, meta) is False

    def test_or_one_matches(self):
        meta = _make_meta(status=Status.FAILED)
        expr = OrExpr(children=[
            SearchClause(field="status", operator="=", value="failed"),
            SearchClause(field="status", operator="=", value="cancelled"),
        ])
        assert evaluate_expr(expr, meta) is True

    def test_or_none_match(self):
        meta = _make_meta(status=Status.COMPLETED)
        expr = OrExpr(children=[
            SearchClause(field="status", operator="=", value="failed"),
            SearchClause(field="status", operator="=", value="cancelled"),
        ])
        assert evaluate_expr(expr, meta) is False

    def test_not_negates_match(self):
        meta = _make_meta(model="gpt-3.5")
        expr = NotExpr(child=SearchClause(field="model", operator="=", value="gpt-3.5"))
        assert evaluate_expr(expr, meta) is False

    def test_not_negates_no_match(self):
        meta = _make_meta(model="gpt-4")
        expr = NotExpr(child=SearchClause(field="model", operator="=", value="gpt-3.5"))
        assert evaluate_expr(expr, meta) is True

    def test_complex_nested(self):
        """(status:failed OR status:cancelled) AND cost>0.01"""
        meta = _make_meta(status=Status.CANCELLED, cost=0.05)
        expr = AndExpr(children=[
            OrExpr(children=[
                SearchClause(field="status", operator="=", value="failed"),
                SearchClause(field="status", operator="=", value="cancelled"),
            ]),
            SearchClause(field="cost", operator=">", value="0.01"),
        ])
        assert evaluate_expr(expr, meta) is True

    def test_complex_nested_fails(self):
        """(status:failed OR status:cancelled) AND cost>0.01"""
        meta = _make_meta(status=Status.COMPLETED, cost=0.05)
        expr = AndExpr(children=[
            OrExpr(children=[
                SearchClause(field="status", operator="=", value="failed"),
                SearchClause(field="status", operator="=", value="cancelled"),
            ]),
            SearchClause(field="cost", operator=">", value="0.01"),
        ])
        assert evaluate_expr(expr, meta) is False

    def test_range_cost_gt(self):
        meta = _make_meta(cost=0.10)
        clause = SearchClause(field="cost", operator=">", value="0.05")
        assert evaluate_expr(clause, meta) is True

    def test_range_cost_lt(self):
        meta = _make_meta(cost=0.01)
        clause = SearchClause(field="cost", operator="<", value="0.05")
        assert evaluate_expr(clause, meta) is True

    def test_range_tokens(self):
        meta = _make_meta(total_tokens=2000)
        clause = SearchClause(field="tokens", operator=">", value="1000")
        assert evaluate_expr(clause, meta) is True

    def test_range_duration(self):
        meta = _make_meta(duration_ms=15000)
        clause = SearchClause(field="duration", operator=">", value="10s")
        assert evaluate_expr(clause, meta) is True

    def test_range_steps(self):
        meta = _make_meta(total_steps=10)
        clause = SearchClause(field="steps", operator=">", value="5")
        assert evaluate_expr(clause, meta) is True

    def test_name_substring(self):
        meta = _make_meta(name="my-chatbot-run")
        clause = SearchClause(field="name", operator="=", value="chatbot")
        assert evaluate_expr(clause, meta) is True

    def test_error_substring(self):
        meta = _make_meta(error="Connection timeout after 30s")
        clause = SearchClause(field="error", operator="=", value="timeout")
        assert evaluate_expr(clause, meta) is True

    def test_error_boolean_true(self):
        meta = _make_meta(error="something broke")
        clause = SearchClause(field="error", operator="=", value="true")
        assert evaluate_expr(clause, meta) is True

    def test_error_boolean_false(self):
        meta = _make_meta(error=None)
        clause = SearchClause(field="error", operator="=", value="false")
        assert evaluate_expr(clause, meta) is True


# ---------------------------------------------------------------------------
# TestHelpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_parse_duration_ms(self):
        assert _parse_duration("100ms") == 100

    def test_parse_duration_seconds(self):
        assert _parse_duration("5s") == 5000

    def test_parse_duration_minutes(self):
        assert _parse_duration("2m") == 120000

    def test_parse_duration_hours(self):
        assert _parse_duration("1h") == 3600000

    def test_parse_duration_plain_number(self):
        assert _parse_duration("500") == 500

    def test_parse_date_relative_days(self):
        dt = _parse_date("-7d")
        assert dt > datetime.utcnow() - timedelta(days=8)
        assert dt < datetime.utcnow() - timedelta(days=6)

    def test_parse_date_absolute(self):
        dt = _parse_date("2025-01-15")
        assert dt.year == 2025
        assert dt.month == 1
        assert dt.day == 15

    def test_parse_date_iso(self):
        dt = _parse_date("2025-01-15T10:30:00")
        assert dt.hour == 10
        assert dt.minute == 30

    def test_parse_date_invalid(self):
        with pytest.raises(ValueError, match="Invalid date"):
            _parse_date("not-a-date")


# ---------------------------------------------------------------------------
# TestSearchEngineIntegration
# ---------------------------------------------------------------------------


class TestSearchEngineIntegration:
    """Integration tests using MemoryStorage."""

    def setup_method(self):
        self.storage = MemoryStorage()
        self.engine = SearchEngine(self.storage)

        # Create test runs
        self.meta_gpt4_ok = _make_meta(
            name="gpt4-chat", project="proj-a", model="gpt-4",
            status=Status.COMPLETED, cost=0.10, total_tokens=2000, total_steps=5,
        )
        self.meta_gpt35_fail = _make_meta(
            name="gpt35-fail", project="proj-a", model="gpt-3.5-turbo",
            status=Status.FAILED, cost=0.01, total_tokens=500, total_steps=2,
            error="Connection timeout",
        )
        self.meta_claude_ok = _make_meta(
            name="claude-agent", project="proj-b", model="claude-3",
            status=Status.COMPLETED, cost=0.20, total_tokens=5000, total_steps=10,
            framework="langchain",
        )
        self.meta_cancelled = _make_meta(
            name="cancelled-run", project="proj-a", model="gpt-4",
            status=Status.CANCELLED, cost=0.03, total_tokens=300, total_steps=1,
        )

        for meta in [self.meta_gpt4_ok, self.meta_gpt35_fail, self.meta_claude_ok, self.meta_cancelled]:
            self.storage.save_run(meta.run_id, meta)

        # Add a tool call step to gpt4_ok
        tool_step = ToolCallStep(
            step_id=uuid4(),
            run_id=self.meta_gpt4_ok.run_id,
            step_number=0,
            timestamp_start=datetime(2025, 1, 15, 10, 0, 0),
            tool_name="web_search",
            input=ToolInput(kwargs={"query": "test"}),
            success=True,
        )
        self.storage.save_step(self.meta_gpt4_ok.run_id, tool_step)

    def test_simple_model_filter(self):
        results = self.engine.search("model:gpt-4")
        run_ids = {r.run_id for r in results}
        assert self.meta_gpt4_ok.run_id in run_ids
        assert self.meta_cancelled.run_id in run_ids
        assert self.meta_gpt35_fail.run_id not in run_ids

    def test_simple_status_filter(self):
        results = self.engine.search("status:failed")
        assert len(results) == 1
        assert results[0].run_id == self.meta_gpt35_fail.run_id

    def test_cost_range(self):
        results = self.engine.search("cost>0.05")
        run_ids = {r.run_id for r in results}
        assert self.meta_gpt4_ok.run_id in run_ids
        assert self.meta_claude_ok.run_id in run_ids
        assert self.meta_gpt35_fail.run_id not in run_ids

    def test_tokens_range(self):
        results = self.engine.search("tokens>1000")
        run_ids = {r.run_id for r in results}
        assert self.meta_gpt4_ok.run_id in run_ids
        assert self.meta_claude_ok.run_id in run_ids
        assert self.meta_gpt35_fail.run_id not in run_ids

    def test_steps_range(self):
        # steps>=5 (RunFilter min_steps is inclusive)
        results = self.engine.search("steps>=5")
        run_ids = {r.run_id for r in results}
        assert self.meta_gpt4_ok.run_id in run_ids  # steps=5
        assert self.meta_claude_ok.run_id in run_ids  # steps=10
        assert self.meta_gpt35_fail.run_id not in run_ids  # steps=2

    def test_name_filter(self):
        results = self.engine.search("name:chatbot")
        # Not found (no "chatbot" in run names, but "chat" is in "gpt4-chat")
        assert len(results) == 0

        results = self.engine.search("name:chat")
        assert len(results) == 1
        assert results[0].run_id == self.meta_gpt4_ok.run_id

    def test_compound_and(self):
        results = self.engine.search("model:gpt-4 AND status:completed")
        assert len(results) == 1
        assert results[0].run_id == self.meta_gpt4_ok.run_id

    def test_compound_or(self):
        results = self.engine.search("status:failed OR status:cancelled")
        run_ids = {r.run_id for r in results}
        assert self.meta_gpt35_fail.run_id in run_ids
        assert self.meta_cancelled.run_id in run_ids
        assert len(results) == 2

    def test_negation_not(self):
        results = self.engine.search("NOT model:gpt-4")
        run_ids = {r.run_id for r in results}
        assert self.meta_gpt4_ok.run_id not in run_ids
        assert self.meta_cancelled.run_id not in run_ids
        assert self.meta_gpt35_fail.run_id in run_ids
        assert self.meta_claude_ok.run_id in run_ids

    def test_negation_prefix(self):
        results = self.engine.search("-model:gpt-4")
        run_ids = {r.run_id for r in results}
        assert self.meta_gpt4_ok.run_id not in run_ids
        assert self.meta_gpt35_fail.run_id in run_ids

    def test_parentheses_grouping(self):
        results = self.engine.search("(status:failed OR status:cancelled) AND cost<0.05")
        run_ids = {r.run_id for r in results}
        # gpt35-fail: cost=0.01 ✓, cancelled: cost=0.03 ✓
        assert self.meta_gpt35_fail.run_id in run_ids
        assert self.meta_cancelled.run_id in run_ids
        assert len(results) == 2

    def test_parentheses_grouping_narrows(self):
        results = self.engine.search("(status:failed OR status:cancelled) AND cost>0.02")
        run_ids = {r.run_id for r in results}
        # gpt35-fail: cost=0.01 ✗, cancelled: cost=0.03 ✓
        assert self.meta_cancelled.run_id in run_ids
        assert self.meta_gpt35_fail.run_id not in run_ids

    def test_tool_filter(self):
        results = self.engine.search("tool:web_search")
        assert len(results) == 1
        assert results[0].run_id == self.meta_gpt4_ok.run_id

    def test_framework_filter(self):
        results = self.engine.search("framework:langchain")
        # framework is stored on metadata but MemoryStorage _matches_filter checks it
        assert len(results) == 1
        assert results[0].run_id == self.meta_claude_ok.run_id

    def test_complex_real_world_query(self):
        """model:gpt-4 cost>0.05 status:completed"""
        results = self.engine.search("model:gpt-4 cost>0.05 status:completed")
        assert len(results) == 1
        assert results[0].run_id == self.meta_gpt4_ok.run_id

    def test_empty_results(self):
        results = self.engine.search("model:nonexistent")
        assert len(results) == 0

    def test_error_boolean_filter(self):
        results = self.engine.search("error:true")
        assert len(results) == 1
        assert results[0].run_id == self.meta_gpt35_fail.run_id

    def test_limit(self):
        results = self.engine.search("project:proj-a", limit=2)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# TestRunFilterNewFields
# ---------------------------------------------------------------------------


class TestRunFilterNewFields:
    """Test that RunFilter new fields work with MemoryStorage."""

    def setup_method(self):
        self.storage = MemoryStorage()

    def test_name_filter(self):
        meta = _make_meta(name="my-chatbot")
        self.storage.save_run(meta.run_id, meta)

        results = self.storage.list_runs(filters=RunFilter(name="chatbot"))
        assert len(results) == 1

        results = self.storage.list_runs(filters=RunFilter(name="nonexistent"))
        assert len(results) == 0

    def test_min_tokens_filter(self):
        meta = _make_meta(total_tokens=2000)
        self.storage.save_run(meta.run_id, meta)

        results = self.storage.list_runs(filters=RunFilter(min_tokens=1000))
        assert len(results) == 1

        results = self.storage.list_runs(filters=RunFilter(min_tokens=3000))
        assert len(results) == 0

    def test_max_tokens_filter(self):
        meta = _make_meta(total_tokens=500)
        self.storage.save_run(meta.run_id, meta)

        results = self.storage.list_runs(filters=RunFilter(max_tokens=1000))
        assert len(results) == 1

        results = self.storage.list_runs(filters=RunFilter(max_tokens=100))
        assert len(results) == 0

    def test_min_steps_filter(self):
        meta = _make_meta(total_steps=10)
        self.storage.save_run(meta.run_id, meta)

        results = self.storage.list_runs(filters=RunFilter(min_steps=5))
        assert len(results) == 1

        results = self.storage.list_runs(filters=RunFilter(min_steps=20))
        assert len(results) == 0

    def test_max_steps_filter(self):
        meta = _make_meta(total_steps=3)
        self.storage.save_run(meta.run_id, meta)

        results = self.storage.list_runs(filters=RunFilter(max_steps=5))
        assert len(results) == 1

        results = self.storage.list_runs(filters=RunFilter(max_steps=2))
        assert len(results) == 0

    def test_framework_filter(self):
        meta = _make_meta(framework="langchain")
        self.storage.save_run(meta.run_id, meta)

        results = self.storage.list_runs(filters=RunFilter(framework="langchain"))
        assert len(results) == 1

        results = self.storage.list_runs(filters=RunFilter(framework="crewai"))
        assert len(results) == 0

    def test_tool_name_filter(self):
        meta = _make_meta()
        self.storage.save_run(meta.run_id, meta)

        tool_step = ToolCallStep(
            step_id=uuid4(),
            run_id=meta.run_id,
            step_number=0,
            timestamp_start=datetime(2025, 1, 15, 10, 0, 0),
            tool_name="calculator",
            input=ToolInput(kwargs={"expr": "1+1"}),
            success=True,
        )
        self.storage.save_step(meta.run_id, tool_step)

        results = self.storage.list_runs(filters=RunFilter(tool_name="calculator"))
        assert len(results) == 1

        results = self.storage.list_runs(filters=RunFilter(tool_name="web_search"))
        assert len(results) == 0
