"""腰头裁片测试（腰头裁片.md §三~§五；直/弯腰头 × 有/无省）。

金标（M 同 test_back_steps：W=70, H=96, Δ=1.0, outseam=102，直腰头扣腰头宽 4）：
  无省时 L_half = front.waistline_arc.length() + back.waistline_arc.length()
    （前腰长 L前 = W/4 − balance + V前省 = 17.5；后腰长 L后 = W/4 + balance + V后省 = 17.5；
     弧长略大于构造长，含 side_rise/弧下凹量）
  有省时 L_half = 弧长 − 省宽（前后独立代数求和）。
断言口径：独立复算（从 ctx 上游腰弧/省元素重推），几何不变量（边长、闭合、
镜像对称），不硬编坐标。
"""

import pytest

from ylpattern.cutter import add_seam_allowance, apply_shrinkage, edge_length
from ylpattern.draft.curves import waistband_curve
from ylpattern.exporters.piece_svg import render_piece_svg
from ylpattern.flows.back_flow import FULL_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.flows.waistband_flow import (_arc_length_of_point,
                                            build_waistband,
                                            extract_waistband_spec)
from ylpattern.geometry import CubicBezier, LineSegment, Point
from ylpattern.params import (Measurements, PatternOptions, WaistbandSeamAllowances,
                              WaistbandType)

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)


def _assert_point_approx(a, b, *, abs=1e-3):
    assert a.x == pytest.approx(b.x, abs=abs)
    assert a.y == pytest.approx(b.y, abs=abs)


@pytest.fixture()
def ctx():
    return FlowRunner(M, PatternOptions(delta=1.0)).run(FULL_FLOW)


@pytest.fixture()
def ctx_darts():
    """有省：后省 2cm + 前口袋吃省 1.5cm（p1_dist=8）。"""
    o = PatternOptions(delta=1.0, back_dart=True, back_dart_width=2.0,
                       front_pocket=True, front_pocket_dart_width=1.5,
                       front_pocket_p1_dist=8.0)
    return FlowRunner(M, o).run(FULL_FLOW)


# ---------- 净长提取（§三 代数求和）----------

def test_spec_no_dart(ctx):
    """无省：L_half = 前+后腰弧长；侧缝刀口 = L_back。"""
    spec = extract_waistband_spec(ctx)
    front_arc = ctx.curve("front.waistline_arc")
    back_arc = ctx.curve("back.waistline_arc")
    assert spec.l_front == pytest.approx(front_arc.length(), abs=1e-3)
    assert spec.l_back == pytest.approx(back_arc.length(), abs=1e-3)
    assert spec.l_half == pytest.approx(spec.l_front + spec.l_back)
    assert spec.side_notch == pytest.approx(spec.l_back)
    assert spec.back_dart_notches == ()
    assert spec.front_dart_notch is None
    assert not spec.has_front_dart and not spec.has_back_dart


def test_spec_with_darts(ctx_darts):
    """有省：L_back = 后弧长 − 后省宽；L_front = 前弧长 − 前吃省宽。"""
    o = ctx_darts.options
    spec = extract_waistband_spec(ctx_darts)
    front_arc = ctx_darts.curve("front.waistline_arc")
    back_arc = ctx_darts.curve("back.waistline_arc")
    assert spec.l_back == pytest.approx(back_arc.length() - 2.0, abs=1e-3)
    assert spec.l_front == pytest.approx(front_arc.length() - 1.5, abs=1e-3)
    assert spec.has_back_dart and spec.has_front_dart
    # 后省刀口 = p_in 投影到后腰弧的弧长（独立复算）
    leg_inner = ctx_darts.line("back.dart1_leg_inner")
    expect_s = _arc_length_of_point(back_arc, leg_inner.b)
    assert spec.back_dart_notches[0] == pytest.approx(expect_s, abs=1e-3)
    # 前省刀口 = L_back + p1_dist
    assert spec.front_dart_notch == pytest.approx(spec.l_back + 8.0)


