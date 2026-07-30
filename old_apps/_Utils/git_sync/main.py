import json
import os
import shutil
import tempfile
import threading
import time
import zipfile
from urllib import error, request

from interfaces import AppBase


class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.context = context
        self.draw = context["drawing"]
        self.font_small = context["fonts"]["small"]
        self.width = context["screen_width"]
        self.height = context["screen_height"]
        self.apps_dir = context.get("APPS_DIR")
        self.overlays_dir = context.get("OVERLAY_DIR")
        self.files_dir = context.get("FILES_DIR") or context.get("files_dir")
        self.state_path = os.path.join(self.files_dir or self.apps_dir, "git_sync_state.json")

        self.repo_owner = "lcraver"
        self.repo_name = "ProxiTalk"
        self.branch = "main"
        self.http_headers = {"User-Agent": "ProxiTalk-GitSync/1.0"}

        self.status_lines = []
        self.progress_text = ""
        self.remote_sha = None
        self.local_sha = None
        self.last_sync_time = None
        self.needs_redraw = True
        self.sync_thread = None
        self.sync_active = False
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.spinner_frames = "|/-\\"
        self.spinner_index = 0
        self.last_spinner_tick = 0

    def start(self):
        self.load_state()
        self.add_log("Ready. Press ENTER to sync.")
        self.mark_dirty()
        self.start_sync(auto=True)

    def stop(self):
        self.stop_event.set()
        if self.sync_thread and self.sync_thread.is_alive():
            self.sync_thread.join(timeout=1.0)

    def start_sync(self, auto=False):
        if self.sync_thread and self.sync_thread.is_alive():
            if not auto:
                self.add_log("Sync already running.")
            return
        self.stop_event.clear()
        self.sync_thread = threading.Thread(target=self.sync_worker, daemon=True)
        self.sync_thread.start()

    def sync_worker(self):
        zip_path = None
        self.set_sync_state(True)
        try:
            self.add_log("Checking GitHub...")
            remote_sha = self.fetch_remote_sha()
            if not remote_sha:
                raise RuntimeError("Unable to read remote commit")
            self.remote_sha = remote_sha
            self.mark_dirty()

            if remote_sha == self.local_sha:
                self.add_log("Device already up to date.")
                return

            self.add_log("Downloading snapshot...")
            zip_path = self.download_repo_snapshot()
            self.raise_if_stopped()

            app_files = self.extract_subtree(zip_path, "apps", self.apps_dir)
            overlay_files = self.extract_subtree(zip_path, "overlays", self.overlays_dir)

            self.save_state(remote_sha)
            self.add_log(f"Sync complete ({app_files} app files, {overlay_files} overlay files).")
            self.add_log("Restart apps via launcher to reload.")
        except Exception as exc:  # noqa: BLE001
            self.add_log(f"Error: {exc}")
        finally:
            self.set_sync_state(False)
            self.progress_text = ""
            if zip_path and os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except OSError:
                    pass
            self.mark_dirty()

    def fetch_remote_sha(self):
        api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/commits/{self.branch}"
        req = request.Request(api_url, headers=self.http_headers)
        try:
            with request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("sha")
        except error.URLError as exc:
            raise RuntimeError(f"GitHub request failed: {exc.reason}") from exc

    def download_repo_snapshot(self):
        download_url = f"https://codeload.github.com/{self.repo_owner}/{self.repo_name}/zip/refs/heads/{self.branch}"
        req = request.Request(download_url, headers=self.http_headers)
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="proxitalk_sync_", suffix=".zip")
        downloaded = 0
        total = None
        try:
            with os.fdopen(tmp_fd, "wb") as tmp_file, request.urlopen(req, timeout=40) as resp:
                total_header = resp.headers.get("Content-Length")
                total = int(total_header) if total_header else None
                while not self.stop_event.is_set():
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    tmp_file.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        percent = int((downloaded / total) * 100)
                        self.progress_text = f"Download {percent}%"
                    else:
                        self.progress_text = f"Download {downloaded // 1024}KB"
                    self.mark_dirty()
        except error.URLError as exc:
            raise RuntimeError(f"Download failed: {exc.reason}") from exc
        self.raise_if_stopped()
        return tmp_path

    def extract_subtree(self, zip_path, folder_name, destination):
        if not destination or not os.path.isdir(destination):
            return 0
        extracted_files = 0
        with zipfile.ZipFile(zip_path, "r") as archive:
            root_prefix = self.detect_root_prefix(archive)
            if not root_prefix:
                raise RuntimeError("Unexpected archive structure")
            target_prefix = f"{root_prefix}{folder_name}/"
            for member in archive.infolist():
                if not member.filename.startswith(target_prefix):
                    continue
                relative_path = member.filename[len(target_prefix):]
                if not relative_path:
                    continue
                safe_rel = os.path.normpath(relative_path)
                if safe_rel.startswith(".."):
                    continue
                destination_path = os.path.join(destination, safe_rel)
                if member.is_dir():
                    os.makedirs(destination_path, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(destination_path), exist_ok=True)
                with archive.open(member) as src, open(destination_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                extracted_files += 1
        return extracted_files

    def detect_root_prefix(self, archive):
        for name in archive.namelist():
            if "/" in name:
                return name.split("/", 1)[0] + "/"
        return None

    def save_state(self, sha_value):
        state_dir = os.path.dirname(self.state_path)
        if state_dir and not os.path.isdir(state_dir):
            os.makedirs(state_dir, exist_ok=True)
        record = {
            "last_sha": sha_value,
            "synced_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2)
        self.local_sha = sha_value
        self.last_sync_time = record["synced_at"]
        self.mark_dirty()

    def load_state(self):
        if not os.path.isfile(self.state_path):
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
                self.local_sha = data.get("last_sha")
                self.last_sync_time = data.get("synced_at")
        except (json.JSONDecodeError, OSError) as exc:
            self.add_log(f"State read failed: {exc}")

    def raise_if_stopped(self):
        if self.stop_event.is_set():
            raise RuntimeError("Sync canceled")

    def set_sync_state(self, active):
        self.sync_active = active
        self.last_spinner_tick = time.time()
        self.mark_dirty()

    def add_log(self, message):
        with self.lock:
            for chunk in self.wrap_text(message):
                self.status_lines.append(chunk)
            self.status_lines = self.status_lines[-6:]
        self.mark_dirty()

    def wrap_text(self, text, limit=22):
        words = text.split()
        if not words:
            return [""]
        lines = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if len(candidate) <= limit:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def mark_dirty(self):
        self.needs_redraw = True

    def format_sha(self, sha_value):
        if not sha_value:
            return "--"
        return sha_value[:7]

    def onkeyup(self, keycode):
        if keycode in ("KEY_ENTER", "KEY_SPACE"):
            self.start_sync(auto=False)
        elif keycode in ("KEY_ESC", "KEY_BACKSPACE"):
            app_manager = self.context.get("app_manager")
            if app_manager:
                app_manager.swap_app_async("git_sync", "launcher", update_rate_hz=20.0, delay=0.1)

    def update(self):
        now = time.time()
        if self.sync_active and now - self.last_spinner_tick > 0.2:
            self.spinner_index = (self.spinner_index + 1) % len(self.spinner_frames)
            self.last_spinner_tick = now
            self.mark_dirty()
        if self.needs_redraw:
            self.render()

    def render(self):
        self.draw["begin_batch"]()
        self.draw["clear_screen"]()

        title = "GitHub Sync"
        self.draw["draw_area"](0, 0, self.width, 9, 255)
        self.draw["draw_text"](title, 2, 1, self.font_small, 0)

        y = 11
        info_lines = [
            f"Remote: {self.format_sha(self.remote_sha)}",
            f"Local : {self.format_sha(self.local_sha)}",
        ]
        state_label = "Syncing " + self.spinner_frames[self.spinner_index] if self.sync_active else "Idle"
        info_lines.append(f"State : {state_label}")
        if self.last_sync_time:
            info_lines.append(f"Last  : {self.last_sync_time}")
        if self.progress_text:
            info_lines.append(self.progress_text)

        for line in info_lines:
            self.draw["draw_text"](line, 2, y, self.font_small, 255)
            y += 7

        y += 1
        for line in self.status_lines:
            if y > self.height - 10:
                break
            self.draw["draw_text"](line, 2, y, self.font_small, 255)
            y += 7

        help_text = "ENTER sync   ESC back"
        help_width = self.context["get_text_size"](help_text, self.font_small)[0]
        self.draw["draw_text"](help_text, max(0, (self.width - help_width) // 2), self.height - 8, self.font_small, 255)

        self.draw["end_batch"]()
        self.needs_redraw = False
