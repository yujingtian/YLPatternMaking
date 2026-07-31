"""前片绘制步骤：每个函数对应手工打版的一笔。

对应 打版流程.md「前片打版实操坐标化步骤」：
  1. 建立基础参考线与"大矩形"框架（本文件 M1 已实现）
  2. 裆部结构 / 3. 腰、侧缝、内缝、脚口（随文档补全逐步扩充）

约束（设计文档 §5.3）：
  - 一个函数只画一个元素；
  - 数值计算必须调用 formulas/，本层只做定位与上版；
  - 元素读取只能通过 DraftContext。
"""

from __future__ import annotations

from ..draft import DraftContext, NamedLine, NamedPoint
from ..formulas import hip as hip_f
from ..formulas import leg as leg_f
from ..formulas import crotch as crotch_f
from ..geometry import LineSegment, Point

_STEP = __name__  # 步骤来源标记，由 FlowRunner 替换为函数名


def _frame_width(ctx: DraftContext) -> float:
    """大矩形框架宽 = 前片臀围线净宽 H前（前后片臀围推导.md §三.1）。"""
    m, o = ctx.measurements, ctx.options
    return hip_f.hip_front(m.hip, o.delta)


def _rise_depth(ctx: DraftContext) -> float:
    """直裆深 = H × rise_ratio + rise_adjust（默认 H/4）。"""
    m, o = ctx.measurements, ctx.options
    return crotch_f.rise_depth(m.hip, o.rise_ratio, o.rise_adjust)


# ---------- 阶段 1：基础参考线与"大矩形"框架 ----------

def draw_hem_line(ctx: DraftContext) -> NamedLine:
    """脚口参考线：过原点 O(0,0) 的水平线，长 = 框架宽。
    依据：打版流程.md 坐标系设定（原点 = 外侧缝 ∩ 脚口线）。"""
    return ctx.add_line("front.hem_line",
                        LineSegment.horizontal(y=0.0, length=_frame_width(ctx)),
                        step="draw_hem_line", basis="打版流程.md 坐标系设定", label="脚口线")


def draw_crotch_line(ctx: DraftContext) -> NamedLine:
    """立裆参考线：腰围线下量直裆深（= 裤长 − 直裆深）。
    直裆深按臀围推导（默认 H/4），非直接等于前浪。
    依据：打版流程.md 前片步骤 1（五条水平参考线）。"""
    m = ctx.measurements
    y = m.outseam - _rise_depth(ctx)
    return ctx.add_line("front.crotch_line",
                        LineSegment.horizontal(y=y, length=_frame_width(ctx)),
                        step="draw_crotch_line", basis="裤长 − 直裆深(H/4)", label="立裆线")


def draw_hip_line(ctx: DraftContext) -> NamedLine:
    """臀围参考线：立裆线上移直裆深的 1/3（经验值）。
    依据：打版流程.md 前片步骤 1。"""
    crotch_y = ctx.line("front.crotch_line").a.y
    y = crotch_y + _rise_depth(ctx) / 3
    return ctx.add_line("front.hip_line",
                        LineSegment.horizontal(y=y, length=_frame_width(ctx)),
                        step="draw_hip_line", basis="立裆线 + 直裆深/3（经验）", label="臀围线")


def draw_knee_line(ctx: DraftContext) -> NamedLine:
    """膝围参考线：脚口线与立裆线中点上移 3cm（经验值，可调）。
    依据：打版流程.md 前片步骤 1；formulas/leg.knee_line_height。"""
    hem_y = ctx.line("front.hem_line").a.y
    crotch_y = ctx.line("front.crotch_line").a.y
    y = leg_f.knee_line_height(hem_y, crotch_y)
    return ctx.add_line("front.knee_line",
                        LineSegment.horizontal(y=y, length=_frame_width(ctx)),
                        step="draw_knee_line",
                        basis="(脚口+立裆)/2 + 3cm（经验）", label="膝围线")


def draw_waist_line(ctx: DraftContext) -> NamedLine:
    """腰围参考线：脚口线上移裤长。
    依据：打版流程.md 前片步骤 1。"""
    m = ctx.measurements
    return ctx.add_line("front.waist_line",
                        LineSegment.horizontal(y=m.outseam,
                                               length=_frame_width(ctx)),
                        step="draw_waist_line", basis="裤长", label="腰围线")


def draw_outseam_refline(ctx: DraftContext) -> NamedLine:
    """外侧缝基础参考线：过原点的铅锤线（Y 轴），长 = 裤长。
    依据：打版流程.md 坐标系设定。"""
    return ctx.add_line("front.outseam_refline",
                        LineSegment.vertical(x=0.0,
                                             length=ctx.measurements.outseam),
                        step="draw_outseam_refline", basis="打版流程.md 坐标系设定", label="外侧缝参考线")


def draw_front_hip_width(ctx: DraftContext) -> NamedPoint:
    """臀围宽度点：从外侧缝参考线向右量取 H前 = H/4 − Δ。
    依据：前后片臀围推导.md §三.1。"""
    m, o = ctx.measurements, ctx.options
    w = hip_f.hip_front(m.hip, o.delta)
    return ctx.add_point("front.hip_width_point", Point(w, 0.0),
                         step="draw_front_hip_width",
                         basis=f"H前 = {m.hip}/4 − {o.delta} = {w:.2f}", label="臀围宽度点")


def draw_inner_seam_refline(ctx: DraftContext) -> NamedLine:
    """内侧缝垂直参考线：过臀围宽度点的铅锤线，长 = 裤长。
    与外侧缝线、五条水平线共同构成前片"大矩形"基础网格。
    依据：打版流程.md 前片步骤 1。"""
    x = ctx.point("front.hip_width_point").x
    return ctx.add_line("front.inner_seam_refline",
                        LineSegment.vertical(
                            x=x, length=ctx.measurements.outseam),
                        step="draw_inner_seam_refline",
                        basis="过臀围宽度点的铅锤线", label="内侧缝参考线")
