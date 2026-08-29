"""腰头裁片测试（腰头裁片.md §三~§五 v0.8；直/弯腰头 × 有/无省）。

金标（M 同 test_back_steps：W=70, H=96, Δ=1.0, outseam=102，直腰头扣腰头宽 4）：
  直腰头无省 L_half = front.waistline_arc.length() + back.waistline_arc.length()
    （前腰长 L前 = W/4 − balance + V前省 = 17.5；后腰长 L后 = W/4 + balance + V后省 = 17.5；
     弧长略大于构造长，含 side_rise/弧下凹量）
  直腰头有省 L_half = 弧长 − 省宽（前后独立代数求和）。
  弯腰头 v0.9 真拼合 + 整根均匀圆弧：后省绕尖闭口 -> 前口袋吃省取上腰头线法足
    （pocket_p1_top）C1 闭口 -> 跨后侧缝反射拼合 -> 局部系（origin=后中、
    X̂=后弧起切向）-> 整根均匀圆弧（curves.uniform_arc_cubic：弧长=链净长精确、
    总转角=链末切向角（保弯曲，sag 经它传入）、起端切向水平（后中镜像 C1/C2），
    曲率恒 1/R 全弧均匀、端点位置派生），l_* = 闭省后链实长；弯/直边数同构恒 8。
断言口径：独立复算（从 ctx 上游腰弧/省元素重推），几何不变量（边数、闭合、
镜像对称、圆顺性），不硬编坐标。
"""

import math

import pytest

from ylpattern.cutter import add_seam_allowance, edge_length
from ylpattern.draft import curves
from ylpattern.exporters.piece_svg import render_piece_svg
from ylpattern.flows.back_flow import FULL_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.flows.waistband_flow import (build_waistband,
                                            extract_waistband_spec)
from ylpattern.geometry import CubicBezier, LineSegment, Point
from ylpattern.params import (Measurements, PatternOptions, WaistbandGrain,
                              WaistbandSeamAllowances, WaistbandType)
from ylpattern.steps import waistband_steps as ws

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)

_CURVED = dict(delta=1.0, waistband_type=WaistbandType.CURVED)


def _assert_point_approx(a, b, *, abs=1e-3):
    assert a.x == pytest.approx(b.x, abs=abs)
    assert a.y == pytest.approx(b.y, abs=abs)


def _line_dist(p, a, b):
    """点 p 到直线 ab（无限延长线）的距离。"""
    v = b - a
    return abs(v.dx * (p.y - a.y) - v.dy * (p.x - a.x)) / v.length


def _end(g, *, start=False):
    """线段/贝塞尔统一端点（LineSegment.a/b、CubicBezier.p0/p3）。"""
    if isinstance(g, LineSegment):
        return g.a if start else g.b
    return g.p0 if start else g.p3


def _tangent(g, t):
    v = g.tangent_at(t)
    return v


def _angle_deg(v1, v2):
    cross = v1.dx * v2.dy - v1.dy * v2.dx
    dot = v1.dx * v2.dx + v1.dy * v2.dy
    return math.degrees(math.atan2(abs(cross), dot))


@pytest.fixture()
def ctx():
    return FlowRunner(M, PatternOptions(delta=1.0)).run(FULL_FLOW)


@pytest.fixture()
def ctx_darts():
    """直腰头有省：后省 2cm + 前口袋吃省 1.5cm（p1_dist=8）。"""
    o = PatternOptions(delta=1.0, back_dart=True, back_dart_width=2.0,
                       front_pocket=True, front_pocket_dart_width=1.5,
                       front_pocket_p1_dist=8.0)
    return FlowRunner(M, o).run(FULL_FLOW)


@pytest.fixture()
def ctx_curved():
    """弯腰头无省（v0.7 真拼合）。"""
    return FlowRunner(M, PatternOptions(**_CURVED)).run(FULL_FLOW)


@pytest.fixture()
def ctx_curved_dart():
    """弯腰头 + 后省 2cm。"""
    o = PatternOptions(back_dart=True, back_dart_width=2.0, **_CURVED)
    return FlowRunner(M, o).run(FULL_FLOW)


@pytest.fixture()
def ctx_curved_full():
    """弯腰头 + 后省 2cm + 前口袋吃省 1.5cm。"""
    o = PatternOptions(back_dart=True, back_dart_width=2.0,
                       front_pocket=True, front_pocket_dart_width=1.5,
                       front_pocket_p1_dist=8.0, **_CURVED)
    return FlowRunner(M, o).run(FULL_FLOW)


