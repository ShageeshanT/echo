"""
Passive memory retrieval — query ChromaDB before every chat turn and inject
relevant memories/transcripts into the system prompt.

Phase 3 completion: the write side (embedder, post_processor) is done;
this module is the read side that closes the loop.
"""
from echo.config import MEMORY_CONTEXT_MAX_CHARS, MEMORY_RELEVANCE_THRESHOLD, MEMORY_TOP_K
from echo.log import log
from echo.memory import vectors


def get_memory_context(user_text: str) -> str | None:
    """Return a formatted context block of relevant memories, or None.

    Called before every Groq request so the LLM knows what ECHO has
    observed in past conversations.  Runs ~50ms on CPU (ChromaDB ONNX).
    """
    if not user_text.strip():
        return None

    try:
        hits = vectors.query(user_text, top_k=MEMORY_TOP_K)
    except Exception as e:
        log("memory", f"context query failed: {e!r}")
        return None

    if not hits:
        return None

    # Filter by distance — ChromaDB always returns top_k results even when
    # nothing is remotely relevant.  Cosine distance: 0 = identical, 2 = opposite.
    relevant = [h for h in hits if h.get("distance", 2.0) < MEMORY_RELEVANCE_THRESHOLD]
    if not relevant:
        return None

    lines = []
    total = 0
    for h in relevant:
        doc = (h.get("document") or "").strip()
        if not doc:
            continue
        # Truncate individual entries that are too long
        if len(doc) > 200:
            doc = doc[:200] + "..."
        if total + len(doc) > MEMORY_CONTEXT_MAX_CHARS:
            break
        source = (h.get("metadata") or {}).get("source", "unknown")
        lines.append(f"- [{source}] {doc}")
        total += len(doc)

    if not lines:
        return None

    block = "[Relevant memories from past conversations:\n" + "\n".join(lines) + "]"
    log("memory", f"injecting {len(lines)} memories ({total} chars) into context")
    return block
