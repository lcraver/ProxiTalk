"""tts package — thin wrapper around the existing, unmodified TTSEngineManager
(re-exposing its methods 1:1), plus a new speak_async() built on
Scheduler.run_background so apps never hand-roll a TTS worker thread the way
V1's proxi app did (~75 lines of tts_queue/tts_thread/tts_worker deleted by
using this instead)."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import core_os.packages.audio.engine as _am
from core_os.packages.tts.engine_manager import TTSEngineManager
from core_os.packages.tts.engines.base import EngineResources

from core_os.packages.base import Package, PackageResources


class _EnginePrefsAdapter:
    """tts_engines/*.py is shared, unmodified code that also runs under the
    old config system, so it still expects a few typed getter/setter calls
    on `resources.user_preferences` (get_piper_model/set_piper_model,
    get_pyopenjtalk_voice/set_pyopenjtalk_voice). This translates those
    calls to shared_config reads/writes so the engines don't need to know
    core_os replaced its config system underneath them."""

    def __init__(self, shared_config) -> None:
        self._config = shared_config

    def get_piper_model(self):
        return self._config.get("piper_model")

    def set_piper_model(self, path) -> None:
        self._config.set("piper_model", path)

    def get_pyopenjtalk_voice(self):
        return self._config.get("pyopenjtalk_voice")

    def set_pyopenjtalk_voice(self, filename) -> None:
        self._config.set("pyopenjtalk_voice", filename)


class TTSPackage(Package):
    package_id = "tts"
    display_name = "Text-to-Speech"
    priority = 30
    capability_tags = {"speech"}

    def initialize(self) -> None:
        r = self.resources
        prefs_adapter = _EnginePrefsAdapter(r.shared_config) if r.shared_config is not None else None
        engine_resources = EngineResources(
            is_windows=r.is_windows,
            cache_dir=r.cache_dir,
            config_dir=r.config_dir,
            user_preferences=prefs_adapter,
            paths=r.paths,
            extra=r.extra,
        )
        preferred = r.shared_config.get("tts_engine") if r.shared_config is not None else None
        self._manager = TTSEngineManager(engine_resources, preferred_engine=preferred)

    def shutdown(self) -> None:
        self._manager.close_all()

    def speak_async(
        self,
        text: str,
        on_done: Optional[Callable[[bytes], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        play: bool = True,
    ) -> None:
        def _work() -> bytes:
            audio_bytes = self._manager.synthesize(text)
            if play and audio_bytes:
                # Engines don't agree on format: Piper returns raw headerless
                # PCM at a fixed 22050Hz, but openjtalk/voicevox return full
                # WAV files with their OWN embedded sample rate (openjtalk
                # ~48000Hz, voicevox 24000Hz). engine.play_audio_sync
                # already auto-detects RIFF-header WAV vs raw PCM (same logic
                # V1's TTS pipeline relies on) and plays each correctly --
                # going through core.audio_output.play_pcm() with a hardcoded
                # 22050Hz here previously forced every engine's output through
                # Piper's format, which for a real WAV file both misread its
                # header bytes as audio and played genuinely-48000Hz audio
                # tagged as 22050Hz (audibly slow + pitched down).
                _am.play_audio_sync(audio_bytes)
            return audio_bytes

        self.resources.core.scheduler.run_background(_work, on_done=on_done, on_error=on_error)

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "speak_async": self.speak_async,
            "synthesize": self._manager.synthesize,
            "set_engine": self._manager.set_engine,
            "get_engine": self._manager.get_current_engine,
            "get_available_engines": self._manager.get_available_engine_ids,
            "get_all_engines": self._manager.get_all_engine_ids,
            "get_disabled_engines": self._manager.get_disabled_engine_ids,
            "set_disabled_engines": self._manager.set_disabled_engines,
            "describe_engines": self._manager.describe_engines,
            "get_engine_capabilities": self._manager.get_engine_capabilities,
            "get_engine_api": self._manager.get_engine_api,
            "call_engine_api": self._manager.call_engine_api,
        }


AVAILABLE_PACKAGES = [TTSPackage]
