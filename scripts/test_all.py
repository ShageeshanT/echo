"""
End-to-end ECHO self-test. Exercises every layer:

    config / .env          flag detection + key loading
    AudioCapture           opens mic, publishes audio.chunk + audio.rms
    bus                    pub/sub topic delivery
    whisper                model load + transcribe()
    transcriber + persist  audio -> transcript.final -> SQLite
    embedder               transcript.persisted -> ChromaDB
    semantic recall        vectors.query
    actions/intent         keyword dispatch (no LLM)
    brain (Groq)           Llama 3.3 70b chat
    Gemini                 raw API ping

Run from project root:  python scripts/test_all.py
"""
import asyncio
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT_ROOT)


def banner(title):
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def main():
    # ------------------------------------------------------------------
    banner("1. IMPORTS + FEATURE FLAGS + API KEYS")
    # ------------------------------------------------------------------
    from echo import bus, config, state  # noqa: F401
    from echo import workers              # registers transcriber/persistence/embedder
    from echo.actions import dispatch
    from echo.brain import call_ai_backend, history
    from echo.capture import AudioCapture
    from echo.memory import db, vectors
    from echo.stt.whisper import _load, get_model, transcribe_audio
    print(f"  AUDIO_OK={config.AUDIO_OK}  PYGAME_OK={config.PYGAME_OK}  "
          f"WHISPER_OK={config.WHISPER_OK}  EDGE_TTS_OK={config.EDGE_TTS_OK}  "
          f"PYTTSX_OK={config.PYTTSX_OK}  PSUTIL_OK={config.PSUTIL_OK}")
    print(f"  GROQ key:    {'set' if config.GROQ_API_KEY else 'MISSING'}")
    print(f"  GEMINI key:  {'set' if config.GEMINI_API_KEY else 'MISSING'}")
    print(f"  MINIMAX key: {'set' if config.MINIMAX_API_KEY else 'MISSING'}")
    print(f"  bus topics with subscribers: {bus.topics()}")

    # ------------------------------------------------------------------
    banner("2. WHISPER MODEL LOAD (synchronous)")
    # ------------------------------------------------------------------
    t0 = time.time()
    _load()
    if get_model() is None:
        print("  FAILED to load whisper")
        return
    print(f"  OK loaded in {time.time() - t0:.1f}s")

    # ------------------------------------------------------------------
    banner("3. AUDIO CAPTURE — opens mic device 5 for 5s")
    # ------------------------------------------------------------------
    chunk_count = [0]
    rms_samples = []

    def on_chunk(evt):
        chunk_count[0] += 1

    def on_rms(evt):
        rms_samples.append(evt.payload)

    unsub_chunk = bus.subscribe("audio.chunk", on_chunk)
    unsub_rms = bus.subscribe("audio.rms", on_rms)

    ac = AudioCapture()
    ac.start()
    print("  capturing 5 seconds of mic input (ambient is fine)...")
    time.sleep(5)
    ac.stop()
    unsub_chunk()
    unsub_rms()

    if chunk_count[0] == 0:
        print("  FAIL NO chunks captured — AudioCapture failed to open the mic")
    else:
        rate = chunk_count[0] / 5
        peak = max(rms_samples) if rms_samples else 0
        avg = sum(rms_samples) / max(1, len(rms_samples))
        print(f"  OK {chunk_count[0]} chunks in 5s  (~{rate:.1f}/sec, expected ~22)")
        print(f"    peak RMS = {peak:.4f}    avg RMS = {avg:.4f}")
        print(f"    transcribe threshold = {config.TRANSCRIBE_RMS_THRESHOLD}")
        if peak < config.TRANSCRIBE_RMS_THRESHOLD:
            print(f"    WARN peak BELOW threshold — silent room is normal; speak in front of mic to test")
        else:
            print(f"    OK peak above threshold — transcriber would have fired")

    # ------------------------------------------------------------------
    banner("4. END-TO-END: synthesize speech -> whisper -> bus -> SQLite -> ChromaDB")
    # ------------------------------------------------------------------
    test_text = "Hello echo, this is a test of the full pipeline. Remember to email Sarah on Friday."
    print(f"  synthesizing: {test_text!r}")

    fd, mp3_path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)

    async def synth():
        import edge_tts
        comm = edge_tts.Communicate(test_text, config.EDGE_TTS_VOICE, rate=config.EDGE_TTS_RATE)
        await comm.save(mp3_path)

    asyncio.run(synth())
    print(f"  saved: {os.path.getsize(mp3_path)} bytes")

    # faster-whisper accepts file paths directly
    print("  transcribing with faster-whisper...")
    t0 = time.time()
    model = get_model()
    segments, _ = model.transcribe(mp3_path, beam_size=1, language="en")
    segments = list(segments)
    transcribed = " ".join(s.text for s in segments).strip()
    print(f"  OK in {time.time() - t0:.1f}s -> {transcribed!r}")
    os.unlink(mp3_path)

    # Drive through bus -> SQLite -> ChromaDB
    db_before = db.transcript_count()
    vec_before = vectors.count()
    print(f"  publishing transcript.final to bus (SQLite={db_before}, ChromaDB={vec_before})")
    bus.publish("transcript.final", {
        "text": transcribed,
        "ts": time.time(),
        "duration_s": 3.0,
    })
    time.sleep(3)  # embedder runs async
    print(f"  OK SQLite:   {db_before} -> {db.transcript_count()}")
    print(f"  OK ChromaDB: {vec_before} -> {vectors.count()}")

    # ------------------------------------------------------------------
    banner("5. SEMANTIC RECALL")
    # ------------------------------------------------------------------
    queries = ["who do I need to message", "what's the test about"]
    for q in queries:
        hits = vectors.query(q, top_k=1)
        if hits:
            h = hits[0]
            print(f"  Q: {q!r}")
            print(f"     -> [d={h['distance']:.3f}] {h['document']!r}")
        else:
            print(f"  Q: {q!r}  -> no hits")

    # ------------------------------------------------------------------
    banner("6. ACTIONS — keyword intent (no LLM)")
    # ------------------------------------------------------------------
    cases = ["what time is it", "what date is today", "asfgkajsdfklj nonsense"]
    for c in cases:
        r = dispatch(c)
        print(f"  {c!r:45s} -> {r!r}")

    # ------------------------------------------------------------------
    banner("7. BRAIN — Groq (Llama 3.3 70b)")
    # ------------------------------------------------------------------
    history.clear()
    t0 = time.time()
    reply = call_ai_backend("In one short sentence, what's 2 plus 2?")
    print(f"  in {time.time() - t0:.1f}s: {reply!r}")

    # ------------------------------------------------------------------
    banner("8. GEMINI 2.0 FLASH — raw API ping")
    # ------------------------------------------------------------------
    try:
        import google.generativeai as genai
        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(config.GEMINI_MODEL)
        t0 = time.time()
        resp = model.generate_content("Reply with exactly: 'gemini ok'")
        text = (resp.text or "").strip()
        print(f"  in {time.time() - t0:.1f}s: {text!r}")
        if "gemini" in text.lower() and "ok" in text.lower():
            print("  OK Gemini key works")
        else:
            print(f"  WARN unexpected response: {text!r}")
    except Exception as e:
        print(f"  FAIL Gemini FAILED: {type(e).__name__}: {e}")

    # ------------------------------------------------------------------
    banner("9. CLEANUP — remove test rows so user starts fresh")
    # ------------------------------------------------------------------
    import sqlite3
    conn = sqlite3.connect(config.SQLITE_PATH)
    cur = conn.execute("DELETE FROM transcripts WHERE text LIKE '%full pipeline%'")
    conn.commit()
    print(f"  removed {cur.rowcount} test transcript(s) from SQLite")
    conn.close()
    # Wipe ChromaDB collection (single-file collection, just remove all)
    coll = vectors._ensure()
    if coll is not None:
        try:
            all_ids = coll.get()["ids"]
            if all_ids:
                coll.delete(ids=all_ids)
            print(f"  removed {len(all_ids)} test vector(s) from ChromaDB")
        except Exception as e:
            print(f"  cleanup failed: {e!r}")

    print()
    print("=" * 72)
    print("ALL TESTS COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    main()
