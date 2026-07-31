"""臀围结构公式。

依据：.doc/前后片臀围推导.md §三
（由 scripts/calc_hip_width.py 迁入，保持公式一致）
"""


def hip_front(hip: float, delta: float) -> float:
    """单侧前片臀围线净宽。H前 = H/4 − Δ（§三.1）。"""
    return hip / 4 - delta


def hip_back(hip: float, delta: float) -> float:
    """单侧后片臀围线净宽。H后 = H/4 + Δ（§三.1）。"""
    return hip / 4 + delta


def crotch_front_width(hip: float, adjust: float = 0.0) -> float:
    """前小裆宽。W小裆 = H/20 + 修正量（§三.2，紧身款修正 -0.5~-1.0）。"""
    return hip / 20 + adjust


def crotch_back_width(hip: float) -> float:
    """后大裆宽。W大裆 = H/10（§三.2）。"""
    return hip / 10


def front_total_width(hip: float, delta: float, adjust: float = 0.0) -> float:
    """前片底裆横向总宽 = H前 + W小裆（§三.3）。"""
    return hip_front(hip, delta) + crotch_front_width(hip, adjust)


def back_total_width(hip: float, delta: float) -> float:
    """后片底裆横向总宽 = H后 + W大裆（§三.3）。"""
    return hip_back(hip, delta) + crotch_back_width(hip)
