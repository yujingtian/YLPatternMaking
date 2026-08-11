"""前口袋袋贴（facing）步骤测试（前口袋绘制.md §三.3.(1)；打版流程.md 第 88 行）。

金标（H=96, Δ=1.0, outseam=102，直腰头扣腰头宽 4，腰线 y=98，臀围线 y=86，
      裤中线立裆点 x=13.9；前口袋默认 P1 距禈 8.5、P2 下落 7.5、吃省 ΔW=2.0、
      袋贴宽 w_waist=3.5、默认侧缝深 w_side=w_waist=3.5；腰弧总长 ≈17.53、外缝弧总长 ≈12.85）：
  袋贴腰头顶点 P_fw：有省自 P1′、无省自 P1，沿腰弧朝前浪顶点量取 w_waist；
  袋贴侧缝顶点 P_fs：自 P2 沿外缝弧向下量取 w_side；
  闭合边弧长：腰弧 [O->P_fw] = p1_dist + dw + w_waist，外缝弧 [P_fs->O] = p2_drop + w_side；
  袋贴内边 L_inner：
    - tangent 模式（推荐）：CubicBezier(P_fw, P_fw + t_w·h1, P_fs + t_s·h2, P_fs)，
      两端切线严格垂直于腰弧与外缝弧；
    - offset 模式：内部控制点法向偏置，端点锁 P_fw/P_fs；
    - bulge 模式：过 P_fw、P_fs 的浅弧。
"""

import pytest

from ylpattern.draft import curves
from ylpattern.flows.front_flow import FRONT_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.params import Measurements, PatternOptions, WaistbandType

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
# 默认采用打版师推荐的 tangent 模式进行全流程测试
O = PatternOptions(
    delta=1.0,
    front_pocket=True,
    front_pocket_facing=True,
    front_pocket_facing_mode="tangent",
    front_pocket_facing_width=3.5,
    front_pocket_facing_side_w=6.0,
    front_pocket_facing_h1=5.0,
    front_pocket_facing_h2=4.0,
)


@pytest.fixture()
def ctx():
    return FlowRunner(M, O).run(FRONT_FLOW)


def _arc_length_between(curve, ta, tb, n=512) -> float:
    """细采样折线近似曲线 [ta, tb] 段的弧长（数值金标用）。"""
    pts = [curve.point_at(ta + (tb - ta) * i / n) for i in range(n + 1)]
    return sum(pts[i].distance_to(pts[i + 1]) for i in range(n))


def _interior_normal(curve, t, interior):
    """曲线 t 处朝裤身内部（crease_point）的单位法向。"""
    n = curve.tangent_at(t).perpendicular()
    a = curve.point_at(t)
    if n.dx * (interior.x - a.x) + n.dy * (interior.y - a.y) < 0:
        n = n.scale(-1)
    return n


def test_facing_waist_vertex_along_waist_arc(ctx):
    # P_fw：有省自 P1′ 沿腰弧朝前浪顶点量取 w_waist
    w_arc = ctx.curve("front.waistline_arc")
    p1r = ctx.point("front.pocket_p1_transfer")
    p_fw = ctx.point("front.pocket_facing_waist")
    t_fw = w_arc.t_at_y(p_fw.y)
    assert w_arc.point_at(t_fw).distance_to(p_fw) < 1e-6
    t1r = w_arc.t_at_y(p1r.y)
    assert _arc_length_between(w_arc, t1r, t_fw) == pytest.approx(
        O.front_pocket_facing_width, abs=1e-2)
    assert p_fw.x > p1r.x                      # 朝前浪顶点侧


def test_facing_side_vertex_independent_width(ctx):
    # P_fs：自 P2 沿外缝弧向下量取独立侧缝深度 w_side = 6.0
    s_arc = ctx.curve("front.outseam_arc")
    p2 = ctx.point("front.pocket_p2")
    p_fs = ctx.point("front.pocket_facing_side")
    t_fs = s_arc.t_at_y(p_fs.y)
    assert s_arc.point_at(t_fs).distance_to(p_fs) < 1e-6
    t2 = s_arc.t_at_y(p2.y)
    assert _arc_length_between(s_arc, t_fs, t2) == pytest.approx(
        O.front_pocket_facing_side_w, abs=1e-2)
    assert p_fs.y < p2.y                        # 低于 P2（向下）