# ---------- 净长提取（§三：直=代数求和；弯=闭省后链实长）----------

def test_spec_no_dart(ctx):
    """无省：L_half = 前+后腰弧长。"""
    spec = extract_waistband_spec(ctx)
    front_arc = ctx.curve("front.waistline_arc")
    back_arc = ctx.curve("back.waistline_arc")
    assert spec.l_front == pytest.approx(front_arc.length(), abs=1e-3)
    assert spec.l_back == pytest.approx(back_arc.length(), abs=1e-3)
    assert spec.l_half == pytest.approx(spec.l_front + spec.l_back)


def test_spec_with_darts(ctx_darts):
    """直腰头有省：L_back = 后弧长 − 后省宽；L_front = 前弧长 − 前吃省宽。"""
    spec = extract_waistband_spec(ctx_darts)
    front_arc = ctx_darts.curve("front.waistline_arc")
    back_arc = ctx_darts.curve("back.waistline_arc")
    assert spec.l_back == pytest.approx(back_arc.length() - 2.0, abs=1e-3)
    assert spec.l_front == pytest.approx(front_arc.length() - 1.5, abs=1e-3)


def test_spec_curved_no_dart_chain_lengths(ctx_curved):
    """弯腰头无省：l_* = 主版腰弧长（无省闭口、反射/局部系刚体保长）；
    拟合弧单条三次、过原点、起切向水平、弧长锁净长（±len_tol）。"""
    spec = extract_waistband_spec(ctx_curved)
    assert isinstance(spec.bottom_arc, CubicBezier)
    assert spec.l_back == pytest.approx(
        ctx_curved.curve("back.waistline_arc").length(), abs=1e-9)
    assert spec.l_front == pytest.approx(
        ctx_curved.curve("front.waistline_arc").length(), abs=1e-9)
    arc = spec.bottom_arc
    _assert_point_approx(arc.p0, Point(0, 0), abs=1e-12)
    t0 = arc.tangent_at(0.0)
    assert abs(t0.dy) < 1e-9                        # 起切向水平（镜像 C1/C2）
    assert arc.length() == pytest.approx(spec.l_half, abs=0.03)


# ---------- 轮廓闭合与形态（§四.分支B：弯/直同构恒 8 边）----------

@pytest.mark.parametrize("fixture_name,n_edges", [
    ("ctx", 8),                 # 直腰头 8 边
    ("ctx_curved", 8),          # 弯 d=0：单弧 8 边
    ("ctx_curved_dart", 8),     # 弯 d=1：单弧 8 边（段数不随省数变化）
    ("ctx_curved_full", 8),     # 弯 d=2：单弧 8 边
])
def test_piece_net_edges_closed(fixture_name, n_edges, request):
    """净样边数随选项集确定且逆时针闭合：边 i 末端 == 边 i+1 首端。"""
    ctx = request.getfixturevalue(fixture_name)
    piece, _ = build_waistband(ctx)
    assert len(piece.net_edges) == n_edges
    n = len(piece.net_edges)
    for i in range(n):
        a = piece.net_edges[i].geom
        b = piece.net_edges[(i + 1) % n].geom
        _assert_point_approx(_end(a), _end(b, start=True), abs=1e-9)


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


def test_piece_curved_top_normal_offset(ctx_curved):
    """弯腰头：上口 = 下口（单条拟合弧）沿端点法向偏移 W（端点切线保留、
    与封边直角）。"""
    piece, local = build_waistband(ctx_curved)
    spec = extract_waistband_spec(ctx_curved)
    W = ctx_curved.options.waistband_width
    bot = local.sheet.get("wb.bottom_right").geom
    top = local.sheet.get("wb.top_right").geom      # 反向序：前中->后中
    assert isinstance(bot, CubicBezier) and isinstance(top, CubicBezier)
    # 上口前中端 = 下口前中端沿前中法向偏移 W（端差 ⊥ 下口末切向）
    offset = top.p0 - bot.p3
    tang = bot.tangent_at(1.0)
    assert abs(offset.dx * tang.dx + offset.dy * tang.dy) < 1e-9
    assert offset.length == pytest.approx(W)
    # 上口后中端仍在镜像轴 x=0（后中起端法向 ⟂ X̂）
    assert abs(top.p3.x) < 1e-9
    # 下口弧长锁净长（弧长罚项 ±len_tol）
    assert bot.length() == pytest.approx(spec.l_half, abs=0.05)


