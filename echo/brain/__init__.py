"""
Brain — LLM orchestration.

Phase 3: memory-augmented chat (ChromaDB context injection).
Phase 4: LLM tool calling (Groq 70B with structured tools).
"""

from echo.brain.groq_client import call_ai_backend  # noqa: F401
from echo.brain.streaming import call_ai_backend_stream  # noqa: F401
from echo.brain import history  # noqa: F401
