"""Tests for the reasoning loop detector."""

from datetime import datetime
from uuid import uuid4

import pytest

from reagent.analysis.loop_detector import (
    LoopConfig,
    LoopDetectionResult,
    LoopDetector,
    LoopPattern,
)
from reagent.classification.classifier import FailureClassifier, classify_failure
from reagent.core.constants import FailureCategory
from reagent.schema.run import Run, RunConfig
from reagent.schema.steps import (
    AgentStep,
    LLMCallStep,
    ToolCallStep,
    ToolInput,
    ToolOutput,
)


# ---- Helpers ----

_RUN_ID = uuid4()


def _tool_step(name: str, step_number: int = 0, **kwargs) -> ToolCallStep:
    return ToolCallStep(
        run_id=_RUN_ID,
        step_number=step_number,
        timestamp_start=datetime.utcnow(),
        tool_name=name,
        input=ToolInput(kwargs=kwargs),
    )


def _llm_step(model: str, prompt: str, step_number: int = 0) -> LLMCallStep:
    return LLMCallStep(
        run_id=_RUN_ID,
        step_number=step_number,
        timestamp_start=datetime.utcnow(),
        model=model,
        prompt=prompt,
    )


def _agent_step(
    action: str,
    action_input: dict | None = None,
    step_number: int = 0,
    agent_name: str | None = None,
) -> AgentStep:
    return AgentStep(
        run_id=_RUN_ID,
        step_number=step_number,
        timestamp_start=datetime.utcnow(),
        action=action,
        action_input=action_input or {},
        agent_name=agent_name,
    )


# ============================================================
# Consecutive Detection
# ============================================================


class TestConsecutiveDetection:
    def test_identical_tool_calls(self):
        steps = [_tool_step("search", query="hello") for _ in range(5)]
        result = LoopDetector().analyze(steps)
        assert result.loop_detected
        assert any(p.pattern_type == "consecutive" for p in result.patterns)
        assert result.confidence == 0.95

    def test_identical_llm_prompts(self):
        steps = [_llm_step("gpt-4", "Tell me a joke") for _ in range(4)]
        result = LoopDetector().analyze(steps)
        assert result.loop_detected
        assert any(p.pattern_type == "consecutive" for p in result.patterns)

    def test_identical_agent_actions(self):
        steps = [_agent_step("search", {"q": "test"}) for _ in range(3)]
        result = LoopDetector().analyze(steps)
        assert result.loop_detected

    def test_below_threshold_not_detected(self):
        steps = [_tool_step("search", query="hello") for _ in range(2)]
        result = LoopDetector().analyze(steps)
        assert not result.loop_detected

    def test_different_inputs_not_detected(self):
        steps = [_tool_step("search", query=f"q{i}") for i in range(5)]
        result = LoopDetector().analyze(steps)
        # No consecutive matches (all different)
        consecutive = [p for p in result.patterns if p.pattern_type == "consecutive"]
        assert len(consecutive) == 0


# ============================================================
# Cyclic Detection
# ============================================================


class TestCyclicDetection:
    def test_ab_ab_ab(self):
        """A→B repeated 3 times."""
        a = _tool_step("search", query="x")
        b = _tool_step("write", content="y")
        steps = [a, b, a, b, a, b]
        # Need new objects with same fingerprint
        steps = []
        for _ in range(3):
            steps.append(_tool_step("search", query="x"))
            steps.append(_tool_step("write", content="y"))

        result = LoopDetector().analyze(steps)
        assert result.loop_detected
        cyclic = [p for p in result.patterns if p.pattern_type == "cyclic"]
        assert len(cyclic) > 0
        assert cyclic[0].cycle_length == 2
        assert result.confidence >= 0.85

    def test_abc_abc_abc(self):
        """A→B→C repeated 3 times."""
        steps = []
        for _ in range(3):
            steps.append(_tool_step("search", query="x"))
            steps.append(_tool_step("write", content="y"))
            steps.append(_tool_step("delete", id="z"))

        result = LoopDetector().analyze(steps)
        assert result.loop_detected
        cyclic = [p for p in result.patterns if p.pattern_type == "cyclic"]
        assert any(p.cycle_length == 3 for p in cyclic)

    def test_no_cycle_in_varied_sequence(self):
        steps = [_tool_step(f"tool_{i}", idx=i) for i in range(6)]
        result = LoopDetector().analyze(steps)
        cyclic = [p for p in result.patterns if p.pattern_type == "cyclic"]
        assert len(cyclic) == 0


# ============================================================
# Non-Consecutive Repetition
# ============================================================


class TestNonConsecutiveRepetition:
    def test_same_action_interleaved(self):
        """Same agent action with different steps in between."""
        steps = []
        for i in range(3):
            steps.append(_agent_step("search", {"q": "test"}, step_number=i * 2))
            steps.append(_tool_step("other_tool", step_number=i * 2 + 1, data=str(i)))

        result = LoopDetector().analyze(steps)
        assert result.loop_detected
        non_consec = [
            p for p in result.patterns if p.pattern_type == "non_consecutive"
        ]
        assert len(non_consec) > 0
        assert non_consec[0].repetitions == 3

    def test_different_actions_no_detection(self):
        steps = [_agent_step(f"action_{i}", {"q": f"q{i}"}) for i in range(5)]
        result = LoopDetector().analyze(steps)
        non_consec = [
            p for p in result.patterns if p.pattern_type == "non_consecutive"
        ]
        assert len(non_consec) == 0


