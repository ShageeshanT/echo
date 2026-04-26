"""
Memory layer — Omi's database/ + vector_db split, local.

  db.py       SQLite — structured: conversations, messages, memories,
              action items, screen events, sessions.
  vectors.py  ChromaDB — semantic recall (uses bundled ONNX embedder).

All readers/writers are thread-safe; SQLite uses check_same_thread=False
behind a per-connection lock.
"""
from echo.memory import db, vectors  # noqa: F401
