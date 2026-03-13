"""Tests for state drift detection between original and replayed runs."""

from datetime import datetime
from uuid import uuid4

import pytest

from reagent.analysis.drift import (
    CheckpointDrift,
    DriftConfig,
    DriftDetector,
    DriftReport,
)
from reagent.schema.run import Run, RunConfig
from reagent.schema.steps import CheckpointStep


# ---- Helpers ----

_RUN_ID = uuid4()
_REPLAY_RUN_ID = uuid4()


def _checkpoint(
    step_number: int,
    state_hash: str,
    checkpoint_name: str | None = None,
    state_data: dict | None = None,
    run_id=_RUN_ID,
) -> CheckpointStep:
    return CheckpointStep(
        run_id=run_id,
        step_number=step_number,
        timestamp_start=datetime.utcnow(),
        checkpoint_name=checkpoint_name,
        state_hash=state_hash,
        state_data=state_data,
    )


def _make_run_with_checkpoints(
    checkpoints: list[CheckpointStep],
    run_id=None,
) -> Run:
    run = Run.create(RunConfig(name="test"))
    if run_id:
        run.metadata.run_id = run_id
    run.steps = checkpoints
    return run


# ============================================================
# Basic Checkpoint Drift
# ============================================================


class TestCheckpointDriftBasic:
    def test_identical_checkpoints_no_drift(self):
        orig = [_checkpoint(0, "abc123", "cp1"), _checkpoint(1, "def456", "cp2")]
        replay = [
            _checkpoint(0, "abc123", "cp1", run_id=_REPLAY_RUN_ID),
            _checkpoint(1, "def456", "cp2", run_id=_REPLAY_RUN_ID),
        ]
        report = DriftDetector().analyze(orig, replay)
        assert not report.significant_drift
        assert report.drift_score == 0.0
        assert report.checkpoints_matched == 2
        assert report.checkpoints_drifted == 0

    def test_different_hashes_detected(self):
        orig = [_checkpoint(0, "abc123", "cp1")]
        replay = [_checkpoint(0, "xyz789", "cp1", run_id=_REPLAY_RUN_ID)]
        report = DriftDetector().analyze(orig, replay)
        assert report.checkpoints_drifted == 1
        assert report.drift_score == 1.0
        assert not report.checkpoint_results[0].hashes_match

    def test_deep_diff_on_mismatch(self):
        orig = [
            _checkpoint(
                0,
                "aaa",
                "cp1",
                state_data={"counter": 5, "status": "ok"},
            )
        ]
        replay = [
            _checkpoint(
                0,
                "bbb",
                "cp1",
                state_data={"counter": 10, "status": "ok"},
                run_id=_REPLAY_RUN_ID,
            )
        ]
        report = DriftDetector().analyze(orig, replay)
        result = report.checkpoint_results[0]
        assert not result.hashes_match
        assert "counter" in result.field_diffs
        assert result.field_diffs["counter"] == (5, 10)
        assert "status" not in result.field_diffs

    def test_no_state_data_hash_only(self):
        orig = [_checkpoint(0, "aaa", "cp1")]
        replay = [_checkpoint(0, "bbb", "cp1", run_id=_REPLAY_RUN_ID)]
        report = DriftDetector().analyze(orig, replay)
        result = report.checkpoint_results[0]
        assert not result.hashes_match
        assert result.drifted
        assert result.diff_count == 0  # No state_data to diff

    def test_no_checkpoints(self):
        report = DriftDetector().analyze([], [])
        assert report.checkpoints_compared == 0
        assert report.drift_score == 0.0
        assert not report.significant_drift


# ============================================================
# Drift Config
# ============================================================


