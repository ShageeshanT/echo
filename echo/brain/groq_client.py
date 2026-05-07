"""
Brain entrypoint — keyword fast-path first, then Groq with tool calling.

call_ai_backend(text) -> reply | "__SLEEP__" | "__EXIT__"

Phase 4: LLM decides which tools to call (open apps, play YouTube, search,
check time, recall memory, etc.) via structured tool calling.
"""
import json

import requests

from echo.actions import intent
from echo.brain import history
from echo.brain.memory_context import get_memory_context
from echo.brain.tools import TOOL_SCHEMAS, execute as execute_tool
from echo.config import (
    GROQ_API_KEY,
    GROQ_ENDPOINT,
    GROQ_MODEL_TOOLS,
    GROQ_SYSTEM,
)
from echo.log import log

MAX_TOOL_ROUNDS = 3


def call_ai_backend(user_text: str) -> str:
    # 1. Deterministic fast-path (mute, sleep, exit).
    handled = intent.dispatch(user_text)
    if handled is not None:
        return handled

    # 2. Build context.
    history.append("user", user_text)

    # Phase 3: inject relevant memories into system prompt.
    mem_ctx = get_memory_context(user_text)
    system_msg = GROQ_SYSTEM + ("\n\n" + mem_ctx if mem_ctx else "")
    messages = [{"role": "system", "content": system_msg}] + history.get()

    # 3. Tool-calling loop (max MAX_TOOL_ROUNDS).
    for _round in range(MAX_TOOL_ROUNDS):
        try:
            resp = requests.post(
                GROQ_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL_TOOLS,
                    "messages": messages,
                    "tools": TOOL_SCHEMAS,
                    "max_tokens": 400,
                    "temperature": 0.7,
                },
                timeout=15,
            )
        except Exception as e:
            log("brain", f"Groq request failed: {e!r}")
            return "I'm having trouble reaching my servers."

        if resp.status_code != 200:
            log("brain", f"Groq HTTP {resp.status_code}: {resp.text[:200]}")
            return "I'm having trouble reaching my servers."

        choice = resp.json()["choices"][0]
        msg = choice["message"]
        finish = choice.get("finish_reason", "stop")

        if finish == "tool_calls" and msg.get("tool_calls"):
            # Append the assistant's tool-call message.
            messages.append(msg)

            for tc in msg["tool_calls"]:
                fn_name = tc["function"]["name"]
                try:
                    fn_args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    fn_args = {}

                result = execute_tool(fn_name, fn_args)

                # Sentinels bubble up immediately.
                if result in ("__SLEEP__", "__EXIT__"):
                    return result

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

            log("brain", f"tool round {_round + 1}: executed {len(msg['tool_calls'])} tool(s)")
            continue  # re-query with tool results

        # Normal text response — done.
        reply = msg.get("content", "")
        if reply:
            history.append("assistant", reply)
            return reply

        return "I'm having trouble reaching my servers."

    # Exhausted tool rounds without a final text response.
    return "I got confused trying to do that. Could you try again?"
