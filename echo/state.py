"""
Shared mutable runtime state.

Tk root reference lives here so non-UI code (action handlers that need to
drop topmost when launching apps) can reach it without circular imports.
The UI sets `app_root` once at startup.
"""
from typing import Optional
import tkinter as tk

app_root: Optional[tk.Misc] = None

# True while the UI is in sleep mode. Read by capture/audio.py to gate the
# expensive wake-word transcription path, and by workers/transcriber.py to
# pause always-on capture. Updated by JarvisApp on _wake_up / _go_to_sleep.
is_sleeping: bool = True


def set_app_root(root: tk.Misc) -> None:
    global app_root
    app_root = root


def set_sleeping(sleeping: bool) -> None:
    global is_sleeping
    is_sleeping = sleeping


def drop_topmost() -> None:
    """Briefly drop -topmost so a launched app appears in front of ECHO."""
    if app_root is None:
        return
    try:
        app_root.attributes("-topmost", False)
    except Exception:
        pass
