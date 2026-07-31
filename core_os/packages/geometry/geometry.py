"""Point/Vector2D/Rect/LineSegment — plain data classes with no gfx
dependency, mirroring Playdate's playdate.geometry module. Deliberately NOT
a replacement for ui/layout.py's Box (a bare x/y/width/height struct baked
into the LayoutNode contract every widget implements) -- these are for
general app logic (collision, motion, sprites) where vector math and
intersection tests actually matter, not layout positioning."""

from __future__ import annotations

import math
from typing import Optional


class Point:
    __slots__ = ("x", "y")

    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        self.x = x
        self.y = y

    def __repr__(self) -> str:
        return f"Point({self.x!r}, {self.y!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Point) and self.x == other.x and self.y == other.y

    def __add__(self, vector: "Vector2D") -> "Point":
        return Point(self.x + vector.dx, self.y + vector.dy)

    def __sub__(self, other):
        if isinstance(other, Point):
            return Vector2D(self.x - other.x, self.y - other.y)
        return Point(self.x - other.dx, self.y - other.dy)

    def distance_to(self, other: "Point") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def as_tuple(self):
        return (self.x, self.y)


class Vector2D:
    __slots__ = ("dx", "dy")

    def __init__(self, dx: float = 0.0, dy: float = 0.0) -> None:
        self.dx = dx
        self.dy = dy

    def __repr__(self) -> str:
        return f"Vector2D({self.dx!r}, {self.dy!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Vector2D) and self.dx == other.dx and self.dy == other.dy

    def __add__(self, other: "Vector2D") -> "Vector2D":
        return Vector2D(self.dx + other.dx, self.dy + other.dy)

    def __sub__(self, other: "Vector2D") -> "Vector2D":
        return Vector2D(self.dx - other.dx, self.dy - other.dy)

    def __mul__(self, scalar: float) -> "Vector2D":
        return Vector2D(self.dx * scalar, self.dy * scalar)

    __rmul__ = __mul__

    def length(self) -> float:
        return math.hypot(self.dx, self.dy)

    def normalized(self) -> "Vector2D":
        length = self.length()
        if length == 0.0:
            return Vector2D(0.0, 0.0)
        return Vector2D(self.dx / length, self.dy / length)

    def dot(self, other: "Vector2D") -> float:
        return self.dx * other.dx + self.dy * other.dy

    def as_tuple(self):
        return (self.dx, self.dy)


class Rect:
    __slots__ = ("x", "y", "width", "height")

    def __init__(self, x: float = 0.0, y: float = 0.0, width: float = 0.0, height: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def __repr__(self) -> str:
        return f"Rect({self.x!r}, {self.y!r}, {self.width!r}, {self.height!r})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Rect)
            and self.x == other.x and self.y == other.y
            and self.width == other.width and self.height == other.height
        )

    @property
    def left(self) -> float:
        return self.x

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def contains_point(self, point: Point) -> bool:
        return self.left <= point.x < self.right and self.top <= point.y < self.bottom

    def intersects(self, other: "Rect") -> bool:
        return (
            self.left < other.right and self.right > other.left
            and self.top < other.bottom and self.bottom > other.top
        )

    def intersection(self, other: "Rect") -> Optional["Rect"]:
        if not self.intersects(other):
            return None
        x = max(self.left, other.left)
        y = max(self.top, other.top)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)
        return Rect(x, y, right - x, bottom - y)

    def union(self, other: "Rect") -> "Rect":
        x = min(self.left, other.left)
        y = min(self.top, other.top)
        right = max(self.right, other.right)
        bottom = max(self.bottom, other.bottom)
        return Rect(x, y, right - x, bottom - y)

    def as_tuple(self):
        return (self.x, self.y, self.width, self.height)


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    return min(a.x, b.x) <= p.x <= max(a.x, b.x) and min(a.y, b.y) <= p.y <= max(a.y, b.y)


