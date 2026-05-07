"""
Edge TTS — Microsoft Azure neural voices, free, no API key.

Drop-in replacement for synth_minimax_async returning raw MP3 bytes.
Verified ~0.9-1.0s first byte vs MiniMax's ~3.8s — same quality range,
arguably better voices, no per-call quota.

Streams chunks internally and concatenates server-side; the WebSocket
contract to the browser stays unchanged (one mp3 per sentence). If we
later want intra-sentence streaming to the browser, the chunked stream
is already available — just forward each chunk instead of joining.
"""
from __future__ import annotations

import time
from typing import AsyncIterator

import edge_tts

from echo.config import EDGE_TTS_OK, EDGE_TTS_RATE, EDGE_TTS_VOICE
from echo.log import log


async def synth_edge_async(text: str) -> bytes:
    """Synthesize via Edge TTS, return concatenated MP3 bytes."""
    if not EDGE_TTS_OK or not text.strip():
        return b""
    t0 = time.time()
    try:
        chunks: list[bytes] = []
        comm = edge_tts.Communicate(text, EDGE_TTS_VOICE, rate=EDGE_TTS_RATE)
        async for chunk in comm.stream():
            if chunk.get("type") == "audio":
                data = chunk.get("data")
                if data:
                    chunks.append(data)
        out = b"".join(chunks)
        elapsed = time.time() - t0
        log("synth",
            f"Edge:    {len(text):4d}ch text -> {len(out):6d}b mp3 in {elapsed:5.2f}s"
            f"  ({text[:60]!r})")
        return out
    except Exception as e:
        elapsed = time.time() - t0
        log("synth", f"Edge TTS exception after {elapsed:.2f}s: {e!r}")
        return b""


async def stream_edge_async(text: str) -> AsyncIterator[bytes]:
    """Yield MP3 chunks as Edge TTS produces them. Available for future
    intra-sentence streaming to the browser via MediaSource API."""
    if not EDGE_TTS_OK or not text.strip():
        return
    try:
        comm = edge_tts.Communicate(text, EDGE_TTS_VOICE, rate=EDGE_TTS_RATE)
        async for chunk in comm.stream():
            if chunk.get("type") == "audio":
                data = chunk.get("data")
                if data:
                    yield data
    except Exception as e:
        log("synth", f"Edge TTS stream exception: {e!r}")
