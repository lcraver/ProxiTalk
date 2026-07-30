"""apps_registry package — enumerates apps/, loads metadata/icons.
Adapted from proxitalk.py's app-discovery logic, scoped to core_os's own
apps/ tree (resources.paths["apps_dir"]) instead of V1's old_apps/."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from PIL import Image

from core_os.packages.base import Package, PackageResources

_SKIP_DIRS = {"__pycache__"}


def _discover_app_dirs(base_dir: str, relative: str = "") -> List[str]:
    discovered: List[str] = []
    try:
        with os.scandir(base_dir) as entries:
            for entry in entries:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                if entry.name.startswith(".") or entry.name in _SKIP_DIRS:
                    continue
                next_relative = os.path.normpath(os.path.join(relative, entry.name)) if relative else entry.name
                main_path = os.path.join(entry.path, "main.py")
                if os.path.isfile(main_path):
                    discovered.append(next_relative)
                else:
                    discovered.extend(_discover_app_dirs(entry.path, next_relative))
    except FileNotFoundError:
        pass
    return discovered


class AppsRegistryPackage(Package):
    package_id = "apps_registry"
    display_name = "Apps Registry"
    priority = 5
    capability_tags = {"apps"}

    def initialize(self) -> None:
        self._apps_dir = self.resources.paths.get("apps_dir")
        self._overlay_dir = self.resources.paths.get("overlay_dir")
        self._apps: List[Dict[str, Any]] = []
        self._by_name: Dict[str, Dict[str, Any]] = {}
        self.refresh()

    def refresh(self) -> None:
        apps: List[Dict[str, Any]] = []
        by_name: Dict[str, Dict[str, Any]] = {}
        if self._apps_dir:
            for relative_path in sorted(_discover_app_dirs(self._apps_dir)):
                folder = os.path.basename(relative_path)
                entry = {
                    "name": folder,
                    "path": relative_path,
                    "metadata": self._load_metadata(relative_path),
                }
                apps.append(entry)
                by_name[folder] = entry
        self._apps = apps
        self._by_name = by_name

    def _load_metadata(self, relative_path: str) -> Dict[str, Any]:
        metadata_path = os.path.join(self._apps_dir, relative_path, "metadata.json")
        default: Dict[str, Any] = {
            "name": relative_path,
            "version": "unknown",
            "type": "app",
            "description": "",
            "author": "Unknown",
            "packages": [],
        }
        if os.path.isfile(metadata_path):
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default.update(data)
            except Exception as exc:
                print(f"[apps_registry] Failed to read metadata for '{relative_path}': {exc}")
        return default

    def load_icon(self, app_identifier: str, state: Optional[str] = None) -> Optional[Image.Image]:
        entry = self._by_name.get(app_identifier)
        relative_path = entry["path"] if entry else app_identifier
        filename = f"icon_{state}.png" if state else "icon.png"
        icon_path = os.path.join(self._apps_dir, relative_path, filename)
        if os.path.isfile(icon_path):
            return Image.open(icon_path).convert("1")
        return None

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "all": self._apps,
            "by_name": self._by_name,
            "apps_dir": self._apps_dir,
            "overlay_dir": self._overlay_dir,
            "load_icon": self.load_icon,
            "refresh": self.refresh,
        }


AVAILABLE_PACKAGES = [AppsRegistryPackage]
