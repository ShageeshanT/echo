"""
E.C.H.O. — Enhanced Cognitive Heuristic Operator
Entrypoint. All logic lives in the echo/ package.
"""
import ctypes

# Per-monitor DPI awareness must be set BEFORE tkinter is imported. Both echo
# and tkinter are imported below.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# Load config (.env, feature flags, pygame.mixer init) before anything else.
from echo import config  # noqa: F401, E402
from echo.ui.app import JarvisApp  # noqa: E402


if __name__ == "__main__":
    JarvisApp()
