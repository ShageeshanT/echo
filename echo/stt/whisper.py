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
    WHISPER_MODEL_SIZE,
    WHISPER_OK,
)

_model = None
_load_lock = threading.Lock()

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
            _model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
        except Exception:
            pass


# Kick off loading in the background — don't block import.
threading.Thread(target=_load, daemon=True).start()


def get_model():
    """Return the loaded model or None if not ready / unavailable."""
    return _model


def voice_to_text():
    """Record from mic until silence, transcribe with faster-whisper.

    Returns the transcript string or None on failure / silence.
    """
    if not AUDIO_OK:
        return None

    RATE = 16000
    CHUNK = 1024
    SILENCE_THRESH = 500
    SILENCE_DURATION = 1.5
    MAX_RECORD = 15

    try:
        pa = pyaudio.PyAudio()
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                         input=True, input_device_index=MIC_DEVICE_INDEX,
                         frames_per_buffer=CHUNK)
    except Exception:
        return None

    frames = []
    silent_chunks = 0
    chunks_for_silence = int(SILENCE_DURATION * RATE / CHUNK)
    max_chunks = int(MAX_RECORD * RATE / CHUNK)

    for _ in range(max_chunks):
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
        except Exception:
            break
        frames.append(data)
        samples = np.frombuffer(data, dtype=np.int16)
        rms = np.sqrt(np.mean(samples.astype(np.float64) ** 2))
        if rms < SILENCE_THRESH:
            silent_chunks += 1
        else:
            silent_chunks = 0
        if silent_chunks >= chunks_for_silence and len(frames) > chunks_for_silence + 5:
            break

    stream.stop_stream()
    stream.close()
    pa.terminate()

    if len(frames) < 10:
        return None

    audio_data = b"".join(frames)
    audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

    model = get_model()
    if model is None:
        return None
    try:
        segments, _ = model.transcribe(
            audio_np, beam_size=1, language="en", vad_filter=True,
        )
        text = " ".join(seg.text for seg in segments).strip()
        return text if text else None
    except Exception:
        return None
