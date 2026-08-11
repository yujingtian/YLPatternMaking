"""步骤与流程测试：前片基础框架（M1）+ 裆部结构。

金标（H=96, Δ=1.0, outseam=102，直裆深 = H/4 = 24，直腰头扣腰头宽 4）：
  脚口线 y=0；立裆线 y=102−24=78（直裆深为人体量，不扣腰头）；
  臀围线 y=78+24/3=86；膝线 y=(0+78)/2+3=42；腰线 y=102−4=98；
  臀围宽度点 x=H/4−Δ=23；内侧缝线 x=23。
  前小裆宽顶点：x = 23 + 96/20 = 27.8，y = 立裆线 78。
  前中内收点：x = 23 − (96−70)/4×0.2 = 21.7，y = 腰线 98。
  裤中线立裆点：x = (23 + 4.8)/2 = 13.9，y = 78；裤中线 (13.9, 0) → (13.9, 98)。
  膝围点：d = (46/2 − 1)/2 = 11 → (2.9, 42)、(24.9, 42)；
  脚口点：d = (36/2 − 1)/2 = 8.5 → (5.4, 0)、(22.4, 0)，浅弧相连（默认弧高 0 = 直线，弦长 17）。
  外缝（α=0.1）：小腿弧 (2.9,42)→(5.4,0)，Q_mid=(4.15−0.25, 21)=(3.9, 21)；
    大腿弧 (0,86)→(2.9,42)，Q1=(−0.15, 78)。
  内缝（与外缝轴对称 x=13.9）：小腿弧 (24.9,42)→(22.4,0)，P_mid=(23.9, 21)；
    大腿弧 (27.8,78)→(24.9,42)，P1=(27.8−0.2×2.9, 78−0.28×36)=(27.22, 67.92)。
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


def test_front_rise_handle_ratio():
    # 前浪裆弯控制柄比例可调：k1=k2=|BC|×ratio（前浪绘制.md §4）。
    # 闭合约束恒成立（斜线长 = 目标 − 弧长），故以弧长随 ratio 变化验证参数生效。
    arc_default = FlowRunner(M, O).run(FRONT_FLOW).curve("front.rise_curve").length()

    o_big = PatternOptions(delta=1.0, front_rise_handle_ratio=0.5)
    ctx_big = FlowRunner(M, o_big).run(FRONT_FLOW)
    arc_big = ctx_big.curve("front.rise_curve").length()

    o_small = PatternOptions(delta=1.0, front_rise_handle_ratio=0.2)
    ctx_small = FlowRunner(M, o_small).run(FRONT_FLOW)
    arc_small = ctx_small.curve("front.rise_curve").length()

    # ratio 越大裆弯弧越饱满（长）
    assert arc_small < arc_default < arc_big
    # 闭合仍成立（直腰头扣腰头宽 4 -> 目标 21）
    for ctx in (ctx_big, ctx_small):
        total = ctx.line("front.rise_slant").length + ctx.curve("front.rise_curve").length()
        assert total == pytest.approx(M.front_rise - O.waistband_width)


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


def test_front_crease_line(ctx):
    # 裤中线立裆点：X = 前横裆总宽/2 = (23 + 4.8)/2 = 13.9（裤中线推导.md §二.1）
    pt = ctx.point("front.crease_point")
    assert pt.x == pytest.approx(13.9)
    assert pt.y == 78.0                       # 落在立裆线上
    # 裤中线为过该点的铅锤线：下抵脚口线、上抵腰围线
    line = ctx.line("front.crease_line")
    assert (line.a.x, line.b.x) == (pt.x, pt.x)
    assert (line.a.y, line.b.y) == (0.0, 98.0)


def test_front_crease_line_with_e():
    # 自定义调节量 e = -0.5（修身显瘦，裤中线推导.md §五）：x = 13.9 − 0.5
    o = PatternOptions(delta=1.0, front_crease_e=-0.5)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    assert ctx.point("front.crease_point").x == pytest.approx(13.4)


def test_crease_front_x_formula():
    # 公式层金标：X = (H/4 − Δ + H/20)/2 + e（裤中线推导.md §二.1）
    from ylpattern.formulas import leg as leg_f
    assert leg_f.crease_front_x(96, 1.0) == pytest.approx(13.9)
    assert leg_f.crease_front_x(96, 1.0, crotch_adjust=-0.5,
                                e=0.5) == pytest.approx(14.15)


def test_knee_hem_width_formulas():
    # 公式层金标：前片 = 总/2 − δ，后片 = 总/2 + δ（先平分再前减后加，推导.md §三.1）
    from ylpattern.formulas import leg as leg_f
    assert leg_f.knee_front(46, 1.0) == 22.0
    assert leg_f.knee_back(46, 1.0) == 24.0
    assert leg_f.hem_front(36, 1.0) == 17.0
    assert leg_f.hem_back(36, 1.0) == 19.0


def test_front_knee_hem_points(ctx):
    # 膝围点关于裤中线 x=13.9 对称，d前膝 = (46/2 − 1)/2 = 11
    ko = ctx.point("front.knee_outseam_point")
    ki = ctx.point("front.knee_inseam_point")
    assert (ko.x, ko.y) == (pytest.approx(2.9), 42.0)
    assert (ki.x, ki.y) == (pytest.approx(24.9), 42.0)
    # 脚口点同理，d前脚 = (36/2 − 1)/2 = 8.5
    ho = ctx.point("front.hem_outseam_point")
    hi = ctx.point("front.hem_inseam_point")
    assert (ho.x, ho.y) == (pytest.approx(5.4), 0.0)
    assert (hi.x, hi.y) == (pytest.approx(22.4), 0.0)


def test_front_hem_line_struct(ctx):
    # 脚口内外缝顶点以浅弧相连；默认弧高 0 → 退化为直线，弦长 = 前片脚口宽 17
    hem = ctx.curve("front.hem")
    assert hem.point_at(0) == ctx.point("front.hem_outseam_point")
    assert hem.point_at(1) == ctx.point("front.hem_inseam_point")
    assert hem.length() == pytest.approx(17.0)
    mid = hem.point_at(0.5)
    assert mid.y == pytest.approx(0.0)     # 弧顶压在弦上（直线）
    assert mid.x == pytest.approx(13.9)    # 裤中线处


def test_front_hem_arc_with_sag():
    # 弧高 0.5（前脚口向下凸）：弧顶精确下移 0.5，端点不动，弧长略大于弦长
    o = PatternOptions(delta=1.0, front_hem_arc_sag=0.5)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    hem = ctx.curve("front.hem")
    assert hem.point_at(0).y == 0.0
    assert hem.point_at(1).y == 0.0
    assert hem.point_at(0.5).y == pytest.approx(-0.5)
    assert hem.point_at(0.5).x == pytest.approx(13.9)
    assert hem.length() > 17.0


def test_front_knee_hem_widths_with_adjust():
    # 膝围、脚口调整量独立传入（推导.md §五.1）：
    # knee_adjust=0.5 → d前膝 = (46/2 − 0.5)/2 = 11.25；hem_adjust 默认 1.0 → d前脚 = 8.5 不变
    o = PatternOptions(delta=1.0, knee_adjust=0.5)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    x_c = ctx.line("front.crease_line").a.x
    assert ctx.point("front.knee_inseam_point").x == pytest.approx(x_c + 11.25)
    assert ctx.point("front.hem_inseam_point").x == pytest.approx(x_c + 8.5)
    # hem_adjust=0.75 → d前脚 = (36/2 − 0.75)/2 = 8.625；d前膝 默认 11 不变
    o = PatternOptions(delta=1.0, hem_adjust=0.75)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    assert ctx.point("front.hem_inseam_point").x == pytest.approx(x_c + 8.625)
    assert ctx.point("front.knee_inseam_point").x == pytest.approx(x_c + 11.0)


def test_outseam_curves(ctx):
    lower = ctx.curve("front.outseam_lower")
    upper = ctx.curve("front.outseam_upper")
    # 小腿弧：膝围外缝点 → 脚口外缝顶点
    assert lower.point_at(0) == ctx.point("front.knee_outseam_point")
    assert lower.point_at(1) == ctx.point("front.hem_outseam_point")
    # 大腿弧：臀围外缝顶点 → 膝围外缝点
    assert upper.point_at(0) == ctx.point("front.hip_outseam_point")
    assert upper.point_at(1) == ctx.point("front.knee_outseam_point")
    # Q1 = (X臀 − δx, 立裆线高) = (−0.15, 78)（前片弧线推导.md §五）
    assert upper.p1.x == pytest.approx(-0.15)
    assert upper.p1.y == pytest.approx(78.0)
    # 膝口 C1 连续：大腿弧终点切线 ∥ 小腿弧起点切线（推导.md §六）
    assert upper.angle_with(lower) == pytest.approx(0.0)


def test_inseam_curves(ctx):
    lower = ctx.curve("front.inseam_lower")
    upper = ctx.curve("front.inseam_upper")
    # 小腿弧：膝围内缝点 → 脚口内缝顶点
    assert lower.point_at(0) == ctx.point("front.knee_inseam_point")
    assert lower.point_at(1) == ctx.point("front.hem_inseam_point")
    # 大腿弧：前小裆宽顶点 → 膝围内缝点
    assert upper.point_at(0) == ctx.point("front.crotch_vertex")
    assert upper.point_at(1) == ctx.point("front.knee_inseam_point")
    # P1 = (X裆 − k1·ΔX, Y裆 − ky·ΔY) = (27.22, 67.92)（推导.md §四）
    assert upper.p1.x == pytest.approx(27.22)
    assert upper.p1.y == pytest.approx(67.92)
    # 膝口 C1 连续
    assert upper.angle_with(lower) == pytest.approx(0.0)


def test_lower_leg_curves_mirror_symmetric(ctx):
    # 内缝小腿弧 = 外缝小腿弧关于裤中线 x=13.9 的轴对称（打版流程.md 步骤 6）
    x_c = ctx.line("front.crease_line").a.x
    out = ctx.curve("front.outseam_lower")
    ins = ctx.curve("front.inseam_lower")
    for op, ip in ((out.p0, ins.p0), (out.p1, ins.p1),
                   (out.p2, ins.p2), (out.p3, ins.p3)):
        assert op.x + ip.x == pytest.approx(2 * x_c)
        assert op.y == pytest.approx(ip.y)


def test_lower_leg_alpha_zero_is_straight():
    # α=0（直筒）：P_mid 退化为弦中点，曲线成 100% 直线（推导.md §三 表格）
    o = PatternOptions(delta=1.0, calf_arc_alpha=0.0)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    lower = ctx.curve("front.outseam_lower")
    mid = lower.point_at(0.5)
    chord_mid = ctx.point("front.knee_outseam_point").midpoint(
        ctx.point("front.hem_outseam_point"))
    assert mid.x == pytest.approx(chord_mid.x)
    assert mid.y == pytest.approx(chord_mid.y)


# —— 弯腰头下腰缝线（前腰头绘制推导.md §4.3、§5.2）——

def _mid_sag(arc):
    """弧中点（t=0.5）相对弦的下凹量（与 curves.waist_sag_p2 同口径，朝 −Y 下凹为正）。"""
    p0, p3 = arc.point_at(0), arc.point_at(1)
    n = (p3 - p0).normalized().perpendicular()
    if n.dy > 0:
        n = n.scale(-1)                     # 取下凹侧（朝 −Y）法向
    rel = arc.point_at(0.5) - p0.midpoint(p3)
    return rel.dx * n.dx + rel.dy * n.dy


def test_front_lower_waistband_straight_skipped(ctx):
    # 直腰头：腰头单独成片，下腰缝线整步跳过（打版流程.md 注意点 1）
    assert "front.lower_waistline_arc" not in ctx.sheet
    assert "front.lower_waist_center_point" not in ctx.sheet
    assert "front.lower_waist_side_point" not in ctx.sheet


def test_front_lower_waistband_curved():
    o = PatternOptions(delta=1.0, waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    W = o.waistband_width
    lower = ctx.curve("front.lower_waistline_arc")
    a = ctx.point("front.rise_top_point")
    a_sub = ctx.point("front.lower_waist_center_point")
    b = ctx.point("front.waist_side_point")
    b_sub = ctx.point("front.lower_waist_side_point")
    outseam = ctx.curve("front.outseam_arc")

    # 端点：下腰头线 B'→A'
    assert lower.point_at(0) == b_sub
    assert lower.point_at(1) == a_sub
    # A'：沿前浪线自 A 向下量取 W（W 小，落在前中斜线上，A→A' 弧长 = W）
    assert a.distance_to(a_sub) == pytest.approx(W)
    assert a_sub.y < a.y
    # B'：沿外缝弧自 B 向下量取 W（B'→B 子弧长 = W）
    t_bsub = outseam.t_at_length(outseam.length() - W)
    assert b_sub == outseam.point_at(t_bsub)
    # B'→B 子弧长 = W（折线近似精度约 1e-4 cm，t_at_length 与子弧 length 各自采样）
    assert outseam.split(t_bsub)[1].length() == pytest.approx(W, abs=1e-3)
    assert b_sub.y < b.y
    # B' 切线 ⟂ 外缝切线（90° 直角法则，§5.1）
    t_lower = lower.tangent_at(0).normalized()
    t_side = outseam.tangent_at(t_bsub).normalized()
    assert abs(t_lower.dx * t_side.dx + t_lower.dy * t_side.dy) < 1e-3
    # 弧度与上腰口线一致：中点下凹量同 sag（§5.2 同曲率平行拟合）
    assert _mid_sag(lower) == pytest.approx(o.front_waist_curve_sag)
    assert _mid_sag(ctx.curve("front.waistline_arc")) == pytest.approx(o.front_waist_curve_sag)


def test_front_lower_waistband_width_param():
    # 腰头宽 3.5：A' 沿前浪下移量随之 = 3.5（腰头宽驱动下腰缝位置）
    o = PatternOptions(delta=1.0, waistband_type=WaistbandType.CURVED,
                       waistband_width=3.5)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    a = ctx.point("front.rise_top_point")
    a_sub = ctx.point("front.lower_waist_center_point")
    assert a.distance_to(a_sub) == pytest.approx(3.5)