def test_curved_join_placement(ctx_curved):
    """真拼合守卫（替代 drop 三测）：拟合弧前中端在前方且低于后中
    （front_rise<back_rise 物理落差显影）；末切向朝右上方（反射拼合
    方向正确性——同侧旋转退化口径前中折返 ~150°，弧末切向左翻即暴露）。"""
    spec = extract_waistband_spec(ctx_curved)
    arc = spec.bottom_arc
    assert arc.p3.x > 0.7 * spec.l_half              # 前中在链前段尽头
    assert -20.0 < arc.p3.y < -5.0                   # 低于后中（落差 ~11.5）
    t_end = arc.tangent_at(1.0)
    assert t_end.dx > 0.0                            # 末切向朝前（右）


def test_fly_extension_straight(ctx):
    """直腰头搭门：切线水平 -> bottom_fly 水平外延 fly；左端竖直在 x=-(L_half+fly)。"""
    o = ctx.options
    piece, local = build_waistband(ctx)
    spec = extract_waistband_spec(ctx)
    bf = local.sheet.get("wb.bottom_fly").geom
    assert isinstance(bf, LineSegment)
    assert abs(bf.a.y - bf.b.y) < 1e-9
    assert bf.length == pytest.approx(o.waistband_fly_extension)
    le = local.sheet.get("wb.left_end").geom
    assert le.a.x == pytest.approx(-(spec.l_half + o.waistband_fly_extension))


def test_curved_ends_right_angle(ctx_curved):
    """弯腰头端点直角：搭门沿端点切线、封边沿端点法向（四处端点为直角）。"""
    piece, local = build_waistband(ctx_curved)
    W = ctx_curved.options.waistband_width
    bot = local.sheet.get("wb.bottom_right").geom
    bot_left = local.sheet.get("wb.bottom_left").geom
    re = local.line("wb.right_end")
    re_vec = re.b - re.a
    tang_front = bot.tangent_at(1.0)
    assert abs(re_vec.dx * tang_front.dx + re_vec.dy * tang_front.dy) < 1e-9
    assert re.length == pytest.approx(W)
    le = local.line("wb.left_end")
    bf = local.sheet.get("wb.bottom_fly").geom
    le_vec = le.b - le.a
    bf_vec = bf.b - bf.a
    assert abs(le_vec.dx * bf_vec.dx + le_vec.dy * bf_vec.dy) < 1e-9
    assert le.length == pytest.approx(W)
    # 搭门沿左前中切线：bottom_fly 与 bottom_left 起点切线共线
    bl_t0 = bot_left.tangent_at(0.0)
    cross = bf_vec.dx * bl_t0.dy - bf_vec.dy * bl_t0.dx
    assert abs(cross) < 1e-9


# ---------- v0.8 新金标：sag 响应 / 圆顺性 / 镜像 / 推码不变量 ----------

@pytest.mark.parametrize("sag_a,sag_b", [(0.2, 0.4)])
def test_curved_sag_response(sag_a, sag_b):
    """(a) sag 响应（用户原始投诉的回归）：front/back_waist_curve_sag 全量
    传到裁片——sag 0.2 -> 0.4 后两版下口弧按弧长分数逐点对照最大偏离
    >= 0.2cm（实测 ~0.47；整弧弦深被前后落差 ~5cm 主导，不能作仪表）。"""
    arcs = {}
    for sag in (sag_a, sag_b):
        o = PatternOptions(back_waist_curve_sag=sag,
                           front_waist_curve_sag=sag, **_CURVED)
        ctx = FlowRunner(M, o).run(FULL_FLOW)
        arcs[sag] = extract_waistband_spec(ctx).bottom_arc

    def _at_frac(arc, f):
        return arc.point_at(arc.t_at_length(f * arc.length()))

    worst = max(_at_frac(arcs[sag_b], i / 64).distance_to(
        _at_frac(arcs[sag_a], i / 64)) for i in range(65))
    assert worst >= 0.2


# ---------- v0.9 新金标：整根均匀圆弧（后段弧度显形 / 曲率均匀）----------

