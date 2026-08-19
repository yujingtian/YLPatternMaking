"""cutter 缝边/折边金标测试（腰头裁片.md §五；后贴袋裁片.md §2~§3 HemTreatment）。

手工演算（金标基准，无缩水，矩形净样 cm）：
    a=(0,0) b=(−14,0) c=(−14,16) d=(0,16)，边序 top a→b / side b→c /
    bottom c→d / side d→a（shoelace = −448 < 0，cutter 外法向外扩）。
    SA top=2.5 / side=bottom=1.0、撇势 taper=−0.15：
    t_h=(−1,0)、N=(0,−1)；锚点 P_notch = 袋口净线 y=0 ∩ 侧缝缝边线
    x=−15 / x=1 → P_a=(1,0)、P_b=(−15,0)（作毛样角点锚定折边起翻；
    亦为 flow 层顶部线延长刀口的落点，§4 刀口不在 cutter 层）；
    镜像方向 D=E−2(E·N)N（E=(0,1) 指向袋内）= (0,−1)，D·N=1 →
    M_a=P_a+D·2.5=(1,−2.5)、M_b=(−15,−2.5)；
    T1 = M_a+t_h·|taper| = (0.85,−2.5)、T2 = (−14.85,−2.5)
    （顶边长 15.7 = 毛样宽 − 2|taper|，倒梯形；翻盖底 = 毛样全宽 16，
    自 P_notch 起翻盖住侧缝折边区——自净角起算会窄 2×SA_side）；
    hem 只产折边几何（T 顶点 / P_notch 角点）、不发刀口：毛样刀口维持
    base（缩水/净样刀口），§4 袋口刀口由 flow 层生成
    （back_patch_flow._top_hem_notches，见 test_back_patch_piece）。
    毛样全序（含 miter/偏移共线冗余点，逐点手算）：
    (0.85,−2.5)→(−14.85,−2.5)→(−15,0)→(−15,16)→(−15,17)→(−14,17)
    →(0,17)→(1,17)→(1,16)→(1,0)，闭合回 T1（凸链无台阶）。

镜像对称金标（top 位于链尾、角点跨环回绕）：
    a=(0,0) d=(0,16) c=(14,16) b=(14,0)，边序 side a→d / bottom d→c /
    side c→b / top b→a（shoelace = −448 < 0）。结果为上者的 x 镜像：
    T=(14.85,−2.5)/(−0.85,−2.5)、P_notch=(15,0)/(−1,0)。
"""

from __future__ import annotations

import pytest

from ylpattern.cutter import HemTreatment, add_seam_allowance, apply_shrinkage
from ylpattern.geometry import CubicBezier, LineSegment, Point
from ylpattern.params import BackPatchSeamAllowances
from ylpattern.pieces import PatternPiece, PieceEdge

SA = BackPatchSeamAllowances          # top 2.5 / side 1.0 / bottom 1.0（§2 示例）


def _rect_piece() -> PatternPiece:
    """金标矩形：袋口宽 14、袋身高 16，cutter 序 shoelace<0。"""
    a, b = Point(0, 0), Point(-14, 0)
    c, d = Point(-14, 16), Point(0, 16)
    edges = (PieceEdge("top", LineSegment(a, b)),
             PieceEdge("side", LineSegment(b, c)),
             PieceEdge("bottom", LineSegment(c, d)),
             PieceEdge("side", LineSegment(d, a)))
    return PatternPiece("demo", "金标演示", edges, notches=(a, b, c, d))


def _assert_poly(poly, expected: list[tuple[float, float]]) -> None:
    assert len(poly) == len(expected)
    for p, (x, y) in zip(poly, expected):
        assert p.x == pytest.approx(x, abs=1e-9)
        assert p.y == pytest.approx(y, abs=1e-9)


def test_hem_rectangle_golden():
    """矩形折边金标：倒梯形（底=毛样全宽）；hem 不发刀口（§4 刀口在 flow 层）。"""
    out = add_seam_allowance(_rect_piece(), SA(), hem=HemTreatment("top", -0.15))
    _assert_poly(out.gross_polygon, [
        (0.85, -2.5), (-14.85, -2.5), (-15, 0), (-15, 16), (-15, 17),
        (-14, 17), (0, 17), (1, 17), (1, 16), (1, 0)])
    # 翻盖底 = 两 P_notch 间毛样全宽 16（自净角起算的旧构造窄 2×SA_side 盖不住）
    assert out.gross_polygon[2].distance_to(out.gross_polygon[-1]) \
        == pytest.approx(16.0)
    # hem 不发刀口（§4 袋口刀口由 flow 层 back_patch_flow._top_hem_notches
    # 生成）：毛样刀口维持 base，方向空 = 出口层自推
    assert out.gross_notches == _rect_piece().notches
    assert out.gross_notch_dirs == ()
    assert any("袋口折边" in n for n in out.notes)
    assert not any("刀口 ×" in n for n in out.notes)


