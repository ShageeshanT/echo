"""
Browser-driven actions — YouTube auto-play via DevTools JS injection,
web search via Brave Search.
"""

import threading
import time
import urllib.parse

from echo import bus
from echo.actions.apps import open_brave


def play_youtube(query: str) -> None:
    """Open YouTube search and click the first result via Ctrl+Shift+J -> JS."""
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
    open_brave(url)

    def _autoplay():
        try:
            import pyautogui
            pyautogui.PAUSE = 0.05
            time.sleep(4)  # let YouTube finish loading
            sx, sy = pyautogui.size()
            pyautogui.click(int(sx * 0.5), int(sy * 0.5))
            time.sleep(0.5)
            pyautogui.hotkey('ctrl', 'shift', 'j')
            time.sleep(1)
            cmd = "document.querySelector('a#video-title').click()"
            pyautogui.typewrite(cmd, interval=0.008)
            time.sleep(0.2)
            pyautogui.press('enter')
            time.sleep(0.5)
            pyautogui.hotkey('ctrl', 'shift', 'j')
        except Exception:
            pass

    threading.Thread(target=_autoplay, daemon=True).start()
    # Notify the bus that media will be playing through speakers — the web
    # frontend listens for this and pauses its mic so it doesn't transcribe
    # the song lyrics back to ECHO.
    bus.publish("media.playing", {"source": "youtube", "query": query})


def web_search(query: str) -> None:
    url = f"https://search.brave.com/search?q={urllib.parse.quote(query)}"
    open_brave(url)
