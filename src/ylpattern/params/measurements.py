"""成品尺寸模型。

对应 打版流程.md「核心参数」：腰围，臀围（净臀围+臀围松量），膝围，
裤口，前浪，裤长，后浪，大腿围。
"""

from __future__ import annotations

from dataclasses import dataclass

from .sizefile import load_size_file


@dataclass(frozen=True)
class Measurements:
    """成品尺寸单，单位 cm。"""

    waist: float        # 腰围（成品）
    hip: float          # 臀围 = 净臀围 + 放松量
    knee: float         # 膝围
    hem: float          # 裤口（脚口）
    front_rise: float   # 前浪
    back_rise: float    # 后浪
    outseam: float      # 裤长（外侧缝长）
    thigh: float = 0.0  # 大腿围（0 = 未录入：毗围限制为可选步骤，
                        #   无毗围尺寸则自动跳过，打版流程.md 后片步骤 8）

    def __post_init__(self) -> None:
        for f in ("waist", "hip", "knee", "hem", "front_rise",
                  "back_rise", "outseam"):
            if getattr(self, f) <= 0:
                raise ValueError(f"尺寸 {f} 必须为正数，得到 {getattr(self, f)}")
        if self.thigh < 0:
            raise ValueError(f"大腿围不能为负数（0 = 未录入），得到 {self.thigh}")
        if self.hip <= self.waist:
            raise ValueError(f"臀围({self.hip})应大于腰围({self.waist})，请检查尺寸单")
        if self.back_rise <= self.front_rise:
            raise ValueError(f"后浪({self.back_rise})应大于前浪({self.front_rise})")
        if self.outseam <= self.front_rise:
            raise ValueError(f"裤长({self.outseam})应大于前浪({self.front_rise})")

    @classmethod
    def from_file(cls, path: str) -> "Measurements":
        data = load_size_file(path)
        # 下划线开头的键为备注，加载时忽略（JSON 无法写注释时的兼容手段）
        fields = {k: v for k, v in data["measurements"].items()
                  if not k.startswith("_")}
        return cls(**fields)