def test_hem_taper_zero():
    """taper=0：T=M 顶边同宽（= 毛样宽 16）。"""
    out = add_seam_allowance(_rect_piece(), SA(), hem=HemTreatment("top", 0.0))
    assert out.gross_polygon[0] == pytest.approx(Point(1.0, -2.5))
    assert out.gross_polygon[1] == pytest.approx(Point(-15.0, -2.5))
    assert out.gross_polygon[0].distance_to(out.gross_polygon[1]) \
        == pytest.approx(16.0)
    assert out.gross_notches == _rect_piece().notches


def test_hem_curved_top_degrades():
    """弧袋口（custom）无直线镜像轴：整条降级常规法向放缝，无 P_notch。"""
    piece = _rect_piece()
    top = piece.net_edges[0].geom
    curve = CubicBezier(top.a, Point(-7, -1.0), Point(-7, 1.0), top.b)
    edges = (PieceEdge("top", curve),) + piece.net_edges[1:]
    curved = PatternPiece("demo", "弧袋口", edges, notches=piece.notches)
    out = add_seam_allowance(curved, SA(), hem=HemTreatment("top", -0.15))
    assert out.gross_notches == curved.notches          # 无 P_notch 新增
    assert not any("P_notch" in n for n in out.notes)   # 未走折边构造
    assert len(out.gross_polygon) > 4                   # 常规偏移多边形仍产出


def test_hem_near_parallel_side_degrades():
    """侧边与袋口近平行（|E·N|≤1e-6）：预扫描降级，多边形仍闭合外扩。"""
    a, b = Point(0, 0), Point(-14, 0)
    c, d = Point(-4, 1e-7), Point(0, 16)     # b→c 近水平（|E·N|≈1e-8 < 1e-6）
    edges = (PieceEdge("top", LineSegment(a, b)),
             PieceEdge("side", LineSegment(b, c)),
             PieceEdge("bottom", LineSegment(c, d)),
             PieceEdge("side", LineSegment(d, a)))
    piece = PatternPiece("demo", "近平行", edges, notches=(a, b, c, d))
    out = add_seam_allowance(piece, SA(), hem=HemTreatment("top", -0.15))
    assert out.gross_notches == piece.notches
    assert not any("P_notch" in n for n in out.notes)
    assert len(out.gross_polygon) > 4
    ys = [p.y for p in out.gross_polygon]
    assert max(ys) > 16                        # 外扩仍成立


def test_hem_none_unchanged():
    """hem=None：与不带 hem 参数完全一致（现有七类裁片零影响守卫）。"""
    piece = _rect_piece()
    plain = add_seam_allowance(piece, SA())
    same = add_seam_allowance(piece, SA(), hem=None)
    assert same.gross_polygon == plain.gross_polygon
    assert same.gross_notches == plain.gross_notches == piece.notches


def test_hem_after_shrinkage():
    """先缩水后折边：折边距缩水后袋口线 sa_top，撇势为绝对量不随缩水放大。"""
    piece = apply_shrinkage(_rect_piece(), 0.02, 0.03)   # x/(1-0.02) / y/(1-0.03)
    out = add_seam_allowance(piece, SA(), hem=HemTreatment("top", -0.15))
    t1, t2 = out.gross_polygon[0], out.gross_polygon[1]
    assert t1.y == pytest.approx(-2.5, abs=1e-9)          # 距缩水后袋口线 2.5
    assert t2.y == pytest.approx(-2.5, abs=1e-9)
    assert t1.x == pytest.approx(1.0 - 0.15, abs=1e-9)    # 锚点 P_notch x=1（缩水
    # 后侧缝缝边线偏移 1.0）+ 撇势绝对量内收
    assert t2.x == pytest.approx(-14 / 0.98 - 1.0 + 0.15, abs=1e-9)


