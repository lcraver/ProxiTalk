"""Synth — plain, no I/O (same reasoning as geometry's classes and
sprite.Sprite: nothing here touches gfx/audio hardware, so it's exposed
directly rather than via a factory). render_note() is pure computation,
fully testable standalone with no audio hardware, same as Sprite/geometry
were before it. Actual playback is SynthEngine's job (player.py) -- kept
separate because that's the one piece that has to touch the audio_output
driver (see player.py's docstring for why it's a real-time mixer rather
than a simple per-note queue)."""

from __future__ import annotations

import struct

from core_os.packages.synth.envelope import ADSREnvelope
from core_os.packages.synth.notes import note_to_frequency
from core_os.packages.synth.waveforms import WAVEFORMS


class Synth:
    def __init__(self, waveform: str = "square") -> None:
        self.set_waveform(waveform)
        self.envelope = ADSREnvelope()
        self.volume = 1.0

    def set_waveform(self, name: str) -> None:
        if name not in WAVEFORMS:
            raise ValueError(f"Unknown waveform {name!r}, expected one of {sorted(WAVEFORMS)}")
        self.waveform_name = name
        self._waveform_fn = WAVEFORMS[name]

    def waveform_amplitude(self, phase: float) -> float:
        """Public per-sample evaluator -- used by SynthEngine's real-time
        mixer (player.py), which needs to call this once per sample per
        active voice rather than render a whole buffer up front."""
        return self._waveform_fn(phase)

    def set_adsr(self, attack: float, decay: float, sustain: float, release: float) -> None:
        self.envelope = ADSREnvelope(attack, decay, sustain, release)

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))

    def render_note(self, pitch, duration: float, velocity: float = 1.0, sample_rate: int = 22050) -> bytes:
        """Returns int16 little-endian mono PCM bytes (matches
        audio/engine.py's wrap_raw_audio_as_wav convention). Length is
        (duration + envelope.release) seconds -- the note rings out past
        its nominal on-time (see envelope.py's docstring)."""
        frequency = note_to_frequency(pitch)
        total_duration = self.envelope.total_duration(duration)
        n = max(0, int(round(total_duration * sample_rate)))
        amplitude_scale = self.volume * max(0.0, min(1.0, velocity))
        frames = bytearray(n * 2)
        for i in range(n):
            t = i / sample_rate
            phase = (frequency * t) % 1.0
            sample = self._waveform_fn(phase) * self.envelope.amplitude_at(t, duration) * amplitude_scale
            value = int(max(-32768, min(32767, round(sample * 32767))))
            struct.pack_into("<h", frames, i * 2, value)
        return bytes(frames)
