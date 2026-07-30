from interfaces import AppBase
import math
import struct
import wave
import io
import os
import json
import tempfile


class App(AppBase):
    """4-track, 16-step music tracker for ProxiTalk."""

    NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    NUM_TRACKS   = 4
    NUM_STEPS    = 16

    # Layout constants — 128×64 monochrome display
    HEADER_H     = 8   # header row height (px)
    ROW_H        = 8   # each step row height (px)
    VISIBLE_ROWS = 7   # HEADER_H + VISIBLE_ROWS * ROW_H = 8 + 56 = 64 ✓
    STEP_COL_W   = 14  # step-number column width
    TRACK_COL_W  = (128 - 14) // NUM_TRACKS  # = 28 px per track

    # Piano-style key → (note, octave_offset)
    # Lower row  :  z s x d c  v g b h n j m
    # Upper row  :  q   w   e  r   t   y   u
    KEY_NOTES = {
        'KEY_Z': ('C',  0), 'KEY_S': ('C#', 0),
        'KEY_X': ('D',  0), 'KEY_D': ('D#', 0),
        'KEY_C': ('E',  0),
        'KEY_V': ('F',  0), 'KEY_G': ('F#', 0),
        'KEY_B': ('G',  0), 'KEY_H': ('G#', 0),
        'KEY_N': ('A',  0), 'KEY_J': ('A#', 0),
        'KEY_M': ('B',  0),
        # Upper row — one octave higher
        'KEY_Q': ('C',  1), 'KEY_W': ('D',  1),
        'KEY_E': ('E',  1),
        'KEY_R': ('F',  1), 'KEY_T': ('G',  1),
        'KEY_Y': ('A',  1), 'KEY_U': ('B',  1),
    }

    def __init__(self, context):
        super().__init__(context)
        self.drawing = context["drawing"]
        self.width   = context["screen_width"]   # 128
        self.height  = context["screen_height"]  # 64
        self.font    = context["fonts"]["small"]
        self.audio   = context["audio"]
        self.path    = context["app_path"]
        if not self.path.endswith(("/", "\\")):
            self.path += "/"

        # Pattern: grid[step][track] = (note_str, octave_int) or None
        self.grid = [[None] * self.NUM_TRACKS for _ in range(self.NUM_STEPS)]
        self.bpm    = 120
        self.octave = 4   # base octave for note entry

        # Cursor / scroll
        self.cursor_step  = 0
        self.cursor_track = 0
        self.scroll_top   = 0  # first visible step index

        # Playback
        self.playing   = False
        self.play_step = 0
        self.play_tick = 0

        # Note sound cache: (note, octave) -> temp wav path
        self._note_cache = {}
        self._temp_dir   = tempfile.mkdtemp(prefix="pttrk_")

        self.needs_redraw = True
        self._load()

    # ------------------------------------------------------------------
    # Audio: synthesise a short sine-wave tone for each note on demand
    # ------------------------------------------------------------------

    def _note_wav(self, note, octave):
        """Return path to a cached synthesised WAV for the given note/octave."""
        key = (note, octave)
        if key in self._note_cache:
            return self._note_cache[key]

        note_idx = self.NOTES.index(note)
        midi     = (octave + 1) * 12 + note_idx      # C4 → midi 60
        freq     = 440.0 * (2.0 ** ((midi - 69) / 12.0))

        sample_rate = 22050
        duration    = 0.18
        n           = int(sample_rate * duration)

        attack  = int(sample_rate * 0.010)  # 10 ms
        decay   = int(sample_rate * 0.030)  # 30 ms
        release = int(sample_rate * 0.050)  # 50 ms
        sustain = 0.70

        frames = bytearray(n * 2)
        for i in range(n):
            t = i / sample_rate
            if i < attack:
                env = i / attack
            elif i < attack + decay:
                env = 1.0 - (1.0 - sustain) * (i - attack) / decay
            elif i >= n - release:
                env = sustain * (n - i) / release
            else:
                env = sustain
            val = int(32767 * env * math.sin(2.0 * math.pi * freq * t))
            struct.pack_into('<h', frames, i * 2, max(-32768, min(32767, val)))

        buf = io.BytesIO()
        with wave.open(buf, 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(bytes(frames))

        safe_note = note.replace('#', 's')
        path = os.path.join(self._temp_dir, f"{safe_note}{octave}.wav")
        with open(path, 'wb') as f:
            f.write(buf.getvalue())

        self._note_cache[key] = path
        return path

    def _play_note(self, note, octave):
        try:
            self.audio["play_sfx"](self._note_wav(note, octave))
        except Exception as e:
            print(f"[Tracker] play_note error: {e}")

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------

    def _save(self):
        try:
            data = {
                "bpm":  self.bpm,
                "grid": [
                    [list(cell) if cell else None for cell in row]
                    for row in self.grid
                ],
            }
            with open(self.path + "pattern.json", 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"[Tracker] save error: {e}")

    def _load(self):
        try:
            p = self.path + "pattern.json"
            if not os.path.isfile(p):
                return
            with open(p) as f:
                data = json.load(f)
            self.bpm = data.get("bpm", 120)
            for si, row in enumerate(data.get("grid", [])):
                if si >= self.NUM_STEPS:
                    break
                for ti, cell in enumerate(row):
                    if ti >= self.NUM_TRACKS:
                        break
                    self.grid[si][ti] = tuple(cell) if cell else None
        except Exception as e:
            print(f"[Tracker] load error: {e}")

    # ------------------------------------------------------------------
    # App lifecycle
    # ------------------------------------------------------------------

    def start(self):
        self.needs_redraw = True

    def update(self):
        if self.playing:
            self.play_tick += 1
            ticks_per_step = max(1, int(60.0 / self.bpm * 20))  # quarter-note steps
            if self.play_tick >= ticks_per_step:
                self.play_tick = 0
                self.play_step = (self.play_step + 1) % self.NUM_STEPS
                for trk in range(self.NUM_TRACKS):
                    cell = self.grid[self.play_step][trk]
                    if cell:
                        self._play_note(cell[0], cell[1])
                self.needs_redraw = True

        if self.needs_redraw:
            self._draw()
            self.needs_redraw = False

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _cell_label(self, cell):
        """Return a 3-char display string for a cell value."""
        if cell is None:
            return "---"
        note, oct_ = cell
        if '#' in note:
            return f"{note}{oct_}"   # e.g. "C#4"
        return f"{note} {oct_}"      # e.g. "C 4"

    def _draw(self):
        draw = self.drawing
        f    = self.font
        W    = self.width        # 128
        HH   = self.HEADER_H     # 8
        RH   = self.ROW_H        # 8
        SCW  = self.STEP_COL_W   # 14
        TCW  = self.TRACK_COL_W  # 28

        draw["begin_batch"]()
        draw["clear_screen"]()

        # ── Header ────────────────────────────────────────────────────
        play_icon = ">>" if self.playing else "||"
        hdr = f"TRK {play_icon} {self.bpm}BPM O{self.octave}"
        draw["draw_text"](hdr, 2, 1, f)
        draw["draw_area"](0, HH - 1, W, 1, fill=255)  # separator

        # ── Grid ──────────────────────────────────────────────────────
        for vis in range(self.VISIBLE_ROWS):
            step  = self.scroll_top + vis
            if step >= self.NUM_STEPS:
                break
            row_y     = HH + vis * RH
            is_cursor = (step == self.cursor_step)
            is_play   = (self.playing and step == self.play_step)

            # Step column
            step_text = f"{step + 1:02d}"
            if is_cursor and not is_play:
                draw["draw_text"](f">{step_text}", 0, row_y + 1, f)
            elif is_play:
                draw["draw_area"](0, row_y, SCW - 1, RH - 1, fill=255)
                draw["draw_text"](step_text, 3, row_y + 1, f, fill=0)
            else:
                draw["draw_text"](f" {step_text}", 1, row_y + 1, f)

            # Track columns
            for trk in range(self.NUM_TRACKS):
                tx    = SCW + trk * TCW
                label = self._cell_label(self.grid[step][trk])

                if is_cursor and trk == self.cursor_track and not is_play:
                    # Selected cell — inverted
                    draw["draw_area"](tx + 1, row_y, TCW - 2, RH - 1, fill=255)
                    draw["draw_text"](label, tx + 3, row_y + 1, f, fill=0)
                elif is_play:
                    # Playing row — inverted
                    draw["draw_area"](tx + 1, row_y, TCW - 2, RH - 1, fill=255)
                    draw["draw_text"](label, tx + 3, row_y + 1, f, fill=0)
                else:
                    draw["draw_text"](label, tx + 3, row_y + 1, f)

            # Column dividers
            for trk in range(1, self.NUM_TRACKS):
                div_x = SCW + trk * TCW
                draw["draw_area"](div_x, row_y, 1, RH - 1, fill=255)

        # Step-column right edge
        draw["draw_area"](SCW - 1, HH, 1, self.VISIBLE_ROWS * RH, fill=255)

        draw["end_batch"]()

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _advance_cursor(self):
        """Move cursor down one step after note entry (standard tracker behaviour)."""
        if self.cursor_step < self.NUM_STEPS - 1:
            self.cursor_step += 1
            if self.cursor_step >= self.scroll_top + self.VISIBLE_ROWS:
                self.scroll_top = self.cursor_step - self.VISIBLE_ROWS + 1

    def onkeyup(self, keycode):
        # Exit
        if keycode == "KEY_ESC":
            self.playing = False
            self._save()
            self.context["app_manager"].swap_app_async(
                "tracker", "launcher", update_rate_hz=20.0, delay=0.1)
            return

        # Play / Stop
        if keycode == "KEY_SPACE":
            self.playing = not self.playing
            if self.playing:
                self.play_step = -1
                self.play_tick = 0
            self.needs_redraw = True
            return

        # Navigation
        if keycode == "KEY_UP":
            if self.cursor_step > 0:
                self.cursor_step -= 1
                if self.cursor_step < self.scroll_top:
                    self.scroll_top = self.cursor_step
            self.needs_redraw = True
            return

        if keycode == "KEY_DOWN":
            if self.cursor_step < self.NUM_STEPS - 1:
                self.cursor_step += 1
                if self.cursor_step >= self.scroll_top + self.VISIBLE_ROWS:
                    self.scroll_top = self.cursor_step - self.VISIBLE_ROWS + 1
            self.needs_redraw = True
            return

        if keycode == "KEY_LEFT":
            if self.cursor_track > 0:
                self.cursor_track -= 1
            self.needs_redraw = True
            return

        if keycode == "KEY_RIGHT":
            if self.cursor_track < self.NUM_TRACKS - 1:
                self.cursor_track += 1
            self.needs_redraw = True
            return

        # Clear cell
        if keycode in ("KEY_BACKSPACE", "KEY_DELETE"):
            self.grid[self.cursor_step][self.cursor_track] = None
            self.needs_redraw = True
            return

        # BPM adjust  (+5 / -5)
        if keycode in ("KEY_PLUS", "KEY_EQUAL"):
            self.bpm = min(300, self.bpm + 5)
            self.needs_redraw = True
            return

        if keycode == "KEY_MINUS":
            self.bpm = max(40, self.bpm - 5)
            self.needs_redraw = True
            return

        # Octave adjust  ( [ / ] )
        if keycode == "KEY_LEFTBRACE":
            self.octave = max(1, self.octave - 1)
            self.needs_redraw = True
            return

        if keycode == "KEY_RIGHTBRACE":
            self.octave = min(8, self.octave + 1)
            self.needs_redraw = True
            return

        # Note entry
        if keycode in self.KEY_NOTES:
            note, oct_offset = self.KEY_NOTES[keycode]
            oct_ = max(1, min(8, self.octave + oct_offset))
            self.grid[self.cursor_step][self.cursor_track] = (note, oct_)
            self._play_note(note, oct_)
            self._advance_cursor()
            self.needs_redraw = True
            return

    def stop(self):
        self.playing = False
        self._save()
        for p in self._note_cache.values():
            try:
                os.remove(p)
            except Exception:
                pass
        try:
            os.rmdir(self._temp_dir)
        except Exception:
            pass
