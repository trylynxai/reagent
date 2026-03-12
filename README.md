# ReAgent

**AI Agent Debugging & Observability Platform**

ReAgent captures, analyzes, and replays AI agent executions. Debug failures, understand costs, and improve reliability of your LLM-powered agents.

## Features

- **Full Execution Recording** - Capture every LLM call, tool execution, and agent decision
- **Failure Analysis** - Track errors with full tracebacks and failure categorization
- **Cost & Token Analytics** - Monitor spending across models and runs
- **Framework Adapters** - Native support for LangChain, OpenAI, and more
- **Interactive CLI** - Inspect, search, and analyze runs from the terminal
- **HTML Reports** - Export interactive reports for sharing and debugging
- **Deterministic Replay** - Reproduce agent behavior for testing
- **PII Redaction** - Automatically mask sensitive data

---

## Installation

```bash
# Install from source
pip install -e .

# With development dependencies
pip install -e ".[dev]"
```

---

## Quick Start

### Basic Usage

```python
from reagent import ReAgent
from reagent.schema.run import RunConfig

# Initialize client
client = ReAgent()

# Record an agent run
with client.trace(RunConfig(name="my-agent-run", project="my-project")) as ctx:
    # Record an LLM call
    ctx.record_llm_call(
        model="gpt-4",
        prompt="What is the capital of France?",
        response="The capital of France is Paris.",
        prompt_tokens=10,
        completion_tokens=8,
        cost_usd=0.001,
    )

    # Record a tool call
    ctx.record_tool_call(
        tool_name="web_search",
        kwargs={"query": "Paris population"},
        result={"population": "2.1 million"},
        duration_ms=500,
    )

# List recorded runs
runs = client.list_runs(project="my-project")
for run in runs:
    print(f"{run.run_id}: {run.name} - {run.status}")
```

### Recording Errors

```python
with client.trace(RunConfig(name="error-demo")) as ctx:
    ctx.record_llm_call(
        model="gpt-4",
        prompt="Process this data",
        response="I'll use the database tool...",
        prompt_tokens=10,
        completion_tokens=15,
    )

    # Record a failed tool call
    ctx.record_tool_call(
        tool_name="database_query",
        kwargs={"query": "SELECT * FROM users"},
        error="Connection refused: localhost:5432",
        error_type="ConnectionError",
    )

    # Record the error with full traceback
    ctx.record_error(
        error_message="Database connection failed",
        error_type="ConnectionError",
        error_traceback="Traceback (most recent call last):\n  ...",
    )

    # Set failure category for filtering
    ctx._metadata.failure_category = "tool_error"

    raise ConnectionError("Database unavailable")
```

---

## Framework Integrations

### LangChain

```python
from langchain_openai import ChatOpenAI
from langchain.agents import create_react_agent, AgentExecutor
from reagent import ReAgent
from reagent.adapters.langchain import ReAgentCallbackHandler

# Initialize ReAgent
client = ReAgent()

# Create callback handler
handler = ReAgentCallbackHandler(
    client=client,
    project="langchain-agent",
    tags=["production", "customer-support"],
)

# Use with LangChain
llm = ChatOpenAI(model="gpt-4", callbacks=[handler])

# Or attach to an agent executor
agent_executor = AgentExecutor(agent=agent, tools=tools, callbacks=[handler])
result = agent_executor.invoke({"input": "What's the weather in NYC?"})

# The run is automatically recorded with all LLM calls, tool uses, and errors
```

### OpenAI SDK

```python
from openai import OpenAI
from reagent import ReAgent
from reagent.adapters.openai import OpenAIAdapter
from reagent.schema.run import RunConfig

# Initialize ReAgent
reagent_client = ReAgent()

# Create a trace context and instrument the OpenAI client
with reagent_client.trace(RunConfig(name="openai-app", project="my-project")) as ctx:
    adapter = OpenAIAdapter(reagent_client)
    openai_client = adapter.reagent_openai_client(OpenAI(), context=ctx)

    # Use as normal - all calls are automatically recorded
    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "Hello!"}],
    )

    # Errors are captured with full context
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": "x" * 1000000}],  # Too long
        )
    except Exception as e:
        # Error is already recorded in ReAgent
        pass
```

Or use the decorator approach:

```python
from reagent.adapters.openai import reagent_openai_call

with reagent_client.trace(RunConfig(name="openai-app")) as ctx:
    @reagent_openai_call(ctx)
    def get_client():
        return OpenAI()

    openai_client = get_client()  # Instrumented with ReAgent
    response = openai_client.chat.completions.create(...)
```

### Manual Integration

For custom agents or frameworks without adapters:

```python
from reagent import ReAgent
from reagent.schema.run import RunConfig
import traceback

client = ReAgent()

def run_my_agent(user_input: str):
    with client.trace(RunConfig(
        name="custom-agent",
        project="my-app",
        input={"user_input": user_input},
    )) as ctx:
        try:
            # Your agent logic here
            llm_response = call_llm(user_input)
            ctx.record_llm_call(
                model="gpt-4",
                prompt=user_input,
                response=llm_response,
                prompt_tokens=len(user_input.split()),
                completion_tokens=len(llm_response.split()),
            )

            # Tool execution
            if needs_tool(llm_response):
                tool_result = execute_tool(llm_response)
                ctx.record_tool_call(
                    tool_name="my_tool",
                    kwargs={"input": llm_response},
                    result=tool_result,
                )

            ctx.set_output({"result": llm_response})
            return llm_response

        except Exception as e:
            # Record the error
            ctx.record_error(
                error_message=str(e),
                error_type=type(e).__name__,
                error_traceback=traceback.format_exc(),
            )
            ctx._metadata.failure_category = categorize_error(e)
            raise
```

