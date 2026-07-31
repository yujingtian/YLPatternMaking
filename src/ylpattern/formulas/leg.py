"""腿部结构公式：膝位、脚口收放等。

经验值仅作默认参数，调用方（步骤层）可通过 PatternOptions 覆盖。
"""


def knee_line_height(hem_y: float, crotch_y: float, offset: float = 3.0) -> float:
    """膝围参考线高度。

    经验：中裆（膝位）位于脚口线与立裆线中点上移 offset（默认 3cm）。
    """
    return (hem_y + crotch_y) / 2 + offset
