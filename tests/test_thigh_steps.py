"""毗围限制步骤与闭环修正测试（打版流程.md 后片步骤 8；前后片毗围推导.md）。

金标（H=96, Δ=1.0, outseam=102，直裆深 24，立裆线 y=78，落裆量 Dc=0.96，
后大裆宽顶点 (67.6, 77.04)，前小裆宽顶点 (27.8, 78)）：
  d = 0（基准情形）：
    前毗围线水平：外缝交点 ≈ (0.2794, 78) → 前小裆宽顶点 (27.8, 78)，
      实测前毗围 ≈ 27.5206；
    后毗围线斜量：外缝交点 ≈ (33.0541, 78) → 后大裆宽顶点 (67.6, 77.04)，
      实测后毗围 ≈ 34.5592（勾股：√(34.5459² + 0.96²)，推导.md §二 W_b0）；
    合计 ≈ 62.0798，目标 58 → ΔW ≈ −4.08。
  d = 2.54（实测下移，测量线 y = 75.46）：
    前 ≈ 27.1894（内端落前内缝大腿弧）、后 ≈ 33.9975（内端落后内缝
    大腿弧，测量线低于裆尖 77.04）。
  闭环（thigh_limit=True）：
    目标 64（ΔW=+1.92 加宽双轨）：前裆 +0.09×1.92 ≈ +0.173、
      后裆 +0.21×1.92 ≈ +0.403，2 轮收敛 |ΔW| ≤ 0.05；
    目标 58（ΔW=−4.08 收窄大差量）：裆尖累计钳制 −0.4 / −1.0（极值
      红线），侧缝触及臀→膝连接轴钳制（防内凹红线），残余 ΔW < 0。
"""

import pytest

from ylpattern.flows.back_flow import FULL_FLOW
from ylpattern.flows.closure import run_with_thigh_closure
from ylpattern.flows.runner import FlowRunner
from ylpattern.params import Measurements, PatternOptions

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
O = PatternOptions(delta=1.0)


@pytest.fixture()
def ctx():
    return FlowRunner(M, O).run(FULL_FLOW)


def _m(thigh: float) -> Measurements:
    return Measurements(waist=70, hip=96, knee=46, hem=36,
                        front_rise=25, back_rise=33, outseam=102, thigh=thigh)


# ---------- 步骤 8：毗围线测量（d = 0 基准情形） ----------

def test_thigh_lines_drawn(ctx):
    for name in ("front.thigh_line", "back.thigh_line",
                 "front.thigh_outseam_point", "back.thigh_outseam_point"):
        assert name in ctx.sheet, f"缺少元素 {name}"
    # 毗围线为参考线（虚线），非结构线
    assert ctx.sheet.get("front.thigh_line").role == "ref"
    assert ctx.sheet.get("back.thigh_line").role == "ref"


def test_front_thigh_line_zero_offset(ctx):
    line = ctx.line("front.thigh_line")
    # 水平线：两端都在立裆线 y=78 上
    assert line.a.y == pytest.approx(78.0)
    assert line.b.y == pytest.approx(78.0)
    # 内端 = 前小裆宽顶点；外端 = 前外缝大腿弧 ∩ 立裆线
    assert line.b == ctx.point("front.crotch_vertex")
    assert line.a.x == pytest.approx(0.2794, abs=1e-3)
    assert line.length == pytest.approx(27.5206, abs=1e-3)
    assert ctx.point("front.thigh_outseam_point") == line.a


def test_back_thigh_line_zero_offset(ctx):
    line = ctx.line("back.thigh_line")
    # 斜量：外缝交点（y=78）→ 后大裆宽顶点（落裆线 y=77.04）
    assert line.a.y == pytest.approx(78.0)
    assert line.b == ctx.point("back.crotch_vertex")
    assert line.a.x == pytest.approx(33.0541, abs=1e-3)
    # 勾股校验：W_b0 = √(L_b² + d_drop²)（推导.md §二 几何校验公式）
    dx = 67.6 - 33.0541
    assert line.length == pytest.approx((dx ** 2 + 0.96 ** 2) ** 0.5, abs=1e-3)
    assert line.length == pytest.approx(34.5592, abs=1e-3)


