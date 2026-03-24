# ReAgent

**AI Agent Debugging & Observability Platform**

ReAgent captures, analyzes, and replays AI agent executions. Debug failures, understand costs, and improve reliability of your LLM-powered agents — locally or in production.

## Features

- **Full Execution Recording** - Capture every LLM call, tool execution, and agent decision
- **Local & Remote Modes** - Write traces to disk for dev, or send to a self-hosted server for production
- **Self-Hosted Server** - Deploy a single-binary backend with Docker; no external dependencies
- **Failure Analysis** - Track errors with full tracebacks and failure categorization
- **Cost & Token Analytics** - Monitor spending across models and runs
- **Framework Adapters** - Native support for LangChain, OpenAI, OpenAI Agents, CrewAI, and LlamaIndex
- **Web Dashboard** - Interactive UI with trace visualization, node graph inspection, and step-through replay
- **Interactive CLI** - Inspect, search, and analyze runs from the terminal
- **HTML Reports** - Export interactive reports for sharing and debugging
- **Deterministic Replay** - Reproduce agent behavior for testing
- **PII Redaction** - Automatically mask sensitive data

---

## Installation

```bash
# Core SDK
pip install -e .

# With server (for self-hosting)
pip install -e ".[server]"

# With all framework adapters
pip install -e ".[all]"

# With development dependencies
pip install -e ".[dev]"
```

---

## Quick Start

### Local Mode (default)

Traces are written to SQLite on disk. No server needed.

```python
from reagent import ReAgent
from reagent.schema.run import RunConfig

client = ReAgent()

with client.trace(RunConfig(name="my-agent-run", project="my-project")) as ctx:
    ctx.record_llm_call(
        model="gpt-4",
        prompt="What is the capital of France?",
        response="The capital of France is Paris.",
        prompt_tokens=10,
        completion_tokens=8,
        cost_usd=0.001,
    )

    ctx.record_tool_call(
        tool_name="web_search",
        kwargs={"query": "Paris population"},
        result={"population": "2.1 million"},
        duration_ms=500,
    )

runs = client.list_runs(project="my-project")
for run in runs:
    print(f"{run.run_id}: {run.name} - {run.status}")
```

### Remote Mode (production)

Point the SDK at a self-hosted ReAgent server. The recording API is identical — only the config changes.

```python
from reagent import ReAgent
from reagent.schema.run import RunConfig

# One-line change: add server_url
client = ReAgent(server_url="https://reagent.example.com", api_key="rk-abc123")

with client.trace(RunConfig(name="my-agent-run", project="prod")) as ctx:
    ctx.record_llm_call(
        model="gpt-4o",
        prompt="What is the capital of France?",
        response="The capital of France is Paris.",
        prompt_tokens=10,
        completion_tokens=8,
        cost_usd=0.001,
    )
```

The SDK buffers events in memory and flushes them as JSON batches over HTTP. If the server is unreachable it falls back to writing to disk locally.

---

## Self-Hosted Server

The ReAgent server is a lightweight FastAPI app backed by SQLite. It reuses the same storage engine as local mode — no ORM, no external database.

### Run with Docker

```bash
docker build -t reagent-server .

docker run -d \
  -p 8080:8080 \
  -v reagent-data:/data \
  -e REAGENT_API_KEYS="rk-abc123,rk-xyz789" \
  reagent-server
```

### Run directly

```bash
pip install -e ".[server]"

# Start with defaults (port 8080, SQLite at reagent_server.db)
reagent server start

# Custom port and database path
reagent server start --port 9090 --db /var/data/traces.db
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/ingest` | POST | Batch event ingestion (used by SDK) |
| `/api/v1/runs` | GET | List runs with filtering and pagination |
| `/api/v1/runs/{id}` | GET | Get full run with all steps |
| `/api/v1/runs/{id}/metadata` | GET | Get run metadata only |
| `/api/v1/runs/{id}/steps` | GET | Get run steps (optional type filter) |
| `/api/v1/runs/count` | GET | Count runs matching filters |
| `/api/v1/runs/{id}` | DELETE | Delete a run |
| `/api/v1/search` | GET | Full-text search across runs |
| `/api/v1/failures` | GET | List failed runs |
| `/api/v1/failures/stats` | GET | Failure category breakdown |
| `/api/v1/stats` | GET | Aggregate statistics |

### Authentication

