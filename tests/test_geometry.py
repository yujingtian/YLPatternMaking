"""几何层性质测试。"""

import math

import pytest

from ylpattern.geometry import Point, LineSegment, CubicBezier, Polygon
from ylpattern.draft import curves


def test_point_basics():
    a, b = Point(0, 0), Point(3, 4)
    assert a.distance_to(b) == 5.0
    assert a.midpoint(b) == Point(1.5, 2.0)


def test_line_constructors():
    h = LineSegment.horizontal(y=10)
    assert h.a.y == h.b.y == 10
    v = LineSegment.vertical(x=5)
    assert v.a.x == v.b.x == 5


def test_bezier_endpoints_and_length():
    bz = CubicBezier(Point(0, 0), Point(1, 2), Point(3, 2), Point(4, 0))
    assert bz.point_at(0) == Point(0, 0)
    assert bz.point_at(1) == Point(4, 0)
    assert bz.length() > 4.0  # 弧长必大于弦长


def test_arc_through_bulge_direction():
    arc = curves.arc_through(Point(0, 0), Point(10, 0), bulge=2.0)
    apex = arc.point_at(0.5)
    # 弦沿 +X 方向，左手法向为 +Y：弧顶应在 y > 0
    assert apex.y > 1.0
    assert abs(apex.x - 5.0) < 0.5


def test_polygon_area_perimeter():
    sq = Polygon((Point(0, 0), Point(4, 0), Point(4, 3), Point(0, 3)))
    assert sq.area() == 12.0
    assert sq.perimeter() == 14.0


def test_rotate_around():
    # (1,0) 绕原点逆时针 90° → (0,1)
    p = Point(1, 0).rotate_around(Point(0, 0), 90)
    assert p.x == pytest.approx(0.0, abs=1e-12)
    assert p.y == pytest.approx(1.0)
    # 0° 恒等
    assert Point(2, 3).rotate_around(Point(1, 1), 0) == Point(2, 3)
    # 任意中心：(2,3) 绕 (2,1) 顺时针 90° → (4,1)
    q = Point(2, 3).rotate_around(Point(2, 1), -90)
    assert q.x == pytest.approx(4.0)
    assert q.y == pytest.approx(1.0)
    # 旋转半径不变
    a, c = Point(5, 7), Point(1, 2)
    assert c.distance_to(a.rotate_around(c, 37)) == pytest.approx(c.distance_to(a))


def test_bezier_t_at_length():
    # 直线贝塞尔：控制点共线，弧长 = 4
    bz = CubicBezier(Point(0, 0), Point(1, 0), Point(3, 0), Point(4, 0))
    assert bz.length() == pytest.approx(4.0)
    assert bz.t_at_length(0.0) == 0.0
    assert bz.t_at_length(4.0) == 1.0
    assert bz.t_at_length(2.0) == pytest.approx(0.5, abs=1e-6)
    assert bz.point_at_length(2.0).x == pytest.approx(2.0, abs=1e-6)
    # 曲线上：弧长尽头即终点
    arc = CubicBezier(Point(0, 0), Point(1, 2), Point(3, 2), Point(4, 0))
    assert arc.point_at_length(arc.length()) == arc.p3
    # 越界抛错
    with pytest.raises(ValueError, match="超出曲线总长"):
        bz.t_at_length(5.0)
    with pytest.raises(ValueError, match="超出曲线总长"):
        bz.t_at_length(-1.0)


def test_bezier_split():
    bz = CubicBezier(Point(0, 0), Point(1, 2), Point(3, 2), Point(4, 0))
    first, second = bz.split(0.5)
    assert first.p0 == bz.p0
    assert second.p3 == bz.p3
    # 两段在 point_at(t) 相接（de Casteljau 与 Bernstein 求值浮点路径不同，用 approx）
    assert first.p3 == second.p0
    assert first.p3.x == pytest.approx(bz.point_at(0.5).x, abs=1e-12)
    assert first.p3.y == pytest.approx(bz.point_at(0.5).y, abs=1e-12)
    # 细分保形：子段中点 = 原曲线对应参数点；两段弧长和 ≈ 总长
    assert first.point_at(0.5).x == pytest.approx(bz.point_at(0.25).x, abs=1e-9)
    assert first.point_at(0.5).y == pytest.approx(bz.point_at(0.25).y, abs=1e-9)
    # 两段弧长和 ≈ 总长（折线近似在子段上的误差与母段不同，容差放宽）
    assert first.length() + second.length() == pytest.approx(bz.length(), abs=1e-3)
