"""公共弧线库单测：uniform_arc_cubic（整根均匀圆弧）/ line_bezier_intersect / t_of_point。

金标（R=20 圆弧 60° 段，手算）：
  起点 P=(0,0)、切向 (1,0)；终点 E=(20·sin60°, 20·(1−cos60°))=(17.3205, 10)、
  末切向 (cos60°, sin60°)=(0.5, 0.8660)；弧长 = 20·π/3 ≈ 20.944；
  曲率恒 = 1/20 = 0.05。
"""

import math

import pytest

from ylpattern.draft import curves
from ylpattern.draft.curves import line_bezier_intersect, t_of_point, uniform_arc_cubic
from ylpattern.geometry import CubicBezier, LineSegment, Point, Vector


# ---------- uniform_arc_cubic ----------

def test_uniform_arc_cubic_golden():
    """R=20、60° 上弯：端点/端切向/弧长/均匀曲率四锁全对（封闭解构造）。"""
    R = 20.0
    b = uniform_arc_cubic(R * math.pi / 3, 60.0)
    # 端点（派生量金标）
    assert b.p0.distance_to(Point(0, 0)) < 1e-12
    assert b.p3.distance_to(Point(20 * math.sin(math.radians(60)),
                                  20 * (1 - math.cos(math.radians(60))))) < 1e-9
    # 起切向水平（后中镜像 C2 构造保证）
    assert b.p1.y == pytest.approx(0.0, abs=1e-12)
    # 末切向 = (cos60°, sin60°)
    te = b.tangent_at(1.0).normalized()
    assert te.dx == pytest.approx(0.5, abs=1e-9)
    assert te.dy == pytest.approx(math.sqrt(3) / 2, abs=1e-9)
    # 弧长精确（圆弧三次近似的经典误差，60° 段 < 0.01%）
    assert b.length() == pytest.approx(R * math.pi / 3, abs=0.005)
    # 全段贴圆弧：径向偏差 ≤ 0.01%·R
    worst = max(abs(math.hypot(b.point_at(i / 32).x,
                               b.point_at(i / 32).y - R) - R)
                for i in range(33))
    assert worst < 0.0001 * R
    # 曲率恒 = 1/R（均匀性——v0.9 口径核心）
    for i in range(9):
        assert b.curvature_at(i / 8) == pytest.approx(1 / R, rel=0.01)


def test_uniform_arc_cubic_downward_mirror():
    """负转角（向下弯）：与同幅上弯逐点 x 等距、y 反号；κ 反号。"""
    up = uniform_arc_cubic(35.07, 43.8)
    dn = uniform_arc_cubic(35.07, -43.8)
    for i in range(33):
        pu, pd = up.point_at(i / 32), dn.point_at(i / 32)
        assert abs(pu.x - pd.x) < 1e-9
        assert abs(pu.y + pd.y) < 1e-9
    assert dn.curvature_at(0.5) == pytest.approx(-up.curvature_at(0.5), abs=1e-12)
    # 腰头量级弧长精确（zhitong 实测金标：L=35.07, θ=43.8° → 35.0699）
    assert dn.length() == pytest.approx(35.07, abs=0.005)


def test_uniform_arc_cubic_straight_degenerate():
    """|turn| ≤ 0.5° 退化为水平直线：长度精确、κ=0。"""
    b = uniform_arc_cubic(12.0, 0.2)
    assert b.length() == pytest.approx(12.0, abs=1e-9)
    assert b.curvature_at(0.5) == pytest.approx(0.0, abs=1e-12)
    assert b.p3.distance_to(Point(12.0, 0.0)) < 1e-12


def test_uniform_arc_cubic_nonpositive_length_raises():
    with pytest.raises(ValueError):
        uniform_arc_cubic(0.0, -43.8)


def test_curves_no_g2_blend_residue():
    """v0.8 清扫：g2_blend 已随局部圆顺窗方案移除；v0.9 清扫：fit_fair_cubic
    已随均匀圆弧口径移除（封闭解取代数值拟合）。"""
    assert not hasattr(curves, "g2_blend")
    assert not hasattr(curves, "fit_fair_cubic")


# ---------- line_bezier_intersect ----------

def test_line_bezier_intersect_golden():
    """y(t)=9t(1−t) 的凸弧 ∩ 水平线 y=0.5：t=(1±√(7/9))/2，首交 t≈0.0590。"""
    bez = CubicBezier(Point(0, 0), Point(1, 3), Point(3, 3), Point(4, 0))
    seg = LineSegment(Point(0, 0.5), Point(4, 0.5))
    res = line_bezier_intersect(seg, bez)
    assert res is not None
    pt, t = res
    t_exact = (1 - math.sqrt(7 / 9)) / 2
    assert t == pytest.approx(t_exact, abs=1e-4)
    assert pt.y == pytest.approx(0.5, abs=1e-9)


def test_line_bezier_intersect_out_of_segment_none():
    """交点在线段范围外（along∉[0,1]）：返回 None。"""
    bez = CubicBezier(Point(0, 0), Point(1, 3), Point(3, 3), Point(4, 0))
    seg = LineSegment(Point(10, 0.5), Point(11, 0.5))
    assert line_bezier_intersect(seg, bez) is None
    # 完全不相交
    assert line_bezier_intersect(
        LineSegment(Point(0, 5), Point(4, 5)), bez) is None


# ---------- t_of_point ----------

def test_t_of_point_recovers_param():
    """曲线上已知点反求参数：构造点 point_at(0.3) → t≈0.3。"""
    bez = CubicBezier(Point(0, 0), Point(1, 3), Point(3, 3), Point(4, 0))
    assert t_of_point(bez, bez.point_at(0.3)) == pytest.approx(0.3, abs=1e-5)
    assert t_of_point(bez, bez.point_at(0.0)) == pytest.approx(0.0, abs=1e-6)
    assert t_of_point(bez, bez.point_at(1.0)) == pytest.approx(1.0, abs=1e-6)


def test_curves_no_g2_blend_residue():
    """v0.8 清扫：g2_blend 已随局部圆顺窗方案移除（整根拟合取代）。"""
    assert not hasattr(curves, "g2_blend")