def test_thigh_total_and_delta_in_basis(ctx):
    el = ctx.sheet.get("back.thigh_line")
    # basis 记录实测/目标/ΔW（推导.md §三 闭环起点）
    assert "62.08" in el.basis and "ΔW = -4.08" in el.basis


# ---------- 步骤 8：实测下移量 d > 0 ----------

def test_thigh_lines_with_offset():
    o = PatternOptions(delta=1.0, thigh_measure_offset=2.54)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    # 测量线 y = 78 − 2.54 = 75.46，内端落在内缝大腿弧上（前后片均低于裆尖）
    f_line = ctx.line("front.thigh_line")
    assert f_line.a.y == pytest.approx(75.46)
    assert f_line.b.y == pytest.approx(75.46)
    assert ctx.point("front.thigh_inseam_point") == f_line.b
    assert f_line.length == pytest.approx(27.1894, abs=1e-3)
    b_line = ctx.line("back.thigh_line")
    assert ctx.point("back.thigh_inseam_point") == b_line.b
    assert b_line.length == pytest.approx(33.9975, abs=1e-3)


def test_thigh_offset_validated():
    with pytest.raises(ValueError):
        PatternOptions(thigh_measure_offset=-1.0)


# ---------- 闭环修正（thigh_limit=True） ----------

def test_closure_disabled_by_default(ctx):
    # 默认关闭：只测量不修正，选项原样保留
    assert ctx.options.front_crotch_adjust == 0.0
    assert ctx.options.back_crotch_adjust == 0.0
    assert ctx.options.outseam_arc_dx == O.outseam_arc_dx


def test_closure_converges_widening():
    # 目标 64 > 自然合计 62.08：加宽双轨，2 轮收敛
    o = PatternOptions(delta=1.0, thigh_limit=True)
    ctx, trace = run_with_thigh_closure(_m(64.0), o)
    w = (ctx.line("front.thigh_line").length
         + ctx.line("back.thigh_line").length)
    assert abs(64.0 - w) <= 0.05
    # 裆尖调拨 = 0.09/0.21 × ΔW（推导.md §三.2 内缝调拨量公式）
    assert ctx.options.front_crotch_adjust == pytest.approx(0.173, abs=1e-3)
    assert ctx.options.back_crotch_adjust == pytest.approx(0.403, abs=1e-3)
    # 侧缝承担 70% 中的前后份额 → 外凸 δx 加大
    assert ctx.options.outseam_arc_dx > O.outseam_arc_dx
    assert ctx.options.back_outseam_arc_dx > O.back_outseam_arc_dx
    assert "收敛" in trace


def test_closure_redline_caps_shrinking():
    # 目标 58 ≪ 自然合计 62.08：收窄大差量，触及全部红线
    o = PatternOptions(delta=1.0, thigh_limit=True)
    ctx, trace = run_with_thigh_closure(M, o)
    # 裆尖累计钳制在极值红线（防卡耻骨 0.4 / 防下蹲崩破 1.0）
    assert ctx.options.front_crotch_adjust == pytest.approx(-0.4)
    assert ctx.options.back_crotch_adjust == pytest.approx(-1.0)
    # 侧缝收窄触及臀→膝连接轴，钳制（防内凹红线）→ 残余 ΔW < 0
    w = (ctx.line("front.thigh_line").length
         + ctx.line("back.thigh_line").length)
    assert 58.0 < w < 62.08          # 尽可能靠近但未达标
    assert "钳制" in trace and "残余" in trace
    # 结构未被破坏：后浪闭合仍成立（浪长 − 腰头宽）
    slant = ctx.line("back.rise_slant")
    arc = ctx.curve("back.rise_curve")
    assert slant.length + arc.length() == pytest.approx(
        M.back_rise - o.waistband_width)


