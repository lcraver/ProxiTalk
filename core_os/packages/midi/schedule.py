"""build_schedule -- turns a parsed MidiFile (midi_file.py) into a flat,
absolute-time note list, the same shape apps/synth_demo's hand-written
_Track.notes already uses conceptually (just seconds instead of beats,
and derived from a real file instead of typed by hand). No engine
concerns here (waveform choice, actually calling note_on/note_off) --
that's player.py's job; this module only resolves WHEN and for HOW LONG
each note sounds."""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Tuple

from core_os.packages.midi.midi_file import MidiFile

_DEFAULT_MICROSECONDS_PER_QUARTER = 500000  # 120 BPM, MIDI's own default absent a Set Tempo event


class ScheduledNote(NamedTuple):
    channel: int
    program: int
    note: int
    velocity: int  # 1-127 (never 0 -- a velocity-0 note-on resolves as a note-off, not a note)
    start_seconds: float
    duration_seconds: float


class _TempoMap:
    """Converts an absolute MIDI tick to seconds, honoring every tempo
    change along the way rather than assuming one constant tempo for the
    whole file -- a file with a tempo change partway through would
    otherwise play at the wrong speed from that point on."""

    def __init__(self, ticks_per_quarter: int, tempo_changes: List[Tuple[int, int]]) -> None:
        # tempo_changes: (tick, microseconds_per_quarter), any order/dupes in.
        changes = sorted(set(tempo_changes))
        if not changes or changes[0][0] != 0:
            changes.insert(0, (0, _DEFAULT_MICROSECONDS_PER_QUARTER))
        # Precompute (tick, cumulative_seconds_at_this_tick, us_per_quarter_from_here) checkpoints.
        self._checkpoints: List[Tuple[int, float, int]] = []
        cumulative_seconds = 0.0
        prev_tick, prev_tempo = changes[0]
        self._checkpoints.append((prev_tick, cumulative_seconds, prev_tempo))
        for tick, tempo in changes[1:]:
            if tick == prev_tick:
                # Two tempo events at the identical tick -- keep only the
                # later one's tempo taking effect from that point.
                self._checkpoints[-1] = (prev_tick, cumulative_seconds, tempo)
                prev_tempo = tempo
                continue
            cumulative_seconds += ((tick - prev_tick) / ticks_per_quarter) * (prev_tempo / 1_000_000.0)
            self._checkpoints.append((tick, cumulative_seconds, tempo))
            prev_tick, prev_tempo = tick, tempo
        self._ticks_per_quarter = ticks_per_quarter

    def seconds_at(self, tick: int) -> float:
        # Checkpoints are tick-ascending; find the last one at or before `tick`.
        lo, hi = 0, len(self._checkpoints) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._checkpoints[mid][0] <= tick:
                lo = mid
            else:
                hi = mid - 1
        checkpoint_tick, checkpoint_seconds, tempo = self._checkpoints[lo]
        return checkpoint_seconds + ((tick - checkpoint_tick) / self._ticks_per_quarter) * (tempo / 1_000_000.0)


def build_schedule(midi_file: MidiFile) -> List[ScheduledNote]:
    tempo_changes: List[Tuple[int, int]] = []
    merged: List[tuple] = []  # (tick, track_index, event_index, event) -- stable merge across tracks
    for track_index, track in enumerate(midi_file.tracks):
        for event_index, event in enumerate(track):
            if event.type == "set_tempo":
                tempo_changes.append((event.tick, event.data2))
            else:
                merged.append((event.tick, track_index, event_index, event))

    tempo_map = _TempoMap(midi_file.ticks_per_quarter, tempo_changes)
    merged.sort(key=lambda item: (item[0], item[1], item[2]))

    programs: Dict[int, int] = {}  # channel -> current program, default 0
    open_notes: Dict[Tuple[int, int], Tuple[int, int, int]] = {}  # (channel, note) -> (start_tick, velocity, program)
    schedule: List[ScheduledNote] = []
    last_tick = 0

    def close_note(channel: int, note: int, end_tick: int) -> None:
        key = (channel, note)
        opened = open_notes.pop(key, None)
        if opened is None:
            return  # note-off with no matching note-on (malformed/truncated input) -- nothing to resolve
        start_tick, velocity, program = opened
        start_seconds = tempo_map.seconds_at(start_tick)
        end_seconds = tempo_map.seconds_at(end_tick)
        schedule.append(ScheduledNote(channel, program, note, velocity, start_seconds, max(0.0, end_seconds - start_seconds)))

    for tick, _track_index, _event_index, event in merged:
        last_tick = max(last_tick, tick)
        if event.type == "program_change":
            programs[event.channel] = event.data1
        elif event.type == "note_on" and event.data2 > 0:
            key = (event.channel, event.data1)
            if key in open_notes:
                # Retriggered without an intervening note-off -- close the
                # stuck one at this same tick rather than losing it or
                # letting the new note-on silently overwrite its start.
                close_note(event.channel, event.data1, tick)
            open_notes[key] = (tick, event.data2, programs.get(event.channel, 0))
        elif event.type == "note_off" or (event.type == "note_on" and event.data2 == 0):
            close_note(event.channel, event.data1, tick)

    # Notes still open when the file ends (no matching note-off at all) --
    # resolve them at the last tick seen rather than dropping them.
    for (channel, note), (start_tick, velocity, program) in list(open_notes.items()):
        close_note(channel, note, last_tick)

    schedule.sort(key=lambda n: n.start_seconds)
    return schedule
