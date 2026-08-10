"""后机头/育克步骤测试（后机头绘制.md §1、§2；打版流程.md「后机头/育克绘制」）。

金标（M 同 test_back_steps：H=96, Δ=1.0, outseam=102，直腰头扣腰头宽 4，
腰线 y=98；后浪闭合目标 33−4=29，后中斜线长约 15、大裆弯弧长约 14）：
  默认 back_yoke_cb_dist=4.0、back_yoke_side_dist=3.0，无中间锚点 -> 直线下口。
  P0 在后中斜线上（D_cb 4 < 斜线长 15），O->P0 直线距 = 弧长 = 4.0；
  PN 在外缝髋腰弧上，自腰端 X 下行 D_side 3.0，PN->X 子弧长 = 3.0。
  弯腰头：量取起点改下腰头顶点，链上距离 = W + D_cb / W + D_side。
"""

import pytest

from ylpattern.flows.back_flow import FULL_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.params import Measurements, PatternOptions, WaistbandType

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
O = PatternOptions(delta=1.0, back_yoke=True)


def _assert_point_approx(a, b, *, abs=1e-3):
    """逐坐标近似比较（Point 非数值，pytest.approx 不直接支持）。"""
    assert a.x == pytest.approx(b.x, abs=abs)
    assert a.y == pytest.approx(b.y, abs=abs)


@pytest.fixture()
def ctx():
    return FlowRunner(M, O).run(FULL_FLOW)


def test_back_yoke_skipped_by_default():
    # 可选步骤：默认开关关闭，不上版任何机头元素
    ctx = FlowRunner(M, PatternOptions(delta=1.0)).run(FULL_FLOW)
    assert "back.yoke_cb_point" not in ctx.sheet
    assert "back.yoke_bottom_seg1" not in ctx.sheet


def test_back_yoke_endpoints_straight(ctx):
    o_pt = ctx.point("back.rise_top_point")          # O 后浪顶点
    x = ctx.point("back.waist_side_point")           # X 腰头外缝顶点
    p0 = ctx.point("back.yoke_cb_point")
    pn = ctx.point("back.yoke_side_point")

    # P0 在后中斜线上：自 O 沿后浪线 D_cb 4.0（直线段：直线距 = 弧长）
    slant = ctx.line("back.rise_slant")
    assert slant.point_at(O.back_yoke_cb_dist / slant.length) == pytest.approx(p0)
    assert o_pt.distance_to(p0) == pytest.approx(O.back_yoke_cb_dist)
    assert p0.y < o_pt.y                             # 在 O 下方

    # PN 在外缝髋腰弧上：自 X 下行 D_side 3.0，PN->X 子弧长 = D_side
    hw = ctx.curve("back.outseam_hip_waist")        # 臀(t=0) -> 腰(t=1)
    t_pn = hw.t_at_length(hw.length() - O.back_yoke_side_dist)
    _assert_point_approx(hw.point_at(t_pn), pn, abs=1e-3)
    assert hw.split(t_pn)[1].length() == pytest.approx(O.back_yoke_side_dist, abs=1e-3)
    assert pn.y < x.y                                # 在 X 下方

    # P0 在后中（高 x）、PN 在侧缝（低 x）：下口线自后中向侧缝
    assert p0.x > pn.x


def test_back_yoke_dist_params():
    # D_cb/D_side 独立录入：5.0 / 4.0
    o = PatternOptions(delta=1.0, back_yoke=True,
                       back_yoke_cb_dist=5.0, back_yoke_side_dist=4.0)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    o_pt = ctx.point("back.rise_top_point")
    p0 = ctx.point("back.yoke_cb_point")
    hw = ctx.curve("back.outseam_hip_waist")
    pn = ctx.point("back.yoke_side_point")
    assert o_pt.distance_to(p0) == pytest.approx(5.0)
    t_pn = hw.t_at_length(hw.length() - 4.0)
    assert hw.split(t_pn)[1].length() == pytest.approx(4.0, abs=1e-3)


