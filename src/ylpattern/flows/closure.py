"""毗围闭环修正驱动（前后片毗围推导.md §三；打版流程.md 后片步骤 8）。

闭环策略（用户确认的"闭环重跑"机制）：
  整版绘制 → 读前/后毗围线实测总长 → ΔW = 目标 − 实测 →
  按 §三 双轨分流把修正量换算为选项增量（裆尖调整 1:1 落在
  front/back_crotch_adjust；侧缝调整经 Q1 控制点精确解落在
  前后 outseam_arc_dx）→ 用调整后选项整版重跑，迭代至收敛。

选择重跑而非版上补丁的原因：裆尖移动会级联影响浪长闭合、裤中线、
膝脚口等全部下游结构，整版重跑让所有结构不变量（浪长闭合、
膝口 C1 连续）自动保持，"不破坏裤子原本的结构"（打版流程.md 步骤 8）。
"""

from __future__ import annotations

from dataclasses import replace

from ..draft import DraftContext
from ..formulas import thigh as thigh_f
from ..geometry import p1_influence
from ..params import Measurements, PatternOptions
from .back_flow import FULL_FLOW
from .runner import FlowRunner


def _outseam_dx_delta(ctx: DraftContext, side: str, dw_out: float,
                      measure_y: float) -> tuple[float, bool]:
    """外缝 δx 选项增量（正 = 外凸加大 = 毗围加宽），返回 (增量, 是否触发钳制)。

    贝塞尔对控制点线性：Q1.x 平移 Δ 时测量高度处曲线 x 平移
    p1_influence(t)·Δ（y 不变、t 不变），单步精确；Q1.x = X臀 − δx，
    故 δx 增量 = −ΔQ1x。收窄时经 clamp_outseam_target 钳制在
    臀→膝线性连接轴上（防内凹红线，推导.md §三.2）。
    """
    curve = ctx.curve(f"{side}.outseam_upper")
    t = curve.t_at_y(measure_y)
    x_cur = curve.point_at(t).x
    hip = ctx.point(f"{side}.hip_outseam_point")
    knee = ctx.point(f"{side}.knee_outseam_point")
    x_chord = hip.x + (knee.x - hip.x) * (hip.y - measure_y) / (hip.y - knee.y)
    x_target = thigh_f.clamp_outseam_target(x_cur, dw_out, x_chord)
    clamped = abs(x_target - (x_cur - dw_out)) > 1e-9
    return -(x_target - x_cur) / p1_influence(t), clamped


def _corrected_options(ctx: DraftContext, o_orig: PatternOptions,
                       o_cur: PatternOptions,
                       dw: float) -> tuple[PatternOptions, list[str]]:
    """按 ΔW 计算修正后的选项（推导.md §三 双轨分流）。

    裆尖调整量按累计钳制（极值红线针对全程累计调整量）：相对用户
    原始选项的累计增量不得突破 ±0.4 / ±1.0；本轮实际增量 = 钳制后
    累计 − 已调累计，钳制残余经 outseam_shifts 回流侧缝。
    """
    fc_applied = o_cur.front_crotch_adjust - o_orig.front_crotch_adjust
    bc_applied = o_cur.back_crotch_adjust - o_orig.back_crotch_adjust
    fc = (thigh_f.cap_crotch_total(
        fc_applied,
        thigh_f.front_crotch_shift(dw, o_cur.thigh_dual_track_min,
                                   o_cur.thigh_front_crotch_coef,
                                   o_cur.thigh_front_crotch_max),
        o_cur.thigh_front_crotch_max) - fc_applied)
    bc = (thigh_f.cap_crotch_total(
        bc_applied,
        thigh_f.back_crotch_shift(dw, o_cur.thigh_dual_track_min,
                                  o_cur.thigh_back_crotch_coef,
                                  o_cur.thigh_back_crotch_max),
        o_cur.thigh_back_crotch_max) - bc_applied)
    f_out, b_out = thigh_f.outseam_shifts(
        dw, fc, bc,
        split_max=o_cur.thigh_piece_split_max,
        share_large=o_cur.thigh_front_share)
    measure_y = ctx.line("front.crotch_line").a.y - o_cur.thigh_measure_offset
    f_dx, f_clamped = _outseam_dx_delta(ctx, "front", f_out, measure_y)
    b_dx, b_clamped = _outseam_dx_delta(ctx, "back", b_out, measure_y)
    notes = [f"前裆 {fc:+.2f}（累计 {fc_applied + fc:+.2f}）/ "
             f"后裆 {bc:+.2f}（累计 {bc_applied + bc:+.2f}）/ "
             f"前侧缝 {f_out:+.2f} / 后侧缝 {b_out:+.2f}"]
    if f_clamped or b_clamped:
        notes.append("侧缝收窄触及臀→膝连接轴，已钳制（防内凹红线）")
    return replace(o_cur,
                   front_crotch_adjust=o_cur.front_crotch_adjust + fc,
                   back_crotch_adjust=o_cur.back_crotch_adjust + bc,
                   outseam_arc_dx=o_cur.outseam_arc_dx + f_dx,
                   back_outseam_arc_dx=o_cur.back_outseam_arc_dx + b_dx), notes


