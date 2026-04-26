"""
Embedder worker — universal vector ingestor for ChromaDB.

Subscribes to three topics:
  transcript.persisted   raw transcripts written by persistence worker
  memory.extracted       memories produced by the post-processor
  action_item.extracted  action items produced by the post-processor

Each event becomes one row in the `echo_memory` collection, tagged with
`source` metadata so the recall API in Phase 3c can filter by type.

The first upsert lazy-downloads ~80MB of ONNX weights to ~/.cache. After
that every embed is ~50ms on CPU. We run in a daemon thread so the bus
publish stays non-blocking — `*.persisted/extracted` subscribers fan out
in the publish thread, and we don't want to hold up other subscribers
while ChromaDB embeds.
"""
import threading

from echo import bus
from echo.log import log
from echo.memory import vectors


def _embed_async(text: str, doc_id: str, metadata: dict) -> None:
    text = (text or "").strip()
    if not text or not doc_id:
        return

    # Drop None values — ChromaDB rejects them in metadata.
    metadata = {k: v for k, v in metadata.items() if v is not None}

    ok = vectors.upsert(doc_id, text, metadata)
    src = metadata.get("source", "?")
    if ok:
        log("embedder", f"embedded {doc_id[:8]} ({src}) — {vectors.count()} total")
    else:
        log("embedder", f"FAILED to embed {doc_id[:8]} ({src})")


def _on_transcript_persisted(evt) -> None:
    p = evt.payload or {}
    metadata = {
        "ts": p.get("ts"),
        "duration_s": p.get("duration_s"),
        "speaker": p.get("speaker"),
        "window_app": p.get("window_app"),
        "source": "transcript",
    }
    threading.Thread(
        target=_embed_async,
        args=(p.get("text"), p.get("id"), metadata),
        daemon=True,
    ).start()


def _on_memory_extracted(evt) -> None:
    p = evt.payload or {}
    metadata = {
        "source": "memory",
        "source_transcript_ids": ",".join(p.get("source_transcript_ids", [])[:3]) or None,
    }
    threading.Thread(
        target=_embed_async,
        args=(p.get("content"), p.get("id"), metadata),
        daemon=True,
    ).start()


def _on_action_item_extracted(evt) -> None:
    p = evt.payload or {}
    metadata = {
        "source": "action_item",
        "source_transcript_ids": ",".join(p.get("source_transcript_ids", [])[:3]) or None,
    }
    threading.Thread(
        target=_embed_async,
        args=(p.get("content"), p.get("id"), metadata),
        daemon=True,
    ).start()


bus.subscribe("transcript.persisted", _on_transcript_persisted)
bus.subscribe("memory.extracted", _on_memory_extracted)
bus.subscribe("action_item.extracted", _on_action_item_extracted)
