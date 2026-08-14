"""独立门襟裁片（单排 + 双排）测试（门襟裁片.md §1~§4）。

金标（H=96, Δ=1.0, front_rise=25，默认 fly_*，fly_separate=True，直腰头）：
  开深 L = 0.35×25 + 2.0 = 10.75；净宽 W = 3.8；R = W − 0.8 = 3.0；
  底部延展 fly_sep_extra = 2.0 -> 裁片高 h = L + 2.0 = 12.75。
  单排边长：top 腰头线子弧弧长 = W = 3.8；外缘直线 = h − R = 9.75；
  底角过渡弧无闭式金标（T 取在弧形腰头线上 -> 前浪与底边实际夹角 ≈82°，
  手柄常数按 90° 调定 -> 贝塞尔外凸，实测 ≈4.92；断言径向 = R + 弧长界于
  圆弧 R·θ 下界与控制多边形上界）；底边 = chord(T,O) − R（T 沿腰头线量取
  弧长 3.8，弦长实测 ≈3.80）；内边 = h = 12.75。
  刀口 = 内边上自 O 开深 10.75 处（拉链止口/前浪对位，§2 Step3）。
  双排（§4）：外缘重构直线 T->E（E = T + 前浪方向·h）与内边严格平行且绝对
  等长 12.75（O,T,E,S 平行四边形）；底端 E->S 直线 = chord(T,O)；半边沿对折轴
  O->S 镜像展开；刀口 = 对折线两端 O/S（§4 Step4 强制）+ 外缘开深 T+前浪方向·10.75。
  缩水轴向（§1）：丝缕竖直 = 经向 = 局部 Y -> X 吃纬 (1+weft)、Y 吃经 (1+warp)，
  刀口同步缩放、缝边在缩水之后（缝份不叠加缩水）。
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
    # 经向 = 丝缕竖直 = 局部 Y：shrunk = net × (1+weft, 1+warp)，刀口同步
    o = PatternOptions(delta=1.0, fly_separate=True,
                       shrinkage_warp=0.03, shrinkage_weft=0.02)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    single, double, _ = build_front_fly(ctx)
    for piece in (single, double):
        for e_net, e_shrunk in zip(piece.net_edges, piece.shrunk_edges):
            for p_net, p_sh in zip(_sample(e_net.geom), _sample(e_shrunk.geom)):
                assert p_sh.x == pytest.approx(p_net.x * 1.02)   # X 吃纬
                assert p_sh.y == pytest.approx(p_net.y * 1.03)   # Y 吃经
        for p_net, p_sh in zip(piece.notches, piece.shrunk_notches):
            assert p_sh.x == pytest.approx(p_net.x * 1.02)
            assert p_sh.y == pytest.approx(p_net.y * 1.03)


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
    assert p_sh.x == pytest.approx(p_net.x * 1.04)
    assert p_sh.y == pytest.approx(p_net.y * 1.05)


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
