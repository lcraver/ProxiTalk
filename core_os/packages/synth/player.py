"""SynthEngine — a real-time software mixer, the one piece of the synth
package that touches I/O. Replaces the earlier discrete "render one finite
buffer, queue it, play it" SynthPlayer: that design could only ever play a
fixed-duration note decided up front, so holding a key had nothing to
extend -- every key-repeat queued another whole separate note. This one
supports actual note_on()/note_off(): a voice keeps generating sound for
as long as it's held, released only when told to.

Runs a single background thread that, whenever >=1 voice is active, mixes
a small chunk of samples (CHUNK_SIZE, ~46ms at 22050Hz) from every active
voice's CONTINUOUS elapsed-sample count -- not a phase reset every chunk,
which is what keeps a held tone click-free across chunk boundaries -- and
writes it to a single long-lived PCMStream (see core/drivers/base.py).
Idles (blocks on a threading.Event) when no voices are active rather than
writing silence or busy-looping.

Pacing is SELF-TIMED, not derived from whatever the backend's write()
happens to do. aplay's stdin pipe blocking (Pi) and
pygame.mixer.Channel.queue() never blocking (Windows) are genuinely
different behaviors -- relying on either implicitly would give the two
backends different failure modes (silent unbounded queue drift on Windows
vs. unverified underrun behavior on the Pi) rather than actual parity. The
mixing loop instead targets a fixed wall-clock cadence itself (the
classic "next_chunk_time += chunk_duration, sleep to it, self-correcting"
pattern) on both backends identically; write() is just "emit this chunk,"
never "wait for room." This doesn't erase real platform differences (SDL's
vs ALSA's own internal buffering/latency is outside this codebase's
control and unverified against real Pi hardware) but removes the
structural, by-design asymmetry that would otherwise exist between the
two backends.

Mixing is a plain sum-then-clip -- multiple simultaneous voices CAN clip/
distort if their combined peak exceeds full scale, same as most simple
software mixers without dynamic normalization; not attempting loudness
compensation here."""

from __future__ import annotations

import itertools
import math
import struct
import threading
import time
import traceback
from typing import Dict, Optional

from core_os.core import debug_log
from core_os.packages.synth.notes import note_to_frequency

_DEBUG_KEY = "synth"
SAMPLE_RATE = 22050
CHUNK_SIZE = 1024  # ~46ms at 22050Hz
_CHUNK_DURATION = CHUNK_SIZE / SAMPLE_RATE
_SCOPE_POINTS = 96  # downsampled points per chunk -- plenty for a small-screen oscilloscope trace, cheap to copy across threads
_SCOPE_STRIDE = CHUNK_SIZE // _SCOPE_POINTS


class _VoiceBase:
    """Shared bookkeeping for both oscillator (_Voice) and sample
    (_SampleVoice) playback -- SynthEngine's note_on/note_off/
    _release_due_voices/_mix_chunk all operate on these three fields
    generically (start_sample/released_at_sample/auto_off_at_sample) with
    no notion of which subtype they're touching, which is what lets both
    kinds mix together in the exact same self._voices dict and the exact
    same per-sample loop -- one mixer, one limiter, one output stream,
    regardless of whether a given voice is a synthesized tone or a
    sampled recording. Subclasses only need to implement sample_at(),
    is_finished(), and debug_label()."""

    def __init__(self, voice_id: int, start_sample: int) -> None:
        self.id = voice_id
        self.start_sample = start_sample
        self.released_at_sample: Optional[int] = None
        self.auto_off_at_sample: Optional[int] = None

    def sample_at(self, absolute_sample: int) -> float:
        raise NotImplementedError

    def is_finished(self, absolute_sample: int) -> bool:
        raise NotImplementedError

    def debug_label(self) -> str:
        raise NotImplementedError

    def visual_info(self) -> Dict[str, Optional[float]]:
        """Static (per-voice, not per-sample) identity for the visualizer's
        snapshot -- waveform name + pitch for an oscillator voice, or just
        "sample" for a sample voice. Kept separate from debug_label()
        (a formatted string for the emulator's text-only Voice Monitor)
        since the visualizer wants the raw fields to render its own bars/
        labels, not a pre-formatted string."""
        raise NotImplementedError


