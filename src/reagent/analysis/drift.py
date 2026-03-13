"""State drift detection between original and replayed runs.

Compares checkpoint state hashes and data between two runs to detect
when a replay diverges from the original execution. Supports:

1. Hash-based fast comparison at each checkpoint
2. Deep diff of state_data when hashes mismatch
3. Configurable tolerance (ignore fields, max allowed diffs)
4. Overall drift score and per-checkpoint results
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from reagent.schema.steps import CheckpointStep


@dataclass
class DriftConfig:
    """Configuration for drift detection tolerance."""

    ignore_fields: set[str] = field(
        default_factory=lambda: {"timestamp", "timestamp_start", "timestamp_end", "duration_ms"}
    )
    max_allowed_diffs: int = 0
    hash_mismatch_is_drift: bool = True
    score_threshold: float = 0.5
    max_diff_depth: int = 20


@dataclass
class CheckpointDrift:
    """Result for a single checkpoint comparison."""

    checkpoint_name: str | None
    step_number_original: int
    step_number_replay: int
    original_hash: str
    replay_hash: str
    hashes_match: bool
    field_diffs: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    diff_count: int = 0
    drifted: bool = False


@dataclass
class DriftReport:
    """Overall drift detection report."""

    original_run_id: UUID
    replay_run_id: UUID
    checkpoints_compared: int
    checkpoints_matched: int
    checkpoints_drifted: int
    checkpoint_results: list[CheckpointDrift] = field(default_factory=list)
    drift_score: float = 0.0
    significant_drift: bool = False
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report to a dictionary."""
        return {
            "original_run_id": str(self.original_run_id),
            "replay_run_id": str(self.replay_run_id),
            "checkpoints_compared": self.checkpoints_compared,
            "checkpoints_matched": self.checkpoints_matched,
            "checkpoints_drifted": self.checkpoints_drifted,
            "drift_score": round(self.drift_score, 4),
            "significant_drift": self.significant_drift,
            "summary": self.summary,
            "checkpoint_results": [
                {
                    "checkpoint_name": cr.checkpoint_name,
                    "step_number_original": cr.step_number_original,
                    "step_number_replay": cr.step_number_replay,
                    "original_hash": cr.original_hash,
                    "replay_hash": cr.replay_hash,
                    "hashes_match": cr.hashes_match,
                    "field_diffs": {
                        k: {"original": v[0], "replay": v[1]}
                        for k, v in cr.field_diffs.items()
                    },
                    "diff_count": cr.diff_count,
                    "drifted": cr.drifted,
                }
                for cr in self.checkpoint_results
            ],
        }


