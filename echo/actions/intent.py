"""
Keyword intent dispatch — the pre-LLM filter from the original `call_ai_backend`.

Returns a string response for handled intents, or None to fall through to the
LLM. Two sentinel strings — "__SLEEP__" and "__EXIT__" — are returned for
state transitions the UI handles.

This whole module gets replaced in Phase 4 by LLM tool calling, but the
underlying handlers (apps, browser, system) stay.
"""
from echo.actions import apps, browser, system


def dispatch(user_text: str) -> str | None:
    lower = user_text.lower().strip()

    # Play something on YouTube — checked BEFORE generic open commands so
    # "play me a song on YouTube" doesn't fall into the YouTube-opener branch.
    if any(w in lower for w in ["play", "put on", "play me"]):
        query = lower
        for prefix in ["play me", "play", "put on", "on youtube", "in youtube",
                       "youtube", "a song", "song", "some", "the", "open", "and"]:
            query = query.replace(prefix, "").strip()
        if query:
            browser.play_youtube(query)
            return f"Playing {query} on YouTube, Sir."

    # App / URL launchers
    if any(w in lower for w in ["open", "launch", "start", "run"]):
        for keywords, cmd, name, use_brave in apps.APP_MAP:
            if any(kw in lower for kw in keywords):
                try:
                    if use_brave:
                        apps.open_brave(cmd)
                    else:
                        apps.open_app(cmd)
                    return f"Opening {name} for you, Sir."
                except Exception:
                    return f"I couldn't open {name}, Sir."

    # Web search
    if any(w in lower for w in ["search for", "google", "look up", "search"]):
        query = lower
        for prefix in ["search for", "google", "look up", "search"]:
            query = query.replace(prefix, "").strip()
        if query:
            browser.web_search(query)
            return f"Searching for {query}, Sir."

    # Time
    if "what time" in lower or "current time" in lower or lower == "time":
        return f"It's currently {system.current_time()}, Sir."

    # Date
    if "what date" in lower or "today's date" in lower or "what day" in lower:
        return f"Today is {system.current_date()}, Sir."

    # Mute toggle
    if "mute" in lower or "unmute" in lower:
        result = system.toggle_mute()
        if result == "muted":
            return "Muted, Sir."
        if result == "unmuted":
            return "Unmuted, Sir."
        # On failure, fall through to LLM

    # Sleep / exit sentinels
    if any(w in lower for w in ["go to sleep", "sleep mode", "go sleep"]):
        return "__SLEEP__"
    if any(w in lower for w in ["shut down", "exit", "close echo", "quit"]):
        return "__EXIT__"

    return None
