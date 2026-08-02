"""腿部结构公式：膝位、裤中线、脚口收放等。

经验值仅作默认参数，调用方（步骤层）可通过 PatternOptions 覆盖。
"""

from .hip import crotch_front_width, hip_front


def knee_line_height(hem_y: float, crotch_y: float, offset: float = 3.0) -> float:
    """膝围参考线高度。

    经验：中裆（膝位）位于脚口线与立裆线中点上移 offset（默认 3cm）。
    """
    return (hem_y + crotch_y) / 2 + offset


def crease_front_x(hip: float, delta: float,
                   crotch_adjust: float = 0.0, e: float = 0.0) -> float:
    """前片裤中线距前侧缝（外侧缝参考线）的距离。

    X = (W前臀宽 + W前小裆宽) / 2 + e
        = 前横裆总宽 / 2 + e（前后片裤中线推导.md §二.1）

    注：§五 实战规范的符号方向（+e 向外缝）与 §二.1 公式字面
    （+e 增大距侧缝距离，即向内缝方向）相反；公式层以 §二.1 为准。
    """
    return (hip_front(hip, delta) + crotch_front_width(hip, crotch_adjust)) / 2 + e
