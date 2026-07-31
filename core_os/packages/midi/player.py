"""MidiPlayer -- schedules a resolved note list (schedule.py's
build_schedule output) through the SAME timer+synth composition
apps/synth_demo's hand-written test songs already use (context["timer"]'s
TimerManager + context["synth"]'s note_on/play_note), rather than adding
any engine-level MIDI awareness. One Synth per distinct (channel, program)
pair, so a multi-instrument file gets real timbral variety instead of
every channel sounding identical -- see _program_to_waveform below for the
General MIDI program -> waveform mapping (this is an oscillator synth, not
a sampler, so a GM program can only ever be approximated, not reproduced).

Uses SynthEngine's existing play_note(synth, pitch, duration, velocity)
(engine auto-releases -- see packages/synth/player.py) rather than
scheduling separate note_on/note_off timer pairs: half as many timers for
the same result, and it's exactly the pattern the hand-written songs in
apps/synth_demo already use."""

from __future__ import annotations

from typing import Dict, List, Tuple

from core_os.packages.midi.schedule import ScheduledNote

_PERCUSSION_CHANNEL = 9  # MIDI channel 10, 0-indexed -- General MIDI's reserved drum channel
_MELODIC_ADSR = (0.01, 0.05, 0.6, 0.1)
_PERCUSSION_ADSR = (0.005, 0.05, 0.0, 0.05)  # near-zero sustain -- a blip, not a held tone


def _program_to_waveform(program: int) -> str:
    """General MIDI's 128 program numbers group into 16-wide instrument
    families; folds those down to this engine's 5 waveforms rather than
    defaulting every channel to the same one, so a multi-instrument file
    still reads as having distinct voices even though none of them are
    faithful to the real instrument."""
    if program < 24:   # Piano, Chromatic Percussion, Organ
        return "sine"
    if program < 56:   # Guitar, Bass, Strings, Ensemble
        return "triangle"
    if program < 80:   # Brass, Reed, Pipe
        return "square"
    if program < 104:  # Synth Lead, Synth Pad, Synth Effects
        return "sawtooth"
    return "noise"      # Ethnic, Percussive, Sound Effects


class MidiPlayer:
    def __init__(self, timers, synth_api) -> None:
        self._timers = timers
        self._synth_api = synth_api
        self._synths: Dict[Tuple[int, int], object] = {}
        self._scheduled: List[object] = []

    def _synth_for(self, channel: int, program: int):
        key = (channel, program)
        synth = self._synths.get(key)
        if synth is None:
            is_percussion = channel == _PERCUSSION_CHANNEL
            waveform = "noise" if is_percussion else _program_to_waveform(program)
            synth = self._synth_api["synth"](waveform=waveform)
            synth.set_adsr(*(_PERCUSSION_ADSR if is_percussion else _MELODIC_ADSR))
            self._synths[key] = synth
        return synth

    def play(self, schedule: List[ScheduledNote]) -> None:
        self.stop()
        for note in schedule:
            synth = self._synth_for(note.channel, note.program)
            velocity = max(0.0, min(1.0, note.velocity / 127.0))
            timer = self._timers.after(
                note.start_seconds,
                lambda s=synth, p=note.note, d=note.duration_seconds, v=velocity: (
                    self._synth_api["play_note"](s, p, d, v)
                ),
            )
            self._scheduled.append(timer)

    def stop(self) -> None:
        for timer in self._scheduled:
            timer.cancel()
        self._scheduled = []
        self._synth_api["stop_all"]()
