"""门襟绘制步骤：前片连裁门襟（门襟绘制.md §1~§4）。

左右片非对称（§1.1）：左前片携带门襟（连裁），右前片不生成门襟、配独立底襟。
本系统前片为单片通用前片，门襟以连裁形式上版于前片（视为左前片）；右前片
镜像与独立底襟属裁片分离后的镜像/配件，暂未生成（先画后裁，裁切层未建）。

局部坐标系（§2.1）：原点 O = 前浪 ∩ 裤身顶边（弯腰头 = 下前中腰点 A'，
直腰头 = 前浪顶点 A，与 effective_waist 同一弯腰头口径）；Y 轴沿前浪下行
（正），X 轴垂直前浪朝门襟外凸（正）。先画后裁：只上版门襟轮廓线与工艺
标记点，不做布尔裁除。
"""

from __future__ import annotations

import math

from ..draft import DraftContext, NamedCurve, NamedLine, NamedPoint
from ..draft import curves
from ..formulas import fly as fly_f
from ..geometry import CubicBezier, LineSegment, Point, Vector
from ..params import WaistbandType
from .front_steps import effective_waist

_STEP = "draw_front_fly"

# 90° 圆角的三次贝塞尔逼近常数 4/3·tan(π/8) ≈ 0.5523（独立门襟底角，§5）
_QUARTER_K = 4 / 3 * math.tan(math.pi / 8)


