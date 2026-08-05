"""公共弧线库：参数化生成打版曲线（设计文档 §5.3.1）。

规则：
- 形状仅由参数区分的弧线一律用本库，保证同类弧线画法统一；
- 共用不强制 —— 裁片特有曲线允许步骤函数自行构造贝塞尔控制点；
- 所有参数必须是有物理意义的量（cm、角度、弦长比例），禁止魔法数。
"""

from __future__ import annotations

import math

from ..geometry import Point, Vector, CubicBezier

# 三次贝塞尔逼近"控制点弦"关系的常用系数：
# 弧顶在 t=0.5 时，弧高 ≈ 0.375 * 控制点相对弦的偏移，故放大 8/3
_BULGE_TO_CTRL = 8 / 3


def arc_through(end_a: Point, end_b: Point, *,
                bulge: float, bulge_at: float = 0.5) -> CubicBezier:
    """过两端点、按弧高控制的通用浅弧（脚口弧、膝围过渡等）。

    参数：
        bulge     弧高（弦的垂直方向凸起量，cm，正值向左手法向凸）
        bulge_at  弧顶位置（弦长比例 0~1，默认中点）
    """
    chord = end_b - end_a
    normal = chord.normalized().perpendicular()
    ctrl_offset = bulge * _BULGE_TO_CTRL
    p1 = end_a.lerp(end_b, bulge_at * 0.5) + normal.scale(ctrl_offset)
    p2 = end_a.lerp(end_b, (1 + bulge_at) * 0.5) + normal.scale(ctrl_offset)
    return CubicBezier(end_a, p1, p2, end_b)


def crotch_curve(start: Point, end: Point, *,
                 tangent_angle_deg: float, depth: float,
                 tension: float = 1.0) -> CubicBezier:
    """裆弯弧：起点切线约束 + 凹入深度控制。

    前后裆弯共用机制，凹深、切线角参数各自独立传入
    （前小裆 H/20、后大裆 H/10，见 前后片臀围推导.md §三.2）。

    参数：
        tangent_angle_deg 起点切线角（度，自 +X 轴逆时针），通常贴立裆线方向
        depth              裆弯凹入深度（cm），即起点沿切线方向的伸出控制长度
        tension            终点侧曲率松紧（>1 更饱满，默认 1.0）
    """
    rad = math.radians(tangent_angle_deg)
    t1 = Vector(math.cos(rad), math.sin(rad))
    p1 = start + t1.scale(depth * tension)

    chord = end - start
    p2 = end - chord.normalized().scale(chord.length / 3 * tension)
    return CubicBezier(start, p1, p2, end)


def front_rise(a: Point, b: Point, c: Point, *,
               target_length: float,
               handle_ratio: float = 1 / 3) -> tuple[Point, CubicBezier]:
    """前浪复合线：斜线 AB + 裆弯凹弧 BC，按总前浪长闭合反推 A 点。

    依据 前浪绘制.md：
      - 弧线 BC 起点切线沿 AB 延伸方向（B 点无折角），终点切线水平（贴立裆线）；
      - 控制柄长 k1 = k2 = |B−C| × handle_ratio（§4 标准控制柄）；
      - 弧长闭合：L_AB = target_length − ArcLength(BC)，
        A 沿 AB 反方向移动至 A_new（§4 方案"延伸点 A"）。

    参数：
        a              前中内收点（初始位置，仅用于确定斜线方向）
        b              臀围线内缝点（拐点）
        c              前小裆宽顶点（底裆点）
        target_length  目标总前浪长（cm，即量体的前浪尺寸）
        handle_ratio   控制柄长 / 弦长比例（默认 1/3，前浪绘制.md §4）

    返回：(a_new, 弧线 BC)；斜线段由调用方以 a_new、b 构造。
    """
    d_ab = (b - a).normalized()
    k = b.distance_to(c) * handle_ratio
    arc = CubicBezier(b, b + d_ab.scale(k), c + Vector(-k, 0.0), c)
    l_ab = target_length - arc.length()
    if l_ab <= 0:
        raise ValueError(
            f"前浪长 {target_length:.2f} 小于裆弯弧长 {arc.length():.2f}，"
            "无法闭合：请加大前浪或减小裆宽/直裆深")
    return b + d_ab.scale(-l_ab), arc


