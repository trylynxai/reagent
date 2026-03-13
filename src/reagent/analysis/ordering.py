"""Async task ordering — causal ordering for concurrent agent steps.

When agents execute steps in parallel (e.g. asyncio.gather, thread pools),
recorded step order reflects finish time, not logical execution order.
This module:

- Detects concurrent steps from overlapping timestamps
- Builds a dependency graph (parent-child, temporal)
- Groups concurrent steps into concurrency groups
- Produces a topologically sorted causal order

Uses only stdlib — no external dependencies.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from reagent.schema.run import Run
from reagent.schema.steps import AnyStep


# ============================================================
# Configuration and result types
# ============================================================


@dataclass
class OrderingConfig:
    """Configuration for async ordering analysis.

    Attributes:
        overlap_threshold_ms: Minimum overlap in milliseconds for two steps
            to be considered concurrent. Default 0 means any overlap counts.
        group_by_parent: Whether to group steps sharing a parent_step_id
            into concurrency groups.
        infer_temporal_deps: Whether to infer dependencies from temporal
            ordering when steps don't overlap.
    """

    overlap_threshold_ms: int = 0
    group_by_parent: bool = True
    infer_temporal_deps: bool = True


@dataclass
class StepDependency:
    """A directed edge in the dependency graph.

    Represents that `to_step` depends on (must execute after) `from_step`.
    """

    from_step: int
    to_step: int
    dependency_type: str  # "parent_child", "temporal", "explicit"

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_step": self.from_step,
            "to_step": self.to_step,
            "type": self.dependency_type,
        }


@dataclass
class ConcurrencyGroup:
    """A set of steps that executed concurrently.

    Steps in a group have overlapping time intervals and no
    dependencies between them — they can run in any order.
    """

    group_id: int
    step_numbers: list[int]
    start_time: datetime | None = None
    end_time: datetime | None = None
    parent_step_id: UUID | None = None

    @property
    def size(self) -> int:
        return len(self.step_numbers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "step_numbers": self.step_numbers,
            "size": self.size,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "parent_step_id": str(self.parent_step_id) if self.parent_step_id else None,
        }


@dataclass
class OrderingResult:
    """Result of async ordering analysis.

    Attributes:
        causal_order: Step numbers in dependency-respecting order.
        concurrency_groups: Groups of steps that ran in parallel.
        dependencies: All detected dependency edges.
        has_concurrency: Whether any concurrent execution was detected.
        original_order: The original step number order for comparison.
        reorder_needed: Whether the causal order differs from the original.
    """

    causal_order: list[int] = field(default_factory=list)
    concurrency_groups: list[ConcurrencyGroup] = field(default_factory=list)
    dependencies: list[StepDependency] = field(default_factory=list)
    has_concurrency: bool = False
    original_order: list[int] = field(default_factory=list)
    reorder_needed: bool = False

    @property
    def total_steps(self) -> int:
        return len(self.causal_order)

    @property
    def concurrent_step_count(self) -> int:
        """Number of steps involved in concurrency groups."""
        seen: set[int] = set()
        for g in self.concurrency_groups:
            seen.update(g.step_numbers)
        return len(seen)

    def to_dict(self) -> dict[str, Any]:
        return {
            "causal_order": self.causal_order,
            "original_order": self.original_order,
            "reorder_needed": self.reorder_needed,
            "has_concurrency": self.has_concurrency,
            "total_steps": self.total_steps,
            "concurrent_step_count": self.concurrent_step_count,
            "concurrency_groups": [g.to_dict() for g in self.concurrency_groups],
            "dependencies": [d.to_dict() for d in self.dependencies],
        }


# ============================================================
# Analyzer
# ============================================================


class AsyncOrderAnalyzer:
    """Analyzes step sequences for concurrency and causal ordering.

    Uses timestamp overlap detection, parent-child relationships, and
    topological sorting to determine correct execution order.
    """

    def __init__(self, config: OrderingConfig | None = None) -> None:
        self._config = config or OrderingConfig()

    def analyze(self, steps: list[AnyStep]) -> OrderingResult:
        """Analyze a list of steps for concurrency and ordering.

        Args:
            steps: List of step objects (any step type).

        Returns:
            OrderingResult with causal order, groups, and dependencies.
        """
        if not steps:
            return OrderingResult()

        if len(steps) == 1:
            sn = steps[0].step_number
            return OrderingResult(
                causal_order=[sn],
                original_order=[sn],
            )

        original_order = [s.step_number for s in steps]
        step_map = {s.step_number: s for s in steps}

        # Build dependency graph
        deps = self._build_dependencies(steps, step_map)

        # Detect concurrency groups
        groups = self._detect_concurrency_groups(steps, deps)

        has_concurrency = len(groups) > 0

        # Topological sort
        causal_order = self._topological_sort(steps, deps)

        reorder_needed = causal_order != original_order

        return OrderingResult(
            causal_order=causal_order,
            concurrency_groups=groups,
            dependencies=deps,
            has_concurrency=has_concurrency,
            original_order=original_order,
            reorder_needed=reorder_needed,
        )

    def analyze_run(self, run: Run) -> OrderingResult:
        """Analyze a run's steps for concurrency and ordering."""
        return self.analyze(list(run.steps))

    def reorder(self, steps: list[AnyStep]) -> list[AnyStep]:
        """Return steps reordered by causal dependency.

        Steps are returned in an order that respects dependencies:
        if step A must happen before step B, A appears first.
        Concurrent steps maintain their relative original order.
        """
        result = self.analyze(steps)
        step_map = {s.step_number: s for s in steps}
        return [step_map[sn] for sn in result.causal_order]

    # ── Dependency detection ──────────────────────────────────

    def _build_dependencies(
        self,
        steps: list[AnyStep],
        step_map: dict[int, AnyStep],
    ) -> list[StepDependency]:
        """Build dependency edges from parent-child and temporal relationships."""
        deps: list[StepDependency] = []
        dep_set: set[tuple[int, int]] = set()

        # Parent-child dependencies
        if self._config.group_by_parent:
            deps.extend(self._parent_child_deps(steps, step_map))
            dep_set.update((d.from_step, d.to_step) for d in deps)

        # Temporal dependencies: non-overlapping sequential steps
        if self._config.infer_temporal_deps:
            for dep in self._temporal_deps(steps):
                key = (dep.from_step, dep.to_step)
                if key not in dep_set:
                    deps.append(dep)
                    dep_set.add(key)

        return deps

    def _parent_child_deps(
        self,
        steps: list[AnyStep],
        step_map: dict[int, AnyStep],
    ) -> list[StepDependency]:
        """Detect parent → child dependencies from parent_step_id."""
        deps: list[StepDependency] = []

        # Map step_id → step_number for lookups
        id_to_num: dict[UUID, int] = {}
        for s in steps:
            id_to_num[s.step_id] = s.step_number

        for s in steps:
            if s.parent_step_id and s.parent_step_id in id_to_num:
                parent_num = id_to_num[s.parent_step_id]
                deps.append(StepDependency(
                    from_step=parent_num,
                    to_step=s.step_number,
                    dependency_type="parent_child",
                ))

        return deps

    def _temporal_deps(self, steps: list[AnyStep]) -> list[StepDependency]:
        """Infer dependencies from temporal ordering.

        If step A ends before step B starts (no overlap), and A has
        a lower step number, infer A → B dependency — but only for
        adjacent non-overlapping steps to avoid a fully connected graph.
        """
        deps: list[StepDependency] = []

        # Sort by start time
        timed = sorted(
            [s for s in steps if s.timestamp_start],
            key=lambda s: s.timestamp_start,
        )

        for i in range(len(timed) - 1):
            a = timed[i]
            b = timed[i + 1]

            if not self._steps_overlap(a, b):
                deps.append(StepDependency(
                    from_step=a.step_number,
                    to_step=b.step_number,
                    dependency_type="temporal",
                ))

        return deps

    # ── Concurrency detection ─────────────────────────────────

    def _steps_overlap(self, a: AnyStep, b: AnyStep) -> bool:
        """Check if two steps have overlapping time intervals."""
        if not a.timestamp_start or not b.timestamp_start:
            return False

        a_end = a.timestamp_end or a.timestamp_start
        b_end = b.timestamp_end or b.timestamp_start

        # Ensure a starts first (or same time)
        if a.timestamp_start > b.timestamp_start:
            a, b = b, a
            a_end, b_end = b_end, a_end

        threshold = timedelta(milliseconds=self._config.overlap_threshold_ms)
        overlap_start = b.timestamp_start
        overlap_end = min(a_end, b_end)

        if overlap_end <= overlap_start:
            return False

        overlap_ms = (overlap_end - overlap_start).total_seconds() * 1000
        return overlap_ms >= self._config.overlap_threshold_ms

    def _detect_concurrency_groups(
        self,
        steps: list[AnyStep],
        deps: list[StepDependency],
    ) -> list[ConcurrencyGroup]:
        """Find groups of steps that executed concurrently.

        Uses union-find on overlapping steps, excluding pairs that
        have a dependency edge between them.
        """
        # Build set of dependency pairs for exclusion
        dep_pairs: set[tuple[int, int]] = set()
        for d in deps:
            dep_pairs.add((d.from_step, d.to_step))
            dep_pairs.add((d.to_step, d.from_step))

        # Find overlapping pairs
        timed = [s for s in steps if s.timestamp_start]
        n = len(timed)

        # Union-Find
        parent: dict[int, int] = {s.step_number: s.step_number for s in timed}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry

        has_overlap = False
        for i in range(n):
            for j in range(i + 1, n):
                a, b = timed[i], timed[j]
                pair = (a.step_number, b.step_number)
                if pair not in dep_pairs and self._steps_overlap(a, b):
                    union(a.step_number, b.step_number)
                    has_overlap = True

        if not has_overlap:
            return []

        # Collect groups
        groups_map: dict[int, list[int]] = defaultdict(list)
        for s in timed:
            root = find(s.step_number)
            groups_map[root].append(s.step_number)

        # Only keep groups with 2+ members
        step_map = {s.step_number: s for s in timed}
        groups: list[ConcurrencyGroup] = []
        group_id = 0

        for members in groups_map.values():
            if len(members) < 2:
                continue
            members.sort()
            member_steps = [step_map[sn] for sn in members]
            starts = [s.timestamp_start for s in member_steps if s.timestamp_start]
            ends = [
                s.timestamp_end or s.timestamp_start
                for s in member_steps
                if s.timestamp_start
            ]

            # Check if all share a parent
            parent_ids = {s.parent_step_id for s in member_steps}
            common_parent = parent_ids.pop() if len(parent_ids) == 1 else None

            groups.append(ConcurrencyGroup(
                group_id=group_id,
                step_numbers=members,
                start_time=min(starts) if starts else None,
                end_time=max(ends) if ends else None,
                parent_step_id=common_parent,
            ))
            group_id += 1

        return groups

    # ── Topological sort ──────────────────────────────────────

    def _topological_sort(
        self,
        steps: list[AnyStep],
        deps: list[StepDependency],
    ) -> list[int]:
        """Topological sort via Kahn's algorithm.

        Produces an ordering that respects all dependency edges.
        Ties are broken by original step_number (lower first) to keep
        the output stable and predictable.
        """
        all_nums = [s.step_number for s in steps]
        num_set = set(all_nums)

        # Build adjacency list and in-degree count
        adj: dict[int, list[int]] = defaultdict(list)
        in_degree: dict[int, int] = {sn: 0 for sn in all_nums}

        for d in deps:
            if d.from_step in num_set and d.to_step in num_set:
                adj[d.from_step].append(d.to_step)
                in_degree[d.to_step] += 1

        # Seed queue with zero in-degree nodes (sorted for stability)
        queue: list[int] = sorted(
            [sn for sn in all_nums if in_degree[sn] == 0]
        )

        result: list[int] = []

        while queue:
            # Pop smallest step number for deterministic output
            node = queue.pop(0)
            result.append(node)

            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    # Insert in sorted position
                    _insort(queue, neighbor)

        # If cycle detected, append remaining nodes by step number
        if len(result) < len(all_nums):
            remaining = sorted(set(all_nums) - set(result))
            result.extend(remaining)

        return result


def _insort(lst: list[int], val: int) -> None:
    """Insert val into a sorted list maintaining sort order."""
    lo, hi = 0, len(lst)
    while lo < hi:
        mid = (lo + hi) // 2
        if lst[mid] < val:
            lo = mid + 1
        else:
            hi = mid
    lst.insert(lo, val)
