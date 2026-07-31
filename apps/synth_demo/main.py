"""Synth Demo — hold 1-5 to sustain a tone, each a different waveform and
pitch; release to stop. ENTER/6/7/8 each play a different public-domain
test song through the timer package, exercising a different corner of
SynthEngine's real-time mixer (core_os/packages/synth/player.py):

  ENTER  Twinkle Twinkle Little Star -- 2 voices (lead+bass), the original
         polyphony smoke test.
  6      Mary Had a Little Lamb -- 1 voice only, confirms plain monophonic
         sequencing works with nothing else going on.
  7      Ode to Joy -- 2 voices, but a longer 32-note sequence (vs. 16),
         a longer-running/more-notes stress test than Twinkle.
  8      A 4-note C-major chord -- not a melody, all 4 voices note_on the
         SAME instant and held together. Twinkle/Ode only ever overlap 2
         voices; this is the actual test for N-voice-at-once mixing (the
         sqrt(voice count) headroom scaling exists specifically for this
         case -- see player.py's _mix_chunk).
  9      Loads and plays files/test.midi (a real, dense third-party
         MIDI file -- 52,913 notes, ~3m43s) through the midi package
         (core_os/packages/midi). Reading+parsing+resolving the schedule
         happens on a background thread (measured ~280ms for this file --
         a visible hitch if done synchronously in onkeydown, worse on
         slower hardware); only the final player.play() call, which
         touches the shared TimerManager, runs on the main thread in
         update() once the background thread's result is ready --
         TimerManager's heap isn't safe to push into concurrently with the
         tick() thread popping from it.

Tracks which keys are currently held (keycode -> voice id) so normal key-
repeat (the physical matrix and the Windows emulator both synthesize
repeated onkeydown events while a key stays down) doesn't retrigger the
note over and over -- onkeydown only starts a new voice on the actual
first press (keycode not yet in self._held); every repeat event for the
same still-held key is ignored. onkeyup ends that specific voice. Only one
song plays at a time (a global _song_playing guard) -- letting two songs'
schedules interleave wouldn't test anything meaningful, just make noise.

Also drives a live visualizer (oscilloscope + per-voice level bars) off
SynthEngine.get_visual_snapshot() (core_os/packages/synth/player.py) --
the actual post-effects, post-limiter mix each chunk, not a re-synthesis,
so it reflects exactly what's audible (clipping/tanh saturation included)
for however many voices happen to be stacked at once, whether that's a
single held key, a 2-4 voice song, or the MIDI file's much higher
polyphony.
"""

from __future__ import annotations

import os
import threading

from PIL import Image, ImageDraw

from core_os.apps_runtime.app_base import AppBase

_KEY_VOICES = {
    "KEY_1": ("sine", "C4"),
    "KEY_2": ("square", "D4"),
    "KEY_3": ("triangle", "E4"),
    "KEY_4": ("sawtooth", "F4"),
    "KEY_5": ("noise", "G4"),
}

_LEAD_ADSR = (0.01, 0.05, 0.6, 0.1)
_PAD_ADSR = (0.05, 0.1, 0.9, 0.2)

# --- visualizer layout (screen is 250x122) ---------------------------------
_HEADER_H = 20
_SCOPE_X, _SCOPE_Y, _SCOPE_W, _SCOPE_H = 4, 24, 242, 40
_BARS_X, _BARS_Y, _BARS_W, _BARS_H = 4, 68, 242, 40
_BARS_LABEL_H = 10  # bottom strip of the bars image reserved for waveform-abbreviation labels
_MAX_BARS = 10  # more voices than this (e.g. the dense MIDI file) just show a "+N" count instead of more columns
_FOOTER_Y = 112

_WAVE_ABBR = {
    "sine": "SIN", "square": "SQR", "triangle": "TRI", "sawtooth": "SAW", "noise": "NSE",
}


class _Track:
    """One voice's part: a waveform/ADSR/volume plus its own
    (pitch, start_beat, duration_beats) note list, all against the song's
    shared beat length."""

    def __init__(self, waveform, adsr, volume, notes):
        self.waveform = waveform
        self.adsr = adsr
        self.volume = volume
        self.notes = notes

    def end_beat(self):
        return max((start + duration for _, start, duration in self.notes), default=0)


