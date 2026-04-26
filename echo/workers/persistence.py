"""
Persistence worker — writes `transcript.final` events to SQLite.

This is the smallest possible worker that mirrors Omi's pusher persistence
path (Omi batches over WebSocket, we just write inline). Phase 3 will add a
sibling worker that *also* embeds the transcript into ChromaDB and runs
post-processing extraction.
"""
from echo import bus
from echo.log import log
from echo.memory import db


def _on_transcript_final(evt) -> None:
    p = evt.payload or {}
    text = (p.get("text") or "").strip()
    if not text:
        return
    try:
        tid = db.insert_transcript(
            text=text,
            ts=p.get("ts"),
            speaker=p.get("speaker"),
            window_app=p.get("window_app"),
        )
        log("persistence", f"wrote transcript {tid[:8]}: {text[:80]!r}")
        # Re-publish so future workers (Phase 3 vector-embedder, plugin
        # subscribers) can react after the row is durable.
        bus.publish("transcript.persisted", {**p, "id": tid})
    except Exception as e:
        log("persistence", f"ERROR writing transcript: {e!r}")


bus.subscribe("transcript.final", _on_transcript_final)
