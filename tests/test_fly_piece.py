"""独立门襟裁片（单排 + 双排）测试（门襟裁片.md §1~§4）。

金标（H=96, Δ=1.0, front_rise=25，默认 fly_*，fly_separate=True，直腰头）：
  开深 L = 0.35×25 + 2.0 = 10.75；净宽 W = 3.8；R = W − 0.8 = 3.0；
  底部延展 fly_sep_extra = 2.0 -> 裁片高 h = L + 2.0 = 12.75。
  单排边长：top 腰头线子弧弧长 = W = 3.8；外缘直线 = h − R = 9.75；
  底角过渡弧无闭式金标（T 取在弧形腰头线上 -> 前浪与底边实际夹角 ≈82°，
  手柄常数按 90° 调定 -> 贝塞尔外凸，实测 ≈4.92；断言径向 = R + 弧长界于
  圆弧 R·θ 下界与控制多边形上界）；底边 = chord(T,O) − R（T 沿腰头线量取
  弧长 3.8，弦长实测 ≈3.80）；内边 = h = 12.75。
  刀口 = 内边上自 O 开深 10.75 处（拉链止口/前浪对位，§2 Step3）；毛样刀口沿
  内边外法向投影至缝边线（净位 + 1.0，打在缝边上）。
  双排（§4）：外缘重构直线 T->E（E = T + 前浪方向·h）与内边严格平行且绝对
  等长 12.75（O,T,E,S 平行四边形）；底端 E->S 直线 = chord(T,O)；半边沿对折轴
  O->S 镜像展开，镜像边加 _m 后缀**异名**（与基边同缝份值）：对折接缝 O/S 交
  cutter 正常 miter，O 为反射角（两腰弧谷底对接、切线突变）交点落在两边偏移
  链途中，越交点的采样尾/头部点被裁剪——同名跳过角点时两偏移链角部自交 =
  顶部缝边三线交错（2026-08 DXF 报障）；刀口 = 对折线两端 O/S（§4 Step4
  强制，**沿对折轴线向外投影**与中心对称线绝对共线——主边外法向带前浪斜度
  必然歪斜，车间须沿直线对折；无缩水时轴线恰过缝边顶点：上端反射角裁剪
  交点、下端凸角 miter 顶点，打口方向 gross_notch_dirs 沿轴显式给定）
  + 外缘开深 T+前浪方向·10.75（外法向 +1.0）。
  刀口落点口径（ET 顶点吸附）：刀口须落缝边线段中部或共线顶点——恰落
  miter/阶梯角顶点（两侧折线不共线）时 CAD 无法判定切线方向、渲染成十字
  孤立点；角点命中多条边时一律按斜率取 |dy| 最大主边外法向投影（不取法向
  均值角平分——凸角均值落 miter 顶点、反射角均值落裁剪交点，均为角顶点），
  如 fly_sep_extra=0 时单排 S 内边×底边、双排外缘 E 外缘×底边（⊥ 恰 1 缝份）。
  缩水轴向（§1）：丝缕竖直 = 经向 = 局部 Y -> X 吃纬 1/(1-weft)、Y 吃经 1/(1-warp)，
  刀口同步缩放、缝边在缩水之后（缝份不叠加缩水）。拐角 miter：T/S/E 内角约
  82°，miter 约 1.52×sa 恰超 cutter 默认限 1.5（曾回退阶梯角），flow 传
  miter_limit=2.0 正常 miter。
断言口径：独立复算几何量与闭环不变量，不硬编坐标（同 test_waistband_piece）。
"""

import math

import pytest

from ylpattern.exporters.piece_svg import render_piece_svg
from ylpattern.flows.back_flow import FULL_FLOW
from ylpattern.flows.front_fly_flow import build_front_fly
from ylpattern.flows.runner import FlowRunner
from ylpattern.geometry import CubicBezier, LineSegment, Point
from ylpattern.params import (Measurements, PatternOptions, WaistbandType,
                              FlySeamAllowances)

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
O = PatternOptions(delta=1.0, fly_separate=True)

# 金标常量（头部演算）
L, W, R, H = 10.75, 3.8, 3.0, 12.75


