"""
Brain entrypoint — keyword intent first, then Groq Llama 3.3 70b.

call_ai_backend(text) -> reply | "__SLEEP__" | "__EXIT__"

Phase 4 will replace this with structured tool calling against Gemini /
Llama-3.3 — but the public signature stays so the UI doesn't change.
"""
import requests

from echo.actions import intent
from echo.brain import history
from echo.config import GROQ_API_KEY, GROQ_ENDPOINT, GROQ_MODEL, GROQ_SYSTEM


def call_ai_backend(user_text: str) -> str:
    # 1. Try the deterministic keyword dispatcher first — instant, offline.
    handled = intent.dispatch(user_text)
    if handled is not None:
        return handled

    # 2. Fall through to Groq.
    history.append("user", user_text)
    messages = [{"role": "system", "content": GROQ_SYSTEM}] + history.get()

    try:
        resp = requests.post(
            GROQ_ENDPOINT,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": messages,
                "max_tokens": 300,
                "temperature": 0.7,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            reply = resp.json()["choices"][0]["message"]["content"]
            history.append("assistant", reply)
            return reply
        return "I'm having trouble reaching my servers, Sir."
    except Exception:
        return "I'm having trouble reaching my servers, Sir."
