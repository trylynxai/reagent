/**
 * Rich static mock data for the ReAgent dashboard.
 * Simulates a production environment with varied runs, failures, and step types.
 */

// ── Helpers ─────────────────────────────────────────────────

let _id = 0;
function uuid() {
  _id++;
  const hex = _id.toString(16).padStart(8, '0');
  return `a1b2c3d4-e5f6-4a7b-8c9d-${hex}000000`.slice(0, 36);
}

function stepId() {
  return uuid();
}

function ago(minutes) {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

function durationMs(min, max) {
  return Math.floor(Math.random() * (max - min) + min);
}

// ── Runs ────────────────────────────────────────────────────

const RUNS = [
  // ── Critical failures ──────────────────────────────
  {
    run_id: "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    name: "customer-support-agent",
    project: "prod-agents",
    tags: ["production", "customer-support", "tier-1"],
    start_time: ago(12),
    end_time: ago(11),
    duration_ms: 45230,
    status: "failed",
    model: "gpt-4o",
    step_count: 8,
    total_tokens: 12450,
    total_cost_usd: 0.0892,
    error: "RateLimitError: Rate limit exceeded for model gpt-4o. Retry after 32 seconds.",
    failure_category: "rate_limit",
  },
  {
    run_id: "b5d3e8a1-7c2f-4b6e-9d1a-3f8c2e5a7b90",
    name: "data-pipeline-orchestrator",
    project: "prod-agents",
    tags: ["production", "data-pipeline", "critical"],
    start_time: ago(25),
    end_time: ago(23),
    duration_ms: 128400,
    status: "failed",
    model: "claude-3.5-sonnet",
    step_count: 15,
    total_tokens: 34200,
    total_cost_usd: 0.2156,
    error: "ToolTimeoutError: Tool 'database_query' timed out after 30000ms while executing SELECT * FROM analytics.events WHERE timestamp > '2024-01-01'",
    failure_category: "tool_timeout",
  },
  {
    run_id: "c8e2f1a3-9b4d-4c7e-a2d5-6f3b8e1c9a70",
    name: "code-review-agent",
    project: "dev-tools",
    tags: ["production", "code-review", "github"],
    start_time: ago(45),
    end_time: ago(44),
    duration_ms: 67800,
    status: "failed",
    model: "gpt-4o",
    step_count: 12,
    total_tokens: 89200,
    total_cost_usd: 0.4521,
    error: "ContextOverflowError: Total tokens (128942) exceed model context window (128000). The diff for PR #2847 is too large to fit in a single pass.",
    failure_category: "context_overflow",
  },
  {
    run_id: "d1a4b7c3-2e5f-4890-b3c6-7d9a1e4f2b80",
    name: "email-drafting-agent",
    project: "prod-agents",
    tags: ["production", "email", "outbound"],
    start_time: ago(60),
    end_time: ago(59),
    duration_ms: 23100,
    status: "failed",
    model: "gpt-4o-mini",
    step_count: 5,
    total_tokens: 4300,
    total_cost_usd: 0.0034,
    error: "AuthenticationError: Invalid API key provided. The API key 'sk-...WxYz' is expired or revoked.",
    failure_category: "authentication",
  },
  {
    run_id: "e2b5c8d4-3f6a-4901-c4d7-8e0b2f5a3c91",
    name: "inventory-check-agent",
    project: "ecommerce",
    tags: ["production", "inventory", "warehouse"],
    start_time: ago(90),
    end_time: ago(88),
    duration_ms: 95300,
    status: "failed",
    model: "claude-3.5-sonnet",
    step_count: 11,
    total_tokens: 18700,
    total_cost_usd: 0.1203,
    error: "ToolError: Tool 'inventory_api' returned HTTP 500: Internal Server Error. Response body: {\"error\": \"database connection pool exhausted\", \"retry_after\": 60}",
    failure_category: "tool_error",
  },
  {
    run_id: "f3c6d9e5-4a7b-4012-d5e8-9f1c3a6b4d02",
    name: "report-generator",
    project: "analytics",
    tags: ["production", "reports", "weekly"],
    start_time: ago(120),
    end_time: ago(118),
    duration_ms: 142000,
    status: "failed",
    model: "gpt-4o",
    step_count: 22,
    total_tokens: 156000,
    total_cost_usd: 1.2340,
    error: "ValidationError: Output schema validation failed. Expected field 'quarterly_revenue' to be float, got string 'N/A'. Agent attempted self-correction 3 times but could not resolve.",
    failure_category: "validation_error",
  },
  {
    run_id: "a4d7e0f6-5b8c-4123-e6f9-0a2d4b7c5e13",
    name: "slack-responder-bot",
    project: "prod-agents",
    tags: ["production", "slack", "auto-reply"],
    start_time: ago(150),
    end_time: ago(149),
    duration_ms: 31200,
    status: "failed",
    model: "gpt-4o-mini",
    step_count: 6,
    total_tokens: 3200,
    total_cost_usd: 0.0019,
    error: "ConnectionError: Failed to connect to Slack API: Connection refused. The Slack webhook endpoint https://hooks.slack.com/services/T0... returned ECONNREFUSED.",
    failure_category: "connection_error",
  },
  {
    run_id: "b5e8f1a7-6c9d-4234-f7a0-1b3e5c8d6f24",
    name: "research-agent-deep-dive",
    project: "research",
    tags: ["production", "research", "multi-step"],
    start_time: ago(180),
    end_time: ago(175),
    duration_ms: 312000,
    status: "failed",
    model: "gpt-4o",
    step_count: 47,
    total_tokens: 245000,
    total_cost_usd: 2.8900,
    error: "ReasoningLoopError: Agent entered infinite reasoning loop. Detected 12 consecutive identical tool calls to 'web_search' with query 'latest AI safety papers 2024'. Circuit breaker triggered after max_iterations=50.",
    failure_category: "reasoning_loop",
  },

  // ── Successful runs ────────────────────────────────
  {
    run_id: "11111111-aaaa-4bbb-cccc-dddddddddd01",
    name: "customer-support-agent",
    project: "prod-agents",
    tags: ["production", "customer-support", "tier-1"],
    start_time: ago(5),
    end_time: ago(4),
    duration_ms: 12300,
    status: "completed",
    model: "gpt-4o",
    step_count: 6,
    total_tokens: 8900,
    total_cost_usd: 0.0534,
    error: null,
    failure_category: null,
  },
  {
    run_id: "11111111-aaaa-4bbb-cccc-dddddddddd02",
    name: "lead-qualification-agent",
    project: "sales",
    tags: ["production", "leads", "crm"],
    start_time: ago(8),
    end_time: ago(7),
    duration_ms: 18200,
    status: "completed",
    model: "gpt-4o-mini",
    step_count: 9,
    total_tokens: 6200,
    total_cost_usd: 0.0078,
    error: null,
    failure_category: null,
  },
  {
    run_id: "11111111-aaaa-4bbb-cccc-dddddddddd03",
    name: "document-summarizer",
    project: "analytics",
    tags: ["production", "summarization"],
    start_time: ago(15),
    end_time: ago(14),
    duration_ms: 34500,
    status: "completed",
    model: "claude-3.5-sonnet",
    step_count: 4,
    total_tokens: 28400,
    total_cost_usd: 0.1704,
    error: null,
    failure_category: null,
  },
  {
    run_id: "11111111-aaaa-4bbb-cccc-dddddddddd04",
    name: "meeting-notes-agent",
    project: "prod-agents",
    tags: ["production", "meetings", "transcription"],
    start_time: ago(30),
    end_time: ago(29),
    duration_ms: 56700,
    status: "completed",
    model: "gpt-4o",
    step_count: 7,
    total_tokens: 15600,
    total_cost_usd: 0.0936,
    error: null,
    failure_category: null,
  },
  {
    run_id: "11111111-aaaa-4bbb-cccc-dddddddddd05",
    name: "competitor-analysis-bot",
    project: "research",
    tags: ["production", "research", "competitive-intel"],
    start_time: ago(50),
    end_time: ago(48),
    duration_ms: 98200,
    status: "completed",
    model: "gpt-4o",
    step_count: 18,
    total_tokens: 42300,
    total_cost_usd: 0.3120,
    error: null,
    failure_category: null,
  },
  {
    run_id: "11111111-aaaa-4bbb-cccc-dddddddddd06",
    name: "onboarding-guide-agent",
    project: "prod-agents",
    tags: ["production", "onboarding", "hr"],
    start_time: ago(70),
    end_time: ago(69),
    duration_ms: 21400,
    status: "completed",
    model: "gpt-4o-mini",
    step_count: 5,
    total_tokens: 4100,
    total_cost_usd: 0.0041,
    error: null,
    failure_category: null,
  },
  {
    run_id: "11111111-aaaa-4bbb-cccc-dddddddddd07",
    name: "pricing-optimizer",
    project: "ecommerce",
    tags: ["production", "pricing", "ml"],
    start_time: ago(100),
    end_time: ago(98),
    duration_ms: 87600,
    status: "completed",
    model: "claude-3.5-sonnet",
    step_count: 14,
    total_tokens: 31200,
    total_cost_usd: 0.1872,
    error: null,
    failure_category: null,
  },
  {
    run_id: "11111111-aaaa-4bbb-cccc-dddddddddd08",
    name: "content-writer",
    project: "marketing",
    tags: ["production", "content", "blog"],
    start_time: ago(130),
    end_time: ago(128),
    duration_ms: 112000,
    status: "completed",
    model: "gpt-4o",
    step_count: 10,
    total_tokens: 52000,
    total_cost_usd: 0.3640,
    error: null,
    failure_category: null,
  },
  {
    run_id: "11111111-aaaa-4bbb-cccc-dddddddddd09",
    name: "ticket-triage-agent",
    project: "prod-agents",
    tags: ["production", "jira", "triage"],
    start_time: ago(160),
    end_time: ago(159),
    duration_ms: 8900,
    status: "completed",
    model: "gpt-4o-mini",
    step_count: 3,
    total_tokens: 2100,
    total_cost_usd: 0.0021,
    error: null,
    failure_category: null,
  },
  {
    run_id: "11111111-aaaa-4bbb-cccc-dddddddddd10",
    name: "api-docs-generator",
    project: "dev-tools",
    tags: ["production", "docs", "openapi"],
    start_time: ago(200),
    end_time: ago(197),
    duration_ms: 178000,
    status: "completed",
    model: "gpt-4o",
    step_count: 24,
    total_tokens: 98000,
    total_cost_usd: 0.7350,
    error: null,
    failure_category: null,
  },
  // Running
  {
    run_id: "22222222-bbbb-4ccc-dddd-eeeeeeeeee01",
    name: "realtime-monitor-agent",
    project: "prod-agents",
    tags: ["production", "monitoring", "alerts"],
    start_time: ago(2),
    end_time: null,
    duration_ms: null,
    status: "running",
    model: "gpt-4o-mini",
    step_count: 3,
    total_tokens: 1800,
    total_cost_usd: 0.0014,
    error: null,
    failure_category: null,
  },
  // Cancelled
  {
    run_id: "33333333-cccc-4ddd-eeee-ffffffffffff",
    name: "bulk-email-campaign",
    project: "marketing",
    tags: ["production", "email", "campaign"],
    start_time: ago(240),
    end_time: ago(238),
    duration_ms: 45000,
    status: "cancelled",
    model: "gpt-4o-mini",
    step_count: 4,
    total_tokens: 3400,
    total_cost_usd: 0.0034,
    error: null,
    failure_category: null,
  },
];

// ── Full run detail (steps) for the first few runs ──────────

function makeRunDetail(summary, steps) {
  return {
    metadata: {
      run_id: summary.run_id,
      name: summary.name,
      project: summary.project,
      tags: summary.tags,
      start_time: summary.start_time,
      end_time: summary.end_time,
      duration_ms: summary.duration_ms,
      status: summary.status,
      model: summary.model,
      models_used: [summary.model],
      cost: { total_usd: summary.total_cost_usd },
      tokens: {
        total_tokens: summary.total_tokens,
        prompt_tokens: Math.floor(summary.total_tokens * 0.6),
        completion_tokens: Math.floor(summary.total_tokens * 0.4),
      },
      steps: {
        total: steps.length,
        llm_calls: steps.filter(s => s.step_type === 'llm_call').length,
        tool_calls: steps.filter(s => s.step_type === 'tool_call').length,
        errors: steps.filter(s => s.step_type === 'error').length,
      },
      error: summary.error,
      error_type: summary.error ? summary.error.split(':')[0] : null,
      failure_category: summary.failure_category,
      input: { user_query: "Process the customer request and respond appropriately" },
      output: summary.status === 'completed' ? { result: "Task completed successfully" } : null,
      custom: { environment: "production", region: "us-east-1" },
      schema_version: "1.0",
    },
    steps,
  };
}

// Steps for "customer-support-agent" (rate_limit failure)
const RUN_DETAIL_RATE_LIMIT = makeRunDetail(RUNS[0], [
  {
    step_id: stepId(), run_id: RUNS[0].run_id, step_number: 0, step_type: "llm_call",
    timestamp_start: ago(12), timestamp_end: ago(12), duration_ms: 2340,
    model: "gpt-4o",
    prompt: "You are a customer support agent. The customer says:\n\n\"I've been charged twice for my subscription this month. Order #ORD-29481. Can you help me get a refund?\"",
    response: "I'll look into this right away. Let me check the billing records for order #ORD-29481.",
    token_usage: { prompt_tokens: 89, completion_tokens: 34, total_tokens: 123 },
  },
  {
    step_id: stepId(), run_id: RUNS[0].run_id, step_number: 1, step_type: "tool_call",
    timestamp_start: ago(12), timestamp_end: ago(12), duration_ms: 890,
    tool_name: "billing_lookup",
    input: { args: [], kwargs: { order_id: "ORD-29481", include_refunds: true } },
    output: { result: { order_id: "ORD-29481", amount: 29.99, charges: [{ date: "2024-03-01", amount: 29.99, status: "settled" }, { date: "2024-03-01", amount: 29.99, status: "settled" }], refunds: [] } },
  },
  {
    step_id: stepId(), run_id: RUNS[0].run_id, step_number: 2, step_type: "llm_call",
    timestamp_start: ago(12), timestamp_end: ago(12), duration_ms: 3100,
    model: "gpt-4o",
    prompt: "Billing records show two charges of $29.99 on 2024-03-01 for order ORD-29481. No refunds have been issued. The customer was indeed double-charged. Draft a response and initiate a refund.",
    response: "I can confirm there was a duplicate charge. I'll initiate the refund now and send the customer a confirmation.",
    token_usage: { prompt_tokens: 156, completion_tokens: 42, total_tokens: 198 },
  },
  {
    step_id: stepId(), run_id: RUNS[0].run_id, step_number: 3, step_type: "tool_call",
    timestamp_start: ago(12), timestamp_end: ago(12), duration_ms: 1200,
    tool_name: "process_refund",
    input: { args: [], kwargs: { order_id: "ORD-29481", amount: 29.99, reason: "duplicate_charge" } },
    output: { result: { refund_id: "REF-88412", status: "pending", estimated_days: 3 } },
  },
  {
    step_id: stepId(), run_id: RUNS[0].run_id, step_number: 4, step_type: "llm_call",
    timestamp_start: ago(11), timestamp_end: ago(11), duration_ms: 1800,
    model: "gpt-4o",
    prompt: "Refund REF-88412 has been initiated for $29.99. Estimated processing time: 3 business days. Now compose a customer-friendly email response.",
    response: null,
    error: "RateLimitError: Rate limit exceeded for model gpt-4o. Retry after 32 seconds.",
    error_type: "RateLimitError",
  },
  {
    step_id: stepId(), run_id: RUNS[0].run_id, step_number: 5, step_type: "llm_call",
    timestamp_start: ago(11), timestamp_end: ago(11), duration_ms: 1500,
    model: "gpt-4o",
    prompt: "[RETRY 1/3] Compose a customer-friendly email response confirming the refund.",
    response: null,
    error: "RateLimitError: Rate limit exceeded for model gpt-4o. Retry after 32 seconds.",
    error_type: "RateLimitError",
  },
  {
    step_id: stepId(), run_id: RUNS[0].run_id, step_number: 6, step_type: "llm_call",
    timestamp_start: ago(11), timestamp_end: ago(11), duration_ms: 1400,
    model: "gpt-4o",
    prompt: "[RETRY 2/3] Compose a customer-friendly email response confirming the refund.",
    response: null,
    error: "RateLimitError: Rate limit exceeded for model gpt-4o. Retry after 32 seconds.",
    error_type: "RateLimitError",
  },
  {
    step_id: stepId(), run_id: RUNS[0].run_id, step_number: 7, step_type: "error",
    timestamp_start: ago(11), timestamp_end: ago(11), duration_ms: 0,
    error: "RateLimitError",
    error_message: "Rate limit exceeded for model gpt-4o. All 3 retries exhausted. Last attempt at 2024-03-14T12:45:32Z. The agent could not complete the customer response email. Refund REF-88412 was already initiated but customer has not been notified.",
    error_traceback: "Traceback (most recent call last):\n  File \"/app/agents/support.py\", line 142, in run\n    response = await self.llm.complete(prompt)\n  File \"/app/lib/llm_client.py\", line 89, in complete\n    return await self._call_with_retry(prompt, max_retries=3)\n  File \"/app/lib/llm_client.py\", line 67, in _call_with_retry\n    raise RateLimitError(f\"Rate limit exceeded after {retries} retries\")\nRateLimitError: Rate limit exceeded for model gpt-4o. Retry after 32 seconds.",
  },
]);

// Steps for "data-pipeline-orchestrator" (tool_timeout)
const RUN_DETAIL_TIMEOUT = makeRunDetail(RUNS[1], [
  {
    step_id: stepId(), run_id: RUNS[1].run_id, step_number: 0, step_type: "chain",
    timestamp_start: ago(25), timestamp_end: ago(23), duration_ms: 128400,
    chain_name: "DataPipelineChain", chain_type: "sequential",
    input: { pipeline: "weekly_analytics", tables: ["events", "users", "transactions"] },
    output: null,
  },
  {
    step_id: stepId(), run_id: RUNS[1].run_id, step_number: 1, step_type: "llm_call",
    timestamp_start: ago(25), timestamp_end: ago(25), duration_ms: 4200,
    model: "claude-3.5-sonnet",
    prompt: "You are a data pipeline orchestrator. Generate the SQL queries needed to build the weekly analytics report for tables: events, users, transactions.",
    response: "I'll create the extraction queries. Starting with the events table which needs filtering by the last 7 days.\n\n1. Events: SELECT * FROM analytics.events WHERE timestamp > '2024-01-01'\n2. Users: SELECT user_id, email, plan_type FROM users WHERE active = true\n3. Transactions: SELECT * FROM transactions WHERE created_at > NOW() - INTERVAL '7 days'",
  },
  {
    step_id: stepId(), run_id: RUNS[1].run_id, step_number: 2, step_type: "tool_call",
    timestamp_start: ago(25), timestamp_end: ago(25), duration_ms: 1200,
    tool_name: "database_query",
    input: { args: [], kwargs: { query: "SELECT user_id, email, plan_type FROM users WHERE active = true", database: "production", timeout_ms: 30000 } },
    output: { result: { rows: 14523, execution_time_ms: 890 } },
  },
  {
    step_id: stepId(), run_id: RUNS[1].run_id, step_number: 3, step_type: "tool_call",
    timestamp_start: ago(25), timestamp_end: ago(24), duration_ms: 30000,
    tool_name: "database_query",
    input: { args: [], kwargs: { query: "SELECT * FROM analytics.events WHERE timestamp > '2024-01-01'", database: "production", timeout_ms: 30000 } },
    output: null,
    error: "ToolTimeoutError: Query timed out after 30000ms. The analytics.events table contains 847M rows and a full scan was triggered due to missing index on timestamp column.",
  },
  {
    step_id: stepId(), run_id: RUNS[1].run_id, step_number: 4, step_type: "llm_call",
    timestamp_start: ago(24), timestamp_end: ago(24), duration_ms: 3800,
    model: "claude-3.5-sonnet",
    prompt: "The query on analytics.events timed out. The table has 847M rows. Suggest an optimized query approach.",
    response: "The events table is too large for a full scan. I'll try partitioning the query by date ranges and using LIMIT to batch the results.",
  },
  {
    step_id: stepId(), run_id: RUNS[1].run_id, step_number: 5, step_type: "tool_call",
    timestamp_start: ago(24), timestamp_end: ago(23), duration_ms: 30000,
    tool_name: "database_query",
    input: { args: [], kwargs: { query: "SELECT * FROM analytics.events WHERE timestamp > '2024-03-07' AND timestamp <= '2024-03-14' LIMIT 1000000", database: "production", timeout_ms: 30000 } },
    output: null,
    error: "ToolTimeoutError: Query timed out again after 30000ms. Even with date filtering, the table scan is too slow without a proper index.",
  },
  {
    step_id: stepId(), run_id: RUNS[1].run_id, step_number: 6, step_type: "error",
    timestamp_start: ago(23), timestamp_end: ago(23), duration_ms: 0,
    error: "ToolTimeoutError",
    error_message: "Tool 'database_query' timed out after 30000ms while executing SELECT * FROM analytics.events WHERE timestamp > '2024-01-01'. Two attempts failed. The analytics.events table (847M rows) requires an index on the timestamp column for this query pattern.",
    error_traceback: "Traceback (most recent call last):\n  File \"/app/agents/pipeline.py\", line 98, in execute_step\n    result = await tool.execute(input, timeout_ms=30000)\n  File \"/app/tools/database.py\", line 45, in execute\n    cursor.execute(query)\n  File \"/usr/lib/python3.12/sqlite3/connection.py\", line 87, in execute\n    raise OperationalError(\"query timed out\")\nsqlite3.OperationalError: query timed out",
  },
]);

// Steps for "code-review-agent" (context_overflow)
const RUN_DETAIL_OVERFLOW = makeRunDetail(RUNS[2], [
  {
    step_id: stepId(), run_id: RUNS[2].run_id, step_number: 0, step_type: "tool_call",
    timestamp_start: ago(45), timestamp_end: ago(45), duration_ms: 2300,
    tool_name: "github_pr_fetch",
    input: { args: [], kwargs: { repo: "acme/backend", pr_number: 2847 } },
    output: { result: { title: "Refactor auth middleware + migrate to JWT v3", files_changed: 47, additions: 3892, deletions: 2104, diff_size_chars: 312000 } },
  },
  {
    step_id: stepId(), run_id: RUNS[2].run_id, step_number: 1, step_type: "llm_call",
    timestamp_start: ago(45), timestamp_end: ago(45), duration_ms: 8200,
    model: "gpt-4o",
    prompt: "Review this pull request:\n\nTitle: Refactor auth middleware + migrate to JWT v3\nFiles changed: 47 | +3892 -2104\n\n[Full diff - 312,000 characters]\n\nProvide a thorough code review covering:\n1. Security concerns\n2. Breaking changes\n3. Performance implications\n4. Code quality issues",
    response: null,
    error: "ContextOverflowError: Total tokens (128942) exceed model context window (128000)",
    error_type: "ContextOverflowError",
  },
  {
    step_id: stepId(), run_id: RUNS[2].run_id, step_number: 2, step_type: "llm_call",
    timestamp_start: ago(45), timestamp_end: ago(44), duration_ms: 6500,
    model: "gpt-4o",
    prompt: "[CHUNKED REVIEW - Batch 1/4] Reviewing files 1-12 of 47:\n\nsrc/middleware/auth.ts (+342 -189)\nsrc/middleware/jwt.ts (+567 -0) [NEW]\n...",
    response: "## Batch 1 Review\n\n### Critical Issues:\n1. **JWT secret rotation** - The new `JWTManager` class stores the signing key in memory without rotation support. In production, keys should be rotated periodically.\n2. **Missing rate limiting** - The auth middleware no longer includes rate limiting logic that was present in the old version.",
  },
  {
    step_id: stepId(), run_id: RUNS[2].run_id, step_number: 3, step_type: "llm_call",
    timestamp_start: ago(44), timestamp_end: ago(44), duration_ms: 7100,
    model: "gpt-4o",
    prompt: "[CHUNKED REVIEW - Batch 2/4] Reviewing files 13-24...",
    response: "## Batch 2 Review\n\n### Issues:\n1. **SQL injection risk** in `user_lookup.ts` line 45 - using string interpolation instead of parameterized queries\n2. **Deprecated crypto.createCipher** usage in encryption helper",
  },
  {
    step_id: stepId(), run_id: RUNS[2].run_id, step_number: 4, step_type: "error",
    timestamp_start: ago(44), timestamp_end: ago(44), duration_ms: 0,
    error: "ContextOverflowError",
    error_message: "Total tokens (128942) exceed model context window (128000). The diff for PR #2847 is too large to fit in a single pass. Chunked review completed 2 of 4 batches before budget was exhausted.",
  },
]);

// Steps for "research-agent-deep-dive" (reasoning_loop)
const RUN_DETAIL_LOOP = makeRunDetail(RUNS[7], [
  {
    step_id: stepId(), run_id: RUNS[7].run_id, step_number: 0, step_type: "llm_call",
    timestamp_start: ago(180), timestamp_end: ago(180), duration_ms: 3200,
    model: "gpt-4o",
    prompt: "Research the latest developments in AI safety. Provide a comprehensive report with sources.",
    response: "I'll conduct a thorough search across multiple sources to compile a comprehensive AI safety report. Let me start by searching for the latest papers and articles.",
  },
  {
    step_id: stepId(), run_id: RUNS[7].run_id, step_number: 1, step_type: "tool_call",
    timestamp_start: ago(180), timestamp_end: ago(180), duration_ms: 4500,
    tool_name: "web_search",
    input: { args: [], kwargs: { query: "latest AI safety papers 2024", max_results: 10 } },
    output: { result: { results: [{ title: "AI Safety Research Agenda 2024", url: "https://arxiv.org/..." }], total: 10 } },
  },
  {
    step_id: stepId(), run_id: RUNS[7].run_id, step_number: 2, step_type: "llm_call",
    timestamp_start: ago(180), timestamp_end: ago(179), duration_ms: 2800,
    model: "gpt-4o",
    prompt: "I found some results but I need more specific papers. Let me search again with a more refined query.",
    response: "The results aren't specific enough. I should search again for more targeted results.",
  },
  ...Array.from({ length: 10 }, (_, i) => ({
    step_id: stepId(), run_id: RUNS[7].run_id, step_number: 3 + i * 2, step_type: "tool_call",
    timestamp_start: ago(179 - i), timestamp_end: ago(179 - i), duration_ms: 4200,
    tool_name: "web_search",
    input: { args: [], kwargs: { query: "latest AI safety papers 2024", max_results: 10 } },
    output: { result: { results: [{ title: "AI Safety Research Agenda 2024", url: "https://arxiv.org/..." }], total: 10 } },
  })),
  ...Array.from({ length: 10 }, (_, i) => ({
    step_id: stepId(), run_id: RUNS[7].run_id, step_number: 4 + i * 2, step_type: "llm_call",
    timestamp_start: ago(179 - i), timestamp_end: ago(179 - i), duration_ms: 2100,
    model: "gpt-4o",
    prompt: "Results still not comprehensive enough. Searching again...",
    response: "I need to find more recent and specific papers. Let me try the search one more time.",
  })),
  {
    step_id: stepId(), run_id: RUNS[7].run_id, step_number: 46, step_type: "error",
    timestamp_start: ago(175), timestamp_end: ago(175), duration_ms: 0,
    error: "ReasoningLoopError",
    error_message: "Agent entered infinite reasoning loop. Detected 12 consecutive identical tool calls to 'web_search' with query 'latest AI safety papers 2024'. Circuit breaker triggered after max_iterations=50.",
    error_traceback: "Traceback (most recent call last):\n  File \"/app/agents/research.py\", line 201, in run_loop\n    action = await self.decide_next_action()\n  File \"/app/agents/research.py\", line 178, in decide_next_action\n    raise ReasoningLoopError(f\"Detected {count} identical calls\")\nReasoningLoopError: Agent entered infinite reasoning loop after 50 iterations",
  },
]);

// Completed run detail
const RUN_DETAIL_SUCCESS = makeRunDetail(RUNS[8], [
  {
    step_id: stepId(), run_id: RUNS[8].run_id, step_number: 0, step_type: "llm_call",
    timestamp_start: ago(5), timestamp_end: ago(5), duration_ms: 2100,
    model: "gpt-4o",
    prompt: "Customer message: \"How do I reset my password? I forgot it and can't log in.\"",
    response: "I'll help the customer with password reset. Let me look up their account first and then provide the reset instructions.",
  },
  {
    step_id: stepId(), run_id: RUNS[8].run_id, step_number: 1, step_type: "tool_call",
    timestamp_start: ago(5), timestamp_end: ago(5), duration_ms: 450,
    tool_name: "crm_lookup",
    input: { args: [], kwargs: { query: "current customer context", fields: ["email", "plan", "last_login"] } },
    output: { result: { email: "j***@example.com", plan: "pro", last_login: "2024-03-10" } },
  },
  {
    step_id: stepId(), run_id: RUNS[8].run_id, step_number: 2, step_type: "tool_call",
    timestamp_start: ago(5), timestamp_end: ago(5), duration_ms: 820,
    tool_name: "send_password_reset",
    input: { args: [], kwargs: { email: "j***@example.com", method: "email" } },
    output: { result: { status: "sent", expires_in: "30 minutes" } },
  },
  {
    step_id: stepId(), run_id: RUNS[8].run_id, step_number: 3, step_type: "llm_call",
    timestamp_start: ago(5), timestamp_end: ago(5), duration_ms: 1900,
    model: "gpt-4o",
    prompt: "Password reset email sent to j***@example.com. Compose a helpful response to the customer.",
    response: "Hi! I've sent a password reset link to your email address on file (j***@example.com). The link will be valid for 30 minutes.\n\nHere's what to do:\n1. Check your inbox (and spam folder) for an email from us\n2. Click the reset link\n3. Choose a new password\n\nIf you don't receive the email within a few minutes, let me know and I can try an alternative method.",
  },
  {
    step_id: stepId(), run_id: RUNS[8].run_id, step_number: 4, step_type: "tool_call",
    timestamp_start: ago(4), timestamp_end: ago(4), duration_ms: 340,
    tool_name: "send_reply",
    input: { args: [], kwargs: { channel: "chat", message: "Password reset instructions sent" } },
    output: { result: { delivered: true, message_id: "msg-44821" } },
  },
  {
    step_id: stepId(), run_id: RUNS[8].run_id, step_number: 5, step_type: "agent",
    timestamp_start: ago(4), timestamp_end: ago(4), duration_ms: 120,
    agent_name: "support-agent", action: "mark_resolved",
    action_input: { ticket_id: "TICK-9921", resolution: "password_reset_sent" },
  },
]);

const RUN_DETAILS = {
  [RUNS[0].run_id]: RUN_DETAIL_RATE_LIMIT,
  [RUNS[1].run_id]: RUN_DETAIL_TIMEOUT,
  [RUNS[2].run_id]: RUN_DETAIL_OVERFLOW,
  [RUNS[7].run_id]: RUN_DETAIL_LOOP,
  [RUNS[8].run_id]: RUN_DETAIL_SUCCESS,
};

// For runs without custom steps, generate generic ones
function generateGenericSteps(summary) {
  const steps = [];
  const count = summary.step_count || 3;
  for (let i = 0; i < count; i++) {
    if (i % 3 === 0) {
      steps.push({
        step_id: stepId(), run_id: summary.run_id, step_number: i, step_type: "llm_call",
        timestamp_start: summary.start_time, timestamp_end: summary.start_time, duration_ms: durationMs(800, 5000),
        model: summary.model, prompt: `Step ${i} prompt for ${summary.name}`, response: `Response for step ${i}`,
      });
    } else if (i % 3 === 1) {
      steps.push({
        step_id: stepId(), run_id: summary.run_id, step_number: i, step_type: "tool_call",
        timestamp_start: summary.start_time, timestamp_end: summary.start_time, duration_ms: durationMs(200, 3000),
        tool_name: ["web_search", "database_query", "api_call", "file_read"][i % 4],
        input: { args: [], kwargs: { query: `query for step ${i}` } },
        output: { result: "ok" },
      });
    } else {
      steps.push({
        step_id: stepId(), run_id: summary.run_id, step_number: i, step_type: "retrieval",
        timestamp_start: summary.start_time, timestamp_end: summary.start_time, duration_ms: durationMs(100, 1500),
        query: `Retrieve context for step ${i}`,
        results: { documents: [{ content: "relevant document" }] },
      });
    }
  }
  if (summary.error) {
    steps.push({
      step_id: stepId(), run_id: summary.run_id, step_number: count, step_type: "error",
      timestamp_start: summary.end_time, timestamp_end: summary.end_time, duration_ms: 0,
      error: summary.error.split(':')[0],
      error_message: summary.error,
    });
  }
  return steps;
}

// ── Exported mock API functions ─────────────────────────────

function delay(ms = 150) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export async function fetchRuns(params = {}) {
  await delay();
  let filtered = [...RUNS];

  if (params.project) filtered = filtered.filter(r => r.project === params.project);
  if (params.status) filtered = filtered.filter(r => r.status === params.status);
  if (params.model) filtered = filtered.filter(r => r.model === params.model);
  if (params.has_error === 'true') filtered = filtered.filter(r => r.error != null);

  const sortBy = params.sort_by || 'start_time';
  const sortOrder = params.sort_order || 'desc';
  filtered.sort((a, b) => {
    let va = a[sortBy], vb = b[sortBy];
    if (typeof va === 'string') return sortOrder === 'desc' ? vb.localeCompare(va) : va.localeCompare(vb);
    return sortOrder === 'desc' ? (vb || 0) - (va || 0) : (va || 0) - (vb || 0);
  });

  const offset = parseInt(params.offset) || 0;
  const limit = parseInt(params.limit) || 50;
  return filtered.slice(offset, offset + limit);
}

export async function fetchRun(runId) {
  await delay(200);
  const summary = RUNS.find(r => r.run_id === runId);
  if (!summary) throw new Error(`Run ${runId} not found`);

  if (RUN_DETAILS[runId]) return RUN_DETAILS[runId];

  const steps = generateGenericSteps(summary);
  return makeRunDetail(summary, steps);
}

export async function fetchRunMetadata(runId) {
  await delay();
  const run = await fetchRun(runId);
  return run.metadata;
}

export async function fetchRunSteps(runId, params = {}) {
  await delay();
  const run = await fetchRun(runId);
  let steps = run.steps;
  if (params.step_type) steps = steps.filter(s => s.step_type === params.step_type);
  return steps;
}

export async function fetchRunCount(params = {}) {
  await delay(50);
  const runs = await fetchRuns(params);
  return { count: runs.length };
}

export async function deleteRun(runId) {
  await delay();
  return { deleted: true };
}

export async function searchRuns(query, params = {}) {
  await delay(200);
  const q = query.toLowerCase();
  return RUNS.filter(r =>
    (r.name && r.name.toLowerCase().includes(q)) ||
    (r.error && r.error.toLowerCase().includes(q)) ||
    (r.tags && r.tags.some(t => t.toLowerCase().includes(q))) ||
    (r.project && r.project.toLowerCase().includes(q))
  );
}

export async function fetchFailures(params = {}) {
  await delay();
  let failed = RUNS.filter(r => r.error != null);
  if (params.project) failed = failed.filter(r => r.project === params.project);
  if (params.failure_category) failed = failed.filter(r => r.failure_category === params.failure_category);
  const offset = parseInt(params.offset) || 0;
  const limit = parseInt(params.limit) || 50;
  return failed.slice(offset, offset + limit);
}

export async function fetchFailureStats(params = {}) {
  await delay(100);
  let failed = RUNS.filter(r => r.error != null);
  if (params.project) failed = failed.filter(r => r.project === params.project);
  const byCategory = {};
  failed.forEach(r => {
    const cat = r.failure_category || 'unknown';
    byCategory[cat] = (byCategory[cat] || 0) + 1;
  });
  return { total_failures: failed.length, by_category: byCategory };
}

export async function fetchStats(params = {}) {
  await delay(100);
  let runs = [...RUNS];
  if (params.project) runs = runs.filter(r => r.project === params.project);
  const completed = runs.filter(r => r.status === 'completed').length;
  const failed = runs.filter(r => r.status === 'failed').length;
  return {
    total_runs: runs.length,
    completed,
    failed,
    total_tokens: runs.reduce((s, r) => s + (r.total_tokens || 0), 0),
    total_cost_usd: runs.reduce((s, r) => s + (r.total_cost_usd || 0), 0),
    success_rate: runs.length > 0 ? completed / runs.length : 0,
  };
}

export async function fetchHealth() {
  await delay(50);
  return { status: 'ok' };
}