@pytest.fixture()
def built():
    ctx = FlowRunner(M, O).run(FULL_FLOW)
    single, double, local = build_front_fly(ctx)
    return ctx, single, double, local


# ---------- 测试辅助（同 test_fly_steps / test_yoke_piece 口径）----------

def _start(g):
    return g.a if isinstance(g, LineSegment) else g.p0


def _end(g):
    return g.b if isinstance(g, LineSegment) else g.p3


def _sample(g, n=32):
    return [g.a, g.b] if isinstance(g, LineSegment) else g.sample(n)


def _length(g):
    return g.length if isinstance(g, LineSegment) else g.length()


def _shoelace(piece):
    pts = [p for e in piece.net_edges for p in _sample(e.geom)]
    s = 0.0
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        s += a.x * b.y - b.x * a.y
    return s


def _assert_closed(piece):
    geoms = [e.geom for e in piece.net_edges]
    for i in range(len(geoms)):
        nxt = geoms[(i + 1) % len(geoms)]
        assert _end(geoms[i]).distance_to(_start(nxt)) < 1e-9, \
            f"{piece.name} 接缝 {i}->{(i + 1) % len(geoms)} 开口"


def _reflect(p, a, b):
    """点 p 关于直线 a->b 的镜像（同 flow._reflect_point 口径，独立复算）。"""
    d = b - a
    ap = p - a
    t = (ap.dx * d.dx + ap.dy * d.dy) / (d.dx * d.dx + d.dy * d.dy)
    proj = a + d.scale(t)
    return proj + (proj - p)


# ---------- 单排（单层，§2）----------

def test_single_edges_closure_orientation(built):
    _, single, _, _ = built
    names = tuple(e.name for e in single.net_edges)
    # 外缘直线 + 底角 J 弧 + 底边为精确 G1 链，必须同名 outer（cutter 异名平行
    # 切线回退阶梯角，缝边会在接缝处凸出尖刺）；局部 Y 反射后 shoelace < 0
    assert names == ("top", "outer", "outer", "outer", "inner")
    _assert_closed(single)
    assert _shoelace(single) < 0
    assert _start(single.net_edges[0].geom) == Point(0.0, 0.0)  # 首边起于局部原点


def test_single_edge_lengths(built):
    ctx, single, _, _ = built
    top, outer1, corner, bottom, inner = [e.geom for e in single.net_edges]
    assert _length(top) == pytest.approx(W, abs=1e-3)         # 腰头线子弧弧长 = W
    assert _length(outer1) == pytest.approx(H - R)            # 外缘直线 = h − R = 9.75
    # 底角过渡弧：构造不变量口径（角弧在局部系，全局向量经局部变换 X 不翻、
    # Y 翻）。T 取在弧形腰头线上 -> 底边与前浪实际夹角 ≈82°，而步骤层手柄常数
    # _QUARTER_K 按 90° 圆弧调定 -> 贝塞尔外凸，弧长无闭式金标（实测 4.916，
    # 介于圆弧 R·θ 下界与控制多边形上界之间）；径向定位与切向 G1 见下
    o_pt = ctx.point("front.fly_origin")
    t_top = ctx.point("front.fly_sep_top_outer")
    s_bot = ctx.point("front.fly_sep_bottom_inner")
    yd = ctx.line("front.rise_slant").direction
    e_bot = t_top + yd.scale(H)
    e_local = Point(e_bot.x - o_pt.x, o_pt.y - e_bot.y)
    s_local = Point(s_bot.x - o_pt.x, o_pt.y - s_bot.y)
    d_bot = (s_local - e_local).normalized()   # 局部系底边方向
    yd_local = (yd.dx, -yd.dy)                 # 局部系前浪方向（元组即可）
    assert corner.p0.distance_to(e_local) == pytest.approx(R)   # 圆角起 = e − y_dir·R
    assert corner.p3.distance_to(e_local) == pytest.approx(R)   # 圆角终 = e + d_bot·R
    cos_t = max(-1.0, min(1.0, yd_local[0] * d_bot.dx + yd_local[1] * d_bot.dy))
    polygon = (corner.p1.distance_to(corner.p0) + corner.p2.distance_to(corner.p1)
               + corner.p3.distance_to(corner.p2))
    assert R * math.acos(cos_t) < _length(corner) < polygon
    chord = t_top.distance_to(o_pt)
    assert _length(bottom) == pytest.approx(chord - R, abs=1e-3)
    assert _length(inner) == pytest.approx(H)                 # 内边 = h = 12.75


