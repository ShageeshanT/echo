# JARVIS BUILD PROMPT — Paste This Into Claude Code

## Context
I have a working Tkinter UI for a Jarvis-style desktop assistant (`jarvis.py`). It has a 3D dot-globe, sidebar waveform visualizer, mic button, text input, and typewriter response display. Right now it has TWO placeholder functions that need to be wired up to real backends:

1. `call_ai_backend(text)` at line 332 — currently just returns a placeholder string
2. `voice_to_text()` at line 336 — currently uses Google speech_recognition (slow, inaccurate)

The app also needs a WAKE SYSTEM — it should start in sleep mode and wake when I double-clap my hands.

## What I Need You To Build

Wire up my jarvis.py with these backends and features to create a low-latency voice assistant:

---

### 1. BRAIN — Groq API (blazing fast LLM)
- **API Endpoint:** `https://api.groq.com/openai/v1/chat/completions`
- **My API Key:** `GROQ_API_KEY` *(I'll replace this with my actual key)*
- **Model:** `llama-3.3-70b-versatile`
- **System prompt:** "You are J.A.R.V.I.S., a personal AI assistant inspired by Iron Man's JARVIS. Be concise, helpful, witty, and conversational. Keep responses under 3 sentences unless asked for detail. Address the user as 'Sir' occasionally. You can help with PC tasks, answer questions, and assist with daily work."
- **Replace** the `call_ai_backend()` function to call Groq via `requests`
- Keep conversation history (last 10 messages) for context
- Handle errors gracefully — if Groq is down, return "I'm having trouble reaching my servers, Sir."

---

### 2. SPEECH-TO-TEXT — faster-whisper (local, fast)
- Install: `pip install faster-whisper`
- Use the `base` model (good balance of speed/accuracy on CPU)
- **Replace** the `voice_to_text()` function
- Record audio from mic using `pyaudio` (already imported in the project)
- Use silence detection — stop recording after 1.5 seconds of silence (threshold-based using RMS)
- Configure: `device="cpu"`, `compute_type="int8"` (my laptop has no dedicated GPU)
- Load the whisper model ONCE at startup (not every time voice_to_text is called) — store it as a global

---

### 3. TEXT-TO-SPEECH — MiniMax TTS API
- **API Endpoint:** `https://api.minimax.chat/v1/t2a_v2`
- **API Key:** `MINIMAX_API_KEY` *(I'll replace with my actual key)*
- **Group ID:** `MINIMAX_GROUP_ID` *(I'll replace with my actual group ID)*
- **Voice ID:** Use `"male-qn-qingse"` as default (or configurable)
- After getting the AI response text, send it to MiniMax TTS
- Play the returned audio using `pygame.mixer`
- Add a function `speak_response(text)` that:
  - Calls MiniMax TTS API with the text
  - Saves audio to a temp file (use `tempfile` module)
  - Plays it through speakers using pygame.mixer
  - Cleans up the temp file after playing
- Call `speak_response()` in a thread right after showing the text response in `_show_resp()`
- If TTS fails, just show text without audio (don't crash)

---

### 4. DOUBLE-CLAP WAKE SYSTEM (Critical Feature)

The app should start in **SLEEP MODE** and wake when I clap my hands twice.

**Sleep Mode behavior:**
- Globe renders in a dim/muted state (multiply dot brightness by 0.15)
- Status shows "SLEEPING" in dim color
- Input bar is disabled
- Mic button is disabled
- A subtle slow pulse animation on the globe (breathing effect)
- The existing `AudioCapture` class keeps running (so mic stays active for clap detection)

**Clap Detection — build into the existing AudioCapture class:**
- Do NOT use a separate library or a second mic stream
- Add clap detection logic inside the existing `_loop` method of `AudioCapture`
- Detect a "clap" as a sudden spike where RMS jumps above a threshold (e.g., RMS > 0.15) and the spike is short-lived (< 200ms)
- Also apply a bandpass filter (200Hz-3200Hz) to focus on clap frequencies and ignore speech/music
- Detect "double clap" as two claps within 300-700ms of each other
- After detecting double clap, set a flag `self.double_clap_detected = True`
- The main app checks this flag each frame in `_animate()` and triggers wake-up
- After triggering, reset the flag and ignore further claps for 2 seconds (debounce)

**Wake-up sequence when double-clap detected:**
1. Set `self.is_sleeping = False`
2. Start playing the wake-up song MP3 (see section 5 below)
3. Transition globe from dim to full brightness over ~2 seconds (animate the brightness multiplier from 0.15 to 1.0)
4. Status changes to "WAKING UP" (cyan color) during the song, then "ONLINE" (green) after
5. Enable input bar and mic button
6. After ~20 seconds, fade the song volume from 100% to 0% over 3 seconds, then stop playback
7. Jarvis speaks: "Online and ready, Sir." (via MiniMax TTS)

**Going back to sleep:**
- User can say "go to sleep" or "sleep mode" — detected as a PC command
- OR automatic sleep after 5 minutes of no interaction (configurable)
- Sleep transition: fade globe brightness from 1.0 to 0.15 over 1 second, status → "SLEEPING"

---

### 5. WAKE-UP SONG PLAYBACK

**Config:**
```python
WAKE_SONG_PATH = r"C:\path\to\your\song.mp3"  # User sets this
WAKE_SONG_DURATION = 20  # seconds to play before fading
WAKE_SONG_FADE_TIME = 3  # seconds to fade out
```

**Implementation:**
- Use `pygame.mixer.music` for song playback (separate from TTS audio which uses `pygame.mixer.Sound` or a separate channel)
- On wake: `pygame.mixer.music.load(WAKE_SONG_PATH)` → `pygame.mixer.music.play()` → `pygame.mixer.music.set_volume(0.8)`
- Start a thread that:
  - Waits `WAKE_SONG_DURATION` seconds
  - Then gradually reduces volume from 0.8 to 0.0 over `WAKE_SONG_FADE_TIME` seconds (use small steps every 50ms)
  - Then calls `pygame.mixer.music.stop()`
- If the song file doesn't exist, skip it gracefully (just wake without music)
- TTS audio should still be able to play OVER the music (use separate pygame mixer channels)

---

### 6. PC CONTROL — Basic Commands
Add intent detection in `call_ai_backend()` — before sending to Groq, check if the user's text matches common PC commands:
- "open chrome" / "open browser" → `os.startfile("chrome")` or `os.system("start chrome")`
- "open notepad" → `os.system("start notepad")`
- "open calculator" → `os.system("start calc")`
- "open file explorer" → `os.system("start explorer")`
- "open spotify" → `os.system("start spotify")`
- "what time is it" → return current time directly
- "go to sleep" / "sleep mode" → trigger sleep mode, return "Going to sleep, Sir."
- "shut down" / "exit" → close the app
- For anything else, fall through to Groq API
- Use simple keyword matching (no NLP needed), case-insensitive

---

## Architecture Flow
```
[SLEEP MODE] — Globe dimmed, listening for claps only
        ↓ (double clap detected)
[WAKE UP] — Play song, animate globe to full, enable UI
        ↓ (song fades after 20s, "Online and ready, Sir.")
[ACTIVE MODE] — Full Jarvis experience
        ↓
User speaks → faster-whisper STT (~0.5-1s)
    → check for PC commands (instant)
    → if not: send to Groq API (~0.3-0.5s)
    → display response with typewriter effect
    → speak response via MiniMax TTS (~1-2s)
        ↓ (5 min idle OR "go to sleep")
[SLEEP MODE] — Back to dimmed state
```

---

## Config Section (add near top of jarvis.py after imports)
```python
# ---- Configuration ----
GROQ_API_KEY = "GROQ_API_KEY"  # Replace with your Groq key
GROQ_MODEL = "llama-3.3-70b-versatile"

MINIMAX_API_KEY = "MINIMAX_API_KEY"  # Replace with your MiniMax key
MINIMAX_GROUP_ID = "MINIMAX_GROUP_ID"  # Replace with your MiniMax group ID
MINIMAX_VOICE_ID = "male-qn-qingse"  # MiniMax voice

WHISPER_MODEL = "base"  # Options: tiny, base, small, medium

WAKE_SONG_PATH = r"C:\Users\YourName\Music\jarvis_wake.mp3"  # Replace with your MP3 path
WAKE_SONG_DURATION = 20  # seconds before fade starts
WAKE_SONG_FADE_TIME = 3  # seconds to fade out

SLEEP_TIMEOUT = 300  # seconds of inactivity before auto-sleep (5 min)

conversation_history = []
MAX_HISTORY = 10
```

---

## Requirements — add to requirements.txt
```
faster-whisper
pyaudio
numpy
Pillow
requests
pygame
SpeechRecognition
```

---

## Critical Implementation Notes

1. **Keep the existing UI code EXACTLY as-is** — only modify/add backend functions and add sleep/wake state management to the `JarvisApp` class
2. **Add `is_sleeping` state** to `JarvisApp.__init__()` — starts as `True`
3. **Add `brightness_multiplier`** to `JarvisApp.__init__()` — starts at `0.15`, target `1.0` when awake
4. **Modify `_animate()`** to:
   - Smoothly interpolate `brightness_multiplier` toward target each frame
   - Pass `brightness_multiplier` to the globe render (multiply the final brightness array)
   - Check `self.audio.double_clap_detected` flag and trigger wake-up
   - Check idle timeout for auto-sleep
5. **Modify `_on_submit()` and `_on_mic()`** to return early if `is_sleeping`
6. **Initialize pygame.mixer** at app startup: `pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)` — do this before mainloop
7. **Load whisper model once** at startup in a background thread (takes a few seconds to download first time)
8. **My laptop** is an HP ZBook Firefly 14 — NO dedicated GPU, Windows OS
9. **faster-whisper MUST** use `device="cpu"`, `compute_type="int8"`
10. The app should still work even if internet is down (STT works offline, just skip Groq and TTS)
11. Don't break the existing animation, globe, sidebar, or title bar — they're working perfectly
12. **Add `last_interaction_time`** to track idle time for auto-sleep
13. **Threading:** TTS playback, song fade, and whisper model loading must run in separate daemon threads so they don't block the UI
14. **pygame audio channels:** Use `pygame.mixer.music` for the wake song and `pygame.mixer.Sound` on a separate channel for TTS so they can overlap

---

## State Diagram
```
App Start → SLEEPING (globe dim, clap detection active)
    → Double Clap → WAKING (song plays, globe brightens)
        → ~20s later → ONLINE (song faded, "Ready Sir", full UI)
            → User interacts → PROCESSING/LISTENING/RESPONDING
            → 5min idle OR "go to sleep" → SLEEPING
```

## File Structure After Build
```
jarvis ui/
├── jarvis.py          (modified with all backends)
├── run.bat            (existing)
├── requirements.txt   (new)
└── README.md          (optional — setup instructions)
```
