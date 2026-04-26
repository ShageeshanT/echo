"""
Shared mutable runtime state.

Tk root reference lives here so non-UI code (action handlers that need to
drop topmost when launching apps) can reach it without circular imports.
The UI sets `app_root` once at startup.
"""
from typing import Optional
import tkinter as tk

app_root: Optional[tk.Misc] = None


def set_app_root(root: tk.Misc) -> None:
    global app_root
    app_root = root


def drop_topmost() -> None:
    """Briefly drop -topmost so a launched app appears in front of ECHO."""
    if app_root is None:
        return
    try:
        app_root.attributes("-topmost", False)
    except Exception:
        pass
