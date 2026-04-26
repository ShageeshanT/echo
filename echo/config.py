"""
Central config — paths, API keys, model names, feature flags.

Loads .env at import time. Initializes pygame.mixer so PYGAME_OK is reliable
before any TTS module is imported. Detects optional libs (pyaudio, pygame,
faster-whisper, edge-tts, pyttsx3, psutil) so the rest of the codebase can
just check the boolean flag.
"""
import os

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ECHO_PKG_DIR = os.path.dirname(os.path.abspath(__file__))      # .../echo/
PROJECT_ROOT = os.path.dirname(ECHO_PKG_DIR)                   # .../jarvis ui/
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
SQLITE_PATH = os.path.join(DATA_DIR, "echo.db")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma")
os.makedirs(DATA_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# .env loader (no python-dotenv dep)
# ---------------------------------------------------------------------------
def _load_dotenv():
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)


_load_dotenv()


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
GROQ_SYSTEM = (
    "You are E.C.H.O., a personal AI assistant inspired by Iron Man's JARVIS. "
    "Be concise, helpful, witty, and conversational. Keep responses under 3 sentences "
    "unless asked for detail. Address the user as 'Sir' occasionally. "
    "You can help with PC tasks, answer questions, and assist with daily work."
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash-exp"   # vision + tool calling, free tier

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_GROUP_ID = os.environ.get("MINIMAX_GROUP_ID", "")
MINIMAX_VOICE_ID = "English_Lucky_Robot"
MINIMAX_MODEL = "speech-2.8-hd"
MINIMAX_ENDPOINT = "https://api.minimax.io/v1/t2a_v2"

EDGE_TTS_VOICE = "en-GB-RyanNeural"
EDGE_TTS_RATE = "+15%"


# ---------------------------------------------------------------------------
# Model / runtime settings
# ---------------------------------------------------------------------------
WHISPER_MODEL_SIZE = "base"

WAKE_SONG_PATH = os.path.join(PROJECT_ROOT, "opening.MP3")
WAKE_SONG_DURATION = 20
WAKE_SONG_FADE_TIME = 3

SLEEP_TIMEOUT = 300                # 5 min idle -> auto sleep
MIC_DEVICE_INDEX = 5               # Intel Smart Sound mic (earphone compatible)

MAX_HISTORY = 10                   # rolling window kept inline; long-term memory in SQLite/Chroma

EMBED_MODEL = "all-MiniLM-L6-v2"   # ChromaDB default ONNX embedder, 384-dim
CHROMA_COLLECTION = "echo_memory"


# ---------------------------------------------------------------------------
# Feature-flag detection — every module checks these instead of try/except'ing
# ---------------------------------------------------------------------------
AUDIO_OK = False
try:
    import pyaudio  # noqa: F401
    AUDIO_OK = True
except ImportError:
    pass

PYGAME_OK = False
try:
    import pygame
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
    PYGAME_OK = True
except Exception:
    pass

EDGE_TTS_OK = False
try:
    import edge_tts  # noqa: F401
    EDGE_TTS_OK = True
except ImportError:
    pass

PYTTSX_OK = False
try:
    import pyttsx3  # noqa: F401
    PYTTSX_OK = True
except ImportError:
    pass

WHISPER_OK = False
try:
    from faster_whisper import WhisperModel  # noqa: F401
    WHISPER_OK = True
except ImportError:
    pass

PSUTIL_OK = False
try:
    import psutil  # noqa: F401
    PSUTIL_OK = True
except ImportError:
    pass
