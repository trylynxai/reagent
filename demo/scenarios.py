#!/usr/bin/env python3
"""ReAgent Demo Scenarios — seeds the trace DB with runs exercising every feature.

Generates ~11 runs covering successes, all failure types, PII, alerts, and nesting.
Always uses mock data — no API key needed.

Usage:
    python demo/scenarios.py

    # Then explore:
    reagent list --project demo
    reagent failures stats --project demo
    reagent inspect <run_id>
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reagent.client.reagent import ReAgent
from reagent.schema.run import RunConfig
from reagent.alerts.engine import AlertEngine
from reagent.alerts.rules import CostThresholdRule
from reagent.alerts.delivery import CallbackDelivery


# ---------------------------------------------------------------------------
# Alert tracking
# ---------------------------------------------------------------------------

triggered_alerts: list[str] = []


def alert_callback(result):
    """Capture alert results for display."""
    msg = f"  ALERT [{result.severity}] {result.rule_name}: {result.message}"
    triggered_alerts.append(msg)
    print(msg)


# ---------------------------------------------------------------------------
# Scenario 1: Successful research with tools, reasoning, chains, tags
# ---------------------------------------------------------------------------

def scenario_successful_research(client: ReAgent) -> str:
    """Multi-step research: 3 LLM calls, 2 tools, nested chain, agent actions."""
    with client.trace(RunConfig(
        name="research: Python history",
        project="demo",
        tags=["demo", "research", "success", "multi-step"],
        input={"question": "What is the history of Python?"},
        metadata={"agent_type": "research_assistant", "llm_mode": "mock"},
    )) as ctx:
        ctx.set_framework("demo-agent", "1.0")
        ctx.set_model("gpt-4o")
        ctx.add_tag("featured")

        # Start research chain
        chain = ctx.start_chain(
            chain_name="ResearchPipeline",
            chain_type="sequential",
            input={"question": "What is the history of Python?"},
        )

        with ctx.nest(chain.step_id):
            # Think
            ctx.record_agent_action(
                action="think",
                thought="I need to search for information about Python's history.",
                agent_name="ResearchAgent",
                agent_type="research_assistant",
            )

            # LLM call 1: decide to search
            ctx.record_llm_call(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a research assistant."},
                    {"role": "user", "content": "What is the history of Python?"},
                ],
                response="Let me search for information about Python's history.\nTOOL:web_search(python programming language history)",
                prompt_tokens=45,
                completion_tokens=22,
                cost_usd=0.002,
                duration_ms=850,
                provider="openai",
                temperature=0.7,
            )

            # Tool call 1: web search
            ctx.record_tool_call(
                tool_name="web_search",
                kwargs={"query": "python programming language history"},
                result={
                    "results": [
                        {"title": "History of Python", "snippet": "Python was created by Guido van Rossum in 1991."},
                        {"title": "Python Timeline", "snippet": "Python 2.0 (2000), Python 3.0 (2008)."},
                    ]
                },
                duration_ms=320,
                tool_description="Search the web for information",
            )

            # Think again
            ctx.record_agent_action(
                action="think",
                thought="I have search results. Let me also read the notes file for additional context.",
                agent_name="ResearchAgent",
                agent_type="research_assistant",
            )

            # LLM call 2: decide to read file
            ctx.record_llm_call(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a research assistant."},
                    {"role": "user", "content": "What is the history of Python?"},
                    {"role": "assistant", "content": "TOOL:web_search(python programming language history)"},
                    {"role": "user", "content": "Tool result: Python was created by Guido van Rossum..."},
                ],
                response="Let me check for any local notes.\nTOOL:file_reader(notes.txt)",
                prompt_tokens=120,
                completion_tokens=18,
                cost_usd=0.004,
                duration_ms=720,
                provider="openai",
            )

            # Tool call 2: file reader
            ctx.record_tool_call(
                tool_name="file_reader",
                kwargs={"path": "notes.txt"},
                result={"path": "notes.txt", "content": "Meeting notes: Discussed Q4 roadmap."},
                duration_ms=5,
                tool_description="Read contents of a file",
            )

            # LLM call 3: final answer
            ctx.record_llm_call(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a research assistant."},
                    {"role": "user", "content": "What is the history of Python?"},
                    {"role": "assistant", "content": "..."},
                    {"role": "user", "content": "Tool results..."},
                ],
                response="ANSWER:Python was created by Guido van Rossum and first released in 1991. Key milestones include Python 2.0 in 2000 and Python 3.0 in 2008.",
                prompt_tokens=200,
                completion_tokens=40,
                cost_usd=0.006,
                duration_ms=680,
                provider="openai",
            )

        ctx.end_chain(chain, output={"answer": "Python was created by Guido van Rossum..."})

        ctx.record_agent_finish(
            final_answer="Python was created by Guido van Rossum and first released in 1991.",
            thought="I have enough information to answer.",
            agent_name="ResearchAgent",
        )

        ctx.set_output({"answer": "Python was created by Guido van Rossum and first released in 1991."})
        ctx.set_metadata("total_tools_used", 2)
        ctx.set_metadata("total_llm_calls", 3)

    return str(ctx.run_id)


# ---------------------------------------------------------------------------
# Scenario 2: Successful weather query (different model, for diff comparison)
# ---------------------------------------------------------------------------

def scenario_successful_weather(client: ReAgent) -> str:
    """Simple weather query using gpt-4o-mini — enables reagent diff comparison."""
    with client.trace(RunConfig(
        name="research: Paris weather",
        project="demo",
        tags=["demo", "weather", "success"],
        input={"question": "What is the weather in Paris?"},
    )) as ctx:
        ctx.set_framework("demo-agent", "1.0")
        ctx.set_model("gpt-4o-mini")

        ctx.record_agent_action(
            action="think",
            thought="User wants weather info. I'll use the weather tool.",
            agent_name="ResearchAgent",
            agent_type="research_assistant",
        )

        ctx.record_llm_call(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "What is the weather in Paris?"}],
            response="TOOL:weather(Paris)",
            prompt_tokens=20,
            completion_tokens=8,
            cost_usd=0.0003,
            duration_ms=450,
            provider="openai",
        )

        ctx.record_tool_call(
            tool_name="weather",
            kwargs={"location": "Paris"},
            result={"location": "Paris, FR", "temp_f": 65, "condition": "Sunny", "humidity": 50},
            duration_ms=15,
        )

        ctx.record_llm_call(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "What is the weather in Paris?"}, {"role": "assistant", "content": "TOOL:weather(Paris)"}, {"role": "user", "content": "Tool result: 65°F, Sunny"}],
            response="ANSWER:The weather in Paris is currently 65°F and Sunny with 50% humidity.",
            prompt_tokens=55,
            completion_tokens=20,
            cost_usd=0.0005,
            duration_ms=380,
            provider="openai",
        )

        ctx.record_agent_finish(
            final_answer="The weather in Paris is currently 65°F and Sunny.",
            agent_name="ResearchAgent",
        )
        ctx.set_output({"answer": "The weather in Paris is currently 65°F and Sunny."})

    return str(ctx.run_id)


# ---------------------------------------------------------------------------
# Scenario 3: Tool timeout failure
# ---------------------------------------------------------------------------

def scenario_tool_timeout(client: ReAgent) -> str:
    """TOOL_TIMEOUT — web_search times out."""
    try:
        with client.trace(RunConfig(
            name="research: AI news (timeout)",
            project="demo",
            tags=["demo", "failure", "timeout"],
            input={"question": "Latest AI news"},
        )) as ctx:
            ctx.set_framework("demo-agent", "1.0")
            ctx.set_model("gpt-4o")

            ctx.record_llm_call(
                model="gpt-4o",
                prompt="Find the latest AI news",
                response="I'll search for the latest AI news.\nTOOL:web_search(latest AI news 2024)",
                prompt_tokens=15,
                completion_tokens=20,
                duration_ms=800,
            )

            ctx.record_tool_call(
                tool_name="web_search",
                kwargs={"query": "latest AI news 2024", "timeout": 30},
                error="Connection timeout after 30000ms",
                error_type="TimeoutError",
                duration_ms=30000,
            )

            ctx.record_error(
                error_message="Tool 'web_search' timed out after 30 seconds",
                error_type="TimeoutError",
                error_traceback="""Traceback (most recent call last):
  File "agent.py", line 145, in execute_tool
    result = await asyncio.wait_for(tool.run(**kwargs), timeout=30)
  File "/usr/lib/python3.11/asyncio/tasks.py", line 479, in wait_for
    raise asyncio.TimeoutError()
