"""note_to_frequency — accepts whatever Playdate's flexible `playNote(pitch,
...)` argument would: a frequency in Hz (float, passed through), a MIDI
note number (int, standard 440*2**((note-69)/12) formula, A4=69=440Hz), or
a note-name string like "C4"/"A#3"/"Eb5" (letter + optional sharp/flat +
octave, converted to a MIDI note number first then the same formula)."""

from __future__ import annotations

from typing import Union

_NOTE_OFFSETS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _midi_to_frequency(midi_note: float) -> float:
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def _parse_note_name(name: str) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Empty note name")
    letter = name[0].upper()
    if letter not in _NOTE_OFFSETS:
        raise ValueError(f"Invalid note letter in {name!r}, expected one of {sorted(_NOTE_OFFSETS)}")
    rest = name[1:]
    accidental = 0
    if rest and rest[0] in "#s":
        accidental = 1
        rest = rest[1:]
    elif rest and rest[0] in "b":
        accidental = -1
        rest = rest[1:]
    if not rest or not (rest.lstrip("-").isdigit()):
        raise ValueError(f"Missing/invalid octave in note name {name!r}")
    octave = int(rest)
    # MIDI note 0 is C-1 in scientific pitch notation -- (octave + 1) * 12
    # lands C at the right multiple of 12, offset by the letter/accidental.
    return (octave + 1) * 12 + _NOTE_OFFSETS[letter] + accidental


def note_to_frequency(pitch: Union[int, float, str]) -> float:
    if isinstance(pitch, str):
        return _midi_to_frequency(_parse_note_name(pitch))
    if isinstance(pitch, bool):
        raise TypeError("pitch must be a note name, MIDI note number, or frequency -- not a bool")
    if isinstance(pitch, int):
        return _midi_to_frequency(pitch)
    return float(pitch)
