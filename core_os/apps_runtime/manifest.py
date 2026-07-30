"""v2 metadata.json reader/validator — extends the existing V1 schema
(name/version/description/author/cursor_enabled) with an explicit "type" and
a "packages" array declaring which Packages an app's scoped context should
contain (mirrors Flipper Zero's .fam deps list).

Every field is optional except "packages" (defaults to an empty list if
omitted, but must be a list of strings if present). Minimal example:

    {
      "name": "My App",
      "version": "1.0",
      "description": "What it does.",
      "author": "Your Name",
      "type": "app",
      "cursor_enabled": false,
      "packages": ["display_gfx", "ui", "storage"]
    }

"packages" controls exactly what shows up in this app's context dict — see
ScopedAppContext in app_loader.py — declare a package_id here (any id a
Package under core_os/packages/<id>/package.py registers, e.g. "ui",
"audio", "tts", "language", "animation", "leds", "storage",
"apps_registry") to get context["<id>"] populated with that package's
get_public_api() dict. Declaring an id no Package registers fails loudly at
load time (AppLoadError), rather than silently omitting it."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List


class ManifestError(RuntimeError):
    pass


@dataclass
class AppManifest:
    name: str
    version: str
    description: str
    author: str
    type: str = "app"
    cursor_enabled: bool = False
    packages: List[str] = field(default_factory=list)


def read_manifest(app_dir: str) -> AppManifest:
    path = os.path.join(app_dir, "metadata.json")
    if not os.path.isfile(path):
        raise ManifestError(f"No metadata.json found in '{app_dir}'")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    packages = data.get("packages", [])
    if not isinstance(packages, list) or not all(isinstance(p, str) for p in packages):
        raise ManifestError(f"'{path}': \"packages\" must be a list of strings")

    return AppManifest(
        name=data.get("name", os.path.basename(app_dir)),
        version=data.get("version", "unknown"),
        description=data.get("description", ""),
        author=data.get("author", "Unknown"),
        type=data.get("type", "app"),
        cursor_enabled=bool(data.get("cursor_enabled", False)),
        packages=packages,
    )
