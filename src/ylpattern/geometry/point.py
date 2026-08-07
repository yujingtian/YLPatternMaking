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

    def rotate(self, angle_deg: float) -> "Vector":
        """逆时针旋转 angle_deg 度（标准旋转矩阵）。

        袋布贝塞尔边手柄方向（袋布绘制.md §三.2(3)）：û(α) = 弦向单位
        向量旋转 α。
        """
        rad = math.radians(angle_deg)
        c, s = math.cos(rad), math.sin(rad)
        return Vector(self.dx * c - self.dy * s,
                      self.dx * s + self.dy * c)


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

    def rotate_around(self, center: "Point", angle_deg: float) -> "Point":
        """绕 center 旋转 angle_deg 度（逆时针为正，标准旋转矩阵）。

        前腰省转移（前口袋绘制.md §三.1）：P′ = A + R(γ)·(P − A)。
        """
        rad = math.radians(angle_deg)
        c, s = math.cos(rad), math.sin(rad)
        v = self - center
        return Point(center.x + v.dx * c - v.dy * s,
                     center.y + v.dx * s + v.dy * c)
