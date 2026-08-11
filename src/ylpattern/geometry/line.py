"""直线段。打版中的参考线用足够长的线段表示（上版时由 sheet 统一裁剪）。"""

from __future__ import annotations

from dataclasses import dataclass

from .point import Point, Vector

# 参考线默认长度（cm），覆盖任何合理裤片宽度
REFLINE_LENGTH = 200.0


@dataclass(frozen=True)
class LineSegment:
    a: Point
    b: Point

    @property
    def length(self) -> float:
        """线段长（属性，非方法；CubicBezier.length() 是方法，须加括号）。"""
        return self.a.distance_to(self.b)

    @property
    def direction(self) -> Vector:
        return (self.b - self.a).normalized()

    @classmethod
    def horizontal(cls, y: float, x0: float = 0.0,
                   length: float = REFLINE_LENGTH) -> "LineSegment":
        """水平参考线（如脚口线、臀围线）。"""
        return cls(Point(x0, y), Point(x0 + length, y))

    @classmethod
    def vertical(cls, x: float, y0: float = 0.0,
                 length: float = REFLINE_LENGTH) -> "LineSegment":
        """垂直参考线（如外侧缝、内侧缝参考线）。"""
        return cls(Point(x, y0), Point(x, y0 + length))

    def point_at(self, t: float) -> Point:
        return self.a.lerp(self.b, t)

    def offset(self, distance: float) -> "LineSegment":
        """沿左手法向平移 distance（正值向行进方向左侧）。"""
        n = self.direction.perpendicular().scale(distance)
        return LineSegment(self.a + n, self.b + n)
