"""Loop detection for agent reasoning traces.

Detects repeated patterns in step sequences that indicate an agent
is stuck in a loop — repeating the same actions without progress.

Three detection strategies:
1. Consecutive identical steps (highest confidence)
2. Cyclic sequences like A→B→C→A→B→C (medium confidence)
3. Non-consecutive repetition of the same action (lower confidence)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from reagent.schema.steps import (
    AgentStep,
    AnyStep,
    LLMCallStep,
    ToolCallStep,
)

if TYPE_CHECKING:
    from reagent.schema.run import Run


@dataclass
class LoopConfig:
    """Configuration thresholds for loop detection."""

    min_repetitions: int = 3
    max_cycle_length: int = 10


@dataclass
class LoopPattern:
    """A single detected loop pattern."""

    pattern_type: str  # "consecutive", "cyclic", "non_consecutive"
    start_step: int
    end_step: int
    cycle_length: int
    repetitions: int
    description: str


@dataclass
class LoopDetectionResult:
    """Overall result of loop detection analysis."""

    loop_detected: bool
    patterns: list[LoopPattern] = field(default_factory=list)
    confidence: float = 0.0
    summary: str = ""


def _stable_hash(obj: object) -> str:
    """Deterministic hash of an arbitrary object."""
    raw = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _fingerprint(step: AnyStep) -> str:
    """Create a fingerprint string for a step based on its type."""
    if isinstance(step, ToolCallStep):
        return f"tool:{step.tool_name}:{_stable_hash(step.input.kwargs)}"
    if isinstance(step, LLMCallStep):
        content = step.prompt or step.messages
        return f"llm:{step.model}:{_stable_hash(content)}"
    if isinstance(step, AgentStep):
        return (
            f"agent:{step.agent_name}:{step.action}:"
            f"{_stable_hash(step.action_input)}"
        )
    # Generic fallback
    return f"{step.step_type}:{step.step_id}"


class LoopDetector:
    """Detects reasoning loops in agent step sequences."""

    def __init__(self, config: LoopConfig | None = None) -> None:
        self.config = config or LoopConfig()

    def analyze(self, steps: list[AnyStep]) -> LoopDetectionResult:
        """Analyze a list of steps for loop patterns."""
        if len(steps) < self.config.min_repetitions:
            return LoopDetectionResult(
                loop_detected=False, summary="Too few steps to detect loops"
            )

        fingerprints = [_fingerprint(s) for s in steps]
        patterns: list[LoopPattern] = []

        patterns.extend(self._detect_consecutive(fingerprints))
        patterns.extend(self._detect_cyclic(fingerprints))
        patterns.extend(self._detect_non_consecutive(steps))

        if not patterns:
            return LoopDetectionResult(
                loop_detected=False, summary="No loop patterns detected"
            )

        confidence = max(p_conf for p_conf in self._pattern_confidences(patterns))
        summary_parts = [p.description for p in patterns]
        return LoopDetectionResult(
            loop_detected=True,
            patterns=patterns,
            confidence=confidence,
            summary="; ".join(summary_parts),
        )

    def analyze_run(self, run: Run) -> LoopDetectionResult:
        """Analyze a Run object for loop patterns."""
        return self.analyze(list(run.steps))

    # ------------------------------------------------------------------
    # Strategy 1: Consecutive identical steps
    # ------------------------------------------------------------------

    def _detect_consecutive(
        self, fingerprints: list[str]
    ) -> list[LoopPattern]:
        patterns: list[LoopPattern] = []
        i = 0
        while i < len(fingerprints):
            run_length = 1
            while (
                i + run_length < len(fingerprints)
                and fingerprints[i + run_length] == fingerprints[i]
            ):
                run_length += 1

            if run_length >= self.config.min_repetitions:
                patterns.append(
                    LoopPattern(
                        pattern_type="consecutive",
                        start_step=i,
                        end_step=i + run_length - 1,
                        cycle_length=1,
                        repetitions=run_length,
                        description=(
                            f"Step repeated {run_length} times consecutively "
                            f"(steps {i}-{i + run_length - 1})"
                        ),
                    )
                )
            i += max(run_length, 1)
        return patterns

    # ------------------------------------------------------------------
    # Strategy 2: Cyclic sequences (A→B→C→A→B→C)
    # ------------------------------------------------------------------

    def _detect_cyclic(self, fingerprints: list[str]) -> list[LoopPattern]:
        patterns: list[LoopPattern] = []
        n = len(fingerprints)

        for cycle_len in range(2, min(self.config.max_cycle_length + 1, n // 2 + 1)):
            for start in range(n - cycle_len * self.config.min_repetitions + 1):
                cycle = fingerprints[start : start + cycle_len]
                reps = 1
                pos = start + cycle_len
                while pos + cycle_len <= n:
                    if fingerprints[pos : pos + cycle_len] == cycle:
                        reps += 1
                        pos += cycle_len
                    else:
                        break

                if reps >= self.config.min_repetitions:
                    end = start + cycle_len * reps - 1
                    # Avoid reporting if already covered by a longer pattern
                    if not any(
                        p.start_step == start
                        and p.end_step == end
                        and p.pattern_type == "cyclic"
                        for p in patterns
                    ):
                        patterns.append(
                            LoopPattern(
                                pattern_type="cyclic",
                                start_step=start,
                                end_step=end,
                                cycle_length=cycle_len,
                                repetitions=reps,
                                description=(
                                    f"Cycle of length {cycle_len} repeated "
                                    f"{reps} times (steps {start}-{end})"
                                ),
                            )
                        )
        return patterns

    # ------------------------------------------------------------------
    # Strategy 3: Non-consecutive agent repetition
    # ------------------------------------------------------------------

    def _detect_non_consecutive(self, steps: list[AnyStep]) -> list[LoopPattern]:
        patterns: list[LoopPattern] = []
        action_positions: dict[str, list[int]] = {}

        for i, step in enumerate(steps):
            if isinstance(step, AgentStep) and step.action is not None:
                key = f"{step.action}:{_stable_hash(step.action_input)}"
                action_positions.setdefault(key, []).append(i)

        for key, positions in action_positions.items():
            if len(positions) >= self.config.min_repetitions:
                # Only report if not all consecutive (that's strategy 1)
                if not all(
                    positions[j] == positions[j - 1] + 1
                    for j in range(1, len(positions))
                ):
                    patterns.append(
                        LoopPattern(
                            pattern_type="non_consecutive",
                            start_step=positions[0],
                            end_step=positions[-1],
                            cycle_length=1,
                            repetitions=len(positions),
                            description=(
                                f"Same agent action repeated {len(positions)} "
                                f"times non-consecutively "
                                f"(steps {positions[0]}-{positions[-1]})"
                            ),
                        )
                    )
        return patterns

    # ------------------------------------------------------------------
    # Confidence mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _pattern_confidences(patterns: list[LoopPattern]) -> list[float]:
        confidence_map = {
            "consecutive": 0.95,
            "cyclic": 0.85,
            "non_consecutive": 0.75,
        }
        return [
            confidence_map.get(p.pattern_type, 0.5) for p in patterns
        ]
