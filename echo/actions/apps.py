"""Brave-aware app launching."""

import json
import os
import subprocess

from echo.state import drop_topmost


def find_brave_profile(name: str = "Shagee") -> str:
    local = os.environ.get("LOCALAPPDATA", "")
    state_path = os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data", "Local State")
    if not os.path.exists(state_path):
        return "Default"
    try:
        with open(state_path, 'r', encoding='utf-8') as f:
            state = json.load(f)
        for folder, info in state.get("profile", {}).get("info_cache", {}).items():
            if info.get("name", "").lower() == name.lower():
                return folder
    except Exception:
        pass
    return "Default"


def find_brave_exe():
    paths = [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""),
                     "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


BRAVE_PROFILE_DIR = find_brave_profile("Shagee")
BRAVE_EXE = find_brave_exe()


def open_brave(url: str = None) -> None:
    """Open Brave with the user's profile, optionally to a URL."""
    drop_topmost()
    if BRAVE_EXE:
        args = [BRAVE_EXE, f'--profile-directory={BRAVE_PROFILE_DIR}']
        if url:
            args.append(url)
        subprocess.Popen(args)
    else:
        os.system(f'start "" "brave"' if not url else f'start "" "{url}"')


def open_app(cmd: str) -> None:
    """Run a shell app command, dropping topmost so it appears in front."""
    drop_topmost()
    os.system(cmd)


# Map of (keywords, command, friendly name, use_brave_flag).
APP_MAP = [
    (["brave", "browser", "chrome", "google"],         None,                          "Brave",         True),
    (["firefox"],                                       'start "" "firefox"',          "Firefox",       False),
    (["edge"],                                          'start "" "msedge"',           "Edge",          False),
    (["notepad"],                                       'start "" "notepad"',          "Notepad",       False),
    (["calculator", "calc"],                            'start "" "calc"',             "Calculator",    False),
    (["file explorer", "explorer", "files"],            'start "" "explorer"',         "File Explorer", False),
    (["spotify"],                                       'start "" "spotify"',          "Spotify",       False),
    (["terminal", "cmd", "command prompt"],             'start "" "cmd"',              "Terminal",      False),
    (["settings"],                                      'start ms-settings:',          "Settings",      False),
    (["task manager"],                                  'start "" "taskmgr"',          "Task Manager",  False),
    (["youtube"],                                       "https://youtube.com",         "YouTube",       True),
    (["whatsapp"],                                      'start "" "whatsapp"',         "WhatsApp",      False),
    (["discord"],                                       'start "" "discord"',          "Discord",       False),
    (["vscode", "vs code", "visual studio code"],       'start "" "code"',             "VS Code",       False),
]
