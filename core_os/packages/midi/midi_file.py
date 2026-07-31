"""SMF (Standard MIDI File) parser -- pure Python, no I/O beyond the bytes
handed to parse(). Implements exactly as much of the spec as this project
needs to schedule note playback: format 0/1 header + track chunks,
variable-length-quantity delta-times, running status, note on/off,
program change, and the Set Tempo meta event. Every other event type
(control change, pitch bend, sysex, other meta events, ...) is parsed just
enough to skip its correct byte length and otherwise ignored -- this is a
player, not an editor, so events that don't affect WHEN a note plays and
at WHAT pitch/velocity don't need to be preserved."""

from __future__ import annotations

from typing import List, NamedTuple, Optional


class MidiEvent(NamedTuple):
    tick: int  # absolute tick position within its own track (not merged across tracks yet)
    type: str  # "note_on" | "note_off" | "set_tempo" | "program_change"
    channel: int  # 0-15; -1 for non-channel events (set_tempo)
    data1: int  # note number, or program number; unused for set_tempo
    data2: int  # velocity, or microseconds-per-quarter-note (set_tempo); unused for program_change


class MidiFile:
    def __init__(self, format: int, ticks_per_quarter: int, tracks: List[List[MidiEvent]]) -> None:
        self.format = format
        self.ticks_per_quarter = ticks_per_quarter
        self.tracks = tracks


class MidiParseError(ValueError):
    pass


def _read_chunk_header(data: bytes, pos: int):
    if pos + 8 > len(data):
        raise MidiParseError(f"Truncated chunk header at offset {pos}")
    chunk_id = data[pos:pos + 4]
    length = int.from_bytes(data[pos + 4:pos + 8], "big")
    return chunk_id, length, pos + 8


def _read_vlq(data: bytes, pos: int):
    """Variable-length quantity: each byte's top bit marks continuation
    (1 = more bytes follow), the low 7 bits are the payload, most
    significant group first."""
    value = 0
    while True:
        if pos >= len(data):
            raise MidiParseError("Truncated variable-length quantity")
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not (byte & 0x80):
            break
    return value, pos


def _parse_track(data: bytes) -> List[MidiEvent]:
    events: List[MidiEvent] = []
    pos = 0
    tick = 0
    running_status: Optional[int] = None
    while pos < len(data):
        delta, pos = _read_vlq(data, pos)
        tick += delta
        status = data[pos]
        if status & 0x80:
            pos += 1
            if status < 0xF0:
                # Running status only applies to channel voice messages
                # (0x80-0xEF) -- meta (0xFF) and sysex (0xF0/0xF7) events
                # neither use nor clear it, per the SMF spec.
                running_status = status
        else:
            # High bit clear: this byte is actually the FIRST DATA byte of
            # an event reusing the previous channel event's status byte
            # (the running-status optimization -- very common in real
            # files, e.g. a run of note-on events on the same channel).
            if running_status is None:
                raise MidiParseError(f"Running status byte with no prior status at track offset {pos}")
            status = running_status

        if status == 0xFF:
            meta_type = data[pos]
            pos += 1
            length, pos = _read_vlq(data, pos)
            meta_data = data[pos:pos + length]
            pos += length
            if meta_type == 0x51 and length == 3:
                microseconds_per_quarter = int.from_bytes(meta_data, "big")
                events.append(MidiEvent(tick, "set_tempo", -1, 0, microseconds_per_quarter))
            # Every other meta type (track name, end-of-track, time
            # signature, lyrics, ...) doesn't affect note scheduling --
            # its length was already consumed above so parsing stays
            # aligned regardless.
        elif status in (0xF0, 0xF7):
            length, pos = _read_vlq(data, pos)
            pos += length  # sysex -- irrelevant to playback, skip
        else:
            event_type = status & 0xF0
            channel = status & 0x0F
            if event_type == 0x90:  # note on (velocity 0 == note off; schedule.py resolves that)
                note, velocity = data[pos], data[pos + 1]
                pos += 2
                events.append(MidiEvent(tick, "note_on", channel, note, velocity))
            elif event_type == 0x80:  # note off
                note, velocity = data[pos], data[pos + 1]
                pos += 2
                events.append(MidiEvent(tick, "note_off", channel, note, velocity))
            elif event_type == 0xC0:  # program change
                program = data[pos]
                pos += 1
                events.append(MidiEvent(tick, "program_change", channel, program, 0))
            elif event_type in (0xA0, 0xB0, 0xE0):  # 2-data-byte events not acted on
                pos += 2
            elif event_type == 0xD0:  # channel pressure, 1 data byte
                pos += 1
            else:
                raise MidiParseError(f"Unrecognized status byte 0x{status:02X} at track offset {pos}")
    return events


def parse(data: bytes) -> MidiFile:
    if data[0:4] != b"MThd":
        raise MidiParseError("Not a MIDI file (missing MThd header)")
    _chunk_id, length, pos = _read_chunk_header(data, 0)
    if length != 6:
        raise MidiParseError(f"Unexpected MThd length {length}, expected 6")
    format_type = int.from_bytes(data[pos:pos + 2], "big")
    ntracks = int.from_bytes(data[pos + 2:pos + 4], "big")
    division = int.from_bytes(data[pos + 4:pos + 6], "big")
    pos += 6
    if division & 0x8000:
        raise MidiParseError("SMPTE-based time division is not supported, only ticks-per-quarter-note")
    if format_type not in (0, 1):
        raise MidiParseError(f"MIDI format {format_type} is not supported (only 0 and 1)")

    tracks: List[List[MidiEvent]] = []
    for _ in range(ntracks):
        chunk_id, chunk_length, pos = _read_chunk_header(data, pos)
        track_data = data[pos:pos + chunk_length]
        pos += chunk_length
        if chunk_id != b"MTrk":
            continue  # unknown chunk type between/after tracks -- skip, not fatal
        tracks.append(_parse_track(track_data))

    return MidiFile(format_type, division, tracks)
