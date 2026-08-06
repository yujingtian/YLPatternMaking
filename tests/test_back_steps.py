"""步骤与流程测试：后片基础框架（打版流程.md 后片步骤 1）。

金标（H=96, Δ=1.0, outseam=102，直裆深 = H/4 = 24，直腰头扣腰头宽 4，
排版间距 piece_gap = 10；前片：立裆线 78、臀围线 86、膝线 42、腰线 98，
前片内侧缝参考线 x=23）：
  后片框架宽 H后 = 96/4 + 1 = 25；落裆量 Dc = 96/100 + 0 = 0.96。
  后片原点（外侧缝参考线）x = 23 + 10 = 33（与前片分开排版，不重叠）；
  后脚口线 y=0（与前片等高）；后立裆线 y=78（与前片横裆线等高）；
  落裆线 y=78−0.96=77.04（单独绘制，确定后大裆尖高度）；
  后臀围线 y=86（等高，不随落裆下移）；后膝围线 y=42（等高，§3.2 准则 3）；
  后腰围线 y=98（等高，后翘后续步骤再加）；
  后臀围宽度点 x=33+25=58；后内侧缝线 x=58。
  水平参考线 x 区间均为 [33, 58]，与前片 [0, 23] 互不重叠。
  后大裆宽顶点：W大裆 = 96/10 = 9.6 → x = 58 + 9.6 = 67.6，
  y = 落裆线 77.04（大裆尖落在落裆线上，落裆推导.md §3.2 准则 1）。
  后中内收点：H_v = 腰线 98 − 臀围线 86 = 12，D_h = 12 × 2.5/15 = 2.0
  → x = 58 − 2.0 = 56.0，y = 腰线 98（斜率锁定，内收量随臀腰高折算）。
  后裤中线立裆点：X后 = X前 13.9 + Δ 1.0 + e 0 = 14.9
  （Δ = (后脚口 19 − 前脚口 17)/2 = 1.0，裤中线推导.md §三 场景 B）
  → x = 33 + 14.9 = 47.9，y = 78；后裤中线 (47.9, 0) → (47.9, 98)。
  后膝围点：d = (46/2 + 1)/2 = 12 → (35.9, 42)、(59.9, 42)；
  后脚口点：d = (36/2 + 1)/2 = 9.5 → (38.4, 0)、(57.4, 0)，浅弧相连（默认弧高 0 = 直线，弦长 19）。
  后外缝：Q1 = (X臀 − 0.15, 78) ≈ (32.59, 78)；内缝 P1 = (67.6 − 0.3×7.7, 77.04 − 0.3×35.04)
  = (65.29, 66.528)；膝口 C1 连续（后片弧线推导.md §三/§四）。
"""

import pytest

from ylpattern.flows.back_flow import BACK_FLOW, FULL_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.params import Measurements, PatternOptions, WaistbandType

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
O = PatternOptions(delta=1.0)


@pytest.fixture()
def ctx():
    return FlowRunner(M, O).run(FULL_FLOW)


def test_five_horizontal_reflines(ctx):
    for name in ("back.hem_line", "back.crotch_line", "back.crotch_drop_line",
                 "back.hip_line", "back.knee_line", "back.waist_line"):
        assert name in ctx.sheet, f"缺少参考线 {name}"


def test_refline_heights(ctx):
    assert ctx.line("back.hem_line").a.y == 0.0
    assert ctx.line("back.crotch_line").a.y == 78.0   # 与前片横裆线等高
    assert ctx.line("back.crotch_drop_line").a.y == pytest.approx(77.04)  # 78 − 0.96
    assert ctx.line("back.hip_line").a.y == 86.0    # 与前片等高
    assert ctx.line("back.knee_line").a.y == 42.0   # 等高，禁止联动下垂
    assert ctx.line("back.waist_line").a.y == 98.0  # 直腰头扣腰头宽 4


