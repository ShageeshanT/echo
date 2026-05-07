"""
Async-friendly MiniMax synth — returns raw MP3 bytes (no playback).

The legacy `tts/minimax.py:speak_minimax` does request + decode + pygame
playback in one go. For the streaming pipeline we want to separate synth
(the slow network call) from playback (which now happens in the browser).

`synth_minimax_async(text)` -> `bytes` of MP3, or `b""` on failure.
Runs the blocking `requests.post` in a worker thread so asyncio stays
responsive.
"""
from __future__ import annotations

import asyncio
import time

import requests

from echo.config import (
    MINIMAX_API_KEY,
    MINIMAX_ENDPOINT,
    MINIMAX_MODEL,
    MINIMAX_VOICE_ID,
)
from echo.log import log


def _synth_minimax_blocking(text: str) -> bytes:
    if not MINIMAX_API_KEY or not text.strip():
        return b""
    t0 = time.time()
    try:
        resp = requests.post(
            MINIMAX_ENDPOINT,
            headers={
                "Authorization": f"Bearer {MINIMAX_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MINIMAX_MODEL,
                "text": text,
                "stream": False,
                "voice_setting": {
                    "voice_id": MINIMAX_VOICE_ID,
                    "speed": 1.0,
                    "vol": 1.0,
                    "pitch": 0,
                },
                "audio_setting": {
                    "sample_rate": 44100,
                    "bitrate": 128000,
                    "format": "mp3",
                    "channel": 1,
                },
                "output_format": "hex",
            },
            timeout=20,
        )
        if resp.status_code != 200:
            log("synth", f"MiniMax HTTP {resp.status_code}")
            return b""
        data = resp.json()
        if data.get("base_resp", {}).get("status_code", -1) != 0:
            log("synth", f"MiniMax base_resp error: {data.get('base_resp')}")
            return b""
        audio_hex = data.get("data", {}).get("audio", "")
        if not audio_hex:
            return b""
        out = bytes.fromhex(audio_hex)
        elapsed = time.time() - t0
        log("synth",
            f"MiniMax: {len(text):4d}ch text -> {len(out):6d}b mp3 in {elapsed:5.2f}s"
            f"  ({text[:60]!r})")
        return out
    except Exception as e:
        elapsed = time.time() - t0
        log("synth", f"MiniMax exception after {elapsed:.2f}s: {e!r}")
        return b""


async def synth_minimax_async(text: str) -> bytes:
    """Off-thread MiniMax synth. Safe to call from asyncio code."""
    return await asyncio.to_thread(_synth_minimax_blocking, text)


# ---------------------------------------------------------------------------
# Provider abstraction — picks Edge TTS by default (free, ~0.9s first byte)
# or MiniMax via TTS_PROVIDER=minimax in .env. Falls back to Edge if the
# selected provider isn't usable.
# ---------------------------------------------------------------------------
async def synth_async(text: str) -> bytes:
    """Top-level async TTS. The streaming pipeline calls this; the actual
    provider is chosen by config.TTS_PROVIDER."""
    from echo.config import TTS_PROVIDER

    if TTS_PROVIDER == "minimax":
        return await synth_minimax_async(text)

    # Default: Edge (free + faster)
    try:
        from echo.tts.edge_synth import synth_edge_async
        return await synth_edge_async(text)
    except Exception:
        # Edge import failed — fall back to MiniMax if we have credentials.
        return await synth_minimax_async(text)
