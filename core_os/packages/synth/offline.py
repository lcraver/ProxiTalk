"""Offline (non-realtime) rendering -- mixes a list of pre-resolved notes
directly into one WAV file, reusing the exact same per-voice waveform/
envelope math and sqrt(active-voice-count)+tanh mixing SynthEngine uses
live (player.py's _Voice / _mix_chunk), just computed in one pass instead
of paced against wall-clock time -- an offline render sounds identical to
what the real-time engine would actually produce (same math, same
limiter), just without waiting out the song's real duration to hear it.
Also the basis for any future automated audio-correctness checks.

Iterates only the voices actually active in each chunk (a start-time-
sorted sweep, add-on-start/drop-on-finish), not every voice for every
chunk -- for a dense file (test.midi: 52,913 notes) the naive
all-voices-every-chunk approach would be millions of times slower than
the number of voices actually overlapping at any one moment."""

from __future__ import annotations

import math
import struct
import wave
from typing import List, NamedTuple

from core_os.packages.synth.notes import note_to_frequency
from core_os.packages.synth.player import CHUNK_SIZE, SAMPLE_RATE, _Voice


class OfflineNote(NamedTuple):
    synth: object  # a Synth instance
    pitch: object  # int MIDI note / float Hz / str note-name -- whatever note_to_frequency accepts
    start_seconds: float
    duration_seconds: float
    velocity: float


def render_to_pcm(notes: List[OfflineNote], sample_rate: int = SAMPLE_RATE) -> bytes:
    voices = []
    for note in notes:
        frequency = note_to_frequency(note.pitch)
        start_sample = max(0, int(round(note.start_seconds * sample_rate)))
        voice = _Voice(0, note.synth, frequency, note.velocity, start_sample)
        voice.released_at_sample = start_sample + max(0, int(round(note.duration_seconds * sample_rate)))
        voice.end_sample = voice.released_at_sample + int(round(note.synth.envelope.release * sample_rate)) + 1
        voices.append(voice)
    voices.sort(key=lambda v: v.start_sample)

    total_samples = max((v.end_sample for v in voices), default=0)
    frames = bytearray(total_samples * 2)

    next_start_index = 0
    active: List[_Voice] = []
    for chunk_start in range(0, total_samples, CHUNK_SIZE):
        chunk_end = min(chunk_start + CHUNK_SIZE, total_samples)

        while next_start_index < len(voices) and voices[next_start_index].start_sample < chunk_end:
            active.append(voices[next_start_index])
            next_start_index += 1
        active = [v for v in active if v.end_sample > chunk_start]

        if not active:
            continue
        headroom = math.sqrt(len(active))
        for i in range(chunk_start, chunk_end):
            total = 0.0
            for voice in active:
                if voice.start_sample <= i < voice.end_sample:
                    total += voice.sample_at(i)
            limited = math.tanh(total / headroom)
            value = int(max(-32768, min(32767, round(limited * 32767))))
            struct.pack_into("<h", frames, i * 2, value)

    return bytes(frames)


def render_to_wav_file(notes: List[OfflineNote], path: str, sample_rate: int = SAMPLE_RATE) -> None:
    pcm = render_to_pcm(notes, sample_rate=sample_rate)
    with wave.open(path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
