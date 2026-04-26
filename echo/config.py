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
# Llama 3.1 8B Instant — first-token in ~150-250ms vs 400-600ms on 70B,
# plenty smart for casual chat. Drop back to 70b-versatile for harder
# requests later if needed (or have brain pick by complexity).
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
# Looser, more human prompt — no forced "Sir", short replies, drop the
# butler vibe so it actually feels like talking to a person.
GROQ_SYSTEM = (
    "You are ECHO, a personal AI assistant. Be relaxed, witty, and concise — "
    "talk like a sharp friend, not a butler. Keep replies short (1-2 sentences "
    "usually) unless the user asks for detail. No need for honorifics like "
    "'Sir' — drop them entirely. If something's simple, just answer. If you "
    "don't know, say so briefly. Skip filler and hedging."
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"       # vision + tool calling, free tier

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_GROUP_ID = os.environ.get("MINIMAX_GROUP_ID", "")
# English_Magnetic_Voice — warm, conversational, sounds way more human.
# Other natural options: English_Trustworthy_Man, English_Confident_Man,
# English_Imaginative_Man. Swap MINIMAX_VOICE_ID to taste.
MINIMAX_VOICE_ID = "English_Magnetic_Voice"
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

# --- Phase 2: always-on transcription ---
# Each AudioCapture chunk is 2048 samples @ 44.1kHz = ~46.4ms.
# Tunes are deliberately a bit conservative — better to drop a "uh ok" than
# to wake whisper for every keyboard tap.
TRANSCRIBE_RMS_THRESHOLD       = 0.008   # normalized RMS floor for "speech present"
TRANSCRIBE_SILENCE_CHUNKS      = 13      # ~600ms of silence ends an utterance
TRANSCRIBE_MIN_UTTERANCE_CHUNKS = 16     # ~740ms minimum to bother transcribing
TRANSCRIBE_MAX_UTTERANCE_CHUNKS = 650    # ~30s maximum, force-flush long monologue

# --- Phase 3b: post-processing extractor ---
# Wake every N seconds, pull unprocessed transcripts, ask Gemini to extract
# memories + action items. Free-tier rate limit is 15 RPM, so 60s = 1 RPM.
POSTPROC_INTERVAL_SECS  = 60     # how often to check for new transcripts
POSTPROC_BATCH_SIZE     = 30     # max transcripts per LLM call (token-budget)
POSTPROC_MIN_TOTAL_CHARS = 50    # skip extraction if batch is too short


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