Set the `REAGENT_API_KEYS` environment variable with a comma-separated list of valid API keys. If unset, the server runs in open dev mode (no auth required).

Clients authenticate with `Authorization: Bearer <api_key>`.

### Server Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REAGENT_SERVER_HOST` | `0.0.0.0` | Bind address |
| `REAGENT_SERVER_PORT` | `8080` | Bind port |
| `REAGENT_SERVER_DB` | `reagent_server.db` | SQLite database path |
| `REAGENT_API_KEYS` | _(empty)_ | Comma-separated valid API keys |

---

## Framework Integrations

### LangChain

```python
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor
from reagent import ReAgent
from reagent.adapters.langchain import ReAgentCallbackHandler

client = ReAgent()

handler = ReAgentCallbackHandler(
    client=client,
    project="langchain-agent",
    tags=["production", "customer-support"],
)

llm = ChatOpenAI(model="gpt-4", callbacks=[handler])
agent_executor = AgentExecutor(agent=agent, tools=tools, callbacks=[handler])
result = agent_executor.invoke({"input": "What's the weather in NYC?"})
```

### OpenAI SDK

```python
from openai import OpenAI
from reagent import ReAgent
from reagent.adapters.openai import OpenAIAdapter
from reagent.schema.run import RunConfig

reagent_client = ReAgent()

with reagent_client.trace(RunConfig(name="openai-app", project="my-project")) as ctx:
    adapter = OpenAIAdapter(reagent_client)
    openai_client = adapter.reagent_openai_client(OpenAI(), context=ctx)

    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "Hello!"}],
    )
```

### Manual Integration

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
            llm_response = call_llm(user_input)
            ctx.record_llm_call(
                model="gpt-4",
                prompt=user_input,
                response=llm_response,
                prompt_tokens=len(user_input.split()),
                completion_tokens=len(llm_response.split()),
            )

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
            ctx.record_error(
                error_message=str(e),
                error_type=type(e).__name__,
                error_traceback=traceback.format_exc(),
            )
            raise
```

---

## Web Dashboard

ReAgent includes an interactive web dashboard built with React, Vite, and Tailwind CSS. It provides three core views for debugging and understanding agent executions.

### Views

- **Run List** (`/runs`) — Card-based grid with status badges, model pills, cost/duration/step metrics, and filter controls (project, status, model, time range). Each card has [Inspect], [Replay], and [Export] actions.
- **Trace Inspect** (`/trace/:runId`) — Interactive node graph (powered by @xyflow/react) showing the execution flow with color-coded nodes (purple=LLM, blue=Tool, green=Retrieval, red=Error). Includes a detail panel with Prompt/Response/Raw/State tabs and a timeline bar.
- **Replay Player** (`/replay/:runId`) — Step-through debugger with playback controls (play/pause/next/prev), adjustable speed (0.5x–5x), breakpoints, a state inspector with expandable tree view, and keyboard shortcuts (Space, arrows, B, Esc, [/]).

### Running the Dashboard

```bash
cd dashboard
npm install
npm run dev      # Development server at http://localhost:5173
npm run build    # Production build to dist/
```

The dashboard runs with static mock data by default. To connect to a live ReAgent server, edit `src/api/client.js` to switch from mock exports to the HTTP client.

### Layout

The dashboard uses a 4-zone layout: global header (logo, search, project switcher), sidebar navigation, main stage, and a status bar (connection health, mode indicator).

---

## CLI Usage

The CLI works in both local and remote mode. For remote mode, set the server URL:

```bash
export REAGENT_SERVER_URL=https://reagent.example.com
export REAGENT_API_KEY=rk-abc123
```

### List and Inspect Runs

```bash
reagent list
reagent list --project my-project
reagent list --status failed
reagent inspect <run_id>
reagent search "database error"
```

### Failure Analysis

```bash
reagent failures list
reagent failures list --project my-project --category tool_timeout
reagent failures list --since 24h
reagent failures inspect <run_id> --traceback
reagent failures stats --project my-project
```

### Export Reports

```bash
reagent export <run_id> -f json -o trace.json
reagent export <run_id> -f markdown -o report.md
reagent export <run_id> -f html -o report.html
```

### Server Management

```bash
reagent server start
reagent server start --port 9090 --db ./traces.db
```

### Other Commands

```bash
reagent stats --project my-project
reagent diff <run_id_1> <run_id_2>
reagent replay <run_id>
reagent delete <run_id>
```

---

## Configuration

### Modes

ReAgent operates in two modes:

| Mode | SDK writes to | CLI reads from | Use case |
|------|--------------|----------------|----------|
| **local** (default) | SQLite/JSONL on disk | Same local files | Development, single-machine |
| **remote** | HTTP POST to server | HTTP GET from server | Production, multi-machine |

### Configuration File

Create `.reagent.yml` in your project root:

```yaml
# Local mode (default)
mode: local
project: my-default-project

