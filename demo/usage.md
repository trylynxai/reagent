# ReAgent Demo Guide

End-to-end walkthrough: generate traces, explore with CLI, run the agent interactively.

## Prerequisites

- Python 3.10+
- ReAgent installed (or run from source with `src/` on path)
- `pip install google-generativeai` + `GEMINI_API_KEY` set (for real mode)
- Get a free API key at: https://aistudio.google.com/apikey

## Quick Start

```bash
# 1. Set your Gemini API key
export GEMINI_API_KEY=your-key-here

# 2. Run the agent
python demo/agent.py "What is the square root of 144?"
python demo/agent.py "What's the weather in Tokyo?"
python demo/agent.py "Tell me about Python"

# 3. Generate all demo traces (11 scenarios, no API key needed)
python demo/scenarios.py

# 4. Explore traces
reagent list --project demo
```

## Running the Agent

### Real Mode (default — needs Gemini API key)

```bash
export GEMINI_API_KEY=your-key-here

# Math
python demo/agent.py "What is 2+2?"
python demo/agent.py "Calculate the square root of 256 plus 3 cubed"

# Weather
python demo/agent.py "What's the weather like in San Francisco?"

# Research
python demo/agent.py "Tell me about artificial intelligence"

# File reading
python demo/agent.py "Read the file pyproject.toml"

# Use a different model
python demo/agent.py "Explain quantum computing" --model gemini-2.0-flash
```

### Mock Mode (no API key, scripted responses)

```bash
python demo/agent.py "What is 2+2?" --mock
python demo/agent.py "What is the weather in Paris?" --mock
```

### Custom Project Name

```bash
python demo/agent.py "My question" --project my-experiment
reagent list --project my-experiment
```

## Feature Walkthrough

### 1. Listing Runs

```bash
reagent list --project demo
reagent list --project demo --status failed
reagent list --project demo --sort-by cost --limit 5
```

### 2. Inspecting a Run

```bash
# Get the run ID from `reagent list`, then:
reagent inspect <run_id>

# Show all steps with details
reagent inspect <run_id> --steps
```

### 3. Searching

```bash
reagent search "status:failed" --project demo
reagent search "model:gpt-4o AND cost>0.01" --project demo
reagent search "tag:timeout" --project demo
reagent search "web_search" --project demo
```

### 4. Failure Analysis

```bash
# List all failed runs
reagent failures list --project demo

# Failure statistics
reagent failures stats --project demo

# Inspect a specific failure with traceback
reagent failures inspect <run_id> --traceback
```

Scenarios 3-8 generate different failure types: timeout, rate limit, connection error,
validation error, reasoning loop, and authentication error.

### 5. Comparing Runs

```bash
# Compare the two successful runs (scenarios 1 and 2)
reagent diff <run_id_1> <run_id_2>
```

This shows differences in model, cost, tokens, steps, and duration between runs.

### 6. Replay

```bash
# Replay a run headlessly (non-interactive)
reagent replay <run_id> --headless

# Interactive replay (step through each event)
reagent replay <run_id>
```

### 7. Export

```bash
# Export to different formats
reagent export <run_id> -f json
reagent export <run_id> -f html -o report.html
reagent export <run_id> -f markdown
reagent export <run_id> -f csv
```

### 8. Statistics

```bash
reagent stats --project demo
```

Shows aggregate statistics: total runs, success/failure rates, cost breakdown, model usage.

### 9. PII Redaction

Scenario 9 includes PII (email, phone, API key) in prompts and responses.
When you inspect this run, observe how ReAgent's redaction engine handles sensitive data:

```bash
# Find the PII scenario run
reagent list --project demo --tag pii

# Inspect it — look for [REDACTED] markers
reagent inspect <pii_run_id>
```

The prompts contain `john.doe@example.com`, `555-123-4567`, and `sk-abc123secretkey456`.

### 10. Budget Alerts

When running `scenarios.py`, scenario 10 (expensive run) triggers a `CostThresholdRule`
set at $0.05. You'll see alert output in the console:

```
ALERT [warning] high_cost_alert: Run cost $0.15 exceeds threshold $0.05
```

Alerts are configured via `AlertEngine` with `CostThresholdRule` and `CallbackDelivery`.

## Code Overview

| File | Lines | Purpose |
|------|-------|---------|
| `demo/tools.py` | ~100 | Four tools: web_search, calculator (real eval), weather, file_reader (reads real files) |
| `demo/agent.py` | ~250 | `ResearchAgent` with Gemini LLM, tool loop, full ReAgent instrumentation |
| `demo/scenarios.py` | ~400 | Seeds 11 runs: successes, all failure types, PII, alerts, nesting |
| `demo/usage.md` | — | This guide |

### Key Patterns

**Recording a trace:**
```python
from reagent.client.reagent import ReAgent
from reagent.schema.run import RunConfig

client = ReAgent(storage_path=".reagent/demo_traces")

with client.trace(RunConfig(name="my-run", project="demo")) as ctx:
    ctx.record_llm_call(model="gemini-2.0-flash", prompt="...", response="...")
    ctx.record_tool_call(tool_name="search", kwargs={"q": "..."}, result={...})
    ctx.record_agent_finish(final_answer="...")
```

**Failure injection:**
```python
try:
    with client.trace(config) as ctx:
        ctx.record_error(error_message="...", error_type="TimeoutError")
        ctx._metadata.failure_category = "tool_timeout"
        raise TimeoutError("...")
except TimeoutError:
    pass
```

**Alert setup:**
```python
from reagent.alerts.engine import AlertEngine
from reagent.alerts.rules import CostThresholdRule
from reagent.alerts.delivery import CallbackDelivery

engine = AlertEngine(
    rules=[CostThresholdRule(name="cost", max_cost_usd=0.05)],
    delivery_backends=[CallbackDelivery(callback=my_handler)],
)
client.set_alert_engine(engine)
```
