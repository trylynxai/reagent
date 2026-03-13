"""Tests for multi-provider pricing and cost analysis."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from reagent.analysis.cost import (
    CostAnalyzer,
    CostBreakdown,
    CostReport,
    DEFAULT_PRICING,
    ModelPricing,
    TokenBreakdown,
    estimate_cost,
    get_provider,
    list_models,
    list_providers,
)
from reagent.schema.run import Run, RunConfig, RunMetadata, CostSummary
from reagent.schema.steps import LLMCallStep, ToolCallStep, TokenUsage, ToolInput, ToolOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(steps=None, name="test-run"):
    """Create a Run with given steps."""
    run_id = uuid4()
    metadata = RunMetadata(
        run_id=run_id,
        name=name,
        start_time=datetime.utcnow(),
    )
    return Run(metadata=metadata, steps=steps or [])


def _make_llm_step(
    model="gpt-4o",
    provider=None,
    prompt_tokens=100,
    completion_tokens=50,
    cost_usd=None,
):
    """Create an LLMCallStep."""
    token_usage = None
    if prompt_tokens or completion_tokens:
        token_usage = TokenUsage.from_counts(
            prompt=prompt_tokens or 0,
            completion=completion_tokens or 0,
        )
    return LLMCallStep(
        run_id=uuid4(),
        step_number=0,
        timestamp_start=datetime.utcnow(),
        timestamp_end=datetime.utcnow(),
        model=model,
        provider=provider,
        token_usage=token_usage,
        cost_usd=cost_usd,
    )


def _make_tool_step(tool_name="search", cost_usd=None):
    """Create a ToolCallStep."""
    return ToolCallStep(
        run_id=uuid4(),
        step_number=0,
        timestamp_start=datetime.utcnow(),
        timestamp_end=datetime.utcnow(),
        tool_name=tool_name,
        input=ToolInput(args=(), kwargs={}),
        output=ToolOutput(result="ok"),
        success=True,
        cost_usd=cost_usd,
    )


# ---------------------------------------------------------------------------
# Pricing Database
# ---------------------------------------------------------------------------


class TestPricingDatabase:
    def test_has_openai_models(self):
        assert "gpt-4o" in DEFAULT_PRICING
        assert "gpt-4" in DEFAULT_PRICING
        assert "gpt-4o-mini" in DEFAULT_PRICING
        assert "o1" in DEFAULT_PRICING

    def test_has_anthropic_models(self):
        assert "claude-opus-4" in DEFAULT_PRICING
        assert "claude-sonnet-4" in DEFAULT_PRICING
        assert "claude-3-haiku" in DEFAULT_PRICING

    def test_has_google_models(self):
        assert "gemini-2.0-flash" in DEFAULT_PRICING
        assert "gemini-1.5-pro" in DEFAULT_PRICING

    def test_has_cohere_models(self):
        assert "command-r-plus" in DEFAULT_PRICING
        assert "command-r" in DEFAULT_PRICING

    def test_has_mistral_models(self):
        assert "mistral-large" in DEFAULT_PRICING
        assert "mistral-small" in DEFAULT_PRICING

    def test_has_meta_models(self):
        assert "llama-3.1-70b" in DEFAULT_PRICING
        assert "llama-4-scout" in DEFAULT_PRICING

    def test_has_deepseek_models(self):
        assert "deepseek-chat" in DEFAULT_PRICING
        assert "deepseek-reasoner" in DEFAULT_PRICING

    def test_has_amazon_models(self):
        assert "amazon.nova-pro" in DEFAULT_PRICING
        assert "amazon.nova-lite" in DEFAULT_PRICING

    def test_model_pricing_calculate(self):
        p = ModelPricing("test", "provider", 0.01, 0.02)
        # 1000 prompt + 500 completion = 0.01 + 0.01 = 0.02
        cost = p.calculate_cost(1000, 500)
        assert abs(cost - 0.02) < 1e-10

    def test_all_models_have_provider(self):
        for name, pricing in DEFAULT_PRICING.items():
            assert pricing.provider, f"{name} has no provider"

    def test_all_models_have_positive_pricing(self):
        for name, pricing in DEFAULT_PRICING.items():
            assert pricing.prompt_cost_per_1k >= 0, f"{name} prompt cost < 0"
            assert pricing.completion_cost_per_1k >= 0, f"{name} completion cost < 0"


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------


class TestEstimateCost:
    def test_exact_match(self):
        cost = estimate_cost("gpt-4o", 1000, 1000)
        expected = DEFAULT_PRICING["gpt-4o"].calculate_cost(1000, 1000)
        assert cost == expected

    def test_substring_match(self):
        """A versioned model name should match via substring."""
        cost = estimate_cost("gpt-4o-2024-11-20", 1000, 0)
        # Should find gpt-4o-2024-11-20 exact match
        assert cost > 0

    def test_unknown_model_falls_back(self):
        """Unknown model should still return a cost (fallback)."""
        cost = estimate_cost("totally-unknown-model-xyz", 1000, 1000)
        assert cost > 0

    def test_zero_tokens(self):
        cost = estimate_cost("gpt-4o", 0, 0)
        assert cost == 0.0

    def test_custom_pricing(self):
        custom = {"my-model": ModelPricing("my-model", "custom", 0.1, 0.2)}
        cost = estimate_cost("my-model", 1000, 1000, pricing=custom)
        assert abs(cost - 0.3) < 1e-10

    def test_anthropic_model(self):
        cost = estimate_cost("claude-3-haiku", 1000, 1000)
        expected = DEFAULT_PRICING["claude-3-haiku"].calculate_cost(1000, 1000)
        assert cost == expected

    def test_gemini_model(self):
        cost = estimate_cost("gemini-2.0-flash", 1000, 1000)
        expected = DEFAULT_PRICING["gemini-2.0-flash"].calculate_cost(1000, 1000)
        assert cost == expected


# ---------------------------------------------------------------------------
# get_provider
# ---------------------------------------------------------------------------


class TestGetProvider:
    def test_exact_match(self):
        assert get_provider("gpt-4o") == "openai"
        assert get_provider("claude-3-haiku") == "anthropic"
        assert get_provider("gemini-1.5-pro") == "google"
        assert get_provider("command-r") == "cohere"
        assert get_provider("mistral-large") == "mistral"
        assert get_provider("llama-3.1-70b") == "meta"
        assert get_provider("deepseek-chat") == "deepseek"
        assert get_provider("amazon.nova-pro") == "amazon"

    def test_substring_match(self):
        # A versioned variant should still resolve
        result = get_provider("gpt-4o-some-variant")
        assert result == "openai"

    def test_unknown_model(self):
        assert get_provider("totally-unknown-xyz") is None


# ---------------------------------------------------------------------------
# list_providers / list_models
# ---------------------------------------------------------------------------


class TestListFunctions:
    def test_list_providers(self):
        providers = list_providers()
        assert "openai" in providers
        assert "anthropic" in providers
        assert "google" in providers
        assert "meta" in providers
        assert isinstance(providers, list)
        assert providers == sorted(providers)

    def test_list_models_all(self):
        models = list_models()
        assert "gpt-4o" in models
        assert "claude-3-haiku" in models
        assert len(models) == len(DEFAULT_PRICING)

    def test_list_models_by_provider(self):
        openai_models = list_models("openai")
        assert all("gpt" in m or "o1" in m or "o3" in m or "o4" in m for m in openai_models)
        anthropic_models = list_models("anthropic")
        assert all("claude" in m for m in anthropic_models)

    def test_list_models_unknown_provider(self):
        assert list_models("nonexistent") == []


# ---------------------------------------------------------------------------
# CostAnalyzer
# ---------------------------------------------------------------------------


class TestCostAnalyzer:
    def test_analyze_empty_run(self):
        analyzer = CostAnalyzer()
        run = _make_run()
        report = analyzer.analyze_run(run)
        assert report.total_cost_usd == 0.0
        assert report.total_tokens == 0
        assert report.run_count == 1

    def test_analyze_single_llm_step(self):
        analyzer = CostAnalyzer()
        step = _make_llm_step(model="gpt-4o", prompt_tokens=1000, completion_tokens=500)
        run = _make_run(steps=[step])
        report = analyzer.analyze_run(run)

        expected = DEFAULT_PRICING["gpt-4o"].calculate_cost(1000, 500)
        assert abs(report.total_cost_usd - expected) < 1e-10
        assert report.total_tokens == 1500
        assert report.most_expensive_model == "gpt-4o"

    def test_analyze_uses_recorded_cost(self):
        """If a step has cost_usd already set, use it instead of estimating."""
        analyzer = CostAnalyzer()
        step = _make_llm_step(
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            cost_usd=0.42,
        )
        run = _make_run(steps=[step])
        report = analyzer.analyze_run(run)
        assert abs(report.total_cost_usd - 0.42) < 1e-10

    def test_provider_breakdown(self):
        analyzer = CostAnalyzer()
        steps = [
            _make_llm_step(model="gpt-4o", provider="openai", prompt_tokens=1000, completion_tokens=500),
            _make_llm_step(model="claude-3-haiku", provider="anthropic", prompt_tokens=1000, completion_tokens=500),
        ]
        run = _make_run(steps=steps)
        report = analyzer.analyze_run(run)

        assert "openai" in report.cost_breakdown.by_provider
        assert "anthropic" in report.cost_breakdown.by_provider
        assert report.most_expensive_provider is not None

    def test_provider_inferred_from_model(self):
        """Provider should be inferred via get_provider() when not set on step."""
        analyzer = CostAnalyzer()
        step = _make_llm_step(model="gpt-4o", provider=None, prompt_tokens=1000, completion_tokens=500)
        run = _make_run(steps=[step])
        report = analyzer.analyze_run(run)

        assert "openai" in report.cost_breakdown.by_provider

    def test_tool_cost_tracked(self):
        analyzer = CostAnalyzer()
        step = _make_tool_step(cost_usd=0.05)
        run = _make_run(steps=[step])
        report = analyzer.analyze_run(run)

        assert abs(report.cost_breakdown.tool_cost_usd - 0.05) < 1e-10
        assert abs(report.total_cost_usd - 0.05) < 1e-10

    def test_multiple_runs(self):
        analyzer = CostAnalyzer()
        run1 = _make_run(steps=[_make_llm_step(model="gpt-4o", prompt_tokens=1000, completion_tokens=500)])
        run2 = _make_run(steps=[_make_llm_step(model="gpt-4o", prompt_tokens=2000, completion_tokens=1000)])
        report = analyzer.analyze_runs([run1, run2])

        assert report.run_count == 2
        assert report.total_tokens == 4500
        assert report.min_cost <= report.max_cost
        assert abs(report.avg_cost_per_run - report.total_cost_usd / 2) < 1e-10

    def test_custom_pricing(self):
        custom = ModelPricing("custom-model", "custom-provider", 0.1, 0.2)
        analyzer = CostAnalyzer()
        analyzer.add_pricing(custom)

        step = _make_llm_step(model="custom-model", prompt_tokens=1000, completion_tokens=1000)
        run = _make_run(steps=[step])
        report = analyzer.analyze_run(run)

        assert abs(report.total_cost_usd - 0.3) < 1e-10

    def test_get_pricing(self):
        analyzer = CostAnalyzer()
        p = analyzer.get_pricing("gpt-4o")
        assert p is not None
        assert p.provider == "openai"

    def test_most_expensive_steps_sorted(self):
        analyzer = CostAnalyzer()
        steps = [
            _make_llm_step(model="gpt-4o", prompt_tokens=100, completion_tokens=50),
            _make_llm_step(model="gpt-4", prompt_tokens=1000, completion_tokens=500),
        ]
        run = _make_run(steps=steps)
        report = analyzer.analyze_run(run)

        assert len(report.most_expensive_steps) == 2
        # Sorted descending by cost
        assert report.most_expensive_steps[0]["cost_usd"] >= report.most_expensive_steps[1]["cost_usd"]


# ---------------------------------------------------------------------------
# CostReport
# ---------------------------------------------------------------------------


class TestCostReport:
    def test_to_dict(self):
        report = CostReport(
            total_cost_usd=1.5,
            total_tokens=5000,
            run_count=2,
            cost_breakdown=CostBreakdown(
                total_usd=1.5,
                llm_cost_usd=1.4,
                tool_cost_usd=0.1,
                by_model={"gpt-4o": 1.0, "claude-3-haiku": 0.5},
                by_provider={"openai": 1.0, "anthropic": 0.5},
            ),
            token_breakdown=TokenBreakdown(
                total_tokens=5000,
                prompt_tokens=3000,
                completion_tokens=2000,
            ),
            avg_cost_per_run=0.75,
            avg_tokens_per_run=2500,
            min_cost=0.5,
            max_cost=1.0,
            most_expensive_model="gpt-4o",
            most_expensive_provider="openai",
            most_expensive_steps=[],
        )
        d = report.to_dict()
        assert d["total_cost_usd"] == 1.5
        assert d["total_tokens"] == 5000
        assert d["run_count"] == 2
        assert d["most_expensive_provider"] == "openai"
        assert d["cost_breakdown"]["by_provider"]["openai"] == 1.0
        assert d["token_breakdown"]["prompt_tokens"] == 3000


# ---------------------------------------------------------------------------
# CostSummary by_provider field
# ---------------------------------------------------------------------------


class TestCostSummaryByProvider:
    def test_by_provider_default_empty(self):
        cs = CostSummary()
        assert cs.by_provider == {}

    def test_by_provider_tracking(self):
        cs = CostSummary()
        cs.by_provider["openai"] = 0.5
        cs.by_provider["anthropic"] = 0.3
        assert cs.by_provider["openai"] == 0.5
        assert cs.by_provider["anthropic"] == 0.3
