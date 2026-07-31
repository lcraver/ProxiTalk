"""tts package — thin wrapper around the existing, unmodified TTSEngineManager
(re-exposing its methods 1:1), plus a new speak_async() built on
Scheduler.run_background so apps never hand-roll a TTS worker thread the way
V1's proxi app did (~75 lines of tts_queue/tts_thread/tts_worker deleted by
using this instead)."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import core_os.packages.audio.engine as _am
from core_os.core import debug_log
from core_os.packages.tts.engine_manager import TTSEngineManager
from core_os.packages.tts.engines.base import EngineResources

from core_os.packages.base import Package, PackageResources


def _log_audio_sources_snapshot() -> None:
    """Dump every audio system's current state to the console so a queued
    TTS line's trace also shows what it's competing with (stream/music/mixer
    all share the one pygame mixer, so overlap here is exactly what causes
    garbled/cut-off playback). Console-only -- the on-screen speaker overlay
    shows live active status instead, via debug_log.set_active/clear_active."""
    stream_info = _am.get_audio_stream_info()
    print(
        "[Audio] Sources -- "
        f"stream: playing={stream_info['is_playing']} paused={stream_info['is_paused']} file={stream_info['file']} | "
        f"music: playing={_am.is_music_playing()} | "
        f"mixer_busy={bool(_am.pygame.mixer.get_busy()) if _am.pygame.mixer.get_init() else 'uninitialized'}",
        flush=True,
    )


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
        engine_id = self._manager.get_current_engine()
        preview = text if len(text) <= 60 else text[:57] + "..."
        print(f"[TTS] Queued line on '{engine_id}': \"{preview}\"", flush=True)
        _log_audio_sources_snapshot()

        def _work() -> bytes:
            debug_log.set_active("tts", f"[TTS] synthesizing ({engine_id}): \"{preview}\"")
            print(f"[TTS] Synthesizing on '{engine_id}': \"{preview}\"", flush=True)
            try:
                audio_bytes = self._manager.synthesize(text)
                print(f"[TTS] Synthesized {len(audio_bytes)} bytes", flush=True)
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
                    debug_log.set_active("tts", f"[TTS] speaking ({engine_id}): \"{preview}\"")
                    print(f"[TTS] Playing line on '{engine_id}'", flush=True)
                    _am.play_audio_sync(audio_bytes)
                    print(f"[TTS] Finished playing line on '{engine_id}'", flush=True)
            finally:
                debug_log.clear_active("tts")
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
