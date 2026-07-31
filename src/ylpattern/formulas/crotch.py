"""裆部结构公式。

经验系数仅作默认参数，调用方（步骤层）通过 PatternOptions 覆盖。
"""


def rise_depth(hip: float, ratio: float = 0.25, adjust: float = 0.0) -> float:
    """直裆深（立裆线深度）：按臀围推导，默认 H/4 + 修正量。

    牛仔裤常用 H/4；宽松款可减、紧身款可微增，通过 adjust 调整。
    """
    return hip * ratio + adjust