---

## CLI Usage

### List and Inspect Runs

```bash
# List all runs
reagent list

# List runs for a specific project
reagent list --project my-project

# List only failed runs
reagent list --status failed

# Inspect a specific run
reagent inspect <run_id>

# Search runs
reagent search "database error"
```

### Failure Analysis

```bash
# List all failures
reagent failures list

# Filter by project and category
reagent failures list --project my-project --category tool_timeout

# Show failures from the last 24 hours
reagent failures list --since 24h

# Inspect a failure with full traceback
reagent failures inspect <run_id> --traceback

# View failure statistics
reagent failures stats --project my-project
```

### Export Reports

```bash
# Export to JSON
reagent export <run_id> -f json -o trace.json

# Export to Markdown
reagent export <run_id> -f markdown -o report.md

# Export to interactive HTML
reagent export <run_id> -f html -o report.html

# Open in browser
open report.html  # macOS
xdg-open report.html  # Linux
```

### Other Commands

```bash
# View usage statistics
reagent stats --project my-project

# Compare two runs
reagent diff <run_id_1> <run_id_2>

# Replay a run (for testing)
reagent replay <run_id>

# Delete a run
reagent delete <run_id>
```

---

## Try the Failure Demo

Generate sample failures to explore ReAgent's debugging capabilities:

```bash
# Generate sample failed runs
python examples/failure_demo.py

# View the failures
reagent failures list --project failure-demo

# Inspect a specific failure
reagent failures inspect <run_id> --traceback

# View failure statistics
reagent failures stats --project failure-demo

# Export to interactive HTML report
reagent export <run_id> -f html -o report.html
```

The demo generates these failure types:
- **Tool Timeout** - Tool execution taking too long
- **Rate Limit** - API rate limit exceeded
- **Context Overflow** - Token limit exceeded
- **Tool Error** - Tool execution exception
- **Validation Error** - Invalid arguments
- **Chain Error** - Error propagating through a chain
- **Auth Error** - Authentication failure

---

## Configuration

### Storage Options

```python
# SQLite (default) - best for most use cases
client = ReAgent(storage_path="./traces")

# In-memory - for testing
from reagent.storage.memory import MemoryStorage
client = ReAgent(storage=MemoryStorage())

# JSONL files - human-readable
from reagent.storage.jsonl import JSONLStorage
client = ReAgent(storage=JSONLStorage(base_path="./traces"))
```

### Configuration File

Create `reagent.yaml` or `reagent.toml`:

```yaml
# reagent.yaml
project: my-default-project

storage:
  type: sqlite
  path: ~/.reagent/traces.db

redaction:
  enabled: true
  mode: mask  # or 'hash', 'remove'

buffer:
  size: 100
  flush_interval_ms: 5000
```

### Environment Variables

```bash
export REAGENT_PROJECT=my-project
export REAGENT_STORAGE_PATH=~/.reagent/traces
export REAGENT_REDACTION_ENABLED=true
```

---

## Advanced Features

### Step Nesting

Track hierarchical execution with parent-child relationships:

```python
with client.trace(RunConfig(name="nested-example")) as ctx:
    # Start a chain
    chain = ctx.start_chain(
        chain_name="ResearchChain",
        chain_type="sequential",
        input={"topic": "AI Safety"},
    )

    # Nest steps under the chain
    with ctx.nest(chain.step_id):
        ctx.record_llm_call(model="gpt-4", prompt="...", response="...")
        ctx.record_tool_call(tool_name="search", kwargs={}, result={})

    # End the chain
    ctx.end_chain(chain, output={"result": "..."})
```

### PII Redaction

```python
from reagent import ReAgent
from reagent.core.config import Config

config = Config(
    redaction={
        "enabled": True,
        "mode": "mask",  # Replace with [REDACTED]
        "patterns": ["email", "phone", "ssn", "api_key"],
    }
)

client = ReAgent(config=config)
```

### Custom Metadata

```python
with client.trace(RunConfig(name="with-metadata")) as ctx:
    ctx.set_metadata("user_id", "user_123")
    ctx.set_metadata("session_id", "sess_456")
    ctx.add_tag("production")
    ctx.add_tag("high-priority")
    ctx.set_framework("custom-agent", "1.0.0")

    # ... agent execution
```

---

## Project Structure

```
src/reagent/
├── client/           # Main SDK client
│   ├── reagent.py    # ReAgent class
│   └── context.py    # RunContext for recording
├── schema/           # Data models
│   ├── run.py        # Run, RunMetadata, RunConfig
│   └── steps.py      # LLMCallStep, ToolCallStep, ErrorStep
├── storage/          # Storage backends
│   ├── sqlite.py     # SQLite with FTS
│   ├── jsonl.py      # JSONL files
│   └── memory.py     # In-memory
├── adapters/         # Framework integrations
│   ├── langchain.py  # LangChain callback handler
│   └── openai.py     # OpenAI client wrapper
├── cli/              # CLI commands
│   ├── commands/     # Individual commands
│   └── templates/    # HTML templates
├── analysis/         # Analytics & search
├── redaction/        # PII redaction
└── replay/           # Deterministic replay
```

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Run with coverage
pytest tests/ --cov=reagent

# Type checking
mypy src/reagent

# Linting
ruff check src/

# Format code
ruff format src/
```

---

## License

MIT License - see LICENSE file for details.

---

## Contributing

Contributions welcome! See [DEVELOPMENT.md](DEVELOPMENT.md) for implementation status and guidelines.
