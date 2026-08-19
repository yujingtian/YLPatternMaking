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
from ylpattern.flows.waistband_flow import (build_waistband,
                                            extract_waistband_spec)
from ylpattern.geometry import CubicBezier, LineSegment, Point
from ylpattern.params import (Measurements, PatternOptions, WaistbandGrain,
                              WaistbandSeamAllowances, WaistbandType)

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)


def _assert_point_approx(a, b, *, abs=1e-3):
    assert a.x == pytest.approx(b.x, abs=abs)
    assert a.y == pytest.approx(b.y, abs=abs)


def _line_dist(p, a, b):
    """点 p 到直线 ab（无限延长线）的距离。"""
    v = b - a
    return abs(v.dx * (p.y - a.y) - v.dy * (p.x - a.x)) / v.length


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
    """无省：L_half = 前+后腰弧长。"""
    spec = extract_waistband_spec(ctx)
    front_arc = ctx.curve("front.waistline_arc")
    back_arc = ctx.curve("back.waistline_arc")
    assert spec.l_front == pytest.approx(front_arc.length(), abs=1e-3)
    assert spec.l_back == pytest.approx(back_arc.length(), abs=1e-3)
    assert spec.l_half == pytest.approx(spec.l_front + spec.l_back)


def test_spec_with_darts(ctx_darts):
    """有省：L_back = 后弧长 − 后省宽；L_front = 前弧长 − 前吃省宽（省宽仅扣长）。"""
    spec = extract_waistband_spec(ctx_darts)
    front_arc = ctx_darts.curve("front.waistline_arc")
    back_arc = ctx_darts.curve("back.waistline_arc")
    assert spec.l_back == pytest.approx(back_arc.length() - 2.0, abs=1e-3)
    assert spec.l_front == pytest.approx(front_arc.length() - 1.5, abs=1e-3)


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


