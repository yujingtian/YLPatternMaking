"""后片绘制步骤：每个函数对应手工打版的一笔。

对应 打版流程.md「后片打版实操坐标化步骤」：
  1. 建立基础参考线与"大矩形"框架（已实现）
  2. 绘制后浪：后大裆宽顶点、后中内收点、后浪弧线（已实现）
  3. 绘制后片腰头（已实现）
  4. 绘制后臀围线（已实现）
  5. 裤中线（已实现）
  6. 确定后片膝围和脚口宽度（已实现）

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

from ..draft import DraftContext, NamedCurve, NamedLine, NamedPoint
from ..draft import curves
from ..formulas import hip as hip_f
from ..formulas import crotch as crotch_f
from ..formulas import leg as leg_f
from ..formulas import waist as waist_f
from ..geometry import CubicBezier, LineSegment, Point
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


def draw_back_center_intake(ctx: DraftContext) -> NamedPoint:
    """后中内收点（腰头倒量点）：先量版上实际臀腰高 H_v（后腰围线 −
    后臀围线），按比例折算内收量 D_h = H_v × X/15，再从腰围内缝顶点
    向裤片主体方向（−X）水平量取 D_h。
    15:X 为斜率比例：斜率锁定、内收量随实际臀腰高浮动
    （后中内收点推导.md §一 核心公式、§三 三步定位法第 2 步）。
    依据：打版流程.md 后片步骤 2（寻找后中内收点）。"""
    o = ctx.options
    h_v = ctx.line("back.waist_line").a.y - ctx.line("back.hip_line").a.y
    d = waist_f.back_center_intake(h_v, o.back_intake)
    x = ctx.line("back.inner_seam_refline").a.x - d
    y = ctx.line("back.waist_line").a.y
    return ctx.add_point("back.center_intake_point", Point(x, y),
                         step="draw_back_center_intake",
                         basis=f"D_h = {h_v:.2f} × {o.back_intake}/15 = "
                               f"{d:.2f}（后中内收点推导.md §一）",
                         label="后中内收点")


def draw_back_rise(ctx: DraftContext) -> NamedCurve:
    """后浪弧线：后中斜线（后浪顶点→臀围线内缝点）+ 大裆弯深凹弧
    （→后大裆宽顶点）。拐点切线连续、底裆点切线水平，控制柄
    k1 = α·|BC|、k2 = β·|BC|（深于前浪），总长按后浪尺寸闭合
    反推后浪顶点（后浪绘制.md §1~§4；延伸量即后翘的自然结果）。
    后浪为含腰头的成衣量：闭合目标统一经 rise_on_pattern 换算
    （直腰头扣腰头宽、弯腰头不扣，与前片扣除口径一致，注意点 1）。
    依据：打版流程.md 后片步骤 2（绘制后浪弧线）。"""
    m, o = ctx.measurements, ctx.options
    a0 = ctx.point("back.center_intake_point")
    b = Point(ctx.line("back.inner_seam_refline").a.x,
              ctx.line("back.hip_line").a.y)
    c = ctx.point("back.crotch_vertex")
    target = o.rise_on_pattern(m.back_rise)
    if o.waistband_type is WaistbandType.STRAIGHT:
        basis_len = f"后浪 {m.back_rise} − 腰头宽 {o.waistband_width} = {target:.2f}"
    else:
        basis_len = f"后浪 {m.back_rise}（弯腰头一体绘制，不扣）"
    a, arc = curves.back_rise(a0, b, c, target_length=target,
                              alpha=o.back_rise_alpha,
                              beta=o.back_rise_beta)
    ctx.add_point("back.hip_inner_point", b,
                  step="draw_back_rise",
                  basis="臀围线 ∩ 内侧缝参考线", label="后臀围线内缝点")
    ctx.add_point("back.rise_top_point", a,
                  step="draw_back_rise",
                  basis=f"{basis_len} 闭合反推（后浪绘制.md §4）",
                  label="后浪顶点")
    ctx.add_line("back.rise_slant", LineSegment(a, b),
                 step="draw_back_rise",
                 basis="后中斜线（后浪绘制.md §1 上段）", label="后中斜线",
                 role="struct")
    return ctx.add_curve("back.rise_curve", arc,
                         step="draw_back_rise",
                         basis=f"大裆弯深凹弧：k1 = {o.back_rise_alpha}·|BC|，"
                               f"k2 = {o.back_rise_beta}·|BC|，起点切线沿"
                               "后中斜线、终点切线水平（后浪绘制.md §3）",
                         label="后浪弧线")


# ---------- 阶段 3：绘制后片腰头 ----------

def draw_back_waistline(ctx: DraftContext) -> NamedLine:
    """后腰头构造（定长斜截法，后腰头绘制推导.md §一）：
    起翘等高辅助线（与前片腰围外缝顶点等高、平行于后腰围基础线）
    + 以后浪顶点为圆心、后腰长 L 为半径斜截辅助线，交点即后腰头
    外缝顶点 B；|AB| = L 为构造直线约束（A = 后浪顶点）。
    L = W/4 + balance + V后省（腰围推导.md §三.2，前减后加口径）。
    本步产物为构造线；最终轮廓由 draw_back_waistband_arc 的弧线取代。
    依据：打版流程.md 后片步骤 3。"""
    m, o = ctx.measurements, ctx.options
    a = ctx.point("back.rise_top_point")
    waist_y = ctx.line("back.waist_line").a.y
    aux_y = ctx.point("front.waist_side_point").y   # 与前片起翘等高
    bc_drop = waist_y - a.y          # 后中落差（A 高出基础线为负）
    waist_len = waist_f.waist_back_target(m.waist, o.waist_balance,
                                          o.back_waist_dart)
    span = waist_f.waistline_horizontal_span(waist_len, aux_y - waist_y,
                                             bc_drop)
    b = Point(a.x - span, aux_y)
    ctx.add_line("back.waist_aux_line",
                 LineSegment.horizontal(y=aux_y, x0=_origin_x(ctx),
                                        length=_frame_width(ctx)),
                 step="draw_back_waistline",
                 basis="与前片腰围外缝顶点等高的起翘辅助线"
                       "（后腰头绘制推导.md §一.1）",
                 label="后腰起翘辅助线")
    ctx.add_point("back.waist_side_point", b,
                  step="draw_back_waistline",
                  basis=f"x = {a.x:.2f} − sqrt({waist_len:.2f}² − "
                        f"({aux_y - a.y:.2f})²)（定长斜截，推导.md §一.2）",
                  label="后腰头外缝顶点")
    return ctx.add_line("back.waistline", LineSegment(b, a),
                        step="draw_back_waistline",
                        basis=f"|AB| = 后腰长 {waist_len:.2f}（后腰头绘制推导.md"
                              " §一.2，构造线）",
                        label="后腰头构造线", role="ref")


def draw_back_waistband_arc(ctx: DraftContext) -> NamedCurve:
    """后腰头线弧（后腰头绘制推导.md §一.3 形态优化）：
    以构造弦 AB 为基准微微下凹（贴合腰背背弓），后浪顶点 A 处切线
    与后中斜线严格 90° 正交（保留直角平顺段，保证左右后片后中缝合
    后腰上口平滑无尖角）；外缝端 B 沿弦向顺出，待后侧缝弧线步骤
    圆顺过渡。腰长按两端点直线距离闭合（上一步构造线已保证）。
    依据：打版流程.md 后片步骤 3。"""
    m, o = ctx.measurements, ctx.options
    a = ctx.point("back.rise_top_point")
    b = ctx.point("back.waist_side_point")
    waist_len = waist_f.waist_back_target(m.waist, o.waist_balance,
                                          o.back_waist_dart)
    # A 点切线 ⟂ 后中斜线（90° 正交，推导.md §一.3 核心要点）
    rise_dir = (ctx.point("back.hip_inner_point") - a).normalized()
    t_a = rise_dir.perpendicular()
    if t_a.dx * (b.x - a.x) + t_a.dy * (b.y - a.y) < 0:
        t_a = t_a.scale(-1)          # 取朝向 B 的一侧
    p1 = a + t_a.scale(o.waist_rect_len)          # §二 直角平顺段
    # 弦中点下凹（补偿 P1 偏离，弧中点下凹 = sag，与前片同口径）
    p2 = curves.waist_sag_p2(a, b, p1, at=0.5,
                             sag=o.back_waist_curve_sag)
    return ctx.add_curve("back.waistline_arc", CubicBezier(a, p1, p2, b),
                         step="draw_back_waistband_arc",
                         basis="微凹后腰弧：A 点切线 ⟂ 后中斜线（90° 正交），"
                               f"弦中点下凹 {o.back_waist_curve_sag}"
                               "（后腰头绘制推导.md §一.3）",
                         label="后腰头线弧")


# ---------- 阶段 4：绘制后臀围线 ----------

def draw_back_hip_final(ctx: DraftContext) -> NamedLine:
    """最终后臀围线（最终后臀围线推导.md §一，三步法）：
    1) 后臀围内缝顶点沿后中斜线同距上移 —— 上移向量 = 后中内收点→后浪
       顶点的位移 d（与后腰起翘同步，立体包容臀大肌凸量）；
    2) 定长斜截：以上移后的内缝顶点为圆心、后臀围长 H后为半径，斜截
       原始后臀围水平基础线，交点即最终后臀围外缝顶点（外缝点回落
       基础线，保证与前片侧缝臀围零高差拼接）；
    3) 两点虚线相连，内高外低，弦长严格 = H后。
    依据：打版流程.md 后片步骤 4。"""
    m, o = ctx.measurements, ctx.options
    a0 = ctx.point("back.center_intake_point")
    a = ctx.point("back.rise_top_point")
    move = a - a0                          # 后中斜线上的起翘位移
    b = ctx.point("back.hip_inner_point") + move
    hip_y = ctx.line("back.hip_line").a.y
    hip_len = hip_f.hip_back(m.hip, o.delta)
    span = hip_f.back_hip_line_span(hip_len, b.y - hip_y)
    out = Point(b.x - span, hip_y)
    ctx.add_point("back.hip_inner_final", b,
                  step="draw_back_hip_final",
                  basis=f"沿后中斜线上移 {move.length:.2f}"
                        "（与后腰起翘同距，推导.md §一.1）",
                  label="最终后臀围内缝顶点")
    ctx.add_point("back.hip_outseam_point", out,
                  step="draw_back_hip_final",
                  basis=f"x = {b.x:.2f} − sqrt({hip_len:.2f}² − "
                        f"({b.y - hip_y:.2f})²)（定长斜截，推导.md §一.2）",
                  label="最终后臀围外缝顶点")
    return ctx.add_line("back.hip_line_final", LineSegment(b, out),
                        step="draw_back_hip_final",
                        basis=f"|内缝顶点→外缝顶点| = 后臀围长 {hip_len:.2f}"
                              "（内高外低，虚线连接，推导.md §一.3）",
                        label="最终后臀围线", role="ref")


# ---------- 阶段 5：裤中线 ----------

def draw_back_crease_line(ctx: DraftContext) -> NamedLine:
    """后片裤中线（烫迹线/丝缕线）：继承前片裤中线距前侧缝的距离 X前，
    加外侧缝单边放大量 Δ = (后脚口总宽 − 前脚口总宽)/2，再加后片自定义
    调节量 e_back，从后外侧缝参考线向裆端量取 X后 = X前 + Δ + e_back
    定点（立裆线上）；过该点作垂直于脚口线的直线，下抵脚口线、
    上抵腰围线（场景 B：CAD 独立制图法，前后片裤中线推导.md §三/§四；
    切勿平分后横裆，§一.2）。
    依据：打版流程.md 后片步骤 5（裤中线）。"""
    m, o = ctx.measurements, ctx.options
    x_front = (ctx.point("front.crease_point").x
               - ctx.line("front.outseam_refline").a.x)
    expansion = (leg_f.hem_back(m.hem, o.hem_adjust)
                 - leg_f.hem_front(m.hem, o.hem_adjust)) / 2
    x_local = leg_f.crease_back_x(x_front, expansion, o.back_crease_e)
    x = _origin_x(ctx) + x_local
    crotch_y = ctx.line("back.crotch_line").a.y
    waist_y = ctx.line("back.waist_line").a.y
    ctx.add_point("back.crease_point", Point(x, crotch_y),
                  step="draw_back_crease_line",
                  basis=f"X后 = X前 {x_front:.2f} + Δ {expansion:.2f} + "
                        f"e {o.back_crease_e} = {x_local:.2f}"
                        "（裤中线推导.md §三 场景 B）",
                  label="后裤中线立裆点")
    return ctx.add_line("back.crease_line",
                        LineSegment(Point(x, 0.0), Point(x, waist_y)),
                        step="draw_back_crease_line",
                        basis="过后裤中线立裆点作脚口线垂线，脚口线 → 腰围线",
                        label="后裤中线")


# ---------- 阶段 6：膝围、脚口宽度 ----------

def draw_back_knee_hem_widths(ctx: DraftContext) -> NamedCurve:
    """后片膝围/脚口内外缝顶点：以后裤中线为对称轴向两侧各延伸片宽一半。
    后片膝围宽 K后 = K/2 + δ、后片脚口宽 B后 = B/2 + δ
    （先平分再前减后加，脚口膝围外缝点推导.md §三.1）。
    脚口内外缝顶点以浅弧相连为脚口结构线，弧高 back_hem_arc_sag
    （0 = 直线，正值向下凸出裤片，与前片独立录入）；膝围只定点、不连线。
    依据：打版流程.md 后片步骤 6（确定后片膝围和脚口宽度）。"""
    m, o = ctx.measurements, ctx.options
    x_c = ctx.line("back.crease_line").a.x
    knee_y = ctx.line("back.knee_line").a.y
    d_knee = leg_f.knee_back(m.knee, o.knee_adjust) / 2
    d_hem = leg_f.hem_back(m.hem, o.hem_adjust) / 2

    ctx.add_point("back.knee_outseam_point", Point(x_c - d_knee, knee_y),
                  step="draw_back_knee_hem_widths",
                  basis=f"d后膝 = ({m.knee}/2 + {o.knee_adjust})/2 = {d_knee:.2f}（裤中线对称，推导.md §三.1）",
                  label="后膝围外缝点")
    ctx.add_point("back.knee_inseam_point", Point(x_c + d_knee, knee_y),
                  step="draw_back_knee_hem_widths",
                  basis=f"d后膝 = {d_knee:.2f}（内缝方向 +X）",
                  label="后膝围内缝点")
    hem_out = ctx.add_point("back.hem_outseam_point", Point(x_c - d_hem, 0.0),
                            step="draw_back_knee_hem_widths",
                            basis=f"d后脚 = ({m.hem}/2 + {o.hem_adjust})/2 = {d_hem:.2f}（裤中线对称，推导.md §三.1）",
                            label="后脚口外缝顶点")
    hem_in = ctx.add_point("back.hem_inseam_point", Point(x_c + d_hem, 0.0),
                           step="draw_back_knee_hem_widths",
                           basis=f"d后脚 = {d_hem:.2f}（内缝方向 +X）",
                           label="后脚口内缝顶点")
    return ctx.add_curve("back.hem",
                         curves.sag_curve(hem_out.geom, hem_in.geom,
                                          sag=-o.back_hem_arc_sag),
                         step="draw_back_knee_hem_widths",
                         basis=f"脚口内外缝顶点浅弧相连，弧高 {o.back_hem_arc_sag}"
                               "（正值向下凸，打版流程.md 后片步骤 6）",
                         label="后脚口线")
