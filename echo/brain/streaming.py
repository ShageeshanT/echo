"""
Streaming brain — async generator that yields complete sentences as they
arrive from Groq. Drives the streaming TTS pipeline.

Yield contract:
  - On intent match (open Brave, time, mute, sleep, exit, etc.):
        yields ONE string that is either the reply text OR a sentinel
        ("__SLEEP__" / "__EXIT__"). Then ends.
  - Otherwise streams Groq with stream=true:
        yields one string per complete sentence (split on `.!?` + whitespace).
        Final partial-sentence remainder is yielded at end of stream.
  - On error: yields nothing extra; caller is responsible for fallback text.

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
from echo.config import GROQ_API_KEY, GROQ_ENDPOINT, GROQ_MODEL, GROQ_SYSTEM
from echo.log import log


# Match sentence-end punctuation followed by whitespace. Pragmatic — will
# split "Mr. Smith" too, which is fine for voice (slight pause sounds OK).
_SENT_BOUNDARY = re.compile(r"[.!?]\s+")
_LONG_REMAINDER_LIMIT = 220   # if no terminal punctuation, force-flush at a comma
_COMMA_BREAK_RE = re.compile(r"[,;]\s+")


def _split_complete_sentences(text: str):
    """Returns (list_of_complete_sentences, remainder).

    A complete sentence ends with [.!?] followed by whitespace. The remainder
    is the partial in-progress sentence after the last complete one. If the
    remainder grows past _LONG_REMAINDER_LIMIT chars without any terminal
    punctuation we look for a comma to keep the TTS pipeline flowing on
    very long utterances.
    """
    sentences = []
    pos = 0
    for m in _SENT_BOUNDARY.finditer(text):
        end = m.end()
        sent = text[pos:end].strip()
        if sent:
            sentences.append(sent)
        pos = end

    remainder = text[pos:]

    # Long-running sentence with no terminal punctuation — break at the
    # latest comma so audio doesn't sit waiting forever.
    if len(remainder) > _LONG_REMAINDER_LIMIT:
        commas = list(_COMMA_BREAK_RE.finditer(remainder))
        if commas:
            m = commas[-1]
            sentences.append(remainder[: m.end()].strip())
            remainder = remainder[m.end():]

    return sentences, remainder


def _groq_stream_blocking(messages):
    """Synchronous generator — yields content chunks from Groq SSE."""
    resp = requests.post(
        GROQ_ENDPOINT,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        json={
            "model": GROQ_MODEL,
            "messages": messages,
            "max_tokens": 400,
            "temperature": 0.7,
            "stream": True,
        },
        stream=True,
        timeout=30,
    )
    if resp.status_code != 200:
        log("brain", f"Groq stream HTTP {resp.status_code}: {resp.text[:200]}")
        return
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw:
            continue
        if not raw.startswith("data:"):
            continue
        payload = raw[5:].strip()
        if payload == "[DONE]":
            return
        try:
            obj = json.loads(payload)
        except Exception:
            continue
        try:
            chunk = obj["choices"][0]["delta"].get("content")
        except Exception:
            chunk = None
        if chunk:
            yield chunk


async def call_ai_backend_stream(text: str) -> AsyncIterator[str]:
    """Async generator. Yields strings.

    Possible yield values:
      - a sentinel: "__SLEEP__" / "__EXIT__" (only as a single yield)
      - a complete sentence
      - on intent match: the full reply (one yield)
    """
    handled = intent.dispatch(text)
    if handled is not None:
        yield handled
        return

    history.append("user", text)
    messages = [{"role": "system", "content": GROQ_SYSTEM}] + history.get()

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def producer():
        try:
            for chunk in _groq_stream_blocking(messages):
                asyncio.run_coroutine_threadsafe(queue.put(chunk), loop)
        except Exception as e:
            log("brain", f"streaming producer error: {e!r}")
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)

    threading.Thread(target=producer, daemon=True).start()

    sentence_buf = ""
    full_reply_parts = []

    while True:
        chunk = await queue.get()
        if chunk is None:
            # End of Groq stream — flush remainder
            if sentence_buf.strip():
                final = sentence_buf.strip()
                full_reply_parts.append(final)
                yield final
            break

        sentence_buf += chunk
        sentences, sentence_buf = _split_complete_sentences(sentence_buf)
        for s in sentences:
            full_reply_parts.append(s)
            yield s

    if full_reply_parts:
        history.append("assistant", " ".join(full_reply_parts))
