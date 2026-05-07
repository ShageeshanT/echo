"""
Streaming brain — async generator that yields complete sentences as they
arrive from Groq. Drives the streaming TTS pipeline.

Phase 4: uses LLM tool calling. If the model calls tools, we execute them,
append results, and re-stream. Content chunks are yielded as they arrive
so the TTS pipeline stays responsive.

Yield contract:
  - On fast-path intent match (mute, sleep, exit):
        yields ONE string (reply text or sentinel). Then ends.
  - On tool call that returns a sentinel (__SLEEP__ / __EXIT__):
        yields the sentinel. Then ends.
  - Otherwise streams Groq with tools + stream=true:
        yields one string per complete sentence.
        Final partial-sentence remainder is yielded at end.
  - On error: yields nothing extra; caller handles fallback.

History is updated:
  - user message appended at start
  - assistant message appended at end with the full accumulated reply
"""
from __future__ import annotations

import asyncio
import json
import re
import threading
from typing import AsyncIterator

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

# Match sentence-end punctuation followed by whitespace.
_SENT_BOUNDARY = re.compile(r"[.!?]\s+")
_LONG_REMAINDER_LIMIT = 220
_COMMA_BREAK_RE = re.compile(r"[,;]\s+")


def _split_complete_sentences(text: str):
    """Returns (list_of_complete_sentences, remainder)."""
    sentences = []
    pos = 0
    for m in _SENT_BOUNDARY.finditer(text):
        end = m.end()
        sent = text[pos:end].strip()
        if sent:
            sentences.append(sent)
        pos = end

    remainder = text[pos:]

    if len(remainder) > _LONG_REMAINDER_LIMIT:
        commas = list(_COMMA_BREAK_RE.finditer(remainder))
        if commas:
            m = commas[-1]
            sentences.append(remainder[: m.end()].strip())
            remainder = remainder[m.end():]

    return sentences, remainder


# ---------------------------------------------------------------------------
# Groq SSE stream with tool call support
# ---------------------------------------------------------------------------
def _groq_stream_blocking(messages, tools=None):
    """Synchronous generator — yields either:
      ("content", chunk_str)  — a content delta
      ("tool_calls", list)    — accumulated tool calls when stream ends with tool_calls
    """
    body = {
        "model": GROQ_MODEL_TOOLS,
        "messages": messages,
        "max_tokens": 400,
        "temperature": 0.7,
        "stream": True,
    }
    if tools:
        body["tools"] = tools

    resp = requests.post(
        GROQ_ENDPOINT,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        json=body,
        stream=True,
        timeout=30,
    )
    if resp.status_code != 200:
        log("brain", f"Groq stream HTTP {resp.status_code}: {resp.text[:200]}")
        return

    # Accumulate tool calls across chunks.
    # Groq sends tool_calls as deltas: {index, id, function.name, function.arguments}
    # The arguments string is fragmented across multiple chunks.
    tool_calls_acc: dict[int, dict] = {}  # index -> {id, name, arguments_parts[]}

    for raw in resp.iter_lines(decode_unicode=True):
        if not raw:
            continue
        if not raw.startswith("data:"):
            continue
        payload = raw[5:].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except Exception:
            continue

        choice = obj.get("choices", [{}])[0]
        delta = choice.get("delta", {})
        finish = choice.get("finish_reason")

        # Content delta
        content = delta.get("content")
        if content:
            yield ("content", content)

        # Tool call deltas
        tc_deltas = delta.get("tool_calls")
        if tc_deltas:
            for tcd in tc_deltas:
                idx = tcd.get("index", 0)
                if idx not in tool_calls_acc:
                    tool_calls_acc[idx] = {
                        "id": tcd.get("id", ""),
                        "name": tcd.get("function", {}).get("name", ""),
                        "arguments_parts": [],
                    }
                else:
                    # id and name might come in the first delta only
                    if tcd.get("id"):
                        tool_calls_acc[idx]["id"] = tcd["id"]
                    if tcd.get("function", {}).get("name"):
                        tool_calls_acc[idx]["name"] = tcd["function"]["name"]

                arg_frag = tcd.get("function", {}).get("arguments", "")
                if arg_frag:
                    tool_calls_acc[idx]["arguments_parts"].append(arg_frag)

        # End of stream — check if we got tool calls
        if finish == "tool_calls" and tool_calls_acc:
            # Assemble complete tool calls
            assembled = []
            for idx in sorted(tool_calls_acc.keys()):
                tc = tool_calls_acc[idx]
                assembled.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": "".join(tc["arguments_parts"]),
                    },
                })
            yield ("tool_calls", assembled)
            return

    # If we had tool calls but didn't get a clean finish_reason, still yield them
    if tool_calls_acc:
        assembled = []
        for idx in sorted(tool_calls_acc.keys()):
            tc = tool_calls_acc[idx]
            assembled.append({
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": "".join(tc["arguments_parts"]),
                },
            })
        yield ("tool_calls", assembled)


# ---------------------------------------------------------------------------
# Main async generator — the public API
# ---------------------------------------------------------------------------
async def call_ai_backend_stream(text: str) -> AsyncIterator[str]:
    """Async generator. Yields strings (sentences or sentinels)."""

    # 1. Deterministic fast-path (mute, sleep, exit).
    handled = intent.dispatch(text)
    if handled is not None:
        yield handled
        return

    # 2. Build context.
    history.append("user", text)

    mem_ctx = get_memory_context(text)
    system_msg = GROQ_SYSTEM + ("\n\n" + mem_ctx if mem_ctx else "")
    messages = [{"role": "system", "content": system_msg}] + history.get()

    # 3. Stream with tool-calling loop.
    loop = asyncio.get_running_loop()
    sentence_buf = ""
    full_reply_parts = []

    for _round in range(MAX_TOOL_ROUNDS):
        queue: asyncio.Queue = asyncio.Queue()

        # Copy messages for the closure (avoid mutation during iteration)
        msgs_snapshot = list(messages)

        def producer(msgs=msgs_snapshot):
            try:
                for item in _groq_stream_blocking(msgs, tools=TOOL_SCHEMAS):
                    asyncio.run_coroutine_threadsafe(queue.put(item), loop)
            except Exception as e:
                log("brain", f"streaming producer error: {e!r}")
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        threading.Thread(target=producer, daemon=True).start()

        tool_calls = None

        while True:
            item = await queue.get()
            if item is None:
                break

            kind, data = item

            if kind == "content":
                sentence_buf += data
                sentences, sentence_buf = _split_complete_sentences(sentence_buf)
                for s in sentences:
                    full_reply_parts.append(s)
                    yield s

            elif kind == "tool_calls":
                tool_calls = data
                break  # exit the queue loop, handle tools below

        if tool_calls is None:
            # Normal end — no more tool calls. Flush remainder.
            break

        # Execute tool calls.
        assistant_msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls,
        }
        messages.append(assistant_msg)

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, KeyError):
                fn_args = {}

            log("brain", f"stream tool call: {fn_name}({fn_args})")
            result = execute_tool(fn_name, fn_args)

            # Sentinels bubble up immediately.
            if result in ("__SLEEP__", "__EXIT__"):
                yield result
                return

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

        log("brain", f"tool round {_round + 1} done, re-streaming for final response")
        # Loop continues — next iteration streams the model's response to tool results.

    # Flush any remaining partial sentence.
    if sentence_buf.strip():
        final = sentence_buf.strip()
        full_reply_parts.append(final)
        yield final

    if full_reply_parts:
        history.append("assistant", " ".join(full_reply_parts))
