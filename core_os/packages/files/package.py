"""files package — read/write access to the device's filesystem, for apps
like file_browser that need to list/rename/delete/preview whatever's there
rather than a fixed path an app already knows about.

Every method takes an absolute `path` (falsy/omitted means `root_dir()`,
the on-device `files/` folder V1 apps like gallery/pt_browser already save
downloads into -- a sensible starting point, not a sandbox boundary).
`filesystem_root()` + `parent_of()` let a caller walk all the way up to the
top of the drive/device and back down any other branch -- there's no
confinement to `root_dir()` here, unlike apps_registry only ever reading
under APPS_DIR: this is the one package whose whole point is letting an app
(file_browser) go anywhere the OS user account can, the same as any other
file manager.
"""

from __future__ import annotations

import os
import shutil
from typing import Any, Dict, List, Optional

from core_os.packages.base import Package, PackageResources


class FilesPackage(Package):
    package_id = "files"
    display_name = "Files"
    priority = 20
    capability_tags = {"files"}

    def initialize(self) -> None:
        self._root = os.path.realpath(self.resources.files_dir)
        os.makedirs(self._root, exist_ok=True)
        # Top of the drive (Windows, e.g. "C:\") or the device (POSIX "/")
        # -- the furthest parent_of() can walk up to.
        drive, _ = os.path.splitdrive(self._root)
        self._fs_root = os.path.realpath(drive + os.sep) if drive else os.path.realpath(os.sep)

    def _normalize(self, path: str) -> str:
        return os.path.realpath(path) if path else self._root

    # --- reading --------------------------------------------------------

    def root_dir(self) -> str:
        """The on-device `files/` folder -- a convenient "home" location,
        not a boundary anything else here enforces."""
        return self._root

    def filesystem_root(self) -> str:
        """Top of the drive/device -- parent_of() never goes past this."""
        return self._fs_root

    def parent_of(self, path: str = "") -> Optional[str]:
        """Absolute parent dir of `path`, or None once `path` already IS
        a filesystem root (nothing further up).

        Checked via splitdrive's (drive, tail) rather than comparing
        dirname(path) back against path -- on Windows, os.path.dirname/
        realpath treat the BARE drive letter "C:" (no trailing separator)
        as "current directory on that drive", not the drive's root, so a
        naive dirname-based stop condition never actually fires there and
        walks back into the process's cwd on that drive instead of
        stopping; splitdrive's tail is empty (or just the separator) only
        for a genuine root, on both Windows and POSIX."""
        abs_path = self._normalize(path)
        _, tail = os.path.splitdrive(abs_path)
        if tail in ("", os.sep, "/"):
            return None
        parent = os.path.dirname(abs_path)
        if not parent or parent == abs_path:
            return None
        return parent

    def resolve_path(self, path: str = "") -> str:
        """Absolute path for `path` (or root_dir() if omitted) -- for
        handing to other packages that draw/play files directly, e.g.
        images.draw_file(files.resolve_path(path))."""
        return self._normalize(path)

    def exists(self, path: str = "") -> bool:
        return os.path.exists(self._normalize(path))

    def is_dir(self, path: str = "") -> bool:
        return os.path.isdir(self._normalize(path))

    def list_dir(self, path: str = "") -> List[Dict[str, Any]]:
        abs_dir = self._normalize(path)
        if not os.path.isdir(abs_dir):
            raise NotADirectoryError(f"Not a directory: '{path}'")
        entries = []
        try:
            names = os.listdir(abs_dir)
        except OSError:
            # Permission-denied directories (common once navigation leaves
            # root_dir() for OS-owned locations) show up as empty rather
            # than crashing the whole list.
            names = []
        for name in names:
            full = os.path.join(abs_dir, name)
            try:
                entry_is_dir = os.path.isdir(full)
                stat = os.stat(full)
                size = 0 if entry_is_dir else stat.st_size
                mtime = stat.st_mtime
            except OSError:
                entry_is_dir, size, mtime = False, 0, 0.0
            entries.append({"name": name, "is_dir": entry_is_dir, "size": size, "mtime": mtime})
        # Directories first, then alphabetical (case-insensitive) within
        # each group -- matches the convention most file managers use.
        entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
        return entries

    def read_text(self, path: str, max_bytes: int = 4096) -> Optional[Dict[str, Any]]:
        """Best-effort text preview -- returns None for content that isn't
        valid UTF-8 (treated as binary) rather than replacing it with
        mangled/garbage characters."""
        abs_path = self._normalize(path)
        with open(abs_path, "rb") as f:
            raw = f.read(max_bytes + 1)
        truncated = len(raw) > max_bytes
        if truncated:
            raw = raw[:max_bytes]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return {"text": text, "truncated": truncated}

    # --- writing --------------------------------------------------------

    def make_dir(self, path: str) -> None:
        os.makedirs(self._normalize(path), exist_ok=True)

    def _guard_protected(self, abs_path: str) -> None:
        if abs_path in (self._root, self._fs_root):
            raise ValueError(f"Refusing to modify '{abs_path}' -- it's a root location")

    def delete(self, path: str) -> None:
        abs_path = self._normalize(path)
        self._guard_protected(abs_path)
        if os.path.isdir(abs_path):
            shutil.rmtree(abs_path)
        else:
            os.remove(abs_path)

    def rename(self, path: str, new_name: str) -> str:
        """Renames the entry at `path` to `new_name` within the SAME
        parent directory (not a move) -- returns the new absolute path."""
        new_name = (new_name or "").strip()
        if not new_name or os.sep in new_name or (os.altsep and os.altsep in new_name) or new_name in (".", ".."):
            raise ValueError(f"Invalid file name: '{new_name}'")
        abs_path = self._normalize(path)
        self._guard_protected(abs_path)
        parent = os.path.dirname(abs_path)
        new_abs = os.path.join(parent, new_name)
        if os.path.exists(new_abs):
            raise FileExistsError(f"'{new_name}' already exists")
        os.rename(abs_path, new_abs)
        return new_abs

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "root_dir": self.root_dir,
            "filesystem_root": self.filesystem_root,
            "parent_of": self.parent_of,
            "resolve_path": self.resolve_path,
            "exists": self.exists,
            "is_dir": self.is_dir,
            "list_dir": self.list_dir,
            "read_text": self.read_text,
            "make_dir": self.make_dir,
            "delete": self.delete,
            "rename": self.rename,
        }


AVAILABLE_PACKAGES = [FilesPackage]