def draw_front_fly(ctx: DraftContext) -> NamedLine | NamedCurve | None:
    """前片门襟（打版流程.md，门襟绘制.md §3~§5，可选步骤）：
    开关 fly（连裁）或 fly_separate（独立）任一开启才绘制；两者为门襟的
    互斥形态，fly_separate 优先（fly_separate=True 时无论 fly 与否都生成
    独立裁片）。两开关都关则整步跳过。

    连裁门襟（fly_separate=False，§3、§4）：门襟轮廓直接连裁上版于前片
      （凸向前片**外侧**、与前片相连）：顶边 → 外线 → J 型底角弧 → 融合弧。
      底角构造（§3.2）：先画**J 型角弧**（外边下端起 90° 圆弧，半径 R =
      W − fly_corner_inset，与独立门襟共用内收口径），在角弧上取**拐点 P_turn**（弧位 fly_corner_turn，
      1.0 = J 底 = 角弧终点；越小拐点越靠上），再自拐点作**融合弧**与前浪底弧
      相切融合（拐点处切于角弧、融合点 P2 处切于前浪，两端 G1）。P2 自 O 沿
      前浪量取 L + drop（drop = fly_blend_drop；None 自动取 W−R，且不小于拐点
      所需防波浪最小值；手动过浅则抛错），落在裆弯弧上、单调下行无波浪。加
      J 字明线（顺外边向内等距偏置的虚线；剪口刀口、打枣点等工艺细节暂不绘制）。
    独立门襟（fly_separate=True，§5）：绘图时**叠在前片上**（以前浪为轴伸入
      前片**内侧**、与前片身体重叠），之后裁片分离为单独裁片；净宽 W、高
      L + extra，底角平弧圆角（R = W − fly_corner_inset）。与连裁门襟互为前浪轴
      的镜像。

    共用局部坐标系（§2.1）：原点 O = 前浪 ∩ 裤身顶边（弯腰头 = 下前中腰点
    A'，直腰头 = 前浪顶点 A，与 effective_waist 同一弯腰头口径）；Y 轴沿前浪
    下行（正），X 轴垂直前浪朝门襟外凸（正）。开深 L = ratio × 前浪 + base。
    依据：打版流程.md；门襟绘制.md §2.1~§5。
    """
    o = ctx.options
    if not (o.fly or o.fly_separate):
        return None                     # 连裁/独立两开关都关，可选步骤跳过

    # 局部坐标系：O = 前浪 ∩ 裤身顶边；Y 沿前浪下行、X 垂直前浪朝外凸
    curved = o.waistband_type is WaistbandType.CURVED
    if curved:
        o_pt = ctx.point("front.lower_waist_center_point")  # A'（弯腰头裤身顶边）
        walk = o.waistband_width                            # A' 距前浪顶点 A 的弧长
    else:
        o_pt = ctx.point("front.rise_top_point")            # A（直腰头裤身顶边）
        walk = 0.0
    rise_slant = ctx.line("front.rise_slant")
    rise_curve = ctx.curve("front.rise_curve")
    y_dir = rise_slant.direction                            # 前浪下行方向（局部 +Y）
    x_dir = y_dir.perpendicular()                           # 门襟外凸方向（局部 +X，CCW）

    def to_global(x: float, y: float) -> Point:
        return o_pt + x_dir.scale(x) + y_dir.scale(y)

    W = o.fly_width
    L = fly_f.fly_length(ctx.measurements.front_rise,
                         o.fly_length_ratio, o.fly_length_base)

    ctx.add_point("front.fly_origin", o_pt,
                  step=_STEP,
                  basis="前浪 ∩ 裤身顶边（弯腰头 A' / 直腰头 A，门襟绘制.md §2.1）",
                  label="门襟原点O")

    if o.fly_separate:
        return _draw_separate_fly(ctx, o, o_pt, x_dir, y_dir,
                                  to_global, W, L)

    R = fly_f.fly_corner_radius(W, o.fly_corner_inset)    # J 型角弧半径（与独立门襟共用内收口径）
    turn = o.fly_corner_turn                             # 拐点弧位（1.0 = J 底，§3.2）
    theta = turn * math.pi / 2                           # 拐点在角弧上的圆心角
    # P2 较 L 下移量：手动录入须不小于防波浪最小值；None 则自动取 W−R 与最小值之大
    extend_min = fly_f.fly_blend_extend_min(W, R, turn)
    if o.fly_blend_drop is None:
        extend = max(fly_f.fly_blend_extend(W, R), extend_min)
    else:
        extend = o.fly_blend_drop
        if extend < extend_min:
            raise ValueError(
                f"融合弧下移量 {extend:.2f} 小于拐点弧位 {turn:.2f} 所需的防波浪"
                f"最小值 {extend_min:.2f}（增大 fly_blend_drop 或调大 fly_corner_turn）")

    # 关键点位（§3）：先画 J 型角弧（外边下端起 90° 圆弧），在角弧上取拐点 P_turn
    # （turn 弧位；1.0 = J 底 = 角弧终点），自拐点作融合弧与前浪底弧相切融合（§3.2）。
    t_top = to_global(W - o.fly_turnback, 0.0)             # 顶外角（退层补偿，§3.1）
    c_start = to_global(W, L - R)                          # 角弧起点 P1（外边下端，§3.2）
    (px, py), (tdx, tdy) = fly_f.fly_corner_turn_point(W, L, R, turn)
    p_turn = to_global(px, py)                             # 拐点（角弧上，§3.2）
    turn_dir = Vector(x_dir.dx * tdx + y_dir.dx * tdy,
                      x_dir.dy * tdx + y_dir.dy * tdy)    # 拐点处角弧切向
    p2 = curves.point_along_chain((rise_slant, rise_curve),
                                  walk + L + extend)       # 融合点 P2（前浪底弧上，§3.2.3）
    j_bottom = to_global(W - R, L)                        # J 底（90° 角弧终点，完整 J 型参考）
    rise_at_L = curves.point_along_chain((rise_slant, rise_curve),
                                         walk + L)         # 前浪@开深 L（完整 J 底边端）

    # P2 处前浪切向（落在斜线段取 y_dir，落在裆弯弧上取弧线切向）
    rem = walk + L + extend - rise_slant.length
    if rem <= 0:
        rise_tan = y_dir
    else:
        rise_tan = rise_curve.tangent_at(
            rise_curve.t_at_length(rem)).normalized()

    # J 型角弧（c_start → p_turn，turn×90° 圆弧段的三次贝塞尔逼近，柄长 4/3·R·tan(θ/4)）；
    # 首柄沿外边方向 d_outer（外边因退层 Δw 微斜），末柄沿 −turn_dir 使弧在拐点切向为
    # turn_dir，保 外边 → 角弧 → 融合弧 三段 G1
    k_arc = 4 / 3 * R * math.tan(theta / 4)
    d_outer = (c_start - t_top).normalized()
    corner_arc = CubicBezier(c_start, c_start + d_outer.scale(k_arc),
                             p_turn + turn_dir.scale(-k_arc), p_turn)

    # 融合弧（p_turn → p2，§3.2.3）：拐点切线与前浪切线求交点 Q，
    # 二次贝塞尔 (p_turn, Q, p2) 升阶为三次 —— 两端 G1 相切，自拐点单调下行
    # 融入前浪底弧（无波浪）；extend 经 fly_blend_extend_min 兜底，切线交点恒正向
    det = turn_dir.dx * rise_tan.dy - turn_dir.dy * rise_tan.dx
    vx, vy = p2.x - p_turn.x, p2.y - p_turn.y
    s = (vx * rise_tan.dy - vy * rise_tan.dx) / det if abs(det) > 1e-9 else -1.0
    u = (vx * turn_dir.dy - vy * turn_dir.dx) / det if abs(det) > 1e-9 else -1.0
    if s > 0 and u > 0:
        q = p_turn + turn_dir.scale(s)                 # 两切线交点（抛物线控制点）
        blend = CubicBezier(p_turn, p_turn + (q - p_turn).scale(2 / 3),
                            p2 + (q - p2).scale(2 / 3), p2)
    else:
        h = p_turn.distance_to(p2) / 3
        blend = CubicBezier(p_turn, p_turn + turn_dir.scale(h),
                            p2 + rise_tan.scale(-h), p2)

    ctx.add_point("front.fly_top_outer", t_top,
                  step=_STEP,
                  basis=f"腰口顶端外角：X = W − Δw = {W - o.fly_turnback:.2f}"
                        "（§3.1 退层补偿）",
                  label="门襟顶外角")
    ctx.add_point("front.fly_start", c_start,
                  step=_STEP,
                  basis=f"角弧起点 P1 = (W {W}, L−R {L - R:.2f})（§3.2 完整 J 型底角）",
                  label="门襟起弧点P1")
    ctx.add_point("front.fly_turn", p_turn,
                  step=_STEP,
                  basis=f"拐点 P_turn：90° 角弧 {turn:.2f} 弧位（θ = {math.degrees(theta):.1f}°，§3.2）",
                  label="门襟拐点")
    ctx.add_point("front.fly_tangent", p2,
                  step=_STEP,
                  basis=f"前浪融合点 P2：自 O 沿前浪量取 L+{extend:.2f} = {L + extend:.2f}"
                        f"（前浪底弧，§3.2.3）",
                  label="门襟融合点P2")

    ctx.add_line("front.fly_top_edge", LineSegment(o_pt, t_top),
                 step=_STEP, basis="门襟腰口顶边（§3.1）",
                 label="门襟顶边", role="struct")
    ctx.add_line("front.fly_outer_edge", LineSegment(t_top, c_start),
                 step=_STEP, basis=f"门襟外线（外凸宽 W = {W}，§3）",
                 label="门襟外线", role="struct")
    ctx.add_curve("front.fly_corner_arc", corner_arc,
                  step=_STEP,
                  basis=f"J 型底角弧：{math.degrees(theta):.1f}° 角弧段，R = {R}（§3.2）",
                  label="门襟底角弧", role="struct")
    bottom = ctx.add_curve("front.fly_bottom_arc", blend,
                           step=_STEP,
                           basis="融合弧：拐点切线 ∩ 前浪切线 = Q，二次贝塞尔升阶"
                                 "（两端 G1，自拐点单调下行融入前浪底弧，§3.2.3）",
                           label="门襟底弧", role="struct")

    # 完整 J 型参考（虚线 ref）：像独立门襟那样把底部画全--角弧剩余段（拐点 → J 底）
    # + J 底边（J 底 → 前浪@L）。实际轮廓（起弧点 → 拐点 + 融合弧）为实线
    # struct；拐点之后到 J 底、再到底边的"虚拟完整 J"以 ref 虚线补全，便于对照版型。
    if turn < 1.0:                                   # 拐点已在 J 底时余段退化，跳过
        k_rest = 4 / 3 * R * math.tan((math.pi / 2 - theta) / 4)
        j_arc_rest = CubicBezier(p_turn, p_turn + turn_dir.scale(k_rest),
                                 j_bottom + x_dir.scale(k_rest), j_bottom)
        ctx.add_curve("front.fly_j_arc_rest", j_arc_rest,
                      step=_STEP,
                      basis=f"J 型角弧剩余段（拐点 → J 底，"
                            f"{math.degrees(math.pi / 2 - theta):.1f}°）虚线参考（完整 J 型，§3.2）",
                      label="门襟J弧余段", role="ref")
    ctx.add_line("front.fly_j_bottom_edge", LineSegment(j_bottom, rise_at_L),
                 step=_STEP,
                 basis="J 底边（J 底 → 前浪@L，完整 J 型参考）虚线（§3.2）",
                 label="门襟J底边", role="ref")

    # 工艺标记：仅保留 J 字明线——顺着门襟外边向内等距偏置（fly_stitch_inset）
    # 的虚线（参考线）。拉链止口剪口（刀口）、打枣点及其底部钩弧暂不绘制
    # （§4 工艺细节，留待后续工艺/裁切模块；见 门襟绘制.md §7 实现注记）。
    inset = o.fly_stitch_inset
    s_top = t_top + x_dir.scale(-inset)     # 明线起点（外边上端 T 向内偏置）
    s_bot = c_start + x_dir.scale(-inset)   # 明线终点（外边下端向内偏置）
    ctx.add_line("front.fly_j_stitch", LineSegment(s_top, s_bot),
                 step=_STEP,
                 basis=f"J 字明线：顺门襟外边向内等距偏置 {inset}（虚线，§4.2 简化）",
                 label="门襟J字明线", role="ref")
    return bottom


