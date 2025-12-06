from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Iterable, List, Type

from .base import EngineResources, TTSEngine


def discover_engine_classes(resources: EngineResources) -> List[Type[TTSEngine]]:
    """Import every module inside tts_engines/ and collect TTSEngine subclasses."""

    package = importlib.import_module(__name__.rsplit(".", 1)[0])
    package_path = Path(package.__file__).parent
    engine_classes: List[Type[TTSEngine]] = []

    for module_info in pkgutil.iter_modules([str(package_path)]):
        name = module_info.name
        if name.startswith("_") or name in {"base", "loader"}:
            continue
        full_name = f"{package.__name__}.{name}"
        module = importlib.import_module(full_name)
        candidates: Iterable[Type[TTSEngine]] = getattr(module, "AVAILABLE_ENGINES", [])
        for cls in candidates:
            if not issubclass(cls, TTSEngine):
                continue
            if not cls.is_available(resources):
                continue
            engine_classes.append(cls)

    # Sort by priority (lower first) then by engine id for deterministic ordering
    engine_classes.sort(key=lambda cls: (getattr(cls, "priority", 100), cls.engine_id))
    return engine_classes
