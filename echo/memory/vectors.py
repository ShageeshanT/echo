"""
ChromaDB — local persistent vector store. Mirrors Omi's `database/vector_db.py`
(Pinecone) at single-user scale.

Embeddings come from ChromaDB's bundled ONNX `all-MiniLM-L6-v2` (384-dim).
No torch dependency. First call lazy-downloads ~80MB to ~/.cache.

`upsert(id, text, metadata)` — store anything (memory, transcript chunk,
action item) with arbitrary metadata.
`query(text, top_k, where)` — semantic search.

Designed to be called from the post-processing worker in Phase 3.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from echo.config import CHROMA_COLLECTION, CHROMA_DIR

_LOCK = threading.Lock()
_client = None
_collection = None


def _ensure() -> Any:
    """Lazy-init ChromaDB client + collection. Returns the collection."""
    global _client, _collection
    if _collection is not None:
        return _collection

    with _LOCK:
        if _collection is not None:
            return _collection
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            return None

        _client = chromadb.PersistentClient(
            path=CHROMA_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        _collection = _client.get_or_create_collection(name=CHROMA_COLLECTION)
    return _collection


def upsert(doc_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
    """Store/overwrite a single document. Returns True on success."""
    coll = _ensure()
    if coll is None:
        return False
    try:
        coll.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata or {}],
        )
        return True
    except Exception:
        return False


def query(text: str, top_k: int = 5, where: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Semantic search. Returns list of {id, document, metadata, distance}."""
    coll = _ensure()
    if coll is None:
        return []
    try:
        res = coll.query(
            query_texts=[text],
            n_results=top_k,
            where=where,
        )
    except Exception:
        return []

    ids = (res.get("ids") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    return [
        {"id": i, "document": d, "metadata": m or {}, "distance": dist}
        for i, d, m, dist in zip(ids, docs, metas, dists)
    ]


def delete(doc_id: str) -> bool:
    coll = _ensure()
    if coll is None:
        return False
    try:
        coll.delete(ids=[doc_id])
        return True
    except Exception:
        return False


def count() -> int:
    coll = _ensure()
    if coll is None:
        return 0
    try:
        return int(coll.count())
    except Exception:
        return 0
