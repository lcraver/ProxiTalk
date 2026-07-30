"""shared_config — a plain dict backed by a JSON file, importable anywhere in
core_os to read/write state shared between packages and apps. Doesn't care
what keys exist or who owns them: get() on a missing key just returns the
given default instead of raising, and set() writes through immediately. No
schema, no per-field getters/setters to maintain as new settings get added.

Anything that wants config scoped to itself alone (not shared with anything
else) should keep its own config file in its own app/package directory
instead of putting it here.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict


class SharedConfig:
    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._save()

    def update(self, values: Dict[str, Any]) -> None:
        with self._lock:
            self._data.update(values)
            self._save()

    def all(self) -> Dict[str, Any]:
        return dict(self._data)


# Global instance — set by init(), then importable directly:
#   from core_os.shared_config import shared_config
shared_config: "SharedConfig | None" = None


def init(path: str) -> SharedConfig:
    global shared_config
    shared_config = SharedConfig(path)
    return shared_config


def open_app_config(app_path: str, filename: str = "config.json") -> SharedConfig:
    """Per-app config, stored in the app's own directory instead of the
    shared store above — for settings only that one app cares about, so
    they never collide with other apps' keys or bloat the shared file.
    Same plain-dict shape (get/set/update/all). `app_path` is the
    "app_path" universal field every app already gets in its context."""
    return SharedConfig(os.path.join(app_path, filename))
