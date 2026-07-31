"""前片绘制步骤：每个函数对应手工打版的一笔。

对应 打版流程.md「前片打版实操坐标化步骤」：
  1. 建立基础参考线与"大矩形"框架（M1 已实现）
  2. 裆部结构：前小裆宽、前中内收点（已实现）
  3. 前浪弧线（已实现）
  4. 腰、侧缝、内缝、脚口（随文档补全逐步扩充）

约束（设计文档 §5.3）：
  - 一个函数只画一个元素（前浪为斜线+凹弧复合线，作为同一步骤的多个上版）；
  - 数值计算必须调用 formulas/，本层只做定位与上版；
  - 元素读取只能通过 DraftContext。
"""

from __future__ import annotations

from ..draft import DraftContext, NamedCurve, NamedLine, NamedPoint
from ..draft import curves
from ..formulas import hip as hip_f
from ..formulas import leg as leg_f
from ..formulas import crotch as crotch_f
from ..formulas import waist as waist_f
from ..geometry import LineSegment, Point
from ..params import WaistbandType

_STEP = __name__  # 步骤来源标记，由 FlowRunner 替换为函数名


def _frame_width(ctx: DraftContext) -> float:
    """大矩形框架宽 = 前片臀围线净宽 H前（前后片臀围推导.md §三.1）。"""
    m, o = ctx.measurements, ctx.options
    return hip_f.hip_front(m.hip, o.delta)


