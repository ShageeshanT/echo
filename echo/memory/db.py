"""
SQLite — structured persistent store. Mirrors Omi's database/ layout
(conversations, messages, memories, action_items) at single-user scale.

Schema is created idempotently on first import. All writes go through
`_LOCK` so concurrent threads can't interleave statements on the single
connection (SQLite supports concurrent reads but a single writer).
"""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from echo.config import SQLITE_PATH

_LOCK = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _init_schema(_conn)
    return _conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            started_at REAL NOT NULL,
            ended_at REAL,
            title TEXT,
            summary TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT,
            role TEXT NOT NULL,           -- user | assistant | system
            content TEXT NOT NULL,
            ts REAL NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conv_ts ON messages(conversation_id, ts);

        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            category TEXT,
            source_conversation_id TEXT,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);

        CREATE TABLE IF NOT EXISTS action_items (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            due_at REAL,
            done INTEGER NOT NULL DEFAULT 0,
            source_conversation_id TEXT,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_action_items_done ON action_items(done, created_at DESC);

        CREATE TABLE IF NOT EXISTS transcripts (
            id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            ts REAL NOT NULL,
            speaker TEXT,
            window_app TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_transcripts_ts ON transcripts(ts DESC);

        CREATE TABLE IF NOT EXISTS screen_events (
            id TEXT PRIMARY KEY,
            ts REAL NOT NULL,
            app_name TEXT,
            window_title TEXT,
            description TEXT             -- vision-model summary, populated in Phase 5
        );
        CREATE INDEX IF NOT EXISTS idx_screen_events_ts ON screen_events(ts DESC);
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Convenience helpers — kept minimal in Phase 1; brain/post-processor will
# extend in later phases.
# ---------------------------------------------------------------------------
def _new_id() -> str:
    return uuid.uuid4().hex


def insert_message(conversation_id: Optional[str], role: str, content: str) -> str:
    mid = _new_id()
    with _LOCK:
        conn = _connect()
        conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, ts) VALUES (?, ?, ?, ?, ?)",
            (mid, conversation_id, role, content, time.time()),
        )
        conn.commit()
    return mid


def insert_memory(content: str, category: str = "", source_conversation_id: Optional[str] = None) -> str:
    mid = _new_id()
    with _LOCK:
        conn = _connect()
        conn.execute(
            "INSERT INTO memories (id, content, category, source_conversation_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (mid, content, category, source_conversation_id, time.time()),
        )
        conn.commit()
    return mid


def insert_action_item(content: str, due_at: Optional[float] = None,
                       source_conversation_id: Optional[str] = None) -> str:
    aid = _new_id()
    with _LOCK:
        conn = _connect()
        conn.execute(
            "INSERT INTO action_items (id, content, due_at, source_conversation_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (aid, content, due_at, source_conversation_id, time.time()),
        )
        conn.commit()
    return aid


def recent_messages(limit: int = 10) -> List[Dict[str, Any]]:
    with _LOCK:
        conn = _connect()
        rows = conn.execute(
            "SELECT role, content, ts FROM messages ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def recent_memories(limit: int = 50) -> List[Dict[str, Any]]:
    with _LOCK:
        conn = _connect()
        rows = conn.execute(
            "SELECT id, content, category, created_at FROM memories ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def open_action_items() -> List[Dict[str, Any]]:
    with _LOCK:
        conn = _connect()
        rows = conn.execute(
            "SELECT id, content, due_at, created_at FROM action_items WHERE done=0 ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def close() -> None:
    global _conn
    with _LOCK:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None


# Eager-init the schema so a fresh checkout works on first run.
_connect()
