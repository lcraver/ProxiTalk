"""geometry package — Point/Vector2D/Rect/LineSegment/AffineTransform,
exposed directly (no factory methods) since none of them need gfx or any
other package injected. Mirrors the ui package's menu_item precedent
(STYLE_GUIDE.md): a plain data class with no injection need is exposed as
the class itself, not wrapped in a make_<name> method."""

from __future__ import annotations

from typing import Any, Dict

from core_os.packages.base import Package, PackageResources
from core_os.packages.geometry.geometry import (
    AffineTransform,
    LineSegment,
    Point,
    Rect,
    Vector2D,
)


class GeometryPackage(Package):
    package_id = "geometry"
    display_name = "Geometry"
    priority = 10
    capability_tags = {"math"}

    def initialize(self) -> None:
        pass

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "point": Point,
            "vector2d": Vector2D,
            "rect": Rect,
            "line_segment": LineSegment,
            "affine_transform": AffineTransform,
        }


AVAILABLE_PACKAGES = [GeometryPackage]
