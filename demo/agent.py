#!/usr/bin/env python3
"""ReAgent Demo Agent — a real research assistant powered by Gemini.

A working AI agent that reasons, calls tools, and answers questions,
fully instrumented with ReAgent for observability.

Usage:
    # Real mode (default) — needs GEMINI_API_KEY
    python demo/agent.py "What is the square root of 144?"
    python demo/agent.py "What's the weather in Tokyo?"
    python demo/agent.py "Read the file pyproject.toml"

    # Mock mode — no API key, scripted responses for testing
    python demo/agent.py "What is 2+2?" --mock
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reagent.client.reagent import ReAgent
from reagent.schema.run import RunConfig

from tools import TOOLS

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a research assistant with access to tools. Think step by step.

Available tools:
{tool_list}

To use a tool, respond with EXACTLY this format (one per message):
TOOL: tool_name("argument")

To give your final answer:
ANSWER: your complete answer here

Rules:
- Use tools when they'd help answer the question.
- You can use multiple tools across multiple turns.
- After getting tool results, either use another tool or give your ANSWER.
- Always end with ANSWER: when you're ready.
- For calculator, pass the raw expression like: TOOL: calculator("2+2")
- For web_search, pass the query: TOOL: web_search("python history")
- For weather, pass the city: TOOL: weather("Tokyo")
- For file_reader, pass the path: TOOL: file_reader("pyproject.toml")
"""

TOOL_PATTERN = re.compile(r'TOOL:\s*(\w+)\(\s*"(.+?)"\s*\)', re.DOTALL)
ANSWER_PATTERN = re.compile(r"ANSWER:\s*(.*)", re.DOTALL)

# ---------------------------------------------------------------------------
# Mock LLM (for --mock mode, no API key)
# ---------------------------------------------------------------------------

MOCK_SCRIPTS: dict[str, list[str]] = {
    r"2\+2|math|calculat|arithmetic": [
        'Let me calculate that.\nTOOL: calculator("2+2")',
        "ANSWER: The result of 2+2 is 4.",
    ],
    "weather|temperature|forecast": [
        'I\'ll check the weather.\nTOOL: weather("Paris")',
        "ANSWER: Paris is currently 65°F and Sunny with 50% humidity.",
    ],
    "python|programming": [
        'Let me search for that.\nTOOL: web_search("python programming language")',
        "ANSWER: Python is a high-level programming language created by Guido van Rossum in 1991, widely used in web development, data science, AI, and automation.",
    ],
    "file|read|pyproject": [
        'TOOL: file_reader("pyproject.toml")',
        "ANSWER: The file contains the project's build configuration and dependencies.",
    ],
}

MOCK_DEFAULT = [
    'TOOL: web_search("{question}")',
    "ANSWER: Based on my research, I found relevant information about your question.",
]


def mock_llm(question: str, step: int) -> str:
    for pattern, script in MOCK_SCRIPTS.items():
        if re.search(pattern, question, re.IGNORECASE):
            return script[min(step, len(script) - 1)]
    return MOCK_DEFAULT[min(step, len(MOCK_DEFAULT) - 1)].replace("{question}", question)


# ---------------------------------------------------------------------------
# Gemini LLM
# ---------------------------------------------------------------------------

def gemini_call(messages: list[dict], model: str = "gemini-2.0-flash") -> tuple[str, dict]:
    """Call Gemini API. Returns (response_text, usage_metadata)."""
    import google.generativeai as genai

    api_key = _get_api_key()
    genai.configure(api_key=api_key)

    gm = genai.GenerativeModel(model)

    # Convert messages to Gemini format
    # Gemini uses 'user' and 'model' roles, system goes in generation config
    system_text = None
    contents = []
    for msg in messages:
        role = msg["role"]
        text = msg["content"]
        if role == "system":
            system_text = text
        elif role == "assistant":
            contents.append({"role": "model", "parts": [text]})
        else:
            contents.append({"role": "user", "parts": [text]})

    gen_config = genai.types.GenerationConfig(temperature=0.7, max_output_tokens=1024)
    if system_text:
        gm = genai.GenerativeModel(model, system_instruction=system_text)

    response = gm.generate_content(contents, generation_config=gen_config)

    # Extract usage
    usage = {}
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        um = response.usage_metadata
        usage = {
            "prompt_tokens": getattr(um, "prompt_token_count", None),
            "completion_tokens": getattr(um, "candidates_token_count", None),
            "total_tokens": getattr(um, "total_token_count", None),
        }

    return response.text, usage