def _top_y(ctx: DraftContext) -> float:
    """版顶（腰线）高度：裤长为含腰头量，直腰头扣除腰头宽，弯腰头不扣。
    扣除口径统一走 PatternOptions.rise_on_pattern（打版流程.md 注意点 1）。"""
    return ctx.options.rise_on_pattern(ctx.measurements.outseam)


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
    """立裆参考线：人体腰节（含腰头的裤长基准）下量直裆深（= 裤长 − 直裆深）。
    直裆深按臀围推导（默认 H/4），为人体量，不随腰头扣除变化。
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
    """腰围参考线：版顶高度 = 裤长 − 腰头宽（直腰头）或 裤长（弯腰头）。
    依据：打版流程.md 前片步骤 1 + 注意点 1。"""
    y = _top_y(ctx)
    o = ctx.options
    basis = (f"裤长 − 腰头宽 {o.waistband_width}（直腰头扣除）"
             if o.waistband_type is WaistbandType.STRAIGHT else "裤长（弯腰头一体绘制）")
    return ctx.add_line("front.waist_line",
                        LineSegment.horizontal(y=y, length=_frame_width(ctx)),
                        step="draw_waist_line", basis=basis, label="腰围线")


def draw_outseam_refline(ctx: DraftContext) -> NamedLine:
    """外侧缝基础参考线：过原点的铅锤线（Y 轴），长 = 版顶高度。
    依据：打版流程.md 坐标系设定。"""
    return ctx.add_line("front.outseam_refline",
                        LineSegment.vertical(x=0.0, length=_top_y(ctx)),
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
    """内侧缝垂直参考线：过臀围宽度点的铅锤线，长 = 版顶高度。
    与外侧缝线、五条水平线共同构成前片"大矩形"基础网格。
    依据：打版流程.md 前片步骤 1。"""
    x = ctx.point("front.hip_width_point").x
    return ctx.add_line("front.inner_seam_refline",
                        LineSegment.vertical(x=x, length=_top_y(ctx)),
                        step="draw_inner_seam_refline",
                        basis="过臀围宽度点的铅锤线", label="内侧缝参考线")


# ---------- 阶段 2：裆部结构 ----------

def draw_front_crotch_width(ctx: DraftContext) -> NamedPoint:
    """前小裆宽顶点：立裆线上，从内侧缝参考线（前中基准）向裆湾方向延长 W小裆。
    W小裆 = H/20 + 修正量（前裆宽推导.md；前后片臀围推导.md §三.2）。
    依据：打版流程.md 前片步骤 2。"""
    m, o = ctx.measurements, ctx.options
    w = hip_f.crotch_front_width(m.hip, o.front_crotch_adjust)
    x = ctx.line("front.inner_seam_refline").a.x + w
    y = ctx.line("front.crotch_line").a.y
    return ctx.add_point("front.crotch_vertex", Point(x, y),
                         step="draw_front_crotch_width",
                         basis=f"W小裆 = {m.hip}/20 + {o.front_crotch_adjust} = {w:.2f}",
                         label="前小裆宽顶点")


def draw_front_center_intake(ctx: DraftContext) -> NamedPoint:
    """前中内收点：腰围线与内侧缝参考线交点（腰围内缝顶点）向侧缝方向内收。
    内收量 = (H − W)/4 × 系数 + 修正量（前中内收量推导.md §三.2；H、W 均为成品尺寸）。
    依据：打版流程.md 前片步骤 2。"""
    m, o = ctx.measurements, ctx.options
    d = waist_f.front_center_intake(m.hip, m.waist,
                                    ratio=o.front_intake_ratio,
                                    adjust=o.front_intake_adjust)
    x = ctx.line("front.inner_seam_refline").a.x - d
    y = ctx.line("front.waist_line").a.y
    return ctx.add_point("front.center_intake_point", Point(x, y),
                         step="draw_front_center_intake",
                         basis=f"内收量 = ({m.hip} − {m.waist})/4 × "
                               f"{o.front_intake_ratio} + "
                               f"{o.front_intake_adjust} = {d:.2f}",
                         label="前中内收点")


def draw_front_rise(ctx: DraftContext) -> NamedCurve:
    """前浪弧线：前中斜线（前浪顶点→臀围线内缝点）+ 裆弯凹弧（→前小裆宽顶点）。
    拐点切线连续、底裆点切线水平，总长按前浪尺寸闭合反推前浪顶点
    （前浪绘制.md §1~§4）。
    前浪为含腰头的成衣量：闭合目标统一经 rise_on_pattern 换算
    （直腰头扣腰头宽、弯腰头不扣，与版顶扣除口径一致，注意点 1）。
    依据：打版流程.md 前片步骤 3。"""
    m, o = ctx.measurements, ctx.options
    a0 = ctx.point("front.center_intake_point")
    b = Point(ctx.line("front.inner_seam_refline").a.x,
              ctx.line("front.hip_line").a.y)
    c = ctx.point("front.crotch_vertex")
    target = o.rise_on_pattern(m.front_rise)
    if o.waistband_type is WaistbandType.STRAIGHT:
        basis_len = f"前浪 {m.front_rise} − 腰头宽 {o.waistband_width} = {target:.2f}"
    else:
        basis_len = f"前浪 {m.front_rise}（弯腰头一体绘制，不扣）"
    a, arc = curves.front_rise(a0, b, c, target_length=target)
    ctx.add_point("front.hip_inner_point", b,
                  step="draw_front_rise",
                  basis="臀围线 ∩ 内侧缝参考线", label="臀围线内缝点")
    ctx.add_point("front.rise_top_point", a,
                  step="draw_front_rise",
                  basis=f"{basis_len} 闭合反推（前浪绘制.md §4）",
                  label="前浪顶点")
    ctx.add_line("front.rise_slant", LineSegment(a, b),
                 step="draw_front_rise",
                 basis="前中斜线（前浪绘制.md §1 上段）", label="前中斜线",
                 role="struct")
    return ctx.add_curve("front.rise_curve", arc,
                         step="draw_front_rise",
                         basis="裆弯凹弧：起点切线沿前中斜线、终点切线水平（前浪绘制.md §3）",
                         label="前浪弧线")


# ---------- 阶段 4：真实腰围线 ----------

def draw_front_waist_outseam_point(ctx: DraftContext) -> NamedPoint:
    """基础腰围外缝顶点：从前中内收点沿腰围基础线向侧缝方向量前片腰围长 T前。
    T前 = W/4 − balance + V前省（调节量前减后加；腰围推导.md §三.2）。
    标准牛仔裤 balance=0、V前省=0。
    该点为暂定位置（打版流程.md：后面可能会变），画腰省/侧缝弧时可能修正。
    依据：打版流程.md 前片步骤 3（绘制真实腰围线）。"""
    m, o = ctx.measurements, ctx.options
    t = waist_f.waist_front_target(m.waist, o.waist_balance, o.front_waist_dart)
    a0 = ctx.point("front.center_intake_point")
    y = ctx.line("front.waist_line").a.y
    return ctx.add_point("front.waist_outseam_base_point",
                         Point(a0.x - t, y),
                         step="draw_front_waist_outseam_point",
                         basis=f"T前 = {m.waist}/4 − {o.waist_balance} + "
                               f"{o.front_waist_dart} = {t:.2f}，自前中内收点量取",
                         label="基础腰围外缝顶点")


def draw_front_side_intake_point(ctx: DraftContext) -> NamedPoint:
    """前片侧缝内收点：腰围基础线上，自外侧缝参考线（x=0）向内量侧缝内收量 ΔX。
    ΔX = 前片臀宽 − 前片纸样腰宽 − 前中收斜（前片侧缝内收推导.md §二.1 母公式）。
    与基础腰围外缝顶点同源（锚点不同、算式等价），该点为侧缝起翘/画弧的基准。
    依据：打版流程.md 前片步骤 3（寻找前片侧缝内收点）。"""
    m, o = ctx.measurements, ctx.options
    front_hip = hip_f.hip_front(m.hip, o.delta)
    front_waist = waist_f.waist_front_target(m.waist, o.waist_balance,
                                             o.front_waist_dart)
    slant = waist_f.front_center_intake(m.hip, m.waist,
                                        ratio=o.front_intake_ratio,
                                        adjust=o.front_intake_adjust)
    dx = waist_f.side_seam_intake_front(front_hip, front_waist, slant)
    y = ctx.line("front.waist_line").a.y
    return ctx.add_point("front.side_intake_point", Point(dx, y),
                         step="draw_front_side_intake_point",
                         basis=f"ΔX = {front_hip:.2f} − {front_waist:.2f} − "
                               f"{slant:.2f} = {dx:.2f}（母公式）",
                         label="前片侧缝内收点")
