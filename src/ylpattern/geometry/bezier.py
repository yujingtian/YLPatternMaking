"""三次贝塞尔曲线：打版弧线（裆弯、腰口弧等）的统一表示。"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .point import Point, Vector


def p1_influence(t: float) -> float:
    """三次贝塞尔控制点 P1 的基函数值 3(1−t)²t。

    曲线对控制点坐标是线性的：P1.x 平移 Δ 时，参数 t 处的曲线点
    x 平移恰为 p1_influence(t)·Δ（y 不受影响，t_at_y 不变），
    用于"让曲线在指定高度精确过某 x"的单步精确解（毗围闭环修正）。
    """
    return 3 * (1 - t) ** 2 * t


@dataclass(frozen=True)
class CubicBezier:
    p0: Point   # 起点
    p1: Point   # 控制点 1
    p2: Point   # 控制点 2
    p3: Point   # 终点

    def point_at(self, t: float) -> Point:
        mt = 1 - t
        return Point(
            mt**3 * self.p0.x + 3 * mt**2 * t * self.p1.x
            + 3 * mt * t**2 * self.p2.x + t**3 * self.p3.x,
            mt**3 * self.p0.y + 3 * mt**2 * t * self.p1.y
            + 3 * mt * t**2 * self.p2.y + t**3 * self.p3.y,
        )

    def tangent_at(self, t: float) -> Vector:
        """t 处的切线方向（未归一化）。用于裆弯拼接顺滑校验。"""
        mt = 1 - t
        return Vector(
            3 * mt**2 * (self.p1.x - self.p0.x)
            + 6 * mt * t * (self.p2.x - self.p1.x)
            + 3 * t**2 * (self.p3.x - self.p2.x),
            3 * mt**2 * (self.p1.y - self.p0.y)
            + 6 * mt * t * (self.p2.y - self.p1.y)
            + 3 * t**2 * (self.p3.y - self.p2.y),
        )

    def sample(self, n: int = 32) -> list[Point]:
        """按参数 t 均匀采样 n+1 个点（含首尾）。"""
        return [self.point_at(i / n) for i in range(n + 1)]

    def length(self, n: int = 64) -> float:
        """折线近似弧长。"""
        pts = self.sample(n)
        return sum(pts[i].distance_to(pts[i + 1]) for i in range(n))

    def angle_with(self, other: "CubicBezier", at_join: bool = True) -> float:
        """与另一条曲线在拼接点处的切线夹角（度）。

        约定 self 的终点与 other 的起点拼接：比较 self.tangent_at(1)
        与 other.tangent_at(0)。180° 为完全顺滑。
        """
        v1 = self.tangent_at(1.0 if at_join else 0.0)
        v2 = other.tangent_at(0.0 if at_join else 1.0)
        dot = v1.dx * v2.dx + v1.dy * v2.dy
        cos = max(-1.0, min(1.0, dot / (v1.length * v2.length)))
        return math.degrees(math.acos(cos))

    def t_at_y(self, y: float, *, tol: float = 1e-9) -> float:
        """求曲线与水平线 y 的交点参数 t（采样定位 + 二分）。

        要求曲线在交点附近 y 随 t 单调（打版大腿段/裆弯弧均满足）。
        无交点时抛 ValueError。
        """
        n = 64
        pts = self.sample(n)
        bracket: tuple[float, float] | None = None
        for i in range(n + 1):
            if abs(pts[i].y - y) <= tol:
                return i / n
            if i < n and (pts[i].y - y) * (pts[i + 1].y - y) < 0:
                bracket = (i / n, (i + 1) / n)
                break
        if bracket is None:
            raise ValueError(
                f"曲线 y 区间 [{pts[0].y:.2f}, {pts[-1].y:.2f}] 内"
                f"不存在水平线 y={y:.2f} 的交点")
        lo, hi = bracket
        for _ in range(60):
            mid = (lo + hi) / 2
            if abs(self.point_at(mid).y - y) <= tol:
                return mid
            if (self.point_at(lo).y - y) * (self.point_at(mid).y - y) < 0:
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2

    def point_at_y(self, y: float) -> Point:
        """曲线与水平线 y 的交点（要求交点附近 y 单调）。"""
        return self.point_at(self.t_at_y(y))
