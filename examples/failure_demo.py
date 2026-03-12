#!/usr/bin/env python3
"""ReAgent Failure Capture Demo

This script generates sample failed runs demonstrating various failure types
that can occur during AI agent execution. Use this to test failure viewing
and analysis capabilities.

Usage:
    python examples/failure_demo.py

    # Then view failures:
    reagent failures list
    reagent failures inspect <run_id> --traceback
    reagent export <run_id> -f html -o report.html
"""

from __future__ import annotations

import random
import sys
import traceback
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reagent.client.reagent import ReAgent
from reagent.schema.run import RunConfig


def generate_tool_timeout_failure(client: ReAgent) -> str:
    """Generate a run that fails due to tool execution timeout."""
    try:
        with client.trace(RunConfig(
            name="tool-timeout-demo",
            project="failure-demo",
            tags=["demo", "timeout", "tool-error"],
        )) as ctx:
            ctx.set_framework("demo-agent", "1.0")

            # Record successful LLM call
            ctx.record_llm_call(
                model="gpt-4",
                prompt="Search the web for recent AI news",
                response="I'll use the web_search tool to find recent AI news.",
                prompt_tokens=15,
                completion_tokens=20,
                duration_ms=850,
            )

            # Record tool call that times out
            ctx.record_tool_call(
                tool_name="web_search",
                kwargs={"query": "latest AI news 2024", "timeout": 30},
                error="Connection timeout after 30000ms",
                error_type="TimeoutError",
                duration_ms=30000,
            )

            # Record the error explicitly
            ctx.record_error(
                error_message="Tool 'web_search' timed out after 30 seconds",
                error_type="TimeoutError",
                error_traceback="""Traceback (most recent call last):
  File "agent.py", line 145, in execute_tool
    result = await asyncio.wait_for(tool.run(**kwargs), timeout=30)
  File "/usr/lib/python3.11/asyncio/tasks.py", line 479, in wait_for
    raise asyncio.TimeoutError()
asyncio.TimeoutError

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "agent.py", line 147, in execute_tool
    raise TimeoutError(f"Tool '{tool_name}' timed out after {timeout} seconds")
TimeoutError: Tool 'web_search' timed out after 30 seconds""",
                source_step_type="tool_call",
            )

            # Set failure category on the run
            ctx._metadata.failure_category = "tool_timeout"

            raise TimeoutError("Tool execution timed out")
    except TimeoutError:
        pass

    return str(ctx.run_id)


def generate_rate_limit_failure(client: ReAgent) -> str:
    """Generate a run that fails due to API rate limiting."""
    try:
        with client.trace(RunConfig(
            name="rate-limit-demo",
            project="failure-demo",
            tags=["demo", "rate-limit", "llm-error"],
        )) as ctx:
            ctx.set_framework("demo-agent", "1.0")

            # Record several successful calls to simulate hitting rate limit
            for i in range(3):
                ctx.record_llm_call(
                    model="gpt-4",
                    prompt=f"Process batch item {i+1}",
                    response=f"Processed item {i+1} successfully",
                    prompt_tokens=10,
                    completion_tokens=8,
                    cost_usd=0.002,
                    duration_ms=random.randint(400, 800),
                )

            # Record the failing LLM call
            ctx.record_llm_call(
                model="gpt-4",
                prompt="Process batch item 4",
                error="Rate limit exceeded. Please retry after 60 seconds.",
                error_type="RateLimitError",
                duration_ms=150,
            )

            ctx.record_error(
                error_message="OpenAI API rate limit exceeded: You have exceeded your rate limit of 10000 tokens per minute. Please retry after 60 seconds.",
                error_type="RateLimitError",
                error_traceback="""Traceback (most recent call last):
  File "openai_wrapper.py", line 89, in call_api
    response = await client.chat.completions.create(**params)
  File "openai/_client.py", line 1045, in create
    raise RateLimitError(message, response=response, body=body)
openai.RateLimitError: Error code: 429 - {'error': {'message': 'Rate limit exceeded', 'type': 'rate_limit_error', 'code': 'rate_limit_exceeded'}}""",
                source_step_type="llm_call",
            )

            ctx._metadata.failure_category = "rate_limit"

            raise Exception("RateLimitError: Rate limit exceeded")
    except Exception:
        pass

    return str(ctx.run_id)


