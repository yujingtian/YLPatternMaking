"""前口袋袋贴（facing）步骤测试（前口袋绘制.md §三.3.(1)；打版流程.md 第 88 行）。

金标（H=96, Δ=1.0, outseam=102，直腰头扣腰头宽 4，腰线 y=98，臀围线 y=86，
      裤中线立裆点 x=13.9；前口袋默认 P1 距禈 8.5、P2 下落 7.5、吃省 ΔW=2.0、
      袋贴宽 w_facing=3.5；腰弧总长 ≈17.53、外缝弧总长 ≈12.85）：
  袋贴腰头顶点 P_fw：有省自 P1′、无省自 P1，沿腰弧朝前浪顶点量取 w_facing；
  袋贴侧缝顶点 P_fs：自 P2 沿外缝弧向下量取 w_facing（等距 d_side=w_facing）；
  闭合边弧长：腰弧 [O->P_fw] = p1_dist+dw+w_facing，外缝弧 [P_fs->O] = p2_drop+w_facing；
  袋贴内边 L_inner：CubicBezier(P_fw, cref.p1+w·N(1/3), cref.p2+w·N(2/3), P_fs)--
    基准 C_ref（有省=切削线 C_cut、无省=净线 C）内部控制点法向偏置 w_facing，
    端点锁 P_fw/P_fs（在腰弧/外缝弧上，自然偏置端点不在弧上故锁，闭合拓扑要求）。
  N(t) = tangent_at(t).perpendicular() 朝裤身内部（crease_point）翻向。
"""

import pytest

from ylpattern.draft import curves
from ylpattern.flows.front_flow import FRONT_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.params import Measurements, PatternOptions, WaistbandType

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
O = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True)


@pytest.fixture()
def ctx():
    return FlowRunner(M, O).run(FRONT_FLOW)


def _arc_length_between(curve, ta, tb, n=512) -> float:
    """细采样折线近似曲线 [ta, tb] 段的弧长（数值金标用）。"""
    pts = [curve.point_at(ta + (tb - ta) * i / n) for i in range(n + 1)]
    return sum(pts[i].distance_to(pts[i + 1]) for i in range(n))


def _interior_normal(curve, t, interior):
    """曲线 t 处朝裤身内部（crease_point）的单位法向（同步骤 _facing_interior_normal）。"""
    n = curve.tangent_at(t).perpendicular()
    a = curve.point_at(t)
    if n.dx * (interior.x - a.x) + n.dy * (interior.y - a.y) < 0:
        n = n.scale(-1)
    return n


def test_facing_waist_vertex_along_waist_arc(ctx):
    # P_fw：有省自 P1′ 沿腰弧朝前浪顶点量取 w_facing
    w_arc = ctx.curve("front.waistline_arc")
    p1r = ctx.point("front.pocket_p1_transfer")
    p_fw = ctx.point("front.pocket_facing_waist")
    t_fw = w_arc.t_at_y(p_fw.y)
    assert w_arc.point_at(t_fw).distance_to(p_fw) < 1e-6
    t1r = w_arc.t_at_y(p1r.y)
    assert _arc_length_between(w_arc, t1r, t_fw) == pytest.approx(
        O.front_pocket_facing_width, abs=1e-2)
    assert p_fw.x > p1r.x                      # 朝前浪顶点侧


def test_facing_side_vertex_along_outseam_arc(ctx):
    # P_fs：自 P2 沿外缝弧向下量取 w_facing（等距约束 d_side=w_facing）
    s_arc = ctx.curve("front.outseam_arc")
    p2 = ctx.point("front.pocket_p2")
    p_fs = ctx.point("front.pocket_facing_side")
    t_fs = s_arc.t_at_y(p_fs.y)
    assert s_arc.point_at(t_fs).distance_to(p_fs) < 1e-6
    t2 = s_arc.t_at_y(p2.y)
    assert _arc_length_between(s_arc, t_fs, t2) == pytest.approx(
        O.front_pocket_facing_width, abs=1e-2)
    assert p_fs.y < p2.y                        # 低于 P2（向下）


