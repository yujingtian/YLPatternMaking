"""裆部结构公式。

经验系数仅作默认参数，调用方（步骤层）通过 PatternOptions 覆盖。
"""


def rise_depth(hip: float, ratio: float = 0.25, adjust: float = 0.0) -> float:
    """直裆深（立裆线深度）：按臀围推导，默认 H/4 + 修正量。

    牛仔裤常用 H/4；宽松款可减、紧身款可微增，通过 adjust 调整。
    """
    return hip * ratio + adjust


def crotch_drop(hip: float, adjust: float = 0.0) -> float:
    """后片落裆量：后横裆大裆尖相对前横裆线的下移距离。

    Dc = H/100 + Δc（落裆推导.md §2.1）。成品臀围已含松量与弹性滤镜，
    标准直筒微弹牛仔 Δc = 0；高弹减（负值）、厚重/宽松加（正值，§2.2）。
    """
    return hip / 100 + adjust
