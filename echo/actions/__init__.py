"""
OS / app control actions.

`intent.dispatch(text)` is the single entrypoint — it does the keyword
matching that brain/groq_client falls back to before hitting the LLM.
In Phase 4 this whole module gets replaced by a tool registry the LLM
can call directly, but the underlying handlers (`apps.open_brave`,
`browser.play_youtube`, etc.) stay the same.
"""

from echo.actions.intent import dispatch  # noqa: F401