def test_back_yoke_endpoints_curved():
    # 弯腰头：量取起点 = 下腰头顶点，链上距离 = W + D_cb / W + D_side
    o = PatternOptions(delta=1.0, back_yoke=True,
                       waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    W = o.waistband_width
    o_pt = ctx.point("back.rise_top_point")          # O
    o_sub = ctx.point("back.lower_waist_center_point")  # O'
    x = ctx.point("back.waist_side_point")           # X
    p0 = ctx.point("back.yoke_cb_point")
    pn = ctx.point("back.yoke_side_point")

    # O' 在 O 下方 W；P0 在 O' 下方 D_cb（均落在后中斜线上）
    assert o_pt.distance_to(o_sub) == pytest.approx(W)
    assert o_sub.distance_to(p0) == pytest.approx(o.back_yoke_cb_dist)
    assert o_pt.distance_to(p0) == pytest.approx(W + o.back_yoke_cb_dist)

    # PN 自 X 下行 W + D_side，PN->X 子弧长 = W + D_side
    hw = ctx.curve("back.outseam_hip_waist")
    t_pn = hw.t_at_length(hw.length() - (W + o.back_yoke_side_dist))
    _assert_point_approx(hw.point_at(t_pn), pn, abs=1e-3)
    assert hw.split(t_pn)[1].length() == pytest.approx(
        W + o.back_yoke_side_dist, abs=1e-3)
    assert pn.y < x.y


def test_back_yoke_default_bottom_line(ctx):
    # 无中间锚点 -> 单段直线 P0->PN，结构线
    p0 = ctx.point("back.yoke_cb_point")
    pn = ctx.point("back.yoke_side_point")
    seg1 = ctx.line("back.yoke_bottom_seg1")
    assert (seg1.a, seg1.b) == (p0, pn)
    assert ctx.sheet.get("back.yoke_bottom_seg1").role == "struct"
    assert "back.yoke_bottom_seg2" not in ctx.sheet
    assert "back.yoke_mid_pt1" not in ctx.sheet


def test_back_yoke_empty_edges_all_straight():
    # edges 留空 = 全段直线（打版流程.md：无控制点即直线；省略 edges 即可）
    o = PatternOptions(delta=1.0, back_yoke=True,
                       back_yoke_mid_anchors=[], back_yoke_edges=[])
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    p0 = ctx.point("back.yoke_cb_point")
    pn = ctx.point("back.yoke_side_point")
    # 归一化：0 锚点 + 空 edges -> 1 段直线
    assert o.back_yoke_edges == (("line",),)
    seg1 = ctx.line("back.yoke_bottom_seg1")
    assert (seg1.a, seg1.b) == (p0, pn)
    assert "back.yoke_bottom_seg2" not in ctx.sheet


def test_back_yoke_empty_edges_with_anchors():
    # 有锚点但 edges 留空 -> 各段皆直线（锚点定型、边型省略）
    o = PatternOptions(delta=1.0, back_yoke=True,
                       back_yoke_mid_anchors=[(0.5, 1.5)], back_yoke_edges=[])
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    p0 = ctx.point("back.yoke_cb_point")
    pn = ctx.point("back.yoke_side_point")
    mid = ctx.point("back.yoke_mid_pt1")
    assert o.back_yoke_edges == (("line",), ("line",))
    assert (ctx.line("back.yoke_bottom_seg1").a,
            ctx.line("back.yoke_bottom_seg1").b) == (p0, mid)
    assert (ctx.line("back.yoke_bottom_seg2").a,
            ctx.line("back.yoke_bottom_seg2").b) == (mid, pn)


def test_back_yoke_mid_anchors():
    # 1 个锚点 (0.5, 1.5)：2 段直线，锚点在弦中点下凸 1.5
    o = PatternOptions(delta=1.0, back_yoke=True,
                       back_yoke_mid_anchors=[(0.5, 1.5)],
                       back_yoke_edges=[("line",), ("line",)])
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    p0 = ctx.point("back.yoke_cb_point")
    pn = ctx.point("back.yoke_side_point")
    mid = ctx.point("back.yoke_mid_pt1")

    chord = pn - p0
    n = chord.normalized().perpendicular()
    if n.dy > 0:
        n = n.scale(-1)                              # 取朝下（入裤身）法向
    expected = p0.lerp(pn, 0.5) + n.scale(1.5)
    assert mid == pytest.approx(expected)
    # depth 正值下凸：锚点低于弦中点
    assert mid.y < p0.lerp(pn, 0.5).y
    # 两段：P0->mid、mid->PN
    assert (ctx.line("back.yoke_bottom_seg1").a,
            ctx.line("back.yoke_bottom_seg1").b) == (p0, mid)
    assert (ctx.line("back.yoke_bottom_seg2").a,
            ctx.line("back.yoke_bottom_seg2").b) == (mid, pn)


def test_back_yoke_custom_edges():
    # 2 锚点 + line/arc/bezier 三段（打版流程.md：每段直线/弧线/贝塞尔可控制）
    o = PatternOptions(delta=1.0, back_yoke=True,
        back_yoke_mid_anchors=[(0.33, 1.0), (0.66, 1.0)],
        back_yoke_edges=[("line",), ("arc", 1.5, 0.5),
                         ("bezier", 30.0, 0.5, -30.0, 0.5)])
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    p0 = ctx.point("back.yoke_cb_point")
    pn = ctx.point("back.yoke_side_point")
    mid1 = ctx.point("back.yoke_mid_pt1")
    mid2 = ctx.point("back.yoke_mid_pt2")

    # seg1 直线 P0->mid1
    assert ctx.line("back.yoke_bottom_seg1").a == p0
    # seg2 arc mid1->mid2（端点吻合）
    arc = ctx.curve("back.yoke_bottom_seg2")
    assert arc.p0 == mid1 and arc.p3 == mid2
    # seg3 bezier mid2->PN（端点 + 控制点构造校验：C1=A+κ1·L0·û(α)）
    bz = ctx.curve("back.yoke_bottom_seg3")
    assert bz.p0 == mid2 and bz.p3 == pn
    chord = pn - mid2
    l0 = chord.length
    u = chord.normalized()
    exp_c1 = mid2 + u.rotate(30.0).scale(0.5 * l0)
    exp_c2 = pn + u.rotate(-30.0).scale(0.5 * l0)
    assert bz.p1.x == pytest.approx(exp_c1.x, abs=1e-9)
    assert bz.p1.y == pytest.approx(exp_c1.y, abs=1e-9)
    assert bz.p2.x == pytest.approx(exp_c2.x, abs=1e-9)
    assert bz.p2.y == pytest.approx(exp_c2.y, abs=1e-9)


def test_back_yoke_with_back_dart():
    # 机头与后片腰省相互独立：两者同开均上版（back_waist_dart 决定腰长，不干扰机头几何）
    o = PatternOptions(delta=1.0, back_yoke=True, back_dart=True)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    assert "back.yoke_cb_point" in ctx.sheet
    assert "back.dart1_center" in ctx.sheet


def test_back_yoke_options_validation():
    with pytest.raises(ValueError, match="后浪端点距离必须为正数"):
        PatternOptions(back_yoke=True, back_yoke_cb_dist=0.0)
    with pytest.raises(ValueError, match="侧缝端点距离必须为正数"):
        PatternOptions(back_yoke=True, back_yoke_side_dist=-1.0)
    with pytest.raises(ValueError, match="弦上位置须在"):
        PatternOptions(back_yoke=True, back_yoke_mid_anchors=[(1.5, 1.0)])
    with pytest.raises(ValueError, match="深度绝对值"):
        PatternOptions(back_yoke=True, back_yoke_mid_anchors=[(0.5, 15.0)])
    with pytest.raises(ValueError, match="严格递增"):
        PatternOptions(back_yoke=True,
                       back_yoke_mid_anchors=[(0.6, 1.0), (0.4, 1.0)])
    with pytest.raises(ValueError, match="个数须为锚点数"):
        PatternOptions(back_yoke=True, back_yoke_mid_anchors=[(0.5, 1.0)],
                       back_yoke_edges=[("line",)])
    with pytest.raises(ValueError, match="边形态只支持"):
        PatternOptions(back_yoke=True, back_yoke_mid_anchors=[(0.5, 1.0)],
                       back_yoke_edges=[("zigzag",)])
    with pytest.raises(ValueError, match="arc 弧顶分位"):
        PatternOptions(back_yoke=True, back_yoke_mid_anchors=[(0.5, 1.0)],
                       back_yoke_edges=[("arc", 1.5, 1.5)])
    with pytest.raises(ValueError, match="bezier 手柄弦长比"):
        PatternOptions(back_yoke=True, back_yoke_mid_anchors=[(0.5, 1.0)],
                       back_yoke_edges=[("bezier", 30, 0.5, -30, 1.5)])


def test_back_yoke_edges_normalized():
    # 边形态归一化为元组（与袋布/小表袋同口径）
    o = PatternOptions(delta=1.0, back_yoke=True,
                       back_yoke_mid_anchors=[(0.5, 1.0)],
                       back_yoke_edges=[("line",), ("arc", 2.0, 0.5)])
    assert o.back_yoke_mid_anchors == ((0.5, 1.0),)
    assert o.back_yoke_edges == (("line",), ("arc", 2.0, 0.5))
