"""scaffold_app.py — generates a new apps/<name>/ directory with a minimal
metadata.json + main.py + strings.json, so starting a new app doesn't mean
copy-pasting an existing one and stripping out its unrelated logic by hand.

Usage (from repo root):
    .venv\\Scripts\\python.exe -m core_os.devtools.scaffold_app my_app
    .venv\\Scripts\\python.exe -m core_os.devtools.scaffold_app my_app --packages display_gfx,ui,storage

The generated app is immediately loadable by AppLoader/AppControl (e.g. from
the launcher, or via `app_control.swap_app_async(...)`) with no further
wiring required.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_DEFAULT_PACKAGES = ["display_gfx", "ui"]

_MAIN_TEMPLATE = '''"""{title} — describe what this app does here."""

from __future__ import annotations

from core_os.apps_runtime.app_base import AppBase


class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.context = context
        self.gfx = context["display_gfx"]
        self.ui = context["ui"]
        self.app_control = context["app_control"]
        self.screen_width = context["screen_width"]
        self.screen_height = context["screen_height"]

    def start(self):
        self.gfx["clear_screen"]()
        label = self.ui["label"]("{title}")
        label.set_bounds(0, 0, self.screen_width, self.screen_height)
        label.draw()

    def update(self):
        pass

    def onkeydown(self, keycode):
        if keycode == "KEY_ESC":
            self.app_control.swap_app_async("{name}", "launcher", delay=0.1)

    def onkeyup(self, keycode):
        pass

    def stop(self):
        pass
'''


def _title_case(name: str) -> str:
    return " ".join(word.capitalize() for word in name.replace("-", "_").split("_"))


def scaffold(apps_dir: str, name: str, packages, author: str) -> str:
    app_dir = os.path.join(apps_dir, name)
    if os.path.exists(app_dir):
        raise FileExistsError(f"App directory already exists: '{app_dir}'")

    title = _title_case(name)
    os.makedirs(app_dir)

    metadata = {
        "name": title,
        "version": "1.0",
        "description": "",
        "author": author,
        "type": "app",
        "cursor_enabled": False,
        "packages": packages,
    }
    with open(os.path.join(app_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
        f.write("\n")

    with open(os.path.join(app_dir, "main.py"), "w", encoding="utf-8") as f:
        f.write(_MAIN_TEMPLATE.format(title=title, name=name))

    strings = {f"apps.{name}": {"en": title, "ja": title}}
    with open(os.path.join(app_dir, "strings.json"), "w", encoding="utf-8") as f:
        json.dump(strings, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return app_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold a new core_os app.")
    parser.add_argument("name", help="App directory name, e.g. 'my_app' (snake_case).")
    parser.add_argument(
        "--packages", default=",".join(_DEFAULT_PACKAGES),
        help=f"Comma-separated package ids to declare (default: {','.join(_DEFAULT_PACKAGES)}).",
    )
    parser.add_argument("--author", default="Unknown")
    parser.add_argument(
        "--apps-dir", default=None,
        help="Override apps directory (default: apps/ at the repo root).",
    )
    args = parser.parse_args()

    apps_dir = args.apps_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "apps"
    )
    packages = [p.strip() for p in args.packages.split(",") if p.strip()]

    try:
        app_dir = scaffold(apps_dir, args.name, packages, args.author)
    except FileExistsError as exc:
        print(f"[scaffold_app] {exc}")
        sys.exit(1)

    print(f"[scaffold_app] Created '{app_dir}' with metadata.json + main.py + strings.json")


if __name__ == "__main__":
    main()
