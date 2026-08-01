"""步骤与流程测试：前片基础框架（M1）+ 裆部结构。

金标（H=96, Δ=1.0, outseam=102，直裆深 = H/4 = 24，直腰头扣腰头宽 4）：
  脚口线 y=0；立裆线 y=102−24=78（直裆深为人体量，不扣腰头）；
  臀围线 y=78+24/3=86；膝线 y=(0+78)/2+3=42；腰线 y=102−4=98；
  臀围宽度点 x=H/4−Δ=23；内侧缝线 x=23。
  前小裆宽顶点：x = 23 + 96/20 = 27.8，y = 立裆线 78。
  前中内收点：x = 23 − (96−70)/4×0.2 = 21.7，y = 腰线 98。
"""

import pytest

from ylpattern.flows.front_flow import FRONT_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.params import Measurements, PatternOptions, WaistbandType

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
O = PatternOptions(delta=1.0)


@pytest.fixture()
def ctx():
    return FlowRunner(M, O).run(FRONT_FLOW)


def test_five_horizontal_reflines(ctx):
    for name in ("front.hem_line", "front.crotch_line", "front.hip_line",
                 "front.knee_line", "front.waist_line"):
        assert name in ctx.sheet, f"缺少参考线 {name}"


def test_refline_heights(ctx):
    assert ctx.line("front.hem_line").a.y == 0.0
    assert ctx.line("front.crotch_line").a.y == 78.0
    assert ctx.line("front.hip_line").a.y == 86.0
    assert ctx.line("front.knee_line").a.y == 42.0
    assert ctx.line("front.waist_line").a.y == 98.0   # 直腰头扣腰头宽 4


