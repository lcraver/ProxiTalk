"""Windows dev-machine audio driver — wraps core_os's own pygame-mixer audio
engine (core_os/packages/audio/engine.py) behind the AudioOutputDriver
contract."""

from __future__ import annotations

import core_os.packages.audio.engine as _am

from core_os.core.drivers.base import AudioOutputDriver


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

    def set_volume(self, volume: float) -> None:
        _am.set_music_volume(volume)
        _am.set_audio_stream_volume(volume)
