"""sprite package — Sprite is exposed directly (plain data, no injection
needed, subclassable for custom update() behavior); SpriteList needs gfx
injected so it's exposed via a factory method instead, same pattern as
animation.package's make_doslide."""

from __future__ import annotations

from typing import Any, Dict

from core_os.packages.base import Package, PackageResources
from core_os.packages.sprite.sprite import Sprite, SpriteList


class SpritePackage(Package):
    package_id = "sprite"
    display_name = "Sprite"
    priority = 27
    capability_tags = {"sprite", "display-list"}
    package_requires = {"display_gfx"}

    def initialize(self) -> None:
        self._gfx = self.require("display_gfx")

    def make_sprite_list(self, layer: str = "base") -> SpriteList:
        return SpriteList(self._gfx, layer=layer)

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "sprite": Sprite,
            "sprite_list": self.make_sprite_list,
        }


AVAILABLE_PACKAGES = [SpritePackage]
