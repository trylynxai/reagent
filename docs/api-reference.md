# ReAgent Server API Reference

Base URL: `http://localhost:8080` (default local development)

Interactive Swagger documentation is available at **`/docs`** when the server
is running.

---

## Authentication

When the server is started with `REAGENT_API_KEYS` set, every request (except
`GET /health`) must include a Bearer token:

```
Authorization: Bearer rk-your-api-key
```

If no API keys are configured, the server runs in **dev mode** and all requests
are allowed without authentication.

### Error Responses for Authentication

| Status | Body | Meaning |
|--------|------|---------|
| `401` | `{"detail": "Missing or invalid Authorization header"}` | No `Authorization: Bearer ...` header present |
| `403` | `{"detail": "Invalid API key"}` | Token not in the configured key list |

---

## Error Response Format

All error responses follow the standard FastAPI format:

```json
{
  "detail": "Human-readable error message"
}
```

Common status codes:

| Code | Meaning |
|------|---------|
| `400` | Bad request / validation error |
| `401` | Missing authentication |
| `403` | Invalid API key |
| `404` | Resource not found |
| `422` | Request validation error (invalid query params or body) |
| `500` | Internal server error |

For `422` validation errors, the response includes field-level details:

```json
{
  "detail": [
    {
      "loc": ["query", "limit"],
      "msg": "ensure this value is greater than or equal to 1",
      "type": "value_error.number.not_ge"
    }
  ]
}
```

---

## Pagination Conventions

List endpoints support `limit` and `offset` query parameters:

| Parameter | Type | Default | Constraints | Description |
|-----------|------|---------|-------------|-------------|
| `limit` | integer | `50` | 1 -- 1000 | Maximum number of items to return |
| `offset` | integer | `0` | >= 0 | Number of items to skip |

Paginated endpoints return a JSON array. Use the array length and your current
offset to determine if more pages are available.

---

## Endpoints

### 1. GET /health

Health check. Not protected by authentication.

**Response**

```json
{
  "status": "ok"
}
```

| Status | Description |
|--------|-------------|
| `200` | Server is healthy |

**curl example**

```bash
curl http://localhost:8080/health
```

---

### 2. POST /api/v1/ingest

Ingest a batch of events (run metadata and/or steps) from the SDK.

**Request Body**

```json
{
  "events": [
    {
      "type": "metadata",
      "run_id": "550e8400-e29b-41d4-a716-446655440000",
      "data": {
        "name": "my-agent-run",
        "project": "my-project",
        "status": "completed",
        "start_time": "2025-01-15T10:30:00Z",
        "end_time": "2025-01-15T10:31:00Z",
        "total_tokens": 1500,
        "total_cost_usd": 0.003
      }
    },
    {
      "type": "step",
      "run_id": "550e8400-e29b-41d4-a716-446655440000",
      "step_type": "llm_call",
      "data": {
        "step_id": "step-001",
        "timestamp": "2025-01-15T10:30:05Z",
        "input": "What is the weather?",
        "output": "I can help with that.",
        "model": "gpt-4",
        "tokens_used": 150,
        "duration_ms": 1200
      }
    }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `events` | array | yes | List of events to ingest |
| `events[].type` | string | yes | `"metadata"` or `"step"` |
| `events[].run_id` | string (UUID) | yes | Run identifier |
| `events[].step_type` | string | no | Step type (e.g. `"llm_call"`, `"tool_call"`, `"custom"`). Only for `type: "step"` |
| `events[].data` | object | yes | Event payload; schema depends on `type` |

**Response**

```json
{
  "status": "ok",
  "events_received": 2
}
```

| Status | Description |
|--------|-------------|
| `200` | Events ingested successfully |
| `401` | Missing authentication |
| `403` | Invalid API key |
| `422` | Validation error |

**curl example**

```bash
curl -X POST http://localhost:8080/api/v1/ingest \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer rk-your-api-key" \
  -d '{
    "events": [
      {
        "type": "metadata",
        "run_id": "550e8400-e29b-41d4-a716-446655440000",
        "data": {"name": "test-run", "project": "demo", "status": "completed"}
      }
    ]
  }'
