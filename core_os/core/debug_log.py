"""Live audio-subsystem status registry.

Each subsystem (TTS, SFX, music, audio stream) sets/clears a line here while
it's actually active. An on-screen overlay (the emulator's speaker
placeholder) reads only what's currently active -- not a scrolling log --
so it always reflects "what's making sound right now", not history.

core_os.core sits below both backends/ and packages/, so either side can
depend on this without a layering violation.

set_voice_detail/get_voice_detail is a second, separate registry alongside
the plain-line one above -- only SynthEngine (player.py) uses it, to hand
the emulator's Voice Monitor window (voice_monitor.py) a per-voice
breakdown (label + held/releasing state) instead of the one summary line
the speaker placeholder has room for.
"""

from __future__ import annotations

import threading
from typing import Dict, List

_lock = threading.Lock()
_status: Dict[str, str] = {}
_voice_detail: Dict[str, List[Dict[str, str]]] = {}


def set_active(key: str, line: str) -> None:
    with _lock:
        _status[key] = line


def clear_active(key: str) -> None:
    with _lock:
        _status.pop(key, None)


def get_active_lines() -> List[str]:
    with _lock:
        return list(_status.values())


def set_voice_detail(key: str, voices: List[Dict[str, str]]) -> None:
    with _lock:
        _voice_detail[key] = voices


def clear_voice_detail(key: str) -> None:
    with _lock:
        _voice_detail.pop(key, None)


def get_voice_detail() -> Dict[str, List[Dict[str, str]]]:
    with _lock:
        return {key: list(voices) for key, voices in _voice_detail.items()}
