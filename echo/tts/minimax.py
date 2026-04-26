"""MiniMax speech-2.8-hd — natural, expressive English voice (primary TTS)."""

import os
import tempfile
import time

import requests

from echo.config import (
    MINIMAX_API_KEY,
    MINIMAX_ENDPOINT,
    MINIMAX_MODEL,
    MINIMAX_VOICE_ID,
    PYGAME_OK,
)

if PYGAME_OK:
    import pygame


def speak_minimax(text: str) -> bool:
    """Synthesize via MiniMax and play through pygame. Returns True on success."""
    if not PYGAME_OK or not MINIMAX_API_KEY:
        return False
    try:
        resp = requests.post(
            MINIMAX_ENDPOINT,
            headers={
                "Authorization": f"Bearer {MINIMAX_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MINIMAX_MODEL,
                "text": text,
                "stream": False,
                "voice_setting": {
                    "voice_id": MINIMAX_VOICE_ID,
                    "speed": 1.0,
                    "vol": 1.0,
                    "pitch": 0,
                },
                "audio_setting": {
                    "sample_rate": 44100,
                    "bitrate": 128000,
                    "format": "mp3",
                    "channel": 1,
                },
                "output_format": "hex",
            },
            timeout=20,
        )
        if resp.status_code != 200:
            return False
        data = resp.json()
        if data.get("base_resp", {}).get("status_code", -1) != 0:
            return False
        audio_hex = data.get("data", {}).get("audio", "")
        if not audio_hex:
            return False

        audio_bytes = bytes.fromhex(audio_hex)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name
        try:
            sound = pygame.mixer.Sound(tmp_path)
            sound.play()
            time.sleep(sound.get_length() + 0.3)
        except Exception:
            pass
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        return True
    except Exception:
        return False