TimeoutError: Tool 'web_search' timed out after 30 seconds""",
                source_step_type="tool_call",
            )

            ctx._metadata.failure_category = "tool_timeout"
            raise TimeoutError("Tool execution timed out")
    except TimeoutError:
        pass

    return str(ctx.run_id)


# ---------------------------------------------------------------------------
# Scenario 4: Rate limit on LLM call
# ---------------------------------------------------------------------------

def scenario_rate_limit(client: ReAgent) -> str:
    """RATE_LIMIT — 429 on LLM call after successful calls."""
    try:
        with client.trace(RunConfig(
            name="batch processing (rate limited)",
            project="demo",
            tags=["demo", "failure", "rate-limit"],
            input={"task": "batch processing"},
        )) as ctx:
            ctx.set_framework("demo-agent", "1.0")
            ctx.set_model("gpt-4o")

            for i in range(3):
                ctx.record_llm_call(
                    model="gpt-4o",
                    prompt=f"Process batch item {i + 1}",
                    response=f"Processed item {i + 1} successfully",
                    prompt_tokens=10,
                    completion_tokens=8,
                    cost_usd=0.002,
                    duration_ms=500 + i * 100,
                )

            ctx.record_llm_call(
                model="gpt-4o",
                prompt="Process batch item 4",
                error="Rate limit exceeded. Please retry after 60 seconds.",
                error_type="RateLimitError",
                duration_ms=150,
            )

            ctx.record_error(
                error_message="OpenAI API rate limit exceeded (429): retry after 60 seconds",
                error_type="RateLimitError",
                error_traceback="""Traceback (most recent call last):
  File "openai_wrapper.py", line 89, in call_api
    response = await client.chat.completions.create(**params)
