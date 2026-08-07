"""前口袋（挖削嵌入式主切口）步骤测试（前口袋绘制.md §二、§三.1~§三.2）。

金标（H=96, Δ=1.0, outseam=102，直裆深 = H/4 = 24，直腰头扣腰头宽 4，
      腰线 y=98，臀围线 y=86，裤中线 x=13.9）：
  锚点为沿弧量取（弧长由贝塞尔几何决定，无法手工闭式演算），
  以细采样折线做数值金标：P1 沿腰弧自腰外缝顶点（O）量取 8.5，
  P2 沿外缝弧自腰外缝顶点向下量取 7.5。
  共线渐变撇削（§三.1）：省顶点 P1′ = P1 沿腰弧朝前浪顶点量取 ΔW = 2.0
  （落在腰头线上，不内折），撇削向量 V = P1′ − P1 沿腰头线方向；
  切削线 C_cut(t) = C(t) + V·(1−t)ⁿ（n = 2.0）—— 金标：
    C_cut(0) = P1′ 在腰弧上，弧长 P1′→P1 = 2.0；
    C_cut(1) = P2 严格重合；
    控制点偏置向量 = V×(2/3)²、V×(1/3)²。
"""

import pytest

from ylpattern.draft import curves
from ylpattern.flows.front_flow import FRONT_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.params import Measurements, PatternOptions

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
O = PatternOptions(delta=1.0, front_pocket=True)


@pytest.fixture()
def ctx():
    return FlowRunner(M, O).run(FRONT_FLOW)


def _arc_length_between(curve, ta, tb, n=512) -> float:
    """细采样折线近似曲线 [ta, tb] 段的弧长（数值金标用）。"""
    pts = [curve.point_at(ta + (tb - ta) * i / n) for i in range(n + 1)]
    return sum(pts[i].distance_to(pts[i + 1]) for i in range(n))


def test_pocket_p1_along_waist_arc(ctx):
    w_arc = ctx.curve("front.waistline_arc")
    p1 = ctx.point("front.pocket_p1")
    # 独立定位：腰弧 y 随 t 单调，按 y 反查 P1 的参数 t*（不沿弧采样逼近）
    ts = w_arc.t_at_y(p1.y)
    assert w_arc.point_at(ts).distance_to(p1) < 1e-6
    # 沿弧自腰外缝顶点（t=0 端，O）量取 = 8.5（细采样数值金标）
    assert _arc_length_between(w_arc, 0.0, ts) == pytest.approx(
        O.front_pocket_p1_dist, abs=1e-2)
    # P1 介于腰外缝顶点 B 与前浪顶点之间
    b = ctx.point("front.waist_side_point")
    a = ctx.point("front.rise_top_point")
    assert b.x < p1.x < a.x


def test_pocket_p2_along_outseam_arc(ctx):
    s_arc = ctx.curve("front.outseam_arc")
    p2 = ctx.point("front.pocket_p2")
    # 外缝弧 y 随 t 单调，按 y 反查 P2 的参数 t*
    ts = s_arc.t_at_y(p2.y)
    assert s_arc.point_at(ts).distance_to(p2) < 1e-6
    # 沿弧到腰外缝顶点（t=1 端）的弧长 = 7.5
    assert _arc_length_between(s_arc, ts, 1.0) == pytest.approx(
        O.front_pocket_p2_drop, abs=1e-2)
    # P2 低于腰外缝顶点
    assert p2.y < ctx.point("front.waist_side_point").y


def test_pocket_design_baseline(ctx):
    # 设计净线 = P1→P2 浅弧（净线袋布贴对位线）
    design = ctx.curve("front.pocket_mouth_baseline")
    assert design.p0 == ctx.point("front.pocket_p1")
    assert design.p3 == ctx.point("front.pocket_p2")
    ref = curves.arc_through(ctx.point("front.pocket_p1"),
                             ctx.point("front.pocket_p2"),
                             bulge=O.front_pocket_mouth_bulge,
                             bulge_at=O.front_pocket_mouth_bulge_at)
    assert design.p1 == ref.p1
    assert design.p2 == ref.p2


