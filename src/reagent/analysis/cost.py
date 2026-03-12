"""Cost and token analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from reagent.schema.run import Run, RunSummary
from reagent.schema.steps import LLMCallStep, ToolCallStep


@dataclass
class ModelPricing:
    """Pricing information for a model."""

    model: str
    provider: str
    prompt_cost_per_1k: float  # USD per 1K prompt tokens
    completion_cost_per_1k: float  # USD per 1K completion tokens

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate cost for given token counts."""
        prompt_cost = (prompt_tokens / 1000) * self.prompt_cost_per_1k
        completion_cost = (completion_tokens / 1000) * self.completion_cost_per_1k
        return prompt_cost + completion_cost


# Default pricing (as of 2024)
DEFAULT_PRICING: dict[str, ModelPricing] = {
    # OpenAI
    "gpt-4": ModelPricing("gpt-4", "openai", 0.03, 0.06),
    "gpt-4-turbo": ModelPricing("gpt-4-turbo", "openai", 0.01, 0.03),
    "gpt-4-turbo-preview": ModelPricing("gpt-4-turbo-preview", "openai", 0.01, 0.03),
    "gpt-4o": ModelPricing("gpt-4o", "openai", 0.005, 0.015),
    "gpt-4o-mini": ModelPricing("gpt-4o-mini", "openai", 0.00015, 0.0006),
    "gpt-3.5-turbo": ModelPricing("gpt-3.5-turbo", "openai", 0.0005, 0.0015),
    "gpt-3.5-turbo-16k": ModelPricing("gpt-3.5-turbo-16k", "openai", 0.001, 0.002),
    # Anthropic
    "claude-3-opus": ModelPricing("claude-3-opus", "anthropic", 0.015, 0.075),
    "claude-3-sonnet": ModelPricing("claude-3-sonnet", "anthropic", 0.003, 0.015),
    "claude-3-haiku": ModelPricing("claude-3-haiku", "anthropic", 0.00025, 0.00125),
    "claude-2": ModelPricing("claude-2", "anthropic", 0.008, 0.024),
    # Mistral
    "mistral-large": ModelPricing("mistral-large", "mistral", 0.008, 0.024),
    "mistral-medium": ModelPricing("mistral-medium", "mistral", 0.0027, 0.0081),
    "mistral-small": ModelPricing("mistral-small", "mistral", 0.002, 0.006),
}


@dataclass
class CostBreakdown:
    """Cost breakdown by category."""

    total_usd: float = 0.0
    llm_cost_usd: float = 0.0
    tool_cost_usd: float = 0.0
    by_model: dict[str, float] = field(default_factory=dict)
    by_step_type: dict[str, float] = field(default_factory=dict)


@dataclass
class TokenBreakdown:
    """Token usage breakdown."""

    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass
class CostReport:
    """Cost analysis report for a run or set of runs."""

    # Summary
    total_cost_usd: float
    total_tokens: int
    run_count: int

    # Breakdowns
    cost_breakdown: CostBreakdown
    token_breakdown: TokenBreakdown

    # Per-run stats
    avg_cost_per_run: float
    avg_tokens_per_run: float
    min_cost: float
    max_cost: float

    # Top contributors
    most_expensive_model: str | None
    most_expensive_steps: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_cost_usd": self.total_cost_usd,
            "total_tokens": self.total_tokens,
            "run_count": self.run_count,
            "avg_cost_per_run": self.avg_cost_per_run,
            "avg_tokens_per_run": self.avg_tokens_per_run,
            "min_cost": self.min_cost,
            "max_cost": self.max_cost,
            "most_expensive_model": self.most_expensive_model,
            "cost_breakdown": {
                "total_usd": self.cost_breakdown.total_usd,
                "llm_cost_usd": self.cost_breakdown.llm_cost_usd,
                "tool_cost_usd": self.cost_breakdown.tool_cost_usd,
                "by_model": self.cost_breakdown.by_model,
            },
            "token_breakdown": {
                "total_tokens": self.token_breakdown.total_tokens,
                "prompt_tokens": self.token_breakdown.prompt_tokens,
                "completion_tokens": self.token_breakdown.completion_tokens,
                "by_model": self.token_breakdown.by_model,
            },
        }