def _get_api_key() -> str:
    import os
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        print("Error: Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable.")
        print("Get one at: https://aistudio.google.com/apikey")
        sys.exit(1)
    return key


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ResearchAgent:
    """Research assistant agent instrumented with ReAgent."""

    def __init__(self, client: ReAgent, use_mock: bool = False, project: str = "demo",
                 model: str = "gemini-2.0-flash"):
        self.client = client
        self.use_mock = use_mock
        self.project = project
        self.model = model
        self.max_steps = 10

    def run(self, question: str) -> str:
        """Run the agent loop and return the final answer."""
        mode = "mock" if self.use_mock else "gemini"
        config = RunConfig(
            name=f"research: {question[:50]}",
            project=self.project,
            tags=["demo", "research-agent", mode],
            input={"question": question},
            metadata={"agent_type": "research_assistant", "llm_mode": mode},
        )

        with self.client.trace(config) as ctx:
            ctx.set_framework("demo-agent", "1.0")
            ctx.set_model(self.model)

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT.format(
                    tool_list="\n".join(f"- {n}: {t['description']}" for n, t in TOOLS.items())
                )},
                {"role": "user", "content": question},
            ]

            step = 0
            while step < self.max_steps:
                # Record thinking
                ctx.record_agent_action(
                    action="think",
                    thought=f"Step {step + 1}: Processing with {len(messages) - 2} context messages.",
                    agent_name="ResearchAgent",
                    agent_type="research_assistant",
                )

                # LLM call
                start = time.time()
                if self.use_mock:
                    response_text = mock_llm(question, step)
                    duration_ms = int((time.time() - start) * 1000) + 100
                    ctx.record_llm_call(
                        model=self.model,
                        messages=messages,
                        response=response_text,
                        prompt_tokens=sum(len(m["content"].split()) for m in messages) * 2,
                        completion_tokens=len(response_text.split()) * 2,
                        cost_usd=0.001,
                        duration_ms=duration_ms,
                    )
                else:
                    response_text, usage = gemini_call(messages, model=self.model)
                    duration_ms = int((time.time() - start) * 1000)
                    ctx.record_llm_call(
                        model=self.model,
                        messages=messages,
                        response=response_text,
                        prompt_tokens=usage.get("prompt_tokens"),
                        completion_tokens=usage.get("completion_tokens"),
                        duration_ms=duration_ms,
                        provider="google",
                    )

                print(f"\n[LLM] {response_text.strip()}")

                messages.append({"role": "assistant", "content": response_text})

                # Parse: check for ANSWER first
                answer_match = ANSWER_PATTERN.search(response_text)
                if answer_match:
                    answer = answer_match.group(1).strip()
                    ctx.record_agent_finish(
                        final_answer=answer,
                        thought="Providing final answer.",
                        agent_name="ResearchAgent",
                    )
                    ctx.set_output({"answer": answer})
                    return answer

                # Parse: check for TOOL call
                tool_match = TOOL_PATTERN.search(response_text)
                if tool_match:
                    tool_name = tool_match.group(1)
                    tool_arg = tool_match.group(2)
                    result = self._execute_tool(ctx, tool_name, tool_arg)
                    print(f"[TOOL:{tool_name}] {result[:200]}")
                    messages.append({"role": "user", "content": f"Tool result from {tool_name}:\n{result}"})
                else:
                    # LLM didn't use the format — treat entire response as answer
                    ctx.record_agent_finish(
                        final_answer=response_text.strip(),
                        thought="LLM responded directly without tool/answer format.",
                        agent_name="ResearchAgent",
                    )
                    ctx.set_output({"answer": response_text.strip()})
                    return response_text.strip()

                step += 1

            # Max steps
            answer = "Reached maximum steps without a final answer."
            ctx.record_agent_finish(
                final_answer=answer,
                thought="Max steps reached.",
                agent_name="ResearchAgent",
            )
            ctx.set_output({"answer": answer})
            return answer

    def _execute_tool(self, ctx, tool_name: str, tool_arg: str) -> str:
        """Execute a tool and record it via ReAgent."""
        if tool_name not in TOOLS:
            error_msg = f"Unknown tool: {tool_name}"
            ctx.record_tool_call(
                tool_name=tool_name,
                kwargs={"arg": tool_arg},
                error=error_msg,
                error_type="ValueError",
            )
            return f"Error: {error_msg}"

        tool = TOOLS[tool_name]
        start = time.time()
        try:
            result = tool["fn"](tool_arg)
            duration_ms = int((time.time() - start) * 1000)
            ctx.record_tool_call(
                tool_name=tool_name,
                kwargs={"arg": tool_arg},
                result=result,
                duration_ms=duration_ms,
                tool_description=tool["description"],
            )
            return str(result)
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            ctx.record_tool_call(
                tool_name=tool_name,
                kwargs={"arg": tool_arg},
                error=str(e),
                error_type=type(e).__name__,
                duration_ms=duration_ms,
                tool_description=tool["description"],
            )
            return f"Error ({type(e).__name__}): {e}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ReAgent Demo — Research Agent powered by Gemini")
    parser.add_argument("question", help="Question to research")
    parser.add_argument("--mock", action="store_true", help="Use mock LLM (no API key needed)")
    parser.add_argument("--model", default="gemini-2.0-flash", help="Gemini model (default: gemini-2.0-flash)")
    parser.add_argument("--project", default="demo", help="ReAgent project name (default: demo)")
    args = parser.parse_args()

    # Check for API key unless mock mode
    if not args.mock:
        import os
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            print("Error: Set GEMINI_API_KEY or GOOGLE_API_KEY to use real mode.")
            print("       Or use --mock for testing without an API key.")
            print("       Get a key at: https://aistudio.google.com/apikey")
            sys.exit(1)

    demo_path = Path(__file__).parent.parent / ".reagent" / "demo_traces"
    demo_path.mkdir(parents=True, exist_ok=True)
    client = ReAgent(storage_path=str(demo_path))

    agent = ResearchAgent(client, use_mock=args.mock, project=args.project, model=args.model)

    print(f"Question: {args.question}")
    print(f"Mode: {'mock' if args.mock else f'Gemini ({args.model})'}")
    print("-" * 50)

    answer = agent.run(args.question)

    print(f"\n{'='*50}")
    print(f"Final Answer: {answer}")
    print(f"{'='*50}")
    print(f"Trace stored. Inspect with: reagent list --project {args.project}")

    client.close()


if __name__ == "__main__":
    main()