openai.RateLimitError: Error code: 429 - Rate limit exceeded""",
                source_step_type="llm_call",
            )

            ctx._metadata.failure_category = "rate_limit"
            raise Exception("RateLimitError: Rate limit exceeded")
    except Exception:
        pass

    return str(ctx.run_id)


# ---------------------------------------------------------------------------
# Scenario 5: Connection error on tool
# ---------------------------------------------------------------------------

def scenario_connection_error(client: ReAgent) -> str:
    """CONNECTION_ERROR — tool network failure."""
    try:
        with client.trace(RunConfig(
            name="research: stock prices (connection error)",
            project="demo",
            tags=["demo", "failure", "connection"],
            input={"question": "Current stock prices"},
        )) as ctx:
            ctx.set_framework("demo-agent", "1.0")
            ctx.set_model("gpt-4o")

            ctx.record_llm_call(
                model="gpt-4o",
                prompt="Get current stock prices",
                response="TOOL:web_search(current stock prices)",
                prompt_tokens=12,
                completion_tokens=10,
                duration_ms=600,
            )

            ctx.record_tool_call(
                tool_name="web_search",
                kwargs={"query": "current stock prices"},
                error="ConnectionError: Failed to resolve hostname api.search.com",
                error_type="ConnectionError",
                duration_ms=5000,
            )

            ctx.record_error(
                error_message="Network connection failed: unable to resolve api.search.com",
                error_type="ConnectionError",
                error_traceback="""Traceback (most recent call last):
  File "tools/web.py", line 34, in search
    response = requests.get(url, timeout=10)
  File "requests/api.py", line 73, in get
    return request("GET", url, **kwargs)