def _draw_separate_fly(ctx: DraftContext, o, o_pt: Point,
                       x_dir, y_dir, to_global, W: float, L: float) -> NamedLine | NamedCurve:
    """独立门襟裁片（门襟绘制.md §5）：顶边沿腰头线、外缘/缝份边沿前浪方向的
    独立裁片（底角平弧圆角）。

    外缝顶点：沿**腰头线**（弯腰头 = 下腰头线，直腰头 = 上腰弧，与 effective_waist
    同口径）自 O 向侧缝方向量取裁片净宽 w_out = W（默认 3.8；缝份/缩水留待裁切
    模块外拓，先画后裁）；顶边 = 腰头线子弧（与前片腰头线重合，门襟顶沿腰头线
    缝进腰头）。裁片高 h = L + extra（默认 + 2.0 作底部延展；上部腰口车合量属裁
    切层缝份）。
    外缘（自外缝顶点）与缝份边（自 O）分别沿前浪方向下行 h，底角圆角半径
    R = W − fly_corner_inset（默认 0.8 -> R=3.0，与连裁门襟共用），90° 圆弧以 _QUARTER_K 常数贝塞尔逼近。

    方向（用户口径）：独立门襟绘图时**叠在前片上**（外缝顶点沿腰头线向侧缝方向、
    裁片伸入前片内侧，与前片身体重叠，之后裁片分离才单独成片）；缝份边（沿前浪）
    与前浪缝合线重合。与连裁门襟（凸向前片外侧、与前片相连）互为前浪轴镜像。
    依据：门襟绘制.md §5。
    """
    extra = o.fly_sep_extra
    R = fly_f.fly_corner_radius(W, o.fly_corner_inset)   # 底角圆角半径（与连裁门襟共用 fly_corner_inset 口径）
    w_out = W                           # 裁片宽 = 净宽 W（缝份/缩水留待裁切模块外拓，先画后裁）
    h = L + extra                       # 裁片高（沿前浪方向）

    # 外缝顶点：沿腰头线自 O（腰头线弧 t=1 端）向侧缝方向（t=0 端）量取 w_out
    _, w_arc, _ = effective_waist(ctx)  # 裤身腰头线弧（弯腰头 = 下腰头线）
    total = w_arc.length()
    if w_out >= total:
        raise ValueError(
            f"独立门襟裁片宽 {w_out:.2f} 超过腰头线长 {total:.2f}（门襟绘制.md §5）")
    t_top = w_arc.t_at_length(total - w_out)
    p_top_outer = w_arc.point_at(t_top)          # 外缝顶点（在腰头线上）
    top_edge = w_arc.split(t_top)[1]             # 顶边 = 腰头线子弧 外缝顶点 → O

    # 外缘（自外缝顶点）与缝份边（自 O）分别沿前浪方向下行 h
    e_bot = p_top_outer + y_dir.scale(h)         # 外缘下端（未倒圆角点）
    s_bot = o_pt + y_dir.scale(h)                # 缝份边下端
    d_bot = (s_bot - e_bot).normalized()         # 底边方向（外缘下端 → 缝份边下端）

    # 底角 90° 圆角：起弧切线 = 前浪方向（+Y）、收弧切线 = 底边方向
    c_start = e_bot + y_dir.scale(-R)            # 圆角起点（外缘上）
    c_end = e_bot + d_bot.scale(R)               # 圆角终点（底边上）
    corner = CubicBezier(c_start, c_start + y_dir.scale(_QUARTER_K * R),
                         c_end + d_bot.scale(-_QUARTER_K * R), c_end)

    ctx.add_point("front.fly_sep_top_outer", p_top_outer,
                  step=_STEP,
                  basis=f"外缝顶点：沿腰头线自 O 量取裁片净宽 {w_out:.2f} = W（§5）",
                  label="独立门襟外缝顶点")
    ctx.add_point("front.fly_sep_bottom_inner", s_bot,
                  step=_STEP,
                  basis=f"缝份边下端（自 O 沿前浪方向下行裁片高 {h:.2f} = L {L:.2f} + 延展 {extra}，§5）",
                  label="独立门襟下内角")
    ctx.add_curve("front.fly_sep_top_edge", top_edge,
                  step=_STEP,
                  basis="顶边 = 腰头线子弧（外缝顶点 → O，与前片腰头线重合，§5）",
                  label="独立门襟顶边")
    ctx.add_line("front.fly_sep_outer_edge", LineSegment(p_top_outer, c_start),
                 step=_STEP, basis=f"外缘（自外缝顶点沿前浪方向下行，宽 {w_out:.2f}，§5）",
                 label="独立门襟外缘", role="struct")
    ctx.add_curve("front.fly_sep_corner", corner,
                  step=_STEP,
                  basis=f"底角 90° 平弧圆角 R = {R:.2f}（平弧 J 字倒角，§5）",
                  label="独立门襟圆角")
    ctx.add_line("front.fly_sep_bottom_edge", LineSegment(c_end, s_bot),
                 step=_STEP, basis="底边（圆角终点 → 缝份边下端，§5）",
                 label="独立门襟底边", role="struct")
    return ctx.add_line("front.fly_sep_inner_edge", LineSegment(s_bot, o_pt),
                        step=_STEP,
                        basis="缝份边（自 O 沿前浪方向下行，与前浪缝合线重合，§5.1）",
                        label="独立门襟内边", role="struct")