def generate_context_overflow_failure(client: ReAgent) -> str:
    """Generate a run that fails due to context window overflow."""
    try:
        with client.trace(RunConfig(
            name="context-overflow-demo",
            project="failure-demo",
            tags=["demo", "context-overflow", "llm-error"],
        )) as ctx:
            ctx.set_framework("demo-agent", "1.0")

            # Simulate building up context
            ctx.record_llm_call(
                model="gpt-4",
                prompt="Analyze this document: " + "x" * 1000,
                response="I've analyzed the first part. Please continue with more context.",
                prompt_tokens=2500,
                completion_tokens=25,
                cost_usd=0.05,
                duration_ms=1200,
            )

            ctx.record_tool_call(
                tool_name="read_document",
                kwargs={"path": "/data/large_report.pdf"},
                result={"content": "..." + "A" * 5000 + "...", "pages": 150},
                duration_ms=500,
            )

            # Record the failing call
            ctx.record_llm_call(
                model="gpt-4",
                prompt="Continue analysis with full document context...",
                error="This model's maximum context length is 128000 tokens. Your messages resulted in 156847 tokens.",
                error_type="ContextLengthExceededError",
                duration_ms=50,
            )

            ctx.record_error(
                error_message="Context length exceeded: This model's maximum context length is 128000 tokens. Your messages resulted in 156847 tokens (152000 in the messages, 4847 in the functions). Please reduce the length of the messages or functions.",
                error_type="ContextLengthExceededError",
                error_traceback="""Traceback (most recent call last):
  File "agent.py", line 234, in process_with_context
    response = await llm.complete(messages=context.messages)
  File "openai_wrapper.py", line 89, in call_api
    response = await client.chat.completions.create(**params)
  File "openai/_client.py", line 1045, in create
    raise BadRequestError(message, response=response, body=body)
openai.BadRequestError: Error code: 400 - {'error': {'message': "This model's maximum context length is 128000 tokens.", 'type': 'invalid_request_error', 'code': 'context_length_exceeded'}}""",
                source_step_type="llm_call",
            )

            ctx._metadata.failure_category = "context_overflow"

            raise Exception("ContextLengthExceededError: Token limit exceeded")
    except Exception:
        pass

    return str(ctx.run_id)


def generate_tool_execution_error(client: ReAgent) -> str:
    """Generate a run that fails due to tool execution error."""
    try:
        with client.trace(RunConfig(
            name="tool-error-demo",
            project="failure-demo",
            tags=["demo", "tool-error", "exception"],
        )) as ctx:
            ctx.set_framework("demo-agent", "1.0")

            ctx.record_llm_call(
                model="gpt-4",
                prompt="Please fetch the user's account data",
                response="I'll retrieve the account data using the database query tool.",
                prompt_tokens=12,
                completion_tokens=18,
                duration_ms=650,
            )

            # Record the failing tool call
            ctx.record_tool_call(
                tool_name="database_query",
                kwargs={
                    "query": "SELECT * FROM users WHERE id = ?",
                    "params": ["user_123"],
                },
                error="Connection refused: Unable to connect to database server at localhost:5432",
                error_type="ConnectionError",
                duration_ms=5000,
            )

            ctx.record_error(
                error_message="Database connection failed: Connection refused to localhost:5432",
                error_type="ConnectionError",
                error_traceback="""Traceback (most recent call last):
  File "tools/database.py", line 45, in execute_query
    conn = await asyncpg.connect(self.connection_string)
  File "asyncpg/connection.py", line 567, in connect
    raise OSError(f"Connection refused: {self.host}:{self.port}")
OSError: Connection refused: localhost:5432

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "tools/database.py", line 48, in execute_query
    raise ConnectionError(f"Database connection failed: {e}")
ConnectionError: Database connection failed: Connection refused to localhost:5432""",
                source_step_type="tool_call",
            )

            ctx._metadata.failure_category = "tool_error"

            raise ConnectionError("Database connection failed")
    except ConnectionError:
        pass

    return str(ctx.run_id)


