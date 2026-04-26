"""
Post-processor — turns raw transcripts into structured memory.

This is the analog of Omi's `utils/conversations/` extraction pipeline:
periodically batches transcripts and asks an LLM (Gemini 2.5 Flash, free
tier, structured output) to extract memories + action items + a summary.

Lifecycle:
  start()              — kicks off the daemon thread (called from JarvisApp init)
  _loop()              — every POSTPROC_INTERVAL_SECS:
                            pull unprocessed transcripts (oldest first)
                            -> Gemini structured-output call
                            -> insert memories + action_items into SQLite
                            -> publish memory.extracted / action_item.extracted
                            -> mark transcripts processed
  stop()               — graceful shutdown

The embedder worker (workers/embedder.py) listens for `memory.extracted`
events and adds them to ChromaDB so brain Phase 4 can recall them.
"""
import json
import threading
import time
import uuid
from typing import Any, Dict, List

from echo import bus
from echo.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    POSTPROC_BATCH_SIZE,
    POSTPROC_INTERVAL_SECS,
    POSTPROC_MIN_TOTAL_CHARS,
)
from echo.log import log
from echo.memory import db


# ---------------------------------------------------------------------------
# Gemini client — lazy, so we don't pay the import cost if the worker is
# never actually started (e.g. in tests).
# ---------------------------------------------------------------------------
_gemini_model = None
_gemini_lock = threading.Lock()


def _get_gemini():
    global _gemini_model
    if _gemini_model is not None or not GEMINI_API_KEY:
        return _gemini_model
    with _gemini_lock:
        if _gemini_model is not None:
            return _gemini_model
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            _gemini_model = genai.GenerativeModel(GEMINI_MODEL)
            log("postproc", f"Gemini initialized ({GEMINI_MODEL})")
        except Exception as e:
            log("postproc", f"Gemini init FAILED: {e!r}")
    return _gemini_model


# ---------------------------------------------------------------------------
# Prompt + structured output schema
# ---------------------------------------------------------------------------
_EXTRACTION_PROMPT = """\
You are an extractor processing transcribed speech captured passively from a \
user's microphone. The user is referred to as "Sir" by the assistant ECHO.

Speech may be:
  - User thinking aloud / working
  - User on a call or in a meeting
  - Background TV / music / other people (IGNORE)
  - Self-talk that's not memorable (IGNORE)

Extract:
1. memories      — first-person facts about the user worth remembering long
                   term. Preferences, plans, opinions, things they revealed
                   about themselves. Each memory: a single self-contained
                   sentence in third person ("user prefers X", "user has a
                   meeting on Thursday at 3pm"). NO meta sentences like "user
                   is testing the system".
2. action_items  — tasks the user said they NEED TO DO. Future tense or
                   imperative. Skip past tense ("I emailed Sarah" is NOT an
                   action item).
3. summary       — 1-2 sentence summary, OR empty string if nothing notable.

BE CONSERVATIVE. If transcripts are short, fragmented, ambiguous, or just
noise, return empty arrays. Better to miss than hallucinate.

Transcripts (oldest first), separated by ---:
"""

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "memories": {
            "type": "array",
            "items": {"type": "string"},
        },
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "due_hint": {"type": "string"},
                },
                "required": ["text"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["memories", "action_items", "summary"],
}


def _extract(transcripts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run Gemini on a batch. Returns parsed JSON or empty dict on failure."""
    model = _get_gemini()
    if model is None:
        return {}

    body = "\n---\n".join(t["text"] for t in transcripts)
    prompt = _EXTRACTION_PROMPT + body

    try:
        from google.generativeai.types import GenerationConfig
        cfg = GenerationConfig(
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
            temperature=0.2,
        )
        t0 = time.time()
        resp = model.generate_content(prompt, generation_config=cfg)
        dt = time.time() - t0
        text = (resp.text or "").strip()
        data = json.loads(text)
        log("postproc",
            f"Gemini OK in {dt:.1f}s — "
            f"{len(data.get('memories', []))} memories, "
            f"{len(data.get('action_items', []))} action_items")
        return data
    except Exception as e:
        log("postproc", f"Gemini extraction FAILED: {type(e).__name__}: {e}")
        return {}


# ---------------------------------------------------------------------------
# Persistence side
# ---------------------------------------------------------------------------
def _persist(extracted: Dict[str, Any], source_ids: List[str]) -> None:
    """Write memories + action items to SQLite, then publish events so the
    embedder (and any future plugin) can react."""
    src_summary = ",".join(s[:8] for s in source_ids[:3])  # short label

    for content in extracted.get("memories", []):
        content = (content or "").strip()
        if not content:
            continue
        mid = db.insert_memory(content, category="extracted",
                               source_conversation_id=src_summary)
        bus.publish("memory.extracted", {
            "id": mid,
            "content": content,
            "source_transcript_ids": source_ids,
        })

    for item in extracted.get("action_items", []):
        text = (item.get("text") or "").strip()
        if not text:
            continue
        # `due_hint` stays as text — Phase 4 brain will resolve to a real
        # timestamp when needed.
        full = text
        hint = (item.get("due_hint") or "").strip()
        if hint:
            full = f"{text} (due hint: {hint})"
        aid = db.insert_action_item(full, source_conversation_id=src_summary)
        bus.publish("action_item.extracted", {
            "id": aid,
            "content": full,
            "source_transcript_ids": source_ids,
        })


# ---------------------------------------------------------------------------
# Daemon loop
# ---------------------------------------------------------------------------
_thread = None
_running = False
_wake_event = threading.Event()


def _process_once() -> int:
    """One pass — returns number of transcripts processed."""
    rows = db.unprocessed_transcripts(limit=POSTPROC_BATCH_SIZE)
    if not rows:
        return 0

    total_chars = sum(len(r["text"]) for r in rows)
    if total_chars < POSTPROC_MIN_TOTAL_CHARS:
        # Not enough material — leave them unprocessed and try again next round
        # (more transcripts may accumulate).
        return 0

    log("postproc", f"processing batch of {len(rows)} transcripts ({total_chars} chars)")
    extracted = _extract(rows)
    if not extracted:
        # Don't mark processed on failure — retry next round.
        return 0

    ids = [r["id"] for r in rows]
    _persist(extracted, ids)
    db.mark_transcripts_processed(ids)
    return len(rows)


def _loop() -> None:
    log("postproc", f"started (interval={POSTPROC_INTERVAL_SECS}s)")
    while _running:
        try:
            _process_once()
        except Exception as e:
            log("postproc", f"loop error: {e!r}")
        # Sleep with cancellable wake
        _wake_event.wait(timeout=POSTPROC_INTERVAL_SECS)
        _wake_event.clear()
    log("postproc", "stopped")


def start() -> None:
    global _thread, _running
    if _running:
        return
    _running = True
    _wake_event.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="postproc")
    _thread.start()


def stop() -> None:
    global _running
    _running = False
    _wake_event.set()


def trigger_now() -> None:
    """Wake the loop early (used by tests / manual flushes)."""
    _wake_event.set()
