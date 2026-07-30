"""dev_state.py — persists which app was in the foreground across a
DevWatcher-triggered restart (os.execv), so `--dev` hot-reload lands back on
whatever app you were testing instead of always restarting at the launcher.
Written on every app swap (see AppControl's `on_app_changed`), read once at
startup (see bootstrap.run) and deleted immediately after -- a genuine cold
start (no --dev, or no restart happened) always still defaults to the
launcher, since nothing ever wrote the file in that case."""

from __future__ import annotations

import json
import os
from typing import Optional

_STATE_FILENAME = "dev_last_app.json"


def _state_path(state_dir: str) -> str:
    return os.path.join(state_dir, _STATE_FILENAME)


def save_last_app(state_dir: str, app_name: str) -> None:
    try:
        os.makedirs(state_dir, exist_ok=True)
        with open(_state_path(state_dir), "w", encoding="utf-8") as f:
            json.dump({"app": app_name}, f)
    except OSError as exc:
        print(f"[DevState] Failed to persist last app: {exc}")


def load_and_clear_last_app(state_dir: str) -> Optional[str]:
    path = _state_path(state_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"[DevState] Failed to read last app: {exc}")
        return None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return data.get("app")
