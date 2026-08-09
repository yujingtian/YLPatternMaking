"""袋布（pouch）步骤测试（袋布绘制.md §二、§三、§五）。

金标（H=96, Δ=1.0, outseam=102，直腰头扣腰头宽 4，腰线 y=98，
      腰外缝顶点 B ≈ (4.3606, 98)，front_pocket=True + front_pouch=True）：
  P_w0：腰弧上自 O 沿弧 8.5 + 4.0 = 12.5 处（数值金标，细采样弧长）；
  P_s0：y = P2.y − 8.0，低于臀围线 86 → 落在大腿外缝弧上；
  节点 K1 = B + (5.0, −16.0) = (9.3606, 82)，K2 = B + (1.5, −13.5) = (5.8606, 84.5)；
  大片节点链 3 段：line（P_w0→K1）、arc h=2.5/t=0.6（K1→K2）、line（K2→P_s0）；
  小片节点链与大片同节点同边形态，起点 = 袋口切削线起点 P1′，终点 = P2。
"""

import math

import pytest

from ylpattern.flows.front_flow import FRONT_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.geometry import CubicBezier
from ylpattern.params import Measurements, PatternOptions, WaistbandType

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
O = PatternOptions(delta=1.0, front_pocket=True, front_pouch=True)


@pytest.fixture()
def ctx():
    return FlowRunner(M, O).run(FRONT_FLOW)


def _arc_length_between(curve, ta, tb, n=512) -> float:
    pts = [curve.point_at(ta + (tb - ta) * i / n) for i in range(n + 1)]
    return sum(pts[i].distance_to(pts[i + 1]) for i in range(n))


def test_pouch_waist_anchor(ctx):
    w_arc = ctx.curve("front.waistline_arc")
    p_w0 = ctx.point("front.pouch_waist_anchor")
    # 在腰弧上（y 单调反查），自 O 沿弧 = P1 距禈 + 安全内延 = 12.5
    t = w_arc.t_at_y(p_w0.y)
    assert w_arc.point_at(t).distance_to(p_w0) < 1e-6
    assert _arc_length_between(w_arc, 0.0, t) == pytest.approx(
        O.front_pocket_p1_dist + O.front_pouch_waist_safe, abs=1e-2)
    # 越过 P1（朝门襟方向）
    assert p_w0.x > ctx.point("front.pocket_p1").x


def test_pouch_side_anchor(ctx):
    p2 = ctx.point("front.pocket_p2")
    p_s0 = ctx.point("front.pouch_side_anchor")
    # 自 P2 垂直下探 8.0
    assert p_s0.y == pytest.approx(p2.y - 8.0)
    # 低于臀围线 → 在大腿外缝弧上
    assert p_s0.y < ctx.line("front.hip_line").a.y
    upper = ctx.curve("front.outseam_upper")
    t = upper.t_at_y(p_s0.y)
    assert upper.point_at(t).distance_to(p_s0) < 1e-6


def test_pouch_nodes_global(ctx):
    # 节点 = O + (dx, −dy)：K1 ≈ (9.3606, 82)，K2 ≈ (5.8606, 84.5)
    b = ctx.point("front.waist_side_point")
    k1 = ctx.point("front.pouch_node1")
    k2 = ctx.point("front.pouch_node2")
    assert k1.x == pytest.approx(b.x + 5.0)
    assert k1.y == pytest.approx(b.y - 16.0)
    assert k2.x == pytest.approx(b.x + 1.5)
    assert k2.y == pytest.approx(b.y - 13.5)


def test_pouch_large_chain(ctx):
    p_w0 = ctx.point("front.pouch_waist_anchor")
    p_s0 = ctx.point("front.pouch_side_anchor")
    k1 = ctx.point("front.pouch_node1")
    k2 = ctx.point("front.pouch_node2")
    # 3 段：line / arc / line，端点依次衔接
    seg1 = ctx.line("front.pouch_large_seg1")
    assert (seg1.a, seg1.b) == (p_w0, k1)
    seg2 = ctx.curve("front.pouch_large_seg2")
    assert isinstance(seg2, CubicBezier)
    assert seg2.p0 == k1
    assert seg2.p3 == k2
    seg3 = ctx.line("front.pouch_large_seg3")
    assert (seg3.a, seg3.b) == (k2, p_s0)
    for name in ("front.pouch_large_seg1", "front.pouch_large_seg3"):
        assert ctx.sheet.get(name).role == "struct"
    # 固定边界：侧缝链（大腿外缝子段 + 外缝弧）+ 腰弧子段
    assert "front.pouch_side_edge_thigh" in ctx.sheet
    assert "front.pouch_side_edge_hip" in ctx.sheet
    # 大片侧缝链连续 P_s0 → 臀围外缝顶点 → B
    thigh_seg = ctx.curve("front.pouch_side_edge_thigh")
    assert thigh_seg.p0.distance_to(p_s0) < 1e-9
    hip_seg = ctx.curve("front.pouch_side_edge_hip")
    assert hip_seg.p3.distance_to(ctx.point("front.waist_side_point")) < 1e-9
    waist_edge = ctx.curve("front.pouch_large_waist_edge")
    assert waist_edge.p0 == ctx.point("front.waist_side_point")
    assert waist_edge.p3.distance_to(p_w0) < 1e-9


