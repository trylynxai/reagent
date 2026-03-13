"""Cost and token analytics with multi-provider pricing.

Provides a centralized pricing database for LLM providers (OpenAI, Anthropic,
Google, Cohere, Mistral, Meta/Llama) and cost analysis tools.

Usage:
    # Estimate cost for a single call
    from reagent.analysis.cost import estimate_cost
    cost = estimate_cost("gpt-4o", prompt_tokens=1000, completion_tokens=500)

    # Analyze a run
    analyzer = CostAnalyzer()
    report = analyzer.analyze_run(run)
    print(report.cost_breakdown.by_provider)

    # Add custom pricing
    analyzer.add_pricing(ModelPricing("my-model", "custom", 0.01, 0.02))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from reagent.schema.run import Run
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


# ---------------------------------------------------------------------------
# Multi-provider pricing database (as of early 2025)
# ---------------------------------------------------------------------------

DEFAULT_PRICING: dict[str, ModelPricing] = {
    # -----------------------------------------------------------------------
    # OpenAI
    # -----------------------------------------------------------------------
    "gpt-4": ModelPricing("gpt-4", "openai", 0.03, 0.06),
    "gpt-4-32k": ModelPricing("gpt-4-32k", "openai", 0.06, 0.12),
    "gpt-4-turbo": ModelPricing("gpt-4-turbo", "openai", 0.01, 0.03),
    "gpt-4-turbo-preview": ModelPricing("gpt-4-turbo-preview", "openai", 0.01, 0.03),
    "gpt-4o": ModelPricing("gpt-4o", "openai", 0.0025, 0.01),
    "gpt-4o-2024-11-20": ModelPricing("gpt-4o-2024-11-20", "openai", 0.0025, 0.01),
    "gpt-4o-mini": ModelPricing("gpt-4o-mini", "openai", 0.00015, 0.0006),
    "gpt-4o-mini-2024-07-18": ModelPricing("gpt-4o-mini-2024-07-18", "openai", 0.00015, 0.0006),
    "gpt-4.1": ModelPricing("gpt-4.1", "openai", 0.002, 0.008),
    "gpt-4.1-mini": ModelPricing("gpt-4.1-mini", "openai", 0.0004, 0.0016),
    "gpt-4.1-nano": ModelPricing("gpt-4.1-nano", "openai", 0.0001, 0.0004),
    "gpt-3.5-turbo": ModelPricing("gpt-3.5-turbo", "openai", 0.0005, 0.0015),
    "gpt-3.5-turbo-16k": ModelPricing("gpt-3.5-turbo-16k", "openai", 0.001, 0.002),
    "o1": ModelPricing("o1", "openai", 0.015, 0.06),
    "o1-mini": ModelPricing("o1-mini", "openai", 0.003, 0.012),
    "o1-preview": ModelPricing("o1-preview", "openai", 0.015, 0.06),
    "o3": ModelPricing("o3", "openai", 0.01, 0.04),
    "o3-mini": ModelPricing("o3-mini", "openai", 0.0011, 0.0044),
    "o4-mini": ModelPricing("o4-mini", "openai", 0.0011, 0.0044),

    # -----------------------------------------------------------------------
    # Anthropic
    # -----------------------------------------------------------------------
    "claude-opus-4": ModelPricing("claude-opus-4", "anthropic", 0.015, 0.075),
    "claude-sonnet-4": ModelPricing("claude-sonnet-4", "anthropic", 0.003, 0.015),
    "claude-3.5-sonnet": ModelPricing("claude-3.5-sonnet", "anthropic", 0.003, 0.015),
    "claude-3-5-sonnet-20241022": ModelPricing("claude-3-5-sonnet-20241022", "anthropic", 0.003, 0.015),
    "claude-3-opus": ModelPricing("claude-3-opus", "anthropic", 0.015, 0.075),
    "claude-3-opus-20240229": ModelPricing("claude-3-opus-20240229", "anthropic", 0.015, 0.075),
    "claude-3-sonnet": ModelPricing("claude-3-sonnet", "anthropic", 0.003, 0.015),
    "claude-3-sonnet-20240229": ModelPricing("claude-3-sonnet-20240229", "anthropic", 0.003, 0.015),
    "claude-3-haiku": ModelPricing("claude-3-haiku", "anthropic", 0.00025, 0.00125),
    "claude-3-haiku-20240307": ModelPricing("claude-3-haiku-20240307", "anthropic", 0.00025, 0.00125),
    "claude-3-5-haiku": ModelPricing("claude-3-5-haiku", "anthropic", 0.0008, 0.004),
    "claude-3-5-haiku-20241022": ModelPricing("claude-3-5-haiku-20241022", "anthropic", 0.0008, 0.004),
    "claude-2": ModelPricing("claude-2", "anthropic", 0.008, 0.024),
    "claude-2.1": ModelPricing("claude-2.1", "anthropic", 0.008, 0.024),

    # -----------------------------------------------------------------------
    # Google (Gemini)
    # -----------------------------------------------------------------------
    "gemini-2.0-flash": ModelPricing("gemini-2.0-flash", "google", 0.0001, 0.0004),
    "gemini-2.0-flash-lite": ModelPricing("gemini-2.0-flash-lite", "google", 0.000075, 0.0003),
    "gemini-1.5-pro": ModelPricing("gemini-1.5-pro", "google", 0.00125, 0.005),
    "gemini-1.5-flash": ModelPricing("gemini-1.5-flash", "google", 0.000075, 0.0003),
    "gemini-1.0-pro": ModelPricing("gemini-1.0-pro", "google", 0.0005, 0.0015),

    # -----------------------------------------------------------------------
    # Cohere
    # -----------------------------------------------------------------------
    "command-r-plus": ModelPricing("command-r-plus", "cohere", 0.003, 0.015),
    "command-r": ModelPricing("command-r", "cohere", 0.0005, 0.0015),
    "command-light": ModelPricing("command-light", "cohere", 0.0003, 0.0006),
    "command": ModelPricing("command", "cohere", 0.001, 0.002),

    # -----------------------------------------------------------------------
    # Mistral
    # -----------------------------------------------------------------------
    "mistral-large": ModelPricing("mistral-large", "mistral", 0.002, 0.006),
    "mistral-large-latest": ModelPricing("mistral-large-latest", "mistral", 0.002, 0.006),
    "mistral-medium": ModelPricing("mistral-medium", "mistral", 0.0027, 0.0081),
    "mistral-medium-latest": ModelPricing("mistral-medium-latest", "mistral", 0.0027, 0.0081),
    "mistral-small": ModelPricing("mistral-small", "mistral", 0.001, 0.003),
    "mistral-small-latest": ModelPricing("mistral-small-latest", "mistral", 0.001, 0.003),
    "open-mistral-nemo": ModelPricing("open-mistral-nemo", "mistral", 0.0003, 0.0003),
    "codestral": ModelPricing("codestral", "mistral", 0.001, 0.003),
    "open-mixtral-8x22b": ModelPricing("open-mixtral-8x22b", "mistral", 0.002, 0.006),
    "open-mixtral-8x7b": ModelPricing("open-mixtral-8x7b", "mistral", 0.0007, 0.0007),

    # -----------------------------------------------------------------------
    # Meta (Llama) — hosted pricing varies by provider; these are typical
    # rates on major hosting platforms (Together, Fireworks, Groq)
    # -----------------------------------------------------------------------
    "llama-3.3-70b": ModelPricing("llama-3.3-70b", "meta", 0.0009, 0.0009),
    "llama-3.1-405b": ModelPricing("llama-3.1-405b", "meta", 0.003, 0.003),
    "llama-3.1-70b": ModelPricing("llama-3.1-70b", "meta", 0.0009, 0.0009),
    "llama-3.1-8b": ModelPricing("llama-3.1-8b", "meta", 0.0002, 0.0002),
    "llama-3-70b": ModelPricing("llama-3-70b", "meta", 0.0009, 0.0009),
    "llama-3-8b": ModelPricing("llama-3-8b", "meta", 0.0002, 0.0002),
    "llama-4-scout": ModelPricing("llama-4-scout", "meta", 0.00015, 0.0006),
    "llama-4-maverick": ModelPricing("llama-4-maverick", "meta", 0.0003, 0.0012),

    # -----------------------------------------------------------------------
    # DeepSeek
    # -----------------------------------------------------------------------
    "deepseek-chat": ModelPricing("deepseek-chat", "deepseek", 0.00014, 0.00028),
    "deepseek-reasoner": ModelPricing("deepseek-reasoner", "deepseek", 0.00055, 0.00219),

    # -----------------------------------------------------------------------
    # Amazon (Bedrock hosted — Nova models)
    # -----------------------------------------------------------------------
    "amazon.nova-pro": ModelPricing("amazon.nova-pro", "amazon", 0.0008, 0.0032),
    "amazon.nova-lite": ModelPricing("amazon.nova-lite", "amazon", 0.00006, 0.00024),
    "amazon.nova-micro": ModelPricing("amazon.nova-micro", "amazon", 0.000035, 0.00014),
}


# Build a lookup of provider for each model
_MODEL_PROVIDER_MAP: dict[str, str] = {
    name: pricing.provider for name, pricing in DEFAULT_PRICING.items()
}


def get_provider(model: str) -> str | None:
    """Get the provider for a model name.

    Tries exact match, then substring match.

    Args:
        model: Model name

    Returns:
        Provider name or None
    """
    if model in _MODEL_PROVIDER_MAP:
        return _MODEL_PROVIDER_MAP[model]

    model_lower = model.lower()
    for name, provider in _MODEL_PROVIDER_MAP.items():
        if name.lower() in model_lower or model_lower in name.lower():
            return provider

    return None


def estimate_cost(
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    pricing: dict[str, ModelPricing] | None = None,
) -> float:
    """Estimate cost for a model call using the centralized pricing database.

    This is the recommended way for all adapters to calculate costs.

    Args:
        model: Model name (e.g. "gpt-4o", "claude-3-sonnet")
        prompt_tokens: Number of prompt/input tokens
        completion_tokens: Number of completion/output tokens
        pricing: Optional custom pricing dict (defaults to DEFAULT_PRICING)

    Returns:
        Estimated cost in USD
    """
    db = pricing or DEFAULT_PRICING
    return _lookup_and_calculate(db, model, prompt_tokens, completion_tokens)


def _lookup_and_calculate(
    db: dict[str, ModelPricing],
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Look up pricing and calculate cost."""
    # 1. Exact match
    if model in db:
        return db[model].calculate_cost(prompt_tokens, completion_tokens)

    # 2. Substring match (case-insensitive)
    model_lower = model.lower()
    for name, pricing in db.items():
        if name.lower() in model_lower or model_lower in name.lower():
            return pricing.calculate_cost(prompt_tokens, completion_tokens)

    # 3. Fallback: gpt-4o pricing (moderate, not the most expensive)
    fallback = db.get("gpt-4o", db.get("gpt-4"))
    if fallback:
        return fallback.calculate_cost(prompt_tokens, completion_tokens)

    # 4. Last resort
    return (prompt_tokens / 1000) * 0.005 + (completion_tokens / 1000) * 0.015


