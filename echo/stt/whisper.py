"""
faster-whisper — local CPU/int8 STT.

Loaded once in a background thread at module import so the model is hot by
the time the user first talks. Other modules call `get_model()` to access.
"""
import threading

import numpy as np

from echo.config import (
    AUDIO_OK,
    MIC_DEVICE_INDEX,
    WHISPER_AVG_LOGPROB_THRESHOLD,
    WHISPER_BEAM_SIZE,
    WHISPER_HALLUCINATION_BLACKLIST,
    WHISPER_MODEL_SIZE,
    WHISPER_NO_SPEECH_THRESHOLD,
    WHISPER_OK,
)
from echo.log import log

_model = None
_load_lock = threading.Lock()
# Serializes ALL transcribe() calls — voice_to_text, wake-word detector in
# capture/audio.py, and the always-on transcriber in workers/transcriber.py
# all share the single model.
model_lock = threading.Lock()

if AUDIO_OK:
    import pyaudio


def _load():
    """Load the model once. Safe to call from multiple threads."""
    global _model
    if _model is not None or not WHISPER_OK:
        return
    with _load_lock:
        if _model is not None:
            return
        try:
            from faster_whisper import WhisperModel
            log("whisper", f"loading model '{WHISPER_MODEL_SIZE}' (cpu/int8)...")
            import time as _t
            t0 = _t.time()
            _model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
            log("whisper", f"model loaded in {_t.time() - t0:.1f}s")
        except Exception as e:
            log("whisper", f"ERROR loading model: {e!r}")


# Kick off loading in the background — don't block import.
threading.Thread(target=_load, daemon=True).start()


def get_model():
    """Return the loaded model or None if not ready / unavailable."""
    return _model


# faster-whisper's `transcribe(numpy_array, ...)` does NOT auto-resample —
# it assumes 16kHz mono. If you pass 44.1kHz audio claiming it's 16kHz,
# whisper hears chipmunk speech at 2.75x slowdown and returns empty.
# This helper does fast linear interpolation; quality is fine for STT.
def _resample(audio_f32, src_sr: int, dst_sr: int):
    if src_sr == dst_sr or len(audio_f32) == 0:
        return audio_f32
    src_len = len(audio_f32)
    dst_len = int(src_len * dst_sr / src_sr)
    src_idx = np.arange(src_len, dtype=np.float64)
    dst_idx = np.linspace(0, src_len - 1, dst_len, dtype=np.float64)
    return np.interp(dst_idx, src_idx, audio_f32).astype(np.float32)


def _save_debug_wav(audio_f32, sr: int, label: str) -> "str | None":
    """Write audio to data/debug_<label>_<ts>.wav so we can listen to what
    whisper actually saw when it returned empty. Capped to 5 most recent
    files per label to avoid filling disk."""
    import os
    import time as _t
    import wave as _wave
    from echo.config import DATA_DIR
    try:
        # Trim old debug files (keep last 5 per label)
        existing = sorted(
            f for f in os.listdir(DATA_DIR)
            if f.startswith(f"debug_{label}_") and f.endswith(".wav")
        )
        for f in existing[:-5]:
            try:
                os.remove(os.path.join(DATA_DIR, f))
            except Exception:
                pass

        path = os.path.join(DATA_DIR, f"debug_{label}_{int(_t.time())}.wav")
        # Convert float32 [-1, 1] back to int16 PCM
        pcm = (np.clip(audio_f32, -1.0, 1.0) * 32767).astype(np.int16)
        with _wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)       # int16
            w.setframerate(sr)
            w.writeframes(pcm.tobytes())
        return path
    except Exception:
        return None


def _is_hallucination(text: str) -> bool:
    """Return True if the transcription matches a known Whisper hallucination."""
    t = text.lower().strip()
    if len(t) <= 1:
        return True
    for phrase in WHISPER_HALLUCINATION_BLACKLIST:
        if phrase in t:
            return True
    # Repetition detector — same word 3+ times in a row = decode loop
    words = t.split()
    if len(words) >= 6:
        for i in range(len(words) - 2):
            if words[i] == words[i + 1] == words[i + 2]:
                return True
    return False