class DriftDetector:
    """Detects state drift between original and replayed runs at checkpoints."""

    def __init__(self, config: DriftConfig | None = None) -> None:
        self.config = config or DriftConfig()

    def analyze(
        self,
        original_checkpoints: list[CheckpointStep],
        replay_checkpoints: list[CheckpointStep],
        original_run_id: UUID | None = None,
        replay_run_id: UUID | None = None,
    ) -> DriftReport:
        """Compare checkpoint state between two sets of checkpoints.

        Args:
            original_checkpoints: Checkpoints from the original run.
            replay_checkpoints: Checkpoints from the replayed run.
            original_run_id: ID of the original run.
            replay_run_id: ID of the replay run.
        """
        from uuid import uuid4

        original_run_id = original_run_id or (
            original_checkpoints[0].run_id if original_checkpoints else uuid4()
        )
        replay_run_id = replay_run_id or (
            replay_checkpoints[0].run_id if replay_checkpoints else uuid4()
        )

        pairs = self._align_checkpoints(original_checkpoints, replay_checkpoints)

        if not pairs:
            return DriftReport(
                original_run_id=original_run_id,
                replay_run_id=replay_run_id,
                checkpoints_compared=0,
                checkpoints_matched=0,
                checkpoints_drifted=0,
                summary="No checkpoints to compare",
            )

        results: list[CheckpointDrift] = []
        for orig, replay in pairs:
            results.append(self.compare_checkpoint_pair(orig, replay))

        matched = sum(1 for r in results if not r.drifted)
        drifted = sum(1 for r in results if r.drifted)
        compared = len(results)
        score = drifted / compared if compared > 0 else 0.0

        summary_parts = []
        if drifted == 0:
            summary_parts.append(f"All {compared} checkpoints match")
        else:
            summary_parts.append(
                f"{drifted}/{compared} checkpoints drifted"
            )
            drifted_names = [
                r.checkpoint_name or f"step {r.step_number_original}"
                for r in results
                if r.drifted
            ]
            summary_parts.append(f"drifted at: {', '.join(drifted_names)}")

        return DriftReport(
            original_run_id=original_run_id,
            replay_run_id=replay_run_id,
            checkpoints_compared=compared,
            checkpoints_matched=matched,
            checkpoints_drifted=drifted,
            checkpoint_results=results,
            drift_score=score,
            significant_drift=score > self.config.score_threshold,
            summary="; ".join(summary_parts),
        )

    def analyze_runs(
        self,
        original_run: Any,
        replay_run: Any,
    ) -> DriftReport:
        """Compare checkpoint state between two Run objects."""
        original_checkpoints = [
            s for s in original_run.steps
            if isinstance(s, CheckpointStep)
        ]
        replay_checkpoints = [
            s for s in replay_run.steps
            if isinstance(s, CheckpointStep)
        ]
        return self.analyze(
            original_checkpoints,
            replay_checkpoints,
            original_run_id=original_run.metadata.run_id,
            replay_run_id=replay_run.metadata.run_id,
        )

    def compare_checkpoint_pair(
        self,
        original: CheckpointStep,
        replay: CheckpointStep,
    ) -> CheckpointDrift:
        """Compare a single pair of checkpoints."""
        hashes_match = original.state_hash == replay.state_hash

        field_diffs: dict[str, tuple[Any, Any]] = {}
        if not hashes_match and original.state_data and replay.state_data:
            field_diffs = self._deep_diff_state(
                original.state_data,
                replay.state_data,
            )

        diff_count = len(field_diffs)

        # Determine if this checkpoint has drifted
        if hashes_match:
            drifted = False
        elif self.config.hash_mismatch_is_drift:
            if diff_count <= self.config.max_allowed_diffs and original.state_data and replay.state_data:
                drifted = False
            else:
                drifted = True
        else:
            drifted = diff_count > self.config.max_allowed_diffs

        return CheckpointDrift(
            checkpoint_name=original.checkpoint_name,
            step_number_original=original.step_number,
            step_number_replay=replay.step_number,
            original_hash=original.state_hash,
            replay_hash=replay.state_hash,
            hashes_match=hashes_match,
            field_diffs=field_diffs,
            diff_count=diff_count,
            drifted=drifted,
        )

    def _align_checkpoints(
        self,
        original: list[CheckpointStep],
        replay: list[CheckpointStep],
    ) -> list[tuple[CheckpointStep, CheckpointStep]]:
        """Align checkpoints by name, falling back to positional order."""
        # Try name-based alignment first
        orig_named = {s.checkpoint_name: s for s in original if s.checkpoint_name}
        replay_named = {s.checkpoint_name: s for s in replay if s.checkpoint_name}

        if orig_named and replay_named:
            common_names = set(orig_named.keys()) & set(replay_named.keys())
            if common_names:
                # Sort by original step number for consistent ordering
                return [
                    (orig_named[name], replay_named[name])
                    for name in sorted(
                        common_names,
                        key=lambda n: orig_named[n].step_number,
                    )
                ]

        # Fallback: positional alignment
        return list(zip(original, replay))

    def _deep_diff_state(
        self,
        original: dict[str, Any],
        replay: dict[str, Any],
        prefix: str = "",
        depth: int = 0,
    ) -> dict[str, tuple[Any, Any]]:
        """Recursive deep diff of state dicts, skipping ignored fields."""
        if depth > self.config.max_diff_depth:
            return {}

        diffs: dict[str, tuple[Any, Any]] = {}
        all_keys = set(original.keys()) | set(replay.keys())

        for key in all_keys:
            if key in self.config.ignore_fields:
                continue

            full_key = f"{prefix}.{key}" if prefix else key
            orig_val = original.get(key)
            replay_val = replay.get(key)

            if orig_val == replay_val:
                continue

            # Recurse into nested dicts
            if isinstance(orig_val, dict) and isinstance(replay_val, dict):
                nested = self._deep_diff_state(
                    orig_val, replay_val, full_key, depth + 1
                )
                diffs.update(nested)
            else:
                diffs[full_key] = (orig_val, replay_val)

        return diffs

    @staticmethod
    def compute_state_hash(state_data: dict[str, Any]) -> str:
        """Compute a deterministic hash from state data.

        Uses the same pattern as other ReAgent hash functions.
        """
        raw = json.dumps(state_data, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