storage:
  type: sqlite
  path: ~/.reagent/traces.db

redaction:
  enabled: true
  mode: mask

buffer:
  size: 100
  flush_interval_ms: 5000
```

```yaml
# Remote mode
mode: remote
server:
  url: "https://reagent.example.com"
  api_key: "rk-abc123"
  batch_size: 50
  flush_interval_ms: 2000
  timeout_seconds: 10
  retry_max: 3
  fallback_to_local: true
```

### Environment Variables

```bash
# Mode and server
export REAGENT_MODE=remote
export REAGENT_SERVER_URL=https://reagent.example.com
export REAGENT_API_KEY=rk-abc123

# General
export REAGENT_PROJECT=my-project
export REAGENT_STORAGE_PATH=~/.reagent/traces
export REAGENT_REDACTION_ENABLED=true
```

### Storage Backends (local mode)

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

---

## Architecture

```
SDK (mode="local")  --> Transport --> SQLiteStorage --> disk
SDK (mode="remote") --> RemoteTransport --> HTTP POST --> ReAgent Server --> SQLiteStorage --> disk
CLI (mode="local")  --> SQLiteStorage --> disk
CLI (mode="remote") --> RemoteStorage --> HTTP GET --> ReAgent Server --> SQLiteStorage --> disk
```

## Project Structure

```
src/reagent/
├── client/           # Main SDK client
│   ├── reagent.py    # ReAgent class (local + remote branching)
│   ├── context.py    # RunContext for recording
│   └── transport.py  # Sync, Async, Buffered, Offline, Remote transports
├── schema/           # Data models
│   ├── run.py        # Run, RunMetadata, RunConfig
│   └── steps.py      # LLMCallStep, ToolCallStep, ErrorStep, etc.
├── storage/          # Storage backends
│   ├── sqlite.py     # SQLite with FTS (used by server too)
│   ├── jsonl.py      # JSONL files
│   ├── memory.py     # In-memory
│   └── remote.py     # Read-only HTTP client for CLI remote mode
├── server/           # Self-hosted backend
│   ├── app.py        # FastAPI application
│   ├── config.py     # Server configuration
│   ├── auth.py       # API key authentication
│   ├── deps.py       # Dependency injection
│   └── routes/       # API endpoints (ingest, runs, search, stats, failures)
├── adapters/         # Framework integrations
│   ├── langchain.py  # LangChain callback handler
│   ├── openai.py     # OpenAI client wrapper
│   ├── openai_agents.py  # OpenAI Agents SDK
│   ├── crewai.py     # CrewAI adapter
│   └── llamaindex.py # LlamaIndex adapter
├── cli/              # CLI commands
│   ├── commands/     # Individual commands (list, inspect, server, etc.)
│   └── templates/    # HTML templates
dashboard/                # Web dashboard (React + Vite + Tailwind)
├── src/
│   ├── components/       # UI components (graph nodes, controls, cards)
│   ├── pages/            # Route pages (Runs, TraceInspect, ReplayPlayer, etc.)
│   ├── stores/           # Zustand state (runStore, traceStore, replayStore)
│   ├── hooks/            # Replay engine and keyboard shortcuts
│   └── api/              # API client and mock data
├── analysis/         # Analytics & search
├── classification/   # Failure classification
├── redaction/        # PII redaction
└── replay/           # Deterministic replay
```

---

## Development

```bash
pip install -e ".[dev]"

# Run tests
pytest tests/

# Run with coverage
pytest tests/ --cov=reagent

# Run integration tests only
pytest tests/integration/ -m integration

# Type checking
mypy src/reagent

# Linting
ruff check src/
ruff format src/
```

---

## License

MIT License - see LICENSE file for details.

---

## Contributing

Contributions welcome! See [DEVELOPMENT.md](DEVELOPMENT.md) for implementation status and guidelines.
