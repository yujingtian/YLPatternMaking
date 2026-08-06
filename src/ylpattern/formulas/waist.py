"""腰部结构公式：前中内收量等。

经验系数仅作默认参数，调用方（步骤层）通过 PatternOptions 覆盖。
"""

import math


def front_center_intake(hip: float, waist: float,
                        ratio: float = 0.2, adjust: float = 0.0) -> float:
    """前中内收量（进量）：(H−W)/4 × 系数 + 修正量，系数默认 0.2。

    前中内收量推导.md §三.2：(H−W)/4 为前片四分之一截面总消纳量，
    内收量占其 15%~20%（系数 0.2 为上限参考值；低腰款可取 0.15）。
    工业标准中腰常用 1.2cm；高腰加大、低腰减小，通过 adjust 调整。
    注意：hip / waist 均为成品尺寸（含松量），非净体尺寸。
    """
    return (hip - waist) / 4 * ratio + adjust


def back_center_intake(h_v: float, intake: float = 2.5,
                       base: float = 15.0) -> float:
    """后中实际内收量 D_h = H_v × X/15（后中内收点推导.md §一 核心公式）。

    15:X 是斜率比例（几何角度比），非绝对数字：X 为比例倒量模数，
    按版型调取系数表（§二：宽松 1.5~2、标准 2.5~3、紧身 3.5~4.5）；
    H_v 为版上实际臀腰高（后臀围线到后腰围线的垂直距离），
    实际内收量按同比例折算 —— 斜率锁定，内收量随尺寸单浮动。

    参数（cm）：
        h_v     实际臀腰高（后腰围线 y − 后臀围线 y）
        intake  比例倒量模数 X
        base    比例参照模数（名义臀腰距 15）
    """
    return h_v * intake / base


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


def waist_back_finished(waist: float, balance: float = 0.0) -> float:
    """单侧后片成品腰宽：W/4 + balance（前减后加，与前片同向）。

    调节量口径与臀围 Δ 一致（前片 = W/4 − balance，见 waist_front_finished）。
    """
    return waist / 4 + balance


def waist_back_target(waist: float, balance: float = 0.0,
                      dart: float = 0.0) -> float:
    """后片腰部目标画线宽（后腰长）：W后成品 + V后省（腰围推导.md §三.2）。

    dart（V后省）为后片省量/约克转移量：标准牛仔裤由后约克 Yoke 承担
    （2.5~4.0，约克步骤前取 0）；西裤直省 2.0~3.0（推导.md §五）。
    """
    return waist_back_finished(waist, balance) + dart


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


def dart_center_ratios(count: int) -> tuple[float, ...]:
    """省中点在腰头直线上的等分比例 t（打版流程.md 后片步骤 9）。

    1 个省：腰头两等分，中点 t = 1/2；
    2 个省：腰头三等分，两个中间点 t = 1/3、2/3。
    t 自腰头内缝端（后中）向腰头外缝端量取。
    """
    if count == 1:
        return (0.5,)
    if count == 2:
        return (1 / 3, 2 / 3)
    raise ValueError(f"后片省数只支持 1 或 2，得到 {count}")


def waistline_horizontal_span(waist_len: float, side_rise: float,
                              fc_drop: float) -> float:
    """真实腰围线水平跨度：sqrt(L² − (h+d)²)（腰头绘制推导.md §4.2）。

    自顶向下约束：腰头内缝顶点 A 到腰围外缝顶点 B 的直线距离恒等于
    单片前腰长 L，B 高出腰围基础线 h（侧缝抬高量，动态参数）：

        x_b = x_a − sqrt(L² − (h + d)²)

    参数（cm）：
        waist_len  单片前腰长 L（见 waist_front_target）
        side_rise  侧缝腰头抬高量 h（0 = 顶点压在腰围基础线上）
        fc_drop    前中下落量 d（A 低于腰围基础线的量；A 高出时为负）

    边界（§6.2）：L ≤ h + d 时高度差超出斜边长，无法构成腰线。
    """
    delta_y = side_rise + fc_drop
    if waist_len <= delta_y:
        raise ValueError(
            f"腰长 {waist_len:.2f} ≤ 高差 {delta_y:.2f}（h={side_rise} + "
            f"d={fc_drop:.2f}），无法构成腰线：请减小侧缝抬高量或加大腰长")
    return math.sqrt(waist_len ** 2 - delta_y ** 2)
