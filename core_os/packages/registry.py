"""PackageRegistry — instantiates one of each discovered Package eagerly (not
lazily like TTS engines, since e.g. display_gfx must be ready before any app
loads), validates core_requires/package_requires, and initializes packages in
dependency order."""

from __future__ import annotations

from typing import Dict, List, Optional, Type

from core_os.packages.base import Package, PackageResources
from core_os.packages.loader import discover_package_classes

_CORE_DRIVER_ATTRS = {"display", "input", "audio_output", "leds", "gpio"}


class PackageDependencyError(RuntimeError):
    pass


class PackageRegistry:
    def __init__(self, resources: PackageResources) -> None:
        self.resources = resources
        self._classes: Dict[str, Type[Package]] = {}
        self._packages: Dict[str, Package] = {}

        for cls in discover_package_classes(resources):
            self._classes[cls.package_id] = cls

        self._validate()
        order = self._topological_order()

        for package_id in order:
            instance = self._classes[package_id](resources)
            instance._bind_registry(self)
            self._packages[package_id] = instance

        for package_id in order:
            self._packages[package_id].initialize()

    def _validate(self) -> None:
        for cls in self._classes.values():
            missing_core = cls.core_requires - _CORE_DRIVER_ATTRS
            if missing_core:
                raise PackageDependencyError(
                    f"Package '{cls.package_id}' requires unknown core capabilities: {sorted(missing_core)}"
                )
            for dep_id in cls.package_requires:
                if dep_id not in self._classes:
                    raise PackageDependencyError(
                        f"Package '{cls.package_id}' requires unknown package '{dep_id}'"
                    )

    def _topological_order(self) -> List[str]:
        done: Dict[str, bool] = {}
        order: List[str] = []

        def visit(package_id: str, stack: tuple) -> None:
            if package_id in stack:
                chain = " -> ".join(stack + (package_id,))
                raise PackageDependencyError(f"Cyclic package dependency: {chain}")
            if done.get(package_id):
                return
            cls = self._classes[package_id]
            for dep_id in sorted(cls.package_requires):
                visit(dep_id, stack + (package_id,))
            done[package_id] = True
            order.append(package_id)

        for package_id in sorted(self._classes.keys()):
            visit(package_id, tuple())

        return order

    def get_package(self, package_id: str) -> Optional[Package]:
        return self._packages.get(package_id)

    def has_package(self, package_id: str) -> bool:
        return package_id in self._packages

    def get_public_api(self, package_id: str) -> Dict[str, object]:
        pkg = self.get_package(package_id)
        return pkg.get_public_api() if pkg is not None else {}

    def describe_packages(self) -> Dict[str, Dict[str, object]]:
        description: Dict[str, Dict[str, object]] = {}
        for package_id, pkg in self._packages.items():
            description[package_id] = {
                "package_id": package_id,
                "display_name": pkg.display_name,
                "priority": pkg.priority,
                "capabilities": sorted(pkg.capabilities()),
                "core_requires": sorted(pkg.core_requires),
                "package_requires": sorted(pkg.package_requires),
            }
        return description

    def shutdown_all(self) -> None:
        for package_id, pkg in self._packages.items():
            try:
                pkg.shutdown()
            except Exception as exc:
                print(f"[PackageRegistry] Error shutting down '{package_id}': {exc}")