# ---------- 轮廓闭合与形态 ----------

def test_piece_net_edges_closed(ctx):
    """净样 8 边逆时针闭合：边 i 末端 == 边 i+1 首端。"""
    piece, _ = build_waistband(ctx)
    assert len(piece.net_edges) == 8
    for i in range(8):
        a = piece.net_edges[i].geom
        b = piece.net_edges[(i + 1) % 8].geom
        end = a.b if isinstance(a, LineSegment) else a.p3
        start = b.a if isinstance(b, LineSegment) else b.p0
        _assert_point_approx(end, start)


def test_piece_straight_rectangle(ctx):
    """直腰头：下口/上口为直线，长度 = L_half；两端竖直长 = W。"""
    piece, local = build_waistband(ctx)
    spec = extract_waistband_spec(ctx)
    W = ctx.options.waistband_width
    br = local.sheet.get("wb.bottom_right").geom
    assert isinstance(br, LineSegment)
    assert br.length == pytest.approx(spec.l_half)
    tr = local.sheet.get("wb.top_right").geom
    assert tr.length == pytest.approx(spec.l_half)
    re = local.sheet.get("wb.right_end").geom
    assert re.length == pytest.approx(W)
    le = local.sheet.get("wb.left_end").geom
    assert le.length == pytest.approx(W)


