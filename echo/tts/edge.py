"""Edge TTS fallback (free Microsoft cloud voices)."""

import asyncio
import os
import tempfile
import time

from echo.config import EDGE_TTS_OK, EDGE_TTS_RATE, EDGE_TTS_VOICE, PYGAME_OK

if EDGE_TTS_OK:
    import edge_tts
if PYGAME_OK:
    import pygame


def speak_edge_tts(text: str) -> bool:
    if not EDGE_TTS_OK or not PYGAME_OK:
        return False
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        tmp_path = tmp.name

        async def _gen():
            tts = edge_tts.Communicate(text, EDGE_TTS_VOICE, rate=EDGE_TTS_RATE)
            await tts.save(tmp_path)

        asyncio.run(_gen())

        if os.path.getsize(tmp_path) > 0:
            sound = pygame.mixer.Sound(tmp_path)
            sound.play()
            time.sleep(sound.get_length() + 0.3)
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return True
    except Exception:
        pass
    return False
