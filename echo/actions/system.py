"""System-level actions: time, date, mute toggle."""

from datetime import datetime


def current_time() -> str:
    return datetime.now().strftime("%I:%M %p")


def current_date() -> str:
    return datetime.now().strftime("%A, %B %d, %Y")


def toggle_mute() -> str | None:
    """Toggle system audio mute. Returns 'muted' / 'unmuted' or None on failure."""
    try:
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        was_muted = volume.GetMute()
        volume.SetMute(not was_muted, None)
        return "unmuted" if was_muted else "muted"
    except Exception:
        return None
