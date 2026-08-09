"""后片绘制步骤：每个函数对应手工打版的一笔。

对应 打版流程.md「后片打版实操坐标化步骤」：
  1. 建立基础参考线与"大矩形"框架（已实现）
  2. 绘制后浪：后大裆宽顶点、后中内收点、后浪弧线（已实现）
  3. 绘制后片腰头（已实现）
  4. 绘制后臀围线（已实现）
  5. 裤中线（已实现）
  6. 确定后片膝围和脚口宽度（已实现）
  7. 外缝、内缝线绘制（已实现）
  8. 毗围限制（已实现：测量上版；闭环修正由 flows/closure.py 驱动）
  9. 后片绘制省（已实现：可选步骤，开关开启且 V后省 > 0 才绘制）

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
    L = W/4 + balance + V后省（腰围推导.md §三.2，前减后加口径；
    V后省即 back_waist_dart，为腰头容位/约克转移量，与是否绘制省无关）。
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


# ---------- 阶段 7：外缝、内缝线 ----------

def draw_back_outseam_curves(ctx: DraftContext) -> NamedCurve:
    """后片外侧缝线（复合线，同一步骤三笔）：
    小腿段（膝围外缝点 → 脚口外缝顶点）：自适应二次贝塞尔，几乎是直线、
    微凸贴合小腿后侧肌肉弧度，弧度由 α 控制（后片弧线推导.md §二）；
    大腿段（臀围外缝顶点 → 膝围外缝点）：三次贝塞尔，膝口与小腿段
    切线共线（C1），上端控制后臀侧包容饱满度（§四）；
    髋腰段（臀围外缝顶点 → 后腰头外缝顶点）：三次贝塞尔，拟合骨盆至
    腰口的微凸平滑过渡（§五）。
    依据：打版流程.md 后片步骤 7（外缝绘制）。"""
    o = ctx.options
    knee = ctx.point("back.knee_outseam_point")
    hem = ctx.point("back.hem_outseam_point")
    hip = ctx.point("back.hip_outseam_point")
    waist = ctx.point("back.waist_side_point")
    crotch_y = ctx.line("back.crotch_line").a.y
    q_mid = curves.lower_leg_mid(knee, hem, o.back_calf_arc_alpha)
    ctx.add_curve("back.outseam_lower",
                  curves.lower_leg_curve(knee, hem, q_mid),
                  step="draw_back_outseam_curves",
                  basis=f"自适应二次贝塞尔（升阶三次），α = {o.back_calf_arc_alpha}"
                        "（后片弧线推导.md §二）",
                  label="后外缝小腿弧")
    ctx.add_curve("back.outseam_upper",
                  curves.thigh_outseam_curve(
                      hip, crotch_y, knee, q_mid,
                      delta_x=o.back_outseam_arc_dx,
                      m2_ratio=o.back_outseam_arc_m2),
                  step="draw_back_outseam_curves",
                  basis=f"三次贝塞尔：δx = {o.back_outseam_arc_dx}，"
                        f"m2 = {o.back_outseam_arc_m2}×ΔY，膝口 C1 共线（§四）",
                  label="后外缝大腿弧")
    return ctx.add_curve("back.outseam_hip_waist",
                         curves.hip_waist_outseam_curve(
                             hip, waist,
                             dx1=-o.back_hipwaist_arc_dx1,
                             k1=o.back_hipwaist_arc_k1,
                             dx2=o.back_hipwaist_arc_dx2,
                             k2=o.back_hipwaist_arc_k2),
                         step="draw_back_outseam_curves",
                         basis=f"三次贝塞尔：δx1 = {o.back_hipwaist_arc_dx1}，"
                               f"k1 = {o.back_hipwaist_arc_k1}，"
                               f"δx2 = {o.back_hipwaist_arc_dx2}，"
                               f"k2 = {o.back_hipwaist_arc_k2}（§五；"
                               "本坐标系外缝朝 −X，δx1 取负、δx2 取正，"
                               "均使正值向外凸）",
                         label="后外缝髋腰弧")


def draw_back_inseam_curves(ctx: DraftContext) -> NamedCurve:
    """后片内侧缝线（复合线，同一步骤两笔）：
    小腿段（膝围内缝点 → 脚口内缝顶点）：自适应二次贝塞尔（同一 α 公式
    在两侧自动镜像，后片弧线推导.md §二）；
    大腿段（后大裆宽顶点 → 膝围内缝点）：三次贝塞尔，保留较强曲率与
    运动空间留量，膝口与小腿段切线共线（C1，§三）。
    依据：打版流程.md 后片步骤 7（内缝绘制）。"""
    o = ctx.options
    knee = ctx.point("back.knee_inseam_point")
    hem = ctx.point("back.hem_inseam_point")
    crotch = ctx.point("back.crotch_vertex")
    p_mid = curves.lower_leg_mid(knee, hem, o.back_calf_arc_alpha)
    ctx.add_curve("back.inseam_lower",
                  curves.lower_leg_curve(knee, hem, p_mid),
                  step="draw_back_inseam_curves",
                  basis=f"自适应二次贝塞尔（升阶三次），α = {o.back_calf_arc_alpha}"
                        "（后片弧线推导.md §二）",
                  label="后内缝小腿弧")
    return ctx.add_curve("back.inseam_upper",
                         curves.thigh_inseam_curve(
                             crotch, knee, p_mid,
                             k1=o.back_inseam_arc_k1,
                             ky=o.back_inseam_arc_ky,
                             k2_ratio=o.back_inseam_arc_k2),
                         step="draw_back_inseam_curves",
                         basis=f"三次贝塞尔：k1 = {o.back_inseam_arc_k1}，"
                               f"ky = {o.back_inseam_arc_ky}，"
                               f"k2 = {o.back_inseam_arc_k2}×ΔY，膝口 C1 共线（§三）",
                         label="后内缝大腿弧")


def draw_back_lower_waistband(ctx: DraftContext) -> NamedCurve | None:
    """后片弯腰头下腰缝线（后腰头绘制推导.md §4，可选步骤）：
    仅弯腰头（waistband_type=CURVED）绘制；直腰头返回 None 跳过。

    自上腰口端点 O（后浪顶点）、X（后腰头外缝顶点）分别沿后浪线、外侧缝线
    向下量取腰头宽 W，得下腰缝端点 O'（沿后浪 = 后中斜线 + 大裆弯弧的复合链）、
    X'（沿外缝髋腰弧）。下腰头线以与上腰口线相同的控制参数重建，弧度一致；
    O' 处切线与后中斜线 90° 正交（§4 核心要点：左右后片后中缝合后腰下口平滑
    连续、无尖角），X' 高度与前片 B' 匹配（侧缝拼接上口、下口齐平）。
    依据：打版流程.md 后片步骤 7（侧缝绘制完之后：弯腰头根据腰头宽绘制下腰头）。"""
    o = ctx.options
    if o.waistband_type is not WaistbandType.CURVED:
        return None                         # 直腰头：腰头单独成片，不下腰缝线
    W = o.waistband_width
    a = ctx.point("back.rise_top_point")            # O 上后浪顶点
    b = ctx.point("back.waist_side_point")          # X 上后腰头外缝顶点
    rise_slant = ctx.line("back.rise_slant")         # 后浪上段：O → 臀围内缝点（后中斜线）
    rise_curve = ctx.curve("back.rise_curve")        # 后浪下段：大裆弯弧
    outseam = ctx.curve("back.outseam_hip_waist")    # 外缝髋腰弧：臀围外缝顶点(t=0) → X(t=1)

    # O'：沿后浪线（后中斜线 + 大裆弯弧）自 O 向下量取 W
    a_sub = curves.point_along_chain((rise_slant, rise_curve), W)
    # X'：沿外缝髋腰弧自 X（t=1）向下量取 W
    t_bsub = outseam.t_at_length(outseam.length() - W)
    b_sub = outseam.point_at(t_bsub)

    # 下腰头线：与上腰口线同参数重建——O' 切线 ⟂ 后中斜线（§4 90° 正交）
    rise_dir = (ctx.point("back.hip_inner_point") - a).normalized()
    t_a = rise_dir.perpendicular()
    if t_a.dx * (b_sub.x - a_sub.x) + t_a.dy * (b_sub.y - a_sub.y) < 0:
        t_a = t_a.scale(-1)                 # 取朝向 X' 的一侧
    p1 = a_sub + t_a.scale(o.waist_rect_len)
    p2 = curves.waist_sag_p2(a_sub, b_sub, p1, at=0.5,
                             sag=o.back_waist_curve_sag)
    lower_arc = CubicBezier(a_sub, p1, p2, b_sub)

    ctx.add_point("back.lower_waist_center_point", a_sub,
                  step="draw_back_lower_waistband",
                  basis=f"沿后浪线自 O 向下量取腰头宽 {W}（后腰头绘制推导.md §4 O'）",
                  label="下后浪顶点O'")
    ctx.add_point("back.lower_waist_side_point", b_sub,
                  step="draw_back_lower_waistband",
                  basis=f"沿外缝线自 X 向下量取腰头宽 {W}（后腰头绘制推导.md §4 X'）",
                  label="下侧缝顶点X'")
    return ctx.add_curve("back.lower_waistline_arc", lower_arc,
                         step="draw_back_lower_waistband",
                         basis=f"下腰头线：与上腰口线同 sag {o.back_waist_curve_sag}、"
                               f"直角段 {o.waist_rect_len} 重建，"
                               "O' 切线 ⟂ 后中斜线（§4 等距平行、90° 正交）",
                         label="后下腰头线")


# ---------- 阶段 8：毗围限制 ----------

def draw_back_thigh_limit(ctx: DraftContext) -> NamedLine | None:
    """毗围线（前后片同一步骤测量上版）：立裆深线下移 d 的水平线上，
    量取前后片外缝交点至裆端的宽度，即前、后片毗围。

    可选步骤：大腿围未录入（thigh = 0）时整步跳过，不上版任何元素
    （"如果有毗围才需要做限制"，打版流程.md 后片步骤 8）。

    d = 0（偏移量为 0，打版流程.md 后片步骤 8 基准情形）：
      前毗围线 = 前直裆深线∩外缝线 → 前小裆宽顶点；
      后毗围线 = 后直裆深线∩外缝线 → 后大裆宽顶点（斜量即推导.md §二
      的 W_b0，sqrt(L_b² + d_drop²) 勾股校验关系自然成立）。
    d > 0（先偏移再测量，推导.md §一 实测下移量 d）：内端改取测量线与
      内边界的交点 —— 前片取前内缝大腿弧；后片按高度取后浪弧
      （测量线在裆尖上方）或后内缝大腿弧（在裆尖下方）。

    本步只测量上版（可选步骤的"测量"一笔）；ΔW 的双轨分流闭环修正
    （推导.md §三）由 flows/closure.py 驱动整版重跑落地，
    thigh_limit 开启时生效。
    依据：打版流程.md 后片步骤 8（毗围限制）。"""
    m, o = ctx.measurements, ctx.options
    if m.thigh <= 0:
        return None                     # 未录入大腿围，可选步骤跳过
    d = o.thigh_measure_offset
    measure_y = ctx.line("back.crotch_line").a.y - d

    # 前片：外缝交点 → 裆端（d=0 即前小裆宽顶点）
    f_out = ctx.curve("front.outseam_upper").point_at_y(measure_y)
    f_in = (ctx.point("front.crotch_vertex") if d == 0
            else ctx.curve("front.inseam_upper").point_at_y(measure_y))
    # 后片：外缝交点 → 后大裆宽顶点（d=0 斜量）/ 内边界交点（d>0）
    b_out = ctx.curve("back.outseam_upper").point_at_y(measure_y)
    if d == 0:
        b_in = ctx.point("back.crotch_vertex")
    else:
        vertex = ctx.point("back.crotch_vertex")
        b_in = (ctx.curve("back.rise_curve") if measure_y > vertex.y
                else ctx.curve("back.inseam_upper")).point_at_y(measure_y)

    ctx.add_point("front.thigh_outseam_point", f_out,
                  step="draw_back_thigh_limit",
                  basis=f"前外缝大腿弧 ∩ 测量线 y = {measure_y:.2f}（d = {d}）",
                  label="前毗围外缝点")
    ctx.add_point("back.thigh_outseam_point", b_out,
                  step="draw_back_thigh_limit",
                  basis=f"后外缝大腿弧 ∩ 测量线 y = {measure_y:.2f}（d = {d}）",
                  label="后毗围外缝点")
    if d > 0:
        ctx.add_point("front.thigh_inseam_point", f_in,
                      step="draw_back_thigh_limit",
                      basis=f"前内缝大腿弧 ∩ 测量线 y = {measure_y:.2f}",
                      label="前毗围内缝点")
        ctx.add_point("back.thigh_inseam_point", b_in,
                      step="draw_back_thigh_limit",
                      basis=f"后片内边界 ∩ 测量线 y = {measure_y:.2f}",
                      label="后毗围内缝点")

    w_f = f_out.distance_to(f_in)
    w_b = b_out.distance_to(b_in)
    dw = m.thigh - (w_f + w_b)
    ctx.add_line("front.thigh_line", LineSegment(f_out, f_in),
                 step="draw_back_thigh_limit",
                 basis=f"实测前毗围 {w_f:.2f}（d = {d}，"
                       "打版流程.md 后片步骤 8）",
                 label="前毗围线")
    return ctx.add_line("back.thigh_line", LineSegment(b_out, b_in),
                        step="draw_back_thigh_limit",
                        basis=f"实测后毗围 {w_b:.2f}；合计 {w_f + w_b:.2f} / "
                              f"目标 {m.thigh}，ΔW = {dw:+.2f}"
                              "（前后片毗围推导.md §三）",
                        label="后毗围线")


# ---------- 阶段 9：后片绘制省 ----------

def draw_back_darts(ctx: DraftContext) -> NamedLine | None:
    """后片腰省（打版流程.md 后片步骤 9，可选步骤）：
    开关 back_dart 开启且至少一个省量 > 0 才绘制，否则整步跳过。

    省中点：将腰头直线（A 后浪顶点 → B 后腰头外缝顶点的构造弦）等分 ——
    1 个省两等分取中点（t = 1/2），2 个省三等分取两个中间点
    （t = 1/3、2/3）；
    省中线：自省中点作腰头直线的垂线，朝裤片内部量取省长
    back_dart_length（默认 11cm），端点即省尖；
    省口：省量逐省配置（back_dart_width 列表，顺序同省中点：后中 → 侧缝；
    写单个值则各省共用；省量为 0 的省不绘制），自省中点沿腰头直线两侧
    各取半个省量得省口两点，与省尖相连成等腰三角形（省中线为对称轴）。
    绘省不动腰头：后腰长由 back_waist_dart（容位/约克转移量）决定，
    与本步绘制的省相互独立（后腰可以有容位）。
    依据：打版流程.md 后片步骤 9。"""
    o = ctx.options
    widths = o.back_dart_width            # __post_init__ 已归一化为元组
    if not o.back_dart or all(w <= 0 for w in widths):
        return None                     # 开关关闭或全部省量为 0，可选步骤跳过
    a = ctx.point("back.rise_top_point")
    b = ctx.point("back.waist_side_point")
    d = (b - a).normalized()            # 腰头直线方向（后中 → 侧缝）
    n = d.perpendicular()
    if n.dy > 0:
        n = n.scale(-1)                 # 省尖朝裤片内部（腰头下方）
    last: NamedLine | None = None
    for i, (t, w) in enumerate(
            zip(waist_f.dart_center_ratios(o.back_dart_count), widths), 1):
        if w <= 0:
            continue                    # 省量为 0 的省不绘制
        half = w / 2
        c = a.lerp(b, t)
        apex = c + n.scale(o.back_dart_length)
        p_in = c + d.scale(-half)       # 省口内侧点（朝后中 A）
        p_out = c + d.scale(half)       # 省口外侧点（朝侧缝 B）
        ctx.add_point(f"back.dart{i}_center", c,
                      step="draw_back_darts",
                      basis=f"腰头直线 {o.back_dart_count + 1} 等分点 "
                            f"t = {t:.4f}（打版流程.md 后片步骤 9）",
                      label=f"省{i}中点")
        ctx.add_point(f"back.dart{i}_apex", apex,
                      step="draw_back_darts",
                      basis=f"省中点沿腰头垂线向内 {o.back_dart_length}",
                      label=f"省{i}尖")
        ctx.add_line(f"back.dart{i}_center_line", LineSegment(c, apex),
                     step="draw_back_darts",
                     basis="腰头直线垂线（省中线，对称轴）",
                     label=f"省{i}中线", role="ref")
        ctx.add_line(f"back.dart{i}_leg_inner", LineSegment(apex, p_in),
                     step="draw_back_darts",
                     basis=f"省尖 → 省口内侧点（省中点两侧各 {half:.2f}）",
                     label=f"省{i}内侧边", role="struct")
        last = ctx.add_line(f"back.dart{i}_leg_outer", LineSegment(apex, p_out),
                            step="draw_back_darts",
                            basis=f"省尖 → 省口外侧点（省量 {w:.2f}，"
                                  "等腰三角形）",
                            label=f"省{i}外侧边", role="struct")
    return last
