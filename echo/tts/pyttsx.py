"""Final fallback — Windows SAPI via pyttsx3 (works offline)."""

import threading

from echo.config import PYTTSX_OK

if PYTTSX_OK:
    import pyttsx3

_tts_lock = threading.Lock()


def speak_pyttsx3(text: str):
    if not PYTTSX_OK:
        return
    with _tts_lock:
        try:
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            for v in voices:
                if 'david' in v.name.lower():
                    engine.setProperty('voice', v.id)
                    break
            engine.setProperty('rate', 175)
            engine.setProperty('volume', 0.9)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception:
            pass
