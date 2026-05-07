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
import time
from typing import Set

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from echo import bus
from echo import config  # noqa: F401  triggers .env load + flag detection
from echo import workers  # noqa: F401  registers transcriber/persistence/embedder/post_processor
from echo.brain import call_ai_backend, call_ai_backend_stream
from echo.log import log
from echo.stt.whisper import _load as load_whisper, transcribe_audio
from echo.tts.synth import synth_async

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

# Per-WebSocket "active stream" — the asyncio.Task currently producing a
# response (text + TTS) for that client. Cancelled by:
#   - a new "submit" arriving (drop the old one, start fresh)
#   - a "stop_tts" arriving (barge-in)
#   - the WebSocket closing
_active_streams: dict[WebSocket, asyncio.Task] = {}


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


def _on_bus_media_playing(evt):
    """ECHO triggered external media (YouTube etc). Tell every connected
    browser to pause its mic so it doesn't transcribe the song lyrics back
    to ECHO. User clicks the mic button to resume."""
    p = evt.payload or {}
    _broadcast({
        "type": "mic.pause",
        "reason": p.get("source", "media"),
    })


bus.subscribe("audio.rms", _on_bus_audio_rms)
bus.subscribe("transcript.final", _on_bus_transcript_final)
bus.subscribe("memory.extracted", _on_bus_memory_extracted)
bus.subscribe("action_item.extracted", _on_bus_action_item_extracted)
bus.subscribe("media.playing", _on_bus_media_playing)


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
                        _start_response(ws, text)

                elif t == "audio_meta":
                    audio_sr = int(data.get("sample_rate", 16000))

                elif t == "wake":
                    # Browser entered active mode — kick off the contextual
                    # greeting (system health + desktop scan + LLM-ish text).
                    _cancel_active_stream(ws)
                    task = asyncio.create_task(_handle_wake(ws))
                    _active_streams[ws] = task
                    task.add_done_callback(
                        lambda _t, _ws=ws: _active_streams.pop(_ws, None)
                    )

                elif t == "sleep":
                    # Browser entered sleep mode — kill any in-flight TTS.
                    _cancel_active_stream(ws)

                elif t == "stop_tts":
                    # Barge-in — user started talking, kill the current
                    # response stream + remaining TTS.
                    _cancel_active_stream(ws)

            elif "bytes" in msg and msg["bytes"] is not None:
                # Browser finalized an utterance and sent raw float32 PCM.
                pcm = np.frombuffer(msg["bytes"], dtype=np.float32)
                if len(pcm) > 0:
                    asyncio.create_task(_handle_audio(ws, pcm, audio_sr))

    except WebSocketDisconnect:
        pass
    finally:
        _cancel_active_stream(ws)
        _clients.discard(ws)
        log("web", f"client disconnected ({len(_clients)} total)")


def _cancel_active_stream(ws: WebSocket) -> None:
    """Cancel and clear any in-flight response task for this WS."""
    task = _active_streams.pop(ws, None)
    if task is not None and not task.done():
        task.cancel()


def _start_response(ws: WebSocket, text: str) -> None:
    """Cancel any in-flight stream for this WS, then start a fresh
    response (text + TTS). Used by both the typed `submit` path and the
    voice path after audio is transcribed — keeps the cancel/track
    bookkeeping in one place."""
    _cancel_active_stream(ws)
    task = asyncio.create_task(_handle_submit(ws, text))
    _active_streams[ws] = task
    task.add_done_callback(lambda _t, _ws=ws: _active_streams.pop(_ws, None))


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
async def _handle_audio(ws: WebSocket, pcm: np.ndarray, sr: int) -> None:
    """Browser sent finalized audio. Whisper -> publish transcript.final
    (so persistence + embedder pick it up) -> trigger a brain reply just
    like a typed submit. The user is in 'talking to ECHO' mode whenever
    the browser mic is on; toggle it off in the UI to stop being heard."""
    duration = len(pcm) / sr
    log("web", f"received audio: {len(pcm)} samples, {duration:.1f}s, sr={sr}")

    if duration < 0.3:
        return  # too short to be a real utterance

    text = await asyncio.to_thread(
        transcribe_audio, pcm, source_sr=sr, vad_filter=False, debug_label="web_mic"
    )
    if not text:
        return

    log("web", f"voice transcript -> {text!r}")
    import time as _t
    bus.publish("transcript.final", {
        "text": text,
        "ts": _t.time(),
        "duration_s": duration,
    })

    # Voice-in -> response-out: same path as typed submit.
    _start_response(ws, text)


