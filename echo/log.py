"""
Tiny console logger — single-user dev tool, no log levels, no rotation.

Default ON in dev. Set ECHO_DEBUG=0 in .env to silence. Output goes to
stderr so it doesn't interfere with anything ECHO writes to stdout.

Usage:
    from echo.log import log
    log("transcriber", "utterance flushed, %.1fs" % duration)
"""
import os
import sys
import time

_ENABLED = os.environ.get("ECHO_DEBUG", "1") not in ("0", "false", "False", "")


def log(tag: str, msg: str) -> None:
    if not _ENABLED:
        return
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [{tag}] {msg}", file=sys.stderr, flush=True)


def is_enabled() -> bool:
    return _ENABLED
