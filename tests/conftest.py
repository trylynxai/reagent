"""Pytest configuration and shared fixtures."""

import pytest
from datetime import datetime
from uuid import uuid4

from reagent.client.reagent import ReAgent
from reagent.core.config import Config
from reagent.core.constants import Status, StorageType
from reagent.schema.run import Run, RunConfig, RunMetadata, CostSummary, TokenSummary, StepSummary
from reagent.schema.steps import LLMCallStep, ToolCallStep, TokenUsage, ToolInput, ToolOutput
from reagent.storage.memory import MemoryStorage


@pytest.fixture
def memory_storage() -> MemoryStorage:
    """Create an in-memory storage backend."""
    return MemoryStorage()


@pytest.fixture
def config() -> Config:
    """Create a test configuration."""
    return Config(
        storage={"type": "memory"},
        redaction={"enabled": False},
    )


@pytest.fixture
def reagent_client(memory_storage: MemoryStorage) -> ReAgent:
    """Create a ReAgent client with in-memory storage."""
    return ReAgent(
        storage=memory_storage,
        config=Config(
            storage={"type": "memory"},
            redaction={"enabled": False},
        ),
    )


@pytest.fixture
def sample_run_id():
    """Generate a sample run ID."""
    return uuid4()


@pytest.fixture
def sample_metadata(sample_run_id) -> RunMetadata:
    """Create sample run metadata."""
    return RunMetadata(
        run_id=sample_run_id,
        name="test-run",
        project="test-project",
        tags=["test"],
        start_time=datetime.utcnow(),
        status=Status.RUNNING,
        model="gpt-4",
        cost=CostSummary(total_usd=0.05),
        tokens=TokenSummary(total_tokens=1000, prompt_tokens=800, completion_tokens=200),
        steps=StepSummary(total=3, llm_calls=2, tool_calls=1),
    )


@pytest.fixture
def sample_llm_step(sample_run_id) -> LLMCallStep:
    """Create a sample LLM call step."""
    return LLMCallStep(
        run_id=sample_run_id,
        step_number=0,
        timestamp_start=datetime.utcnow(),
        model="gpt-4",
        provider="openai",
        prompt="What is 2+2?",
        response="4",
        token_usage=TokenUsage(prompt_tokens=10, completion_tokens=1, total_tokens=11),
        cost_usd=0.001,
    )


@pytest.fixture
def sample_tool_step(sample_run_id) -> ToolCallStep:
    """Create a sample tool call step."""
    return ToolCallStep(
        run_id=sample_run_id,
        step_number=1,
        timestamp_start=datetime.utcnow(),
        tool_name="calculator",
        input=ToolInput(args=(), kwargs={"expression": "2+2"}),
        output=ToolOutput(result=4),
        success=True,
    )


@pytest.fixture
def sample_run(sample_metadata, sample_llm_step, sample_tool_step) -> Run:
    """Create a sample run with steps."""
    sample_metadata.complete(output={"result": "success"})
    return Run(
        metadata=sample_metadata,
        steps=[sample_llm_step, sample_tool_step],
    )
