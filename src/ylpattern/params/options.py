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
    front_intake_adjust: float = 0.0       # 前中内收修正（高腰加大、低腰减小）
    rise_ratio: float = 0.25               # 直裆深系数（H 的比例，默认 H/4）
    rise_adjust: float = 0.0               # 直裆深修正量（cm）
    waistband_type: WaistbandType = WaistbandType.STRAIGHT
    fit: Fit = Fit.REGULAR
    seam_allowance: float = 1.0            # 默认缝份

    def __post_init__(self) -> None:
        if not 0.0 <= self.delta <= 2.0:
            raise ValueError(f"Δ={self.delta} 超出常规范围 0~2.0 cm")
        if self.seam_allowance <= 0:
            raise ValueError("缝份必须为正数")

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
