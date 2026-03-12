"""Trace diffing and comparison tools."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from reagent.schema.run import Run, RunMetadata
from reagent.schema.steps import AnyStep


@dataclass
class StepDiff:
    """Difference between two steps."""

    step_number_a: int | None
    step_number_b: int | None
    step_type: str
    change_type: str  # "added", "removed", "modified", "unchanged"
    field_diffs: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    similarity: float = 1.0

    @property
    def is_same(self) -> bool:
        return self.change_type == "unchanged"


@dataclass
class DiffResult:
    """Result of comparing two traces."""

    run_id_a: UUID
    run_id_b: UUID
    metadata_diff: dict[str, tuple[Any, Any]]
    step_diffs: list[StepDiff]
    overall_similarity: float
    step_count_a: int
    step_count_b: int
    steps_added: int
    steps_removed: int
    steps_modified: int
    steps_unchanged: int

    @property
    def has_differences(self) -> bool:
        return self.overall_similarity < 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "run_id_a": str(self.run_id_a),
            "run_id_b": str(self.run_id_b),
            "overall_similarity": self.overall_similarity,
            "step_count_a": self.step_count_a,
            "step_count_b": self.step_count_b,
            "steps_added": self.steps_added,
            "steps_removed": self.steps_removed,
            "steps_modified": self.steps_modified,
            "steps_unchanged": self.steps_unchanged,
            "metadata_diff": {
                k: {"a": v[0], "b": v[1]}
                for k, v in self.metadata_diff.items()
            },
            "step_diffs": [
                {
                    "step_number_a": d.step_number_a,
                    "step_number_b": d.step_number_b,
                    "step_type": d.step_type,
                    "change_type": d.change_type,
                    "similarity": d.similarity,
                }
                for d in self.step_diffs
            ],
        }


class TraceDiff:
    """Tool for comparing two traces.

    Supports:
    - Structural comparison (step sequence)
    - Content comparison (field-level diffs)
    - Similarity scoring
    - Configurable noise filtering
    """

    # Fields to ignore in comparison (always differ)
    DEFAULT_IGNORE_FIELDS = {
        "step_id",
        "run_id",
        "parent_step_id",
        "timestamp_start",
        "timestamp_end",
        "duration_ms",
    }

    def __init__(
        self,
        ignore_fields: set[str] | None = None,
        ignore_timing: bool = True,
    ) -> None:
        """Initialize the differ.

        Args:
            ignore_fields: Fields to ignore in comparison
            ignore_timing: Whether to ignore timing fields
        """
        self._ignore_fields = ignore_fields or self.DEFAULT_IGNORE_FIELDS
        if ignore_timing:
            self._ignore_fields |= {"timestamp_start", "timestamp_end", "duration_ms"}

    def diff(self, run_a: Run, run_b: Run) -> DiffResult:
        """Compare two runs.

        Args:
            run_a: First run
            run_b: Second run

        Returns:
            Diff result
        """
        # Compare metadata
        metadata_diff = self._diff_metadata(run_a.metadata, run_b.metadata)

        # Align and compare steps
        step_diffs = self._diff_steps(run_a.steps, run_b.steps)

        # Calculate statistics
        steps_added = sum(1 for d in step_diffs if d.change_type == "added")
        steps_removed = sum(1 for d in step_diffs if d.change_type == "removed")
        steps_modified = sum(1 for d in step_diffs if d.change_type == "modified")
        steps_unchanged = sum(1 for d in step_diffs if d.change_type == "unchanged")

        # Calculate overall similarity
        if step_diffs:
            overall_similarity = sum(d.similarity for d in step_diffs) / len(step_diffs)
        else:
            overall_similarity = 1.0

        return DiffResult(
            run_id_a=run_a.run_id,
            run_id_b=run_b.run_id,
            metadata_diff=metadata_diff,
            step_diffs=step_diffs,
            overall_similarity=overall_similarity,
            step_count_a=len(run_a.steps),
            step_count_b=len(run_b.steps),
            steps_added=steps_added,
            steps_removed=steps_removed,
            steps_modified=steps_modified,
            steps_unchanged=steps_unchanged,
        )

    def diff_steps_only(
        self,
        steps_a: list[AnyStep],
        steps_b: list[AnyStep],
    ) -> list[StepDiff]:
        """Compare just the steps (without full runs).

        Args:
            steps_a: First step list
            steps_b: Second step list

        Returns:
            List of step diffs
        """
        return self._diff_steps(steps_a, steps_b)

    def _diff_metadata(
        self,
        meta_a: RunMetadata,
        meta_b: RunMetadata,
    ) -> dict[str, tuple[Any, Any]]:
        """Compare metadata fields."""
        diffs: dict[str, tuple[Any, Any]] = {}

        # Compare key fields
        fields_to_compare = [
            "name", "project", "tags", "status", "model",
            "error", "failure_category",
        ]

        for field in fields_to_compare:
            val_a = getattr(meta_a, field, None)
            val_b = getattr(meta_b, field, None)

            if val_a != val_b:
                diffs[field] = (val_a, val_b)

        # Compare cost totals
        if meta_a.cost.total_usd != meta_b.cost.total_usd:
            diffs["cost.total_usd"] = (meta_a.cost.total_usd, meta_b.cost.total_usd)

        # Compare token totals
        if meta_a.tokens.total_tokens != meta_b.tokens.total_tokens:
            diffs["tokens.total_tokens"] = (meta_a.tokens.total_tokens, meta_b.tokens.total_tokens)

        return diffs

    def _diff_steps(
        self,
        steps_a: list[AnyStep],
        steps_b: list[AnyStep],
    ) -> list[StepDiff]:
        """Compare step sequences using Myers diff algorithm."""
        # Create step type sequences for alignment
        types_a = [s.step_type for s in steps_a]
        types_b = [s.step_type for s in steps_b]

        # Use difflib for sequence alignment
        matcher = difflib.SequenceMatcher(None, types_a, types_b)
        opcodes = matcher.get_opcodes()

        diffs: list[StepDiff] = []

        for tag, i1, i2, j1, j2 in opcodes:
            if tag == "equal":
                # Compare equal sections in detail
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    step_a = steps_a[i]
                    step_b = steps_b[j]
                    field_diffs, similarity = self._compare_steps(step_a, step_b)

                    change_type = "unchanged" if similarity == 1.0 else "modified"
                    diffs.append(StepDiff(
                        step_number_a=step_a.step_number,
                        step_number_b=step_b.step_number,
                        step_type=step_a.step_type,
                        change_type=change_type,
                        field_diffs=field_diffs,
                        similarity=similarity,
                    ))

            elif tag == "replace":
                # Steps were replaced
                for i in range(i1, i2):
                    step_a = steps_a[i]
                    diffs.append(StepDiff(
                        step_number_a=step_a.step_number,
                        step_number_b=None,
                        step_type=step_a.step_type,
                        change_type="removed",
                        similarity=0.0,
                    ))
                for j in range(j1, j2):
                    step_b = steps_b[j]
                    diffs.append(StepDiff(
                        step_number_a=None,
                        step_number_b=step_b.step_number,
                        step_type=step_b.step_type,
                        change_type="added",
                        similarity=0.0,
                    ))

            elif tag == "delete":
                for i in range(i1, i2):
                    step_a = steps_a[i]
                    diffs.append(StepDiff(
                        step_number_a=step_a.step_number,
                        step_number_b=None,
                        step_type=step_a.step_type,
                        change_type="removed",
                        similarity=0.0,
                    ))

            elif tag == "insert":
                for j in range(j1, j2):
                    step_b = steps_b[j]
                    diffs.append(StepDiff(
                        step_number_a=None,
                        step_number_b=step_b.step_number,
                        step_type=step_b.step_type,
                        change_type="added",
                        similarity=0.0,
                    ))

        return diffs

    def _compare_steps(
        self,
        step_a: AnyStep,
        step_b: AnyStep,
    ) -> tuple[dict[str, tuple[Any, Any]], float]:
        """Compare two steps field by field.

        Returns:
            Tuple of (field_diffs, similarity_score)
        """
        dict_a = step_a.model_dump()
        dict_b = step_b.model_dump()

        field_diffs: dict[str, tuple[Any, Any]] = {}
        total_fields = 0
        matching_fields = 0

        all_keys = set(dict_a.keys()) | set(dict_b.keys())

        for key in all_keys:
            if key in self._ignore_fields:
                continue

            val_a = dict_a.get(key)
            val_b = dict_b.get(key)

            total_fields += 1

            if val_a == val_b:
                matching_fields += 1
            else:
                field_diffs[key] = (val_a, val_b)

        similarity = matching_fields / total_fields if total_fields > 0 else 1.0

        return field_diffs, similarity

    def format_text_diff(
        self,
        text_a: str,
        text_b: str,
        context_lines: int = 3,
    ) -> str:
        """Format a unified diff between two text values.

        Args:
            text_a: First text
            text_b: Second text
            context_lines: Number of context lines

        Returns:
            Unified diff string
        """
        lines_a = text_a.splitlines(keepends=True)
        lines_b = text_b.splitlines(keepends=True)

        diff = difflib.unified_diff(
            lines_a,
            lines_b,
            fromfile="a",
            tofile="b",
            n=context_lines,
        )

        return "".join(diff)
