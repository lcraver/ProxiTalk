"""Windows dev-machine audio driver — wraps core_os's own pygame-mixer audio
engine (core_os/packages/audio/engine.py) behind the AudioOutputDriver
contract."""

from __future__ import annotations

import pygame

import core_os.packages.audio.engine as _am

from core_os.core.drivers.base import AudioOutputDriver, PCMStream


class _PygamePCMStream(PCMStream):
    """Claims a RESERVED mixer channel (pygame.mixer.set_reserved) so
    unrelated sfx/tts/music playback elsewhere (which all go through
    Sound.play()'s automatic any-free-channel selection, or their own
    explicit channels) can never steal it mid-stream. Only supports the
    process-wide mixer's fixed MIXER_SETTINGS rate -- matches
    packages/synth's own sample rate everywhere, so not a real constraint
    in practice."""

    def __init__(self, sample_rate: int) -> None:
        _am.initialize_audio_system()
        expected_rate = _am.MIXER_SETTINGS["frequency"]
        if sample_rate != expected_rate:
            raise ValueError(
                f"_PygamePCMStream only supports the process-wide mixer's fixed "
                f"{expected_rate}Hz, got {sample_rate}"
            )
        pygame.mixer.set_reserved(1)
        self._channel = pygame.mixer.Channel(0)

    def write(self, pcm_bytes: bytes) -> None:
        # WAV-wrapped, not Sound(buffer=pcm_bytes) -- confirmed by direct
        # testing that pygame.mixer.init(channels=1) is only a REQUEST:
        # get_init() on this system reports (22050, -16, 2), stereo, even
        # though mono was asked for (SDL silently substitutes whatever the
        # device actually supports). Sound(buffer=...) has zero format
        # safety -- it just reinterprets the given bytes AS the mixer's
        # real current format, so raw mono PCM handed to a stereo mixer
        # plays back at ~2x speed with every pair of mono samples garbled
        # into one bogus L/R stereo frame (audible as a fast, warbly,
        # inconsistent tone instead of a steady one -- confirmed: a chunk
        # timed for 0.2s of mono audio measured at ~0.1s actual playback,
        # exactly the 2x-speed signature). A WAV wrapper (same
        # wrap_raw_audio_as_wav already used by every other pygame
        # playback path in this codebase -- play_pcm, TTS, sfx) declares
        # the format explicitly in its header, and SDL_mixer correctly
        # auto-converts a loaded Sound's declared format to the real
        # device format -- unlike the raw-buffer path, which has no such
        # conversion at all.
        wav_buf = _am.wrap_raw_audio_as_wav(pcm_bytes, sample_rate=_am.MIXER_SETTINGS["frequency"])
        sound = pygame.mixer.Sound(wav_buf)
        if not self._channel.get_busy():
            self._channel.play(sound)
            return
        # pygame.mixer.Channel.queue() has exactly ONE pending slot --
        # calling it again before the already-queued Sound is promoted to
        # "current" SILENTLY DROPS that pending sound and replaces it
        # (confirmed by direct testing against the installed pygame; not
        # documented as a FIFO). SynthEngine's mixer thread paces itself on
        # a fixed wall-clock cadence (see packages/synth/player.py) with no
        # guarantee it never runs even slightly ahead of actual playback --
        # every time it did, a whole chunk of audio silently vanished and
        # the next one resumed mid-phase, heard as periodic glitches/
        # warbling instead of one steady tone. Waiting here for the slot to
        # actually be free is what makes write() safe regardless of minor
        # timing drift -- a short, self-correcting wait, not a redesign of
        # the pacing itself.
        while self._channel.get_queue() is not None:
            pygame.time.wait(1)
        self._channel.queue(sound)

    def close(self) -> None:
        self._channel.stop()


class PygameAudioOutputDriver(AudioOutputDriver):
    def __init__(self) -> None:
        _am.initialize_audio_system()

    def play_pcm(self, pcm_bytes: bytes, sample_rate: int, blocking: bool = False) -> None:
        wav_buf = _am.wrap_raw_audio_as_wav(pcm_bytes, sample_rate=sample_rate)
        _am.play_audio_sync(wav_buf.getvalue())

    def play_file(self, path: str, blocking: bool = False) -> None:
        if blocking:
            _am.play_sfx_internal(path)
        else:
            _am.play_sfx(path)

    def stop(self) -> None:
        _am.stop_music()
        _am.stop_audio_stream()

    def open_pcm_stream(self, sample_rate: int) -> PCMStream:
        return _PygamePCMStream(sample_rate)

    def set_volume(self, volume: float) -> None:
        _am.set_music_volume(volume)
        _am.set_audio_stream_volume(volume)