def generate_validation_error(client: ReAgent) -> str:
    """Generate a run that fails due to invalid arguments/validation."""
    try:
        with client.trace(RunConfig(
            name="validation-error-demo",
            project="failure-demo",
            tags=["demo", "validation", "input-error"],
        )) as ctx:
            ctx.set_framework("demo-agent", "1.0")

            ctx.record_llm_call(
                model="gpt-4",
                prompt="Send an email to the user",
                response='I\'ll send an email using the send_email tool with parameters: {"to": "invalid-email", "subject": "Test", "body": "Hello"}',
                prompt_tokens=10,
                completion_tokens=35,
                duration_ms=720,
            )

            ctx.record_tool_call(
                tool_name="send_email",
                kwargs={
                    "to": "invalid-email",  # Invalid email format
                    "subject": "Test Email",
                    "body": "Hello, this is a test.",
                },
                error="Validation error: 'to' must be a valid email address",
                error_type="ValidationError",
                duration_ms=10,
            )

            ctx.record_error(
                error_message="Tool argument validation failed: 'to' field value 'invalid-email' is not a valid email address",
                error_type="ValidationError",
                error_traceback="""Traceback (most recent call last):
  File "tools/email.py", line 28, in send_email
    validated = EmailSchema.model_validate(kwargs)
  File "pydantic/main.py", line 568, in model_validate
    raise ValidationError.from_exception_data(cls.__name__, errors)
pydantic.ValidationError: 1 validation error for EmailSchema
to
  value is not a valid email address: An email address must have an @-sign. [type=value_error, input_value='invalid-email', input_type=str]""",
                source_step_type="tool_call",
            )

            ctx._metadata.failure_category = "validation_error"

            raise ValueError("ValidationError: Invalid email address")
    except ValueError:
        pass

    return str(ctx.run_id)


def generate_chain_propagation_error(client: ReAgent) -> str:
    """Generate a run where an error propagates through a chain."""
    try:
        with client.trace(RunConfig(
            name="chain-error-demo",
            project="failure-demo",
            tags=["demo", "chain", "propagation"],
        )) as ctx:
            ctx.set_framework("langchain", "0.1.0")

            # Start a chain
            chain = ctx.start_chain(
                chain_name="ResearchChain",
                chain_type="sequential",
                input={"topic": "AI Safety Research"},
            )

            with ctx.nest(chain.step_id):
                # First step succeeds
                ctx.record_llm_call(
                    model="gpt-4",
                    prompt="Generate research queries for: AI Safety Research",
                    response="1. Current AI alignment techniques\n2. RLHF limitations\n3. Interpretability methods",
                    prompt_tokens=15,
                    completion_tokens=25,
                    duration_ms=800,
                )

                # Second step - tool call succeeds
                ctx.record_tool_call(
                    tool_name="web_search",
                    kwargs={"query": "Current AI alignment techniques 2024"},
                    result={"results": [{"title": "AI Alignment Survey", "url": "..."}]},
                    duration_ms=2500,
                )

                # Third step - summarization fails
                ctx.record_llm_call(
                    model="gpt-4",
                    prompt="Summarize the research findings...",
                    error="Service temporarily unavailable",
                    error_type="ServiceUnavailableError",
                    duration_ms=100,
                )

            # End chain with error
            ctx.end_chain(
                chain,
                error="Chain execution failed at step 3: ServiceUnavailableError",
            )

            ctx.record_error(
                error_message="Chain 'ResearchChain' failed: LLM service temporarily unavailable during summarization step",
                error_type="ChainExecutionError",
                error_traceback="""Traceback (most recent call last):
  File "chains/sequential.py", line 89, in execute
    result = await step.run(context)
  File "chains/llm_step.py", line 45, in run
    response = await self.llm.complete(prompt)
  File "openai_wrapper.py", line 92, in complete
    raise ServiceUnavailableError("Service temporarily unavailable")
ServiceUnavailableError: Service temporarily unavailable

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "chains/sequential.py", line 95, in execute
    raise ChainExecutionError(f"Chain '{self.name}' failed at step {i}: {e}")
ChainExecutionError: Chain 'ResearchChain' failed at step 3: ServiceUnavailableError""",
                source_step_type="chain",
            )

            ctx._metadata.failure_category = "chain_error"

            raise Exception("ChainExecutionError: Chain failed")
    except Exception:
        pass

    return str(ctx.run_id)