def test_single_outer_g1_chain(built):
    # G1 链接缝切向点积 == 1（外缘->角弧、角弧->底边），三段同名 outer 的依据
    _, single, _, _ = built
    _, outer1, corner, bottom, _ = [e.geom for e in single.net_edges]
    t_corner0 = corner.tangent_at(0).normalized()
    t_corner1 = corner.tangent_at(1).normalized()
    d_outer = (outer1.b - outer1.a).normalized()
    d_bottom = (bottom.b - bottom.a).normalized()
    assert t_corner0.dx * d_outer.dx + t_corner0.dy * d_outer.dy == pytest.approx(1.0)
    assert t_corner1.dx * d_bottom.dx + t_corner1.dy * d_bottom.dy == pytest.approx(1.0)


def test_single_notch_at_fly_depth(built):
    # 刀口 = 内边上自 O 开深 L = 10.75 处（拉链止口/前浪对位，§2 Step3）
    ctx, single, _, _ = built
    o_pt = ctx.point("front.fly_origin")
    yd = ctx.line("front.rise_slant").direction
    p = o_pt + yd.scale(L)
    assert len(single.notches) == 1
    assert single.notches[0].x == pytest.approx(p.x - o_pt.x)
    assert single.notches[0].y == pytest.approx(o_pt.y - p.y)


# ---------- 双排（对折，§4）----------

def test_double_edges_closure_orientation(built):
    _, _, double, _ = built
    names = tuple(e.name for e in double.net_edges)
    # 镜像边加 _m 后缀异名（与基边同缝份值）：对折接缝 O/S 交 cutter 正常
    # miter（O 反射角交点自动裁剪）——同名跳过角点时 O 两腰弧偏移链越过交点
    # 自交 = 顶部缝边三线交错（DXF 报障）；局部 Y 反射后 shoelace < 0
    assert names == ("top", "outer", "bottom", "bottom_m", "outer_m", "top_m")
    _assert_closed(double)
    assert _shoelace(double) < 0


def test_double_parallelogram(built):
    # 外缘重构直线：E = T + 前浪方向·h（重算链）；与内边严格平行且绝对等长；
    # 底端 E->S 直线 = chord(T,O)；镜像边等长
    ctx, _, double, _ = built
    o_pt = ctx.point("front.fly_origin")
    t_top = ctx.point("front.fly_sep_top_outer")
    s_bot = ctx.point("front.fly_sep_bottom_inner")
    yd = ctx.line("front.rise_slant").direction
    e_bot = t_top + yd.scale(H)
    top, outer, bottom, bottom_m, outer_m, top_m = [e.geom for e in double.net_edges]
    # 外缘 = 直线 T->E（局部坐标逐点对照主版换算）
    assert outer.a.x == pytest.approx(t_top.x - o_pt.x)
    assert outer.a.y == pytest.approx(o_pt.y - t_top.y)
    assert outer.b.x == pytest.approx(e_bot.x - o_pt.x)
    assert outer.b.y == pytest.approx(o_pt.y - e_bot.y)
    # 平行等长：outer / outer_m 均长 h 且 ∥ 前浪方向（局部系 X 不翻、Y 翻）
    d_local = (outer.b - outer.a).normalized()
    yd_local = (yd.dx, -yd.dy)
    assert d_local.dx * yd_local[0] + d_local.dy * yd_local[1] == pytest.approx(1.0)
    assert _length(outer) == pytest.approx(H)
    assert _length(outer_m) == pytest.approx(H)
    # 底端直线闭合 = chord(T,O)，两侧等长
    chord = t_top.distance_to(o_pt)
    assert _length(bottom) == pytest.approx(chord, abs=1e-3)
    assert _length(bottom_m) == pytest.approx(chord, abs=1e-3)
    # 底端两端点 = 局部 S（对折线下端点 = 第 2 刀口）
    assert _end(bottom).distance_to(
        Point(s_bot.x - o_pt.x, o_pt.y - s_bot.y)) < 1e-9


