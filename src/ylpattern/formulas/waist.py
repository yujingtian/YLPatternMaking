"""腰部结构公式：前中内收量等。

经验系数仅作默认参数，调用方（步骤层）通过 PatternOptions 覆盖。
"""


def front_center_intake(hip: float, waist: float,
                        ratio: float = 0.2, adjust: float = 0.0) -> float:
    """前中内收量（进量）：(H−W)/4 × 系数 + 修正量，系数默认 0.2。

    前中内收量推导.md §三.2：(H−W)/4 为前片四分之一截面总消纳量，
    内收量占其 15%~20%（系数 0.2 为上限参考值；低腰款可取 0.15）。
    工业标准中腰常用 1.2cm；高腰加大、低腰减小，通过 adjust 调整。
    注意：hip / waist 均为成品尺寸（含松量），非净体尺寸。
    """
    return (hip - waist) / 4 * ratio + adjust


def waist_front_finished(waist: float, balance: float = 0.0) -> float:
    """单侧前片成品腰宽：W/4 − balance（前减后加）。

    调节量方向与臀围 Δ 一致：前片减、后片加（后片 = W/4 + balance），
    即 前片侧缝内收推导.md §二.1 的 k_waist（通常 1.0~1.5cm；
    前后平分取 0）。
    """
    return waist / 4 - balance


def waist_front_target(waist: float, balance: float = 0.0,
                       dart: float = 0.0) -> float:
    """前片腰部目标画线宽（纸样腰宽）：W前成品 + V前省（推导.md §三.2）。

    dart（V前省）为前片省量/褶量：标准牛仔裤取 0（无前省，贴合前腹）；
    西裤直省 1.5~2.5、打褶 3~6（推导.md §五）。
    """
    return waist_front_finished(waist, balance) + dart


def side_seam_intake_front(front_hip: float, front_waist: float,
                           front_slant: float) -> float:
    """前片侧缝内收量（母公式，前片侧缝内收推导.md §二.1）：

        ΔX = 前片成品臀宽 − (前片成品净腰宽 + 前省/褶量) − 前中收斜

    参数均为已推导宽度（cm）：
        front_hip    前片成品臀宽（H/4 − Δ，见 hip.hip_front）
        front_waist  前片纸样腰宽（W/4 − balance + 省量，见 waist_front_target）
        front_slant  前中收斜/前中内收量（见 front_center_intake）

    调节量口径统一为"前减后加"：front_waist 即文档中的
    W_front_waist + S_dart = W/4 − k_waist + S_dart。
    """
    return front_hip - front_waist - front_slant