class CostAnalyzer:
    """Analyzer for cost and token usage."""

    def __init__(
        self,
        pricing: dict[str, ModelPricing] | None = None,
    ) -> None:
        """Initialize the analyzer.

        Args:
            pricing: Custom pricing dictionary
        """
        self._pricing = pricing or DEFAULT_PRICING

    def analyze_run(self, run: Run) -> CostReport:
        """Analyze costs for a single run.

        Args:
            run: Run to analyze

        Returns:
            Cost report
        """
        return self.analyze_runs([run])

    def analyze_runs(self, runs: list[Run]) -> CostReport:
        """Analyze costs across multiple runs.

        Args:
            runs: Runs to analyze

        Returns:
            Aggregated cost report
        """
        cost_breakdown = CostBreakdown()
        token_breakdown = TokenBreakdown()
        run_costs: list[float] = []
        expensive_steps: list[dict[str, Any]] = []

        for run in runs:
            run_cost = 0.0

            for step in run.steps:
                step_cost = 0.0

                if isinstance(step, LLMCallStep):
                    # Get token usage
                    prompt_tokens = 0
                    completion_tokens = 0

                    if step.token_usage:
                        prompt_tokens = step.token_usage.prompt_tokens
                        completion_tokens = step.token_usage.completion_tokens

                    # Calculate cost
                    if step.cost_usd:
                        step_cost = step.cost_usd
                    else:
                        step_cost = self._estimate_cost(
                            step.model,
                            prompt_tokens,
                            completion_tokens,
                        )

                    # Update breakdowns
                    cost_breakdown.llm_cost_usd += step_cost
                    cost_breakdown.by_model[step.model] = (
                        cost_breakdown.by_model.get(step.model, 0) + step_cost
                    )

                    token_breakdown.total_tokens += prompt_tokens + completion_tokens
                    token_breakdown.prompt_tokens += prompt_tokens
                    token_breakdown.completion_tokens += completion_tokens

                    if step.model not in token_breakdown.by_model:
                        token_breakdown.by_model[step.model] = {
                            "total": 0,
                            "prompt": 0,
                            "completion": 0,
                        }
                    token_breakdown.by_model[step.model]["total"] += prompt_tokens + completion_tokens
                    token_breakdown.by_model[step.model]["prompt"] += prompt_tokens
                    token_breakdown.by_model[step.model]["completion"] += completion_tokens

                elif isinstance(step, ToolCallStep):
                    if step.cost_usd:
                        step_cost = step.cost_usd
                        cost_breakdown.tool_cost_usd += step_cost

                # Track by step type
                cost_breakdown.by_step_type[step.step_type] = (
                    cost_breakdown.by_step_type.get(step.step_type, 0) + step_cost
                )

                cost_breakdown.total_usd += step_cost
                run_cost += step_cost

                # Track expensive steps
                if step_cost > 0:
                    expensive_steps.append({
                        "run_id": str(run.run_id),
                        "step_number": step.step_number,
                        "step_type": step.step_type,
                        "cost_usd": step_cost,
                    })

            run_costs.append(run_cost)

        # Sort expensive steps
        expensive_steps.sort(key=lambda x: x["cost_usd"], reverse=True)

        # Find most expensive model
        most_expensive_model = None
        if cost_breakdown.by_model:
            most_expensive_model = max(
                cost_breakdown.by_model,
                key=lambda m: cost_breakdown.by_model[m],
            )

        # Calculate averages
        run_count = len(runs)
        avg_cost = cost_breakdown.total_usd / run_count if run_count > 0 else 0
        avg_tokens = token_breakdown.total_tokens / run_count if run_count > 0 else 0

        return CostReport(
            total_cost_usd=cost_breakdown.total_usd,
            total_tokens=token_breakdown.total_tokens,
            run_count=run_count,
            cost_breakdown=cost_breakdown,
            token_breakdown=token_breakdown,
            avg_cost_per_run=avg_cost,
            avg_tokens_per_run=avg_tokens,
            min_cost=min(run_costs) if run_costs else 0,
            max_cost=max(run_costs) if run_costs else 0,
            most_expensive_model=most_expensive_model,
            most_expensive_steps=expensive_steps[:10],
        )

    def _estimate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Estimate cost for a model call.

        Args:
            model: Model name
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            Estimated cost in USD
        """
        # Try exact match
        if model in self._pricing:
            return self._pricing[model].calculate_cost(prompt_tokens, completion_tokens)

        # Try partial match
        model_lower = model.lower()
        for name, pricing in self._pricing.items():
            if name.lower() in model_lower or model_lower in name.lower():
                return pricing.calculate_cost(prompt_tokens, completion_tokens)

        # Default to gpt-4 pricing as fallback
        return DEFAULT_PRICING["gpt-4"].calculate_cost(prompt_tokens, completion_tokens)

    def add_pricing(self, pricing: ModelPricing) -> None:
        """Add custom pricing for a model.

        Args:
            pricing: Pricing to add
        """
        self._pricing[pricing.model] = pricing

    def get_pricing(self, model: str) -> ModelPricing | None:
        """Get pricing for a model.

        Args:
            model: Model name

        Returns:
            Pricing or None
        """
        return self._pricing.get(model)