def test_double_mirror_symmetry(built):
    # 半边（top+outer+bottom）采样点关于对折轴 local(O)->local(S) 的镜像
    # 落在 _m 边采样点集上（点集互检，同袋布口径）
    _, _, double, _ = built
    axis_a = double.notches[0]      # local O = (0,0)
    axis_b = double.notches[1]      # local S
    half = [p for e in double.net_edges[:3] for p in _sample(e.geom)]
    mirror = [p for e in double.net_edges[3:] for p in _sample(e.geom)]
    for p in half:
        m = _reflect(p, axis_a, axis_b)
        assert min(m.distance_to(q) for q in mirror) < 1e-6


def test_double_notches_and_marks(built):
    # 刀口（§4 Step4）：对折线两端点 O/S 必含 + 外缘开深 L 对位点；
    # 标记 = 对折线 O->S 画稿折叠指示
    ctx, _, double, _ = built
    o_pt = ctx.point("front.fly_origin")
    t_top = ctx.point("front.fly_sep_top_outer")
    s_bot = ctx.point("front.fly_sep_bottom_inner")
    yd = ctx.line("front.rise_slant").direction
    assert double.notches[0] == Point(0.0, 0.0)              # local O 精确
    assert double.notches[1].x == pytest.approx(s_bot.x - o_pt.x)
    assert double.notches[1].y == pytest.approx(o_pt.y - s_bot.y)
    p = t_top + yd.scale(L)
    assert double.notches[2].x == pytest.approx(p.x - o_pt.x)
    assert double.notches[2].y == pytest.approx(o_pt.y - p.y)
    assert len(double.marks) == 1                             # 对折线画稿标记


# ---------- 缩水（§1：主面料，None=回退全局；先缩水后缝边）----------

def test_shrinkage_axes():
    # 经向 = 丝缕竖直 = 局部 Y：shrunk = net / (1-weft, 1-warp)，刀口同步
    o = PatternOptions(delta=1.0, fly_separate=True,
                       shrinkage_warp=0.03, shrinkage_weft=0.02)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    single, double, _ = build_front_fly(ctx)
    for piece in (single, double):
        for e_net, e_shrunk in zip(piece.net_edges, piece.shrunk_edges):
            for p_net, p_sh in zip(_sample(e_net.geom), _sample(e_shrunk.geom)):
                assert p_sh.x == pytest.approx(p_net.x / 0.98)   # X 吃纬
                assert p_sh.y == pytest.approx(p_net.y / 0.97)   # Y 吃经
        for p_net, p_sh in zip(piece.notches, piece.shrunk_notches):
            assert p_sh.x == pytest.approx(p_net.x / 0.98)
            assert p_sh.y == pytest.approx(p_net.y / 0.97)


def test_shrinkage_override_global():
    # fly_shrinkage_* 覆盖全局（0.05/0.04 胜 0.03/0.02）
    o = PatternOptions(delta=1.0, fly_separate=True,
                       shrinkage_warp=0.03, shrinkage_weft=0.02,
                       fly_shrinkage_warp=0.05, fly_shrinkage_weft=0.04)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    single, _, _ = build_front_fly(ctx)
    e_net = single.net_edges[0].geom
    e_shrunk = single.shrunk_edges[0].geom
    p_net, p_sh = _start(e_net), _start(e_shrunk)
    assert p_sh.x == pytest.approx(p_net.x / 0.96)
    assert p_sh.y == pytest.approx(p_net.y / 0.95)


# ---------- 丝缕线（§1：与前/后片经向一致 = 竖直）----------

def test_grain_vertical(built):
    _, single, double, _ = built
    for piece in (single, double):
        g = piece.grain
        assert g.a.x == pytest.approx(g.b.x)                   # 竖直
        ys = [p.y for e in piece.net_edges for p in _sample(e.geom)]
        assert (g.b.y - g.a.y) == pytest.approx(0.7 * (max(ys) - min(ys)))  # 15% 边距


