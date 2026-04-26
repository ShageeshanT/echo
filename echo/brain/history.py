"""
Rolling conversation history (last MAX_HISTORY turns).

Kept in-memory for now to preserve original behavior. In Phase 3 the
post-processing worker will mirror these to SQLite + ChromaDB so memory
survives restarts and becomes RAG-able.
"""
from typing import Dict, List

from echo.config import MAX_HISTORY

_history: List[Dict[str, str]] = []


def get() -> List[Dict[str, str]]:
    return _history


def append(role: str, content: str) -> None:
    _history.append({"role": role, "content": content})
    # Trim from the front to keep the most recent MAX_HISTORY messages.
    if len(_history) > MAX_HISTORY:
        del _history[:len(_history) - MAX_HISTORY]


def clear() -> None:
    _history.clear()