```

---

### 3. GET /api/v1/runs

List agent runs with optional filters, sorting, and pagination.

**Query Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `project` | string | *(none)* | Filter by project name |
| `status` | string | *(none)* | Filter by status. Comma-separated for multiple values (e.g. `completed,failed`) |
| `model` | string | *(none)* | Filter by model name |
| `has_error` | string | *(none)* | `"true"` or `"false"` to filter by error presence |
| `failure_category` | string | *(none)* | Filter by failure category |
| `name` | string | *(none)* | Filter by run name |
| `limit` | integer | `50` | Max results (1--1000) |
| `offset` | integer | `0` | Results to skip |
| `sort_by` | string | `start_time` | Field to sort by |
| `sort_order` | string | `desc` | `asc` or `desc` |

**Response**

```json
[
  {
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "my-agent-run",
    "project": "my-project",
    "status": "completed",
    "start_time": "2025-01-15T10:30:00Z",
    "end_time": "2025-01-15T10:31:00Z",
    "total_tokens": 1500,
    "total_cost_usd": 0.003,
    "has_error": false,
    "failure_category": null
  }
]
```

| Status | Description |
|--------|-------------|
| `200` | Success |
| `401` | Missing authentication |
| `403` | Invalid API key |
| `422` | Invalid query parameters |

**curl example**

```bash
curl "http://localhost:8080/api/v1/runs?project=my-project&status=completed&limit=10" \
  -H "Authorization: Bearer rk-your-api-key"
```

---

### 4. GET /api/v1/runs/{run_id}

Retrieve a single run by its ID.

**Path Parameters**

| Name | Type | Description |
|------|------|-------------|
| `run_id` | string (UUID) | The run identifier |

**Response**

```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "my-agent-run",
  "project": "my-project",
  "status": "completed",
  "start_time": "2025-01-15T10:30:00Z",
  "end_time": "2025-01-15T10:31:00Z",
  "total_tokens": 1500,
  "total_cost_usd": 0.003,
  "steps": [ ... ]
}
```

| Status | Description |
|--------|-------------|
| `200` | Success |
| `401` | Missing authentication |
| `403` | Invalid API key |
| `404` | Run not found |

**curl example**

```bash
curl http://localhost:8080/api/v1/runs/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer rk-your-api-key"
```

---

### 5. GET /api/v1/runs/{run_id}/metadata

Retrieve only the metadata for a run (without steps).

**Path Parameters**

| Name | Type | Description |
|------|------|-------------|
| `run_id` | string (UUID) | The run identifier |

**Response**

```json
{
  "name": "my-agent-run",
  "project": "my-project",
  "status": "completed",
  "start_time": "2025-01-15T10:30:00Z",
  "end_time": "2025-01-15T10:31:00Z",
  "total_tokens": 1500,
  "total_cost_usd": 0.003
}
```

| Status | Description |
|--------|-------------|
| `200` | Success |
| `401` | Missing authentication |
| `403` | Invalid API key |
| `404` | Run not found |

**curl example**

```bash
curl http://localhost:8080/api/v1/runs/550e8400-e29b-41d4-a716-446655440000/metadata \
  -H "Authorization: Bearer rk-your-api-key"
```

---

### 6. GET /api/v1/runs/{run_id}/steps

Retrieve the steps for a run, with optional filtering.

**Path Parameters**

| Name | Type | Description |
|------|------|-------------|
| `run_id` | string (UUID) | The run identifier |

**Query Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `step_type` | string | *(none)* | Filter by step type (e.g. `llm_call`, `tool_call`) |
| `start` | integer | *(none)* | Start index for step range |
| `end` | integer | *(none)* | End index for step range |

**Response**

```json
[
  {
    "step_id": "step-001",
    "step_type": "llm_call",
    "timestamp": "2025-01-15T10:30:05Z",
    "input": "What is the weather?",
    "output": "I can help with that.",
    "model": "gpt-4",
    "tokens_used": 150,
    "duration_ms": 1200
  },
  {
    "step_id": "step-002",
    "step_type": "tool_call",
    "timestamp": "2025-01-15T10:30:07Z",
    "tool_name": "weather_api",
    "input": {"location": "San Francisco"},
    "output": {"temp": 65, "unit": "F"}
  }
]
```

| Status | Description |
|--------|-------------|
| `200` | Success |
| `401` | Missing authentication |
| `403` | Invalid API key |
| `404` | Run not found |

**curl example**

```bash
curl "http://localhost:8080/api/v1/runs/550e8400-e29b-41d4-a716-446655440000/steps?step_type=llm_call" \
  -H "Authorization: Bearer rk-your-api-key"
