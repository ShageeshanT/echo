"""Top-level speak orchestrator + wake-up song player."""

import os
import threading
import time

from echo.config import (
    PYGAME_OK,
    WAKE_SONG_DURATION,
    WAKE_SONG_FADE_TIME,
    WAKE_SONG_PATH,
)
from echo.tts.edge import speak_edge_tts
from echo.tts.minimax import speak_minimax
from echo.tts.pyttsx import speak_pyttsx3

if PYGAME_OK:
    import pygame


def speak_response(text: str):
    """Speak text — MiniMax first, Edge TTS second, pyttsx3 last. Non-blocking."""
    def _tts_thread():
        if not speak_minimax(text):
            if not speak_edge_tts(text):
                speak_pyttsx3(text)
    threading.Thread(target=_tts_thread, daemon=True).start()


def play_wake_song():
    """Play the wake-up song and fade out after WAKE_SONG_DURATION seconds."""
    if not PYGAME_OK or not os.path.exists(WAKE_SONG_PATH):
        return

    def _song_thread():
        try:
            pygame.mixer.music.load(WAKE_SONG_PATH)
            pygame.mixer.music.set_volume(0.8)
            pygame.mixer.music.play()
            time.sleep(WAKE_SONG_DURATION)
            steps = int(WAKE_SONG_FADE_TIME / 0.05)
            vol = 0.8
            for _ in range(steps):
                vol -= 0.8 / steps
                pygame.mixer.music.set_volume(max(0, vol))
                time.sleep(0.05)
            pygame.mixer.music.stop()
        except Exception:
            pass

    threading.Thread(target=_song_thread, daemon=True).start()
