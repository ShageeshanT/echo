"""
Browser frontend for ECHO.

The Python backend (echo/) stays unchanged. This package adds a FastAPI
server that:
  - Serves the static HTML/JS/CSS at /
  - Exposes a WebSocket at /ws that bridges echo.bus events <-> browser

Run with:
    python -m echo.web.server
or use run-web.bat
"""
