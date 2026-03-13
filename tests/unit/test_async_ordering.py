"""Tests for async task ordering and concurrency detection."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from reagent.analysis.ordering import (
    AsyncOrderAnalyzer,
    ConcurrencyGroup,
    OrderingConfig,
    OrderingResult,
    StepDependency,
)
from reagent.schema.run import Run, RunConfig
from reagent.schema.steps import (
    LLMCallStep,
    ToolCallStep,
    AgentStep,
    ToolInput,
    ToolOutput,
)


# ---- Helpers ----

_RUN_ID = uuid4()
_BASE_TIME = datetime(2025, 1, 1, 12, 0, 0)


def _ts(offset_ms: int) -> datetime:
    """Create a timestamp offset from base time."""
    return _BASE_TIME + timedelta(milliseconds=offset_ms)


def _llm(step_number: int, start_ms: int, end_ms: int, **kwargs) -> LLMCallStep:
    return LLMCallStep(
        run_id=_RUN_ID,
        step_number=step_number,
        timestamp_start=_ts(start_ms),
        timestamp_end=_ts(end_ms),
        duration_ms=end_ms - start_ms,
        model="gpt-4",
        **kwargs,
    )


def _tool(
    step_number: int,
    start_ms: int,
    end_ms: int,
    tool_name: str = "search",
    **kwargs,
) -> ToolCallStep:
    return ToolCallStep(
        run_id=_RUN_ID,
        step_number=step_number,
        timestamp_start=_ts(start_ms),
        timestamp_end=_ts(end_ms),
        duration_ms=end_ms - start_ms,
        tool_name=tool_name,
        input=ToolInput(),
        success=True,
        **kwargs,
    )


def _agent(step_number: int, start_ms: int, end_ms: int, **kwargs) -> AgentStep:
    return AgentStep(
        run_id=_RUN_ID,
        step_number=step_number,
        timestamp_start=_ts(start_ms),
        timestamp_end=_ts(end_ms),
        duration_ms=end_ms - start_ms,
        agent_name="agent",
        action="act",
        **kwargs,
    )


# ============================================================
# Sequential steps (no concurrency)
# ============================================================


class TestSequentialSteps:
    def test_sequential_no_overlap(self):
        steps = [
            _llm(0, 0, 100),
            _tool(1, 100, 200),
            _llm(2, 200, 300),
        ]
        analyzer = AsyncOrderAnalyzer()
        result = analyzer.analyze(steps)

        assert not result.has_concurrency
        assert result.causal_order == [0, 1, 2]
        assert not result.reorder_needed
        assert len(result.concurrency_groups) == 0

    def test_single_step(self):
        steps = [_llm(0, 0, 100)]
        result = AsyncOrderAnalyzer().analyze(steps)
        assert result.causal_order == [0]
        assert not result.has_concurrency

    def test_empty_steps(self):
        result = AsyncOrderAnalyzer().analyze([])
        assert result.causal_order == []
        assert result.total_steps == 0

    def test_original_order_preserved(self):
        steps = [
            _llm(0, 0, 100),
            _tool(1, 100, 200),
        ]
        result = AsyncOrderAnalyzer().analyze(steps)
        assert result.original_order == [0, 1]


# ============================================================
# Concurrent steps (overlapping timestamps)
# ============================================================


class TestConcurrentSteps:
    def test_two_overlapping_steps(self):
        """Two tool calls running in parallel."""
        steps = [
            _tool(0, 0, 200, tool_name="search"),
            _tool(1, 50, 250, tool_name="fetch"),
        ]
        analyzer = AsyncOrderAnalyzer()
        result = analyzer.analyze(steps)

        assert result.has_concurrency
        assert len(result.concurrency_groups) == 1
        group = result.concurrency_groups[0]
        assert set(group.step_numbers) == {0, 1}
        assert group.size == 2

    def test_three_parallel_tools(self):
        """Three tool calls via asyncio.gather."""
        steps = [
            _tool(0, 0, 300, tool_name="search"),
            _tool(1, 10, 200, tool_name="weather"),
            _tool(2, 20, 250, tool_name="calendar"),
        ]
        result = AsyncOrderAnalyzer().analyze(steps)

        assert result.has_concurrency
        assert len(result.concurrency_groups) == 1
        assert set(result.concurrency_groups[0].step_numbers) == {0, 1, 2}

    def test_concurrent_then_sequential(self):
        """Parallel tools followed by a sequential LLM call."""
        steps = [
            _tool(0, 0, 200, tool_name="search"),
            _tool(1, 10, 180, tool_name="fetch"),
            _llm(2, 300, 500),  # After both tools finish
        ]
        result = AsyncOrderAnalyzer().analyze(steps)

        assert result.has_concurrency
        assert len(result.concurrency_groups) == 1
        assert set(result.concurrency_groups[0].step_numbers) == {0, 1}
        # LLM should come after both tools in causal order
        assert result.causal_order.index(2) > result.causal_order.index(0)
        assert result.causal_order.index(2) > result.causal_order.index(1)

    def test_two_concurrent_groups(self):
        """Two separate groups of parallel steps."""
        steps = [
            _tool(0, 0, 100, tool_name="a"),
            _tool(1, 10, 90, tool_name="b"),
            _llm(2, 200, 300),  # Sequential break
            _tool(3, 400, 600, tool_name="c"),
            _tool(4, 410, 580, tool_name="d"),
        ]
        result = AsyncOrderAnalyzer().analyze(steps)

        assert result.has_concurrency
        assert len(result.concurrency_groups) == 2

    def test_concurrent_step_count(self):
        steps = [
            _tool(0, 0, 200, tool_name="a"),
            _tool(1, 10, 180, tool_name="b"),
            _llm(2, 300, 500),
        ]
        result = AsyncOrderAnalyzer().analyze(steps)
        assert result.concurrent_step_count == 2

    def test_overlap_threshold(self):
        """Steps overlapping less than threshold are not concurrent."""
        steps = [
            _tool(0, 0, 105, tool_name="a"),
            _tool(1, 100, 200, tool_name="b"),  # 5ms overlap
        ]
        config = OrderingConfig(overlap_threshold_ms=10)
        result = AsyncOrderAnalyzer(config).analyze(steps)
        assert not result.has_concurrency

    def test_overlap_threshold_met(self):
        """Steps overlapping at least threshold are concurrent."""
        steps = [
            _tool(0, 0, 120, tool_name="a"),
            _tool(1, 100, 200, tool_name="b"),  # 20ms overlap
        ]
        config = OrderingConfig(overlap_threshold_ms=10)
        result = AsyncOrderAnalyzer(config).analyze(steps)
        assert result.has_concurrency

    def test_group_time_bounds(self):
        steps = [
            _tool(0, 100, 300, tool_name="a"),
            _tool(1, 150, 400, tool_name="b"),
        ]
        result = AsyncOrderAnalyzer().analyze(steps)
        group = result.concurrency_groups[0]
        assert group.start_time == _ts(100)
        assert group.end_time == _ts(400)


# ============================================================
# Parent-child dependencies
# ============================================================


class TestParentChildDeps:
    def test_parent_child_dependency(self):
        parent = _agent(0, 0, 500)
        child1 = _tool(1, 50, 200, parent_step_id=parent.step_id)
        child2 = _tool(2, 60, 250, parent_step_id=parent.step_id)

        result = AsyncOrderAnalyzer().analyze([parent, child1, child2])

        # Parent should be before children in causal order
        assert result.causal_order.index(0) < result.causal_order.index(1)
        assert result.causal_order.index(0) < result.causal_order.index(2)

        # Children with same parent overlap → concurrent group
        # But they have parent_child dep from parent, not between themselves
        pc_deps = [d for d in result.dependencies if d.dependency_type == "parent_child"]
        assert len(pc_deps) == 2

    def test_children_concurrent_under_parent(self):
        """Children of the same parent that overlap are concurrent."""
        parent = _agent(0, 0, 500)
        child1 = _tool(1, 50, 200, parent_step_id=parent.step_id)
        child2 = _tool(2, 60, 250, parent_step_id=parent.step_id)

        result = AsyncOrderAnalyzer().analyze([parent, child1, child2])

        # child1 and child2 overlap and are not directly dep-connected
        concurrent_nums = set()
        for g in result.concurrency_groups:
            concurrent_nums.update(g.step_numbers)
        assert {1, 2}.issubset(concurrent_nums)

    def test_shared_parent_in_group(self):
        parent = _agent(0, 0, 500)
        child1 = _tool(1, 50, 200, parent_step_id=parent.step_id)
        child2 = _tool(2, 60, 250, parent_step_id=parent.step_id)

        result = AsyncOrderAnalyzer().analyze([parent, child1, child2])

        # The concurrent group of children should reference the parent
        children_groups = [
            g for g in result.concurrency_groups
            if 1 in g.step_numbers and 2 in g.step_numbers
        ]
        assert len(children_groups) == 1
        assert children_groups[0].parent_step_id == parent.step_id

    def test_disable_parent_grouping(self):
        parent = _agent(0, 0, 500)
        child1 = _tool(1, 50, 200, parent_step_id=parent.step_id)

        config = OrderingConfig(group_by_parent=False)
        result = AsyncOrderAnalyzer(config).analyze([parent, child1])

        pc_deps = [d for d in result.dependencies if d.dependency_type == "parent_child"]
        assert len(pc_deps) == 0


# ============================================================
# Causal ordering (topological sort)
# ============================================================


class TestCausalOrdering:
    def test_reorder_out_of_order_steps(self):
        """Steps recorded in finish order but started in different order."""
        # Step 2 started first but step 0 finished first
        steps = [
            _tool(0, 100, 150, tool_name="fast"),   # started later, finished first
            _tool(1, 200, 300, tool_name="medium"),
            _tool(2, 0, 50, tool_name="early"),      # started earliest
        ]
        result = AsyncOrderAnalyzer().analyze(steps)

        # Causal order should respect start times for non-overlapping
        assert result.causal_order == [2, 0, 1]
        assert result.reorder_needed

    def test_reorder_method(self):
        steps = [
            _tool(0, 100, 150, tool_name="fast"),
            _tool(1, 0, 50, tool_name="early"),
        ]
        analyzer = AsyncOrderAnalyzer()
        reordered = analyzer.reorder(steps)
        assert reordered[0].step_number == 1  # early first
        assert reordered[1].step_number == 0

    def test_diamond_dependency(self):
        """A → (B, C concurrent) → D pattern."""
        a = _llm(0, 0, 100)
        b = _tool(1, 100, 300, tool_name="search")
        c = _tool(2, 110, 250, tool_name="fetch")
        d = _llm(3, 350, 500)

        result = AsyncOrderAnalyzer().analyze([a, b, c, d])

        # A before B and C, both before D
        order = result.causal_order
        assert order.index(0) < order.index(1)
        assert order.index(0) < order.index(2)
        assert order.index(1) < order.index(3)
        assert order.index(2) < order.index(3)

    def test_no_reorder_when_already_correct(self):
        steps = [
            _llm(0, 0, 100),
            _tool(1, 100, 200),
            _llm(2, 200, 300),
        ]
        result = AsyncOrderAnalyzer().analyze(steps)
        assert not result.reorder_needed
        assert result.causal_order == [0, 1, 2]

    def test_concurrent_steps_stable_order(self):
        """Concurrent steps maintain original step_number ordering."""
        steps = [
            _tool(0, 0, 200, tool_name="a"),
            _tool(1, 10, 180, tool_name="b"),
            _tool(2, 20, 190, tool_name="c"),
        ]
        result = AsyncOrderAnalyzer().analyze(steps)
        # All concurrent, should stay in 0, 1, 2 order
        assert result.causal_order == [0, 1, 2]


# ============================================================
# Run-level analysis
# ============================================================


class TestAnalyzeRun:
    def test_analyze_run(self):
        run = Run.create(RunConfig(name="test"))
        run.steps = [
            _llm(0, 0, 100),
            _tool(1, 100, 200),
        ]
        result = AsyncOrderAnalyzer().analyze_run(run)
        assert result.total_steps == 2
        assert not result.has_concurrency


# ============================================================
# Serialization
# ============================================================


class TestSerialization:
    def test_result_to_dict(self):
        steps = [
            _tool(0, 0, 200, tool_name="a"),
            _tool(1, 10, 180, tool_name="b"),
            _llm(2, 300, 400),
        ]
        result = AsyncOrderAnalyzer().analyze(steps)
        d = result.to_dict()

        assert "causal_order" in d
        assert "concurrency_groups" in d
        assert "dependencies" in d
        assert "has_concurrency" in d
        assert "total_steps" in d
        assert "concurrent_step_count" in d
        assert d["has_concurrency"] is True
        assert d["total_steps"] == 3

    def test_group_to_dict(self):
        group = ConcurrencyGroup(
            group_id=0,
            step_numbers=[1, 2, 3],
            start_time=_BASE_TIME,
            end_time=_BASE_TIME + timedelta(seconds=1),
        )
        d = group.to_dict()
        assert d["group_id"] == 0
        assert d["step_numbers"] == [1, 2, 3]
        assert d["size"] == 3
        assert d["start_time"] is not None

    def test_dependency_to_dict(self):
        dep = StepDependency(from_step=0, to_step=1, dependency_type="temporal")
        d = dep.to_dict()
        assert d == {"from_step": 0, "to_step": 1, "type": "temporal"}


# ============================================================
# Edge cases
# ============================================================


class TestEdgeCases:
    def test_steps_without_end_time(self):
        """Steps with no timestamp_end still work (use start as end)."""
        s1 = LLMCallStep(
            run_id=_RUN_ID,
            step_number=0,
            timestamp_start=_ts(0),
            model="gpt-4",
        )
        s2 = ToolCallStep(
            run_id=_RUN_ID,
            step_number=1,
            timestamp_start=_ts(100),
            tool_name="search",
            input=ToolInput(),
            success=True,
        )
        result = AsyncOrderAnalyzer().analyze([s1, s2])
        assert result.causal_order == [0, 1]

    def test_same_start_time(self):
        """Steps starting at the exact same time are concurrent."""
        steps = [
            _tool(0, 0, 100, tool_name="a"),
            _tool(1, 0, 100, tool_name="b"),
        ]
        result = AsyncOrderAnalyzer().analyze(steps)
        assert result.has_concurrency

    def test_disable_temporal_deps(self):
        config = OrderingConfig(infer_temporal_deps=False)
        steps = [
            _llm(0, 0, 100),
            _tool(1, 100, 200),
        ]
        result = AsyncOrderAnalyzer(config).analyze(steps)
        temporal = [d for d in result.dependencies if d.dependency_type == "temporal"]
        assert len(temporal) == 0

    def test_many_concurrent_steps(self):
        """Large number of concurrent steps doesn't crash."""
        steps = [
            _tool(i, i * 5, i * 5 + 500, tool_name=f"tool-{i}")
            for i in range(20)
        ]
        result = AsyncOrderAnalyzer().analyze(steps)
        assert result.has_concurrency
        assert result.concurrent_step_count == 20

    def test_config_defaults(self):
        config = OrderingConfig()
        assert config.overlap_threshold_ms == 0
        assert config.group_by_parent is True
        assert config.infer_temporal_deps is True