def test_crotch_drop_with_adjust():
    # Δc = +0.2（宽松/重磅）：落裆线 y = 78 − (0.96 + 0.2) = 76.84
    o = PatternOptions(delta=1.0, crotch_drop_adjust=0.2)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    assert ctx.line("back.crotch_drop_line").a.y == pytest.approx(76.84)
    # 落裆不联动其他水平线
    assert ctx.line("back.crotch_line").a.y == 78.0
    assert ctx.line("back.knee_line").a.y == 42.0
    assert ctx.line("back.hip_line").a.y == 86.0


def test_curved_waistband_keeps_full_length():
    o = PatternOptions(delta=1.0, waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    assert ctx.line("back.waist_line").a.y == 102.0  # 弯腰头一体绘制，不扣


def test_hip_width_point(ctx):
    pt = ctx.point("back.hip_width_point")
    assert pt.x == 58.0   # 后片原点 33 + H后 25


def test_inner_seam_refline_completes_frame(ctx):
    assert ctx.line("back.outseam_refline").a.x == 33.0   # 23 + piece_gap 10
    assert ctx.line("back.inner_seam_refline").a.x == 58.0
    # 大矩形水平参考线长度 = 后片框架宽
    for name in ("back.hem_line", "back.crotch_line", "back.crotch_drop_line",
                 "back.hip_line", "back.knee_line", "back.waist_line"):
        assert ctx.line(name).length == pytest.approx(25.0)


def test_pieces_do_not_overlap(ctx):
    # 前后片分开排版：后片 x 区间 [33, 58] 与前片 [0, 23] 无交集，
    # 间距 = piece_gap = 10
    front_right = ctx.line("front.inner_seam_refline").a.x
    back_left = ctx.line("back.outseam_refline").a.x
    assert back_left - front_right == pytest.approx(O.piece_gap)
    for name in ("back.hem_line", "back.crotch_line", "back.crotch_drop_line",
                 "back.hip_line", "back.knee_line", "back.waist_line"):
        line = ctx.line(name)
        assert line.a.x == pytest.approx(33.0)
        assert line.b.x == pytest.approx(58.0)


def test_piece_gap_adjustable():
    o = PatternOptions(delta=1.0, piece_gap=20.0)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    assert ctx.line("back.outseam_refline").a.x == 43.0   # 23 + 20
    assert ctx.point("back.hip_width_point").x == 68.0    # 43 + 25


def test_back_flow_requires_front():
    # 后片步骤读取前片共享基准线，必须在前片之后执行
    runner = FlowRunner(M, O)
    with pytest.raises(Exception):
        runner.run(BACK_FLOW)


def test_back_crotch_vertex(ctx):
    pt = ctx.point("back.crotch_vertex")
    assert pt.x == pytest.approx(67.6)              # 58 + 96/10
    assert pt.y == pytest.approx(77.04)             # 落在落裆线上


def test_back_crotch_vertex_with_adjust():
    # Δ' = +0.5（复古/宽松）：W大裆 = 9.6 + 0.5 = 10.1 → x = 68.1
    o = PatternOptions(delta=1.0, back_crotch_adjust=0.5)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    assert ctx.point("back.crotch_vertex").x == pytest.approx(68.1)


def test_back_center_intake_point(ctx):
    pt = ctx.point("back.center_intake_point")
    assert pt.x == pytest.approx(56.0)  # 58 − 12×2.5/15 = 58 − 2.0
    assert pt.y == 98.0                 # 落在腰线上


def test_back_center_intake_adjustable():
    # X = 4.0（紧身/提臀档 3.5~4.5）：D_h = 12 × 4/15 = 3.2 → x = 54.8
    o = PatternOptions(delta=1.0, back_intake=4.0)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    assert ctx.point("back.center_intake_point").x == pytest.approx(54.8)


def test_back_rise_composite(ctx):
    # 拐点 B = 臀围线 ∩ 内侧缝线 = (58, 86)
    b = ctx.point("back.hip_inner_point")
    assert (b.x, b.y) == (58.0, 86.0)

    # 弧线端点 = B 与后大裆宽顶点 C = (67.6, 77.04)
    arc = ctx.curve("back.rise_curve")
    assert arc.point_at(0) == b
    assert arc.point_at(1) == ctx.point("back.crotch_vertex")

    # C¹ 连续：起点切线沿后中斜线方向；终点切线水平（后浪绘制.md §1.2）
    a0 = ctx.point("back.center_intake_point")
    d_ab = (b - a0).normalized()
    t0 = arc.tangent_at(0).normalized()
    assert t0.dx == pytest.approx(d_ab.dx)
    assert t0.dy == pytest.approx(d_ab.dy)
    assert arc.tangent_at(1).dy == pytest.approx(0.0)


def test_back_rise_length_closure(ctx):
    # 弧长闭合：后中斜线长 + 大裆弯弧长 = 后浪 − 腰头宽 = 33 − 4 = 29
    # （后浪为含腰头成衣量，直腰头扣除；后浪绘制.md §4）
    slant = ctx.line("back.rise_slant")
    arc = ctx.curve("back.rise_curve")
    assert slant.length + arc.length() == pytest.approx(
        M.back_rise - O.waistband_width)
    # 后浪顶点在斜线延长方向上（延伸量即后翘）
    a = ctx.point("back.rise_top_point")
    b = ctx.point("back.hip_inner_point")
    assert slant.a == a and slant.b == b
    # 后浪线为结构线（实线渲染），非参考线
    assert ctx.sheet.get("back.rise_slant").role == "struct"


def test_back_rise_closure_curved_waistband():
    # 弯腰头一体绘制：闭合目标 = 后浪原值 33
    o = PatternOptions(delta=1.0, waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    slant = ctx.line("back.rise_slant")
    arc = ctx.curve("back.rise_curve")
    assert slant.length + arc.length() == pytest.approx(M.back_rise)


def test_back_waistline(ctx):
    # 起翘辅助线与前片腰围外缝顶点等高（side_rise=0 → 腰线 98）
    aux = ctx.line("back.waist_aux_line")
    assert aux.a.y == ctx.point("front.waist_side_point").y == 98.0

    # 定长斜截：|AB| = 后腰长 = 70/4 + 0 + 0 = 17.5，B 在辅助线上
    a = ctx.point("back.rise_top_point")
    b = ctx.point("back.waist_side_point")
    assert b.y == 98.0
    assert a.distance_to(b) == pytest.approx(17.5)
    # 构造线为参考线（虚线），非最终轮廓
    assert ctx.sheet.get("back.waistline").role == "ref"


def test_back_waistband_arc(ctx):
    a = ctx.point("back.rise_top_point")
    b = ctx.point("back.waist_side_point")
    arc = ctx.curve("back.waistline_arc")
    assert arc.point_at(0) == a
    assert arc.point_at(1) == b

    # A 点切线与后中斜线 90° 正交（后腰头绘制推导.md §一.3 核心要点）
    rise_dir = (ctx.point("back.hip_inner_point") - a).normalized()
    t0 = arc.tangent_at(0).normalized()
    dot = t0.dx * rise_dir.dx + t0.dy * rise_dir.dy
    assert dot == pytest.approx(0.0, abs=1e-9)

    # 微微下凹：弧中点相对弦的下凹量精确 = sag（0.3），P1 正交段的
    # 偏离已被 P2 补偿（curves.waist_sag_p2，前后片同口径）
    d = (b - a).normalized()
    n = d.perpendicular()
    if n.dy > 0:
        n = n.scale(-1)          # 取朝下的法向
    pt = arc.point_at(0.5)
    dev = (pt - a).dx * n.dx + (pt - a).dy * n.dy
    assert dev == pytest.approx(O.back_waist_curve_sag)


def test_back_hip_final(ctx):
    a0 = ctx.point("back.center_intake_point")
    a = ctx.point("back.rise_top_point")
    b0 = ctx.point("back.hip_inner_point")
    b = ctx.point("back.hip_inner_final")
    out = ctx.point("back.hip_outseam_point")

    # 上移量一致：内缝顶点位移 = 后中内收点→后浪顶点的位移（同向量）
    assert b.x - b0.x == pytest.approx(a.x - a0.x)
    assert b.y - b0.y == pytest.approx(a.y - a0.y)

    # 外缝顶点回落原始臀围基础线（y=86，与前片侧缝零高差拼接）
    assert out.y == ctx.line("back.hip_line").a.y == 86.0

    # 弦长严格 = 后臀围长 H后 = 25（内高外低）
    assert b.distance_to(out) == pytest.approx(25.0)
    assert b.y > out.y

    # 最终后臀围线为虚线（参考线），非结构线
    assert ctx.sheet.get("back.hip_line_final").role == "ref"


def test_back_crease_line(ctx):
    # 后裤中线立裆点：X后 = X前 13.9 + Δ 1.0 + e 0 = 14.9
    # （Δ = (后脚口 19 − 前脚口 17)/2 = hem_adjust = 1.0，推导.md §三 场景 B）
    pt = ctx.point("back.crease_point")
    assert pt.x == pytest.approx(47.9)      # 后片原点 33 + 14.9
    assert pt.y == 78.0                     # 落在后立裆线上
    # 后裤中线为过该点的铅锤线：下抵脚口线、上抵腰围线
    line = ctx.line("back.crease_line")
    assert (line.a.x, line.b.x) == (pt.x, pt.x)
    assert (line.a.y, line.b.y) == (0.0, 98.0)


def test_back_crease_line_independent_e():
    # 前后片调节量分别独立录入：
    # front_crease_e=-0.5 → X前 = 13.4；back_crease_e=+0.5
    # → X后 = 13.4 + 1.0 + 0.5 = 14.9（后片不受前片 e 的符号影响，各自生效）
    o = PatternOptions(delta=1.0, front_crease_e=-0.5, back_crease_e=0.5)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    assert ctx.point("front.crease_point").x == pytest.approx(13.4)
    assert ctx.point("back.crease_point").x == pytest.approx(47.9)
    # 仅后片 e：X后 = 13.9 + 1.0 − 0.5 = 14.4 → x = 47.4，前片不动
    o = PatternOptions(delta=1.0, back_crease_e=-0.5)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    assert ctx.point("front.crease_point").x == pytest.approx(13.9)
    assert ctx.point("back.crease_point").x == pytest.approx(47.4)


def test_back_crease_line_follows_hem_adjust():
    # hem_adjust=1.25 → Δ = 1.25 → X后 = 13.9 + 1.25 = 15.15 → x = 48.15
    o = PatternOptions(delta=1.0, hem_adjust=1.25)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    assert ctx.point("back.crease_point").x == pytest.approx(48.15)


def test_crease_back_x_formula():
    # 公式层金标：X后 = X前 + Δ + e（裤中线推导.md §三 场景 B）
    from ylpattern.formulas import leg as leg_f
    assert leg_f.crease_back_x(13.9, 1.0) == pytest.approx(14.9)
    assert leg_f.crease_back_x(13.9, 1.0, e=-0.5) == pytest.approx(14.4)


def test_back_knee_hem_points(ctx):
    # 后膝围点关于后裤中线 x=47.9 对称，d后膝 = (46/2 + 1)/2 = 12
    ko = ctx.point("back.knee_outseam_point")
    ki = ctx.point("back.knee_inseam_point")
    assert (ko.x, ko.y) == (pytest.approx(35.9), 42.0)
    assert (ki.x, ki.y) == (pytest.approx(59.9), 42.0)
    # 后脚口点同理，d后脚 = (36/2 + 1)/2 = 9.5
    ho = ctx.point("back.hem_outseam_point")
    hi = ctx.point("back.hem_inseam_point")
    assert (ho.x, ho.y) == (pytest.approx(38.4), 0.0)
    assert (hi.x, hi.y) == (pytest.approx(57.4), 0.0)


def test_back_hem_line_struct(ctx):
    # 脚口内外缝顶点以浅弧相连；默认弧高 0 → 退化为直线，弦长 = 后片脚口宽 19
    hem = ctx.curve("back.hem")
    assert hem.point_at(0) == ctx.point("back.hem_outseam_point")
    assert hem.point_at(1) == ctx.point("back.hem_inseam_point")
    assert hem.length() == pytest.approx(19.0)
    mid = hem.point_at(0.5)
    assert mid.y == pytest.approx(0.0)     # 弧顶压在弦上（直线）
    assert mid.x == pytest.approx(47.9)    # 后裤中线处


def test_back_knee_hem_widths_with_adjust():
    # 调整量独立传入（前减后加，推导.md §三.1）：
    # knee_adjust=0.5 → d后膝 = (46/2 + 0.5)/2 = 11.75；hem_adjust=1.5 → d后脚 = 9.75
    o = PatternOptions(delta=1.0, knee_adjust=0.5, hem_adjust=1.5)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    x_c = ctx.line("back.crease_line").a.x
    assert ctx.point("back.knee_inseam_point").x == pytest.approx(x_c + 11.75)
    assert ctx.point("back.hem_inseam_point").x == pytest.approx(x_c + 9.75)


def test_back_hem_arc_with_sag():
    # 弧高 0.5（后脚口向下凸）：弧顶精确下移 0.5，端点不动，弧长略大于弦长；
    # 前后片弧高独立录入：back_hem_arc_sag 不影响前片脚口（仍为直线）
    o = PatternOptions(delta=1.0, back_hem_arc_sag=0.5)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    hem = ctx.curve("back.hem")
    assert hem.point_at(0).y == 0.0
    assert hem.point_at(1).y == 0.0
    assert hem.point_at(0.5).y == pytest.approx(-0.5)
    assert hem.point_at(0.5).x == pytest.approx(47.9)
    assert hem.length() > 19.0
    assert ctx.curve("front.hem").point_at(0.5).y == pytest.approx(0.0)


# ---------- 阶段 7：外缝、内缝线 ----------

def test_back_outseam_curves(ctx):
    lower = ctx.curve("back.outseam_lower")
    upper = ctx.curve("back.outseam_upper")
    # 小腿弧：膝围外缝点 → 脚口外缝顶点
    assert lower.point_at(0) == ctx.point("back.knee_outseam_point")
    assert lower.point_at(1) == ctx.point("back.hem_outseam_point")
    # 大腿弧：臀围外缝顶点 → 膝围外缝点
    assert upper.point_at(0) == ctx.point("back.hip_outseam_point")
    assert upper.point_at(1) == ctx.point("back.knee_outseam_point")
    # Q1 = (X臀 − δx, 立裆线高) ≈ (32.735 − 0.15, 78)（后片弧线推导.md §四）
    assert upper.p1.x == pytest.approx(32.585, abs=0.01)
    assert upper.p1.y == pytest.approx(78.0)
    # 膝口 C1 连续：大腿弧终点切线 ∥ 小腿弧起点切线（推导.md §一）
    assert upper.angle_with(lower) == pytest.approx(0.0)


def test_back_inseam_curves(ctx):
    lower = ctx.curve("back.inseam_lower")
    upper = ctx.curve("back.inseam_upper")
    # 小腿弧：膝围内缝点 → 脚口内缝顶点
    assert lower.point_at(0) == ctx.point("back.knee_inseam_point")
    assert lower.point_at(1) == ctx.point("back.hem_inseam_point")
    # 大腿弧：后大裆宽顶点 → 膝围内缝点
    assert upper.point_at(0) == ctx.point("back.crotch_vertex")
    assert upper.point_at(1) == ctx.point("back.knee_inseam_point")
    # P1 = (X裆 − k1·ΔX, Y裆 − ky·ΔY) = (67.6 − 0.3×7.7, 77.04 − 0.3×35.04)
    #    = (65.29, 66.528)（推导.md §三）
    assert upper.p1.x == pytest.approx(65.29)
    assert upper.p1.y == pytest.approx(66.528)
    # 膝口 C1 连续
    assert upper.angle_with(lower) == pytest.approx(0.0, abs=1e-6)


def test_back_lower_leg_curves_mirror_symmetric(ctx):
    # 内/外缝小腿弧关于后裤中线 x=47.9 轴对称（同一 α 公式两侧自动镜像）
    x_c = ctx.line("back.crease_line").a.x
    out = ctx.curve("back.outseam_lower")
    ins = ctx.curve("back.inseam_lower")
    for op, ip in ((out.p0, ins.p0), (out.p1, ins.p1),
                   (out.p2, ins.p2), (out.p3, ins.p3)):
        assert op.x + ip.x == pytest.approx(2 * x_c)
        assert op.y == pytest.approx(ip.y)


def test_back_arc_params_customizable():
    # 弧线形态参数独立录入：k1 0.30→0.35 → P1.x = 67.6 − 0.35×7.7 = 64.905；
    # δx 0.15→0.25 → Q1.x = X臀 − 0.25；前片弧线参数不受影响
    o = PatternOptions(delta=1.0, back_inseam_arc_k1=0.35,
                       back_outseam_arc_dx=0.25)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    assert ctx.curve("back.inseam_upper").p1.x == pytest.approx(64.905)
    hip_x = ctx.point("back.hip_outseam_point").x
    assert ctx.curve("back.outseam_upper").p1.x == pytest.approx(hip_x - 0.25)
    # 前片仍用前片默认值（k1 = 0.20、δx = 0.15）
    assert ctx.curve("front.inseam_upper").p1.x == pytest.approx(27.22)


def test_back_hip_waist_outseam_arc(ctx):
    # 髋腰侧缝段：最终臀围外缝顶点 → 后腰头外缝顶点（后片弧线推导.md §五）
    c = ctx.curve("back.outseam_hip_waist")
    assert c.point_at(0) == ctx.point("back.hip_outseam_point")
    assert c.point_at(1) == ctx.point("back.waist_side_point")
    # ΔY = 98 − 86 = 12：
    # W1 = (X臀 − δx1, Y臀 + k1·ΔY) = (32.735 − 0.15, 86 + 0.4×12) = (32.585, 90.8)
    # （本坐标系外缝朝 −X，δx1 取负使正值向外凸，§五 + 坐标系适配）
    assert c.p1.x == pytest.approx(32.585, abs=0.01)
    assert c.p1.y == pytest.approx(90.8)
    # W2 = (X腰 − δx2, Y腰 − k2·ΔY) = (37.2675 − 0, 98 − 0.25×12) = (37.2675, 95.0)
    waist = ctx.point("back.waist_side_point")
    assert c.p2.x == pytest.approx(waist.x)
    assert c.p2.y == pytest.approx(95.0)


def test_back_hip_waist_arc_params_customizable():
    # §五 四参数独立录入：k1 0.40→0.45 → W1.y = 86 + 0.45×12 = 91.4；
    # k2 0.25→0.30 → W2.y = 98 − 0.30×12 = 94.4；
    # δx1 0.15→0.3（骨盆外凸）、δx2 0→0.1（腰头凸量，正值均向外缝侧凸）
    o = PatternOptions(delta=1.0, back_hipwaist_arc_dx1=0.3,
                       back_hipwaist_arc_k1=0.45,
                       back_hipwaist_arc_dx2=0.1, back_hipwaist_arc_k2=0.30)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    c = ctx.curve("back.outseam_hip_waist")
    hip = ctx.point("back.hip_outseam_point")
    waist = ctx.point("back.waist_side_point")
    assert c.p1.x == pytest.approx(hip.x - 0.3)
    assert c.p1.y == pytest.approx(91.4)
    assert c.p2.x == pytest.approx(waist.x - 0.1)
    assert c.p2.y == pytest.approx(94.4)


# ---------- 阶段 9：后片绘制省（打版流程.md 后片步骤 9） ----------
#
# 金标（M 同上，back_dart=True，省量单独配置 back_dart_width；绘省不动
# 腰头，后腰长只由 back_waist_dart 容位决定，默认 0 → |AB| = 17.5）：
#   1 个省、省量 2.0：省中点 = AB 中点（两等分）；省中线长 11（垂线）；
#     省口两侧各 2.0/2 = 1.0 → 省口宽 2.0；
#     省边长 = sqrt(11² + 1²) = sqrt(122) ≈ 11.0454（等腰三角形）。
#   2 个省、单省省量 1.5：省中点在 t = 1/3、2/3 处
#     （距 A 17.5/3 ≈ 5.833、35/3 ≈ 11.667）；省口两侧各 0.75，
#     省边长 = sqrt(11² + 0.75²) ≈ 11.0256。

O_DART = PatternOptions(delta=1.0, back_dart=True)


@pytest.fixture()
def ctx_dart():
    return FlowRunner(M, O_DART).run(FULL_FLOW)


def test_back_darts_skipped_by_default(ctx):
    # 可选步骤：默认开关关闭，不上版任何省元素
    assert "back.dart1_center" not in ctx.sheet


def test_back_darts_skipped_without_dart_amount():
    # 开关开启但省量 = 0：整步跳过
    o = PatternOptions(delta=1.0, back_dart=True, back_dart_width=0.0)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    assert "back.dart1_center" not in ctx.sheet


def test_back_dart_single(ctx_dart):
    a = ctx_dart.point("back.rise_top_point")
    b = ctx_dart.point("back.waist_side_point")
    # 绘省不动腰头：|AB| = 后腰长 = 70/4 + 0 + 0 = 17.5（不受省量影响）
    assert a.distance_to(b) == pytest.approx(17.5)

    c = ctx_dart.point("back.dart1_center")
    apex = ctx_dart.point("back.dart1_apex")
    # 省中点 = 腰头直线两等分中点
    assert c == a.midpoint(b)
    # 省中线 ⟂ 腰头直线，长 = 11，省尖朝裤片内部（腰头下方）
    d = (b - a).normalized()
    v = apex - c
    assert v.dx * d.dx + v.dy * d.dy == pytest.approx(0.0, abs=1e-9)
    assert c.distance_to(apex) == pytest.approx(11.0)
    assert apex.y < c.y

    # 省口：省中点沿腰头直线两侧各 1.0（省量 2.0），距 A 7.75 / 9.75
    l_in = ctx_dart.line("back.dart1_leg_inner")
    l_out = ctx_dart.line("back.dart1_leg_outer")
    assert a.distance_to(l_in.b) == pytest.approx(17.5 / 2 - 1.0)
    assert a.distance_to(l_out.b) == pytest.approx(17.5 / 2 + 1.0)
    assert l_in.b.distance_to(l_out.b) == pytest.approx(2.0)
    # 等腰三角形：两省边等长 = sqrt(11² + 1²)
    assert l_in.length == pytest.approx((11.0 ** 2 + 1.0 ** 2) ** 0.5)
    assert l_out.length == pytest.approx(l_in.length)
    # 省边为结构线（实线），省中线为参考线（虚线）
    assert ctx_dart.sheet.get("back.dart1_leg_inner").role == "struct"
    assert ctx_dart.sheet.get("back.dart1_center_line").role == "ref"


def test_back_dart_double():
    o = PatternOptions(delta=1.0, back_dart=True, back_dart_count=2,
                       back_dart_width=1.5)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    a = ctx.point("back.rise_top_point")
    b = ctx.point("back.waist_side_point")
    assert a.distance_to(b) == pytest.approx(17.5)   # 绘省不动腰头

    # 三等分两个中间点：距 A 17.5/3、35/3
    c1 = ctx.point("back.dart1_center")
    c2 = ctx.point("back.dart2_center")
    assert a.distance_to(c1) == pytest.approx(17.5 / 3)
    assert a.distance_to(c2) == pytest.approx(35.0 / 3)
    # 单值广播：两个省省量同为 1.5，省口两侧各 0.75
    for i in (1, 2):
        l_in = ctx.line(f"back.dart{i}_leg_inner")
        l_out = ctx.line(f"back.dart{i}_leg_outer")
        assert l_in.b.distance_to(l_out.b) == pytest.approx(1.5)
        assert l_in.length == pytest.approx((11.0 ** 2 + 0.75 ** 2) ** 0.5)
        assert l_in.length == pytest.approx(l_out.length)


def test_back_dart_widths_per_dart():
    # 省量列表逐省控制：省1（近后中）1.0、省2（近侧缝）2.0
    o = PatternOptions(delta=1.0, back_dart=True, back_dart_count=2,
                       back_dart_width=[1.0, 2.0])
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    mouths = {1: 1.0, 2: 2.0}
    for i, w in mouths.items():
        l_in = ctx.line(f"back.dart{i}_leg_inner")
        l_out = ctx.line(f"back.dart{i}_leg_outer")
        assert l_in.b.distance_to(l_out.b) == pytest.approx(w)
        assert l_in.length == pytest.approx((11.0 ** 2 + (w / 2) ** 2) ** 0.5)
        assert l_in.length == pytest.approx(l_out.length)


def test_back_dart_zero_width_skipped():
    # 省量为 0 的省不绘制：只上版省2（省量 2.0）的元素
    o = PatternOptions(delta=1.0, back_dart=True, back_dart_count=2,
                       back_dart_width=[0.0, 2.0])
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    assert "back.dart1_center" not in ctx.sheet
    assert "back.dart2_center" in ctx.sheet
    l_in = ctx.line("back.dart2_leg_inner")
    l_out = ctx.line("back.dart2_leg_outer")
    assert l_in.b.distance_to(l_out.b) == pytest.approx(2.0)


def test_back_dart_independent_of_waist_length():
    # 绘省与后腰长相互独立：back_waist_dart=5.0 决定腰长（|AB| = 22.5），
    # back_dart_width=2.0 只控制省口宽（2.0），互不干扰
    o = PatternOptions(delta=1.0, back_waist_dart=5.0, back_dart=True)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    a = ctx.point("back.rise_top_point")
    b = ctx.point("back.waist_side_point")
    assert a.distance_to(b) == pytest.approx(22.5)
    l_in = ctx.line("back.dart1_leg_inner")
    l_out = ctx.line("back.dart1_leg_outer")
    assert l_in.b.distance_to(l_out.b) == pytest.approx(2.0)


def test_back_dart_length_configurable():
    o = PatternOptions(delta=1.0, back_dart=True, back_dart_length=13.0)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    c = ctx.point("back.dart1_center")
    apex = ctx.point("back.dart1_apex")
    assert c.distance_to(apex) == pytest.approx(13.0)


def test_back_dart_options_validation():
    with pytest.raises(ValueError, match="省数"):
        PatternOptions(back_dart_count=3)
    with pytest.raises(ValueError, match="省量不能为负数"):
        PatternOptions(back_dart_width=-1.0)
    with pytest.raises(ValueError, match="省量个数"):
        PatternOptions(back_dart_count=2, back_dart_width=[2.0, 1.5, 1.0])
    with pytest.raises(ValueError, match="省中线长"):
        PatternOptions(back_dart_length=0.0)


def test_back_dart_width_normalized():
    # 标量 → 元组；单值 + 两个省 → 广播共用
    assert PatternOptions().back_dart_width == (2.0,)
    assert PatternOptions(back_dart_width=1.5).back_dart_width == (1.5,)
    assert PatternOptions(back_dart_count=2,
                          back_dart_width=1.5).back_dart_width == (1.5, 1.5)
    assert PatternOptions(back_dart_count=2,
                          back_dart_width=[1.0, 2.0]).back_dart_width == (1.0, 2.0)