class TestDriftConfig:
    def test_ignore_fields_respected(self):
        config = DriftConfig(ignore_fields={"counter"})
        orig = [
            _checkpoint(0, "aaa", "cp1", state_data={"counter": 5, "name": "x"})
        ]
        replay = [
            _checkpoint(
                0, "bbb", "cp1",
                state_data={"counter": 999, "name": "x"},
                run_id=_REPLAY_RUN_ID,
            )
        ]
        detector = DriftDetector(config)
        report = detector.analyze(orig, replay)
        result = report.checkpoint_results[0]
        assert "counter" not in result.field_diffs
        # No non-ignored diffs, but hash mismatch still counts as drift
        assert result.diff_count == 0

    def test_max_allowed_diffs_tolerance(self):
        """With state_data and max_allowed_diffs, small diffs are tolerated."""
        config = DriftConfig(max_allowed_diffs=3, hash_mismatch_is_drift=True)
        orig = [
            _checkpoint(
                0, "aaa", "cp1",
                state_data={"a": 1, "b": 2, "c": 3, "d": 4},
            )
        ]
        # 2 field diffs (within tolerance of 3)
        replay_ok = [
            _checkpoint(
                0, "bbb", "cp1",
                state_data={"a": 1, "b": 99, "c": 88, "d": 4},
                run_id=_REPLAY_RUN_ID,
            )
        ]
        report = DriftDetector(config).analyze(orig, replay_ok)
        assert not report.checkpoint_results[0].drifted

        # 4 field diffs (exceeds tolerance of 3)
        replay_bad = [
            _checkpoint(
                0, "ccc", "cp1",
                state_data={"a": 10, "b": 20, "c": 30, "d": 40},
                run_id=_REPLAY_RUN_ID,
            )
        ]
        report = DriftDetector(config).analyze(orig, replay_bad)
        assert report.checkpoint_results[0].drifted

    def test_score_threshold(self):
        config = DriftConfig(score_threshold=0.8)
        # 1 of 2 checkpoints drifted -> score 0.5, below 0.8
        orig = [
            _checkpoint(0, "aaa", "cp1"),
            _checkpoint(1, "bbb", "cp2"),
        ]
        replay = [
            _checkpoint(0, "aaa", "cp1", run_id=_REPLAY_RUN_ID),
            _checkpoint(1, "zzz", "cp2", run_id=_REPLAY_RUN_ID),
        ]
        report = DriftDetector(config).analyze(orig, replay)
        assert report.drift_score == 0.5
        assert not report.significant_drift  # Below 0.8

    def test_hash_mismatch_is_drift_false(self):
        """When hash_mismatch_is_drift=False, only field diffs matter."""
        config = DriftConfig(hash_mismatch_is_drift=False, max_allowed_diffs=0)
        orig = [
            _checkpoint(
                0, "aaa", "cp1",
                state_data={"x": 1},
            )
        ]
        replay = [
            _checkpoint(
                0, "bbb", "cp1",
                state_data={"x": 1},  # Same data, different hash
                run_id=_REPLAY_RUN_ID,
            )
        ]
        report = DriftDetector(config).analyze(orig, replay)
        assert not report.checkpoint_results[0].drifted

    def test_default_config(self):
        config = DriftConfig()
        assert config.max_allowed_diffs == 0
        assert config.hash_mismatch_is_drift is True
        assert config.score_threshold == 0.5
        assert "timestamp" in config.ignore_fields


# ============================================================
# Checkpoint Alignment
# ============================================================


class TestCheckpointAlignment:
    def test_alignment_by_name(self):
        """Checkpoints with same names but different step numbers align."""
        orig = [
            _checkpoint(0, "aaa", "init"),
            _checkpoint(5, "bbb", "mid"),
        ]
        replay = [
            _checkpoint(1, "aaa", "init", run_id=_REPLAY_RUN_ID),
            _checkpoint(8, "bbb", "mid", run_id=_REPLAY_RUN_ID),
        ]
        report = DriftDetector().analyze(orig, replay)
        assert report.checkpoints_compared == 2
        assert report.checkpoints_matched == 2
        # Verify alignment used step numbers from both
        r0 = report.checkpoint_results[0]
        assert r0.step_number_original == 0
        assert r0.step_number_replay == 1

    def test_alignment_by_position_fallback(self):
        """Unnamed checkpoints align by position."""
        orig = [_checkpoint(0, "aaa"), _checkpoint(1, "bbb")]
        replay = [
            _checkpoint(0, "aaa", run_id=_REPLAY_RUN_ID),
            _checkpoint(1, "bbb", run_id=_REPLAY_RUN_ID),
        ]
        report = DriftDetector().analyze(orig, replay)
        assert report.checkpoints_compared == 2

    def test_unequal_checkpoint_counts(self):
        """Only pairs up to the shorter list."""
        orig = [
            _checkpoint(0, "aaa"),
            _checkpoint(1, "bbb"),
            _checkpoint(2, "ccc"),
        ]
        replay = [_checkpoint(0, "aaa", run_id=_REPLAY_RUN_ID)]
        report = DriftDetector().analyze(orig, replay)
        assert report.checkpoints_compared == 1


