"""几何层性质测试。"""

import math

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
