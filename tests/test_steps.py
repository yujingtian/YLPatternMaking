"""步骤与流程测试：前片基础框架（M1）。

金标（H=96, Δ=1.0, outseam=102，直裆深 = H/4 = 24）：
  脚口线 y=0；立裆线 y=102−24=78；臀围线 y=78+24/3=86；
  膝线 y=(0+78)/2+3=42；腰线 y=102；
  臀围宽度点 x=H/4−Δ=23；内侧缝线 x=23。
  前小裆宽顶点：x = 23 + 96/20 = 27.8，y = 立裆线 78。
"""

import pytest

from ylpattern.flows.front_flow import FRONT_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.params import Measurements, PatternOptions

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
    assert ctx.line("front.waist_line").a.y == 102.0


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