def test_facing_tangent_mode_orthogonal(ctx):
    # tangent 模式：内边在两端与腰弧、外缝弧严格正交（切线点积 dot ≈ 0）
    inner = ctx.curve("front.pocket_facing_inner")
    w_arc = ctx.curve("front.waistline_arc")
    s_arc = ctx.curve("front.outseam_arc")
    p_fw = ctx.point("front.pocket_facing_waist")
    p_fs = ctx.point("front.pocket_facing_side")

    assert inner.p0 == p_fw
    assert inner.p3 == p_fs

    # 1. 腰头端正交性验证
    t_inner_start = inner.tangent_at(0.0).normalized()
    t_w = w_arc.tangent_at(w_arc.t_at_y(p_fw.y)).normalized()
    dot_waist = t_inner_start.dx * t_w.dx + t_inner_start.dy * t_w.dy
    assert dot_waist == pytest.approx(0.0, abs=1e-5)

    # 2. 侧缝端正交性验证
    t_inner_end = inner.tangent_at(1.0).normalized()
    t_s = s_arc.tangent_at(s_arc.t_at_y(p_fs.y)).normalized()
    dot_side = t_inner_end.dx * t_s.dx + t_inner_end.dy * t_s.dy
    assert dot_side == pytest.approx(0.0, abs=1e-5)


def test_facing_closure_edges(ctx):
    b = ctx.point("front.waist_side_point")
    p_fw = ctx.point("front.pocket_facing_waist")
    p_fs = ctx.point("front.pocket_facing_side")

    # 腰弧 [O->P_fw]：弧长 = p1_dist + dw + w_waist
    waist_edge = ctx.curve("front.pocket_facing_waist_edge")
    assert waist_edge.point_at(0).distance_to(b) < 1e-6
    assert waist_edge.point_at(1).distance_to(p_fw) < 1e-6
    assert waist_edge.length() == pytest.approx(
        O.front_pocket_p1_dist + O.front_pocket_dart_width
        + O.front_pocket_facing_width, abs=1e-2)

    # 外缝弧 [P_fs->O]：弧长 = p2_drop + w_side (6.0)
    outseam_edge = ctx.curve("front.pocket_facing_outseam_edge")
    assert outseam_edge.point_at(0).distance_to(p_fs) < 1e-6
    assert outseam_edge.point_at(1).distance_to(b) < 1e-6
    assert outseam_edge.length() == pytest.approx(
        O.front_pocket_p2_drop + O.front_pocket_facing_side_w, abs=1e-2)


def test_facing_offset_mode_fallback():
    # offset 模式兼容性测试：控制点域法向偏置
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       front_pocket_facing_mode="offset",
                       front_pocket_facing_width=3.5)
    ctx_offset = FlowRunner(M, o).run(FRONT_FLOW)
    cref = ctx_offset.curve("front.pocket_mouth")
    inner = ctx_offset.curve("front.pocket_facing_inner")
    crease = ctx_offset.point("front.crease_point")
    w = o.front_pocket_facing_width

    assert inner.p0 == ctx_offset.point("front.pocket_facing_waist")
    assert inner.p3 == ctx_offset.point("front.pocket_facing_side")
    assert inner.p1.distance_to(
        cref.p1 + _interior_normal(cref, 1 / 3, crease).scale(w)) < 1e-9
    assert inner.p2.distance_to(
        cref.p2 + _interior_normal(cref, 2 / 3, crease).scale(w)) < 1e-9