def test_pocket_mouth_bulge_at_shifts_apex():
    # 弧顶位置 > 0.5：净线最大偏离点偏向侧缝端（t > 0.5）
    o = PatternOptions(delta=1.0, front_pocket=True,
                       front_pocket_mouth_bulge_at=0.7)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    design = ctx.curve("front.pocket_mouth_baseline")
    chord_a, chord_b = design.p0, design.p3
    ts = range(101)
    t_apex = max(ts, key=lambda i: design.point_at(i / 100).distance_to(
        chord_a.lerp(chord_b, i / 100))) / 100
    assert t_apex > 0.5


def test_pocket_mouth_polyline_mode():
    # 折角式（带倒角折线）：多折角列表，Ki = 弦上 ui 处沿左手法向推进 di
    o = PatternOptions(delta=1.0, front_pocket=True,
                       front_pocket_mouth_mode="polyline",
                       front_pocket_mouth_corners=[(0.35, 1.2), (0.7, 0.8)])
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    p1 = ctx.point("front.pocket_p1")
    p2 = ctx.point("front.pocket_p2")
    p1r = ctx.point("front.pocket_p1_transfer")
    n = (p2 - p1).normalized().perpendicular()
    v = p1r - p1
    # 折角点手工演算（逐角）
    ks = []
    for i, (u, d) in enumerate(o.front_pocket_mouth_corners, 1):
        k = ctx.point(f"front.pocket_mouth_corner{i}")
        exp = p1.lerp(p2, u) + n.scale(d)
        assert k.x == pytest.approx(exp.x, abs=1e-9)
        assert k.y == pytest.approx(exp.y, abs=1e-9)
        ks.append(k)
    # 切削折角点：Ki′ = Ki + V·(1−ui)ⁿ
    krs = []
    for i, (u, _) in enumerate(o.front_pocket_mouth_corners, 1):
        kr = ctx.point(f"front.pocket_mouth_corner_cut{i}")
        exp = ks[i - 1] + v.scale((1 - u) ** o.front_pocket_paring_n)
        assert kr.x == pytest.approx(exp.x, abs=1e-9)
        assert kr.y == pytest.approx(exp.y, abs=1e-9)
        krs.append(kr)
    # 净线段链：P1 → K1 → K2 → P2；切削段链：P1′ → K1′ → K2′ → P2
    net_pts = [p1, *ks, p2]
    cut_pts = [p1r, *krs, p2]
    for i in range(3):
        seg = ctx.line(f"front.pocket_mouth_baseline_seg{i + 1}")
        assert (seg.a, seg.b) == (net_pts[i], net_pts[i + 1])
        cseg = ctx.line(f"front.pocket_mouth_seg{i + 1}")
        assert (cseg.a, cseg.b) == (cut_pts[i], cut_pts[i + 1])
        assert ctx.sheet.get(f"front.pocket_mouth_baseline_seg{i + 1}").role == "struct"
        assert ctx.sheet.get(f"front.pocket_mouth_seg{i + 1}").role == "struct"


def test_pocket_mouth_polyline_zero_depth_is_straight():
    # 折角深度全 0 = 直袋口：折角落在弦上
    o = PatternOptions(delta=1.0, front_pocket=True,
                       front_pocket_mouth_mode="polyline",
                       front_pocket_mouth_corners=[(0.35, 0.0), (0.7, 0.0)])
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    p1 = ctx.point("front.pocket_p1")
    p2 = ctx.point("front.pocket_p2")
    for i, (u, _) in enumerate(o.front_pocket_mouth_corners, 1):
        k = ctx.point(f"front.pocket_mouth_corner{i}")
        assert k.distance_to(p1.lerp(p2, u)) < 1e-9


def test_pocket_mouth_polyline_empty_is_straight():
    # 空折角列表 = 直袋口：净线/切削线各一段
    o = PatternOptions(delta=1.0, front_pocket=True,
                       front_pocket_mouth_mode="polyline",
                       front_pocket_mouth_corners=[])
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    seg = ctx.line("front.pocket_mouth_baseline_seg1")
    assert (seg.a, seg.b) == (ctx.point("front.pocket_p1"),
                              ctx.point("front.pocket_p2"))
    cseg = ctx.line("front.pocket_mouth_seg1")
    assert (cseg.a, cseg.b) == (ctx.point("front.pocket_p1_transfer"),
                                ctx.point("front.pocket_p2"))
    assert "front.pocket_mouth_baseline_seg2" not in ctx.sheet