# ============================================================
# Drift Report
# ============================================================


class TestDriftReport:
    def test_to_dict_serialization(self):
        orig = [
            _checkpoint(0, "aaa", "cp1", state_data={"x": 1}),
        ]
        replay = [
            _checkpoint(0, "bbb", "cp1", state_data={"x": 2}, run_id=_REPLAY_RUN_ID),
        ]
        report = DriftDetector().analyze(
            orig, replay,
            original_run_id=_RUN_ID,
            replay_run_id=_REPLAY_RUN_ID,
        )
        d = report.to_dict()
        assert d["original_run_id"] == str(_RUN_ID)
        assert d["replay_run_id"] == str(_REPLAY_RUN_ID)
        assert d["checkpoints_compared"] == 1
        assert d["checkpoints_drifted"] == 1
        assert len(d["checkpoint_results"]) == 1
        cr = d["checkpoint_results"][0]
        assert cr["checkpoint_name"] == "cp1"
        assert "x" in cr["field_diffs"]
        assert cr["field_diffs"]["x"]["original"] == 1
        assert cr["field_diffs"]["x"]["replay"] == 2

    def test_drift_score_calculation(self):
        orig = [
            _checkpoint(0, "aaa", "cp1"),
            _checkpoint(1, "bbb", "cp2"),
            _checkpoint(2, "ccc", "cp3"),
            _checkpoint(3, "ddd", "cp4"),
        ]
        replay = [
            _checkpoint(0, "aaa", "cp1", run_id=_REPLAY_RUN_ID),
            _checkpoint(1, "zzz", "cp2", run_id=_REPLAY_RUN_ID),  # drifted
            _checkpoint(2, "ccc", "cp3", run_id=_REPLAY_RUN_ID),
            _checkpoint(3, "yyy", "cp4", run_id=_REPLAY_RUN_ID),  # drifted
        ]
        report = DriftDetector().analyze(orig, replay)
        assert report.drift_score == 0.5  # 2/4

    def test_summary_no_drift(self):
        orig = [_checkpoint(0, "aaa", "cp1")]
        replay = [_checkpoint(0, "aaa", "cp1", run_id=_REPLAY_RUN_ID)]
        report = DriftDetector().analyze(orig, replay)
        assert "All 1 checkpoints match" in report.summary

    def test_summary_with_drift(self):
        orig = [_checkpoint(0, "aaa", "cp1")]
        replay = [_checkpoint(0, "zzz", "cp1", run_id=_REPLAY_RUN_ID)]
        report = DriftDetector().analyze(orig, replay)
        assert "1/1 checkpoints drifted" in report.summary
        assert "cp1" in report.summary


# ============================================================
# Deep Diff
# ============================================================


