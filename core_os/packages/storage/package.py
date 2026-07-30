"""storage package — thin wrapper around core_os.shared_config, the generic
dict-backed global store. Exposes get/set/update/all so apps and other
packages can read/write shared state without this package needing to know
what keys exist."""

from __future__ import annotations

from typing import Any, Dict

from core_os.packages.base import Package, PackageResources


class StoragePackage(Package):
    package_id = "storage"
    display_name = "Storage"
    priority = 5
    capability_tags = {"config"}

    def initialize(self) -> None:
        self._config = self.resources.shared_config

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "get": self._config.get,
            "set": self._config.set,
            "update": self._config.update,
            "all": self._config.all,
        }


AVAILABLE_PACKAGES = [StoragePackage]
