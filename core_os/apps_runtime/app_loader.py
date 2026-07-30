"""AppLoader — resolves an app's declared packages into a ScopedAppContext
and instantiates its App class. Replaces AppManager's importlib loading + the
giant global context dict with a per-app scoped context built from only the
packages that app's manifest declares. Declaring an unknown package fails
loudly at load time rather than silently giving a partial context."""

from __future__ import annotations

import importlib.util
import os
from typing import Any, Dict

from core_os.apps_runtime.app_base import AppBase
from core_os.apps_runtime.app_host import AppHost
from core_os.apps_runtime.manifest import ManifestError, read_manifest
from core_os.packages.registry import PackageRegistry


class AppLoadError(RuntimeError):
    pass


class ScopedAppContext:
    """Passed to App.__init__ in place of V1's giant context dict. Behaves
    like a read-only dict but ONLY contains the packages an app declared in
    its manifest, plus a small fixed set of universal fields every app gets
    regardless of declaration (screen size, its own path, app_control)."""

    def __init__(self, package_apis: Dict[str, Dict[str, Any]], universal: Dict[str, Any]) -> None:
        self._data: Dict[str, Any] = {**universal, **package_apis}

    def __getitem__(self, key: str) -> Any:
        try:
            return self._data[key]
        except KeyError:
            raise KeyError(
                f"'{key}' is not in this app's context. Either it's misspelled, or the app's "
                f"metadata.json is missing \"{key}\" from its \"packages\" list. "
                f"Available keys: {sorted(self._data.keys())}"
            ) from None

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def keys(self):
        return self._data.keys()


class AppLoader:
    def __init__(
        self,
        apps_dir: str,
        package_registry: PackageRegistry,
        universal_fields: Dict[str, Any],
    ) -> None:
        self.apps_dir = apps_dir
        self.package_registry = package_registry
        self.universal_fields = universal_fields

    def _resolve_dir(self, app_name: str) -> str:
        return os.path.join(self.apps_dir, app_name)

    def load_app_instance(self, app_name: str) -> AppHost:
        app_dir = self._resolve_dir(app_name)
        if not os.path.isdir(app_dir):
            raise AppLoadError(f"App directory not found: '{app_dir}'")

        try:
            manifest = read_manifest(app_dir)
        except ManifestError as exc:
            raise AppLoadError(str(exc)) from exc

        package_apis: Dict[str, Dict[str, Any]] = {}
        for package_id in manifest.packages:
            if not self.package_registry.has_package(package_id):
                raise AppLoadError(f"App '{app_name}' requires unknown package '{package_id}'")
            package_apis[package_id] = self.package_registry.get_public_api(package_id)

        universal = dict(self.universal_fields)
        universal["app_path"] = os.path.normpath(app_dir) + os.sep

        scoped_context = ScopedAppContext(package_apis, universal)

        main_path = os.path.join(app_dir, "main.py")
        if not os.path.isfile(main_path):
            raise AppLoadError(f"No main.py found for app '{app_name}'")

        spec = importlib.util.spec_from_file_location(f"core_os_apps.{app_name}.main", main_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        if not hasattr(module, "App"):
            raise AppLoadError(f"No 'App' class found in app '{app_name}'")

        app_instance = module.App(scoped_context)
        if not isinstance(app_instance, AppBase):
            raise AppLoadError(f"App '{app_name}' does not inherit from AppBase")

        return AppHost(app_name, app_instance, manifest, scoped_context)