# ---------- 缝边（§1：缩水后偏移，缝份不叠加缩水）----------

def test_seam_zero_gross_equals_net():
    # 缝份全 0：毛样折线 = 净样采样边界（无外扩）
    o = PatternOptions(delta=1.0, fly_separate=True,
                       fly_seam_allowances=FlySeamAllowances(0, 0, 0, 0))
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    single, double, _ = build_front_fly(ctx)
    for piece in (single, double):
        net_pts = [p for e in piece.net_edges for p in _sample(e.geom)]
        assert piece.gross_polygon
        for p in piece.gross_polygon:
            assert min(p.distance_to(q) for q in net_pts) < 1e-9


def test_gross_offsets_outward(built):
    # 默认缝份 1.0：毛样 bbox 各向超出净样 bbox（外法向外扩；默认缩水 0）
    _, single, double, _ = built
    for piece in (single, double):
        nxs = [p.x for e in piece.net_edges for p in _sample(e.geom)]
        nys = [p.y for e in piece.net_edges for p in _sample(e.geom)]
        gxs = [p.x for p in piece.gross_polygon]
        gys = [p.y for p in piece.gross_polygon]
        assert min(gxs) < min(nxs) - 0.9
        assert max(gxs) > max(nxs) + 0.9
        assert min(gys) < min(nys) - 0.9
        assert max(gys) > max(nys) + 0.9


# ---------- 刀口（§2 Step3 / §4 Step4：锚定净样位、打在缝边外沿）----------

def _dist_to_poly(p: Point, poly) -> float:
    """点 p 到闭合折线的最近距离（段上参数投影 clamp）。"""
    best = float("inf")
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        v = b - a
        L2 = v.dx * v.dx + v.dy * v.dy
        t = max(0.0, min(1.0, ((p.x - a.x) * v.dx + (p.y - a.y) * v.dy) / L2)) \
            if L2 > 0 else 0.0
        best = min(best, p.distance_to(a + v.scale(t)))
    return best


def test_notches_projected_to_gross(built):
    # 毛样刀口全部落在毛样折线上（打在缝边外沿=裁切线上；ET 按折线顶点吸附
    # 挂刀口符号，净样位刀口不显示）；净样位刀口（shrunk_notches）保留
    _, single, double, _ = built
    for piece in (single, double):
        for g in piece.gross_notches:
            assert _dist_to_poly(g, piece.gross_polygon) < 1e-9
        assert piece.shrunk_notches == piece.notches    # 缝合线位不丢


def test_single_notch_offset_along_inner_normal(built):
    # 单排唯一刀口（内边开深 L 前浪对位点）：毛样刀口 = 净刀口 + 内边外法向·
    # sa.inner——垂于内边、距离恰一个缝份、同沿线位置（平行偏移到缝边线）
    _, single, _, _ = built
    inner = [e for e in single.net_edges if e.name == "inner"][0].geom
    p = single.notches[0]
    g = single.gross_notches[0]
    d = g - p
    assert d.length == pytest.approx(1.0)               # sa.inner = 1.0
    t = (inner.b - inner.a).normalized()
    assert abs(d.dx * t.dx + d.dy * t.dy) < 1e-9        # ⊥ 内边（法向）


def test_double_notch_on_outer_offset(built):
    # 双排外缘开深 L 刀口：外缘（重构直线）外法向一个缝份；O/S 对折线端点
    # 刀口**沿对折轴线向外投影**（2026-08 口径：与中心对称线绝对共线供车间
    # 直线对折——主边外法向带前浪斜度必然歪斜）；打口方向 gross_notch_dirs
    # 同为轴向、指向对端（刀口切进方向沿轴）
    _, _, double, _ = built
    outer = [e for e in double.net_edges if e.name == "outer"][0].geom
    p = double.notches[2]
    g = double.gross_notches[2]
    d = g - p
    assert d.length == pytest.approx(1.0)
    t = (outer.b - outer.a).normalized()
    assert abs(d.dx * t.dx + d.dy * t.dy) < 1e-9
    axis = (double.notches[1] - double.notches[0]).normalized()
    for i in (0, 1):
        d = double.gross_notches[i] - double.notches[i]
        assert 1e-6 < d.length <= 2.0
        cross = abs(d.dx * axis.dy - d.dy * axis.dx) / d.length
        assert cross < 1e-9                     # 位移沿轴线（与中心线共线）
        nd = double.gross_notch_dirs[i]
        assert nd is not None
        assert abs(nd.dx * axis.dy - nd.dy * axis.dx) < 1e-9   # 打口方向沿轴
        sign = nd.dx * axis.dx + nd.dy * axis.dy
        assert (sign > 0) if i == 0 else (sign < 0)            # 指向对端


