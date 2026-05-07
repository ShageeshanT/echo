"""
Tool registry for Phase 4 LLM tool calling.

Each tool has an OpenAI-format schema (for the `tools` request param) and
an executor function. The brain sends schemas to Groq, gets back tool_calls,
and calls `execute(name, args)` to run them.

The underlying action handlers (apps, browser, system) are unchanged — we
just wire them through structured tool calling instead of keyword matching.
"""
from __future__ import annotations

import json

from echo.actions import apps, browser, system
from echo.log import log
from echo.memory import vectors


# ---------------------------------------------------------------------------
# Normalized app name -> (command, friendly_name, use_brave) from APP_MAP
# ---------------------------------------------------------------------------
_APP_LOOKUP: dict[str, tuple] = {}
for _kws, _cmd, _name, _brave in apps.APP_MAP:
    for _kw in _kws:
        _APP_LOOKUP[_kw] = (_cmd, _name, _brave)


# ---------------------------------------------------------------------------
# Tool schemas — OpenAI function-calling format
# ---------------------------------------------------------------------------
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "play_youtube",
            "description": (
                "Play a song, video, or music on YouTube. Use when the user "
                "asks to play, listen to, or put on music/videos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for YouTube (song name, artist, video title, etc.)",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": (
                "Open an application or website on the user's computer. "
                "Available apps: brave/browser, firefox, edge, notepad, "
                "calculator, file explorer, spotify, terminal, settings, "
                "task manager, youtube, whatsapp, discord, vscode."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": (
                            "Name of the app to open. Use lowercase: brave, firefox, "
                            "edge, notepad, calculator, explorer, spotify, terminal, "
                            "settings, task manager, youtube, whatsapp, discord, vscode"
                        ),
                    }
                },
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for information. Use when the user asks to "
                "search, google, or look something up."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current time. Use when the user asks what time it is.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_date",
            "description": "Get today's date and day of the week.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "toggle_mute",
            "description": "Mute or unmute the system audio.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": (
                "Search ECHO's memory of past conversations for relevant information. "
                "Use when the user asks about something they mentioned before, or "
                "when you need context from previous sessions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for in memory",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Max results to return (default 3)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "go_to_sleep",
            "description": "Put ECHO into sleep mode. Use when the user says goodnight, go to sleep, etc.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shut_down",
            "description": "Shut down ECHO. Use when the user says exit, quit, shut down, or close ECHO.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------
def execute(name: str, arguments: dict) -> str:
    """Run a tool and return a string result for the LLM."""
    log("tools", f"executing {name}({arguments})")

    try:
        if name == "play_youtube":
            query = arguments.get("query", "")
            if not query:
                return "No query provided."
            browser.play_youtube(query)
            return f"Now playing '{query}' on YouTube."

        if name == "open_app":
            app_name = arguments.get("app_name", "").lower().strip()
            if not app_name:
                return "No app name provided."
            # Try direct lookup, then fuzzy match against keywords
            match = _APP_LOOKUP.get(app_name)
            if not match:
                # Try partial match
                for key, val in _APP_LOOKUP.items():
                    if key in app_name or app_name in key:
                        match = val
                        break
            if not match:
                return f"Unknown app '{app_name}'. Available: brave, firefox, edge, notepad, calculator, explorer, spotify, terminal, settings, task manager, youtube, whatsapp, discord, vscode."
            cmd, friendly, use_brave = match
            if use_brave:
                apps.open_brave(cmd)
            else:
                apps.open_app(cmd)
            return f"Opening {friendly}."

        if name == "web_search":
            query = arguments.get("query", "")
            if not query:
                return "No query provided."
            browser.web_search(query)
            return f"Searching the web for '{query}'."

        if name == "get_current_time":
            return f"The current time is {system.current_time()}."

        if name == "get_current_date":
            return f"Today is {system.current_date()}."

        if name == "toggle_mute":
            result = system.toggle_mute()
            if result == "muted":
                return "System audio muted."
            if result == "unmuted":
                return "System audio unmuted."
            return "Failed to toggle mute."

        if name == "recall_memory":
            query = arguments.get("query", "")
            top_k = arguments.get("top_k", 3)
            if not query:
                return "No query provided."
            hits = vectors.query(query, top_k=top_k)
            if not hits:
                return "No relevant memories found."
            lines = []
            for h in hits:
                doc = (h.get("document") or "").strip()
                if not doc:
                    continue
                if len(doc) > 200:
                    doc = doc[:200] + "..."
                dist = h.get("distance", 0)
                lines.append(f"- {doc} (relevance: {max(0, 1 - dist):.0%})")
            return "\n".join(lines) if lines else "No relevant memories found."

        if name == "go_to_sleep":
            return "__SLEEP__"

        if name == "shut_down":
            return "__EXIT__"

        return f"Unknown tool: {name}"

    except Exception as e:
        log("tools", f"execution error for {name}: {e!r}")
        return f"Tool '{name}' failed: {e}"
