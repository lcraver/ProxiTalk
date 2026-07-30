"""audio package — sfx/music/streaming helpers. Simple one-shot playback goes
through the injected core.audio_output driver (so the platform branch lives
only in the backend); music/streaming reuse core_os's own engine.py
streamer/music-manager singletons for their richer semantics (pause/resume/
position tracking)."""

from __future__ import annotations

from typing import Any, Dict

import core_os.packages.audio.engine as _am

from core_os.packages.base import Package, PackageResources


class AudioPackage(Package):
    package_id = "audio"
    display_name = "Audio"
    priority = 20
    capability_tags = {"sfx", "music", "streaming"}
    core_requires = {"audio_output"}

    def initialize(self) -> None:
        pass

    def play_sfx(self, path: str) -> None:
        self.resources.core.audio_output.play_file(path, blocking=False)

    def play_music(self, path: str, loop: bool = True) -> None:
        _am.play_music(path, loop=loop)

    def stop_music(self) -> None:
        _am.stop_music()

    def set_music_volume(self, volume: float) -> None:
        _am.set_music_volume(volume)

    def is_music_playing(self) -> bool:
        return _am.is_music_playing()

    def start_stream(self, path: str, start_offset: float = 0.0) -> bool:
        return _am.start_audio_stream(path, start_offset)

    def pause_stream(self) -> None:
        _am.pause_audio_stream()

    def resume_stream(self) -> None:
        _am.resume_audio_stream()

    def stop_stream(self) -> None:
        _am.stop_audio_stream()

    def set_stream_volume(self, volume: float) -> None:
        _am.set_audio_stream_volume(volume)

    def get_stream_position(self) -> float:
        return _am.get_audio_stream_position()

    def is_stream_playing(self) -> bool:
        return _am.is_audio_stream_playing()

    def is_stream_paused(self) -> bool:
        return _am.is_audio_stream_paused()

    def get_stream_info(self) -> Dict[str, Any]:
        return _am.get_audio_stream_info()

    def get_duration(self, path: str) -> float:
        return _am.get_audio_duration(path)

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "play_sfx": self.play_sfx,
            "play_music": self.play_music,
            "stop_music": self.stop_music,
            "set_music_volume": self.set_music_volume,
            "is_music_playing": self.is_music_playing,
            "start_stream": self.start_stream,
            "pause_stream": self.pause_stream,
            "resume_stream": self.resume_stream,
            "stop_stream": self.stop_stream,
            "set_stream_volume": self.set_stream_volume,
            "get_stream_position": self.get_stream_position,
            "is_stream_playing": self.is_stream_playing,
            "is_stream_paused": self.is_stream_paused,
            "get_stream_info": self.get_stream_info,
            "get_duration": self.get_duration,
        }


AVAILABLE_PACKAGES = [AudioPackage]
