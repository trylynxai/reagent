"""Demo tools for the ReAgent research agent.

Real working tools — calculator does real math, file_reader reads real files,
web_search and weather use canned data (no external API deps).
"""

from __future__ import annotations

import json
import math
import os


def web_search(query: str) -> str:
    """Search the web for information. Returns search results as text.

    Note: Uses canned results to avoid external API dependencies.
    In a real agent you'd plug in Google Search, Tavily, etc.
    """
    # Simple keyword-based canned results — enough for the LLM to work with
    results = {
        "python": "Python is a high-level programming language created by Guido van Rossum, first released in 1991. It emphasizes code readability and supports multiple paradigms including procedural, object-oriented, and functional programming. Python 3 is the current major version.",
        "weather": "Weather information requires a real-time API. Common weather APIs include OpenWeatherMap, WeatherAPI, and the National Weather Service API.",
        "capital": "World capitals: France — Paris, Japan — Tokyo, United Kingdom — London, Germany — Berlin, Italy — Rome, Spain — Madrid, India — New Delhi, China — Beijing, Brazil — Brasilia, Australia — Canberra.",
        "ai": "Artificial intelligence (AI) is intelligence demonstrated by machines. Key subfields include machine learning, natural language processing, computer vision, and robotics. Recent advances include large language models (LLMs) like GPT-4, Gemini, and Claude.",
        "reagent": "ReAgent is an observability SDK for AI agents. It records LLM calls, tool executions, reasoning steps, and errors. It provides CLI tools for inspecting, searching, replaying, and exporting agent traces.",
    }
    query_lower = query.lower()
    matched = []
    for keyword, info in results.items():
        if keyword in query_lower:
            matched.append(info)
    if matched:
        return "\n\n".join(matched)
    return f"Search results for '{query}': No specific results found. The query may need to be more specific."


def calculator(expression: str) -> str:
    """Evaluate a mathematical expression. Supports basic arithmetic, powers, and math functions.

    Examples: '2+2', 'sqrt(144)', 'sin(3.14/2)', '2**10'
    """
    # Provide safe math functions
    safe_globals = {"__builtins__": {}}
    safe_locals = {
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "log10": math.log10,
        "pi": math.pi,
        "e": math.e,
        "abs": abs,
        "round": round,
        "pow": pow,
        "min": min,
        "max": max,
    }
    try:
        result = eval(expression, safe_globals, safe_locals)  # noqa: S307
    except Exception as e:
        raise ValueError(f"Cannot evaluate '{expression}': {e}") from e
    return str(result)


def weather(location: str) -> str:
    """Get current weather for a location.

    Note: Uses canned data. In a real agent you'd use OpenWeatherMap, etc.
    """
    data = {
        "new york": {"location": "New York, NY", "temp_f": 72, "condition": "Partly Cloudy", "humidity": 55, "wind_mph": 8},
        "london": {"location": "London, UK", "temp_f": 59, "condition": "Overcast", "humidity": 78, "wind_mph": 12},
        "tokyo": {"location": "Tokyo, JP", "temp_f": 68, "condition": "Clear", "humidity": 45, "wind_mph": 5},
        "paris": {"location": "Paris, FR", "temp_f": 65, "condition": "Sunny", "humidity": 50, "wind_mph": 7},
        "san francisco": {"location": "San Francisco, CA", "temp_f": 58, "condition": "Foggy", "humidity": 85, "wind_mph": 15},
        "sydney": {"location": "Sydney, AU", "temp_f": 75, "condition": "Sunny", "humidity": 60, "wind_mph": 10},
    }
    key = location.lower().strip()
    for name, info in data.items():
        if name in key or key in name:
            return json.dumps(info)
    return json.dumps({"location": location, "temp_f": 70, "condition": "Clear", "humidity": 50, "wind_mph": 6, "note": "Approximate data — location not in database"})


def file_reader(path: str) -> str:
    """Read the contents of a file from the filesystem.

    Reads real files. Returns the file content as text (max 5000 chars).
    """
    resolved = os.path.expanduser(path)
    if not os.path.exists(resolved):
        raise FileNotFoundError(f"File not found: '{path}'")
    if not os.path.isfile(resolved):
        raise ValueError(f"Not a file: '{path}'")
    with open(resolved) as f:
        content = f.read(5000)
    if len(content) == 5000:
        content += "\n... (truncated at 5000 chars)"
    return content


TOOLS = {
    "web_search": {
        "fn": web_search,
        "description": "Search the web for information. Args: query (str). Returns text results.",
    },
    "calculator": {
        "fn": calculator,
        "description": "Evaluate a math expression. Args: expression (str). Supports +, -, *, /, **, sqrt(), sin(), cos(), log(), pi, e. Returns the result.",
    },
    "weather": {
        "fn": weather,
        "description": "Get current weather for a location. Args: location (str). Returns JSON with temp_f, condition, humidity, wind_mph.",
    },
    "file_reader": {
        "fn": file_reader,
        "description": "Read a file from the filesystem. Args: path (str). Returns file contents as text (max 5000 chars).",
    },
}