def test_piece_curved_bezier_parallel():
    """弯腰头：下口为贝塞尔；上口 = 下口上移 W（控制点 y 差 = W）。"""
    o = PatternOptions(delta=1.0, waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, local = build_waistband(ctx)
    br = local.sheet.get("wb.bottom_right").geom
    assert isinstance(br, CubicBezier)
    tr = local.sheet.get("wb.top_right").geom      # 反向 + 上移 W
    assert isinstance(tr, CubicBezier)
    # 上口 = 下口反向上移 W：p0 对应下口 p3，y 差 = -W
    assert tr.p0.y - br.p3.y == pytest.approx(-o.waistband_width)
    assert tr.p3.y - br.p0.y == pytest.approx(-o.waistband_width)
    # 下口线弧长 = L_half（waistband_curve 长度精确）
    spec = extract_waistband_spec(ctx)
    assert br.length() == pytest.approx(spec.l_half, abs=1e-6)


def test_dynamic_drop_auto():
    """弯腰头不指定 drop：自动按侧缝夹角推算出合理正值 computed_drop。"""
    o = PatternOptions(delta=1.0, waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    spec = extract_waistband_spec(ctx)
    assert o.waistband_front_drop is None          # 未手动指定
    assert spec.computed_drop > 0.0                 # 前中低于后中（front_rise<back_rise）
    # 合理量级：约 1~6cm（不过平、不过陡，不触底 length 上限）
    assert 1.0 < spec.computed_drop < 6.0
    # 下口线弧长仍精确等于 L_half（drop 不影响长度闭环）
    bot = build_waistband(ctx)[1].sheet.get("wb.bottom_right").geom
    assert bot.length() == pytest.approx(spec.l_half, abs=1e-6)


def test_dynamic_drop_override():
    """弯腰头指定 drop：computed_drop 用用户值覆盖自动推算。"""
    o = PatternOptions(delta=1.0, waistband_type=WaistbandType.CURVED,
                       waistband_front_drop=2.5)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    spec = extract_waistband_spec(ctx)
    assert spec.computed_drop == pytest.approx(2.5)


def test_dynamic_drop_straight_is_zero(ctx):
    """直腰头：computed_drop = 0（与弯腰头路径无关）。"""
    spec = extract_waistband_spec(ctx)
    assert spec.computed_drop == 0.0



    """搭门量：左端 x = -(L_half + fly)；bottom_fly 为水平延伸。"""
    o = ctx.options
    piece, local = build_waistband(ctx)
    spec = extract_waistband_spec(ctx)
    bf = local.sheet.get("wb.bottom_fly").geom
    assert isinstance(bf, LineSegment)
    # 水平延伸（dy = 0），长度 = fly_extension
    assert abs(bf.a.y - bf.b.y) < 1e-9
    assert bf.length == pytest.approx(o.waistband_fly_extension)
    # 左端在 x = -(L_half + fly) 处
    le = local.sheet.get("wb.left_end").geom
    assert le.a.x == pytest.approx(-(spec.l_half + o.waistband_fly_extension))


# ---------- 刀口（§三.2）----------

def test_notches_on_bottom_and_mirrored(ctx_darts):
    """刀口在下口线上、左右镜像对称。"""
    piece, local = build_waistband(ctx_darts)
    spec = extract_waistband_spec(ctx_darts)
    bot = local.sheet.get("wb.bottom_right").geom
    # 侧缝刀口在右半下口线上（弧长 = L_back）
    side = local.point("wb.notch_side")
    if isinstance(bot, CubicBezier):
        expect = bot.point_at_length(spec.side_notch)
    else:
        expect = bot.a.lerp(bot.b, spec.side_notch / spec.l_half)
    _assert_point_approx(side, expect)
    # 镜像刀口 x 取负、y 不变
    side_m = local.point("wb.notch_side_mirror")
    assert side_m.x == pytest.approx(-side.x)
    assert side_m.y == pytest.approx(side.y)
    # 后省、前省刀口各两个（右 + 镜像）
    assert "wb.notch_back_dart1" in local.sheet
    assert "wb.notch_back_dart1_mirror" in local.sheet
    assert "wb.notch_front_dart" in local.sheet
    assert "wb.notch_front_dart_mirror" in local.sheet


# ---------- 缩水（§五.2）----------

def test_shrinkage_scales_geometry(ctx):
    """缩水：各点 x·(1+warp)、y·(1+weft)；刀口同步。"""
    o = PatternOptions(delta=1.0, shrinkage_warp=0.03, shrinkage_weft=0.02)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, _ = build_waistband(ctx)
    sx, sy = 1.03, 1.02
    # 净样 vs 缩水：第一边端点
    n0 = piece.net_edges[0].geom
    s0 = piece.shrunk_edges[0].geom
    na = n0.a if isinstance(n0, LineSegment) else n0.p0
    sa = s0.a if isinstance(s0, LineSegment) else s0.p0
    assert sa.x == pytest.approx(na.x * sx)
    assert sa.y == pytest.approx(na.y * sy)
    # 刀口同步
    for n, s in zip(piece.notches, piece.shrunk_notches):
        assert s.x == pytest.approx(n.x * sx)
        assert s.y == pytest.approx(n.y * sy)


def test_no_shrinkage_shrunk_equals_net(ctx):
    """无缩水：shrunk 边 == net 边。"""
    piece, _ = build_waistband(ctx)
    assert piece.shrunk_edges  # 默认 0 缩水仍填充（=net）
    for n, s in zip(piece.net_edges, piece.shrunk_edges):
        ng = n.geom.b if isinstance(n.geom, LineSegment) else n.geom.p3
        sg = s.geom.b if isinstance(s.geom, LineSegment) else s.geom.p3
        _assert_point_approx(ng, sg)


# ---------- 缝边（§五.3）----------

def test_seam_allowance_offset(ctx):
    """缝边：gross 外扩 = 各边缝份；直腰头 gross 矩形边界正确。"""
    sa = WaistbandSeamAllowances(top=1.0, bottom=1.0, left_end=1.2, right_end=1.0)
    o = PatternOptions(delta=1.0, waistband_seam_allowances=sa)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, _ = build_waistband(ctx)
    spec = extract_waistband_spec(ctx)
    fly = o.waistband_fly_extension
    W = o.waistband_width
    xs = [p.x for p in piece.gross_polygon]
    ys = [p.y for p in piece.gross_polygon]
    # x 边界 = [-(L_half+fly+left_end), L_half+right_end]
    assert min(xs) == pytest.approx(-(spec.l_half + fly + sa.left_end))
    assert max(xs) == pytest.approx(spec.l_half + sa.right_end)
    # y 边界 = [-W-top, +bottom]
    assert min(ys) == pytest.approx(-W - sa.top)
    assert max(ys) == pytest.approx(sa.bottom)


def test_seam_allowance_zero(ctx):
    """缝份全 0：gross 多边形 == 净样采样（重合）。"""
    sa = WaistbandSeamAllowances(top=0, bottom=0, left_end=0, right_end=0)
    piece_none, _ = build_waistband(ctx)
    piece_zero = add_seam_allowance(piece_none, sa)
    # gross 非空且边界 == 净样边界
    xs = [p.x for p in piece_zero.gross_polygon]
    nx = []
    for e in piece_zero.net_edges:
        g = e.geom
        pts = [g.a, g.b] if isinstance(g, LineSegment) else g.sample(8)
        nx += [p.x for p in pts]
    assert min(xs) == pytest.approx(min(nx), abs=1e-6)
    assert max(xs) == pytest.approx(max(nx), abs=1e-6)


# ---------- 独立 SVG（§五.4）----------

def test_svg_render(ctx):
    piece, _ = build_waistband(ctx)
    svg = render_piece_svg(piece)
    assert svg.startswith("<svg")
    assert "gross" in svg
    assert "net" in svg
    assert "grain" in svg
    assert "腰头裁片" in svg


def test_svg_curved_with_darts(ctx_darts):
    piece, _ = build_waistband(ctx_darts)
    svg = render_piece_svg(piece)
    assert svg.startswith("<svg")
    assert "notch" in svg


# ---------- 边界与降级 ----------

def test_waistband_curve_drop_zero_is_line():
    """drop=0 退化为直线（直腰头底边）。"""
    c = waistband_curve(35.0, 0.0)
    assert c.p0.y == pytest.approx(0.0)
    assert c.p3.y == pytest.approx(0.0)
    assert c.p0.y == c.p1.y == c.p2.y == c.p3.y
    assert c.length() == pytest.approx(35.0)


def test_waistband_curve_length_exact():
    """drop>0 时曲线弧长精确等于目标（§四 数学要求）。"""
    for drop in (0.5, 1.5, 3.0):
        c = waistband_curve(40.0, drop)
        assert c.length() == pytest.approx(40.0, abs=1e-9)


def test_options_validation():
    """缝份负数 / 缩水越界 raise。"""
    with pytest.raises(ValueError):
        PatternOptions(delta=1.0, shrinkage_warp=0.5)
    with pytest.raises(ValueError):
        PatternOptions(delta=1.0, waistband_seam_allowances=
                       WaistbandSeamAllowances(top=-1.0))
    with pytest.raises(ValueError):
        PatternOptions(delta=1.0, waistband_front_drop=-1.0)


def test_curved_no_dart_builds():
    """弯腰头无省：完整构建不抛错（覆盖弯腰头 + 镜像 + 搭门）。"""
    o = PatternOptions(delta=1.0, waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, _ = build_waistband(ctx)
    assert len(piece.net_edges) == 8
    assert piece.gross_polygon


def test_piece_fly_zero_no_degenerate_edges():
    """fly_extension=0：不产生零长搭门边，裁片构建与缝边不抛错（zhitong 场景）。

    零长边无切线，旧版 cutter._offset_edge_points 对 (b-a).normalized() 抛
    「零向量无法归一化」；装配时滤除后净样 6 边、缝边正常外扩。
    """
    o = PatternOptions(delta=1.0, waistband_type=WaistbandType.CURVED,
                       waistband_fly_extension=0.0)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, _ = build_waistband(ctx)
    # 无零长退化边
    assert all(edge_length(e.geom) > 1e-9 for e in piece.net_edges)
    # 8 边去掉两条零长搭门边（top_fly / bottom_fly）= 6 条有效边
    assert len(piece.net_edges) == 6
    # gross 正常生成（不触发零向量归一化），至少 6 个外扩顶点
    assert piece.gross_polygon
    assert len(piece.gross_polygon) >= 6