class _Voice(_VoiceBase):
    def __init__(self, voice_id: int, synth, frequency: float, velocity: float, start_sample: int) -> None:
        super().__init__(voice_id, start_sample)
        self.synth = synth
        self.frequency = frequency
        self.velocity = max(0.0, min(1.0, velocity))

    def sample_at(self, absolute_sample: int) -> float:
        elapsed = (absolute_sample - self.start_sample) / SAMPLE_RATE
        if self.released_at_sample is None:
            note_duration = math.inf
        else:
            note_duration = (self.released_at_sample - self.start_sample) / SAMPLE_RATE
        envelope_amp = self.synth.envelope.amplitude_at(elapsed, note_duration)
        if envelope_amp <= 0.0 and self.released_at_sample is not None:
            return 0.0
        phase = (self.frequency * elapsed) % 1.0
        return self.synth.waveform_amplitude(phase) * envelope_amp * self.velocity * self.synth.volume

    def is_finished(self, absolute_sample: int) -> bool:
        if self.released_at_sample is None:
            return False
        elapsed_since_release = (absolute_sample - self.released_at_sample) / SAMPLE_RATE
        return elapsed_since_release >= self.synth.envelope.release

    def debug_label(self) -> str:
        return f"[Synth] {self.synth.waveform_name} {self.frequency:.1f}Hz"

    def visual_info(self) -> Dict[str, Optional[float]]:
        return {"kind": "synth", "waveform": self.synth.waveform_name, "frequency": self.frequency}


class _SampleVoice(_VoiceBase):
    """Plays back a loaded Sample (sample.py) -- no ADSR envelope (that's
    an oscillator/synth concept); a one-shot plays to the end of its
    buffer and finishes, a looping one plays until explicitly released
    (note_off), which stops it immediately rather than fading -- simplest
    predictable behavior for v1, with EffectsChain available for anyone
    who wants a shaped decay instead."""

    def __init__(self, voice_id: int, sample, velocity: float, pitch_scale: float, loop: bool, start_sample: int) -> None:
        super().__init__(voice_id, start_sample)
        self.sample = sample
        self.velocity = max(0.0, min(1.0, velocity))
        self.pitch_scale = max(0.01, pitch_scale)
        self.loop = loop
        self._rate_ratio = (sample.sample_rate / SAMPLE_RATE) * self.pitch_scale

    def sample_at(self, absolute_sample: int) -> float:
        frames = self.sample.frames
        source_position = (absolute_sample - self.start_sample) * self._rate_ratio
        if self.loop:
            source_position %= len(frames)
        elif source_position >= len(frames) - 1:
            return 0.0
        index = int(source_position)
        frac = source_position - index
        next_index = (index + 1) % len(frames) if self.loop else min(index + 1, len(frames) - 1)
        s1, s2 = frames[index], frames[next_index]
        return (s1 + (s2 - s1) * frac) * self.velocity

    def is_finished(self, absolute_sample: int) -> bool:
        if self.released_at_sample is not None:
            return absolute_sample >= self.released_at_sample
        if self.loop:
            return False
        source_position = (absolute_sample - self.start_sample) * self._rate_ratio
        return source_position >= len(self.sample.frames) - 1

    def debug_label(self) -> str:
        return f"[Sample] {self.sample.name or 'sample'}"

    def visual_info(self) -> Dict[str, Optional[float]]:
        return {"kind": "sample", "waveform": None, "frequency": None}