def test_curved_uniform_back_section_visible(ctx_curved):
    """(v0.9 核心) 后段弧度显形（用户投诉回归：v0.8 拟合忠实保留拼合链
    「平后段+侧缝肘弯」，后段贴水平线近直）：下口弧按弧长分数量取——
    侧缝位（frac=0.5，无省态 l_back≈l_front）下凹 >= 2.5cm、后段中点
    （frac=0.25）下凹 >= 0.5cm（实测 3.11 / 0.79；v0.8 同位 -0.7 / +0.1）。"""
    spec = extract_waistband_spec(ctx_curved)
    arc = spec.bottom_arc
    L = arc.length()

    def _y(f):
        return arc.point_at(arc.t_at_length(f * L)).y

    assert _y(0.5) <= -2.5
    assert _y(0.25) <= -0.5


@pytest.mark.parametrize("fixture_name", ["ctx_curved", "ctx_curved_full"])
def test_curved_uniform_curvature(fixture_name, request):
    """(v0.9 核心) 曲率全弧均匀（抛物线样顺滑弧，总转角=链末切向、净长
    精确）：κ 采样单一凹向（无 v0.8 构造性正卷曲/钟形集中）、
    max|κ|/min|κ| <= 1.05（圆弧三次近似误差 <1%）。"""
    ctx = request.getfixturevalue(fixture_name)
    spec = extract_waistband_spec(ctx)
    arc = spec.bottom_arc
    ks = [arc.curvature_at(i / 16) for i in range(1, 16)]
    assert all(k < 0 for k in ks)                    # 单一凹向（朝下弯）
    assert max(abs(k) for k in ks) / min(abs(k) for k in ks) <= 1.05
    assert arc.length() == pytest.approx(spec.l_half, abs=0.01)


def _tangent_steps(arc, n=32):
    """弧上相邻采样切向角步进（度，unwrap 后）。"""
    angs = []
    for i in range(n + 1):
        v = arc.tangent_at(i / n)
        a = math.degrees(math.atan2(v.dy, v.dx))
        if angs and a - angs[-1] > 180.0:
            a -= 360.0
        elif angs and a - angs[-1] < -180.0:
            a += 360.0
        angs.append(a)
    return [abs(angs[i + 1] - angs[i]) for i in range(n)]


@pytest.mark.parametrize("fixture_name", ["ctx_curved", "ctx_curved_full"])
def test_curved_fairness_smooth(fixture_name, request):
    """(b) 整根圆顺：下口弧无折角/无环——切向角沿曲线连续（相邻步进 < 5°）、
    总转角 <= 270°（均匀弧构造保证）；闭省折角不进弧形（v0.9 均匀弧
    只取链净长与末切向）。"""
    ctx = request.getfixturevalue(fixture_name)
    piece, local = build_waistband(ctx)
    arc = local.sheet.get("wb.bottom_right").geom
    steps = _tangent_steps(arc)
    assert max(steps) < 5.0
    assert sum(steps) <= 270.0


def test_curved_cb_no_w(ctx_curved):
    """(c) 后中无 W：左右半精确镜像（mirror(x) 逐点重合 1e-9，镜像+反向
    参数化构造保证）；后中窗内不上鼓（+y 峰 <= 0.1cm——均匀弧 y 恒 <= 0，构造保证不上鼓）。"""
    piece, local = build_waistband(ctx_curved)
    gr = local.sheet.get("wb.bottom_right").geom
    gl = local.sheet.get("wb.bottom_left").geom
    for s in range(9):
        pr = gr.point_at(s / 8)
        pl = gl.point_at(1 - s / 8)
        assert abs(pr.x + pl.x) < 1e-9
        assert abs(pr.y - pl.y) < 1e-9
    assert max(p.y for p in gr.sample(9)[:3]) <= 0.1   # 后中端不上鼓


def test_curved_curvature_peak_bounded(ctx_curved_full):
    """(d) 弧面饱满：全弧 |κ| 峰值 <= 0.25（杜绝 R=4cm 级酒窝；均匀弧 κ=|turn|/L≈0.02，探针实测）。"""
    piece, local = build_waistband(ctx_curved_full)
    arc = local.sheet.get("wb.bottom_right").geom
    peak = max(abs(arc.curvature_at(i / 16)) for i in range(1, 16))
    assert peak <= 0.25