def _analytic_miter(p, t_a, t_b, sa_a, sa_b):
    """角点 p 处不限长 miter 解析交点（两偏移切线延伸求交，独立复算）。"""
    off_a = p + t_a.perpendicular().scale(sa_a)
    off_b = p + t_b.perpendicular().scale(sa_b)
    det = t_a.dx * t_b.dy - t_a.dy * t_b.dx
    d = off_b - off_a
    s = (d.dx * t_b.dy - d.dy * t_b.dx) / det
    return off_a + t_a.scale(s)


def test_corners_mitered_not_stair(built):
    # 拐角 miter（miter_limit=2.0）：腰口×外缘 T、底边×内边 S 内角约 82°，
    # miter 长约 1.52×sa 恰超 cutter 默认限 1.5 曾回退阶梯角（缝边拐角凸出
    # 一个缝份量台阶，DXF 目检"前浪线外侧缝边不直"）；现毛样顶点应含解析
    # miter 交点、不含阶梯外角点
    _, single, double, _ = built
    edges = single.net_edges           # [top, outer线, outer弧, outer线, inner]
    sa = 1.0
    # S 角：底边（outer[3]）× inner
    bottom, inner = edges[3].geom, edges[4].geom
    s_miter = _analytic_miter(bottom.b, (bottom.b - bottom.a).normalized(),
                              (inner.b - inner.a).normalized(), sa, sa)
    assert s_miter.distance_to(bottom.b) == pytest.approx(1.52, abs=0.01)
    assert any(v.distance_to(s_miter) < 1e-9 for v in single.gross_polygon)
    # T 角：top 腰口弧 × outer 直线
    top, outer = edges[0].geom, edges[1].geom
    t_miter = _analytic_miter(outer.a, top.tangent_at(1.0).normalized(),
                              (outer.b - outer.a).normalized(), sa, sa)
    assert any(v.distance_to(t_miter) < 1e-9 for v in single.gross_polygon)
    # 阶梯外角点（corner + n_a + n_b）不应在毛样折线上
    for corner, t_a, t_b in ((bottom.b, (bottom.b - bottom.a).normalized(),
                              (inner.b - inner.a).normalized()),
                             (outer.a, top.tangent_at(1.0).normalized(),
                              (outer.b - outer.a).normalized())):
        stair = corner + t_a.perpendicular() + t_b.perpendicular()
        assert all(v.distance_to(stair) > 1e-6 for v in single.gross_polygon)
    # 双排 E 角：outer × bottom 同口径
    d_outer, d_bottom = double.net_edges[1].geom, double.net_edges[2].geom
    e_miter = _analytic_miter(d_outer.b, (d_outer.b - d_outer.a).normalized(),
                              (d_bottom.b - d_bottom.a).normalized(), sa, sa)
    assert any(v.distance_to(e_miter) < 1e-9 for v in double.gross_polygon)
    # 双排对折线两端 O/S：镜像边异名 -> cutter 正常 miter。O 为反射角（内角
    # >180°，两腰弧谷底对接切线突变）：miter 交点落在两边偏移链**途中**，
    # 越过交点的采样尾/头部点被裁剪（不裁则两偏移链角部自交 = 顶部缝边三线
    # 交错，DXF 报障）——两腰弧在 O 的自然垂足（O + 切向法向·sa）均越过交点、
    # 必须不在毛样折线上，交点本身必须在
    d_top, d_top_m = double.net_edges[0].geom, double.net_edges[5].geom
    tan_top_o = d_top.tangent_at(0.0).normalized()
    tan_topm_o = d_top_m.tangent_at(1.0).normalized()
    o_miter = _analytic_miter(Point(0.0, 0.0), tan_topm_o, tan_top_o, sa, sa)
    assert any(v.distance_to(o_miter) < 1e-9 for v in double.gross_polygon)
    foot_o = Point(0.0, 0.0) + tan_top_o.perpendicular().scale(sa)
    foot_m_o = Point(0.0, 0.0) + tan_topm_o.perpendicular().scale(sa)
    assert all(v.distance_to(foot_o) > 1e-6 for v in double.gross_polygon)
    assert all(v.distance_to(foot_m_o) > 1e-6 for v in double.gross_polygon)
    # S 为凸角（约 160°，bottom ∥ chord(T,O) 与镜像底边折 ~20°）：miter 长仅
    # ≈1.02×sa 正常生成不回退阶梯，S + 2n·sa 尖刺外角点不在折线上
    d_bottom_m = double.net_edges[3].geom
    s_miter = _analytic_miter(
        d_bottom.b, (d_bottom.b - d_bottom.a).normalized(),
        (d_bottom_m.b - d_bottom_m.a).normalized(), sa, sa)
    assert any(v.distance_to(s_miter) < 1e-9 for v in double.gross_polygon)
    n_a = (d_bottom.b - d_bottom.a).normalized().perpendicular()
    n_b = (d_bottom_m.b - d_bottom_m.a).normalized().perpendicular()
    stair = d_bottom.b + n_a.scale(sa) + n_b.scale(sa)   # S + 2n·sa 尖刺外角点
    assert all(v.distance_to(stair) > 1e-6 for v in double.gross_polygon)


