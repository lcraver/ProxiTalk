from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class EngineResources:
    """Shared configuration/state provided to every TTS engine."""

    is_windows: bool
    cache_dir: str
    config_dir: str
    user_preferences: Any
    paths: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)


class TTSEngine(ABC):
    """Interface all TTS engine implementations must follow."""

    engine_id: str = "base"
    display_name: str = "Base"
    priority: int = 100  # smaller values are preferred when auto-selecting
    capability_tags: set[str] = set()

    def __init__(self, resources: EngineResources):
        self.resources = resources

    @classmethod
    def is_available(cls, resources: EngineResources) -> bool:
        """Return True if the engine can run on this system."""

        return True

    @abstractmethod
    def initialize(self) -> None:
        """Perform any expensive start-up work (spawn processes, cache data, etc.)."""

    @abstractmethod
    def synthesize(self, text: str, timeout: Optional[float] = None) -> bytes:
        """Return raw audio bytes for the requested text."""

    def shutdown(self) -> None:
        """Release resources or terminate background processes."""

    def capabilities(self) -> set[str]:
        """Optional hint describing extra features (voice selection, models, etc.)."""

        return set()

    def get_public_api(self) -> Dict[str, Any]:
        """Return a mapping of public helper methods exposed to the app layer."""

        return {}

    def cache_identity(self) -> Dict[str, Any]:
        """Provide state info for cache key generation (e.g., active voice/model)."""

        return {}
