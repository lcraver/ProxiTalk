"""Tween — interpolates a single value (or an (x, y, ...) tuple) from
from_value to to_value over `duration` seconds, along an easing curve.

Must be advanced by calling update(dt) once per frame from an app's own
update() — there is no background-thread auto-animation here, since drawing
only ever happens safely on the single cooperative scheduler thread (see
core/scheduler.py). This mirrors why leds.blink()'s animation thread never
touches the display directly: if an app stops calling update(), the tween
simply stops advancing, nothing leaks or keeps running unattended."""

from __future__ import annotations

from typing import Callable, Optional, Tuple, Union

Number = Union[int, float]
Value = Union[Number, Tuple[Number, ...]]


def _interpolate(a: Value, b: Value, t: float) -> Value:
    if isinstance(a, tuple) and isinstance(b, tuple):
        return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))
    return a + (b - a) * t  # type: ignore[operator]


class Tween:
    def __init__(
        self,
        from_value: Value,
        to_value: Value,
        duration: float,
        easing: Callable[[float], float],
        on_complete: Optional[Callable[[], None]] = None,
    ) -> None:
        self.from_value = from_value
        self.to_value = to_value
        self.duration = duration
        self.easing = easing
        self.on_complete = on_complete
        self.elapsed = 0.0
        self.done = duration <= 0
        self.value: Value = to_value if self.done else from_value

    def update(self, dt: float) -> None:
        if self.done:
            return
        self.elapsed = min(self.elapsed + dt, self.duration)
        t = self.easing(self.elapsed / self.duration)
        self.value = _interpolate(self.from_value, self.to_value, t)
        if self.elapsed >= self.duration:
            self.done = True
            if self.on_complete:
                self.on_complete()