def test_facing_inner_construction(ctx):
    # L_inner = CubicBezier(P_fw, cref.p1+w·N(1/3), cref.p2+w·N(2/3), P_fs)
    # 基准 C_ref：有省 = 切削线 front.pocket_mouth
    cref = ctx.curve("front.pocket_mouth")
    inner = ctx.curve("front.pocket_facing_inner")
    crease = ctx.point("front.crease_point")
    w = O.front_pocket_facing_width
    assert inner.p0 == ctx.point("front.pocket_facing_waist")
    assert inner.p3 == ctx.point("front.pocket_facing_side")
    assert inner.p1.distance_to(
        cref.p1 + _interior_normal(cref, 1 / 3, crease).scale(w)) < 1e-9
    assert inner.p2.distance_to(
        cref.p2 + _interior_normal(cref, 2 / 3, crease).scale(w)) < 1e-9


def test_facing_inner_interior_side(ctx):
    # 内边在裤身内部侧：各采样点比基准 C_ref 同参数点更靠近 crease_point
    cref = ctx.curve("front.pocket_mouth")
    inner = ctx.curve("front.pocket_facing_inner")
    crease = ctx.point("front.crease_point")
    w = O.front_pocket_facing_width
    for t in (0.2, 0.5, 0.8):
        qi, cm = inner.point_at(t), cref.point_at(t)
        assert qi.distance_to(crease) < cm.distance_to(crease)
        # 法向偏置距离近似 w_facing（控制点域近似 + 端点锁定，容差放宽）
        foot = curves.foot_on_bezier(cref, qi)
        assert w * 0.6 < qi.distance_to(foot) < w * 1.2


def test_facing_closure_edges(ctx):
    b = ctx.point("front.waist_side_point")
    p_fw = ctx.point("front.pocket_facing_waist")
    p_fs = ctx.point("front.pocket_facing_side")
    # 腰弧 [O->P_fw]：弧长 = p1_dist + dw + w_facing
    waist_edge = ctx.curve("front.pocket_facing_waist_edge")
    assert waist_edge.point_at(0).distance_to(b) < 1e-6
    assert waist_edge.point_at(1).distance_to(p_fw) < 1e-6
    assert waist_edge.length() == pytest.approx(
        O.front_pocket_p1_dist + O.front_pocket_dart_width
        + O.front_pocket_facing_width, abs=1e-2)
    # 外缝弧 [P_fs->O]：弧长 = p2_drop + w_facing
    outseam_edge = ctx.curve("front.pocket_facing_outseam_edge")
    assert outseam_edge.point_at(0).distance_to(p_fs) < 1e-6
    assert outseam_edge.point_at(1).distance_to(b) < 1e-6
    assert outseam_edge.length() == pytest.approx(
        O.front_pocket_p2_drop + O.front_pocket_facing_width, abs=1e-2)


def test_facing_no_dart_uses_p1_and_net_curve():
    # 无省：P_fw 自 P1 量取（无 P1′）；腰弧边弧长 = p1_dist + w_facing
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       front_pocket_dart_width=0.0)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    assert "front.pocket_p1_transfer" not in ctx.sheet
    w_arc = ctx.curve("front.waistline_arc")
    p1 = ctx.point("front.pocket_p1")
    p_fw = ctx.point("front.pocket_facing_waist")
    t1 = w_arc.t_at_y(p1.y)
    t_fw = w_arc.t_at_y(p_fw.y)
    assert _arc_length_between(w_arc, t1, t_fw) == pytest.approx(
        o.front_pocket_facing_width, abs=1e-2)
    assert ctx.curve("front.pocket_facing_waist_edge").length() == pytest.approx(
        o.front_pocket_p1_dist + o.front_pocket_facing_width, abs=1e-2)
    # 基准 C_ref = 净线 front.pocket_mouth_baseline（无省切削线 = 净线，二者重合）
    cref = ctx.curve("front.pocket_mouth_baseline")
    inner = ctx.curve("front.pocket_facing_inner")
    crease = ctx.point("front.crease_point")
    w = o.front_pocket_facing_width
    assert inner.p1.distance_to(
        cref.p1 + _interior_normal(cref, 1 / 3, crease).scale(w)) < 1e-9


