"""
Keyword intent dispatch — deterministic fast-path for commands that must be
instant (no LLM round-trip latency).

Phase 4 moved YouTube, app launch, web search, time, and date to LLM tool
calling. This module now only handles:
  - Mute/unmute (hardware toggle, must be instant)
  - Sleep/exit sentinels (state transitions the UI handles)
"""
from echo.actions import system


def dispatch(user_text: str) -> str | None:
    lower = user_text.lower().strip()

    # Mute toggle — must be instant, no LLM latency.
    if "mute" in lower or "unmute" in lower:
        result = system.toggle_mute()
        if result == "muted":
            return "Muted."
        if result == "unmuted":
            return "Unmuted."

    # Sleep / exit sentinels
    if any(w in lower for w in ["go to sleep", "sleep mode", "go sleep"]):
        return "__SLEEP__"
    if any(w in lower for w in ["shut down", "exit", "close echo", "quit"]):
        return "__EXIT__"

    return None