```

---

### 7. GET /api/v1/runs/count

Return the total number of runs matching optional filters.

**Query Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `project` | string | *(none)* | Filter by project name |
| `status` | string | *(none)* | Filter by status (comma-separated for multiple) |

**Response**

```json
{
  "count": 42
}
```

| Status | Description |
|--------|-------------|
| `200` | Success |
| `401` | Missing authentication |
| `403` | Invalid API key |

**curl example**

```bash
curl "http://localhost:8080/api/v1/runs/count?project=my-project" \
  -H "Authorization: Bearer rk-your-api-key"
```

---

### 8. DELETE /api/v1/runs/{run_id}

Delete a run and all its associated steps.

**Path Parameters**

| Name | Type | Description |
|------|------|-------------|
| `run_id` | string (UUID) | The run identifier |

**Response**

```json
{
  "deleted": true
}
```

Returns `{"deleted": false}` if the run did not exist.

| Status | Description |
|--------|-------------|
| `200` | Request processed (check `deleted` field) |
| `401` | Missing authentication |
| `403` | Invalid API key |

**curl example**

```bash
curl -X DELETE http://localhost:8080/api/v1/runs/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer rk-your-api-key"
```

---

### 9. GET /api/v1/search

Full-text search across runs.

**Query Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `q` | string | *(required)* | Search query string |
| `project` | string | *(none)* | Limit search to a project |
| `limit` | integer | `50` | Max results (1--1000) |
| `offset` | integer | `0` | Results to skip |

**Response**

Returns an array of run objects matching the query (same shape as
`GET /api/v1/runs`).

```json
[
  {
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "weather-agent-run",
    "project": "my-project",
    "status": "completed",
    ...
  }
]
```

| Status | Description |
|--------|-------------|
| `200` | Success |
| `401` | Missing authentication |
| `403` | Invalid API key |
| `422` | Missing required `q` parameter |

**curl example**

```bash
curl "http://localhost:8080/api/v1/search?q=weather&project=my-project&limit=20" \
  -H "Authorization: Bearer rk-your-api-key"
```

---

### 10. GET /api/v1/failures

List runs that have errors.

**Query Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `project` | string | *(none)* | Filter by project name |
| `limit` | integer | `50` | Max results (1--1000) |
| `offset` | integer | `0` | Results to skip |

**Response**

Returns an array of run objects where `has_error` is `true` (same shape as
`GET /api/v1/runs`).

```json
[
  {
    "run_id": "660e8400-e29b-41d4-a716-446655440001",
    "name": "failing-agent",
    "project": "my-project",
    "status": "failed",
    "has_error": true,
    "failure_category": "timeout",
    ...
  }
]
```

| Status | Description |
|--------|-------------|
| `200` | Success |
| `401` | Missing authentication |
| `403` | Invalid API key |

**curl example**

```bash
curl "http://localhost:8080/api/v1/failures?project=my-project&limit=10" \
  -H "Authorization: Bearer rk-your-api-key"
```

---

### 11. GET /api/v1/failures/stats

Aggregate failure statistics, grouped by failure category.

**Query Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `project` | string | *(none)* | Filter by project name |

**Response**

```json
{
  "total_failures": 15,
  "by_category": {
    "timeout": 7,
    "rate_limit": 5,
    "unknown": 3
  }
}
```

| Status | Description |
|--------|-------------|
| `200` | Success |
| `401` | Missing authentication |
| `403` | Invalid API key |

**curl example**

```bash
curl "http://localhost:8080/api/v1/failures/stats?project=my-project" \
  -H "Authorization: Bearer rk-your-api-key"
```

---

### 12. GET /api/v1/stats

Aggregate statistics across all runs.

**Query Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `project` | string | *(none)* | Filter by project name |

**Response**

```json
{
  "total_runs": 100,
  "completed": 85,
  "failed": 15,
  "total_tokens": 250000,
  "total_cost_usd": 1.25,
  "success_rate": 0.85
}
```

| Status | Description |
|--------|-------------|
| `200` | Success |
| `401` | Missing authentication |
| `403` | Invalid API key |

**curl example**

```bash
curl "http://localhost:8080/api/v1/stats?project=my-project" \
  -H "Authorization: Bearer rk-your-api-key"
```