class SynthEngine:
    def __init__(self, audio_output) -> None:
        self._stream = audio_output.open_pcm_stream(SAMPLE_RATE)
        self._lock = threading.Lock()
        self._voices: Dict[int, _VoiceBase] = {}
        self._next_voice_id = itertools.count(1)
        self._total_samples = 0
        self._wake_event = threading.Event()
        self._closed = False
        self._effects = None
        self._last_scope: list = []
        self._last_voices: list = []
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def get_visual_snapshot(self) -> Dict[str, list]:
        """For a UI that wants to visualize what's currently playing --
        e.g. synth_demo's oscilloscope/level-meter display. `scope` is the
        most recent mixed chunk's final (post-effects, post-limiter)
        output, downsampled to _SCOPE_POINTS floats in [-1, 1] -- i.e.
        exactly what the speaker is actually playing right now, not a
        re-synthesis. `voices` is one dict per currently-active voice:
        {"kind": "synth"/"sample", "waveform", "frequency", "level"
        (that voice's own peak amplitude this chunk, in [0, 1], BEFORE
        headroom/effects/limiting -- so a single voice and a 4-voice chord
        report comparable bar heights instead of the chord's bars shrinking
        just because more voices are mixed), "state": "held"/"releasing"}.
        Both are empty once every voice has finished -- mirrors
        debug_log's clear-on-idle behavior below, so a caller can tell
        "actually silent" apart from "just hasn't been asked yet".

        Called from the app's own update() (main thread), reading state
        written by the mixer thread -- same cross-thread read-mostly
        pattern as debug_log's get_voice_detail(), so it takes the same
        lock rather than risking a torn read of the list being copied."""
        with self._lock:
            return {"scope": list(self._last_scope), "voices": list(self._last_voices)}

    def set_effects(self, effects_chain) -> None:
        """Master-bus effects (effects.py's EffectsChain), applied to the
        final mixed signal every chunk -- None (the default) to bypass
        entirely. One chain for the whole engine, not per-voice routing
        (see effects.py's docstring)."""
        self._effects = effects_chain

    def note_on(self, synth, pitch, velocity: float = 1.0) -> int:
        if self._closed:
            return -1
        frequency = note_to_frequency(pitch)
        with self._lock:
            voice_id = next(self._next_voice_id)
            self._voices[voice_id] = _Voice(voice_id, synth, frequency, velocity, self._total_samples)
        self._wake_event.set()
        return voice_id

    def play_sample(self, sample, velocity: float = 1.0, pitch_scale: float = 1.0, loop: bool = False) -> int:
        """Starts playing a loaded Sample (sample.py) as its own voice,
        mixed into the SAME output as oscillator voices -- see
        _VoiceBase's docstring for why one voice dict/mixer/limiter
        serves both kinds. Returns a voice id; note_off() stops it (a
        looping sample keeps going until told to stop; a one-shot finishes
        on its own once the buffer runs out either way)."""
        if self._closed:
            return -1
        with self._lock:
            voice_id = next(self._next_voice_id)
            self._voices[voice_id] = _SampleVoice(voice_id, sample, velocity, pitch_scale, loop, self._total_samples)
        self._wake_event.set()
        return voice_id

    def note_off(self, voice_id: int) -> None:
        with self._lock:
            voice = self._voices.get(voice_id)
            if voice is not None and voice.released_at_sample is None:
                voice.released_at_sample = self._total_samples

    def play_note(self, synth, pitch, duration: float, velocity: float = 1.0) -> int:
        """Fixed-duration convenience: note_on() plus an auto-release point
        the mixer loop itself honors (_release_due_voices), so no separate
        timer/thread is needed just to call note_off() later."""
        voice_id = self.note_on(synth, pitch, velocity=velocity)
        if voice_id == -1:
            return voice_id
        with self._lock:
            voice = self._voices.get(voice_id)
            if voice is not None:
                voice.auto_off_at_sample = voice.start_sample + max(0, int(round(duration * SAMPLE_RATE)))
        return voice_id

    def stop_all(self) -> None:
        """Unlike the old queue-based stop_all (which could only discard
        NOT-YET-STARTED notes -- a blocking play_pcm call already in flight
        couldn't be interrupted), this genuinely cuts every voice
        immediately: we own the mix, nothing's irrevocably committed to a
        blocking driver call the way a one-shot play_pcm was."""
        with self._lock:
            self._voices.clear()
            self._last_scope = []
            self._last_voices = []
        debug_log.clear_active(_DEBUG_KEY)
        debug_log.clear_voice_detail(_DEBUG_KEY)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with self._lock:
            self._voices.clear()
        self._wake_event.set()
        self._thread.join(timeout=2.0)
        self._stream.close()

    # --- mixer thread ------------------------------------------------------

    def _release_due_voices(self) -> None:
        for voice in self._voices.values():
            if (
                voice.auto_off_at_sample is not None
                and voice.released_at_sample is None
                and self._total_samples >= voice.auto_off_at_sample
            ):
                voice.released_at_sample = voice.auto_off_at_sample

    def _mix_chunk(self) -> bytes:
        with self._lock:
            self._release_due_voices()
            voices = list(self._voices.values())

        # sqrt(voice count) headroom, not a naive sum-then-clamp: a single
        # voice (the common case) is untouched (divide by sqrt(1) = 1, no
        # coloration), but N simultaneous voices at or near full amplitude
        # would otherwise sum past +-1.0 -- audibly harsh, flat-topped
        # digital distortion, not just "square/sawtooth are buzzy
        # waveforms" (measured: two overlapping voices near full volume
        # produced a combined peak ~17% over full scale before this).
        # sqrt rather than a straight divide-by-N because dividing by N
        # over-attenuates every voice as more join in (halves a 2-voice mix
        # even though voices are rarely all peaking in phase at once).
        #
        # sqrt-headroom alone is NOT sufficient, though -- confirmed by
        # testing a 4-voice square-wave chord (all notes on at once), which
        # still clipped ~7% of samples even with sqrt(4)=2 headroom. Square
        # waves are binary threshold functions (always exactly +1 or -1,
        # never in between), so several of them landing on the same sign at
        # once is COMMON, not the rare edge case sqrt-scaling assumes.
        # tanh() as a final soft limiter (not another hard clamp) fixes
        # this properly: its range is strictly (-1, 1) for any input, so it
        # mathematically can never hard-clip regardless of how many voices
        # or how they align, and it saturates smoothly (gentle compression)
        # rather than the harsh flat-top a hard clamp produces when it DOES
        # trigger. Trade-off: a single full-scale voice (total=1.0 after
        # headroom, since sqrt(1)=1) now peaks at tanh(1.0)=/-76% of full
        # scale rather than 100% -- accepted deliberately, consistent
        # headroom beats occasional harsh clipping.
        headroom = math.sqrt(max(1, len(voices)))
        effects = self._effects
        # Each voice's own peak |amplitude| this chunk -- BEFORE headroom/
        # effects/limiting, so a lone voice and a 4-voice chord report
        # comparable levels rather than the chord's bars shrinking just
        # because more voices are being mixed (see get_visual_snapshot's
        # docstring). Keyed by voice id since two voices can share a
        # waveform/frequency (e.g. the chord-stack test) and wouldn't be
        # distinguishable any other way.
        peaks = {voice.id: 0.0 for voice in voices}
        scope: list = []

        frames = bytearray(CHUNK_SIZE * 2)
        for i in range(CHUNK_SIZE):
            absolute_sample = self._total_samples + i
            total = 0.0
            for voice in voices:
                s = voice.sample_at(absolute_sample)
                total += s
                a = abs(s)
                if a > peaks[voice.id]:
                    peaks[voice.id] = a
            total /= headroom
            # Effects run BEFORE the limiter, not after -- see
            # effects.py's docstring: a musical effect (Overdrive
            # especially) is meant to be free to push the signal hot, and
            # the limiter's job is to guarantee the final output never
            # hard-clips no matter what the chain did to it, not to cap
            # what the chain is allowed to do.
            if effects is not None:
                total = effects.process(total)
            limited = math.tanh(total)
            if i % _SCOPE_STRIDE == 0:
                scope.append(limited)
            value = int(max(-32768, min(32767, round(limited * 32767))))
            struct.pack_into("<h", frames, i * 2, value)

        self._total_samples += CHUNK_SIZE
        finished_ids = [v.id for v in voices if v.is_finished(self._total_samples)]
        if finished_ids:
            with self._lock:
                for voice_id in finished_ids:
                    self._voices.pop(voice_id, None)

        if voices:
            # Speaker placeholder only has room for one short line -- a
            # count, not every label (that got unreadable past 2-3 voices).
            # Full per-voice detail goes to voice_detail instead, for the
            # emulator's separate Voice Monitor window.
            debug_log.set_active(_DEBUG_KEY, f"{len(voices)} voice(s)")
            debug_log.set_voice_detail(
                _DEBUG_KEY,
                [
                    {
                        "label": v.debug_label(),
                        "state": "releasing" if v.released_at_sample is not None else "held",
                    }
                    for v in voices
                ],
            )
        else:
            debug_log.clear_active(_DEBUG_KEY)
            debug_log.clear_voice_detail(_DEBUG_KEY)

        with self._lock:
            self._last_scope = scope
            self._last_voices = [
                {
                    **v.visual_info(),
                    "level": min(1.0, peaks[v.id]),
                    "state": "releasing" if v.released_at_sample is not None else "held",
                }
                for v in voices
            ]

        return bytes(frames)

    def _run(self) -> None:
        while not self._closed:
            self._wake_event.wait()
            if self._closed:
                return
            next_chunk_time = time.monotonic()
            while True:
                with self._lock:
                    active = bool(self._voices)
                if not active:
                    self._wake_event.clear()
                    debug_log.clear_active(_DEBUG_KEY)
                    debug_log.clear_voice_detail(_DEBUG_KEY)
                    with self._lock:
                        self._last_scope = []
                        self._last_voices = []
                    break
                now = time.monotonic()
                sleep_for = next_chunk_time - now
                if sleep_for > 0:
                    time.sleep(sleep_for)
                try:
                    chunk = self._mix_chunk()
                    self._stream.write(chunk)
                except Exception:
                    traceback.print_exc()
                next_chunk_time += _CHUNK_DURATION
