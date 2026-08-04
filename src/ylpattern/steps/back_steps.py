"""后片绘制步骤：每个函数对应手工打版的一笔。

对应 打版流程.md「后片打版实操坐标化步骤」：
  1. 建立基础参考线与"大矩形"框架（已实现）
  2. 绘制后浪：后大裆宽顶点（已实现）

与前片的关系（同一全局坐标系的一张 DraftSheet，前后片分开排版）：
  - 后片整体置于前片右侧：后片外侧缝参考线 x = 前片内侧缝参考线 x
    + 排版间距 piece_gap，互不重叠；
  - 脚口线、臀围线、膝围线、腰围线与前片**等高**（共享人体基准线；
    膝围线前后绝对等高为落裆推导.md §3.2 准则 3 的铁律），
    因此高度直接读 front.xxx 元素，保证结构上恒等；
  - 立裆线与前片横裆线等高；落裆线单独绘制：后立裆线下移落裆量
    Dc（落裆推导.md §2.1），Dc 只降裆底，不联动其他水平线；
  - 框架宽为后片臀围线净宽 H后 = H/4 + Δ（前减后加，
    前后片臀围推导.md §三.1）。

约束（设计文档 §5.3）：
  - 一个函数只画一个元素；
  - 数值计算必须调用 formulas/，本层只做定位与上版；
  - 元素读取只能通过 DraftContext。
"""

from __future__ import annotations

from ..draft import DraftContext, NamedLine, NamedPoint
from ..formulas import hip as hip_f
from ..formulas import crotch as crotch_f
from ..geometry import LineSegment, Point
from ..params import WaistbandType

_STEP = __name__  # 步骤来源标记，由 FlowRunner 替换为函数名


def _origin_x(ctx: DraftContext) -> float:
    """后片外侧缝参考线 x = 前片框架右缘 + 排版间距（前后片分开排版）。"""
    return ctx.line("front.inner_seam_refline").a.x + ctx.options.piece_gap


def _frame_width(ctx: DraftContext) -> float:
    """大矩形框架宽 = 后片臀围线净宽 H后（前后片臀围推导.md §三.1）。"""
    m, o = ctx.measurements, ctx.options
    return hip_f.hip_back(m.hip, o.delta)


def _top_y(ctx: DraftContext) -> float:
    """版顶（腰线）高度：与前片同一扣除口径，统一走 rise_on_pattern
    （打版流程.md 注意点 1）。后翘在后续后腰步骤追加，框架阶段不抬。"""
    return ctx.options.rise_on_pattern(ctx.measurements.outseam)


# ---------- 阶段 1：基础参考线与"大矩形"框架 ----------

def draw_back_hem_line(ctx: DraftContext) -> NamedLine:
    """脚口参考线：与前片脚口线等高（y=0 共享基准），长 = 后片框架宽。
    依据：打版流程.md 后片步骤 1（五条水平参考线）。"""
    y = ctx.line("front.hem_line").a.y
    return ctx.add_line("back.hem_line",
                        LineSegment.horizontal(y=y, x0=_origin_x(ctx),
                                               length=_frame_width(ctx)),
                        step="draw_back_hem_line",
                        basis="与 front.hem_line 等高（共享人体基准线）",
                        label="后脚口线")


def draw_back_crotch_line(ctx: DraftContext) -> NamedLine:
    """立裆参考线：与前片横裆线等高（立裆深为人体量，前后片同深）。
    落裆下移画在单独的落裆线上，不动立裆线。
    依据：打版流程.md 后片步骤 1（五条水平参考线）。"""
    y = ctx.line("front.crotch_line").a.y
    return ctx.add_line("back.crotch_line",
                        LineSegment.horizontal(y=y, x0=_origin_x(ctx),
                                               length=_frame_width(ctx)),
                        step="draw_back_crotch_line",
                        basis="与 front.crotch_line 等高（立裆深前后相同）",
                        label="后立裆线")


def draw_back_crotch_drop_line(ctx: DraftContext) -> NamedLine:
    """落裆线：后立裆线下移落裆量 Dc = H/100 + Δc，确定后大裆尖高度。
    落裆只降裆底，膝围线等其他水平线禁止联动下移（落裆推导.md §3.2）。
    依据：落裆推导.md §2.1、§3.2 准则 1（下落垂移）。"""
    m, o = ctx.measurements, ctx.options
    dc = crotch_f.crotch_drop(m.hip, o.crotch_drop_adjust)
    y = ctx.line("back.crotch_line").a.y - dc
    return ctx.add_line("back.crotch_drop_line",
                        LineSegment.horizontal(y=y, x0=_origin_x(ctx),
                                               length=_frame_width(ctx)),
                        step="draw_back_crotch_drop_line",
                        basis=f"Dc = {m.hip}/100 + {o.crotch_drop_adjust} = "
                              f"{dc:.2f}（落裆推导.md §2.1）",
                        label="落裆线")


