"""
Brain — LLM orchestration.

Phase 1: keyword intent first, then Groq for everything else (current behavior).
Phase 4: replace with full LLM tool calling — same module, swap implementations.
"""

from echo.brain.groq_client import call_ai_backend  # noqa: F401
from echo.brain.streaming import call_ai_backend_stream  # noqa: F401
from echo.brain import history  # noqa: F401
