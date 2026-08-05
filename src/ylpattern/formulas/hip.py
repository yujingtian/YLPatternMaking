"""臀围结构公式。

依据：.doc/前后片臀围推导.md §三
（由 scripts/calc_hip_width.py 迁入，保持公式一致）
"""

import math


def hip_front(hip: float, delta: float) -> float:
    """单侧前片臀围线净宽。H前 = H/4 − Δ（§三.1）。"""
    return hip / 4 - delta


def hip_back(hip: float, delta: float) -> float:
    """单侧后片臀围线净宽。H后 = H/4 + Δ（§三.1）。"""
    return hip / 4 + delta


def crotch_front_width(hip: float, adjust: float = 0.0) -> float:
    """前小裆宽。W小裆 = H/20 + 修正量（§三.2，紧身款修正 -0.5~-1.0）。"""
    return hip / 20 + adjust


def crotch_back_width(hip: float, adjust: float = 0.0) -> float:
    """后大裆宽。W大裆 = H/10 + 修正量（§三.2，坐姿伸展加深取正）。"""
    return hip / 10 + adjust


def front_total_width(hip: float, delta: float, adjust: float = 0.0) -> float:
    """前片底裆横向总宽 = H前 + W小裆（§三.3）。"""
    return hip_front(hip, delta) + crotch_front_width(hip, adjust)


def back_total_width(hip: float, delta: float, adjust: float = 0.0) -> float:
    """后片底裆横向总宽 = H后 + W大裆（§三.3）。"""
    return hip_back(hip, delta) + crotch_back_width(hip, adjust)


def back_hip_line_span(hip_len: float, lift: float) -> float:
    """最终后臀围线水平跨度：sqrt(L后臀² − 上移量²)（定长斜截）。

    最终后臀围线推导.md §一.2：以后臀围内缝顶点（上移后）为圆心、
    后臀围长 L 为半径斜截原始臀围水平基础线，跨度 = sqrt(L² − h²)，
    h 为内缝顶点高出基础线的距离（即起翘上移量的垂直分量）。
    """
    if hip_len <= lift:
        raise ValueError(
            f"后臀围长 {hip_len:.2f} ≤ 内缝顶点上移量 {lift:.2f}，"
            "无法斜截臀围基础线：请减小后浪/内收量或加大臀围")
    return math.sqrt(hip_len ** 2 - lift ** 2)