def test_facing_bulge_mode():
    # bulge 模式测试
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       front_pocket_facing_mode="bulge",
                       front_pocket_facing_bulge=1.5,
                       front_pocket_facing_bulge_at=0.6)
    ctx_bulge = FlowRunner(M, o).run(FRONT_FLOW)
    p_fw = ctx_bulge.point("front.pocket_facing_waist")
    p_fs = ctx_bulge.point("front.pocket_facing_side")
    inner = ctx_bulge.curve("front.pocket_facing_inner")

    assert inner.p0 == p_fw
    assert inner.p3 == p_fs


def test_facing_no_dart_uses_p1():
    # 无省：P_fw 自 P1 量取
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       front_pocket_facing_mode="tangent",
                       front_pocket_dart_width=0.0)
    ctx_nodart = FlowRunner(M, o).run(FRONT_FLOW)
    assert "front.pocket_p1_transfer" not in ctx_nodart.sheet
    w_arc = ctx_nodart.curve("front.waistline_arc")
    p1 = ctx_nodart.point("front.pocket_p1")
    p_fw = ctx_nodart.point("front.pocket_facing_waist")
    t1 = w_arc.t_at_y(p1.y)
    t_fw = w_arc.t_at_y(p_fw.y)
    assert _arc_length_between(w_arc, t1, t_fw) == pytest.approx(
        o.front_pocket_facing_width, abs=1e-2)


def test_facing_polyline_mode():
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       front_pocket_mouth_mode="polyline",
                       front_pocket_mouth_corners=[(0.4, 1.2), (0.7, 0.8)])
    ctx_poly = FlowRunner(M, o).run(FRONT_FLOW)
    p_fw = ctx_poly.point("front.pocket_facing_waist")
    p_fs = ctx_poly.point("front.pocket_facing_side")
    assert ctx_poly.line("front.pocket_facing_inner_seg1").a == p_fw
    assert ctx_poly.line("front.pocket_facing_inner_seg3").b == p_fs


def test_facing_curved_waistband():
    # 弯腰头：锚点相对下腰头线
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       front_pocket_facing_mode="tangent",
                       waistband_type=WaistbandType.CURVED)
    ctx_curved = FlowRunner(M, o).run(FRONT_FLOW)
    b_sub = ctx_curved.point("front.lower_waist_side_point")
    assert ctx_curved.curve("front.pocket_facing_waist_edge").point_at(0).distance_to(b_sub) < 1e-6


def test_facing_skipped_by_default():
    ctx_skip = FlowRunner(M, PatternOptions(delta=1.0, front_pocket=True)).run(FRONT_FLOW)
    assert "front.pocket_facing_inner" not in ctx_skip.sheet


def test_facing_requires_pocket():
    o = PatternOptions(delta=1.0, front_pocket_facing=True)
    with pytest.raises(ValueError, match="依赖前口袋主切口"):
        FlowRunner(M, o).run(FRONT_FLOW)


def test_facing_options_validation():
    with pytest.raises(ValueError, match="袋贴腰头宽"):
        PatternOptions(front_pocket_facing_width=0.0)
    with pytest.raises(ValueError, match="袋贴腰头宽"):
        PatternOptions(front_pocket_facing_width=11.0)
    with pytest.raises(ValueError, match="袋贴侧缝端深度"):
        PatternOptions(front_pocket_facing_side_w=-1.0)
    with pytest.raises(ValueError, match="袋贴内边模式"):
        PatternOptions(front_pocket_facing_mode="unknown_mode")
    with pytest.raises(ValueError, match="front_pocket_facing_h1"):
        PatternOptions(front_pocket_facing_h1=0.0)
    with pytest.raises(ValueError, match="袋贴内边弧高绝对值"):
        PatternOptions(front_pocket_facing_bulge=15.0)
    with pytest.raises(ValueError, match="袋贴内边弧顶位置"):
        PatternOptions(front_pocket_facing_bulge_at=1.2)


def test_facing_side_beyond_outseam_raises():
    # 独立侧缝深 6.0 越界测试
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       front_pocket_p2_drop=7.5,
                       front_pocket_facing_side_w=6.0)
    with pytest.raises(ValueError, match="越出外缝弧"):
        FlowRunner(M, o).run(FRONT_FLOW)