def test_pocket_mouth_tangent_mode():
    # 两端垂直式：P1 端切线 ⟂ 腰弧切线、P2 端切线 ⟂ 外缝弧切线
    o = PatternOptions(delta=1.0, front_pocket=True,
                       front_pocket_mouth_mode="tangent",
                       front_pocket_mouth_h1=3.0, front_pocket_mouth_h2=4.0)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    design = ctx.curve("front.pocket_mouth_baseline")
    assert design.p0 == ctx.point("front.pocket_p1")
    assert design.p3 == ctx.point("front.pocket_p2")
    # 端点切线方向 = 柄向量（贝塞尔端点切线 = 3×(控制点 − 端点)）
    # 柄长校验：|tangent_at(0)| = 3×h1，|tangent_at(1)| = 3×h2
    assert design.tangent_at(0).length == pytest.approx(3 * 3.0)
    assert design.tangent_at(1).length == pytest.approx(3 * 4.0)
    # 垂直校验：与腰弧/外缝弧在锚点处的切线正交（锚点参数经 y 反查）
    w_arc = ctx.curve("front.waistline_arc")
    s_arc = ctx.curve("front.outseam_arc")
    t1 = w_arc.t_at_y(design.p0.y)
    t2 = s_arc.t_at_y(design.p3.y)
    tw = w_arc.tangent_at(t1)
    ts = s_arc.tangent_at(t2)
    t0 = design.tangent_at(0)
    t3 = design.tangent_at(1)
    assert (t0.dx * tw.dx + t0.dy * tw.dy) == pytest.approx(0.0, abs=1e-6)
    assert (t3.dx * ts.dx + t3.dy * ts.dy) == pytest.approx(0.0, abs=1e-6)
    # 行进方向：腰头端朝裤片内部向下扎入，侧缝端朝侧缝（−x）抵达
    # （控制柄取内向侧，端点行进切线 = −柄方向）
    assert t0.dy < 0
    assert t3.dx < 0


def test_pocket_cut_curve_dart_absorption(ctx):
    w_arc = ctx.curve("front.waistline_arc")
    design = ctx.curve("front.pocket_mouth_baseline")
    cut = ctx.curve("front.pocket_mouth")
    p1 = ctx.point("front.pocket_p1")
    p1r = ctx.point("front.pocket_p1_transfer")
    # 省顶点 P1′ = C_cut(0)，落在腰弧上（y 单调反查参数）
    assert cut.p0 == p1r
    tr = w_arc.t_at_y(p1r.y)
    assert w_arc.point_at(tr).distance_to(p1r) < 1e-6
    t1 = w_arc.t_at_y(p1.y)
    # 数值金标：腰弧上 P1→P1′ 的弧长 = 吃省 2.0（P1′ 在 P1 朝前浪顶点侧）
    assert _arc_length_between(w_arc, t1, tr) == pytest.approx(
        O.front_pocket_dart_width, abs=1e-2)
    # 沿腰头线朝前浪顶点方向（不内折）
    assert p1r.x > p1.x
    # 侧缝端严格重合（衰减至 0，不破坏侧缝数据）
    assert cut.p3 == design.p3 == ctx.point("front.pocket_p2")
    # 控制点偏置向量 = V×(1−t)ⁿ：V×(2/3)²、V×(1/3)²
    v = p1r - p1
    pw = O.front_pocket_paring_n
    for t_mid, cp in ((2 / 3, "p1"), (1 / 3, "p2")):
        off = getattr(cut, cp) - getattr(design, cp)
        exp = v.scale(t_mid ** pw)
        assert off.dx == pytest.approx(exp.dx, abs=1e-9)
        assert off.dy == pytest.approx(exp.dy, abs=1e-9)


def test_pocket_cut_start_edge(ctx):
    # 吃省撇削边 = P1 → P1′，沿腰头线，结构线
    p1 = ctx.point("front.pocket_p1")
    p1r = ctx.point("front.pocket_p1_transfer")
    edge = ctx.line("front.pocket_cut_start")
    assert (edge.a, edge.b) == (p1, p1r)
    assert ctx.sheet.get("front.pocket_cut_start").role == "struct"
    # 边长 ≈ 吃省量（弦长略小于弧长，腰弧近直，差 < 0.01）
    assert edge.length == pytest.approx(O.front_pocket_dart_width, abs=1e-2)


