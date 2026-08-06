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
    back_waist_dart: float = 0.0           # 后片省量/约克转移量 V后省（约克步骤前 0；Yoke 2.5~4.0；
                                           #   后腰长容位，与绘制的腰省相互独立）
    back_dart: bool = False                # 后片腰省绘制开关（可选步骤，打版流程.md 后片步骤 9；
                                           #   只画省，不动腰头）
    back_dart_count: int = 1               # 后片省数（1 = 腰头两等分取中点；2 = 三等分取两个中点）
    back_dart_width: tuple[float, ...] | float = (2.0,)
                                           # 每个省的省量列表（默认 2cm，顺序同省中点：后中 → 侧缝）；
                                           # 写单个值则各省共用；省量为 0 的省不绘制
    back_dart_length: float = 11.0         # 省中线长（省中点沿腰头直线垂线向内，默认 11cm）
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
    back_crease_e: float = 0.0             # 后片裤中线调节量 e（§五；常规与 front_crease_e 一致，特体独立设定）
    knee_adjust: float = 1.0               # 膝围前后片调整量 δ（前减后加，脚口膝围推导.md §三.1；高弹 0.5~0.75）
    hem_adjust: float = 1.0                # 脚口前后片调整量 δ（前减后加，§三.1；微喇/阔腿可微调）
    calf_arc_alpha: float = 0.10           # 小腿段弧弓高系数 α（前片弧线推导.md §三，0.08~0.12；0 = 直筒直线）
    inseam_arc_k1: float = 0.20            # 内缝大腿段小裆弯度 k1（§四，0.15~0.25）
    inseam_arc_ky: float = 0.28            # 内缝大腿段纵向系数 ky（§四）
    inseam_arc_k2: float = 0.35            # 内缝大腿段切线柄长系数（k2 = 本值×ΔY，§四）
    outseam_arc_dx: float = 0.15           # 外缝大腿段大转子外凸 δx（§五，0.1~0.2；顺直 0）
    outseam_arc_m2: float = 0.40           # 外缝大腿段切线柄长系数（m2 = 本值×ΔY，§五）
    back_calf_arc_alpha: float = 0.10      # 后片小腿段弧弓高系数 α（后片弧线推导.md §二，0.08~0.12；0 = 直筒直线）
    back_inseam_arc_k1: float = 0.30       # 后内缝大腿段大裆弯度 k1（§三，0.25~0.35，大于前片留运动空间）
    back_inseam_arc_ky: float = 0.30       # 后内缝大腿段纵向系数 ky（§三，= 0.30）
    back_inseam_arc_k2: float = 0.35       # 后内缝大腿段切线柄长系数（k2 = 本值×ΔY，§三）
    back_outseam_arc_dx: float = 0.15      # 后外缝大腿段臀侧饱满度 δx（§四，0.1~0.25；顺直 0）
    back_outseam_arc_m2: float = 0.40      # 后外缝大腿段切线柄长系数（m2 = 本值×ΔY，§四）
    back_hipwaist_arc_dx1: float = 0.15    # 臀侧凸出多少（§五，0~0.3；0 = 顺直不凸，越大越往外鼓）
    back_hipwaist_arc_k1: float = 0.40     # 臀侧凸感延续多高（§五，0.35~0.45；越大越晚往腰头弯）
    back_hipwaist_arc_dx2: float = 0.0     # 腰头角点凸出多少（§五，0~0.3；0 = 竖直顺直进角，越大角点越鼓）
    back_hipwaist_arc_k2: float = 0.25     # 多早往腰头收（§五，0.20~0.30；越大上段越早内缩、末端笔直进角）
    front_hem_arc_sag: float = 0.0         # 前片脚口弧高（0 = 直线；正值向下凸出裤片，常取 0.3~0.8）
    back_hem_arc_sag: float = 0.0          # 后片脚口弧高（口径同前片，前后片独立录入）
    thigh_limit: bool = False              # 毗围闭环修正开关（可选步骤，打版流程.md 后片步骤 8）
    thigh_measure_offset: float = 0.0      # 毗围实测下移量 d（0 = 立裆深线直量；常规实测 2.54，前后片毗围推导.md §一）
    # —— 毗围闭环修正控制参数（前后片毗围推导.md §三，默认值即文档规范值） ——
    thigh_piece_split_max: float = 0.2     # 片间分配分界：|ΔW| ≤ 本值平分，否则按大差量比（§三.1）
    thigh_front_share: float = 0.2         # 大差量前片分配比（后片 = 1 − 本值；红线：严禁 50:50，§三.1）
    thigh_dual_track_min: float = 0.3      # 双轨分流阈值：|ΔW| ≤ 本值单动侧缝，否则内外联动（§三.2）
    thigh_front_crotch_coef: float = 0.09  # 前小裆尖调拨系数（ΔX前 = 本值×ΔW，§三.2）
    thigh_back_crotch_coef: float = 0.21   # 后大裆尖调拨系数（ΔX后 = 本值×ΔW，§三.2）
    thigh_front_crotch_max: float = 0.4    # 前小裆累计调整上限（防卡耻骨，极值红线，§三.2）
    thigh_back_crotch_max: float = 1.0     # 后大裆累计调整上限（防下蹲崩破，极值红线，§三.2）
    thigh_max_iter: int = 6                # 闭环最大迭代轮数（§三.3；侧缝被钳后仅靠裆宽收敛慢，可加大）
    thigh_tol: float = 0.3                 # 闭环收敛容差（§三.3；|ΔW| ≤ 本值即判定达标）
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
        if self.thigh_measure_offset < 0:
            raise ValueError("毗围实测下移量 d 不能为负数")
        if self.back_dart_count not in (1, 2):
            raise ValueError(f"后片省数只支持 1 或 2，得到 {self.back_dart_count}")
        # 省量归一化为元组：标量 → 单元素；单元素且两个省 → 广播共用
        widths = self.back_dart_width
        if isinstance(widths, (int, float)):
            widths = (float(widths),)
        else:
            widths = tuple(float(w) for w in widths)
        if len(widths) == 1 and self.back_dart_count == 2:
            widths = widths * 2
        if len(widths) != self.back_dart_count:
            raise ValueError(f"省量个数须等于省数 {self.back_dart_count}，"
                             f"得到 {len(widths)} 个")
        if any(w < 0 for w in widths):
            raise ValueError(f"省量不能为负数，得到 {widths}")
        object.__setattr__(self, "back_dart_width", widths)
        if self.back_dart_length <= 0:
            raise ValueError(f"省中线长必须为正数，得到 {self.back_dart_length}")
        if not 0.0 < self.thigh_front_share < 1.0:
            raise ValueError(f"大差量前片分配比须在 (0, 1) 内，得到 {self.thigh_front_share}")
        for name in ("thigh_piece_split_max", "thigh_dual_track_min",
                     "thigh_front_crotch_coef", "thigh_back_crotch_coef",
                     "thigh_front_crotch_max", "thigh_back_crotch_max"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} 不能为负数，得到 {getattr(self, name)}")
        if self.thigh_max_iter < 1:
            raise ValueError(f"闭环最大迭代轮数必须 ≥ 1，得到 {self.thigh_max_iter}")
        if self.thigh_tol <= 0:
            raise ValueError(f"闭环收敛容差必须为正数，得到 {self.thigh_tol}")

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