def test_curved_grading_edge_count_invariant():
    """(e) 推码不变量：同一 options 不同码，弯腰头净边数恒 8（多码 DXF
    跨码对应的前提；段数只依赖选项集、与省数无关）。"""
    o = PatternOptions(back_dart=True, back_dart_width=2.0,
                       front_pocket=True, front_pocket_dart_width=1.5,
                       front_pocket_p1_dist=8.0, **_CURVED)
    m2 = Measurements(waist=74, hip=99, knee=47.5, hem=37,
                      front_rise=25.5, back_rise=33.5, outseam=103, thigh=60)
    piece_a, _ = build_waistband(FlowRunner(M, o).run(FULL_FLOW))
    piece_b, _ = build_waistband(FlowRunner(m2, o).run(FULL_FLOW))
    assert len(piece_a.net_edges) == len(piece_b.net_edges) == 8


def test_curved_back_dart_closure_golden(ctx_curved_dart):
    """(f) 后省闭口金标：l_back = 后弧长 − 省口弧段（独立求交复算，
    线-贝塞尔求交与闭口逻辑互不复用）；与代数扣省宽差 < 3%（弧 vs 弦）。"""
    ctx = ctx_curved_dart
    spec = extract_waistband_spec(ctx)
    arc = ctx.curve("back.waistline_arc")
    leg_in = ctx.line("back.dart1_leg_inner")
    leg_out = ctx.line("back.dart1_leg_outer")
    hit_a = curves.line_bezier_intersect(leg_in, arc)
    hit_b = curves.line_bezier_intersect(leg_out, arc)
    assert hit_a is not None and hit_b is not None
    t_a, t_b = sorted((hit_a[1], hit_b[1]))
    mouth = curves.bezier_subrange(arc, t_a, t_b).length()
    # 独立求交与闭口内求交的定位精度差 ~1e-5（采样二分容差）
    assert spec.l_back == pytest.approx(arc.length() - mouth, abs=1e-4)
    # 省口弧段略窄于省宽：省口两点定义在腰头直线（弦）上、腿向省尖收拢
    # 半角 atan(1/11)≈5.2°，弧 sag ~0.33 朝省尖侧下凹，收缩量 ≈
    # 2·sag·sin(半角) ≈ 0.06（实测 0.0616）——闭口在弧上取窄量即 ET 口径
    assert mouth == pytest.approx(2.0, abs=0.08)
    # 净长锁进拟合弧（省折角抹顺、长度不丢）
    assert spec.bottom_arc.length() == pytest.approx(spec.l_half, abs=0.03)


def test_curved_pocket_dart_closure_golden(ctx_curved_full):
    """(f) 前口袋吃省闭口金标：切点 = 上腰头线法足（pocket_p1_top 在弧上，
    弧上残差 < 1e-3）；闭后 l_front = 前弧长 − 省口弧段。"""
    ctx = ctx_curved_full
    spec = extract_waistband_spec(ctx)
    arc = ctx.curve("front.waistline_arc")
    p1 = ctx.point("front.pocket_p1_top")
    p1t = ctx.point("front.pocket_p1_transfer_top")
    ta = curves.t_of_point(arc, p1)
    tb = curves.t_of_point(arc, p1t)
    assert arc.point_at(ta).distance_to(p1) < 1e-3
    assert arc.point_at(tb).distance_to(p1t) < 1e-3
    mouth = curves.bezier_subrange(arc, ta, tb).length()
    assert spec.l_front == pytest.approx(arc.length() - mouth, abs=1e-3)
    assert spec.bottom_arc.length() == pytest.approx(spec.l_half, abs=0.03)


def test_curved_two_back_darts_builds():
    """双后省（共轭复合闭口）：构建成功、8 边闭合、弧圆顺。"""
    o = PatternOptions(back_dart=True, back_dart_count=2,
                       back_dart_width=(1.5, 1.5), **_CURVED)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, local = build_waistband(ctx)
    assert len(piece.net_edges) == 8
    arc = local.sheet.get("wb.bottom_right").geom
    assert max(_tangent_steps(arc)) < 5.0


# ---------- 刀口（§四.2 v0.4：后中净样位 + 四角缝边交点位）----------

