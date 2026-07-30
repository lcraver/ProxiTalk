"""core_os's own held-key repeat tracker, independent of the old OS's
utils/key_repeat.py."""

from __future__ import annotations

import time


class KeyRepeat:
    """Tracks held keys and emits accelerating repeat events.

    Usage:
        self.key_repeat = KeyRepeat()

        # in onkeydown:
        self.key_repeat.press(keycode)

        # in onkeyup:
        self.key_repeat.release(keycode)

        # in update():
        for keycode in self.key_repeat.tick():
            self.handle_key(keycode)

    Only keys passed to press() are tracked — ignore the rest in onkeydown as normal.
    """

    def __init__(
        self,
        initial_delay=0.4,   # seconds before first repeat fires
        initial_interval=0.1, # seconds between early repeats
        min_interval=0.03,    # fastest repeat interval (at full acceleration)
        acceleration=0.85,    # interval multiplied by this after each repeat
    ):
        self.initial_delay = initial_delay
        self.initial_interval = initial_interval
        self.min_interval = min_interval
        self.acceleration = acceleration
        self._held = {}  # keycode -> {press_time, last_fire, interval}

    def press(self, keycode):
        """Register a key as held. Call from onkeydown."""
        now = time.time()
        self._held[keycode] = {
            "press_time": now,
            "last_fire": now,
            "interval": self.initial_interval,
        }

    def release(self, keycode):
        """Unregister a held key. Call from onkeyup."""
        self._held.pop(keycode, None)

    def release_all(self):
        """Clear all held keys (useful on focus loss or mode change)."""
        self._held.clear()

    def tick(self):
        """Call from update(). Returns list of keycodes that should repeat this tick."""
        now = time.time()
        fires = []
        for keycode, state in self._held.items():
            if now - state["press_time"] < self.initial_delay:
                continue
            if now - state["last_fire"] >= state["interval"]:
                fires.append(keycode)
                state["last_fire"] = now
                state["interval"] = max(self.min_interval, state["interval"] * self.acceleration)
        return fires