def list_providers() -> list[str]:
    """List all known providers."""
    return sorted({p.provider for p in DEFAULT_PRICING.values()})


def list_models(provider: str | None = None) -> list[str]:
    """List all known models, optionally filtered by provider.

    Args:
        provider: Filter by provider name (e.g. "openai", "anthropic")

    Returns:
        List of model names
    """
    if provider:
        return sorted(
            name for name, p in DEFAULT_PRICING.items() if p.provider == provider
        )
    return sorted(DEFAULT_PRICING.keys())


# ---------------------------------------------------------------------------
# Cost analysis data classes
# ---------------------------------------------------------------------------


@dataclass
class CostBreakdown:
    """Cost breakdown by category."""

    total_usd: float = 0.0
    llm_cost_usd: float = 0.0
    tool_cost_usd: float = 0.0
    by_model: dict[str, float] = field(default_factory=dict)
    by_provider: dict[str, float] = field(default_factory=dict)
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
    most_expensive_provider: str | None
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
            "most_expensive_provider": self.most_expensive_provider,
            "cost_breakdown": {
                "total_usd": self.cost_breakdown.total_usd,
                "llm_cost_usd": self.cost_breakdown.llm_cost_usd,
                "tool_cost_usd": self.cost_breakdown.tool_cost_usd,
                "by_model": self.cost_breakdown.by_model,
                "by_provider": self.cost_breakdown.by_provider,
            },
            "token_breakdown": {
                "total_tokens": self.token_breakdown.total_tokens,
                "prompt_tokens": self.token_breakdown.prompt_tokens,
                "completion_tokens": self.token_breakdown.completion_tokens,
                "by_model": self.token_breakdown.by_model,
            },
        }


