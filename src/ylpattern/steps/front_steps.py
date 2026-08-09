"""前片绘制步骤：每个函数对应手工打版的一笔。

对应 打版流程.md「前片打版实操坐标化步骤」：
  1. 建立基础参考线与"大矩形"框架（M1 已实现）
  2. 裆部结构：前小裆宽、前中内收点（已实现）
  3. 前浪弧线（已实现）
  4. 真实腰围线（已实现）
  5. 裤中线（已实现）
  6. 膝围、脚口宽度（已实现）
  7. 外缝、内缝线（已实现）

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
from ..geometry import CubicBezier, LineSegment, Point, Vector
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

def draw_front_waistline(ctx: DraftContext) -> NamedLine:
    """真实腰围线（构造直线）：从腰头内缝顶点（前浪顶点 A）向侧缝方向画
    腰围长 L 的直线，终点为基础腰围外缝顶点 B0，B0 高出腰围基础线 h（动态参数）。

    自顶向下约束（腰头绘制推导.md §4.2）：|AB| = L 恒定，
    x_b = x_a − sqrt(L² − (h+d)²)，d = 前中下落量（前浪闭合自然推出）。
    L = W/4 − balance + V前省（腰围推导.md §三.2）。
    本步产物为构造线；最终轮廓由 draw_front_waist_outseam_curves 的弧线取代。
    依据：打版流程.md 前片步骤 3（绘制真实腰围线）。"""
    m, o = ctx.measurements, ctx.options
    a = ctx.point("front.rise_top_point")
    waist_y = ctx.line("front.waist_line").a.y
    fc_drop = waist_y - a.y          # 前中下落量 d（A 低于基础线为正）
    waist_len = waist_f.waist_front_target(m.waist, o.waist_balance,
                                           o.front_waist_dart)
    span = waist_f.waistline_horizontal_span(waist_len, o.side_rise, fc_drop)
    b = Point(a.x - span, waist_y + o.side_rise)
    ctx.add_point("front.waist_side_point", b,
                  step="draw_front_waistline",
                  basis=f"x = {a.x:.2f} − sqrt({waist_len:.2f}² − "
                        f"({o.side_rise}+{fc_drop:.2f})²)，h = {o.side_rise}",
                  label="腰围外缝顶点")
    return ctx.add_line("front.waistline", LineSegment(b, a),
                        step="draw_front_waistline",
                        basis=f"|AB| = 腰长 {waist_len:.2f}（腰头绘制推导.md §4.2，构造线）",
                        label="真实腰围线", role="ref")


def draw_front_waist_outseam_curves(ctx: DraftContext) -> NamedCurve:
    """腰部轮廓弧：外侧缝微凸弧（臀围线外缝顶点→腰围外缝顶点）
    + 真实腰围线微凹弧（腰围外缝顶点→腰头内缝顶点）。

    约束（打版流程.md 前片步骤 3 第二条）：
      - 腰弧在 B 点切线 ⟂ 侧缝弧切线（90° 直角法则，前片侧缝内收推导.md §四）；
      - 腰弧下凹量 c（腰头绘制推导.md §5 P2）。
    腰长按两端点直线距离闭合（上一步直线约束已保证），
    弧长自然略长于腰长，不做补偿（§5 的内收微调不启用）。
    """
    m, o = ctx.measurements, ctx.options
    a = ctx.point("front.rise_top_point")
    b = ctx.point("front.waist_side_point")
    hip_out = Point(ctx.line("front.outseam_refline").a.x,
                    ctx.line("front.hip_line").a.y)
    waist_len = waist_f.waist_front_target(m.waist, o.waist_balance,
                                           o.front_waist_dart)

    # 微凸外缝弧：弦朝 B 的左手法向为 −X（向外），bulge 取正
    s_arc = curves.arc_through(hip_out, b, bulge=o.outseam_bulge)

    t_w = s_arc.tangent_at(1).normalized().perpendicular()
    # 两个垂直方向中取朝向 A 的一侧（90° 直角切入）
    if t_w.dx * (a.x - b.x) + t_w.dy * (a.y - b.y) < 0:
        t_w = t_w.scale(-1)
    p1 = b + t_w.scale(o.waist_rect_len)          # §5 P1：直角修正段
    # §5 P2：倾斜 + 下凹（距 A 1/3 弦长处；补偿 P1 偏离，弧中点下凹 = sag）
    p2 = curves.waist_sag_p2(b, a, p1, at=2 / 3,
                             sag=o.front_waist_curve_sag)
    w_arc = CubicBezier(b, p1, p2, a)

    ctx.add_point("front.hip_outseam_point", hip_out,
                  step="draw_front_waist_outseam_curves",
                  basis="臀围线 ∩ 外侧缝参考线", label="臀围线外缝顶点")
    ctx.add_curve("front.outseam_arc", s_arc,
                  step="draw_front_waist_outseam_curves",
                  basis=f"微凸外缝弧，凸量 {o.outseam_bulge}",
                  label="外侧缝弧线")
    return ctx.add_curve("front.waistline_arc", w_arc,
                         step="draw_front_waist_outseam_curves",
                         basis="微凹腰弧：B 点切线 ⟂ 侧缝弧切线（90° 法则），"
                               f"下凹 {o.front_waist_curve_sag}（腰长按端点直线距离闭合）",
                         label="真实腰围线弧")


def draw_front_lower_waistband(ctx: DraftContext) -> NamedCurve | None:
    """前片弯腰头下腰缝线（前腰头绘制推导.md §4.3、§5.2，可选步骤）：
    仅弯腰头（waistband_type=CURVED）绘制；直腰头腰头单独成片，本步返回
    None 跳过（打版流程.md 注意点 1）。

    自上腰口端点 A（前浪顶点）、B（腰围外缝顶点）分别沿前浪线、外侧缝线
    向下量取腰头宽 W，得下腰缝端点 A'（沿前浪 = 前中斜线 + 裆弯弧的复合链，
    近腰部前浪近似垂直，§4.3）、B'（沿外缝弧）。下腰头线以与上腰口线相同的
    控制参数（直角修正段 waist_rect_len、下凹量 front_waist_curve_sag）在
    A'、B' 间重建三次贝塞尔——弧度与上腰口线一致、起端切线 ⟂ 外缝切线
    （§5.2 同曲率平行拟合），腰头宽处处约等于 W。
    依据：打版流程.md 前片步骤 3（弯腰头：根据腰头宽绘制下腰头）。"""
    o = ctx.options
    if o.waistband_type is not WaistbandType.CURVED:
        return None                         # 直腰头：腰头单独成片，不下腰缝线
    W = o.waistband_width
    a = ctx.point("front.rise_top_point")          # A 上前中腰点（前浪顶点）
    b = ctx.point("front.waist_side_point")        # B 上侧缝腰点
    rise_slant = ctx.line("front.rise_slant")       # 前浪上段：A → 臀围内缝点
    rise_curve = ctx.curve("front.rise_curve")      # 前浪下段：臀围内缝点 → 前小裆顶点
    outseam = ctx.curve("front.outseam_arc")        # 外缝弧：臀围外缝顶点(t=0) → B(t=1)

    # A'：沿前浪线（斜线 + 裆弯弧）自 A 向下量取 W
    a_sub = curves.point_along_chain((rise_slant, rise_curve), W)
    # B'：沿外缝弧自 B（t=1）向下量取 W（point_at_length 自 t=0 起算，故取 total − W）
    t_bsub = outseam.t_at_length(outseam.length() - W)
    b_sub = outseam.point_at(t_bsub)

    # 下腰头线：与上腰口线同参数重建（§5.2）——起端 B' 切线 ⟂ 外缝切线（90° 法则）
    t_side = outseam.tangent_at(t_bsub).normalized().perpendicular()
    if t_side.dx * (a_sub.x - b_sub.x) + t_side.dy * (a_sub.y - b_sub.y) < 0:
        t_side = t_side.scale(-1)           # 取朝向 A' 的一侧
    p1 = b_sub + t_side.scale(o.waist_rect_len)
    p2 = curves.waist_sag_p2(b_sub, a_sub, p1, at=2 / 3,
                             sag=o.front_waist_curve_sag)
    lower_arc = CubicBezier(b_sub, p1, p2, a_sub)

    ctx.add_point("front.lower_waist_center_point", a_sub,
                  step="draw_front_lower_waistband",
                  basis=f"沿前浪线自 A 向下量取腰头宽 {W}（前腰头绘制推导.md §4.3 A'）",
                  label="下前中腰点A'")
    ctx.add_point("front.lower_waist_side_point", b_sub,
                  step="draw_front_lower_waistband",
                  basis=f"沿外缝弧自 B 向下量取腰头宽 {W}（前腰头绘制推导.md §4.3 B'）",
                  label="下侧缝腰点B'")
    return ctx.add_curve("front.lower_waistline_arc", lower_arc,
                         step="draw_front_lower_waistband",
                         basis=f"下腰头线：与上腰口线同 sag {o.front_waist_curve_sag}、"
                               f"直角段 {o.waist_rect_len} 重建，"
                               "B' 切线 ⟂ 外缝切线（§5.2 同曲率平行）",
                         label="前下腰头线")


def effective_waist(ctx: DraftContext) -> tuple[Point, CubicBezier, float]:
    """腰部挖削特征（前口袋 / 袋布）的"有效腰口"定位基准。

    弯腰头时腰头为独立裁片（上腰弧 → 下腰头线之间裁除），裤身顶边是下腰头
    线，口袋开在裤身上，故特征锚点相对下腰头线定位；直腰头时腰头打版扣除、
    裤身顶边即上腰弧，特征相对上腰头线定位。

    返回 (b, w_arc, s_side)：
      b      侧缝腰点（弯腰头 = 下侧缝腰点 B'，直腰头 = 腰外缝顶点 B）——局部原点 O；
      w_arc  腰弧（弯腰头 = 下腰头线，直腰头 = 上腰弧），t=0 在 b 端、朝前浪顶点；
      s_side b 在外缝弧 front.outseam_arc 上的弧长位置（自臀围端 t=0 起算；
             弯腰头 = 总长 − 腰头宽，即 B' 自顶端 B 向下 W 处；直腰头 = 总长）。
    依据：前腰头绘制推导.md §4.3/§5.2（弯腰头下腰头为裤身与腰头分界线）。
    """
    o = ctx.options
    if o.waistband_type is WaistbandType.CURVED:
        s_side = ctx.curve("front.outseam_arc").length() - o.waistband_width
        return (ctx.point("front.lower_waist_side_point"),
                ctx.curve("front.lower_waistline_arc"), s_side)
    return (ctx.point("front.waist_side_point"),
            ctx.curve("front.waistline_arc"),
            ctx.curve("front.outseam_arc").length())


# ---------- 阶段 5：裤中线 ----------

def draw_front_crease_line(ctx: DraftContext) -> NamedLine:
    """前片裤中线（烫迹线/丝缕线）：立裆线上从前侧缝（外侧缝参考线）向裆端
    量取 X = 前横裆总宽/2 + e 定点，过该点作垂直于脚口线的直线，
    下抵脚口线、上抵腰围线（前后片裤中线推导.md §二）。
    依据：打版流程.md 前片步骤 4（绘制裤中线）。"""
    m, o = ctx.measurements, ctx.options
    x = leg_f.crease_front_x(m.hip, o.delta, o.front_crotch_adjust,
                             o.front_crease_e)
    crotch_y = ctx.line("front.crotch_line").a.y
    waist_y = ctx.line("front.waist_line").a.y
    ctx.add_point("front.crease_point", Point(x, crotch_y),
                  step="draw_front_crease_line",
                  basis=f"X = (H前 + W小裆)/2 + e = {x:.2f}"
                        f"（裤中线推导.md §二.1，e = {o.front_crease_e}）",
                  label="裤中线立裆点")
    return ctx.add_line("front.crease_line",
                        LineSegment(Point(x, 0.0), Point(x, waist_y)),
                        step="draw_front_crease_line",
                        basis="过裤中线立裆点作脚口线垂线，脚口线 → 腰围线",
                        label="裤中线")


# ---------- 阶段 6：膝围、脚口宽度 ----------

def draw_front_knee_hem_widths(ctx: DraftContext) -> NamedCurve:
    """膝围/脚口内外缝顶点：以裤中线为对称轴向两侧各延伸片宽一半。
    前片膝围宽 K前 = K/2 − δ、前片脚口宽 B前 = B/2 − δ
    （先平分再前减后加，脚口膝围外缝点推导.md §三.1）。
    脚口内外缝顶点以浅弧相连为脚口结构线，弧高 front_hem_arc_sag
    （0 = 直线，正值向下凸出裤片，符合日常脚口形态）；膝围只定点、不连线。
    依据：打版流程.md 前片步骤 5（确定膝围和脚口宽度）。"""
    m, o = ctx.measurements, ctx.options
    x_c = ctx.line("front.crease_line").a.x
    knee_y = ctx.line("front.knee_line").a.y
    d_knee = leg_f.knee_front(m.knee, o.knee_adjust) / 2
    d_hem = leg_f.hem_front(m.hem, o.hem_adjust) / 2

    ctx.add_point("front.knee_outseam_point", Point(x_c - d_knee, knee_y),
                  step="draw_front_knee_hem_widths",
                  basis=f"d前膝 = ({m.knee}/2 − {o.knee_adjust})/2 = {d_knee:.2f}（裤中线对称，推导.md §三.2）",
                  label="膝围外缝点")
    ctx.add_point("front.knee_inseam_point", Point(x_c + d_knee, knee_y),
                  step="draw_front_knee_hem_widths",
                  basis=f"d前膝 = {d_knee:.2f}（内缝方向 +X）",
                  label="膝围内缝点")
    hem_out = ctx.add_point("front.hem_outseam_point", Point(x_c - d_hem, 0.0),
                            step="draw_front_knee_hem_widths",
                            basis=f"d前脚 = ({m.hem}/2 − {o.hem_adjust})/2 = {d_hem:.2f}（裤中线对称，推导.md §三.2）",
                            label="脚口外缝顶点")
    hem_in = ctx.add_point("front.hem_inseam_point", Point(x_c + d_hem, 0.0),
                           step="draw_front_knee_hem_widths",
                           basis=f"d前脚 = {d_hem:.2f}（内缝方向 +X）",
                           label="脚口内缝顶点")
    return ctx.add_curve("front.hem",
                         curves.sag_curve(hem_out.geom, hem_in.geom,
                                          sag=-o.front_hem_arc_sag),
                         step="draw_front_knee_hem_widths",
                         basis=f"脚口内外缝顶点浅弧相连，弧高 {o.front_hem_arc_sag}"
                               "（正值向下凸，打版流程.md 步骤 5）",
                         label="脚口线")


# ---------- 阶段 7：外缝、内缝线 ----------

def draw_front_outseam_curves(ctx: DraftContext) -> NamedCurve:
    """外侧缝线（复合线，同一步骤两笔）：
    小腿段（膝围外缝点 → 脚口外缝顶点）：自适应二次贝塞尔，几乎是直线、
    微微内凹，弧度由 α 控制（前片弧线推导.md §三）；
    大腿段（臀围外缝顶点 → 膝围外缝点）：三次贝塞尔，膝口与小腿段
    切线共线（C1），上端微凸顺势衔接臀→腰外缝弧（§五）。
    依据：打版流程.md 前片步骤 6（外缝绘制）。"""
    o = ctx.options
    knee = ctx.point("front.knee_outseam_point")
    hem = ctx.point("front.hem_outseam_point")
    hip = ctx.point("front.hip_outseam_point")
    crotch_y = ctx.line("front.crotch_line").a.y
    q_mid = curves.lower_leg_mid(knee, hem, o.calf_arc_alpha)
    ctx.add_curve("front.outseam_lower",
                  curves.lower_leg_curve(knee, hem, q_mid),
                  step="draw_front_outseam_curves",
                  basis=f"自适应二次贝塞尔（升阶三次），α = {o.calf_arc_alpha}（推导.md §三）",
                  label="外缝小腿弧")
    return ctx.add_curve("front.outseam_upper",
                         curves.thigh_outseam_curve(
                             hip, crotch_y, knee, q_mid,
                             delta_x=o.outseam_arc_dx,
                             m2_ratio=o.outseam_arc_m2),
                         step="draw_front_outseam_curves",
                         basis=f"三次贝塞尔：δx = {o.outseam_arc_dx}，"
                               f"m2 = {o.outseam_arc_m2}×ΔY，膝口 C1 共线（推导.md §五）",
                         label="外缝大腿弧")


def draw_front_inseam_curves(ctx: DraftContext) -> NamedCurve:
    """内侧缝线（复合线，同一步骤两笔）：
    小腿段（膝围内缝点 → 脚口内缝顶点）：与外缝小腿段关于裤中线轴对称
    （同一 α 公式在两侧自动镜像，前片弧线推导.md §三）；
    大腿段（前小裆宽顶点 → 膝围内缝点）：三次贝塞尔，微微凹入，
    膝口与小腿段切线共线（C1，§四）。
    依据：打版流程.md 前片步骤 6（内缝绘制）。"""
    o = ctx.options
    knee = ctx.point("front.knee_inseam_point")
    hem = ctx.point("front.hem_inseam_point")
    crotch = ctx.point("front.crotch_vertex")
    p_mid = curves.lower_leg_mid(knee, hem, o.calf_arc_alpha)
    ctx.add_curve("front.inseam_lower",
                  curves.lower_leg_curve(knee, hem, p_mid),
                  step="draw_front_inseam_curves",
                  basis=f"自适应二次贝塞尔（升阶三次），α = {o.calf_arc_alpha}，"
                        "与外缝关于裤中线轴对称（推导.md §三）",
                  label="内缝小腿弧")
    return ctx.add_curve("front.inseam_upper",
                         curves.thigh_inseam_curve(
                             crotch, knee, p_mid,
                             k1=o.inseam_arc_k1,
                             ky=o.inseam_arc_ky,
                             k2_ratio=o.inseam_arc_k2),
                         step="draw_front_inseam_curves",
                         basis=f"三次贝塞尔：k1 = {o.inseam_arc_k1}，ky = {o.inseam_arc_ky}，"
                               f"k2 = {o.inseam_arc_k2}×ΔY，膝口 C1 共线（推导.md §四）",
                         label="内缝大腿弧")
