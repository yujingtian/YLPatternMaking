"""门襟几何公式：纯 float 计算（门襟绘制.md §2.2、§3.2）。

步骤层只做定位与上版，数值计算一律收敛到本模块（纯 float 函数）。
"""

from __future__ import annotations

import math


def fly_length(front_rise: float, ratio: float = 0.35, base: float = 2.0) -> float:
    """门襟开深 L = ratio × 前浪长 + base（门襟绘制.md §2.2 核心输入参数表）。

    前浪长取量体前浪 front_rise（含腰头的成衣量；门襟开深为设计尺寸，
    与腰头扣除口径无关）。文档 §6 JSON 金标：front_rise = 25 -> L = 10.75。
    （参数表给的区间 14~18 与公式及 JSON 示例矛盾，以公式 + JSON 为准。）
    """
    return ratio * front_rise + base


def fly_corner_radius(W: float, inset: float) -> float:
    """底角圆角半径 R = W − inset（门襟绘制.md §3.2、§5）。

    连裁门襟与独立门襟**共用**内收口径 fly_corner_inset：R 由门襟宽 W 减内收量
    inset 得出（默认 inset=0.8 -> R=3.0）。inset 越大角越紧；0 < inset < W
    保证 0 < R < W（角弧落在门襟宽内）。统一口径取代旧的 fly_corner_radius
    （连裁直给 R）与 fly_sep_corner_inset（独立内收）两套参数。
    """
    return W - inset


def fly_corner_turn_point(W: float, L: float, R: float,
                          turn: float = 1.0
                          ) -> tuple[tuple[float, float], tuple[float, float]]:
    """连裁门襟 J 型角弧上的拐点 P_turn 及其单位切向（门襟绘制.md §3.2）。

    J 型底角 = 90° 圆弧：圆心 (W−R, L−R)，自外边下端角弧起点 (W, L−R)
    （角度 0°）扫至 J 底 (W−R, L)（角度 90°）。拐点取弧上 turn 比例处
    （1.0 = J 底，90° 弧终点；越小越靠上、角弧越短）：
    P = 圆心 + R·(cosθ, sinθ)，θ = turn·90°；切向 = (−sinθ, cosθ)
    （沿弧下行方向，转过 θ 后仍为单位向量）。turn=1.0（J 底）时切向水平
    朝前浪（局部 −X），即轮廓脱离 J 型圆弧、曲率反向向前浪收拢的起始分离点。
    局部坐标：X 朝门襟外凸为正，Y 沿前浪下行为正。返回 (点, 单位切向)。
    """
    theta = turn * math.pi / 2
    point = (W - R + R * math.cos(theta), L - R + R * math.sin(theta))
    tangent = (-math.sin(theta), math.cos(theta))
    return point, tangent


def fly_blend_extend(W: float, R: float) -> float:
    """连裁门襟融合点 P2 较开深 L 的默认下移量 = W − R（门襟绘制.md §3.2.3）。

    J 底 (W−R, L) 距前浪水平 W−R；自 J 底作与 J 弧相切、又与前浪相切的融合弧，
    其切圆自然落点 P2 在前浪上较 L 下移 W−R（对称四分之一卷）。即默认 P2 自 O
    沿前浪量取 L + fly_blend_extend(W, R)。此为 fly_blend_drop=None 时的取值
    下界（实际自动取值见 fly_blend_extend_min，二者取大以防波浪）。
    """
    return W - R


def fly_blend_extend_min(W: float, R: float, turn: float = 1.0) -> float:
    """拐点 turn 处融合弧**不产生波浪**所需的 P2 最小下移量（门襟绘制.md §3.2.3）。

    拐点切线（沿 J 弧）与前浪切线求交得融合弧控制点 Q；当 P2 过浅时两切线交点
    反向（u≤0），融合弧被迫下坠后回升（波浪）。不波浪的充要条件是 P2 较 L 下移
    量 extend ≥ 本值。推导（前浪切线取铅垂，裆弯弧近段近似成立）：
        θ = turn·90°，extend_min = cosθ·(W−R+R·cosθ)/sinθ − R·(1−sinθ)
    turn=1.0（J 底，θ=90°）-> 0（任意正下移都不波浪）；turn 越小（拐点越靠上）
    -> 所需下移越大，turn→0 -> ∞（拐点逼近起弧点，无法有限下移融合）。
    fly_blend_drop 由本值兜底校验/自动取值，保证任意合法组合无波浪。
    """
    theta = turn * math.pi / 2
    sin_t, cos_t = math.sin(theta), math.cos(theta)
    return cos_t * (W - R + R * cos_t) / sin_t - R * (1 - sin_t)