def run_with_thigh_closure(m: Measurements, o: PatternOptions, *,
                           until: str | None = None, trace: bool = False,
                           max_iter: int | None = None,
                           tol: float | None = None
                           ) -> tuple[DraftContext, str]:
    """整版绘制 + 毗围闭环修正。

    until 指定、thigh_limit 关闭、或大腿围未录入（thigh = 0，可选步骤
    自动跳过，打版流程.md 后片步骤 8）时退化为单次执行
    （闭环需要完整版和毗围目标）。
    max_iter / tol 缺省取 PatternOptions.thigh_max_iter / thigh_tol。
    返回 (最终 DraftContext, 追踪文本)：每轮迭代记录 ΔW 与修正量，
    收敛或达到 max_iter 为止；未收敛时残余 ΔW 见末轮记录（尽可能
    靠近目标，不破坏结构）。
    """
    if until or not o.thigh_limit or m.thigh <= 0:
        runner = FlowRunner(m, o)
        ctx = runner.run(FULL_FLOW, until=until, trace=trace)
        note = ("[thigh_closure] 大腿围未录入（thigh = 0），"
                "毗围限制可选步骤已跳过\n"
                if o.thigh_limit and m.thigh <= 0 and not until else "")
        return ctx, note + runner.trace_text()

    if max_iter is None:
        max_iter = o.thigh_max_iter
    if tol is None:
        tol = o.thigh_tol

    opts = o
    log: list[str] = []
    ctx: DraftContext | None = None
    prev_dw: float | None = None
    for it in range(1, max_iter + 1):
        runner = FlowRunner(m, opts)
        ctx = runner.run(FULL_FLOW, trace=trace)
        w_f = ctx.line("front.thigh_line").length
        w_b = ctx.line("back.thigh_line").length
        dw = m.thigh - (w_f + w_b)
        log.append(f"[thigh_closure] 第 {it} 轮：实测 {w_f + w_b:.2f} = "
                   f"前 {w_f:.2f} + 后 {w_b:.2f}，ΔW = {dw:+.2f}")
        if abs(dw) <= tol:
            log.append(f"[thigh_closure] 收敛（|ΔW| ≤ {tol}）")
            break
        if prev_dw is not None and abs(dw) >= abs(prev_dw) - 1e-9:
            log.append(f"[thigh_closure] 实测已无改善，残余 ΔW = {dw:+.2f}"
                       "（红线钳制，尽可能靠近）")
            break
        if it == max_iter:
            log.append(f"[thigh_closure] 已达最大迭代 {max_iter} 轮，"
                       f"残余 ΔW = {dw:+.2f}（红线钳制，尽可能靠近）")
            break
        prev_dw = dw
        opts, notes = _corrected_options(ctx, o, opts, dw)
        log.append(f"[thigh_closure] 修正：{'；'.join(notes)} → 整版重跑")
    assert ctx is not None
    if trace:
        log.append(runner.trace_text())
    return ctx, "\n".join(log)