def test_notches_net_positions(ctx_darts):
    """净样刀口 5 点：后中 O + 左右两端下/上顶点（有省不打省位/侧缝刀口）。"""
    piece, local = build_waistband(ctx_darts)
    _assert_point_approx(local.point("wb.notch_back_center"), Point(0, 0))
    bot = local.sheet.get("wb.bottom_right").geom
    front = _end(bot)
    _assert_point_approx(local.point("wb.notch_right_bottom"), front)
    top = local.sheet.get("wb.top_right").geom
    _assert_point_approx(local.point("wb.notch_right_top"),
                         _end(top, start=True))
    _assert_point_approx(local.point("wb.notch_left_bottom"),
                         local.sheet.get("wb.bottom_fly").geom.a)
    _assert_point_approx(local.point("wb.notch_left_top"),
                         local.sheet.get("wb.left_end").geom.a)
    assert len(piece.notches) == 5
    for gone in ("wb.notch_side", "wb.notch_back_dart1", "wb.notch_front_dart"):
        assert gone not in local.sheet


def test_notches_gross_at_sa_crossings(ctx_darts):
    """直腰头毛样刀口 5 点全在缝边交点上（净线延长线 ∩ 缝边线，§四.2 v0.4）。

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
    _assert_point_approx(gn[0], Point(0, sa.bottom))
    _assert_point_approx(gn[1], Point(l, sa.bottom))
    _assert_point_approx(gn[2], Point(l + sa.right_end, -W))
    _assert_point_approx(gn[3], Point(-(l + fly) - sa.left_end, -W))
    _assert_point_approx(gn[4], Point(-(l + fly), sa.bottom))


def test_notches_curved_gross_on_sa_lines(ctx_curved):
    """弯腰头毛样刀口：交点在对应缝边线上（距净边=缝份）且在净线延长线上。"""
    piece, local = build_waistband(ctx_curved)
    sa = ctx_curved.options.waistband_seam_allowances
    gn = piece.gross_notches
    assert len(gn) == 5
    right_end = local.line("wb.right_end")
    left_end = local.line("wb.left_end")
    bf = local.sheet.get("wb.bottom_fly").geom
    tf = local.sheet.get("wb.top_fly").geom
    br = local.sheet.get("wb.bottom_right").geom   # 拟合弧（原点、起切向 X̂）
    tr = local.sheet.get("wb.top_right").geom
    assert gn[0].x == pytest.approx(0.0, abs=1e-6)
    assert _line_dist(gn[0], br.p0, br.p0 + br.tangent_at(0.0)) == pytest.approx(
        sa.bottom, abs=1e-6)
    assert _line_dist(gn[1], right_end.a, right_end.b) == pytest.approx(0.0, abs=1e-6)
    assert _line_dist(gn[1], br.p3, br.p3 + br.tangent_at(1.0)) == pytest.approx(
        sa.bottom, abs=1e-6)
    assert _line_dist(gn[2], right_end.a, right_end.b) == pytest.approx(
        sa.right_end, abs=1e-6)
    assert _line_dist(gn[2], tr.p0, tr.p0 + tr.tangent_at(0.0)) == pytest.approx(
        0.0, abs=1e-6)
    assert _line_dist(gn[3], left_end.a, left_end.b) == pytest.approx(
        sa.left_end, abs=1e-6)
    assert _line_dist(gn[3], tf.a, tf.b) == pytest.approx(0.0, abs=1e-6)
    assert _line_dist(gn[4], left_end.a, left_end.b) == pytest.approx(0.0, abs=1e-6)
    assert _line_dist(gn[4], bf.a, bf.b) == pytest.approx(sa.bottom, abs=1e-6)


# ---------- 缩水（§五.2）----------

def test_shrinkage_scales_geometry(ctx):
    """缩水：按 waistband_grain 把经/纬率映射到 X/Y 轴（默认 WIDTH：X=纬、Y=经）。"""
    o = PatternOptions(delta=1.0, shrinkage_warp=0.03, shrinkage_weft=0.02)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, _ = build_waistband(ctx)
    assert o.waistband_grain is WaistbandGrain.WIDTH
    sx, sy = 1 / 0.98, 1 / 0.97
    n0 = piece.net_edges[1].geom
    s0 = piece.shrunk_edges[1].geom
    nb = _end(n0)
    sb = _end(s0)
    assert sb.x == pytest.approx(nb.x * sx)
    assert sb.y == pytest.approx(nb.y * sy)
    for n, s in zip(piece.notches, piece.shrunk_notches):
        assert s.x == pytest.approx(n.x * sx)
        assert s.y == pytest.approx(n.y * sy)


def test_shrinkage_length_grain_swaps_axes():
    """LENGTH（长向=经）：X 吃 warp、Y 吃 weft（与默认 WIDTH 相反）。"""
    o = PatternOptions(delta=1.0, waistband_grain=WaistbandGrain.LENGTH,
                       shrinkage_warp=0.03, shrinkage_weft=0.02)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, _ = build_waistband(ctx)
    sx, sy = 1 / 0.97, 1 / 0.98
    n0 = piece.net_edges[1].geom
    s0 = piece.shrunk_edges[1].geom
    nb = _end(n0)
    sb = _end(s0)
    assert sb.x == pytest.approx(nb.x * sx)
    assert sb.y == pytest.approx(nb.y * sy)


def test_grain_orientation():
    """丝缕线方向随 waistband_grain：WIDTH 竖向（沿裤长）、LENGTH 水平（沿周向）。"""
    o = PatternOptions(delta=1.0)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    _, local = build_waistband(ctx)
    g = local.line("wb.grain")
    assert g.a.x == pytest.approx(g.b.x)
    assert g.a.y != pytest.approx(g.b.y)
    o2 = PatternOptions(delta=1.0, waistband_grain=WaistbandGrain.LENGTH)
    ctx2 = FlowRunner(M, o2).run(FULL_FLOW)
    _, local2 = build_waistband(ctx2)
    g2 = local2.line("wb.grain")
    assert g2.a.y == pytest.approx(g2.b.y)
    assert g2.a.x != pytest.approx(g2.b.x)


def test_no_shrinkage_shrunk_equals_net(ctx):
    """无缩水：shrunk 边 == net 边。"""
    piece, _ = build_waistband(ctx)
    assert piece.shrunk_edges
    for n, s in zip(piece.net_edges, piece.shrunk_edges):
        _assert_point_approx(_end(n.geom), _end(s.geom))


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
    assert min(xs) == pytest.approx(-(spec.l_half + fly + sa.left_end))
    assert max(xs) == pytest.approx(spec.l_half + sa.right_end)
    assert min(ys) == pytest.approx(-W - sa.top)
    assert max(ys) == pytest.approx(sa.bottom)


def test_seam_allowance_zero(ctx):
    """缝份全 0：gross 多边形 == 净样采样（重合）。"""
    sa = WaistbandSeamAllowances(top=0, bottom=0, left_end=0, right_end=0)
    piece_none, _ = build_waistband(ctx)
    piece_zero = add_seam_allowance(piece_none, sa)
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


def test_svg_curved_with_darts(ctx_curved_full):
    """弯腰头 + 双省：8 边 SVG 正常渲染。"""
    piece, _ = build_waistband(ctx_curved_full)
    svg = render_piece_svg(piece)
    assert svg.startswith("<svg")
    assert "notch" in svg


# ---------- 边界与降级 ----------

def test_options_validation():
    """缝份负数 / 缩水越界 raise。"""
    with pytest.raises(ValueError):
        PatternOptions(delta=1.0, shrinkage_warp=0.5)
    with pytest.raises(ValueError):
        PatternOptions(delta=1.0, waistband_seam_allowances=
                       WaistbandSeamAllowances(top=-1.0))


def test_curved_fly_zero_no_degenerate_edges():
    """fly_extension=0：不产生零长搭门边，裁片构建与缝边不抛错（zhitong 场景）。

    零长边无切线，旧版 cutter._offset_edge_points 对 (b-a).normalized() 抛
    「零向量无法归一化」；装配时滤除后 8 边去两条零长搭门边 = 6。
    """
    o = PatternOptions(waistband_fly_extension=0.0, **_CURVED)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, _ = build_waistband(ctx)
    assert all(edge_length(e.geom) > 1e-9 for e in piece.net_edges)
    assert len(piece.net_edges) == 6
    assert piece.gross_polygon
    assert len(piece.gross_polygon) >= 6


def test_from_dict_drop_shim_warns():
    """from_dict 一次性垫片：已删参数（v0.7 waistband_front_drop、
    v0.8 圆顺窗长）弹出并告警（不抛 TypeError）。"""
    import io
    import contextlib
    raw = {"delta": 1.0, "waistband_type": "curved",
           "waistband_front_drop": 2.5, "waistband_blend_cb": 4.0}
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        o = PatternOptions.from_dict(raw)
    assert o.waistband_type is WaistbandType.CURVED
    assert not hasattr(o, "waistband_front_drop")
    assert not hasattr(o, "waistband_blend_cb")
    assert "waistband_front_drop" in err.getvalue()
    assert "waistband_blend_cb" in err.getvalue()
