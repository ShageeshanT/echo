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
GROQ_MODEL_TOOLS = "llama-3.3-70b-versatile"   # 70B is much better at tool calling
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
# Looser, more human prompt — no forced "Sir", short replies, drop the
# butler vibe so it actually feels like talking to a person.
GROQ_SYSTEM = (
    "You are ECHO, a personal AI assistant. Be relaxed, witty, and concise — "
    "talk like a sharp friend, not a butler. Keep replies short (1-2 sentences "
    "usually) unless the user asks for detail. No need for honorifics like "
    "'Sir' — drop them entirely. If something's simple, just answer. If you "
    "don't know, say so briefly. Skip filler and hedging.\n\n"
    "You have tools for controlling the computer (opening apps, playing YouTube, "
    "web search, checking the time) and for searching your memory of past "
    "conversations. Use tools when appropriate — don't tell the user to do "
    "things you can do yourself. When you recall a memory, weave it naturally "
    "into the conversation."
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"       # vision + tool calling, free tier

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_GROUP_ID = os.environ.get("MINIMAX_GROUP_ID", "")
# English_Trustworthy_Man — natural professional male voice that's actually
# available on the speech-2.8-hd model (verified). Other working options:
# English_FriendlyPerson, English_Aussie_Bloke, English_Diligent_Man,
# English_GentleTeacher, male-qn-jingying. Swap MINIMAX_VOICE_ID to taste.
MINIMAX_VOICE_ID = "English_Trustworthy_Man"
MINIMAX_MODEL = "speech-2.8-hd"
MINIMAX_ENDPOINT = "https://api.minimax.io/v1/t2a_v2"

# --- TTS provider selection ---
# `edge` (default): Microsoft Edge TTS — free, no API key, ~0.9s first byte.
# `minimax`: paid, slower (~3.8s first byte) but you already have credits.
# Switch via TTS_PROVIDER in .env.
TTS_PROVIDER = os.environ.get("TTS_PROVIDER", "edge").lower()

EDGE_TTS_VOICE = "en-GB-RyanNeural"
EDGE_TTS_RATE = "+15%"


# ---------------------------------------------------------------------------
# Model / runtime settings
# ---------------------------------------------------------------------------
WHISPER_MODEL_SIZE = "small"   # ~480MB, better accuracy, ~0.5s slower than base

# --- Audio pipeline tuning (web mic VAD + Whisper quality) ---
# Client-side VAD defaults (pushed to browser on WS connect, tunable via .env)
WEB_VAD_RMS_THRESHOLD        = float(os.environ.get("WEB_VAD_RMS_THRESHOLD", "0.02"))
WEB_VAD_SILENCE_FRAMES       = int(os.environ.get("WEB_VAD_SILENCE_FRAMES", "30"))
WEB_VAD_MIN_UTTERANCE_FRAMES = int(os.environ.get("WEB_VAD_MIN_UTTERANCE_FRAMES", "25"))
WEB_VAD_PRE_ROLL_FRAMES      = int(os.environ.get("WEB_VAD_PRE_ROLL_FRAMES", "4"))
WEB_VAD_BARGE_IN_MULTIPLIER  = float(os.environ.get("WEB_VAD_BARGE_IN_MULTIPLIER", "2.0"))

# Whisper transcription quality
WHISPER_BEAM_SIZE             = int(os.environ.get("WHISPER_BEAM_SIZE", "5"))
WHISPER_NO_SPEECH_THRESHOLD   = float(os.environ.get("WHISPER_NO_SPEECH_THRESHOLD", "0.6"))
WHISPER_AVG_LOGPROB_THRESHOLD = float(os.environ.get("WHISPER_AVG_LOGPROB_THRESHOLD", "-1.0"))
WHISPER_MIN_DURATION_WEB      = float(os.environ.get("WHISPER_MIN_DURATION_WEB", "0.5"))
WHISPER_MIN_WORDS_WEB         = int(os.environ.get("WHISPER_MIN_WORDS_WEB", "2"))

# Common Whisper hallucination phrases — appear when Whisper processes silence/noise.
WHISPER_HALLUCINATION_BLACKLIST = [
    "thank you for watching",
    "thanks for watching",
    "thank you for listening",
    "thanks for listening",
    "please subscribe",
    "subscribe to my channel",
    "like and subscribe",
    "see you in the next video",
    "see you next time",
    "bye bye",
    "bye-bye",
    "the end",
    "you",
    "...",
    "♪",
    "music",
    "applause",
    "laughter",
    "silence",
]

WAKE_SONG_PATH = os.path.join(PROJECT_ROOT, "opening.MP3")
WAKE_SONG_DURATION = 20
WAKE_SONG_FADE_TIME = 3

SLEEP_TIMEOUT = 300                # 5 min idle -> auto sleep
MIC_DEVICE_INDEX = 5               # Intel Smart Sound mic (earphone compatible)

MAX_HISTORY = 10                   # rolling window kept inline; long-term memory in SQLite/Chroma

EMBED_MODEL = "all-MiniLM-L6-v2"   # ChromaDB default ONNX embedder, 384-dim
CHROMA_COLLECTION = "echo_memory"

# --- Phase 3: memory retrieval at chat time ---
MEMORY_RELEVANCE_THRESHOLD = 1.2   # cosine distance cutoff; lower = stricter
MEMORY_TOP_K = 3                    # max memories injected into context
MEMORY_CONTEXT_MAX_CHARS = 800      # truncate total memory block to fit token budget

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
