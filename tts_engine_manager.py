from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Type

from tts_engines.base import EngineResources, TTSEngine
from tts_engines.loader import discover_engine_classes


@dataclass
class EngineEntry:
    cls: Type[TTSEngine]
    instance: Optional[TTSEngine] = None


class TTSEngineManager:
    def __init__(self, resources: EngineResources, preferred_engine: Optional[str] = None):
        self.resources = resources
        self._entries: Dict[str, EngineEntry] = {}
        for engine_cls in discover_engine_classes(resources):
            self._entries[engine_cls.engine_id] = EngineEntry(cls=engine_cls)
        if not self._entries:
            raise RuntimeError("No TTS engines available. Install at least one TTS plug-in.")
        self._current_engine_id: Optional[str] = None
        default_engine = preferred_engine if preferred_engine in self._entries else next(iter(self._entries))
        self.set_engine(default_engine)

    # ----- Internal helpers -----
    def _get_entry(self, engine_id: str) -> Optional[EngineEntry]:
        return self._entries.get(engine_id)

    def _ensure_instance(self, engine_id: str) -> Optional[TTSEngine]:
        entry = self._get_entry(engine_id)
        if not entry:
            print(f"[TTS] Engine '{engine_id}' not available")
            return None
        if not entry.instance:
            try:
                entry.instance = entry.cls(self.resources)
                entry.instance.initialize()
            except Exception as exc:
                print(f"[TTS] Failed to initialize engine '{engine_id}': {exc}")
                entry.instance = None
        return entry.instance

    def _call_engine_method(self, engine_id: str, method_name: str, *args, **kwargs):
        instance = self._ensure_instance(engine_id)
        if not instance:
            return None
        method = getattr(instance, method_name, None)
        if not method:
            print(f"[TTS] Engine '{engine_id}' does not implement '{method_name}'")
            return None
        return method(*args, **kwargs)

    # ----- Public API -----
    def get_available_engine_ids(self) -> list[str]:
        return list(self._entries.keys())

    def get_current_engine(self) -> Optional[str]:
        return self._current_engine_id

    def set_engine(self, engine_id: str) -> bool:
        if engine_id not in self._entries:
            print(f"[TTS] Invalid engine: {engine_id}")
            return False
        if self._current_engine_id == engine_id:
            return True

        if self._current_engine_id:
            current_entry = self._entries[self._current_engine_id]
            if current_entry.instance:
                try:
                    current_entry.instance.shutdown()
                except Exception as exc:
                    print(f"[TTS] Warning: error shutting down '{self._current_engine_id}': {exc}")
                current_entry.instance = None

        instance = self._ensure_instance(engine_id)
        if not instance:
            print(f"[TTS] Unable to initialize engine '{engine_id}'")
            return False

        self._current_engine_id = engine_id
        print(f"[TTS] Active engine set to '{engine_id}'")
        return True

    def synthesize(self, text: str) -> bytes:
        if not self._current_engine_id:
            print("[TTS] No engine selected")
            return b""
        instance = self._ensure_instance(self._current_engine_id)
        if not instance:
            return b""
        return instance.synthesize(text)

    def close_all(self) -> None:
        for engine_id, entry in self._entries.items():
            if entry.instance:
                try:
                    entry.instance.shutdown()
                except Exception as exc:
                    print(f"[TTS] Warning: error shutting down '{engine_id}': {exc}")
                entry.instance = None

    # ----- Dynamic helpers -----
    def describe_engines(self) -> Dict[str, Dict[str, Any]]:
        description: Dict[str, Dict[str, Any]] = {}
        for engine_id, entry in self._entries.items():
            capability_tags = getattr(entry.cls, "capability_tags", set())
            description[engine_id] = {
                "engine_id": engine_id,
                "display_name": getattr(entry.cls, "display_name", engine_id),
                "priority": getattr(entry.cls, "priority", 100),
                "capabilities": sorted(capability_tags),
            }
        return description

    def get_engine_capabilities(self, engine_id: Optional[str] = None) -> list[str]:
        target_id = engine_id or self._current_engine_id
        if not target_id:
            return []
        description = self.describe_engines()
        engine_info = description.get(target_id)
        if not engine_info:
            return []
        return engine_info.get("capabilities", [])

    def get_engine_api(self, engine_id: Optional[str] = None) -> Dict[str, Any]:
        target_id = engine_id or self._current_engine_id
        if not target_id:
            return {}
        instance = self._ensure_instance(target_id)
        if not instance:
            return {}
        try:
            api = instance.get_public_api()
            return api or {}
        except Exception as exc:
            print(f"[TTS] Engine '{target_id}' failed to provide public API: {exc}")
            return {}

    def call_engine_api(
        self,
        method_name: str,
        *args,
        engine_id: Optional[str] = None,
        **kwargs,
    ):
        target_id = engine_id or self._current_engine_id
        if not target_id:
            print(f"[TTS] Cannot call API '{method_name}' without an active engine")
            return None
        api = self.get_engine_api(target_id)
        func = api.get(method_name)
        if not func:
            print(f"[TTS] Engine '{target_id}' does not expose API '{method_name}'")
            return None
        return func(*args, **kwargs)

    def get_cache_identity(self, engine_id: Optional[str] = None) -> Dict[str, Any]:
        target_id = engine_id or self._current_engine_id
        if not target_id:
            return {}
        instance = self._ensure_instance(target_id)
        if not instance:
            return {}
        try:
            identity = instance.cache_identity() or {}
            if not isinstance(identity, dict):
                return {}
            safe_identity = {}
            for key, value in identity.items():
                if value is None:
                    continue
                safe_identity[str(key)] = str(value)
            return safe_identity
        except Exception as exc:
            print(f"[TTS] Engine '{target_id}' cache identity error: {exc}")
            return {}
