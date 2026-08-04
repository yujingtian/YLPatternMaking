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