def test_facing_polyline_mode():
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       front_pocket_mouth_mode="polyline",
                       front_pocket_mouth_corners=[(0.4, 1.2), (0.7, 0.8)])
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    p_fw = ctx.point("front.pocket_facing_waist")
    p_fs = ctx.point("front.pocket_facing_side")
    # 基准切削折角链：P1′ -> K1′ -> K2′ -> P2（front.pocket_mouth_seg1..3）
    segs = []
    i = 1
    while f"front.pocket_mouth_seg{i}" in ctx.sheet:
        segs.append(ctx.line(f"front.pocket_mouth_seg{i}"))
        i += 1
    verts = [segs[0].a] + [s.b for s in segs]
    # 弦法向 n（向内侧）
    crease = ctx.point("front.crease_point")
    n = (verts[-1] - verts[0]).normalized().perpendicular()
    if n.dx * (crease.x - verts[0].x) + n.dy * (crease.y - verts[0].y) < 0:
        n = n.scale(-1)
    w = o.front_pocket_facing_width
    # 内边折角链：端点锁 P_fw/P_fs，折角顶点沿 n 平移 w，逐段直线
    assert "front.pocket_facing_inner_seg1" in ctx.sheet
    assert "front.pocket_facing_inner_seg3" in ctx.sheet
    assert "front.pocket_facing_inner_seg4" not in ctx.sheet
    assert ctx.line("front.pocket_facing_inner_seg1").a == p_fw
    assert ctx.line("front.pocket_facing_inner_seg1").b.distance_to(
        verts[1] + n.scale(w)) < 1e-9
    assert ctx.line("front.pocket_facing_inner_seg3").b == p_fs
    for i in (1, 2, 3):
        assert ctx.sheet.get(f"front.pocket_facing_inner_seg{i}").role == "struct"


def test_facing_curved_waistband():
    # 弯腰头：锚点相对下腰头线（下侧缝腰点 B'），经 effective_waist
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    lw_arc = ctx.curve("front.lower_waistline_arc")
    b_sub = ctx.point("front.lower_waist_side_point")
    p1r = ctx.point("front.pocket_p1_transfer")
    p_fw = ctx.point("front.pocket_facing_waist")
    t_fw = lw_arc.t_at_y(p_fw.y)
    assert lw_arc.point_at(t_fw).distance_to(p_fw) < 1e-6
    t1r = lw_arc.t_at_y(p1r.y)
    assert _arc_length_between(lw_arc, t1r, t_fw) == pytest.approx(
        o.front_pocket_facing_width, abs=1e-2)
    # 腰侧边界上端 = B'（下腰头线侧，非腰外缝顶点 B）
    assert ctx.curve("front.pocket_facing_waist_edge").point_at(0).distance_to(b_sub) < 1e-6


def test_facing_skipped_by_default():
    ctx = FlowRunner(M, PatternOptions(delta=1.0, front_pocket=True)).run(FRONT_FLOW)
    assert "front.pocket_facing_inner" not in ctx.sheet
    assert "front.pocket_facing_waist" not in ctx.sheet


def test_facing_requires_pocket():
    o = PatternOptions(delta=1.0, front_pocket_facing=True)
    with pytest.raises(ValueError, match="依赖前口袋主切口"):
        FlowRunner(M, o).run(FRONT_FLOW)


def test_facing_options_validation():
    with pytest.raises(ValueError, match="袋贴宽"):
        PatternOptions(front_pocket_facing_width=0.0)
    with pytest.raises(ValueError, match="袋贴宽"):
        PatternOptions(front_pocket_facing_width=11.0)


def test_facing_waist_beyond_arc_raises():
    # P1 距禈 + 吃省 + 袋贴宽 ≥ 腰弧总长（17.53）-> P_fw 越出腰弧
    # （p1_dist+dw=10.5 < 17.53，口袋步骤通过；袋贴 w=8 -> s_fw=18.5 越出）
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       front_pocket_facing_width=8.0)
    with pytest.raises(ValueError, match="超过腰弧总长"):
        FlowRunner(M, o).run(FRONT_FLOW)


def test_facing_side_beyond_outseam_raises():
    # P2 深度 7.5 − 袋贴宽 6 ≤ 0 -> P_fs 越出外缝弧臀围端
    # （s_fw=10.5+6=16.5 < 17.53 腰弧通过；s_fs=5.35−6<0 外缝越出）
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       front_pocket_facing_width=6.0)
    with pytest.raises(ValueError, match="越出外缝弧"):
        FlowRunner(M, o).run(FRONT_FLOW)
