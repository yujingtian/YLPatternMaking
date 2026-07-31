"""闭合多边形：裁片轮廓。曲线段需先采样为折线再加入。"""

from __future__ import annotations

from dataclasses import dataclass

from .point import Point


@dataclass(frozen=True)
class Polygon:
    """闭合轮廓。points 不含重复的首尾点，闭合性由构造保证。"""

    points: tuple[Point, ...]

    def __post_init__(self) -> None:
        if len(self.points) < 3:
            raise ValueError("多边形至少需要 3 个点")

    @property
    def is_closed(self) -> bool:
        return True  # 语义上恒闭合

    def perimeter(self) -> float:
        n = len(self.points)
        return sum(self.points[i].distance_to(self.points[(i + 1) % n])
                   for i in range(n))

    def area(self) -> float:
        """鞋带公式，逆时针为正。"""
        n = len(self.points)
        s = 0.0
        for i in range(n):
            p, q = self.points[i], self.points[(i + 1) % n]
            s += p.x * q.y - q.x * p.y
        return s / 2

    def translate(self, dx: float, dy: float) -> "Polygon":
        return Polygon(tuple(Point(p.x + dx, p.y + dy) for p in self.points))

    def bounds(self) -> tuple[float, float, float, float]:
        xs = [p.x for p in self.points]
        ys = [p.y for p in self.points]
        return min(xs), min(ys), max(xs), max(ys)