def test_pouch_small_chain(ctx):
    # 小片节点链与大片同锚点同节点（1:1 重合），不直连口袋顶点
    p_w0 = ctx.point("front.pouch_waist_anchor")
    p_s0 = ctx.point("front.pouch_side_anchor")
    p2 = ctx.point("front.pocket_p2")
    k1 = ctx.point("front.pouch_node1")
    k2 = ctx.point("front.pouch_node2")
    seg1 = ctx.line("front.pouch_small_seg1")
    assert (seg1.a, seg1.b) == (p_w0, k1)
    seg3 = ctx.line("front.pouch_small_seg3")
    assert (seg3.a, seg3.b) == (k2, p_s0)
    # 上沿侧缝链 P_s0 → P2（两段：大腿外缝子段 + 外缝弧子段），连续衔接
    s1 = ctx.curve("front.pouch_small_side_seg1")
    assert s1.p0.distance_to(p_s0) < 1e-9
    s2 = ctx.curve("front.pouch_small_side_seg2")
    assert s2.p3.distance_to(p2) < 1e-9
    # 袋口切削线：P2 → P1′（反向主切口）
    mouth = ctx.curve("front.pouch_small_mouth_seg1")
    cut = ctx.curve("front.pocket_mouth")
    assert mouth.p0.distance_to(cut.p3) < 1e-9   # P2
    assert mouth.p3.distance_to(cut.p0) < 1e-9   # P1′
    # 腰弧子段：P1 → P_w0（t_at_y 与 split 路径不同，浮点容差放宽）
    waist = ctx.curve("front.pouch_small_waist_edge")
    assert waist.p0.distance_to(ctx.point("front.pocket_p1")) < 1e-6
    assert waist.p3.distance_to(p_w0) < 1e-6


def test_pouch_bezier_edge():
    # bezier 边手工演算：C1 = A + κ1·L0·û(α)，C2 = B + κ2·L0·û(β)
    o = PatternOptions(delta=1.0, front_pocket=True, front_pouch=True,
                       front_pouch_edges=[("line",),
                                          ("bezier", 20.0, 0.3, -20.0, 0.4),
                                          ("line",)])
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    k1 = ctx.point("front.pouch_node1")
    k2 = ctx.point("front.pouch_node2")
    seg2 = ctx.curve("front.pouch_large_seg2")
    chord = k2 - k1
    l0 = chord.length
    u = chord.normalized()
    c1 = k1 + u.rotate(20.0).scale(0.3 * l0)
    c2 = k2 + u.rotate(-20.0).scale(0.4 * l0)
    assert seg2.p1.x == pytest.approx(c1.x, abs=1e-9)
    assert seg2.p1.y == pytest.approx(c1.y, abs=1e-9)
    assert seg2.p2.x == pytest.approx(c2.x, abs=1e-9)
    assert seg2.p2.y == pytest.approx(c2.y, abs=1e-9)


def test_pouch_requires_front_pocket():
    o = PatternOptions(delta=1.0, front_pouch=True)   # 未开 front_pocket
    with pytest.raises(ValueError, match="依赖前口袋主切口"):
        FlowRunner(M, o).run(FRONT_FLOW)


def test_pouch_skipped_by_default():
    ctx = FlowRunner(M, PatternOptions(delta=1.0, front_pocket=True)
                     ).run(FRONT_FLOW)
    assert "front.pouch_large_seg1" not in ctx.sheet


def test_pouch_options_validation():
    with pytest.raises(ValueError, match="安全内延/垂深"):
        PatternOptions(front_pouch_side_safe=-1.0)
    with pytest.raises(ValueError, match="至少 2 个"):
        PatternOptions(front_pouch_nodes=[(5.0, 16.0)])
    with pytest.raises(ValueError, match=r"节点数 \+ 1"):
        PatternOptions(front_pouch_edges=[("line",), ("line",)])
    with pytest.raises(ValueError, match="只支持 line / arc / bezier"):
        PatternOptions(front_pouch_edges=[("line",), ("spline", 1, 0.5),
                                          ("line",)])
    with pytest.raises(ValueError, match="弧顶分位"):
        PatternOptions(front_pouch_edges=[("line",), ("arc", 2.5, 0.05),
                                          ("line",)])
    with pytest.raises(ValueError, match="弦长比"):
        PatternOptions(front_pouch_edges=[("line",),
                                          ("bezier", 20, 0.0, -20, 0.3),
                                          ("line",)])


def test_pouch_anchors_curved_waistband():
    # 弯腰头：袋布锚点相对下腰头线定位（裤身顶边为下腰头线，腰头独立成片）
    o = PatternOptions(delta=1.0, front_pocket=True, front_pouch=True,
                       waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    lw_arc = ctx.curve("front.lower_waistline_arc")
    b_sub = ctx.point("front.lower_waist_side_point")
    p_w0 = ctx.point("front.pouch_waist_anchor")

    # 腰缝接触锚点 P_w0 在下腰头线上，自 B' 沿弧 8.5 + 4.0 = 12.5
    t = lw_arc.t_at_y(p_w0.y)
    assert lw_arc.point_at(t).distance_to(p_w0) < 1e-6
    assert _arc_length_between(lw_arc, 0.0, t) == pytest.approx(
        O.front_pocket_p1_dist + O.front_pouch_waist_safe, abs=1e-2)
    # 袋布节点相对 B'（弯腰头局部原点 O 下移）
    k1 = ctx.point("front.pouch_node1")
    assert k1.x == pytest.approx(b_sub.x + 5.0)
    assert k1.y == pytest.approx(b_sub.y - 16.0)
    # 大片固定边界截到有效腰口：腰缝边在下腰头线上（上端 B'）；
    # 侧缝边（默认 side_safe=8.0 → P_s0 低于臀围线，走大腿+髋腰两段子链）
    # 髋腰段上端 = B'（非 B）
    assert ctx.curve("front.pouch_large_waist_edge").point_at(0).distance_to(b_sub) < 1e-6
    hip_edge = ctx.curve("front.pouch_side_edge_hip")
    assert hip_edge.point_at(1).distance_to(b_sub) < 1e-6
    assert hip_edge.point_at(0).distance_to(
        ctx.point("front.hip_outseam_point")) < 1e-6
