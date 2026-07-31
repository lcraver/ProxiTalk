"""Master-bus audio effects, mirroring the shape of Playdate's
playdate.sound effects (bitcrusher/onepolefilter/delayline/overdrive/
ringmodulator) -- each is a small stateful per-sample processor
(`.process(sample: float) -> float`, input and output both -1..1),
chained together and applied to the FINAL mixed signal in
player.py's SynthEngine._mix_chunk, after the sqrt-headroom scaling but
BEFORE the tanh safety limiter -- so an effect (especially Overdrive,
which is a deliberate musical drive control, a different knob from the
limiter's fixed anti-clip role) can push the signal hot and the limiter
still guarantees it never actually hard-clips regardless of what the
chain did to it.

This is master-bus only (one chain applied to the whole mix), not
per-voice routing -- Playdate supports routing effects onto individual
sound sources via channels; that's a meaningfully bigger routing system
this doesn't attempt."""

from __future__ import annotations

import math
from typing import List


class Bitcrusher:
    """Two independent degradations, both optional: amplitude quantized to
    2**bit_depth levels (bit_depth=16 is effectively a no-op), and/or a
    sample-and-hold that only updates every `sample_rate_divisor` calls
    (1 = no-op, 4 = effectively a 22050/4 ~= 5512Hz sample rate)."""

    def __init__(self, bit_depth: int = 8, sample_rate_divisor: int = 1) -> None:
        self.bit_depth = max(1, min(16, bit_depth))
        self.sample_rate_divisor = max(1, sample_rate_divisor)
        self._held_value = 0.0
        self._counter = 0

    def process(self, sample: float) -> float:
        if self._counter % self.sample_rate_divisor == 0:
            levels = 2 ** self.bit_depth
            self._held_value = round(sample * levels / 2) / (levels / 2)
        self._counter += 1
        return max(-1.0, min(1.0, self._held_value))


class OnePoleFilter:
    """Single-pole IIR low-pass or high-pass. Standard textbook one-pole
    coefficients (not a resonant/multi-pole filter -- gentle 6dB/octave
    rolloff, matches Playdate's onepolefilter, which is exactly this and
    no more)."""

    def __init__(self, cutoff_hz: float, sample_rate: int = 22050, mode: str = "lowpass") -> None:
        if mode not in ("lowpass", "highpass"):
            raise ValueError(f"mode must be 'lowpass' or 'highpass', got {mode!r}")
        self.mode = mode
        rc = 1.0 / (2.0 * math.pi * max(1.0, cutoff_hz))
        dt = 1.0 / sample_rate
        self._alpha_lp = dt / (rc + dt)
        self._alpha_hp = rc / (rc + dt)
        self._prev_in = 0.0
        self._prev_out = 0.0

    def process(self, sample: float) -> float:
        if self.mode == "lowpass":
            out = self._prev_out + self._alpha_lp * (sample - self._prev_out)
        else:
            out = self._alpha_hp * (self._prev_out + sample - self._prev_in)
        self._prev_in = sample
        self._prev_out = out
        return out


class Delay:
    """Ring-buffer echo. `feedback` controls how many repeats decay in
    (0 = single echo, closer to 1 = long decaying trail -- kept < 1 to
    avoid runaway gain); `mix` is dry/wet balance."""

    def __init__(self, delay_seconds: float, feedback: float = 0.3, mix: float = 0.3, sample_rate: int = 22050) -> None:
        self.feedback = max(0.0, min(0.95, feedback))
        self.mix = max(0.0, min(1.0, mix))
        size = max(1, int(round(delay_seconds * sample_rate)))
        self._buffer: List[float] = [0.0] * size
        self._pos = 0

    def process(self, sample: float) -> float:
        delayed = self._buffer[self._pos]
        self._buffer[self._pos] = sample + delayed * self.feedback
        self._pos = (self._pos + 1) % len(self._buffer)
        return sample * (1.0 - self.mix) + delayed * self.mix


class Overdrive:
    """Deliberate musical drive/waveshaping, distinct from the mixer's own
    fixed anti-clip tanh limiter (player.py's _mix_chunk) -- this is a
    user-dialed effect (gain + dry/wet), not a safety net; the limiter
    still runs after this regardless of how hot Overdrive pushes the
    signal."""

    def __init__(self, gain: float = 2.0, mix: float = 1.0) -> None:
        self.gain = max(0.0, gain)
        self.mix = max(0.0, min(1.0, mix))

    def process(self, sample: float) -> float:
        driven = math.tanh(sample * self.gain)
        return sample * (1.0 - self.mix) + driven * self.mix


class RingModulator:
    """Multiplies the signal by a sine carrier -- classic metallic/bell-
    like ring-mod character. Carrier phase is free-running (its own
    counter, not tied to any voice), matching Playdate's ringmodulator."""

    def __init__(self, carrier_hz: float, sample_rate: int = 22050) -> None:
        self.carrier_hz = carrier_hz
        self._sample_rate = sample_rate
        self._phase = 0.0

    def process(self, sample: float) -> float:
        carrier = math.sin(2.0 * math.pi * self._phase)
        self._phase = (self._phase + self.carrier_hz / self._sample_rate) % 1.0
        return sample * carrier


class EffectsChain:
    def __init__(self) -> None:
        self._effects = []

    def add(self, effect) -> None:
        self._effects.append(effect)

    def clear(self) -> None:
        self._effects.clear()

    def process(self, sample: float) -> float:
        for effect in self._effects:
            sample = effect.process(sample)
        return sample
