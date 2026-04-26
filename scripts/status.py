"""
ECHO state inspector — shows every layer at once.

Usage:
    python scripts/inspect.py          # full snapshot
    python scripts/inspect.py recall "what was I working on"   # semantic recall test
"""
import os
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT_ROOT)


def fmt_ts(ts):
    if not ts:
        return "(unprocessed)"
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def section(title):
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def main():
    from echo.memory import db, vectors

    if len(sys.argv) > 1 and sys.argv[1] == "recall":
        query = " ".join(sys.argv[2:])
        if not query:
            print("Usage: python scripts/inspect.py recall <query>")
            return
        section(f"SEMANTIC RECALL: {query!r}")
        hits = vectors.query(query, top_k=5)
        if not hits:
            print("  no results (ChromaDB is empty or query found nothing)")
            return
        for i, h in enumerate(hits, 1):
            src = h["metadata"].get("source", "?")
            print(f"  {i}. [d={h['distance']:.3f}, src={src}]")
            print(f"     {h['document']}")
        return

    # Default: full snapshot
    section("TRANSCRIPTS")
    rows = db.recent_transcripts(20)
    print(f"  total: {db.transcript_count()}, showing latest {len(rows)}")
    print()
    for r in rows:
        proc = "✓" if r.get("processed_at") else " "  # processed flag
        # ASCII fallback for Windows cp1252
        proc = "[done]" if r.get("processed_at") else "[pend]"
        print(f"  {fmt_ts(r['ts'])}  {proc}  {r['text']}")
    if not rows:
        print("  (none)")

    section("MEMORIES")
    mems = db.recent_memories(20)
    if mems:
        for m in mems:
            print(f"  {fmt_ts(m['created_at'])}  [{m.get('category','')}]  {m['content']}")
    else:
        print("  (none — post-processor hasn't run yet, or hasn't found anything notable)")

    section("ACTION ITEMS (open)")
    items = db.open_action_items()
    if items:
        for a in items:
            print(f"  {fmt_ts(a['created_at'])}  {a['content']}")
    else:
        print("  (none)")

    section("CHROMADB VECTOR INDEX")
    n = vectors.count()
    print(f"  total vectors: {n}")
    if n > 0:
        # Quick distribution by source
        coll = vectors._ensure()
        if coll is not None:
            try:
                all_meta = coll.get(include=["metadatas"])["metadatas"]
                src_counts = {}
                for m in all_meta:
                    s = (m or {}).get("source", "?")
                    src_counts[s] = src_counts.get(s, 0) + 1
                for s, c in sorted(src_counts.items()):
                    print(f"    {s}: {c}")
            except Exception as e:
                print(f"    (couldn't break down: {e})")

    section("BUS — registered topics")
    from echo import bus
    from echo import workers  # noqa: F401  triggers subscriptions
    for t in bus.topics():
        print(f"  {t}")

    print()


if __name__ == "__main__":
    main()
