"""点与向量。单位 cm，不可变。"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Vector:
    dx: float
    dy: float

    @property
    def length(self) -> float:
        return math.hypot(self.dx, self.dy)

    def normalized(self) -> "Vector":
        if self.length == 0:
            raise ValueError("零向量无法归一化")
        return Vector(self.dx / self.length, self.dy / self.length)

    def perpendicular(self) -> "Vector":
        """逆时针旋转 90° 的单位法向量。"""
        return Vector(-self.dy, self.dx).normalized()

    def scale(self, k: float) -> "Vector":
        return Vector(self.dx * k, self.dy * k)


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def __add__(self, v: Vector) -> "Point":
        return Point(self.x + v.dx, self.y + v.dy)

    def __sub__(self, other: "Point") -> Vector:
        return Vector(self.x - other.x, self.y - other.y)

    def distance_to(self, other: "Point") -> float:
        return (self - other).length

    def midpoint(self, other: "Point") -> "Point":
        return Point((self.x + other.x) / 2, (self.y + other.y) / 2)

    def lerp(self, other: "Point", t: float) -> "Point":
        """线性插值，t=0 在 self，t=1 在 other。"""
        return Point(self.x + (other.x - self.x) * t,
                     self.y + (other.y - self.y) * t)
