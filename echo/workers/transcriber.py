"""
Always-on transcriber.

Subscribes to `audio.chunk`, segments speech via simple energy-based VAD,
runs faster-whisper on each utterance, publishes `transcript.final`. Same
role as the always-on listen path in Omi (`backend/routers/transcribe.py` +
`backend/utils/stt/streaming.py`), collapsed to a single subscriber.

Lifecycle is bus-driven via two public functions:
  enable()   -> start consuming chunks (called by JarvisApp on _wake_up)
  disable()  -> stop and clear buffer (called on _go_to_sleep / _on_mic)

VAD strategy is intentionally dumb (RMS threshold + silence-frame counter)
for Phase 2. Phase 3 swaps in webrtcvad / silero if energy false-positives
become a problem.
"""
import threading
import time

import numpy as np

from echo import bus, state
from echo.config import (
    AUDIO_OK,
    TRANSCRIBE_MAX_UTTERANCE_CHUNKS,
    TRANSCRIBE_MIN_UTTERANCE_CHUNKS,
    TRANSCRIBE_RMS_THRESHOLD,
    TRANSCRIBE_SILENCE_CHUNKS,
    WHISPER_OK,
)
from echo.log import log
from echo.stt.whisper import get_model, transcribe_audio

_buffer_lock = threading.Lock()
_enabled = False
_buffer = []          # list of int16 numpy arrays (one per audio chunk)
_silence_count = 0    # consecutive sub-threshold chunks since last speech

# RMS observability — track peak/recent so we can log periodically while
# enabled. Helps diagnose "is my mic gain too low for the threshold".
_obs_lock = threading.Lock()
_obs_peak = 0.0
_obs_chunks = 0
_obs_last_log = 0.0
_OBS_LOG_INTERVAL = 5.0  # seconds between "still listening, peak RMS=..." logs


def enable() -> None:
    """Start consuming audio chunks. Idempotent — safe to call repeatedly."""
    global _enabled, _buffer, _silence_count
    global _obs_peak, _obs_chunks, _obs_last_log
    with _buffer_lock:
        was = _enabled
        _enabled = True
        _buffer = []
        _silence_count = 0
    with _obs_lock:
        _obs_peak = 0.0
        _obs_chunks = 0
        _obs_last_log = time.time()
    if not was:
        model_state = "loaded" if get_model() is not None else "still loading"
        log("transcriber", f"ENABLED (whisper {model_state}, "
            f"rms_threshold={TRANSCRIBE_RMS_THRESHOLD})")


def disable() -> None:
    """Stop consuming and drop any in-flight buffer."""
    global _enabled, _buffer, _silence_count
    with _buffer_lock:
        was = _enabled
        _enabled = False
        _buffer = []
        _silence_count = 0
    if was:
        log("transcriber", "DISABLED")


def is_enabled() -> bool:
    return _enabled


def _spawn_transcribe(snapshot) -> None:
    """Run whisper on `snapshot` in a daemon thread; publish on success."""

    def _run():
        try:
            samples = np.concatenate(snapshot).astype(np.float32) / 32768.0
            duration = len(samples) / 44100.0
            if duration < 0.5:
                return
            t0 = time.time()
            log("transcriber", f"flushing utterance, {duration:.1f}s of audio...")
            # AudioCapture records at 44.1kHz — declare it so whisper helper
            # resamples to 16kHz before transcribing.
            text = transcribe_audio(samples, source_sr=44100, vad_filter=False,
                                    debug_label="always_on")
            elapsed = time.time() - t0
            if not text:
                log("transcriber", f"whisper returned empty after {elapsed:.1f}s")
                return
            log("transcriber", f"transcribed in {elapsed:.1f}s: {text!r}")
            bus.publish("transcript.final", {
                "text": text,
                "ts": time.time(),
                "duration_s": duration,
            })
        except Exception as e:
            log("transcriber", f"ERROR in whisper thread: {e!r}")

    threading.Thread(target=_run, daemon=True).start()


def _on_chunk(evt) -> None:
    """Subscriber callback for `audio.chunk`. Must stay LIGHT — runs inline
    on the AudioCapture thread. All heavy work goes to a worker thread."""
    global _buffer, _silence_count
    global _obs_peak, _obs_chunks, _obs_last_log

    # Cheap top-level gates first — avoid taking the lock when we can't
    # possibly use the chunk anyway.
    if not _enabled or state.is_sleeping:
        return

    samples = evt.payload
    if samples is None or len(samples) == 0:
        return

    # Normalized RMS (matches AudioCapture's own self.rms calc).
    rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)) / 32768.0)
    is_speech = rms > TRANSCRIBE_RMS_THRESHOLD

    # RMS observability — periodic peak report so the user can see whether
    # their mic is producing levels above TRANSCRIBE_RMS_THRESHOLD.
    now = time.time()
    with _obs_lock:
        if rms > _obs_peak:
            _obs_peak = rms
        _obs_chunks += 1
        if now - _obs_last_log > _OBS_LOG_INTERVAL:
            log("transcriber",
                f"observing mic: peak RMS={_obs_peak:.4f} over last "
                f"{_OBS_LOG_INTERVAL:.0f}s (threshold={TRANSCRIBE_RMS_THRESHOLD})")
            _obs_peak = 0.0
            _obs_chunks = 0
            _obs_last_log = now

    snapshot = None
    with _buffer_lock:
        # Drop pure-silence chunks before we've heard anything, so an idle
        # mic doesn't grow the buffer slowly forever.
        if not _buffer and not is_speech:
            return

        _buffer.append(samples)
        if is_speech:
            _silence_count = 0
        else:
            _silence_count += 1

        # Two flush triggers: long silence after enough speech, OR cap hit.
        long_silence = (
            _silence_count >= TRANSCRIBE_SILENCE_CHUNKS
            and len(_buffer) >= TRANSCRIBE_MIN_UTTERANCE_CHUNKS
        )
        cap_hit = len(_buffer) >= TRANSCRIBE_MAX_UTTERANCE_CHUNKS

        if long_silence or cap_hit:
            snapshot = _buffer
            _buffer = []
            _silence_count = 0

    if snapshot is not None:
        _spawn_transcribe(snapshot)


# Register subscriber at import time. The transcriber stays disabled until
# JarvisApp calls enable() after the wake-up sequence completes.
if AUDIO_OK and WHISPER_OK:
    bus.subscribe("audio.chunk", _on_chunk)
