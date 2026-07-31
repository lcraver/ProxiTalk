"""Real hardware audio driver — plays back via aplay (ALSA), using core_os's
own audio engine (core_os/packages/audio/engine.py)."""

from __future__ import annotations

import subprocess

import core_os.packages.audio.engine as _am

from core_os.core.drivers.base import AudioOutputDriver, PCMStream


class _AplayPCMStream(PCMStream):
    """ONE persistent `aplay` process, stdin kept open for the stream's
    whole lifetime -- distinct from play_pcm's per-call
    Popen(...).communicate(), which spawns a fresh process and closes stdin
    every call. aplay just blocks reading stdin between writes; no re-open
    needed between chunks, and unlike two independent per-call aplay
    processes (the concurrency risk a fully polyphonic design would have
    hit -- see packages/synth/player.py's docstring), there's only ever
    ONE aplay process for this stream's entire lifetime, so there's no
    device-contention risk between chunks the way there would be between
    two SEPARATE overlapping play_pcm calls."""

    def __init__(self, sample_rate: int) -> None:
        # -c 1 explicit, not relying on aplay's raw-mode default -- the
        # Windows pygame backend's equivalent implicit assumption (that
        # requesting a mono mixer actually gets one) turned out to be
        # false on real hardware (SDL silently substituted stereo), which
        # silently played every synth chunk at ~2x speed with garbled
        # channel data. No evidence of the equivalent bug here, but
        # there's no reason to lean on an unstated default a second time.
        self._proc = subprocess.Popen(
            ["aplay", "-r", str(sample_rate), "-c", "1", "-f", "S16_LE", "-t", "raw", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    def write(self, pcm_bytes: bytes) -> None:
        self._proc.stdin.write(pcm_bytes)
        self._proc.stdin.flush()

    def close(self) -> None:
        try:
            self._proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        try:
            self._proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()


class AplayAudioOutputDriver(AudioOutputDriver):
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
        return _AplayPCMStream(sample_rate)

    def set_volume(self, volume: float) -> None:
        _am.set_music_volume(volume)
        _am.set_audio_stream_volume(volume)