def generate_authentication_error(client: ReAgent) -> str:
    """Generate a run that fails due to authentication issues."""
    try:
        with client.trace(RunConfig(
            name="auth-error-demo",
            project="failure-demo",
            tags=["demo", "authentication", "api-error"],
        )) as ctx:
            ctx.set_framework("demo-agent", "1.0")

            ctx.record_llm_call(
                model="gpt-4",
                prompt="Fetch data from the external API",
                response="I'll call the external API to fetch the requested data.",
                prompt_tokens=12,
                completion_tokens=15,
                duration_ms=600,
            )

            ctx.record_tool_call(
                tool_name="external_api",
                kwargs={"endpoint": "/v1/data", "method": "GET"},
                error="401 Unauthorized: Invalid or expired API key",
                error_type="AuthenticationError",
                duration_ms=200,
            )

            ctx.record_error(
                error_message="API authentication failed: The provided API key is invalid or has expired",
                error_type="AuthenticationError",
                error_traceback="""Traceback (most recent call last):
  File "tools/api_client.py", line 67, in make_request
    response = await self.session.request(method, url, headers=headers)
  File "aiohttp/client.py", line 536, in _request
    resp = await self._request(method, url, **kwargs)
aiohttp.ClientResponseError: 401, message='Unauthorized'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "tools/api_client.py", line 72, in make_request
    raise AuthenticationError(f"API authentication failed: {response.status}")
AuthenticationError: API authentication failed: The provided API key is invalid or has expired""",
                source_step_type="tool_call",
            )

            ctx._metadata.failure_category = "authentication"

            raise Exception("AuthenticationError: Invalid API key")
    except Exception:
        pass

    return str(ctx.run_id)


def main():
    """Generate all demo failure runs."""
    print("ReAgent Failure Capture Demo")
    print("=" * 40)
    print()

    # Initialize client with SQLite storage in demo_traces directory
    demo_path = Path(__file__).parent.parent / ".reagent" / "demo_traces"
    demo_path.mkdir(parents=True, exist_ok=True)

    client = ReAgent(storage_path=str(demo_path))

    # Generate all failure types
    demos = [
        ("Tool Timeout", generate_tool_timeout_failure),
        ("Rate Limit", generate_rate_limit_failure),
        ("Context Overflow", generate_context_overflow_failure),
        ("Tool Error", generate_tool_execution_error),
        ("Validation Error", generate_validation_error),
        ("Chain Propagation", generate_chain_propagation_error),
        ("Authentication Error", generate_authentication_error),
    ]

    generated_ids = []

    for name, generator in demos:
        try:
            run_id = generator(client)
            generated_ids.append((name, run_id))
            print(f"[OK] {name}: {run_id[:8]}")
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            traceback.print_exc()

    print()
    print("=" * 40)
    print(f"Generated {len(generated_ids)} demo failure runs")
    print()
    print("View failures with:")
    print("  reagent failures list --project failure-demo")
    print("  reagent failures inspect <run_id> --traceback")
    print("  reagent failures stats --project failure-demo")
    print()
    print("Export to HTML:")
    print(f"  reagent export {generated_ids[0][1][:8]} -f html -o report.html")

    client.close()


if __name__ == "__main__":
    main()
