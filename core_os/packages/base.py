"""Package base — generalizes tts_engines/base.py's proven shape (a resources
DI object + subclass discovery + capability tags + narrow public API) to
every ProxiTalk subsystem, not just TTS.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from core_os.core.registry import CoreRegistry


@dataclass(frozen=True)
class PackageResources:
    """Shared configuration/state provided to every Package. Generalizes
    tts_engines.base.EngineResources."""

    is_windows: bool
    core: CoreRegistry
    config_dir: str
    files_dir: str
    cache_dir: str
    shared_config: Any = None
    paths: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)


class Package(ABC):
    """Interface all Package implementations must follow."""

    package_id: str = "base"
    display_name: str = "Base"
    priority: int = 100  # smaller values initialize first when order is otherwise unconstrained
    capability_tags: Set[str] = set()
    core_requires: Set[str] = set()      # names of CoreRegistry driver attrs this package needs
    package_requires: Set[str] = set()   # package_ids of OTHER packages this package depends on

    def __init__(self, resources: PackageResources) -> None:
        self.resources = resources
        self._registry: Optional["object"] = None  # bound by PackageRegistry before initialize()

    @classmethod
    def is_available(cls, resources: PackageResources) -> bool:
        return True

    def _bind_registry(self, registry: "object") -> None:
        self._registry = registry

    def require(self, package_id: str) -> "Package":
        """Look up an already-initialized dependency. `package_id` MUST also
        be listed in this class's `package_requires` — that's what
        PackageRegistry topologically sorts on to guarantee the dependency
        is already initialize()'d by the time this runs. Calling require()
        for an id missing from package_requires is a bug in the package
        itself (initialization order isn't guaranteed for it) and raises
        immediately rather than only failing if that other package happens
        not to exist."""
        if self._registry is None:
            raise RuntimeError(f"Package '{self.package_id}' is not bound to a registry yet")
        if package_id not in self.package_requires:
            raise RuntimeError(
                f"Package '{self.package_id}' called require('{package_id}') without declaring it in "
                f"package_requires — add '{package_id}' to {self.__class__.__name__}.package_requires"
            )
        pkg = self._registry.get_package(package_id)  # type: ignore[attr-defined]
        if pkg is None:
            raise RuntimeError(f"Package '{self.package_id}' requires undeclared package '{package_id}'")
        return pkg

    @abstractmethod
    def initialize(self) -> None:
        """Perform any expensive start-up work."""

    def shutdown(self) -> None:
        """Release resources or terminate background threads/processes."""

    def capabilities(self) -> Set[str]:
        return set(self.capability_tags)

    @abstractmethod
    def get_public_api(self) -> Dict[str, Any]:
        """Return the flat dict of callables/values exposed to apps that
        declare this package_id in their manifest — this dict becomes
        context[package_id]."""
