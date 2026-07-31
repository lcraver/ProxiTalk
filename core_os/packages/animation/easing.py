"""Easing curves: t in [0, 1] -> t' in [0, 1], the shape a Tween's progress
follows rather than moving at a constant rate. Shared by Tween and anything
else in this package that takes an `easing=` argument by name (see
EASINGS)."""

from __future__ import annotations

import math
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


def ease_in_cubic(t: float) -> float:
    return t * t * t


def ease_out_cubic(t: float) -> float:
    t -= 1.0
    return t * t * t + 1.0


def ease_in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4.0 * t * t * t
    t = -2.0 * t + 2.0
    return 1.0 - (t * t * t) / 2.0


def ease_in_quart(t: float) -> float:
    return t * t * t * t


def ease_out_quart(t: float) -> float:
    t -= 1.0
    return 1.0 - t * t * t * t


def ease_in_out_quart(t: float) -> float:
    if t < 0.5:
        return 8.0 * t * t * t * t
    t = -2.0 * t + 2.0
    return 1.0 - (t * t * t * t) / 2.0


def ease_in_quint(t: float) -> float:
    return t * t * t * t * t


def ease_out_quint(t: float) -> float:
    t -= 1.0
    return 1.0 + t * t * t * t * t


def ease_in_out_quint(t: float) -> float:
    if t < 0.5:
        return 16.0 * t * t * t * t * t
    t = -2.0 * t + 2.0
    return 1.0 - (t * t * t * t * t) / 2.0


def ease_in_sine(t: float) -> float:
    return 1.0 - math.cos(t * math.pi / 2.0)


def ease_out_sine(t: float) -> float:
    return math.sin(t * math.pi / 2.0)


def ease_in_out_sine(t: float) -> float:
    return -(math.cos(math.pi * t) - 1.0) / 2.0


def ease_in_expo(t: float) -> float:
    return 0.0 if t <= 0.0 else 2.0 ** (10.0 * t - 10.0)


def ease_out_expo(t: float) -> float:
    return 1.0 if t >= 1.0 else 1.0 - 2.0 ** (-10.0 * t)


def ease_in_out_expo(t: float) -> float:
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    if t < 0.5:
        return (2.0 ** (20.0 * t - 10.0)) / 2.0
    return (2.0 - 2.0 ** (-20.0 * t + 10.0)) / 2.0


def ease_in_circ(t: float) -> float:
    return 1.0 - math.sqrt(1.0 - t * t)


def ease_out_circ(t: float) -> float:
    t -= 1.0
    return math.sqrt(1.0 - t * t)


def ease_in_out_circ(t: float) -> float:
    if t < 0.5:
        return (1.0 - math.sqrt(1.0 - (2.0 * t) ** 2)) / 2.0
    return (math.sqrt(1.0 - (-2.0 * t + 2.0) ** 2) + 1.0) / 2.0


# Elastic overshoots repeatedly (a spring settling) rather than "back"'s
# single overshoot -- c4/c5 are the standard easings.net constants tuning
# the oscillation period.
_ELASTIC_C4 = (2.0 * math.pi) / 3.0
_ELASTIC_C5 = (2.0 * math.pi) / 4.5


def ease_in_elastic(t: float) -> float:
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return -(2.0 ** (10.0 * t - 10.0)) * math.sin((t * 10.0 - 10.75) * _ELASTIC_C4)


def ease_out_elastic(t: float) -> float:
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return (2.0 ** (-10.0 * t)) * math.sin((t * 10.0 - 0.75) * _ELASTIC_C4) + 1.0


def ease_in_out_elastic(t: float) -> float:
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    if t < 0.5:
        return -((2.0 ** (20.0 * t - 10.0)) * math.sin((20.0 * t - 11.125) * _ELASTIC_C5)) / 2.0
    return ((2.0 ** (-20.0 * t + 10.0)) * math.sin((20.0 * t - 11.125) * _ELASTIC_C5)) / 2.0 + 1.0


def ease_out_bounce(t: float) -> float:
    n1 = 7.5625
    d1 = 2.75
    if t < 1.0 / d1:
        return n1 * t * t
    if t < 2.0 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


def ease_in_bounce(t: float) -> float:
    return 1.0 - ease_out_bounce(1.0 - t)


def ease_in_out_bounce(t: float) -> float:
    if t < 0.5:
        return (1.0 - ease_out_bounce(1.0 - 2.0 * t)) / 2.0
    return (1.0 + ease_out_bounce(2.0 * t - 1.0)) / 2.0


EASINGS: Dict[str, Callable[[float], float]] = {
    "linear": linear,
    "ease_in": ease_in,
    "ease_out": ease_out,
    "ease_in_out": ease_in_out,
    "ease_in_back": ease_in_back,
    "ease_out_back": ease_out_back,
    "ease_in_out_back": ease_in_out_back,
    "ease_in_cubic": ease_in_cubic,
    "ease_out_cubic": ease_out_cubic,
    "ease_in_out_cubic": ease_in_out_cubic,
    "ease_in_quart": ease_in_quart,
    "ease_out_quart": ease_out_quart,
    "ease_in_out_quart": ease_in_out_quart,
    "ease_in_quint": ease_in_quint,
    "ease_out_quint": ease_out_quint,
    "ease_in_out_quint": ease_in_out_quint,
    "ease_in_sine": ease_in_sine,
    "ease_out_sine": ease_out_sine,
    "ease_in_out_sine": ease_in_out_sine,
    "ease_in_expo": ease_in_expo,
    "ease_out_expo": ease_out_expo,
    "ease_in_out_expo": ease_in_out_expo,
    "ease_in_circ": ease_in_circ,
    "ease_out_circ": ease_out_circ,
    "ease_in_out_circ": ease_in_out_circ,
    "ease_in_elastic": ease_in_elastic,
    "ease_out_elastic": ease_out_elastic,
    "ease_in_out_elastic": ease_in_out_elastic,
    "ease_in_bounce": ease_in_bounce,
    "ease_out_bounce": ease_out_bounce,
    "ease_in_out_bounce": ease_in_out_bounce,
}
