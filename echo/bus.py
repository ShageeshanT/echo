"""
Event bus — Omi's pusher pattern, collapsed to in-process.

Capture -> bus -> workers -> memory.  Subscribers register a callback per
topic; publishers fire-and-forget.  Thread-safe (uses a lock around the
subscriber dict) so audio threads, the Tk main loop, and asyncio workers
can all publish freely.

Topics we'll use as we build out phases:
    audio.rms              live RMS for UI
    audio.wake_detected    clap/whistle/wakeword hit
    transcript.partial     streaming whisper interim
    transcript.final       a finalized utterance
    memory.extracted       post-processing produced a memory
    memory.action_item     post-processing extracted an action item
    screen.changed         perceptual hash diff (Phase 5)
    proactive.suggest      proactive worker wants to whisper something
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


@dataclass
class Event:
    topic: str
    payload: Any = None
    ts: float = field(default_factory=time.time)


_subscribers: Dict[str, List[Callable[[Event], None]]] = defaultdict(list)
_lock = threading.Lock()


def subscribe(topic: str, callback: Callable[[Event], None]) -> Callable[[], None]:
    """Register callback for topic. Returns an unsubscribe function."""
    with _lock:
        _subscribers[topic].append(callback)

    def _unsub():
        with _lock:
            try:
                _subscribers[topic].remove(callback)
            except ValueError:
                pass

    return _unsub


def publish(topic: str, payload: Any = None) -> None:
    """Fire-and-forget publish. Subscriber exceptions are swallowed so a bad
    plugin can't take down the bus."""
    with _lock:
        callbacks = list(_subscribers.get(topic, ()))
    if not callbacks:
        return
    evt = Event(topic=topic, payload=payload)
    for cb in callbacks:
        try:
            cb(evt)
        except Exception:
            pass


def topics() -> List[str]:
    with _lock:
        return list(_subscribers.keys())