class _Song:
    def __init__(self, name, beat, tracks, legato=False):
        self.name = name
        self.beat = beat
        self.tracks = tracks
        # Melodic tracks get a slight gap between notes (staccato, avoids a
        # blurred legato run); a held chord/pad track wants the opposite --
        # full length, no gap.
        self.note_gap = 1.0 if legato else 0.85

    def duration(self):
        return max((t.end_beat() for t in self.tracks), default=0) * self.beat


# Twinkle Twinkle Little Star, first two phrases -- public domain.
_TWINKLE = _Song(
    name="Twinkle Twinkle (2 voices)",
    beat=0.3,
    tracks=[
        _Track("square", _LEAD_ADSR, 1.0, [
            ("C4", 0, 1), ("C4", 1, 1), ("G4", 2, 1), ("G4", 3, 1),
            ("A4", 4, 1), ("A4", 5, 1), ("G4", 6, 2),
            ("F4", 8, 1), ("F4", 9, 1), ("E4", 10, 1), ("E4", 11, 1),
            ("D4", 12, 1), ("D4", 13, 1), ("C4", 14, 2),
        ]),
        _Track("triangle", _PAD_ADSR, 0.5, [("C3", 0, 8), ("F3", 8, 8)]),
    ],
)

# Mary Had a Little Lamb, first two phrases -- public domain. Single voice
# on purpose (see module docstring).
_MARY = _Song(
    name="Mary Had a Little Lamb (1 voice)",
    beat=0.25,
    tracks=[
        _Track("sine", (0.02, 0.05, 0.7, 0.15), 1.0, [
            ("E4", 0, 1), ("D4", 1, 1), ("C4", 2, 1), ("D4", 3, 1),
            ("E4", 4, 1), ("E4", 5, 1), ("E4", 6, 2),
            ("D4", 8, 1), ("D4", 9, 1), ("D4", 10, 2),
            ("E4", 12, 1), ("G4", 13, 1), ("G4", 14, 2),
        ]),
    ],
)

# Beethoven's "Ode to Joy" main theme, first 8 bars -- public domain
# (early 1800s). Longer/more notes than Twinkle -- a bigger sequencing
# stress test, still only 2 overlapping voices.
_ODE_TO_JOY = _Song(
    name="Ode to Joy (2 voices, long)",
    beat=0.28,
    tracks=[
        _Track("triangle", (0.01, 0.05, 0.7, 0.1), 0.9, [
            ("E4", 0, 1), ("E4", 1, 1), ("F4", 2, 1), ("G4", 3, 1),
            ("G4", 4, 1), ("F4", 5, 1), ("E4", 6, 1), ("D4", 7, 1),
            ("C4", 8, 1), ("C4", 9, 1), ("D4", 10, 1), ("E4", 11, 1),
            ("E4", 12, 1), ("D4", 13, 1), ("D4", 14, 2),
            ("E4", 16, 1), ("E4", 17, 1), ("F4", 18, 1), ("G4", 19, 1),
            ("G4", 20, 1), ("F4", 21, 1), ("E4", 22, 1), ("D4", 23, 1),
            ("C4", 24, 1), ("C4", 25, 1), ("D4", 26, 1), ("E4", 27, 1),
            ("D4", 28, 1), ("C4", 29, 1), ("C4", 30, 2),
        ]),
        _Track("sawtooth", _PAD_ADSR, 0.4, [("C3", 0, 16), ("F3", 16, 16)]),
    ],
)

# Not a melody -- a straight 4-note C-major chord, all voices note_on the
# same instant. The actual N-voice-at-once mixing test (see module
# docstring); everything else here only ever overlaps 2 voices.
_CHORD_STACK = _Song(
    name="Chord Stack (4 voices)",
    beat=0.6,
    tracks=[
        _Track("square", (0.02, 0.1, 0.8, 0.3), 0.7, [(pitch, 0, 2)])
        for pitch in ("C4", "E4", "G4", "C5")
    ],
    legato=True,
)

_KEY_SONGS = {
    "KEY_ENTER": _TWINKLE,
    "KEY_6": _MARY,
    "KEY_7": _ODE_TO_JOY,
    "KEY_8": _CHORD_STACK,
}

