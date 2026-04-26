"""
FastAPI server — WebSocket bridge between echo.bus and browser, plus static
file serving for the web UI.

WebSocket protocol (JSON unless noted):
  Browser -> Server
    text:  {"type": "submit", "text": "..."}                user typed something
    text:  {"type": "wake"} / {"type": "sleep"}             state transition request
    text:  {"type": "audio_meta", "sample_rate": 16000}     before sending audio
    binary:                                                 raw float32 PCM mono @ 16kHz
                                                            (one finalized utterance)

  Server -> Browser  (mirrored bus events)
    {"type": "audio.rms", "value": 0.04}
    {"type": "transcript.partial", "text": "..."}           future
    {"type": "transcript.final", "text": "..."}
    {"type": "memory.extracted", "content": "..."}
    {"type": "action_item.extracted", "content": "..."}
    {"type": "response.start"}                              brain started
    {"type": "response.chunk", "text": "..."}               streaming token
    {"type": "response.tts_chunk_b64", "data": "..."}       streaming MP3 (base64)
    {"type": "response.end"}
    {"type": "status", "value": "online" | "thinking" | "speaking" | "sleeping"}
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
from typing import Set

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from echo import bus
from echo import config  # noqa: F401  triggers .env load + flag detection
from echo import workers  # noqa: F401  registers transcriber/persistence/embedder/post_processor
from echo.brain import call_ai_backend
from echo.log import log
from echo.stt.whisper import _load as load_whisper, transcribe_audio
from echo.tts.minimax import speak_minimax  # for now; will swap to streaming later

# ---------------------------------------------------------------------------
# App + static files
# ---------------------------------------------------------------------------
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = FastAPI(title="ECHO web UI")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.get("/favicon.ico")
async def favicon():
    # Avoid 404 noise — return the index page's empty default
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


# ---------------------------------------------------------------------------
# Connection manager — keeps a set of live WebSockets and broadcasts bus
# events to all of them. The bus subscriptions are registered ONCE at module
# import time (when uvicorn loads echo.web.server).
# ---------------------------------------------------------------------------
_clients: Set[WebSocket] = set()
_loop: asyncio.AbstractEventLoop | None = None


def _broadcast(payload: dict) -> None:
    """Schedule a JSON broadcast on the asyncio loop (called from any thread,
    including bus subscriber callbacks running in audio threads)."""
    if _loop is None or not _clients:
        return
    msg = json.dumps(payload)

    async def _send_all():
        dead = []
        for ws in list(_clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _clients.discard(ws)

    asyncio.run_coroutine_threadsafe(_send_all(), _loop)


# Bus subscriptions — register once, forward to all connected browsers.
def _on_bus_audio_rms(evt):
    _broadcast({"type": "audio.rms", "value": evt.payload})


def _on_bus_transcript_final(evt):
    p = evt.payload or {}
    _broadcast({
        "type": "transcript.final",
        "text": p.get("text", ""),
        "ts": p.get("ts"),
        "duration_s": p.get("duration_s"),
    })


def _on_bus_memory_extracted(evt):
    p = evt.payload or {}
    _broadcast({
        "type": "memory.extracted",
        "content": p.get("content", ""),
    })


def _on_bus_action_item_extracted(evt):
    p = evt.payload or {}
    _broadcast({
        "type": "action_item.extracted",
        "content": p.get("content", ""),
    })


bus.subscribe("audio.rms", _on_bus_audio_rms)
bus.subscribe("transcript.final", _on_bus_transcript_final)
bus.subscribe("memory.extracted", _on_bus_memory_extracted)
bus.subscribe("action_item.extracted", _on_bus_action_item_extracted)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    global _loop
    _loop = asyncio.get_running_loop()

    await ws.accept()
    _clients.add(ws)
    log("web", f"client connected ({len(_clients)} total)")
    await ws.send_text(json.dumps({"type": "status", "value": "online"}))

    # Per-connection state for incoming audio. Browser sends a JSON
    # `audio_meta` first, then one binary blob with the PCM samples.
    audio_sr = 16000

    try:
        while True:
            msg = await ws.receive()

            if "text" in msg and msg["text"] is not None:
                try:
                    data = json.loads(msg["text"])
                except Exception:
                    continue

                t = data.get("type")
                if t == "submit":
                    text = (data.get("text") or "").strip()
                    if text:
                        # Run brain off the asyncio thread so we don't block
                        # incoming audio frames.
                        asyncio.create_task(_handle_submit(ws, text))

                elif t == "audio_meta":
                    audio_sr = int(data.get("sample_rate", 16000))

            elif "bytes" in msg and msg["bytes"] is not None:
                # Browser finalized an utterance and sent raw float32 PCM.
                pcm = np.frombuffer(msg["bytes"], dtype=np.float32)
                if len(pcm) > 0:
                    asyncio.create_task(_handle_audio(ws, pcm, audio_sr))

    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(ws)
        log("web", f"client disconnected ({len(_clients)} total)")


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
async def _handle_audio(ws: WebSocket, pcm: np.ndarray, sr: int) -> None:
    """Browser sent finalized audio. Whisper -> publish transcript.final ->
    bus subscribers (persistence, embedder) take it from there. The brain
    is NOT auto-triggered from passive utterances; user must hit the
    'send to ECHO' button or it's left as ambient capture."""
    duration = len(pcm) / sr
    log("web", f"received audio: {len(pcm)} samples, {duration:.1f}s, sr={sr}")

    if duration < 0.3:
        return  # too short

    text = await asyncio.to_thread(
        transcribe_audio, pcm, source_sr=sr, vad_filter=False, debug_label="web_mic"
    )
    if not text:
        return

    import time as _t
    bus.publish("transcript.final", {
        "text": text,
        "ts": _t.time(),
        "duration_s": duration,
    })