class TestDeepDiffState:
    def test_flat_dict_diff(self):
        detector = DriftDetector()
        diffs = detector._deep_diff_state(
            {"a": 1, "b": 2, "c": 3},
            {"a": 1, "b": 99, "c": 3},
        )
        assert diffs == {"b": (2, 99)}

    def test_nested_dict_diff(self):
        detector = DriftDetector()
        diffs = detector._deep_diff_state(
            {"outer": {"inner": 1, "same": "ok"}},
            {"outer": {"inner": 2, "same": "ok"}},
        )
        assert "outer.inner" in diffs
        assert diffs["outer.inner"] == (1, 2)

    def test_list_diff(self):
        detector = DriftDetector()
        diffs = detector._deep_diff_state(
            {"items": [1, 2, 3]},
            {"items": [1, 2, 4]},
        )
        assert "items" in diffs

    def test_identical_state_no_diffs(self):
        detector = DriftDetector()
        diffs = detector._deep_diff_state(
            {"a": 1, "b": {"c": 2}},
            {"a": 1, "b": {"c": 2}},
        )
        assert len(diffs) == 0

    def test_missing_keys(self):
        detector = DriftDetector()
        diffs = detector._deep_diff_state(
            {"a": 1, "b": 2},
            {"a": 1},
        )
        assert "b" in diffs
        assert diffs["b"] == (2, None)

    def test_added_keys(self):
        detector = DriftDetector()
        diffs = detector._deep_diff_state(
            {"a": 1},
            {"a": 1, "b": 2},
        )
        assert "b" in diffs
        assert diffs["b"] == (None, 2)

    def test_ignore_fields_in_nested(self):
        config = DriftConfig(ignore_fields={"timestamp"})
        detector = DriftDetector(config)
        diffs = detector._deep_diff_state(
            {"data": {"value": 1, "timestamp": "old"}},
            {"data": {"value": 1, "timestamp": "new"}},
        )
        assert len(diffs) == 0


# ============================================================
# analyze_runs
# ============================================================


class TestAnalyzeRuns:
    def test_matching_runs(self):
        orig_run = _make_run_with_checkpoints([
            _checkpoint(0, "aaa", "cp1"),
            _checkpoint(1, "bbb", "cp2"),
        ])
        replay_run = _make_run_with_checkpoints([
            _checkpoint(0, "aaa", "cp1"),
            _checkpoint(1, "bbb", "cp2"),
        ])
        report = DriftDetector().analyze_runs(orig_run, replay_run)
        assert report.checkpoints_matched == 2
        assert report.drift_score == 0.0

    def test_drifted_runs(self):
        orig_run = _make_run_with_checkpoints([
            _checkpoint(0, "aaa", "cp1"),
        ])
        replay_run = _make_run_with_checkpoints([
            _checkpoint(0, "zzz", "cp1"),
        ])
        report = DriftDetector().analyze_runs(orig_run, replay_run)
        assert report.checkpoints_drifted == 1

    def test_runs_with_no_checkpoints(self):
        orig_run = _make_run_with_checkpoints([])
        replay_run = _make_run_with_checkpoints([])
        report = DriftDetector().analyze_runs(orig_run, replay_run)
        assert report.checkpoints_compared == 0


# ============================================================
# Compute State Hash
# ============================================================


class TestComputeStateHash:
    def test_deterministic(self):
        data = {"b": 2, "a": 1}
        h1 = DriftDetector.compute_state_hash(data)
        h2 = DriftDetector.compute_state_hash(data)
        assert h1 == h2

    def test_different_data_different_hash(self):
        h1 = DriftDetector.compute_state_hash({"a": 1})
        h2 = DriftDetector.compute_state_hash({"a": 2})
        assert h1 != h2

    def test_key_order_independent(self):
        h1 = DriftDetector.compute_state_hash({"a": 1, "b": 2})
        h2 = DriftDetector.compute_state_hash({"b": 2, "a": 1})
        assert h1 == h2


# ============================================================
# Replay Session Integration
# ============================================================


class TestReplaySessionCheckpoints:
    def test_record_and_retrieve_checkpoint_state(self):
        from reagent.core.constants import ReplayMode
        from reagent.replay.session import ReplaySession
        from reagent.schema.run import RunMetadata

        meta = RunMetadata(
            run_id=_RUN_ID,
            start_time=datetime.utcnow(),
        )
        session = ReplaySession(
            run_id=_RUN_ID,
            original_metadata=meta,
            mode=ReplayMode.STRICT,
        )

        session.record_checkpoint_state(
            step_number=5,
            checkpoint_name="mid",
            state_hash="abc123",
            state_data={"counter": 42},
        )

        assert len(session.replay_checkpoints) == 1
        cp = session.replay_checkpoints[0]
        assert cp["step_number"] == 5
        assert cp["checkpoint_name"] == "mid"
        assert cp["state_hash"] == "abc123"
        assert cp["state_data"]["counter"] == 42