ConnectionError: Failed to resolve hostname api.search.com""",
                source_step_type="tool_call",
            )

            ctx._metadata.failure_category = "connection_error"
            raise ConnectionError("Network failure")
    except ConnectionError:
        pass

    return str(ctx.run_id)


# ---------------------------------------------------------------------------
# Scenario 6: Validation error on tool input
# ---------------------------------------------------------------------------

def scenario_validation_error(client: ReAgent) -> str:
    """VALIDATION_ERROR — bad tool input."""
    try:
        with client.trace(RunConfig(
            name="research: calculation (validation error)",
            project="demo",
            tags=["demo", "failure", "validation"],
            input={"question": "Calculate something"},
        )) as ctx:
            ctx.set_framework("demo-agent", "1.0")
            ctx.set_model("gpt-4o")

            ctx.record_llm_call(
                model="gpt-4o",
                prompt="Calculate import os; os.system('rm -rf /')",
                response="TOOL:calculator(import os; os.system('rm -rf /'))",
                prompt_tokens=20,
                completion_tokens=15,
                duration_ms=550,
            )

            ctx.record_tool_call(
                tool_name="calculator",
                kwargs={"expression": "import os; os.system('rm -rf /')"},
                error="ValueError: Invalid expression — only mathematical expressions allowed",
                error_type="ValueError",
                duration_ms=2,
            )

            ctx.record_error(
                error_message="Tool argument validation failed: expression contains disallowed operations",
                error_type="ValueError",
                error_traceback="""Traceback (most recent call last):
  File "tools.py", line 38, in calculator
    result = eval(expression, allowed)
  File "<string>", line 1
    import os; os.system('rm -rf /')
    ^^^^^^
SyntaxError: invalid syntax""",
                source_step_type="tool_call",
            )

            ctx._metadata.failure_category = "validation_error"
            raise ValueError("Invalid tool input")
    except ValueError:
        pass

    return str(ctx.run_id)


# ---------------------------------------------------------------------------
# Scenario 7: Reasoning loop — same tool called 5x with identical args
# ---------------------------------------------------------------------------

def scenario_reasoning_loop(client: ReAgent) -> str:
    """REASONING_LOOP — agent stuck calling same tool repeatedly."""
    try:
        with client.trace(RunConfig(
            name="research: stuck in loop",
            project="demo",
            tags=["demo", "failure", "reasoning-loop"],
            input={"question": "Find the answer to everything"},
        )) as ctx:
            ctx.set_framework("demo-agent", "1.0")
            ctx.set_model("gpt-4o")

            for i in range(5):
                ctx.record_llm_call(
                    model="gpt-4o",
                    prompt="Find the answer to everything",
                    response="TOOL:web_search(answer to everything)",
                    prompt_tokens=15 + i * 10,
                    completion_tokens=8,
                    cost_usd=0.001,
                    duration_ms=500,
                )

                ctx.record_tool_call(
                    tool_name="web_search",
                    kwargs={"query": "answer to everything"},
                    result={"results": [{"title": "42", "snippet": "The answer is 42."}]},
                    duration_ms=300,
                )

            ctx.record_error(
                error_message="Reasoning loop detected: tool 'web_search' called 5 times with identical arguments",
                error_type="ReasoningLoopError",
                error_traceback="""Traceback (most recent call last):
  File "agent.py", line 98, in run
    self._check_for_loops(history)
  File "agent.py", line 112, in _check_for_loops
    raise ReasoningLoopError(f"Tool '{tool}' called {count} times with identical args")