async def _handle_submit(ws: WebSocket, text: str) -> None:
    """User typed (or spoke + clicked send). Run brain, stream chunks back."""
    await ws.send_text(json.dumps({"type": "status", "value": "thinking"}))
    await ws.send_text(json.dumps({"type": "response.start"}))

    reply = await asyncio.to_thread(call_ai_backend, text)

    if reply == "__SLEEP__":
        await ws.send_text(json.dumps({"type": "response.chunk", "text": "Going to sleep."}))
        await ws.send_text(json.dumps({"type": "response.end"}))
        await ws.send_text(json.dumps({"type": "status", "value": "sleeping"}))
        return
    if reply == "__EXIT__":
        await ws.send_text(json.dumps({"type": "response.chunk", "text": "Goodbye."}))
        await ws.send_text(json.dumps({"type": "response.end"}))
        return

    # Until we wire streaming Groq, send the whole reply at once.
    await ws.send_text(json.dumps({"type": "response.chunk", "text": reply}))
    await ws.send_text(json.dumps({"type": "response.end"}))
    await ws.send_text(json.dumps({"type": "status", "value": "speaking"}))

    # Synthesize speech in parallel — don't block the response chunk delivery.
    asyncio.create_task(_synthesize_and_send(ws, reply))


async def _synthesize_and_send(ws: WebSocket, text: str) -> None:
    """Stream MiniMax MP3 bytes to browser. Phase A is non-streaming (one
    blob); Phase B will swap to MiniMax stream=True for true streaming."""
    # Off-thread synthesis so we don't block the asyncio loop
    audio_bytes = await asyncio.to_thread(_synth_minimax_to_bytes, text)
    if not audio_bytes:
        await ws.send_text(json.dumps({"type": "status", "value": "online"}))
        return

    b64 = base64.b64encode(audio_bytes).decode("ascii")
    try:
        await ws.send_text(json.dumps({"type": "response.tts_chunk_b64", "data": b64}))
    except Exception:
        pass
    await ws.send_text(json.dumps({"type": "status", "value": "online"}))


def _synth_minimax_to_bytes(text: str) -> bytes:
    """Synth via MiniMax, return raw MP3 bytes (no playback). Quick
    adaptation of speak_minimax's request without the pygame play step."""
    import requests
    from echo.config import (
        MINIMAX_API_KEY, MINIMAX_ENDPOINT, MINIMAX_MODEL, MINIMAX_VOICE_ID,
    )
    if not MINIMAX_API_KEY:
        return b""
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
                    "speed": 1.0, "vol": 1.0, "pitch": 0,
                },
                "audio_setting": {
                    "sample_rate": 44100, "bitrate": 128000,
                    "format": "mp3", "channel": 1,
                },
                "output_format": "hex",
            },
            timeout=20,
        )
        if resp.status_code != 200:
            log("web", f"MiniMax error {resp.status_code}")
            return b""
        data = resp.json()
        if data.get("base_resp", {}).get("status_code", -1) != 0:
            return b""
        audio_hex = data.get("data", {}).get("audio", "")
        if not audio_hex:
            return b""
        return bytes.fromhex(audio_hex)
    except Exception as e:
        log("web", f"MiniMax exception: {e!r}")
        return b""


# ---------------------------------------------------------------------------
# Pre-warm: load whisper at startup so first transcribe is instant
# ---------------------------------------------------------------------------
def _prewarm():
    threading.Thread(target=load_whisper, daemon=True).start()


_prewarm()


# Allow `python -m echo.web.server` direct launch
if __name__ == "__main__":
    import uvicorn
    log("web", "starting uvicorn on http://127.0.0.1:8765")
    uvicorn.run("echo.web.server:app", host="127.0.0.1", port=8765, reload=False)
