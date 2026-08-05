"""版型选项：经验值统一收敛于此，公式层与步骤层不硬编码经验常数。"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from .sizefile import load_size_file


class WaistbandType(enum.Enum):
    """腰头类型（打版流程.md「注意点 1」）。"""

    STRAIGHT = "straight"  # 直腰头：打版时直接扣除腰头宽，腰头单独成片
    CURVED = "curved"      # 弯腰头：与前片一体绘制，裁切阶段再裁出


class Fit(enum.Enum):
    SKINNY = "skinny"
    SLIM = "slim"
    REGULAR = "regular"
    LOOSE = "loose"


# 前后片臀围单侧调节量 Δ 预设（前后片臀围推导.md §四 对照表，取区间中值）
DELTA_PRESETS: dict[str, tuple[float, str]] = {
    "women_standard": (1.00, "标准女装西裤 / 无弹牛仔"),
    "women_curvy":    (1.35, "女性翘臀高腰牛仔裤（1.2~1.5）"),
    "men_straight":   (0.60, "标准男装直筒牛仔裤（0.5~0.75）"),
    "high_stretch":   (0.40, "高弹力紧身女牛仔裤（0.3~0.5）"),
    "loose_wide":     (0.25, "超宽松阔腿裤 / 工装裤（0~0.5）"),
}


@dataclass(frozen=True)
class PatternOptions:
    delta: float = 1.0                     # 前后片臀围单侧调节量 Δ（推导文档 §四）
    front_crotch_adjust: float = 0.0       # 前小裆修正（紧身款 -0.5~-1.0，§三.2）
    back_crotch_adjust: float = 0.0        # 后大裆修正（坐姿伸展加深取正，§三.2）
    front_intake_ratio: float = 0.2        # 前中内收系数（内收量 = (H−W)/4 × 系数，低腰 0.15）
    front_intake_adjust: float = 0.0       # 前中内收修正（高腰加大、低腰减小）
    back_intake: float = 2.5               # 后中内收比例模数 X（实际内收 = 臀腰高×X/15；宽松 1.5~2、标准 2.5~3、紧身 3.5~4.5）
    waist_balance: float = 0.0             # 腰围前后片调节量（前减后加，同臀围 Δ；平分 0）
    front_waist_dart: float = 0.0          # 前片省量/褶量 V前省（牛仔裤 0；西裤 1.5~2.5）
    back_waist_dart: float = 0.0           # 后片省量/约克转移量 V后省（约克步骤前 0；Yoke 2.5~4.0）
    side_intake_k_waist: float = 1.0       # 侧缝内收推导的 k_waist（前减后加，常取 1.0~1.5）
    side_rise: float = 0.0                 # 侧缝腰头抬高量 h（0 = 外缝顶点压腰围基础线，0~1.5）
    outseam_bulge: float = 0.3             # 外侧缝弧外凸量（微微凸，0.2~0.5）
    front_waist_curve_sag: float = 0.3     # 前片腰围线弧额外下凹量（腰头绘制推导.md §3，0.3~0.5）
    back_waist_curve_sag: float = 0.3      # 后片腰头线弧额外下凹量（后腰头绘制推导.md §二，0.3~0.5）
                                           # （0 = 无额外下凹，但 90° 正交平顺段的弯曲仍在，非直线）
    waist_rect_len: float = 1.2            # 腰弧侧缝端直角修正段长 l_rect（推导.md §3，1.0~1.5）
    rise_ratio: float = 0.25               # 直裆深系数（H 的比例，默认 H/4）
    rise_adjust: float = 0.0               # 直裆深修正量（cm）
    crotch_drop_adjust: float = 0.0        # 后片落裆调节量 Δc（落裆推导.md §2.2，-0.4~+0.3）
    back_rise_alpha: float = 0.40          # 后浪上控制柄系数 α（0.38~0.42，后浪绘制.md §3.1）
    back_rise_beta: float = 0.50           # 后浪下控制柄系数 β（0.48~0.55，紧身提臀 0.55，§3.1）
    front_crease_e: float = 0.0            # 前片裤中线调节量 e（裤中线推导.md §五，常规 0；修身 -0.5~-0.8）
    knee_adjust: float = 1.0               # 膝围前后片调整量 δ（前减后加，脚口膝围推导.md §三.1；高弹 0.5~0.75）
    hem_adjust: float = 1.0                # 脚口前后片调整量 δ（前减后加，§三.1；微喇/阔腿可微调）
    calf_arc_alpha: float = 0.10           # 小腿段弧弓高系数 α（前片弧线推导.md §三，0.08~0.12；0 = 直筒直线）
    inseam_arc_k1: float = 0.20            # 内缝大腿段小裆弯度 k1（§四，0.15~0.25）
    inseam_arc_ky: float = 0.28            # 内缝大腿段纵向系数 ky（§四）
    inseam_arc_k2: float = 0.35            # 内缝大腿段切线柄长系数（k2 = 本值×ΔY，§四）
    outseam_arc_dx: float = 0.15           # 外缝大腿段大转子外凸 δx（§五，0.1~0.2；顺直 0）
    outseam_arc_m2: float = 0.40           # 外缝大腿段切线柄长系数（m2 = 本值×ΔY，§五）
    hem_arc_sag: float = 0.0               # 脚口弧高（0 = 直线；正值向上凹入裤片，常取 0.3~0.8）
    piece_gap: float = 10.0                # 前后片排版间距（后片整体置于前片右侧，分开不重叠）
    waistband_type: WaistbandType = WaistbandType.STRAIGHT
    waistband_width: float = 4.0           # 腰头宽（直腰头打版时从版顶扣除，注意点 1）
    fit: Fit = Fit.REGULAR
    seam_allowance: float = 1.0            # 默认缝份

    def __post_init__(self) -> None:
        if not 0.0 <= self.delta <= 2.0:
            raise ValueError(f"Δ={self.delta} 超出常规范围 0~2.0 cm")
        if self.waistband_width < 0:
            raise ValueError("腰头宽不能为负数")
        if self.seam_allowance <= 0:
            raise ValueError("缝份必须为正数")

    def rise_on_pattern(self, rise: float) -> float:
        """版上浪长：前浪/后浪均为含腰头的成衣量（自腰头顶量起），
        直腰头打版时统一扣除腰头宽；弯腰头一体绘制，不扣。
        前片、后片步骤一律经本方法换算，保证扣除口径一致（注意点 1）。"""
        if self.waistband_type is WaistbandType.STRAIGHT:
            return rise - self.waistband_width
        return rise

    @classmethod
    def from_file(cls, path: str) -> "PatternOptions":
        raw = load_size_file(path).get("options", {})
        # 下划线开头的键为备注，加载时忽略（JSON 无法写注释时的兼容手段）
        data = {k: v for k, v in raw.items() if not k.startswith("_")}
        if "waistband_type" in data:
            data["waistband_type"] = WaistbandType(data["waistband_type"])
        if "fit" in data:
            data["fit"] = Fit(data["fit"].lower())
        return cls(**data)