def test_pocket_cutout_boundary(ctx):
    b = ctx.point("front.waist_side_point")
    p1 = ctx.point("front.pocket_p1")
    p2 = ctx.point("front.pocket_p2")
    # 腰侧边界 = 腰弧 O→P1 子段，弧长 = P1 距禈 8.5
    waist_edge = ctx.curve("front.pocket_waist_edge")
    assert waist_edge.p0 == b
    assert waist_edge.p3.distance_to(p1) < 1e-9
    assert waist_edge.length() == pytest.approx(O.front_pocket_p1_dist,
                                                abs=1e-2)
    # 侧缝边界 = 外缝弧 P2→O 子段（与裁片外缝线重合）
    edge = ctx.curve("front.pocket_outseam_edge")
    assert edge.p3 == b
    assert edge.p0.distance_to(p2) < 1e-9
    # 子段弧长 = P2 沿弧深度 7.5（与外缝弧共线）
    assert edge.length() == pytest.approx(O.front_pocket_p2_drop, abs=1e-2)


def test_pocket_zero_dart_cut_equals_design():
    o = PatternOptions(delta=1.0, front_pocket=True,
                       front_pocket_dart_width=0.0)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    design = ctx.curve("front.pocket_mouth_baseline")
    cut = ctx.curve("front.pocket_mouth")
    # ΔW = 0：切削线与设计净线完全一致
    assert cut == design
    # 无吃省顶点与吃省边
    assert "front.pocket_p1_transfer" not in ctx.sheet
    assert "front.pocket_cut_start" not in ctx.sheet


def test_pocket_skipped_by_default():
    ctx = FlowRunner(M, PatternOptions(delta=1.0)).run(FRONT_FLOW)
    assert "front.pocket_mouth" not in ctx.sheet
    assert "front.pocket_p1" not in ctx.sheet


def test_pocket_options_validation():
    with pytest.raises(ValueError, match="P1 弧长距离必须为正数"):
        PatternOptions(front_pocket_p1_dist=0.0)
    with pytest.raises(ValueError, match="P2 弧长深度必须为正数"):
        PatternOptions(front_pocket_p2_drop=-1.0)
    with pytest.raises(ValueError, match="腰头吃省总宽"):
        PatternOptions(front_pocket_dart_width=7.0)
    with pytest.raises(ValueError, match="腰头吃省总宽"):
        PatternOptions(front_pocket_dart_width=-1.0)
    with pytest.raises(ValueError, match="撇削衰减幂指数"):
        PatternOptions(front_pocket_paring_n=0.5)
    with pytest.raises(ValueError, match="袋口母线弧高"):
        PatternOptions(front_pocket_mouth_bulge=6.0)
    with pytest.raises(ValueError, match="袋口弧顶位置"):
        PatternOptions(front_pocket_mouth_bulge_at=1.5)
    with pytest.raises(ValueError, match="袋口净线模式"):
        PatternOptions(front_pocket_mouth_mode="zipper")
    with pytest.raises(ValueError, match="切线柄长必须为正数"):
        PatternOptions(front_pocket_mouth_h1=0.0)
    with pytest.raises(ValueError, match="折角位置须按弦上比例严格递增"):
        PatternOptions(front_pocket_mouth_corners=[(0.7, 1.0), (0.35, 1.0)])
    with pytest.raises(ValueError, match="折角位置须在"):
        PatternOptions(front_pocket_mouth_corners=[(1.5, 1.0)])
    with pytest.raises(ValueError, match="折角内推深度"):
        PatternOptions(front_pocket_mouth_corners=[(0.5, -1.0)])


def test_pocket_anchor_beyond_arc_raises():
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_p1_dist=999.0)
    with pytest.raises(ValueError, match="超过腰弧总长"):
        FlowRunner(M, o).run(FRONT_FLOW)


def test_pocket_dart_beyond_waist_arc_raises():
    # P1 距禈 + 吃省量 ≥ 腰弧总长时 P1′ 越出腰弧段，抛错
    o = PatternOptions(delta=1.0, front_pocket=True,
                       front_pocket_p1_dist=16.0, front_pocket_dart_width=6.0)
    with pytest.raises(ValueError, match="之和超过腰弧总长"):
        FlowRunner(M, o).run(FRONT_FLOW)
