"""
ECHO mic + whisper diagnostic.

Run from the project root:
    python scripts/diagnose.py

What it does:
  1. Lists every pyaudio input device with its index, channels, default-rate.
  2. Records 5 seconds from echo.config.MIC_DEVICE_INDEX, prints peak RMS.
  3. Confirms faster-whisper loaded; runs transcription on the recording.
  4. Tells you whether echo.config.MIC_DEVICE_INDEX needs to change.
"""
import os
import sys
import time

# Make sure echo/ is importable when running from project root or scripts/.
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT_ROOT)

from echo import config  # noqa: E402  (also triggers .env load + pygame init)


def list_input_devices():
    import pyaudio
    print("=" * 72)
    print("INPUT DEVICES")
    print("=" * 72)
    print(f"  configured MIC_DEVICE_INDEX = {config.MIC_DEVICE_INDEX}")
    print()
    pa = pyaudio.PyAudio()
    default_in = None
    try:
        default_in = pa.get_default_input_device_info()
    except Exception:
        pass
    n = pa.get_device_count()
    found = []
    for i in range(n):
        try:
            info = pa.get_device_info_by_index(i)
        except Exception:
            continue
        if info.get("maxInputChannels", 0) <= 0:
            continue
        marker = ""
        if default_in and info["index"] == default_in["index"]:
            marker += " [SYSTEM DEFAULT]"
        if i == config.MIC_DEVICE_INDEX:
            marker += " [<- ECHO uses this]"
        print(f"  [{i:3d}] {info['name']!r:<55} "
              f"{int(info['maxInputChannels'])}ch @ "
              f"{int(info['defaultSampleRate'])}Hz{marker}")
        found.append(i)
    pa.terminate()
    print()
    if config.MIC_DEVICE_INDEX not in found:
        print(f"  ⚠  MIC_DEVICE_INDEX={config.MIC_DEVICE_INDEX} is NOT a valid input device.")
        print(f"     Pick one of {found} and update echo/config.py")
        print()
    return found


def test_record_and_transcribe():
    import numpy as np
    import pyaudio

    print("=" * 72)
    print(f"RECORDING 5 seconds from device_index={config.MIC_DEVICE_INDEX}")
    print("  (TALK NOW — say something like 'hello echo this is a test')")
    print("=" * 72)
    RATE = 16000
    CHUNK = 1024
    SECONDS = 5
    pa = pyaudio.PyAudio()
    try:
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                         input=True, input_device_index=config.MIC_DEVICE_INDEX,
                         frames_per_buffer=CHUNK)
    except Exception as e:
        print(f"  ✗ FAILED to open mic: {e!r}")
        print("    The MIC_DEVICE_INDEX is wrong or the device is busy.")
        pa.terminate()
        return None

    frames = []
    peak = 0
    rms_samples = []
    for i in range(int(RATE / CHUNK * SECONDS)):
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
        except Exception as e:
            print(f"  ✗ stream.read error after {i} chunks: {e!r}")
            break
        frames.append(data)
        s = np.frombuffer(data, dtype=np.int16)
        rms = float(np.sqrt(np.mean(s.astype(np.float64) ** 2)))
        rms_samples.append(rms)
        if rms > peak:
            peak = rms
        # Live readout
        bar = "#" * min(40, int(rms / 50))
        sys.stdout.write(f"\r  RMS: {rms:6.0f}  |{bar:<40}|  ")
        sys.stdout.flush()
    print()
    stream.stop_stream()
    stream.close()
    pa.terminate()

    if not frames:
        print("  ✗ no frames recorded")
        return None

    avg_rms = sum(rms_samples) / max(1, len(rms_samples))
    norm_peak = peak / 32768.0
    norm_avg = avg_rms / 32768.0
    print(f"  peak raw RMS = {peak:.0f}      (normalized {norm_peak:.4f})")
    print(f"  avg  raw RMS = {avg_rms:.0f}    (normalized {norm_avg:.4f})")
    print(f"  TRANSCRIBE_RMS_THRESHOLD     = {config.TRANSCRIBE_RMS_THRESHOLD}")
    print()
    if norm_peak < config.TRANSCRIBE_RMS_THRESHOLD:
        print(f"  ⚠  peak normalized RMS ({norm_peak:.4f}) is BELOW the always-on threshold.")
        print(f"     Always-on transcription will never fire on your mic.")
        print(f"     Either (a) talk louder, (b) lower TRANSCRIBE_RMS_THRESHOLD in")
        print(f"     echo/config.py to about {norm_peak * 0.5:.4f}, or")
        print(f"     (c) try a different MIC_DEVICE_INDEX above.")
    else:
        print(f"  ✓ peak RMS is well above threshold — always-on should fire.")
    print()

    # Save the audio for re-test if needed
    audio_data = b"".join(frames)
    audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

    print("=" * 72)
    print("WHISPER")
    print("=" * 72)
    if not config.WHISPER_OK:
        print("  ✗ faster-whisper not installed")
        return None

    from echo.stt.whisper import _load, transcribe_audio, get_model
    print("  loading model (synchronous)...")
    t0 = time.time()
    _load()
    if get_model() is None:
        print(f"  ✗ model failed to load after {time.time() - t0:.1f}s")
        return None
    print(f"  ✓ loaded in {time.time() - t0:.1f}s")

    print("  transcribing the 5-second recording...")
    t0 = time.time()
    text = transcribe_audio(audio_np)
    dt = time.time() - t0
    print(f"  → result after {dt:.1f}s: {text!r}")
    print()
    if text:
        print("  ✓ end-to-end mic + whisper works.")
    else:
        print("  ⚠  whisper returned nothing. Either you didn't speak loud enough,")
        print("     or the mic is recording silence/noise. Re-run and talk into the mic.")
    return text


if __name__ == "__main__":
    print()
    devices = list_input_devices()
    print()
    test_record_and_transcribe()
    print()
