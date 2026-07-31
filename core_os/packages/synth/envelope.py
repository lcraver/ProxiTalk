"""ADSREnvelope — amplitude-over-time shape for a rendered note, matching
Playdate's synth:setADSR(attack, decay, sustain, release) argument shape
exactly: attack/decay/release are durations in seconds, sustain is a 0..1
level (not a duration). A note's audible length is `note_duration +
release` -- it keeps ringing out past its nominal on-time, same model
Playdate uses, rather than being hard-cut at note_duration."""

from __future__ import annotations


class ADSREnvelope:
    def __init__(self, attack: float = 0.01, decay: float = 0.05, sustain: float = 0.8, release: float = 0.1) -> None:
        self.attack = max(0.0, attack)
        self.decay = max(0.0, decay)
        self.sustain = max(0.0, min(1.0, sustain))
        self.release = max(0.0, release)

    def total_duration(self, note_duration: float) -> float:
        return note_duration + self.release

    def amplitude_at(self, t: float, note_duration: float) -> float:
        if t < 0:
            return 0.0
        if t < self.attack:
            return (t / self.attack) if self.attack > 0 else 1.0
        if t < self.attack + self.decay:
            if self.decay <= 0:
                return self.sustain
            decay_t = (t - self.attack) / self.decay
            return 1.0 - decay_t * (1.0 - self.sustain)
        if t < note_duration:
            return self.sustain
        release_t = t - note_duration
        if release_t >= self.release:
            return 0.0
        if self.release <= 0:
            return 0.0
        return self.sustain * (1.0 - release_t / self.release)