ReasoningLoopError: Reasoning loop detected""",
                source_step_type="agent_action",
            )

            ctx._metadata.failure_category = "reasoning_loop"
            raise Exception("ReasoningLoopError")
    except Exception:
        pass

    return str(ctx.run_id)


# ---------------------------------------------------------------------------
# Scenario 8: Authentication error
# ---------------------------------------------------------------------------

def scenario_auth_error(client: ReAgent) -> str:
    """AUTHENTICATION — invalid API key."""
    try:
        with client.trace(RunConfig(
            name="research: with bad API key",
            project="demo",
            tags=["demo", "failure", "auth"],
            input={"question": "Test query"},
        )) as ctx:
            ctx.set_framework("demo-agent", "1.0")
            ctx.set_model("gpt-4o")

            ctx.record_llm_call(
                model="gpt-4o",
                prompt="Test query",
                error="401 Unauthorized: Invalid API key provided",
                error_type="AuthenticationError",
                duration_ms=120,
            )

            ctx.record_error(
                error_message="API authentication failed: Invalid API key 'sk-...abc123'",
                error_type="AuthenticationError",
                error_traceback="""Traceback (most recent call last):
  File "openai_wrapper.py", line 89, in call_api
    response = await client.chat.completions.create(**params)
openai.AuthenticationError: Error code: 401 - Invalid API key provided""",
                source_step_type="llm_call",
            )

            ctx._metadata.failure_category = "authentication"
            raise Exception("AuthenticationError: Invalid API key")
    except Exception:
        pass

    return str(ctx.run_id)


# ---------------------------------------------------------------------------
# Scenario 9: PII exposure in prompts
# ---------------------------------------------------------------------------

def scenario_pii_exposure(client: ReAgent) -> str:
    """PII in prompts: email, phone, API key."""
    with client.trace(RunConfig(
        name="research: user data lookup (PII)",
        project="demo",
        tags=["demo", "pii", "sensitive"],
        input={"question": "Look up information for john.doe@example.com"},
    )) as ctx:
        ctx.set_framework("demo-agent", "1.0")
        ctx.set_model("gpt-4o")

        # LLM call with PII in prompt
        ctx.record_llm_call(
            model="gpt-4o",
            prompt="Look up the account for john.doe@example.com. Their phone is 555-123-4567. Use API key sk-abc123secretkey456 to authenticate.",
            response="I found the account for john.doe@example.com. Phone: 555-123-4567. Account is active.",
            prompt_tokens=45,
            completion_tokens=25,
            cost_usd=0.003,
            duration_ms=900,
            provider="openai",
        )

        # Tool call with PII
        ctx.record_tool_call(
            tool_name="web_search",
            kwargs={"query": "john.doe@example.com account info"},
            result={"results": [{"title": "Account Found", "snippet": "Email: john.doe@example.com, Phone: 555-123-4567"}]},
            duration_ms=250,
        )

        ctx.record_agent_finish(
            final_answer="Account found for john.doe@example.com. Phone: 555-123-4567. Status: active.",
            agent_name="ResearchAgent",
        )
        ctx.set_output({"answer": "Account found", "email": "john.doe@example.com"})

    return str(ctx.run_id)


# ---------------------------------------------------------------------------
# Scenario 10: Expensive run triggering cost alert
# ---------------------------------------------------------------------------

def scenario_expensive_run(client: ReAgent) -> str:
    """High cost ($0.15) triggers CostThresholdRule($0.05)."""
    with client.trace(RunConfig(
        name="research: comprehensive analysis (expensive)",
        project="demo",
        tags=["demo", "expensive", "alert"],
        input={"question": "Comprehensive market analysis"},
    )) as ctx:
        ctx.set_framework("demo-agent", "1.0")
        ctx.set_model("gpt-4o")

        # Many expensive LLM calls
        for i in range(5):
            ctx.record_llm_call(
                model="gpt-4o",
                prompt=f"Analyze market segment {i + 1} in detail with all available data",
                response=f"Detailed analysis of segment {i + 1}: Market size is $X billion..." + "x" * 200,
                prompt_tokens=500 + i * 100,
                completion_tokens=800 + i * 50,
                cost_usd=0.03,
                duration_ms=2000 + i * 500,
                provider="openai",
            )

            ctx.record_tool_call(
                tool_name="web_search",
                kwargs={"query": f"market segment {i + 1} analysis 2024"},
                result={"results": [{"title": f"Segment {i + 1}", "snippet": "Market data..."}]},
                duration_ms=400,
            )

        ctx.record_agent_finish(
            final_answer="Comprehensive market analysis complete across 5 segments.",
            agent_name="ResearchAgent",
        )
        ctx.set_output({"answer": "Market analysis complete", "segments_analyzed": 5})

    return str(ctx.run_id)


# ---------------------------------------------------------------------------
# Scenario 11: Nested chains (3-level nesting)
# ---------------------------------------------------------------------------

def scenario_nested_chains(client: ReAgent) -> str:
    """3-level nesting with start_chain/end_chain."""
    with client.trace(RunConfig(
        name="research: multi-stage pipeline",
        project="demo",
        tags=["demo", "nesting", "chains", "pipeline"],
        input={"question": "Full research pipeline test"},
    )) as ctx:
        ctx.set_framework("demo-agent", "1.0")
        ctx.set_model("gpt-4o")

        # Level 1: Outer pipeline
        outer = ctx.start_chain(
            chain_name="OuterPipeline",
            chain_type="sequential",
            input={"stage": "full_pipeline"},
        )

        with ctx.nest(outer.step_id):
            ctx.record_agent_action(
                action="plan",
                thought="Starting 3-stage research pipeline: gather, analyze, synthesize.",
                agent_name="ResearchAgent",
            )

            # Level 2: Gather chain
            gather = ctx.start_chain(
                chain_name="GatherChain",
                chain_type="parallel",
                input={"stage": "gather"},
            )

            with ctx.nest(gather.step_id):
                ctx.record_llm_call(
                    model="gpt-4o",
                    prompt="Generate search queries for research",
                    response="Query 1: topic overview, Query 2: recent developments",
                    prompt_tokens=20,
                    completion_tokens=15,
                    cost_usd=0.001,
                    duration_ms=400,
                )

                ctx.record_tool_call(
                    tool_name="web_search",
                    kwargs={"query": "topic overview"},
                    result={"results": [{"title": "Overview", "snippet": "Topic overview data"}]},
                    duration_ms=200,
                )

                ctx.record_tool_call(
                    tool_name="web_search",
                    kwargs={"query": "recent developments"},
                    result={"results": [{"title": "Developments", "snippet": "Recent data"}]},
                    duration_ms=180,
                )

            ctx.end_chain(gather, output={"queries_run": 2, "results_found": 2})

            # Level 2: Analyze chain
            analyze = ctx.start_chain(
                chain_name="AnalyzeChain",
                chain_type="sequential",
                input={"stage": "analyze"},
            )

            with ctx.nest(analyze.step_id):
                # Level 3: Sub-analysis
                sub = ctx.start_chain(
                    chain_name="SubAnalysis",
                    chain_type="map_reduce",
                    input={"stage": "sub_analyze"},
                )

                with ctx.nest(sub.step_id):
                    ctx.record_llm_call(
                        model="gpt-4o",
                        prompt="Analyze gathered data for patterns",
                        response="Pattern analysis: found 3 key trends...",
                        prompt_tokens=150,
                        completion_tokens=60,
                        cost_usd=0.005,
                        duration_ms=1200,
                    )

                ctx.end_chain(sub, output={"patterns_found": 3})

                ctx.record_llm_call(
                    model="gpt-4o",
                    prompt="Synthesize analysis results",
                    response="Synthesis: The three key trends indicate...",
                    prompt_tokens=100,
                    completion_tokens=80,
                    cost_usd=0.004,
                    duration_ms=900,
                )

            ctx.end_chain(analyze, output={"analysis_complete": True})

        ctx.end_chain(outer, output={"pipeline_complete": True, "stages": 3})

        ctx.record_agent_finish(
            final_answer="Pipeline complete: gathered data, analyzed patterns, synthesized results.",
            agent_name="ResearchAgent",
        )
        ctx.set_output({"answer": "Pipeline complete", "stages": 3})

    return str(ctx.run_id)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("ReAgent Demo Scenarios")
    print("=" * 60)
    print()

    # Initialize client
    demo_path = Path(__file__).parent.parent / ".reagent" / "demo_traces"
    demo_path.mkdir(parents=True, exist_ok=True)
    client = ReAgent(storage_path=str(demo_path))

    # Set up alert engine
    engine = AlertEngine(
        rules=[
            CostThresholdRule(
                name="high_cost_alert",
                max_cost_usd=0.05,
            ),
        ],
        delivery_backends=[
            CallbackDelivery(callback=alert_callback),
        ],
        storage=client.storage,
    )
    client.set_alert_engine(engine)

    # Run all scenarios
    scenarios = [
        ("1. Successful Research", scenario_successful_research, "3 LLM calls, 2 tools, chain, tags"),
        ("2. Successful Weather", scenario_successful_weather, "gpt-4o-mini, enables diff"),
        ("3. Tool Timeout", scenario_tool_timeout, "TOOL_TIMEOUT failure"),
        ("4. Rate Limit", scenario_rate_limit, "RATE_LIMIT failure (429)"),
        ("5. Connection Error", scenario_connection_error, "CONNECTION_ERROR failure"),
        ("6. Validation Error", scenario_validation_error, "VALIDATION_ERROR failure"),
        ("7. Reasoning Loop", scenario_reasoning_loop, "REASONING_LOOP failure"),
        ("8. Auth Error", scenario_auth_error, "AUTHENTICATION failure"),
        ("9. PII Exposure", scenario_pii_exposure, "PII in prompts"),
        ("10. Expensive Run", scenario_expensive_run, "Cost alert trigger"),
        ("11. Nested Chains", scenario_nested_chains, "3-level nesting"),
    ]

    results = []

    for name, fn, description in scenarios:
        try:
            run_id = fn(client)
            short_id = run_id[:8]
            results.append((name, short_id, "OK", description))
            print(f"  [OK] {name}: {short_id}  ({description})")
        except Exception as e:
            results.append((name, "N/A", "FAIL", str(e)))
            print(f"  [FAIL] {name}: {e}")

    client.close()

    # Summary table
    print()
    print("=" * 60)
    print(f"Generated {sum(1 for r in results if r[2] == 'OK')}/{len(results)} scenarios")
    print()

    if triggered_alerts:
        print("Alerts triggered:")
        for a in triggered_alerts:
            print(a)
        print()

    print("Run IDs:")
    print(f"  {'Scenario':<30} {'ID':<10} {'Status':<6} Description")
    print(f"  {'-'*30} {'-'*10} {'-'*6} {'-'*30}")
    for name, rid, status, desc in results:
        print(f"  {name:<30} {rid:<10} {status:<6} {desc}")

    print()
    print("Explore with:")
    print("  reagent list --project demo")
    print("  reagent failures stats --project demo")
    print("  reagent inspect <run_id>")
    print("  reagent search \"status:failed\" --project demo")
    if len(results) >= 2 and results[0][2] == "OK" and results[1][2] == "OK":
        print(f"  reagent diff {results[0][1]} {results[1][1]}")


if __name__ == "__main__":
    main()
