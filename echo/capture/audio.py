"""
AudioCapture — continuous mic stream + 3-way wake detection.

Three triggers, all ORed together:
  1. Double clap   — RMS spike pattern (200ms wide, 150-800ms gap)
  2. Whistle       — sustained tonal peak in 500-4000Hz, high spectral purity
  3. Wake word     — buffer ~1.5s of speech, transcribe, match "hey echo"

Publishes RMS + bands on the bus so UI consumers can read without poking
into private state. Wake hits set `wake_detected = True` and are also
published as `audio.wake_detected`.

Phase 2 will add VAD-gated transcript streaming on this same loop.
"""
import threading
import time

import numpy as np

from echo import bus
from echo.config import AUDIO_OK, MIC_DEVICE_INDEX
from echo.stt.whisper import get_model

if AUDIO_OK:
    import pyaudio


class AudioCapture:
    def __init__(self):
        self.rms = 0.0
        self.running = False
        self.bands = [0.0] * 8
        # Wake detection state
        self.wake_detected = False
        self._clap_times = []
        self._last_wake_trigger = 0.0
        self._rms_history = []
        self._rms_baseline = 0.005
        # Whistle state
        self._whistle_frames = 0
        self._WHISTLE_FRAMES_NEEDED = 6
        # Wake word buffer
        self._wake_buf = []
        self._wake_buf_frames = 0
        self._WAKE_BUF_MAX = 30
        self._wake_checking = False

    def start(self):
        if not AUDIO_OK:
            return
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.running = False

    def _loop(self):
        try:
            pa = pyaudio.PyAudio()
            st = pa.open(format=pyaudio.paInt16, channels=1, rate=44100,
                         input=True, input_device_index=MIC_DEVICE_INDEX,
                         frames_per_buffer=2048)
            while self.running:
                data = st.read(2048, exception_on_overflow=False)
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float64)
                self.rms = float(np.sqrt(np.mean(samples ** 2)) / 32768)

                # FFT bands for visualizer
                fft = np.abs(np.fft.rfft(samples))[:256]
                bs = len(fft) // 8
                self.bands = [
                    float(np.mean(fft[i * bs:(i + 1) * bs])) / 40000 for i in range(8)
                ]
                bus.publish("audio.rms", self.rms)

                now = time.time()
                full_fft = np.abs(np.fft.rfft(samples))

                # ========== CLAP DETECTION (RMS spike) ==========
                self._rms_history.append(self.rms)
                if len(self._rms_history) > 50:
                    self._rms_history.pop(0)
                sorted_rms = sorted(self._rms_history)
                baseline_idx = max(1, int(len(sorted_rms) * 0.6))
                self._rms_baseline = max(0.003, sorted_rms[baseline_idx - 1])

                spike_threshold = self._rms_baseline * 4.0
                is_spike = self.rms > spike_threshold and self.rms > 0.015

                if is_spike:
                    if not self._clap_times or (now - self._clap_times[-1]) > 0.1:
                        self._clap_times.append(now)

                self._clap_times = [t for t in self._clap_times if now - t < 1.5]

                if len(self._clap_times) >= 2:
                    gap = self._clap_times[-1] - self._clap_times[-2]
                    if 0.15 <= gap <= 0.8:
                        if now - self._last_wake_trigger > 2.5:
                            self.wake_detected = True
                            self._last_wake_trigger = now
                            self._clap_times.clear()
                            bus.publish("audio.wake_detected", "clap")

                # ========== WHISTLE DETECTION (tonal peak) ==========
                freq_res = 44100 / len(samples)
                bin_500 = int(500 / freq_res)
                bin_4000 = int(4000 / freq_res)

                whistle_band = full_fft[bin_500:bin_4000]
                if len(whistle_band) > 0 and self.rms > 0.008:
                    peak_val = np.max(whistle_band)
                    mean_val = np.mean(whistle_band)
                    purity = peak_val / mean_val if mean_val > 0 else 0
                    is_whistle = purity > 6 and peak_val > 5000 and self.rms > 0.01

                    if is_whistle:
                        self._whistle_frames += 1
                    else:
                        self._whistle_frames = max(0, self._whistle_frames - 2)

                    if self._whistle_frames >= self._WHISTLE_FRAMES_NEEDED:
                        if now - self._last_wake_trigger > 2.5:
                            self.wake_detected = True
                            self._last_wake_trigger = now
                            bus.publish("audio.wake_detected", "whistle")
                        self._whistle_frames = 0
                else:
                    self._whistle_frames = max(0, self._whistle_frames - 1)

                # ========== WAKE WORD: "hey echo" ==========
                whisper_model = get_model()
                if self.rms > 0.008 and whisper_model is not None:
                    self._wake_buf.append(samples.copy())
                    self._wake_buf_frames += 1
                else:
                    if self._wake_buf_frames > 5:
                        self._wake_buf_frames = self._WAKE_BUF_MAX  # force check

                if (self._wake_buf_frames >= self._WAKE_BUF_MAX
                        and not self._wake_checking
                        and whisper_model is not None):
                    buf_copy = list(self._wake_buf)
                    self._wake_buf.clear()
                    self._wake_buf_frames = 0
                    self._wake_checking = True

                    def _check_wake(audio_chunks, model):
                        try:
                            audio_np = np.concatenate(audio_chunks).astype(np.float32) / 32768.0
                            segments, _ = model.transcribe(
                                audio_np, beam_size=1, language="en", vad_filter=True,
                            )
                            text = " ".join(s.text for s in segments).lower().strip()
                            wake_phrases = ["hey echo", "hey eco", "hey eko",
                                            "hey iko", "a echo", "hey e cho",
                                            "hey ekko"]
                            for phrase in wake_phrases:
                                if phrase in text:
                                    inner_now = time.time()
                                    if inner_now - self._last_wake_trigger > 3.0:
                                        self.wake_detected = True
                                        self._last_wake_trigger = inner_now
                                        bus.publish("audio.wake_detected", "wakeword")
                                    break
                        except Exception:
                            pass
                        finally:
                            self._wake_checking = False

                    threading.Thread(target=_check_wake, args=(buf_copy, whisper_model), daemon=True).start()

                if len(self._wake_buf) > 60:
                    self._wake_buf = self._wake_buf[-30:]

            st.stop_stream()
            st.close()
            pa.terminate()
        except Exception:
            self.running = False