# ============================================================
# analyze_run
# ============================================================


class TestLoopDetectorWithRun:
    def test_looping_run(self):
        run = Run.create(RunConfig(name="loop-test"))
        for i in range(5):
            run.steps.append(
                _tool_step("search", step_number=i, query="same")
            )

        result = LoopDetector().analyze_run(run)
        assert result.loop_detected
        assert result.confidence >= 0.9

    def test_normal_run(self):
        run = Run.create(RunConfig(name="normal"))
        for i in range(5):
            run.steps.append(
                _tool_step(f"tool_{i}", step_number=i, data=str(i))
            )

        result = LoopDetector().analyze_run(run)
        # Should not detect consecutive or non-consecutive patterns
        assert not any(
            p.pattern_type in ("consecutive", "non_consecutive")
            for p in result.patterns
        )


# ============================================================
# Custom Config
# ============================================================


class TestLoopConfig:
    def test_higher_min_repetitions(self):
        """With min_repetitions=5, 4 repeats should not trigger."""
        config = LoopConfig(min_repetitions=5)
        steps = [_tool_step("search", query="x") for _ in range(4)]
        result = LoopDetector(config).analyze(steps)
        assert not result.loop_detected

    def test_lower_min_repetitions(self):
        """With min_repetitions=2, 2 repeats should trigger."""
        config = LoopConfig(min_repetitions=2)
        steps = [_tool_step("search", query="x") for _ in range(2)]
        result = LoopDetector(config).analyze(steps)
        assert result.loop_detected

    def test_max_cycle_length_limits_detection(self):
        """Cycle longer than max_cycle_length should not be detected."""
        config = LoopConfig(max_cycle_length=2)
        # Create cycle of length 3
        steps = []
        for _ in range(3):
            steps.append(_tool_step("a", x="1"))
            steps.append(_tool_step("b", x="2"))
            steps.append(_tool_step("c", x="3"))

        result = LoopDetector(config).analyze(steps)
        cyclic = [p for p in result.patterns if p.pattern_type == "cyclic"]
        assert not any(p.cycle_length == 3 for p in cyclic)


# ============================================================
# Classifier Integration
# ============================================================


class TestClassifierIntegration:
    def test_reasoning_loop_from_error_message(self):
        result = classify_failure(error="Agent stuck in a loop after 10 iterations")
        assert result.category == FailureCategory.REASONING_LOOP

    def test_max_iterations_exceeded(self):
        result = classify_failure(error="Maximum iterations exceeded")
        assert result.category == FailureCategory.REASONING_LOOP

    def test_too_many_retries(self):
        result = classify_failure(error="too many retries")
        assert result.category == FailureCategory.REASONING_LOOP

    def test_infinite_loop_detected(self):
        result = classify_failure(error="infinite loop detected in agent execution")
        assert result.category == FailureCategory.REASONING_LOOP

    def test_loop_detection_from_steps(self):
        """Classifier detects loop from step sequences when no error pattern matches."""
        steps = [_tool_step("search", query="hello") for _ in range(5)]
        classifier = FailureClassifier()
        result = classifier.classify(
            error="unknown failure",
            steps=steps,
        )
        assert result.category == FailureCategory.REASONING_LOOP
        assert result.rule_name == "step_sequence_loop"
        assert result.confidence >= 0.9

    def test_no_loop_detection_when_error_matches_first(self):
        """Error pattern rules take priority over step-based loop detection."""
        steps = [_tool_step("search", query="hello") for _ in range(5)]
        result = classify_failure(error="request timeout", steps=steps)
        assert result.category == FailureCategory.TOOL_TIMEOUT


# ============================================================
# No False Positives
# ============================================================


class TestNoFalsePositives:
    def test_varied_tool_calls(self):
        steps = [
            _tool_step("search", query="weather"),
            _tool_step("calculator", expr="2+2"),
            _tool_step("write", content="The answer is 4"),
            _llm_step("gpt-4", "Summarize the results"),
            _agent_step("respond", {"message": "done"}),
        ]
        result = LoopDetector().analyze(steps)
        assert not result.loop_detected

    def test_similar_but_not_identical(self):
        """Steps with same tool but different inputs should not trigger."""
        steps = [
            _tool_step("search", query="cats"),
            _tool_step("search", query="dogs"),
            _tool_step("search", query="birds"),
            _tool_step("search", query="fish"),
        ]
        result = LoopDetector().analyze(steps)
        consecutive = [p for p in result.patterns if p.pattern_type == "consecutive"]
        assert len(consecutive) == 0

    def test_empty_steps(self):
        result = LoopDetector().analyze([])
        assert not result.loop_detected

    def test_single_step(self):
        result = LoopDetector().analyze([_tool_step("search", query="x")])
        assert not result.loop_detected
