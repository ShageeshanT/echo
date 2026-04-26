"""TTS — MiniMax (primary) -> Edge TTS -> pyttsx3 (offline fallback)."""

from echo.tts.speak import speak_response, play_wake_song  # noqa: F401
from echo.tts.minimax import speak_minimax  # noqa: F401
from echo.tts.edge import speak_edge_tts  # noqa: F401
from echo.tts.pyttsx import speak_pyttsx3  # noqa: F401
