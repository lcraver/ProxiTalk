"""updater.py — checks GitHub Releases for a newer ProxiTalk version,
downloads and installs it, then reboots the device.

Only ever called from entry_device.py, before any hardware driver is built --
run_auto_update() is deliberately fail-open: no internet, a GitHub outage, a
malformed release, or any other error just falls through to booting the
current, already-working install. A flaky network must never be able to
block the device from starting up.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from typing import Callable, Optional, Tuple

REPO = "lcraver/ProxiTalk"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
USER_AGENT = "ProxiTalk-Updater"

# Paths that hold live user/device state -- never overwritten by an update,
# even though they're tracked in git (config/user_preferences.json is
# gitignored going forward but was committed historically, so a release
# zipball can still contain a stale copy of it).
PRESERVE_RELATIVE_PATHS = {
    os.path.join("config", "user_preferences.json"),
    os.path.join("config", "shared_config.json"),
    os.path.join("config", "discourse_login.conf"),
    "VERSION",
}


def has_internet(timeout: float = 3.0) -> bool:
    try:
        socket.create_connection(("api.github.com", 443), timeout=timeout).close()
        return True
    except OSError:
        return False


def _parse_version(version: str) -> Tuple[int, ...]:
    version = version.strip().lstrip("vV")
    parts = []
    for chunk in version.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(remote_version: str, local_version: str) -> bool:
    return _parse_version(remote_version) > _parse_version(local_version)


def read_local_version(repo_root: str) -> str:
    try:
        with open(os.path.join(repo_root, "VERSION"), "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0.0.0"


def write_local_version(repo_root: str, version: str) -> None:
    with open(os.path.join(repo_root, "VERSION"), "w", encoding="utf-8") as f:
        f.write(version.strip() + "\n")


def fetch_latest_release(timeout: float = 5.0) -> Optional[dict]:
    request = urllib.request.Request(
        API_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"[updater] Failed to fetch latest release: {exc}")
        return None


def download_zip(
    url: str,
    dest_path: str,
    timeout: float = 60.0,
    on_progress: Optional[Callable[[float], None]] = None,
) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, open(dest_path, "wb") as out_file:
            total = response.headers.get("Content-Length")
            total = int(total) if total else 0
            read = 0
            last_percent = -1
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                out_file.write(chunk)
                read += len(chunk)
                if on_progress is not None and total:
                    percent = int(read * 100 / total)
                    if percent != last_percent:
                        last_percent = percent
                        on_progress(read / total)
        return True
    except (urllib.error.URLError, OSError) as exc:
        print(f"[updater] Failed to download update: {exc}")
        return False


def extract_zip(zip_path: str, extract_dir: str) -> Optional[str]:
    """GitHub's auto-generated zipball wraps everything in a single
    `<owner>-<repo>-<sha>/` top-level folder -- that's what gets returned."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
        entries = [e for e in os.listdir(extract_dir) if os.path.isdir(os.path.join(extract_dir, e))]
        if len(entries) != 1:
            print(f"[updater] Unexpected archive layout: {entries}")
            return None
        return os.path.join(extract_dir, entries[0])
    except (zipfile.BadZipFile, OSError) as exc:
        print(f"[updater] Failed to extract update: {exc}")
        return None


def install_update(extracted_root: str, repo_root: str) -> None:
    """Copy every file from the extracted release over repo_root, skipping
    PRESERVE_RELATIVE_PATHS so live user/device state survives the update.
    Files not present in the release (recordings, caches, etc.) are left
    untouched -- this only overlays, never wipes repo_root first."""
    for dirpath, _dirnames, filenames in os.walk(extracted_root):
        rel_dir = os.path.relpath(dirpath, extracted_root)
        for filename in filenames:
            rel_path = filename if rel_dir == "." else os.path.join(rel_dir, filename)
            if rel_path in PRESERVE_RELATIVE_PATHS:
                continue
            src = os.path.join(dirpath, filename)
            dst = os.path.join(repo_root, rel_path)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)


def reboot() -> None:
    print("[updater] Rebooting to apply update...")
    subprocess.run(["sudo", "reboot"], check=False)


def run_auto_update(repo_root: str, enabled: bool = True, ui=None) -> bool:
    """Returns True only once a new version has been installed and a reboot
    has been triggered -- the caller should stop booting immediately in that
    case rather than continuing on into the old, now-overwritten process
    image.

    `ui`, if given, is an updater_ui.UpdaterUI (or anything with the same
    show_lines/show_progress methods) used to render progress on the
    device's own screen -- entirely optional so this stays testable/callable
    headless (emulator, unit tests, no display driver available yet)."""
    if not enabled:
        return False

    try:
        if ui is not None:
            ui.show_lines(["Checking for", "updates..."])

        if not has_internet():
            print("[updater] No internet connection, skipping update check.")
            return False

        release = fetch_latest_release()
        if release is None:
            return False

        remote_version = release.get("tag_name", "")
        local_version = read_local_version(repo_root)
        if not remote_version or not is_newer(remote_version, local_version):
            print(f"[updater] Already up to date (local={local_version}, latest={remote_version}).")
            return False

        zip_url = release.get("zipball_url")
        if not zip_url:
            print("[updater] Release has no zipball_url, skipping.")
            return False

        print(f"[updater] New version available: {local_version} -> {remote_version}")
        if ui is not None:
            ui.show_lines([f"Update found: {remote_version}", "Downloading..."])

        with tempfile.TemporaryDirectory(prefix="proxitalk_update_") as tmp_dir:
            zip_path = os.path.join(tmp_dir, "release.zip")

            def _on_progress(fraction: float) -> None:
                if ui is not None:
                    ui.show_progress("Downloading update", fraction)

            if not download_zip(zip_url, zip_path, on_progress=_on_progress):
                if ui is not None:
                    ui.show_lines(["Update failed", "Continuing boot..."])
                return False

            if ui is not None:
                ui.show_lines(["Installing update..."])

            extracted_root = extract_zip(zip_path, os.path.join(tmp_dir, "extracted"))
            if extracted_root is None:
                if ui is not None:
                    ui.show_lines(["Update failed", "Continuing boot..."])
                return False

            install_update(extracted_root, repo_root)
            write_local_version(repo_root, remote_version)

        print(f"[updater] Installed version {remote_version}.")
        if ui is not None:
            ui.show_lines(["Update installed", "Rebooting..."])
        reboot()
        return True
    except Exception as exc:  # never let an update failure block boot
        print(f"[updater] Update check failed unexpectedly: {exc}")
        if ui is not None:
            try:
                ui.show_lines(["Update failed", "Continuing boot..."])
            except Exception:
                pass
        return False