def test_curved_waistband_keeps_full_length():
    o = PatternOptions(delta=1.0, waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    assert ctx.line("front.waist_line").a.y == 102.0  # 弯腰头一体绘制，不扣
    assert ctx.line("front.crotch_line").a.y == 78.0  # 立裆线不受影响


def test_hip_width_point(ctx):
    pt = ctx.point("front.hip_width_point")
    assert pt.x == 23.0


def test_inner_seam_refline_completes_frame(ctx):
    assert ctx.line("front.inner_seam_refline").a.x == 23.0
    assert ctx.line("front.outseam_refline").a.x == 0.0


def test_front_crotch_vertex(ctx):
    pt = ctx.point("front.crotch_vertex")
    assert pt.x == pytest.approx(27.8)   # 23 + 96/20
    assert pt.y == 78.0                  # 落在立裆线上


def test_front_crotch_vertex_with_adjust():
    o = PatternOptions(delta=1.0, front_crotch_adjust=-0.5)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    pt = ctx.point("front.crotch_vertex")
    assert pt.x == pytest.approx(27.3)   # 23 + 4.8 − 0.5


def test_front_center_intake_point(ctx):
    pt = ctx.point("front.center_intake_point")
    assert pt.x == pytest.approx(21.7)  # 23 − (96−70)/4×0.2
    assert pt.y == 98.0                   # 落在腰线上（直腰头已扣 4）


def test_front_rise_composite(ctx):
    # 拐点 B = 臀围线 ∩ 内侧缝线 = (23, 86)
    b = ctx.point("front.hip_inner_point")
    assert (b.x, b.y) == (23.0, 86.0)

    # 弧线端点 = B 与前小裆宽顶点 C = (27.8, 78)
    arc = ctx.curve("front.rise_curve")
    assert arc.point_at(0) == b
    assert arc.point_at(1) == ctx.point("front.crotch_vertex")

    # C¹ 连续：起点切线沿前中斜线方向；终点切线水平（前浪绘制.md §1.2）
    a0 = ctx.point("front.center_intake_point")
    d_ab = (b - a0).normalized()
    t0 = arc.tangent_at(0).normalized()
    assert t0.dx == pytest.approx(d_ab.dx)
    assert t0.dy == pytest.approx(d_ab.dy)
    assert arc.tangent_at(1).dy == pytest.approx(0.0)


def test_front_rise_length_closure(ctx):
    # 弧长闭合：前中斜线长 + 裆弯弧长 = 前浪 − 腰头宽 = 25 − 4 = 21
    # （前浪为含腰头成衣量，直腰头扣除；前浪绘制.md §4）
    slant = ctx.line("front.rise_slant")
    arc = ctx.curve("front.rise_curve")
    assert slant.length + arc.length() == pytest.approx(
        M.front_rise - O.waistband_width)
    # 前浪顶点在斜线延长方向上
    a = ctx.point("front.rise_top_point")
    b = ctx.point("front.hip_inner_point")
    assert slant.a == a and slant.b == b
    # 前浪线为结构线（实线渲染），非参考线
    assert ctx.sheet.get("front.rise_slant").role == "struct"


def test_front_rise_closure_curved_waistband():
    # 弯腰头一体绘制：闭合目标 = 前浪原值 25
    o = PatternOptions(delta=1.0, waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    total = ctx.line("front.rise_slant").length + ctx.curve("front.rise_curve").length()
    assert total == pytest.approx(M.front_rise)


def test_rise_on_pattern_deduction():
    # 前浪/后浪统一扣除口径：直腰头 − 腰头宽，弯腰头原值（注意点 1）
    straight = PatternOptions(waistband_type=WaistbandType.STRAIGHT,
                              waistband_width=4.0)
    assert straight.rise_on_pattern(25) == 21.0   # 前浪
    assert straight.rise_on_pattern(33) == 29.0   # 后浪
    curved = PatternOptions(waistband_type=WaistbandType.CURVED)
    assert curved.rise_on_pattern(25) == 25.0
    assert curved.rise_on_pattern(33) == 33.0


def test_front_rise_too_short_raises():
    m = Measurements(waist=70, hip=96, knee=46, hem=36,
                     front_rise=5, back_rise=33, outseam=102, thigh=58)
    with pytest.raises(ValueError, match="无法闭合"):
        FlowRunner(m, O).run(FRONT_FLOW)


def test_front_center_intake_with_adjust():
    o = PatternOptions(delta=1.0, front_intake_adjust=-0.5)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    pt = ctx.point("front.center_intake_point")
    assert pt.x == pytest.approx(22.2)  # 23 − (1.3 − 0.5)


def test_until_interrupt():
    runner = FlowRunner(M, O)
    ctx = runner.run(FRONT_FLOW, until="draw_hip_line")
    assert "front.hip_line" in ctx.sheet
    assert "front.knee_line" not in ctx.sheet  # 后续步骤未执行


def test_trace_records_steps():
    runner = FlowRunner(M, O)
    runner.run(FRONT_FLOW, trace=True)
    assert len(runner.trace_log) == len(FRONT_FLOW)
    assert "[draw_front_hip_width] -> front.hip_width_point" in runner.trace_log[6]


def test_unknown_element_error_message(ctx):
    with pytest.raises(KeyError, match="版上不存在元素"):
        ctx.point("front.no_such_point")


def test_front_waistline(ctx):
    # 真实腰围线（构造直线）：从腰头内缝顶点出发，长度 = W/4 = 17.5
    line = ctx.line("front.waistline")
    a = ctx.point("front.rise_top_point")
    assert line.b == a                          # 终点锚在腰头内缝顶点
    assert line.length == pytest.approx(17.5)   # 腰长约束恒定（腰头绘制推导.md §4.2）
    # h=0（默认）：基础外缝顶点压在腰围基础线上
    b = ctx.point("front.waist_side_point")
    assert line.a == b
    assert b.y == pytest.approx(98.0)
    assert b.x < a.x                            # 向侧缝方向延伸
    # 直线阶段为构造线（最终轮廓由弧线取代）
    assert ctx.sheet.get("front.waistline").role == "ref"


def test_front_waistline_side_rise():
    # h=1.0：外缝顶点抬到基础线上方 1cm，腰长仍恒等于 17.5
    o = PatternOptions(delta=1.0, side_rise=1.0)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    b = ctx.point("front.waist_side_point")
    assert b.y == pytest.approx(99.0)
    assert ctx.line("front.waistline").length == pytest.approx(17.5)


def test_front_waistline_impossible_raises():
    # 抬高量超过腰长所能容纳的高差 → 报错（腰头绘制推导.md §6.2）
    o = PatternOptions(delta=1.0, side_rise=30.0)
    with pytest.raises(ValueError, match="无法构成腰线"):
        FlowRunner(M, o).run(FRONT_FLOW)


def test_front_waist_outseam_curves(ctx):
    a = ctx.point("front.rise_top_point")
    b = ctx.point("front.waist_side_point")
    w_arc = ctx.curve("front.waistline_arc")
    s_arc = ctx.curve("front.outseam_arc")

    # 端点：腰弧 B→A；侧缝弧 臀围线外缝顶点(0, 86) → B
    assert w_arc.point_at(0) == b
    assert w_arc.point_at(1) == a
    assert s_arc.point_at(0) == ctx.point("front.hip_outseam_point")
    assert s_arc.point_at(1) == b

    # 腰长按端点直线距离闭合 = 17.5；弧长自然略长，不补偿
    assert a.distance_to(b) == pytest.approx(17.5)
    assert w_arc.length() > 17.5

    # 90° 直角法则：腰弧起点切线 ⟂ 侧缝弧终点切线
    t_w = w_arc.tangent_at(0).normalized()
    t_s = s_arc.tangent_at(1).normalized()
    dot = t_w.dx * t_s.dx + t_w.dy * t_s.dy
    assert abs(dot) < 1e-3

    # 侧缝弧向外（−X）微凸：弧中点在弦的左侧
    mid = s_arc.point_at(0.5)
    chord_mid = s_arc.point_at(0).midpoint(s_arc.point_at(1))
    assert mid.x < chord_mid.x


def test_front_waist_outseam_curves_side_rise():
    # h=1.0 时端点直线距离仍恒等于 17.5，B 抬到基础线上方 1cm
    o = PatternOptions(delta=1.0, side_rise=1.0)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    a = ctx.point("front.rise_top_point")
    b = ctx.point("front.waist_side_point")
    assert a.distance_to(b) == pytest.approx(17.5)
    assert b.y == pytest.approx(99.0)