def back_rise(a: Point, b: Point, c: Point, *,
              target_length: float,
              alpha: float = 0.40, beta: float = 0.50
              ) -> tuple[Point, CubicBezier]:
    """后浪复合线：后中斜线 AB + 大裆弯深凹弧 BC，按总后浪长闭合反推 A 点。

    依据 后浪绘制.md：
      - 弧线 BC 起点切线严格共线于 AB 延伸方向（B 点无折角，§1.2），
        终点切线水平（平行立裆线，§1.2）；
      - 控制柄 k1 = α·|B−C|、k2 = β·|B−C|（§3.1：后裆弯深于前浪，
        α∈[0.38,0.42]、β∈[0.48,0.55]，紧身提臀 β 取 0.55）；
      - 弧长闭合：L_AB = target_length − ArcLength(BC)，
        A 沿 AB 反方向延伸至 A_new（§4 反推点 A 延伸法；
        延伸量即后翘高的自然结果）。

    参数：
        a              后中内收点（初始位置，仅用于确定斜线方向）
        b              臀围线内缝点（拐点）
        c              后大裆宽顶点（底裆点）
        target_length  目标总后浪长（cm，即量体的后浪尺寸）
        alpha          上控制柄系数（k1/弦长，§3.1）
        beta           下控制柄系数（k2/弦长，§3.1）

    返回：(a_new, 弧线 BC)；斜线段由调用方以 a_new、b 构造。
    """
    d_ab = (b - a).normalized()
    chord = b.distance_to(c)
    arc = CubicBezier(b, b + d_ab.scale(alpha * chord),
                      c + Vector(-beta * chord, 0.0), c)
    l_ab = target_length - arc.length()
    if l_ab <= 0:
        raise ValueError(
            f"后浪长 {target_length:.2f} 小于大裆弯弧长 {arc.length():.2f}，"
            "无法闭合：请加大后浪或减小裆宽/直裆深")
    return b + d_ab.scale(-l_ab), arc


def lower_leg_mid(knee: Point, hem: Point, alpha: float) -> Point:
    """小腿段中介控制点 P_mid/Q_mid（前片弧线推导.md §三）。

    M = 膝口与脚口的直线中点，横向自适应补偿 α·(X膝 − X脚口)：
    Δx = 0（直筒）时退化为中点，曲线成 100% 直线；
    Δx > 0（上宽下窄）向肌肉侧微凸；Δx < 0（喇叭）微凹展开。
    """
    m = knee.midpoint(hem)
    return Point(m.x + alpha * (knee.x - hem.x), m.y)


def sag_curve(end_a: Point, end_b: Point, *, sag: float) -> CubicBezier:
    """过两端点的浅弧，弧顶（t=0.5）精确偏离弦 sag cm（正值向左手法向凸）。

    对称控制点位于弦的 1/4、3/4 处，偏移 4/3·sag（三次贝塞尔中点
    偏移 = 3/4 × 控制点偏移）；sag = 0 时退化为直线。
    用于脚口弧等需要"弧高"语义精确的场合（区别于 arc_through 的
    bulge 经验系数）。
    """
    normal = (end_b - end_a).normalized().perpendicular()
    ctrl = normal.scale(sag * 4 / 3)
    p1 = end_a.lerp(end_b, 0.25) + ctrl
    p2 = end_a.lerp(end_b, 0.75) + ctrl
    return CubicBezier(end_a, p1, p2, end_b)


def lower_leg_curve(knee: Point, hem: Point, mid: Point) -> CubicBezier:
    """小腿段自适应二次贝塞尔（膝口 → 脚口），升阶为三次返回（§三）。

    二次曲线 (knee, mid, hem) 升阶：
    P1 = knee + 2/3·(mid − knee)，P2 = hem + 2/3·(mid − hem)。
    """
    p1 = knee + (mid - knee).scale(2 / 3)
    p2 = hem + (mid - hem).scale(2 / 3)
    return CubicBezier(knee, p1, p2, hem)


def thigh_inseam_curve(crotch: Point, knee: Point, mid: Point, *,
                       k1: float, ky: float, k2_ratio: float) -> CubicBezier:
    """内缝大腿段三次贝塞尔（前小裆顶点 → 膝围内缝点，前片弧线推导.md §四）。

    P1 = (X裆 − k1·ΔX, Y裆 − ky·ΔY) 控制小裆弧弯度急缓；
    P2 锁死在 mid → knee 射线延伸方向上（k2 = k2_ratio·ΔY），
    与小腿段膝口切线严格共线（C1 连续，§六）。
    """
    dx = crotch.x - knee.x
    dy = crotch.y - knee.y
    p1 = Point(crotch.x - k1 * dx, crotch.y - ky * dy)
    p2 = knee + (knee - mid).normalized().scale(k2_ratio * dy)
    return CubicBezier(crotch, p1, p2, knee)


def thigh_outseam_curve(hip: Point, crotch_y: float, knee: Point,
                        mid: Point, *,
                        delta_x: float, m2_ratio: float) -> CubicBezier:
    """外缝大腿段三次贝塞尔（臀围外缝顶点 → 膝围外缝点，前片弧线推导.md §五）。

    Q1 = (X臀 − δx, 立裆线高) 控制大转子外凸饱满度（δx=0 为顺直）；
    Q2 锁死在 mid → knee 射线延伸方向上（m2 = m2_ratio·ΔY），
    与小腿段膝口切线严格共线（C1 连续，§六）。
    """
    q1 = Point(hip.x - delta_x, crotch_y)
    q2 = knee + (knee - mid).normalized().scale(m2_ratio * (crotch_y - knee.y))
    return CubicBezier(hip, q1, q2, knee)