class LineSegment:
    __slots__ = ("p1", "p2")

    def __init__(self, p1: Point, p2: Point) -> None:
        self.p1 = p1
        self.p2 = p2

    def __repr__(self) -> str:
        return f"LineSegment({self.p1!r}, {self.p2!r})"

    def intersects(self, other: "LineSegment") -> bool:
        """Standard orientation-based segment intersection test (handles the
        general case + collinear/touching-endpoint edge cases); doesn't
        distinguish "overlapping collinear segments" as a special case
        beyond reporting True, which is enough for the sprite/collision use
        this exists for."""
        o1 = _orientation(self.p1, self.p2, other.p1)
        o2 = _orientation(self.p1, self.p2, other.p2)
        o3 = _orientation(other.p1, other.p2, self.p1)
        o4 = _orientation(other.p1, other.p2, self.p2)

        if o1 != o2 and o3 != o4 and (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
            return True

        if o1 == 0 and _on_segment(self.p1, self.p2, other.p1):
            return True
        if o2 == 0 and _on_segment(self.p1, self.p2, other.p2):
            return True
        if o3 == 0 and _on_segment(other.p1, other.p2, self.p1):
            return True
        if o4 == 0 and _on_segment(other.p1, other.p2, self.p2):
            return True
        return False

    def intersection_point(self, other: "LineSegment") -> Optional[Point]:
        """Only resolves the general (non-parallel, non-collinear) case --
        returns None for parallel or collinear segments even if they
        overlap, since a single point can't represent that anyway and
        intersects() already answers the yes/no question for those cases."""
        x1, y1, x2, y2 = self.p1.x, self.p1.y, self.p2.x, self.p2.y
        x3, y3, x4, y4 = other.p1.x, other.p1.y, other.p2.x, other.p2.y
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if denom == 0:
            return None
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / denom
        if not (0.0 <= t <= 1.0 and 0.0 <= u <= 1.0):
            return None
        return Point(x1 + t * (x2 - x1), y1 + t * (y2 - y1))


class AffineTransform:
    """2D affine transform (translate/scale/rotate/compose), mirroring
    Playdate's playdate.geometry.affineTransform. Represented as Playdate's
    own 6-value [a, b, c, d, tx, ty] form:

        | a  b  0 |
        | c  d  0 |
        | tx ty 1 |

    applied to a row vector: x' = a*x + c*y + tx, y' = b*x + d*y + ty.
    Immutable -- every operation returns a NEW AffineTransform rather than
    mutating in place, so a transform already handed to a sprite/shape
    can't change out from under it."""

    __slots__ = ("a", "b", "c", "d", "tx", "ty")

    def __init__(self, a: float = 1.0, b: float = 0.0, c: float = 0.0, d: float = 1.0, tx: float = 0.0, ty: float = 0.0) -> None:
        self.a, self.b, self.c, self.d, self.tx, self.ty = a, b, c, d, tx, ty

    def __repr__(self) -> str:
        return f"AffineTransform({self.a!r}, {self.b!r}, {self.c!r}, {self.d!r}, {self.tx!r}, {self.ty!r})"

    @classmethod
    def identity(cls) -> "AffineTransform":
        return cls()

    @classmethod
    def translation(cls, dx: float, dy: float) -> "AffineTransform":
        return cls(1.0, 0.0, 0.0, 1.0, dx, dy)

    @classmethod
    def scaling(cls, sx: float, sy: Optional[float] = None) -> "AffineTransform":
        return cls(sx, 0.0, 0.0, sy if sy is not None else sx, 0.0, 0.0)

    @classmethod
    def rotation(cls, degrees: float) -> "AffineTransform":
        theta = math.radians(degrees)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        return cls(cos_t, sin_t, -sin_t, cos_t, 0.0, 0.0)

    def concat(self, other: "AffineTransform") -> "AffineTransform":
        """self THEN other -- i.e. `t1.concat(t2)` applied to a point gives
        the same result as `t2.apply_to_point(t1.apply_to_point(p))`.
        Verified by hand: for row-vector convention (p' = p * M), applying
        M1 then M2 composes as the matrix product M1 * M2, in that left-
        to-right order."""
        return AffineTransform(
            self.a * other.a + self.b * other.c,
            self.a * other.b + self.b * other.d,
            self.c * other.a + self.d * other.c,
            self.c * other.b + self.d * other.d,
            self.tx * other.a + self.ty * other.c + other.tx,
            self.tx * other.b + self.ty * other.d + other.ty,
        )

    def apply_to_point(self, point: Point) -> Point:
        return Point(
            self.a * point.x + self.c * point.y + self.tx,
            self.b * point.x + self.d * point.y + self.ty,
        )

    def apply_to_vector(self, vector: Vector2D) -> Vector2D:
        """Vectors ignore translation -- a direction/magnitude has no
        position to translate."""
        return Vector2D(
            self.a * vector.dx + self.c * vector.dy,
            self.b * vector.dx + self.d * vector.dy,
        )