def draw_back_hip_line(ctx: DraftContext) -> NamedLine:
    """臀围参考线：与前片臀围线等高（裆上高为人体固定常数，
    不随落裆下移；落裆推导.md §3 空间关系）。
    依据：打版流程.md 后片步骤 1。"""
    y = ctx.line("front.hip_line").a.y
    return ctx.add_line("back.hip_line",
                        LineSegment.horizontal(y=y, x0=_origin_x(ctx),
                                               length=_frame_width(ctx)),
                        step="draw_back_hip_line",
                        basis="与 front.hip_line 等高（裆上高恒定，不随落裆下移）",
                        label="后臀围线")


def draw_back_knee_line(ctx: DraftContext) -> NamedLine:
    """膝围参考线：与前片膝围线绝对等高齐平，禁止随落裆联动下垂
    （落裆推导.md §3.2 准则 3）。
    依据：打版流程.md 后片步骤 1。"""
    y = ctx.line("front.knee_line").a.y
    return ctx.add_line("back.knee_line",
                        LineSegment.horizontal(y=y, x0=_origin_x(ctx),
                                               length=_frame_width(ctx)),
                        step="draw_back_knee_line",
                        basis="与 front.knee_line 等高（落裆推导.md §3.2 准则 3）",
                        label="后膝围线")


def draw_back_waist_line(ctx: DraftContext) -> NamedLine:
    """腰围参考线：与前片腰线同高（版顶 = 裤长 − 腰头宽，直腰头；
    弯腰头不扣）。后翘量在后续后腰步骤追加，框架阶段不抬。
    依据：打版流程.md 后片步骤 1 + 注意点 1。"""
    y = ctx.line("front.waist_line").a.y
    o = ctx.options
    basis = ("与 front.waist_line 等高：裤长 − 腰头宽 "
             f"{o.waistband_width}（直腰头扣除）"
             if o.waistband_type is WaistbandType.STRAIGHT
             else "与 front.waist_line 等高：裤长（弯腰头一体绘制）")
    return ctx.add_line("back.waist_line",
                        LineSegment.horizontal(y=y, x0=_origin_x(ctx),
                                               length=_frame_width(ctx)),
                        step="draw_back_waist_line", basis=basis,
                        label="后腰围线")


def draw_back_outseam_refline(ctx: DraftContext) -> NamedLine:
    """外侧缝基础参考线：后片自己的铅锤基准线，x = 前片框架右缘 + 排版
    间距 piece_gap，长 = 版顶高度。
    依据：打版流程.md 坐标系设定（后片平移排版，局部坐标系同向前片）。"""
    x = _origin_x(ctx)
    return ctx.add_line("back.outseam_refline",
                        LineSegment.vertical(x=x, length=_top_y(ctx)),
                        step="draw_back_outseam_refline",
                        basis=f"前片右缘 + 排版间距 {ctx.options.piece_gap}"
                              f" = {x:.2f}（前后片分开排版）",
                        label="后外侧缝参考线")


def draw_back_hip_width(ctx: DraftContext) -> NamedPoint:
    """后片臀围宽度点：从后外侧缝参考线向右量取 H后 = H/4 + Δ（前减后加）。
    依据：前后片臀围推导.md §三.1；打版流程.md 后片步骤 1。"""
    m, o = ctx.measurements, ctx.options
    w = hip_f.hip_back(m.hip, o.delta)
    x = _origin_x(ctx) + w
    return ctx.add_point("back.hip_width_point", Point(x, 0.0),
                         step="draw_back_hip_width",
                         basis=f"H后 = {m.hip}/4 + {o.delta} = {w:.2f}",
                         label="后臀围宽度点")


def draw_back_inner_seam_refline(ctx: DraftContext) -> NamedLine:
    """内侧缝垂直参考线：过后臀围宽度点的铅锤线，长 = 版顶高度。
    与外侧缝线、五条水平线共同构成后片"大矩形"基础网格。
    依据：打版流程.md 后片步骤 1。"""
    x = ctx.point("back.hip_width_point").x
    return ctx.add_line("back.inner_seam_refline",
                        LineSegment.vertical(x=x, length=_top_y(ctx)),
                        step="draw_back_inner_seam_refline",
                        basis="过后臀围宽度点的铅锤线", label="后内侧缝参考线")


# ---------- 阶段 2：绘制后浪 ----------

def draw_back_crotch_width(ctx: DraftContext) -> NamedPoint:
    """后大裆宽顶点：从后中基准（内侧缝参考线）沿落裆线向裆湾方向
    延长 W大裆。W大裆 = H/10 + 修正量（前后裆宽推导.md §三；
    前后片臀围推导.md §三.2）。
    顶点落在落裆线上（非立裆线）：落裆线下移 Dc 就是为了确定
    后大裆尖水平高度（落裆推导.md §3.2 准则 1）。
    依据：打版流程.md 后片步骤 2（绘制后浪）。"""
    m, o = ctx.measurements, ctx.options
    w = hip_f.crotch_back_width(m.hip, o.back_crotch_adjust)
    x = ctx.line("back.inner_seam_refline").a.x + w
    y = ctx.line("back.crotch_drop_line").a.y
    return ctx.add_point("back.crotch_vertex", Point(x, y),
                         step="draw_back_crotch_width",
                         basis=f"W大裆 = {m.hip}/10 + {o.back_crotch_adjust} = "
                               f"{w:.2f}，落裆线高度（落裆推导.md §3.2）",
                         label="后大裆宽顶点")