def test_piece_curved_top_normal_offset():
    """弯腰头：下口为贝塞尔；上口 = 下口沿端点法向偏移 W（端点切线保留、与封边直角）。"""
    o = PatternOptions(delta=1.0, waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, local = build_waistband(ctx)
    br = local.sheet.get("wb.bottom_right").geom
    assert isinstance(br, CubicBezier)
    tr = local.sheet.get("wb.top_right").geom      # 反向后：tr.p0 = 上口前中端
    assert isinstance(tr, CubicBezier)
    W = o.waistband_width
    # 上口前中端 = 下口前中端沿前中法向偏移 W：偏移向量 ⊥ 前中切线、|偏移|=W
    offset = tr.p0 - br.p3
    tang = br.tangent_at(1.0)
    assert abs(offset.dx * tang.dx + offset.dy * tang.dy) < 1e-9   # ⊥ 前中切线
    assert offset.length == pytest.approx(W)
    # 上口后中端仍在镜像轴 x=0（后中法向垂直）：tr.p3.x = 0
    assert abs(tr.p3.x) < 1e-9
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


def test_fly_extension_straight(ctx):
    """直腰头搭门：切线水平 -> bottom_fly 水平外延 fly；左端竖直在 x=-(L_half+fly)。"""
    o = ctx.options
    piece, local = build_waistband(ctx)
    spec = extract_waistband_spec(ctx)
    bf = local.sheet.get("wb.bottom_fly").geom
    assert isinstance(bf, LineSegment)
    # 直腰头端点切线水平 -> 搭门水平延伸（dy = 0），长度 = fly_extension
    assert abs(bf.a.y - bf.b.y) < 1e-9
    assert bf.length == pytest.approx(o.waistband_fly_extension)
    # 左端在 x = -(L_half + fly) 处
    le = local.sheet.get("wb.left_end").geom
    assert le.a.x == pytest.approx(-(spec.l_half + o.waistband_fly_extension))


def test_curved_ends_right_angle():
    """弯腰头端点直角：搭门沿端点切线、封边沿端点法向（四处端点为直角）。"""
    o = PatternOptions(delta=1.0, waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, local = build_waistband(ctx)
    W = o.waistband_width

    bot = local.sheet.get("wb.bottom_right").geom       # CubicBezier（右半下口）
    # 右端封边沿前中法向：封边向量 ⊥ 前中切线，长度 = W
    re = local.sheet.get("wb.right_end").geom
    re_vec = re.b - re.a
    tang_front = bot.tangent_at(1.0)
    assert abs(re_vec.dx * tang_front.dx + re_vec.dy * tang_front.dy) < 1e-9
    assert re.length == pytest.approx(W)
    # 左端封边 ⊥ 搭门（bottom_fly），长度 = W
    le = local.sheet.get("wb.left_end").geom
    bf = local.sheet.get("wb.bottom_fly").geom
    le_vec = le.b - le.a
    bf_vec = bf.b - bf.a
    assert abs(le_vec.dx * bf_vec.dx + le_vec.dy * bf_vec.dy) < 1e-9
    assert le.length == pytest.approx(W)
    # 搭门沿左前中切线：bottom_fly 与 bottom_left 起点切线共线（曲线顺势顺滑外延）
    bl = local.sheet.get("wb.bottom_left").geom
    bl_t0 = bl.tangent_at(0.0)
    cross = bf_vec.dx * bl_t0.dy - bf_vec.dy * bl_t0.dx
    assert abs(cross) < 1e-9


# ---------- 刀口（§四.2 v0.4：后中净样位 + 四角缝边交点位）----------

def test_notches_net_positions(ctx_darts):
    """净样刀口 5 点：后中 O + 左右两端下/上顶点（有省不打省位/侧缝刀口）。"""
    piece, local = build_waistband(ctx_darts)
    _assert_point_approx(local.point("wb.notch_back_center"), Point(0, 0))
    # 右下顶点 = 下口线前中端；右上顶点 = 上口线前中端（top_right 反向后 p0）
    bot = local.sheet.get("wb.bottom_right").geom
    front = bot.b if isinstance(bot, LineSegment) else bot.p3
    _assert_point_approx(local.point("wb.notch_right_bottom"), front)
    top = local.sheet.get("wb.top_right").geom
    front_top = top.a if isinstance(top, LineSegment) else top.p0
    _assert_point_approx(local.point("wb.notch_right_top"), front_top)
    # 左侧两顶点 = 搭门外端上下（bottom_fly.a == left_end.b / top_fly.b == left_end.a）
    _assert_point_approx(local.point("wb.notch_left_bottom"),
                         local.sheet.get("wb.bottom_fly").geom.a)
    _assert_point_approx(local.point("wb.notch_left_top"),
                         local.sheet.get("wb.left_end").geom.a)
    assert len(piece.notches) == 5
    # 旧省位/侧缝刀口不再上版（回归守卫）
    for gone in ("wb.notch_side", "wb.notch_back_dart1", "wb.notch_front_dart"):
        assert gone not in local.sheet


def test_notches_gross_at_sa_crossings(ctx_darts):
    """毛样刀口 5 点全在缝边交点上：净线延长线 ∩ 缝边线（§四.2 v0.4）。

    直腰头金标：后中 (0, sa.bottom)、右下 (L_half, sa.bottom)、
    右上 (L_half+sa.right, -W)、左上 (-(L_half+fly)-sa.left, -W)、
    左下 (-(L_half+fly), sa.bottom)。
    """
    o = ctx_darts.options
    piece, _ = build_waistband(ctx_darts)
    spec = extract_waistband_spec(ctx_darts)
    l, W, fly = spec.l_half, o.waistband_width, o.waistband_fly_extension
    sa = o.waistband_seam_allowances
    gn = piece.gross_notches
    assert len(gn) == 5
    _assert_point_approx(gn[0], Point(0, sa.bottom))                  # 后中：垂线∩下口缝边
    _assert_point_approx(gn[1], Point(l, sa.bottom))                  # 右下：宽线∩下口缝边
    _assert_point_approx(gn[2], Point(l + sa.right_end, -W))          # 右上：腰头线∩右端缝边
    _assert_point_approx(gn[3], Point(-(l + fly) - sa.left_end, -W))  # 左上：腰头线∩左端缝边
    _assert_point_approx(gn[4], Point(-(l + fly), sa.bottom))         # 左下：宽线∩下口缝边


def test_notches_curved_gross_on_sa_lines():
    """弯腰头毛样刀口：交点在对应缝边线上（距净边=缝份）且在净线延长线上。"""
    o = PatternOptions(delta=1.0, waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, local = build_waistband(ctx)
    sa = o.waistband_seam_allowances
    gn = piece.gross_notches
    assert len(gn) == 5
    right_end = local.line("wb.right_end")
    left_end = local.line("wb.left_end")
    bf = local.sheet.get("wb.bottom_fly").geom
    tf = local.sheet.get("wb.top_fly").geom
    br = local.sheet.get("wb.bottom_right").geom      # CubicBezier（弯腰头下口）
    tr = local.sheet.get("wb.top_right").geom
    # 后中：在原点垂线（x=0）上、距下口线（后中起端切向）= bottom 缝份
    assert gn[0].x == pytest.approx(0.0, abs=1e-6)
    assert _line_dist(gn[0], br.p0, br.p0 + br.tangent_at(0.0)) == pytest.approx(
        sa.bottom, abs=1e-6)
    # 右下：在宽线（right_end 线）上、距下口线（末端切向）= bottom 缝份
    assert _line_dist(gn[1], right_end.a, right_end.b) == pytest.approx(0.0, abs=1e-6)
    assert _line_dist(gn[1], br.p3, br.p3 + br.tangent_at(1.0)) == pytest.approx(
        sa.bottom, abs=1e-6)
    # 右上：距右端封边线 = right_end 缝份、在上口切向线（top_right 起端）上
    assert _line_dist(gn[2], right_end.a, right_end.b) == pytest.approx(
        sa.right_end, abs=1e-6)
    assert _line_dist(gn[2], tr.p0, tr.p0 + tr.tangent_at(0.0)) == pytest.approx(
        0.0, abs=1e-6)
    # 左上：距左端封边线 = left_end 缝份、在上口搭门线（top_fly）上
    assert _line_dist(gn[3], left_end.a, left_end.b) == pytest.approx(
        sa.left_end, abs=1e-6)
    assert _line_dist(gn[3], tf.a, tf.b) == pytest.approx(0.0, abs=1e-6)
    # 左下：在左端封边线上、距下口搭门线（bottom_fly）= bottom 缝份
    assert _line_dist(gn[4], left_end.a, left_end.b) == pytest.approx(0.0, abs=1e-6)
    assert _line_dist(gn[4], bf.a, bf.b) == pytest.approx(sa.bottom, abs=1e-6)


# ---------- 缩水（§五.2）----------

def test_shrinkage_scales_geometry(ctx):
    """缩水：按 waistband_grain 把经/纬率映射到 X/Y 轴（默认 WIDTH：X=纬、Y=经）。"""
    o = PatternOptions(delta=1.0, shrinkage_warp=0.03, shrinkage_weft=0.02)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, _ = build_waistband(ctx)
    assert o.waistband_grain is WaistbandGrain.WIDTH          # 默认宽向=经
    sx, sy = 1 / 0.98, 1 / 0.97   # WIDTH：X(长向)=纬、Y(宽向)=经（÷(1-r) 口径）
    # 右端封边（EDGE_ORDER[1]）末端 (X,−W)：x、y 均非零，同时校验两轴
    n0 = piece.net_edges[1].geom
    s0 = piece.shrunk_edges[1].geom
    nb = n0.b if isinstance(n0, LineSegment) else n0.p3
    sb = s0.b if isinstance(s0, LineSegment) else s0.p3
    assert sb.x == pytest.approx(nb.x * sx)
    assert sb.y == pytest.approx(nb.y * sy)
    # 刀口同步（直腰头刀口在下口 y=0，主要校验 x 轴）
    for n, s in zip(piece.notches, piece.shrunk_notches):
        assert s.x == pytest.approx(n.x * sx)
        assert s.y == pytest.approx(n.y * sy)


def test_shrinkage_length_grain_swaps_axes():
    """LENGTH（长向=经）：X 吃 warp、Y 吃 weft（与默认 WIDTH 相反）。"""
    o = PatternOptions(delta=1.0, waistband_grain=WaistbandGrain.LENGTH,
                       shrinkage_warp=0.03, shrinkage_weft=0.02)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, _ = build_waistband(ctx)
    sx, sy = 1 / 0.97, 1 / 0.98   # LENGTH：X=经、Y=纬（÷(1-r) 口径）
    n0 = piece.net_edges[1].geom
    s0 = piece.shrunk_edges[1].geom
    nb = n0.b if isinstance(n0, LineSegment) else n0.p3
    sb = s0.b if isinstance(s0, LineSegment) else s0.p3
    assert sb.x == pytest.approx(nb.x * sx)
    assert sb.y == pytest.approx(nb.y * sy)


def test_grain_orientation():
    """丝缕线方向随 waistband_grain：WIDTH 竖向（沿裤长）、LENGTH 水平（沿周向）。"""
    o = PatternOptions(delta=1.0)                          # 默认 WIDTH
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    _, local = build_waistband(ctx)
    g = local.line("wb.grain")
    assert g.a.x == pytest.approx(g.b.x)                   # 竖向：x 相同
    assert g.a.y != pytest.approx(g.b.y)
    o2 = PatternOptions(delta=1.0, waistband_grain=WaistbandGrain.LENGTH)
    ctx2 = FlowRunner(M, o2).run(FULL_FLOW)
    _, local2 = build_waistband(ctx2)
    g2 = local2.line("wb.grain")
    assert g2.a.y == pytest.approx(g2.b.y)                 # 水平：y 相同
    assert g2.a.x != pytest.approx(g2.b.x)


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
