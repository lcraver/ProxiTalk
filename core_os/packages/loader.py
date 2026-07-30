"""Discovers Package subclasses under core_os/packages/<name>/package.py,
generalizing tts_engines/loader.py's AVAILABLE_ENGINES convention to
AVAILABLE_PACKAGES."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Iterable, List, Type

from core_os.packages.base import Package, PackageResources


def discover_package_classes(resources: PackageResources) -> List[Type[Package]]:
    package = importlib.import_module(__name__.rsplit(".", 1)[0])  # core_os.packages
    package_path = Path(package.__file__).parent
    package_classes: List[Type[Package]] = []

    for module_info in pkgutil.iter_modules([str(package_path)]):
        name = module_info.name
        if name.startswith("_") or name in {"base", "loader", "registry"}:
            continue
        sub_module_name = f"{package.__name__}.{name}.package"
        try:
            module = importlib.import_module(sub_module_name)
        except ModuleNotFoundError:
            continue
        if not hasattr(module, "AVAILABLE_PACKAGES"):
            print(
                f"[packages.loader] '{sub_module_name}' has no AVAILABLE_PACKAGES list — "
                f"it won't be registered. Add e.g. AVAILABLE_PACKAGES = [MyPackage] to that file."
            )
            continue
        candidates: Iterable[Type[Package]] = getattr(module, "AVAILABLE_PACKAGES", [])
        for cls in candidates:
            if not issubclass(cls, Package):
                continue
            if not cls.is_available(resources):
                continue
            package_classes.append(cls)

    package_classes.sort(key=lambda cls: (getattr(cls, "priority", 100), cls.package_id))
    return package_classes
