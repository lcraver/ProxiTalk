"""Easing curves: t in [0, 1] -> t' in [0, 1], the shape a Tween's progress
follows rather than moving at a constant rate. Shared by Tween and anything
else in this package that takes an `easing=` argument by name (see
EASINGS)."""

from __future__ import annotations

from typing import Callable, Dict


def linear(t: float) -> float:
    return t


def ease_in(t: float) -> float:
    return t * t


def ease_out(t: float) -> float:
    return t * (2.0 - t)


def ease_in_out(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


# "back" easings overshoot past 0/1 before settling -- a small backswing
# then snap forward (ease_in_back), or a small overshoot past the target
# then settle back (ease_out_back), giving a springier, less mechanical
# feel than the plain quadratic curves above. Standard Penner constants:
# c1 tunes how far past 0/1 the overshoot swings.
_C1 = 1.70158
_C3 = _C1 + 1.0
_C2 = _C1 * 1.525


def ease_in_back(t: float) -> float:
    return _C3 * t * t * t - _C1 * t * t


def ease_out_back(t: float) -> float:
    t -= 1.0
    return 1.0 + _C3 * t * t * t + _C1 * t * t


def ease_in_out_back(t: float) -> float:
    if t < 0.5:
        t2 = 2.0 * t
        return (t2 * t2 * ((_C2 + 1.0) * t2 - _C2)) / 2.0
    t2 = 2.0 * t - 2.0
    return (t2 * t2 * ((_C2 + 1.0) * t2 + _C2) + 2.0) / 2.0


EASINGS: Dict[str, Callable[[float], float]] = {
    "linear": linear,
    "ease_in": ease_in,
    "ease_out": ease_out,
    "ease_in_out": ease_in_out,
    "ease_in_back": ease_in_back,
    "ease_out_back": ease_out_back,
    "ease_in_out_back": ease_in_out_back,
}