async def _handle_wake(ws: WebSocket) -> None:
    """Browser woke up — scan system + desktop, build a contextual greeting,
    deliver it as a normal response (text + TTS)."""
    from echo.context.desktop import get_desktop_context
    from echo.context.greeting import build_wake_greeting
    from echo.context.system_health import get_system_health
    from echo.brain import history

    # Run scans in worker threads (they're sync + slow-ish).
    health = await asyncio.to_thread(get_system_health)
    ctx = await asyncio.to_thread(get_desktop_context)

    try:
        greeting = build_wake_greeting(ctx, health)
    except Exception:
        greeting = "Online. What's up?"

    # Inject context as a system note so the next chat turn knows what's open.
    context_msg = (
        f"[ECHO just woke up. Time: {ctx.get('time', '?')}, {ctx.get('date', '?')}. "
        f"Open apps: {', '.join(ctx.get('app_names', []))}. "
        f"Activities: {', '.join(ctx.get('activities', []))}. "
        f"Battery: {health.get('battery_percent', 'N/A')}%, "
        f"RAM used: {health.get('ram_percent_used', 'N/A')}%, "
        f"Internet: {'connected' if health.get('internet') else 'disconnected'}.]"
    )
    history.append("system", context_msg)

    await ws.send_text(json.dumps({"type": "response.start"}))
    await ws.send_text(json.dumps({"type": "response.chunk", "text": greeting}))
    await ws.send_text(json.dumps({"type": "response.end"}))
    await ws.send_text(json.dumps({"type": "status", "value": "speaking"}))

    # Synth in worker thread, send when ready, then back to online.
    audio = await synth_async(greeting)
    if audio:
        b64 = base64.b64encode(audio).decode("ascii")
        await _send_safe(ws, {"type": "response.tts_chunk_b64", "data": b64})
    await _send_safe(ws, {"type": "status", "value": "online"})


async def _handle_submit(ws: WebSocket, text: str) -> None:
    """User typed (or spoke + clicked send). Run STREAMING brain, send each
    sentence as it arrives, kick off MiniMax synth in parallel, send TTS
    chunks in order. Cancellable mid-flight via barge-in."""
    await ws.send_text(json.dumps({"type": "status", "value": "thinking"}))
    await ws.send_text(json.dumps({"type": "response.start"}))

    # Queue of pending TTS futures, IN ORDER. Producer kicks them off,
    # consumer awaits them sequentially and forwards audio.
    tts_q: asyncio.Queue = asyncio.Queue()

    async def producer():
        first_yield = True
        try:
            async for sentence in call_ai_backend_stream(text):
                if first_yield:
                    first_yield = False
                    if sentence == "__SLEEP__":
                        await _send_safe(ws, {"type": "response.chunk",
                                              "text": "Going to sleep."})
                        await _send_safe(ws, {"type": "response.end"})
                        await _send_safe(ws, {"type": "status", "value": "sleeping"})
                        return
                    if sentence == "__EXIT__":
                        await _send_safe(ws, {"type": "response.chunk",
                                              "text": "Goodbye."})
                        await _send_safe(ws, {"type": "response.end"})
                        return

                # 1. Emit the text immediately for the typewriter UI.
                await _send_safe(ws, {"type": "response.chunk",
                                      "text": sentence + " "})
                # 2. Start MiniMax synth in parallel — task goes to consumer.
                synth_task = asyncio.create_task(synth_async(sentence))
                await tts_q.put(synth_task)
        finally:
            await tts_q.put(None)  # sentinel so consumer can finish

    async def consumer():
        sent_speaking = False
        while True:
            item = await tts_q.get()
            if item is None:
                break
            if not sent_speaking:
                await _send_safe(ws, {"type": "status", "value": "speaking"})
                sent_speaking = True
            try:
                audio = await item
            except asyncio.CancelledError:
                # Drain remaining tasks so they don't leak
                while not tts_q.empty():
                    nxt = tts_q.get_nowait()
                    if nxt is not None and not nxt.done():
                        nxt.cancel()
                raise
            if audio:
                b64 = base64.b64encode(audio).decode("ascii")
                await _send_safe(ws, {"type": "response.tts_chunk_b64",
                                      "data": b64})
        # Stream finished cleanly
        await _send_safe(ws, {"type": "response.end"})
        await _send_safe(ws, {"type": "status", "value": "online"})

    try:
        await asyncio.gather(producer(), consumer())
    except asyncio.CancelledError:
        # Barge-in / new submit / disconnect — let the WS know we stopped
        await _send_safe(ws, {"type": "tts.stopped"})
        await _send_safe(ws, {"type": "status", "value": "online"})
        raise
    except Exception as e:
        log("web", f"submit handler error: {e!r}")
        await _send_safe(ws, {"type": "response.end"})
        await _send_safe(ws, {"type": "status", "value": "online"})


async def _send_safe(ws: WebSocket, payload: dict) -> None:
    """Send JSON and swallow disconnect errors so handlers can still
    finish their cleanup paths."""
    try:
        await ws.send_text(json.dumps(payload))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Pre-warm — load whisper at startup so the first transcription is instant.
# (TTS providers used to need warmup but Edge/MiniMax are reasonably steady
# now; we save the synth round-trip until the first real request.)
# ---------------------------------------------------------------------------
def _prewarm():
    threading.Thread(target=load_whisper, daemon=True).start()
    log("web", f"prewarming whisper; TTS provider = {config.TTS_PROVIDER}")


_prewarm()


# Allow `python -m echo.web.server` direct launch
if __name__ == "__main__":
    import uvicorn
    log("web", "starting uvicorn on http://127.0.0.1:8765")
    uvicorn.run("echo.web.server:app", host="127.0.0.1", port=8765, reload=False)