# ---------- 刀口落点（ET 顶点吸附：不落角顶点，切线可判）----------

def _on_corner_vertex(g: Point, poly) -> bool:
    """刀口 g 是否恰落毛样折线的**角顶点**（两侧折线不共线）。

    ET 等服装 CAD 按裁切折线顶点吸附挂刀口符号，角顶点两侧折线不共线、切线
    方向无法判定，刀口渲染成十字孤立点（DXF 报障即此）；段中或共线顶点
    （切线唯一）为合法落点。
    """
    n = len(poly)
    for i, v in enumerate(poly):
        if v.distance_to(g) > 1e-9:
            continue
        a = poly[(i - 1) % n] - v
        b = poly[(i + 1) % n] - v
        if a.length < 1e-12 or b.length < 1e-12:
            continue
        cross = abs(a.dx * b.dy - a.dy * b.dx) / (a.length * b.length)
        if cross > 1e-6:
            return True
    return False


def test_notches_not_on_corner_vertices(built):
    # 回归（DXF 刀口十字孤立点报障）：刀口坐标不得恰落缝边外沿的角顶点
    # （miter/阶梯角顶点两侧折线不共线，ET 无法判定切线方向）。例外：双排
    # 对折线两端 O/S 刀口为**工艺指定落点**——沿轴线投影，无缩水时轴线恰过
    # 缝边顶点（上端反射角裁剪交点、下端凸角 miter 顶点），打口方向由
    # gross_notch_dirs 沿轴显式给定、不依赖折线切线；改为断言与中心线共线
    _, single, double, _ = built
    for g in single.gross_notches:
        assert not _on_corner_vertex(g, single.gross_polygon), \
            f"{single.name} 刀口落在角顶点上（渲染十字孤立点）"
    for g in double.gross_notches[2:]:
        assert not _on_corner_vertex(g, double.gross_polygon), \
            f"{double.name} 刀口落在角顶点上（渲染十字孤立点）"
    axis = (double.notches[1] - double.notches[0]).normalized()
    for i in (0, 1):
        d = double.gross_notches[i] - double.notches[0]
        cross = abs(d.dx * axis.dy - d.dy * axis.dx) / d.length
        assert cross < 1e-9                     # 落在中心对称线上（绝对共线）