def transcribe_audio(audio_np, source_sr: int = 16000,
                     vad_filter: bool = False,
                     debug_label: str = "unknown",
                     min_words: int = 0) -> "str | None":
    """Thread-safe transcription. Takes a float32 numpy array.

    Args:
        audio_np    : float32 mono samples, any sample rate
        source_sr   : sample rate of audio_np. Resampled to 16kHz internally.
        vad_filter  : enable Silero VAD pre-filter. True for always-on mic
                      paths (web, background transcriber). False for
                      user-initiated recording (mic button press).
        debug_label : tag for debug wav dumps on failure.
        min_words   : reject results with fewer words (0 = no filter).
    """
    model = get_model()
    if model is None:
        return None

    audio_16k = _resample(audio_np, source_sr, 16000)

    try:
        with model_lock:
            segments, info = model.transcribe(
                audio_16k,
                beam_size=WHISPER_BEAM_SIZE,
                language="en",
                vad_filter=vad_filter,
            )
            segments = list(segments)

        # ── Confidence filtering: reject segments Whisper isn't sure about ──
        filtered = []
        for seg in segments:
            if seg.no_speech_prob > WHISPER_NO_SPEECH_THRESHOLD:
                log("whisper", f"rejected (no_speech={seg.no_speech_prob:.2f}): {seg.text!r}")
                continue
            if seg.avg_logprob < WHISPER_AVG_LOGPROB_THRESHOLD:
                log("whisper", f"rejected (logprob={seg.avg_logprob:.2f}): {seg.text!r}")
                continue
            filtered.append(seg)

        text = " ".join(seg.text for seg in filtered).strip()

        if not text:
            path = _save_debug_wav(audio_16k, 16000, debug_label)
            if path:
                log("whisper", f"all segments filtered out; audio saved to {path}")
            return None

        # Hallucination blacklist
        if _is_hallucination(text):
            log("whisper", f"rejected hallucination: {text!r}")
            return None

        # Minimum word count
        if min_words > 0 and len(text.split()) < min_words:
            log("whisper", f"rejected ({len(text.split())} words < {min_words}): {text!r}")
            return None

        return text
    except Exception as e:
        log("whisper", f"transcribe error: {e!r}")
        return None


def voice_to_text():
    """Record from mic until silence, transcribe with faster-whisper.

    Returns the transcript string or None on failure / silence.
    """
    if not AUDIO_OK:
        log("stt", "voice_to_text: pyaudio not available")
        return None

    RATE = 16000
    CHUNK = 1024
    SILENCE_THRESH = 500
    SILENCE_DURATION = 1.5
    MAX_RECORD = 15

    log("stt", f"voice_to_text: opening mic device_index={MIC_DEVICE_INDEX} @ {RATE}Hz")
    try:
        pa = pyaudio.PyAudio()
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                         input=True, input_device_index=MIC_DEVICE_INDEX,
                         frames_per_buffer=CHUNK)
    except Exception as e:
        log("stt", f"voice_to_text: FAILED to open mic — {e!r}")
        log("stt", "voice_to_text: try `python scripts/diagnose.py` to find the right MIC_DEVICE_INDEX")
        return None

    frames = []
    silent_chunks = 0
    chunks_for_silence = int(SILENCE_DURATION * RATE / CHUNK)
    max_chunks = int(MAX_RECORD * RATE / CHUNK)
    peak_rms = 0

    # Wall-clock pacer (same reason as AudioCapture — Intel Smart Sound
    # driver returns pyaudio.read() instantly instead of blocking at the
    # audio rate). Without this, "10s of recording" might be only 0.3s of
    # wall time, and whisper gets bogus stale buffer data.
    EXPECTED_DT = CHUNK / RATE         # 64ms at 16kHz/1024
    import time as _t
    next_deadline = _t.time()
    real_start_t = _t.time()

    for _ in range(max_chunks):
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
        except Exception as e:
            log("stt", f"voice_to_text: stream.read error — {e!r}")
            break
        frames.append(data)
        samples = np.frombuffer(data, dtype=np.int16)
        rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
        if rms > peak_rms:
            peak_rms = rms
        if rms < SILENCE_THRESH:
            silent_chunks += 1
        else:
            silent_chunks = 0
        if silent_chunks >= chunks_for_silence and len(frames) > chunks_for_silence + 5:
            break

        # Throttle so we read at real audio rate even if driver returns
        # data instantly.
        next_deadline += EXPECTED_DT
        sleep_amt = next_deadline - _t.time()
        if sleep_amt > 0:
            _t.sleep(sleep_amt)
        else:
            next_deadline = _t.time()

    stream.stop_stream()
    stream.close()
    pa.terminate()

    real_elapsed = _t.time() - real_start_t
    duration_s = len(frames) * CHUNK / RATE
    log("stt", f"voice_to_text: recorded {len(frames)} chunks, "
        f"{duration_s:.1f}s of audio over {real_elapsed:.1f}s wall-time, "
        f"peak RMS={peak_rms:.0f} (silence_thresh={SILENCE_THRESH})")

    if len(frames) < 10:
        log("stt", "voice_to_text: too short, dropping")
        return None

    if peak_rms < SILENCE_THRESH:
        log("stt", "voice_to_text: peak RMS below silence threshold — mic may be muted, "
            "wrong device index, or gain too low")
        return None

    audio_data = b"".join(frames)
    audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

    if get_model() is None:
        log("stt", "voice_to_text: whisper model not loaded yet — waiting...")

    import time as _t
    t0 = _t.time()
    # Source rate is RATE (16kHz, what voice_to_text records at). VAD
    # pre-filter off — user explicitly clicked mic, no need to second-guess.
    result = transcribe_audio(audio_np, source_sr=RATE, vad_filter=False,
                              debug_label="mic_press")
    log("stt", f"voice_to_text: transcribed in {_t.time() - t0:.1f}s -> {result!r}")
    return result