def test_hem_side_sa_zero_no_step():
    """两侧缝份 0：锚点 P_notch 退化为净角 -> 链自然相接（无台阶）。"""
    sa = BackPatchSeamAllowances(top=2.5, side=0.0, bottom=1.0)
    out = add_seam_allowance(_rect_piece(), sa, hem=HemTreatment("top", -0.15))
    assert out.gross_notches == _rect_piece().notches     # 无 P_notch 新增
    assert out.gross_polygon[0] == pytest.approx(Point(-0.15, -2.5))
    assert out.gross_polygon[1] == pytest.approx(Point(-13.85, -2.5))
    assert out.gross_polygon[2] == pytest.approx(Point(-14, 0))


def test_hem_top_last_in_chain_mirror():
    """镜像矩形且 top 居链尾：角点跨环回绕，结果为金标的 x 镜像（对称性）。"""
    a, d0, c0, b = Point(0, 0), Point(0, 16), Point(14, 16), Point(14, 0)
    edges = (PieceEdge("side", LineSegment(a, d0)),
             PieceEdge("bottom", LineSegment(d0, c0)),
             PieceEdge("side", LineSegment(c0, b)),
             PieceEdge("top", LineSegment(b, a)))
    piece = PatternPiece("demo", "镜像金标", edges, notches=(a, d0, c0, b))
    out = add_seam_allowance(piece, SA(), hem=HemTreatment("top", -0.15))
    # 毛样从 base[0]（侧边）起量：与金标同一环序、起点旋至 (−1,0)，末点与
    # 首点重合已去重，闭合边 (−0.85,−2.5)->(−1,0) 即折边线（凸链无台阶）
    _assert_poly(out.gross_polygon, [
        (-1, 0), (-1, 16), (-1, 17), (0, 17),
        (14, 17), (15, 17), (15, 16), (15, 0),
        (14.85, -2.5), (-0.85, -2.5)])
    assert out.gross_notches == piece.notches


def test_miter_treatment_bypasses_limit():
    """corner_treatments "miter"（不限长尖角，前片裁片.md §2.2 裆尖尖角跟随净样）：
    尖角 C=(0,0)、转角 −105°（内角 75°）、缝宽 1——真 miter = (1.3032, 1.0)、
    距 C ≈1.643 > 1.5 限长：不声明处理时回退阶梯角（outer = C+n_a+n_b
    = (0.9659, 0.7412) 台阶点），声明后角点 = 真 miter（同式复算），
    键序对称（("rise","inseam") / ("inseam","rise") 同果）。"""
    from math import cos, sin, radians
    from ylpattern.cutter import _miter_point
    from ylpattern.geometry import Vector
    c = Point(0.0, 0.0)
    t_a = Vector(1.0, 0.0)                       # rise 进入角点方向
    th = radians(-105.0)
    t_b = Vector(cos(th), sin(th))               # inseam 离开角点方向（顺时针转 105°）
    p0 = c + t_a.scale(-20.0)
    p1 = c + t_b.scale(20.0)
    edges = (PieceEdge("rise", LineSegment(p0, c)),
             PieceEdge("inseam", LineSegment(c, p1)),
             PieceEdge("side", LineSegment(p1, p0)))   # shoelace < 0
    piece = PatternPiece("demo", "尖角", edges)
    sa = {"rise": 1.0, "inseam": 1.0, "side": 1.0}
    exp = _miter_point(c, t_a, t_b, 1.0, 1.0, float("inf"))
    assert exp is not None and exp.distance_to(c) > 1.5   # 超默认限长
    # 未声明：miter 限长回退阶梯角，毛样无真 miter 顶点、有台阶外点
    limited = add_seam_allowance(piece, sa)
    assert min(p.distance_to(exp) for p in limited.gross_polygon) > 0.1
    step = c + t_a.perpendicular().scale(1.0) + t_b.perpendicular().scale(1.0)
    assert min(p.distance_to(step) for p in limited.gross_polygon) < 1e-9
    # 声明 "miter"：角点 = 真 miter，无台阶点；键序对称
    for key in (("rise", "inseam"), ("inseam", "rise")):
        out = add_seam_allowance(piece, sa, corner_treatments={key: "miter"})
        assert min(p.distance_to(exp) for p in out.gross_polygon) < 1e-9
        assert min(p.distance_to(step) for p in out.gross_polygon) > 0.1