def test_corner_notch_projects_along_main_edge():
    # fly_sep_extra=0（zhitong 例）：单排刀口恰在 S 角点（内边×底边）、双排
    # 外缘刀口恰在 E 角点（外缘×底边）——角点不走角平分均值（会落 miter
    # 角顶点 -> 十字孤立点），按斜率取 |dy| 最大主边外法向：⊥ 内边/外缘恰
    # 1 缝份，落点在该边缝边线上（共线顶点，切线可判）
    o = PatternOptions(delta=1.0, fly_separate=True, fly_sep_extra=0.0)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    single, double, _ = build_front_fly(ctx)
    inner = [e for e in single.net_edges if e.name == "inner"][0].geom
    d = single.gross_notches[0] - single.notches[0]
    assert d.length == pytest.approx(1.0)                  # sa.inner = 1.0
    t = (inner.b - inner.a).normalized()
    assert abs(d.dx * t.dx + d.dy * t.dy) < 1e-9           # ⊥ 内边（主边外法向）
    outer = [e for e in double.net_edges if e.name == "outer"][0].geom
    d = double.gross_notches[2] - double.notches[2]
    assert d.length == pytest.approx(1.0)
    t = (outer.b - outer.a).normalized()
    assert abs(d.dx * t.dx + d.dy * t.dy) < 1e-9           # ⊥ 外缘（主边外法向）
    for g in single.gross_notches:
        assert _dist_to_poly(g, single.gross_polygon) < 1e-9
        assert not _on_corner_vertex(g, single.gross_polygon)
    for g in double.gross_notches:
        assert _dist_to_poly(g, double.gross_polygon) < 1e-9
    for g in double.gross_notches[2:]:          # 双排 O/S 沿轴线=工艺指定落点（同上）
        assert not _on_corner_vertex(g, double.gross_polygon)


# ---------- 开关与守卫 ----------

def test_double_disabled_returns_none():
    o = PatternOptions(delta=1.0, fly_separate=True, fly_sep_double=False)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    single, double, local = build_front_fly(ctx)
    assert single is not None
    assert double is None
    assert "front_fly_single.edge0" in local.sheet
    assert "front_fly_double.edge0" not in local.sheet


def test_requires_fly_separate():
    ctx = FlowRunner(M, PatternOptions(delta=1.0)).run(FULL_FLOW)
    with pytest.raises(ValueError, match="fly_separate"):
        build_front_fly(ctx)


def test_curved_waistband_smoke():
    # 弯腰头：流程读 front.fly_sep_*（顶边=下腰头线子弧）自动适配，构建不抛错
    o = PatternOptions(delta=1.0, fly_separate=True,
                       waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    single, double, _ = build_front_fly(ctx)
    _assert_closed(single)
    _assert_closed(double)
    assert _shoelace(single) < 0
    assert _shoelace(double) < 0


# ---------- 校验 / 序列化 / SVG 冒烟 ----------

def test_options_validation():
    with pytest.raises(ValueError, match="不能为负数"):
        PatternOptions(fly_separate=True,
                       fly_seam_allowances=FlySeamAllowances(top=-1))
    with pytest.raises(ValueError, match="须在"):
        PatternOptions(fly_separate=True, fly_shrinkage_warp=0.5)
    with pytest.raises(TypeError, match="FlySeamAllowances"):
        PatternOptions(fly_separate=True, fly_seam_allowances={})


def test_fly_sa_from_dict_defaults():
    sa = FlySeamAllowances.from_dict({})
    assert (sa.top, sa.outer, sa.bottom, sa.inner) == (1.0, 1.0, 1.0, 1.0)


def test_svg_smoke(built):
    _, single, double, _ = built
    svg1 = render_piece_svg(single)
    assert "单排门襟裁片" in svg1
    assert "经向" in svg1
    svg2 = render_piece_svg(double)
    assert "双排门襟裁片" in svg2


def test_local_ctx_keys(built):
    # 局部调试 ctx：两片命名边齐备（front_fly_single.edge0..4 / _double.edge0..5）
    _, _, _, local = built
    for i in range(5):
        assert f"front_fly_single.edge{i}" in local.sheet
    for i in range(6):
        assert f"front_fly_double.edge{i}" in local.sheet
