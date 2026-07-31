"""腰部结构公式：前中内收量等。

经验系数仅作默认参数，调用方（步骤层）通过 PatternOptions 覆盖。
"""


def front_center_intake(hip: float, waist: float,
                        divisor: float = 16.0, adjust: float = 0.0) -> float:
    """前中内收量（进量）：按成品腰臀差推导，默认 (H−W)/16 + 修正量。

    前中内收推导.md §三.2：占前片四分之一纸样总消纳量的 15%~20%。
    工业标准中腰常用 1.2cm；高腰加大、低腰减小，通过 adjust 调整。
    注意：hip / waist 均为成品尺寸（含松量），非净体尺寸。
    """
    return (hip - waist) / divisor + adjust