def test_closure_until_degrades_to_single_pass():
    # --until 调版时闭环不生效（闭环需要完整版）
    o = PatternOptions(delta=1.0, thigh_limit=True)
    ctx, _ = run_with_thigh_closure(M, o, until="draw_back_hip_line")
    assert "back.thigh_line" not in ctx.sheet
    assert ctx.options.front_crotch_adjust == 0.0


def test_closure_params_overridable():
    # 双轨阈值覆盖：ΔW=−1.41（自然合计 62.08，目标 60.67）在默认阈值 0.3
    # 下走内外联动（裆尖启用）；阈值覆盖回 1.5 后回到单动侧缝（裆尖锁死）
    o_default = PatternOptions(delta=1.0, thigh_limit=True)
    ctx_d, _ = run_with_thigh_closure(_m(60.67), o_default)
    assert ctx_d.options.front_crotch_adjust < 0.0      # 默认阈值 0.3：裆宽启用
    o_high = PatternOptions(delta=1.0, thigh_limit=True, thigh_dual_track_min=1.5)
    ctx_h, _ = run_with_thigh_closure(_m(60.67), o_high)
    assert ctx_h.options.front_crotch_adjust == 0.0     # |ΔW| ≤ 1.5 锁死裆尖
    assert ctx_h.options.back_crotch_adjust == 0.0
    # 累计上限覆盖：目标 58（大差量）+ 前裆上限 0.4→0.2 → 累计钳 −0.2
    o_cap = PatternOptions(delta=1.0, thigh_limit=True,
                           thigh_front_crotch_max=0.2)
    ctx_c, _ = run_with_thigh_closure(M, o_cap)
    assert ctx_c.options.front_crotch_adjust == pytest.approx(-0.2)
    assert ctx_c.options.back_crotch_adjust == pytest.approx(-1.0)  # 后裆默认上限不变


def test_closure_param_validation():
    with pytest.raises(ValueError):
        PatternOptions(thigh_front_share=1.5)       # 分配比须在 (0, 1) 内
    with pytest.raises(ValueError):
        PatternOptions(thigh_dual_track_min=-0.1)   # 阈值不能为负


# ---------- 大腿围未录入（可选步骤自动跳过） ----------

def test_thigh_step_skipped_without_measurement():
    # 大腿围缺省（默认 0 = 未录入）：整步跳过，不上版任何毗围元素
    m = Measurements(waist=70, hip=96, knee=46, hem=36,
                     front_rise=25, back_rise=33, outseam=102)
    runner = FlowRunner(m, O)
    ctx = runner.run(FULL_FLOW, trace=True)
    assert "front.thigh_line" not in ctx.sheet
    assert "back.thigh_line" not in ctx.sheet
    assert any("draw_back_thigh_limit" in t and "跳过" in t
               for t in runner.trace_log)


def test_closure_degrades_without_thigh():
    # thigh_limit 开启但大腿围未录入：闭环退化单次执行，选项不动，
    # trace 标注跳过原因（"如果有毗围才需要做限制"）
    m = Measurements(waist=70, hip=96, knee=46, hem=36,
                     front_rise=25, back_rise=33, outseam=102)
    o = PatternOptions(delta=1.0, thigh_limit=True)
    ctx, trace = run_with_thigh_closure(m, o)
    assert "back.thigh_line" not in ctx.sheet
    assert ctx.options.front_crotch_adjust == 0.0
    assert "未录入" in trace


def test_negative_thigh_rejected():
    with pytest.raises(ValueError):
        Measurements(waist=70, hip=96, knee=46, hem=36,
                     front_rise=25, back_rise=33, outseam=102, thigh=-1.0)