# ---------------------------------------------------------------------------
# CostAnalyzer
# ---------------------------------------------------------------------------


class CostAnalyzer:
    """Analyzer for cost and token usage across multiple providers."""

    def __init__(
        self,
        pricing: dict[str, ModelPricing] | None = None,
    ) -> None:
        """Initialize the analyzer.

        Args:
            pricing: Custom pricing dictionary (merged with defaults)
        """
        self._pricing = dict(DEFAULT_PRICING)
        if pricing:
            self._pricing.update(pricing)

    def analyze_run(self, run: Run) -> CostReport:
        """Analyze costs for a single run."""
        return self.analyze_runs([run])

    def analyze_runs(self, runs: list[Run]) -> CostReport:
        """Analyze costs across multiple runs.

        Calculates costs using the centralized pricing database. If a step
        already has cost_usd set (e.g. from an adapter), that value is used.
        Otherwise, cost is estimated from token counts and model pricing.
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
                    prompt_tokens = 0
                    completion_tokens = 0

                    if step.token_usage:
                        prompt_tokens = step.token_usage.prompt_tokens
                        completion_tokens = step.token_usage.completion_tokens

                    # Use recorded cost or estimate
                    if step.cost_usd:
                        step_cost = step.cost_usd
                    else:
                        step_cost = estimate_cost(
                            step.model,
                            prompt_tokens,
                            completion_tokens,
                            self._pricing,
                        )

                    # Model breakdown
                    cost_breakdown.llm_cost_usd += step_cost
                    cost_breakdown.by_model[step.model] = (
                        cost_breakdown.by_model.get(step.model, 0) + step_cost
                    )

                    # Provider breakdown
                    provider = (
                        step.provider
                        or get_provider(step.model)
                        or "unknown"
                    )
                    cost_breakdown.by_provider[provider] = (
                        cost_breakdown.by_provider.get(provider, 0) + step_cost
                    )

                    # Token breakdown
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

        # Most expensive model
        most_expensive_model = None
        if cost_breakdown.by_model:
            most_expensive_model = max(
                cost_breakdown.by_model,
                key=lambda m: cost_breakdown.by_model[m],
            )

        # Most expensive provider
        most_expensive_provider = None
        if cost_breakdown.by_provider:
            most_expensive_provider = max(
                cost_breakdown.by_provider,
                key=lambda p: cost_breakdown.by_provider[p],
            )

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
            most_expensive_provider=most_expensive_provider,
            most_expensive_steps=expensive_steps[:10],
        )

    def add_pricing(self, pricing: ModelPricing) -> None:
        """Add custom pricing for a model."""
        self._pricing[pricing.model] = pricing

    def get_pricing(self, model: str) -> ModelPricing | None:
        """Get pricing for a model."""
        return self._pricing.get(model)
