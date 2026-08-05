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
