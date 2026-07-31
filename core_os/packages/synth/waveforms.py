"""Oscillator waveforms: phase in [0, 1) (one full cycle) -> amplitude in
[-1, 1]. Mirrors animation/easing.py's EASINGS shape (a dict of named pure
functions) so a Synth can swap waveforms by string name the same way a
Tween swaps easing curves. The classic 5 (sine/square/triangle/sawtooth/
noise) -- skipping Playdate's exotic PO-prefixed hardware-oscillator
emulations (POPhase/PODigital/POVosim), which don't mean anything outside
Playdate's own hardware."""

from __future__ import annotations

import math
import random
from typing import Callable, Dict


def sine(phase: float) -> float:
    return math.sin(2.0 * math.pi * phase)


def square(phase: float) -> float:
    return 1.0 if phase < 0.5 else -1.0


def triangle(phase: float) -> float:
    # -1 (at 0) -> 0 (at 0.25) -> 1 (at 0.5) -> 0 (at 0.75) -> -1 (at 1.0),
    # continuous across the phase=0.5 wrap (a naive two-branch piecewise
    # version breaks continuity right there -- verified by hand before
    # settling on this formula, since a jump would click audibly).
    return 2.0 * abs(2.0 * (phase - math.floor(phase + 0.5))) - 1.0


def sawtooth(phase: float) -> float:
    return 2.0 * phase - 1.0


def noise(phase: float) -> float:
    # Genuinely random per sample -- phase is unused, kept only so every
    # entry in WAVEFORMS shares the same fn(phase) -> amplitude signature.
    return random.uniform(-1.0, 1.0)


WAVEFORMS: Dict[str, Callable[[float], float]] = {
    "sine": sine,
    "square": square,
    "triangle": triangle,
    "sawtooth": sawtooth,
    "noise": noise,
}