_MIDI_FILENAME = "test.midi"


class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.gfx = context["display_gfx"]
        self.synth_api = context["synth"]
        self.midi_api = context["midi"]
        self.files = context["files"]
        self.app_control = context["app_control"]
        self.timers = context["timer"]["timer_manager"]()
        self.screen_width = context["screen_width"]
        self.screen_height = context["screen_height"]
        self._synths = {}
        self._held = {}  # keycode -> voice id, only for keys currently sounding
        self._last_played = ""
        self._song_playing = False
        self.midi_player = None
        self._midi_loading = False
        self._midi_result = None  # set by the background load thread: a schedule list, or an Exception

    def start(self):
        for waveform, _ in _KEY_VOICES.values():
            self._get_synth(waveform, _LEAD_ADSR, 1.0)
        self.midi_player = self.midi_api["player"](self.timers, self.synth_api)
        self.gfx["clear_screen"]()
        font = self.gfx["fonts"]["small"]
        self.gfx["draw_text"]("1-5 hold, ENTER/6/7/8/9 song", 4, _FOOTER_Y, font=font)
        self._draw()

    def _get_synth(self, waveform, adsr, volume):
        """One shared Synth per (waveform, adsr, volume) combination --
        set_waveform/set_adsr/set_volume are cheap config, not per-note
        work, so nothing here needs a fresh Synth per note or per song."""
        key = (waveform, adsr, volume)
        synth = self._synths.get(key)
        if synth is None:
            synth = self.synth_api["synth"](waveform=waveform)
            synth.set_adsr(*adsr)
            synth.set_volume(volume)
            self._synths[key] = synth
        return synth

    def _draw(self):
        # Only the header band -- clear_screen() here would wipe the
        # scope/level-meter visualizer drawn below it every time a note or
        # song starts (this is called from onkeydown, independently of the
        # per-tick _draw_scope/_draw_bars redraw in update()).
        self.gfx["clear_area"](0, 0, self.screen_width, _HEADER_H)
        font = self.gfx["fonts"]["small"]
        self.gfx["draw_text"]("Synth Demo", 4, 2, font=font)
        self.gfx["draw_text"](f"Last: {self._last_played}", 4, 11, font=font)

    def _play_song(self, song):
        if self._song_playing:
            return
        self._song_playing = True
        self._last_played = song.name
        self._draw()
        for track in song.tracks:
            synth = self._get_synth(track.waveform, track.adsr, track.volume)
            for pitch, start_beat, duration_beats in track.notes:
                start = start_beat * song.beat
                duration = duration_beats * song.beat * song.note_gap
                self.timers.after(
                    start, lambda p=pitch, d=duration, s=synth: self.synth_api["play_note"](s, p, d)
                )
        self.timers.after(song.duration(), self._on_song_done)

    def _on_song_done(self):
        self._song_playing = False

    def _play_midi_file(self):
        if self._song_playing or self._midi_loading:
            return
        self._midi_loading = True
        self._last_played = f"Loading {_MIDI_FILENAME}..."
        self._draw()
        path = os.path.join(self.files["root_dir"](), _MIDI_FILENAME)

        def _load():
            # Runs on a background thread -- read+parse+build_schedule are
            # pure functions over immutable input, safe off-thread. Does
            # NOT touch self.timers/self.midi_player here (see module
            # docstring: TimerManager's heap isn't safe to push into
            # concurrently with the main thread's tick() popping from it)
            # -- the result is just handed back via self._midi_result for
            # update() to act on from the main thread.
            try:
                midi_file = self.midi_api["load_file"](path)
                self._midi_result = self.midi_api["build_schedule"](midi_file)
            except Exception as exc:
                self._midi_result = exc

        threading.Thread(target=_load, daemon=True).start()

    def _handle_midi_result(self):
        result, self._midi_result = self._midi_result, None
        self._midi_loading = False
        if isinstance(result, Exception):
            self._last_played = f"MIDI load failed: {result}"
            self._draw()
            return
        self._song_playing = True
        self._last_played = f"{_MIDI_FILENAME} ({len(result)} notes)"
        self._draw()
        self.midi_player.play(result)
        total_duration = max((n.start_seconds + n.duration_seconds for n in result), default=0.0)
        self.timers.after(total_duration, self._on_song_done)

    def _draw_scope(self, scope):
        """Oscilloscope trace: the actual mixed-output samples for the last
        chunk, downsampled (see player.py's _SCOPE_POINTS), rendered as one
        polyline. A flat center line -- the correct at-rest look for a real
        scope -- when nothing's playing, rather than leaving the area
        blank or stale."""
        img = Image.new("1", (_SCOPE_W, _SCOPE_H), 0)
        draw = ImageDraw.Draw(img)
        mid = _SCOPE_H // 2
        if len(scope) >= 2:
            step = (_SCOPE_W - 1) / (len(scope) - 1)
            points = [(round(i * step), round(mid - v * (mid - 1))) for i, v in enumerate(scope)]
            draw.line(points, fill=1, width=1)
        else:
            draw.line([(0, mid), (_SCOPE_W - 1, mid)], fill=1)
        self.gfx["draw_image"](img, _SCOPE_X, _SCOPE_Y)

    def _draw_bars(self, voices):
        """Per-voice level meter: one column per currently-active voice,
        height == that voice's own peak amplitude this chunk (comparable
        across 1 voice or a 4-voice chord -- see get_visual_snapshot's
        docstring), filled while held and hollow while releasing (the
        envelope's fade-out tail) so a note letting go is visually
        distinct from one still being sustained. Labeled with its
        waveform underneath; a voice count past _MAX_BARS (the dense MIDI
        file can have many more active notes than there's room for
        columns) collapses to a "+N" instead of more columns."""
        img = Image.new("1", (_BARS_W, _BARS_H), 0)
        draw = ImageDraw.Draw(img)
        font = self.gfx["fonts"]["small"]
        bar_area_h = _BARS_H - _BARS_LABEL_H
        slot = _BARS_W // _MAX_BARS
        for idx, voice in enumerate(voices[:_MAX_BARS]):
            x0 = idx * slot + 2
            x1 = x0 + slot - 5
            bar_h = round(voice["level"] * (bar_area_h - 1))
            y1 = bar_area_h - 1
            y0 = y1 - bar_h
            if voice["state"] == "held":
                draw.rectangle([x0, y0, x1, y1], fill=1)
            elif bar_h > 0:
                draw.rectangle([x0, y0, x1, y1], outline=1)
            label = _WAVE_ABBR.get(voice["waveform"], "SMP")
            draw.text((x0, bar_area_h + 1), label, font=font, fill=1)
        if len(voices) > _MAX_BARS:
            extra = f"+{len(voices) - _MAX_BARS}"
            w, _ = self.gfx["get_text_size"](extra, font)
            draw.text((_BARS_W - w - 1, 0), extra, font=font, fill=1)
        self.gfx["draw_image"](img, _BARS_X, _BARS_Y)

    def update(self):
        self.timers.tick()
        if self._midi_loading and self._midi_result is not None:
            self._handle_midi_result()
        snapshot = self.synth_api["get_visual_snapshot"]()
        self._draw_scope(snapshot["scope"])
        self._draw_bars(snapshot["voices"])

    def onkeydown(self, keycode):
        if keycode == "KEY_ESC":
            self.app_control.swap_app_async("synth_demo", "launcher", delay=0.1)
            return
        if keycode == "KEY_9":
            self._play_midi_file()
            return
        song = _KEY_SONGS.get(keycode)
        if song is not None:
            self._play_song(song)
            return
        voice = _KEY_VOICES.get(keycode)
        if voice is None or keycode in self._held:
            return
        waveform, note = voice
        self._held[keycode] = self.synth_api["note_on"](self._get_synth(waveform, _LEAD_ADSR, 1.0), note)
        self._last_played = f"{waveform} {note}"
        self._draw()

    def onkeyup(self, keycode):
        voice_id = self._held.pop(keycode, None)
        if voice_id is not None:
            self.synth_api["note_off"](voice_id)

    def stop(self):
        if self.midi_player is not None:
            self.midi_player.stop()
        self.synth_api["stop_all"]()
