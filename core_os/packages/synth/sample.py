"""Sample — a loaded audio buffer for playback through SynthEngine
alongside (and mixed together with) oscillator voices, mirroring
Playdate's playdate.sound.sample. Mono, float -1..1 internally regardless
of source bit depth, so playback math (player.py's _SampleVoice) never
needs to know the original format."""

from __future__ import annotations

import struct
import wave
from typing import List, Optional


class Sample:
    def __init__(self, frames: List[float], sample_rate: int, name: Optional[str] = None) -> None:
        self.frames = frames
        self.sample_rate = sample_rate
        self.name = name

    @classmethod
    def load_wav(cls, path: str) -> "Sample":
        with wave.open(path, "rb") as wav_file:
            n_channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            raw = wav_file.readframes(wav_file.getnframes())

        if sample_width != 2:
            raise ValueError(f"Only 16-bit WAV files are supported, got {sample_width * 8}-bit ({path!r})")

        values = struct.unpack(f"<{len(raw) // 2}h", raw)
        if n_channels == 1:
            mono = values
        elif n_channels == 2:
            # Downmix by averaging L/R pairs -- this engine's mixer/output
            # stream is mono throughout (see player.py/audio_output.py),
            # so a stereo source has to collapse somewhere, and doing it
            # once at load time is simpler than carrying two channels
            # through every downstream sample_at() call.
            mono = [(values[i] + values[i + 1]) / 2.0 for i in range(0, len(values) - 1, 2)]
        else:
            raise ValueError(f"Only mono or stereo WAV files are supported, got {n_channels} channels ({path!r})")

        frames = [v / 32768.0 for v in mono]
        name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return cls(frames, sample_rate, name=name)
