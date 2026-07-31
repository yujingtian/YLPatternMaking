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
