"""版型选项：经验值统一收敛于此，公式层与步骤层不硬编码经验常数。"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from .sizefile import load_size_file


class WaistbandType(enum.Enum):
    """腰头类型（打版流程.md「注意点 1」）。"""

    STRAIGHT = "straight"  # 直腰头：打版时直接扣除腰头宽，腰头单独成片
    CURVED = "curved"      # 弯腰头：与前片一体绘制，裁切阶段再裁出


class WaistbandGrain(enum.Enum):
    """腰头裁片经向（面料 warp）方向（腰头裁片.md §五.2）。

    经向是面料属性、全局统一：前后片丝缕线（裤中线）沿裤长（Y），即全局经向=裤长。
    腰头从标准铺布横裁时其宽向（=裤长=Y）即经向，故默认 WIDTH。
    """

    WIDTH = "width"    # 宽向（=裤长=Y）为经向（默认；标准铺布横裁）
    LENGTH = "length"  # 长向（腰头周向=X）为经向（直裁）


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
class WaistbandSeamAllowances:
    """腰头裁片四边独立缝份（cm，腰头裁片.md §二.3）。

    full_piece=True 时四边均为裁切边（后中为折线不外扩）：
    top 上口线 / bottom 下口线（拼接线）/ left_end 左端（含门襟搭门侧）/
    right_end 右端（常规侧）。
    """
    top: float = 1.0
    bottom: float = 1.0
    left_end: float = 1.2
    right_end: float = 1.0

    @classmethod
    def from_dict(cls, d: dict) -> "WaistbandSeamAllowances":
        return cls(top=float(d.get("top", 1.0)),
                   bottom=float(d.get("bottom", 1.0)),
                   left_end=float(d.get("left_end", 1.2)),
                   right_end=float(d.get("right_end", 1.0)))


@dataclass(frozen=True)
class YokeSeamAllowances:
    """后机头/育克裁片四边独立缝份（cm，机头裁片.md §4.1）。

    底边（拼后大身、埋夹工艺）做阴阳缝份 1.2~1.5；腰口/后中/侧缝常规 1.0~1.2。
    top 腰口（上腰头/拷边）/ bottom 底边（埋夹）/ cb 后中（拼对称片）/
    side 侧缝（拼前片侧缝）。后中为拼合线仍外扩（非折线），与腰头后中折线不同。
    """
    top: float = 1.0
    bottom: float = 1.2
    cb: float = 1.0
    side: float = 1.0

    @classmethod
    def from_dict(cls, d: dict) -> "YokeSeamAllowances":
        return cls(top=float(d.get("top", 1.0)),
                   bottom=float(d.get("bottom", 1.2)),
                   cb=float(d.get("cb", 1.0)),
                   side=float(d.get("side", 1.0)))


@dataclass(frozen=True)
class FrontFacingSeamAllowances:
    """前口袋袋贴裁片三边独立缝份（cm，前口袋裁片.md §2.1）。

    袋贴外边界完美复制前大片（腰弧段 + 外缝弧段），三条边均与大片拼合：
    waist 腰弧段（车入腰头）/ inner 袋贴内边（接袋布）/ side 外缝弧段（车入侧缝）。
    """
    waist: float = 1.0
    inner: float = 1.0
    side: float = 1.0

    @classmethod
    def from_dict(cls, d: dict) -> "FrontFacingSeamAllowances":
        return cls(waist=float(d.get("waist", 1.0)),
                   inner=float(d.get("inner", 1.0)),
                   side=float(d.get("side", 1.0)))


@dataclass(frozen=True)
class FrontPatchSeamAllowances:
    """前贴袋裁片缝份（cm，前口袋裁片.md §2.2）。

    贴袋为折边口袋：top 袋口内折边（向反面折转缝合，常规 3.0 = 30mm 双折）；
    side 四周缝边（常规 1.2 = 12mm，含底边与两侧、最终折光车缝到前大片）。
    """
    top: float = 3.0
    side: float = 1.2

    @classmethod
    def from_dict(cls, d: dict) -> "FrontPatchSeamAllowances":
        return cls(top=float(d.get("top", 3.0)),
                   side=float(d.get("side", 1.2)))


@dataclass(frozen=True)
class PouchSeamAllowances:
    """前口袋袋布裁片缝份（cm，口袋布裁片.md §4）。

    一片式对折裁片五语义边：fold 对折线（内边对称轴，放量为 0，内部边周界不使用）/
    mouth 挖削袋口弧线（常规 1.0）/ waist 腰头边（与前片腰头缝份一致）/
    side 侧缝边（与前片侧缝缝份一致）/ bottom 袋底与外围（1.0~1.5）。
    """
    fold: float = 0.0
    mouth: float = 1.0
    waist: float = 1.0
    side: float = 1.0
    bottom: float = 1.2

    @classmethod
    def from_dict(cls, d: dict) -> "PouchSeamAllowances":
        return cls(fold=float(d.get("fold", 0.0)),
                   mouth=float(d.get("mouth", 1.0)),
                   waist=float(d.get("waist", 1.0)),
                   side=float(d.get("side", 1.0)),
                   bottom=float(d.get("bottom", 1.2)))


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
    # -- 后机头/育克（back yoke）：后片腰部横向分割育克裁片（后机头绘制.md） --
    back_yoke: bool = False                # 后机头绘制开关（可选步骤，打版流程.md「后机头/育克绘制」；
                                           #   只上版分割下口线，不做布尔裁除--先画后裁）
    back_yoke_cb_dist: float = 4.0         # P0 后浪端点：自腰头内缝顶点沿后浪线向下量取的弧长 D_cb
                                           #   （cm，§1；机头后中深度）
    back_yoke_side_dist: float = 3.0       # PN 侧缝端点：自腰头外缝顶点沿外缝线向下量取的弧长 D_side
                                           #   （cm，§1；机头侧缝深度；D_cb − D_side = 倾斜落差 ΔH）
    back_yoke_mid_anchors: tuple[tuple[float, float], ...] = ()
                                           # 下口线中间控制点（§2 N-Point 分段拓扑）：
                                           #   每个 = (u, depth)，u = P0->PN 弦上位置比例 0~1（严格递增）、
                                           #   depth = 偏离弦的深度（cm，正值向下凸入裤身、0 = 压弦、负值上凸）；
                                           #   空 = 直线下口（打版流程.md：无锚点即直线）
    back_yoke_edges: tuple = ()
                                           # 下口线分段形态（§2.2 LINEAR/CURVE），个数 = 中间锚点数 + 1
                                           #   （P0->P1、…、Pn->PN 逐段）：
                                           #   ("line",) 直线 / ("arc", 弧高, 弧顶分位 0~1) 弧高式
                                           #   / ("bezier", α°, κ1, β°, κ2) 双手柄贝塞尔
                                           #   （夹角相对弦向，κ 为弦长比，§2.2；与袋布/小表袋边形态同口径）
                                           #   空 = 全段直线（自动；打版流程.md：无控制点即直线，省略 edges 即可）
    back_yoke_seam_allowances: YokeSeamAllowances = field(
        default_factory=YokeSeamAllowances)
                                           # 机头裁片四边独立缝份（§4.1；缝份不叠加缩水）：
                                           #   底边埋夹 1.2、腰口/后中/侧缝 1.0（阴阳缝份另调）
    back_yoke_join_fillet: float = 0.4     # 有省拼合处折角 G1 倒圆的退弧量 δ（cm，§2.2.3；
                                           #   入/出边各退 δ 弧长后插三次贝塞尔圆顺）
    back_yoke_side_corner_mirror: bool = True  # 内缝顶点（bottom×side）缝份镜像折角：侧缝缝份
                                           #   边界取原侧缝切线关于底边缝折线垂线的轴对称镜像，车缝
                                           #   翻折后与裁片重合（机头裁片.md §4.2.1；直角退化即 miter；
                                           #   False=纯 miter）
    back_yoke_cb_corner_mirror: bool = True    # 后中底角（bottom×cb）缝份镜像折角：同侧缝口径，
                                           #   后中缝份边界取原后中切线关于底边缝折线垂线的轴对称镜像
                                           #   （§4.2.1；直角退化即 miter；False=纯 miter）
    back_yoke_shrinkage_warp: float | None = None
                                           # 机头裁片经向缩水率（None=用全局
                                           #   shrinkage_warp；换布/不同批次时可单独控制，§3/§5）
    back_yoke_shrinkage_weft: float | None = None
                                           # 机头裁片纬向缩水率（None=用全局 shrinkage_weft）
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
    front_rise_handle_ratio: float = 1 / 3  # 前浪裆弯控制柄比例（k1=k2=|BC|×本值；默认 1/3，前浪绘制.md §4；越大弧线越饱满）
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
    # —— 前口袋：挖削嵌入式（INSET）主切口（前口袋绘制.md §二、§三） ——
    front_pocket: bool = False             # 前口袋主切口绘制开关（可选步骤；只画切口边界，
                                           #   不做布尔裁除——先画后裁，裁切层未建）
    front_pocket_p1_dist: float = 8.5      # P1 锚点：腰弧上自腰外缝顶点朝前浪顶点的弧长距离（cm，§二）
    front_pocket_p2_drop: float = 7.5      # P2 锚点：外缝弧上自腰外缝顶点向下的弧长深度（cm，§二）
    front_pocket_dart_width: float = 2.0   # 腰头吃省总宽 ΔW_dart（cm，§三.1，常规 1.5~2.5；
                                           #   P1′ = P1 沿腰弧朝前浪顶点量取，省顶点落在腰头线上；
                                           #   袋口线按 V·(1−t)ⁿ 共线渐变偏置，侧缝端衰减至 0；
                                           #   0 = 不吃省，切削线 = 设计净线）
    front_pocket_paring_n: float = 2.0     # 撇削衰减幂指数 n（§三.1，常规 1.5~2.0；
                                           #   越大吃量越集中在腰头端）
    front_pocket_mouth_bulge: float = 0.5  # 袋口母线 C(t) 弧高（bulge 模式；正值向裤片内侧凹入
                                           #   加深勺口；0 = 直口）
    front_pocket_mouth_bulge_at: float = 0.5
                                           # 袋口弧顶位置（bulge 模式；弦长比例 0~1，0 = 腰头端、
                                           #   1 = 侧缝端；中点 0.5；最低点偏侧缝端取 0.6~0.7）
    front_pocket_mouth_mode: str = "bulge" # 袋口净线模式（§二 曲线控制函数）：
                                           #   "bulge"    = 弧高式（bulge / bulge_at 控制）
                                           #   "tangent"  = 两端垂直式：P1 端切线 ⟂ 腰弧切线、
                                           #                P2 端切线 ⟂ 外缝弧切线（h1/h2 控制）
                                           #   "polyline" = 折角式（带倒角折线：P1 → 折角 K → P2，
                                           #                corner_at / corner_depth 控制）
    front_pocket_mouth_h1: float = 3.0     # 腰头端切线柄长（tangent 模式，cm；越大勺口越深）
    front_pocket_mouth_h2: float = 3.0     # 侧缝端切线柄长（tangent 模式，cm）
    front_pocket_mouth_corners: tuple[tuple[float, float], ...] = ((0.55, 1.5),)
                                           # 折角列表（polyline 模式；每个折角 = (弦上位置 0~1,
                                           #   内推深度 cm)，按位置严格递增，可多个；
                                           #   空列表 = 直袋口）
    # -- 前口袋袋贴（facing）：挖削嵌入式袋口贴布裁片（前口袋绘制.md §三.3.(1)） --
    front_pocket_facing: bool = False      # 袋贴绘制开关（可选步骤，依赖 front_pocket 主切口；
                                           #   只上版袋贴边界，不做布尔裁除--先画后裁）
    front_pocket_facing_width: float = 3.5 # 袋贴宽 w_facing（cm，即距离 A；腰头端量取距离 =
                                           #   侧缝端下落距离 = 内边缘法向偏置间距，三者等距，§三.3.(1)；
                                           #   常规 3.0~4.0，schema facing_width_mm=35）
    front_pocket_facing_side_w: float = 0.0 # 侧缝端袋贴深度 w_side（cm；0 = 与腰头端同宽，
                                           #   常规 5.0~7.0；非 0 时启用两端独立宽度）
    front_pocket_facing_mode: str = "offset" # 袋贴内边模式：
                                           #   "tangent" = 两端垂直式（推荐，P_fw ⟂ 腰弧、P_fs ⟂ 外缝弧）
                                           #   "offset"  = 传统等距偏置（控制点域近似 / 折角平移）
                                           #   "bulge"   = 弧高式浅弧
    front_pocket_facing_h1: float = 5.0    # 腰头端切线柄长（tangent 模式，cm；越大腰端平缓下垂越长）
    front_pocket_facing_h2: float = 4.0    # 侧缝端切线柄长（tangent 模式，cm；越大侧缝端平缓进深越长）
    front_pocket_facing_bulge: float = 0.0 # 袋贴内边弧高（bulge 模式，cm；正值向裤身内侧凹入）
    front_pocket_facing_bulge_at: float = 0.5 # 弧顶位置（bulge 模式；弦长比例 0~1，默认 0.5）
    # —— 前贴袋：表面外贴式（PATCH）独立样板（前口袋绘制.md §四；前片不裁切） ——
    front_patch: bool = False              # 前贴袋绘制开关（净样上版即表面定位标记，§四.1）
    front_patch_top_drop: float = 10.0     # 袋口外上角自腰外缝顶点垂直向下（cm）
    front_patch_top_inset: float = 2.0     # 袋口外上角自侧缝水平向内（cm）
    front_patch_width: float = 14.0        # 袋口宽（cm）
    front_patch_height: float = 15.0       # 袋身高（cm）
    front_patch_shape: str = "rectangle"   # 净形（§五 net_outline_type）：
                                           #   "rectangle" 方底 / "baker_shield" 盾形尖底
                                           #   / "angular" 底角斜切 / "custom" 全自定义
    front_patch_bottom_width: float = 0.0  # 袋底宽（baker_shield/angular，cm；
                                           #   0 = 与袋口同宽，底边两侧对称内收）
    front_patch_rotate_deg: float = 0.0    # 贴袋整体绕袋口外上角旋转角（度，顺时针为正；
                                           #   调整贴袋摆放角度，各形态与 custom 均生效）
    front_patch_tip_depth: float = 2.5     # 盾形底尖额外深度（baker_shield，cm）
    front_patch_chamfer: float = 2.0       # 底角斜切量（angular，cm）
    front_patch_custom_points: tuple[tuple[float, float], ...] = ()
                                           # custom 净形角点列表（相对袋口外上角的 dx/dy，
                                           #   ≥3 个，顺时针绕行）
    front_patch_custom_edges: tuple[tuple[float, float], ...] = ()
                                           # custom 每边形态：(弧高, 弧顶位置 0~1)，
                                           #   弧高 0 = 直线，正值沿左手法向凸；
                                           #   个数须等于角点数（闭合边）
    # -- 后贴袋：表面外贴式（PATCH）独立样板（后贴袋绘制.md §一~§三；
    #    依赖后机头下口线育克底线定位，须先开 back_yoke） --
    back_patch: bool = False              # 后贴袋绘制开关（净样上版即表面定位标记，
                                           #   §三 02_MARKING / 03_PATCH_NET；先画后裁）
    back_patch_inset_x: float = 4.5       # 距离后浪线的距离：自后浪线沿约克底线朝侧缝
                                           #   量取（cm，§一.2 inset_x；常规 4.0~5.5）
    back_patch_drop_y: float = 3.5        # 距离约克底线的距离：自约克底线向下量取
                                           #   （cm，§一.2 drop_y；常规 3.0~4.5）
    back_patch_width: float = 14.0        # 袋口宽 W（cm，§二.1）
    back_patch_height: float = 16.0       # 袋身高 H（cm，§二.1）
    back_patch_shape: str = "rectangle"   # 净形（§二.1 形态路由）：
                                           #   "rectangle" 方底 / "baker_shield" 盾形尖底
                                           #   / "angular" 底角斜切 / "custom" 全自定义
    back_patch_bottom_width: float = 0.0  # 袋底宽（baker_shield/angular，cm；
                                           #   0 = 与袋口同宽，底边两侧对称内收）
    back_patch_rotate_deg: float = 0.0    # 贴袋整体绕袋口近后浪侧顶点旋转角（度，
                                           #   顺时针为正，§二.2 θ；默认 0 = 平行约克底线≈后腰线）
    back_patch_tip_depth: float = 2.5     # 盾形底尖额外深度（baker_shield，cm，§二.1 D_tip）
    back_patch_chamfer: float = 2.0       # 底角斜切量（angular，cm，§二.1 C_chamfer）
    back_patch_custom_points: tuple[tuple[float, float], ...] = ()
                                           # custom 净形角点列表（局部 u-v：u 朝侧缝 +、
                                           #   v 向下 +，相对袋口近后浪侧顶点，≥3 个，顺时针）
    back_patch_custom_edges: tuple[tuple[float, float], ...] = ()
                                           # custom 每边形态：(弧高, 弧顶位置 0~1)，
                                           #   弧高 0 = 直线，正值沿左手法向凸；
                                           #   个数须等于角点数（闭合边）
    # —— 袋布（pouch）：嵌入式前口袋储物袋布大片/小片（袋布绘制.md §一~§五） ——
    front_pouch: bool = False              # 袋布绘制开关（依赖前口袋主切口，须先开 front_pocket）
    front_pouch_waist_safe: float = 4.0    # 腰缝锚点安全内延 ΔW_safe（沿腰弧自 P1 朝门襟，
                                           #   cm，文档推荐 3.5~5.0，§二.1）
    front_pouch_side_safe: float = 8.0     # 侧缝锚点安全垂深 ΔH_safe（自 P2 沿侧缝下探，
                                           #   cm，文档推荐 6.0~10.0，§二.2）
    front_pouch_nodes: tuple[tuple[float, float], ...] = ((5.0, 16.0), (1.5, 13.5))
                                           # 自定义内部节点列表 K（≥2 个；相对局部原点
                                           #   O = 腰外缝顶点，x 朝门襟 +、y 向下 +，§三.1）
    front_pouch_edges: tuple = (("line",), ("arc", 2.5, 0.6), ("line",))
                                           # 边形态列表，个数 = 节点数 + 1
                                           #   （P_w0→K1、Ki→Ki+1、Kn→P_s0 逐边）：
                                           #   ("line",) 直线
                                           #   ("arc", 弧高h, 弧顶分位 0.1~0.9) 弧高式
                                           #   ("bezier", α°, κ1, β°, κ2) 双手柄贝塞尔
                                           #   （夹角相对弦向，κ 为弦长比，§三.2）
    # -- 小表袋（watch pocket）：嵌于挖削嵌入式前口袋内的小贴袋（小表袋绘制.md） --
    watch_pocket: bool = False              # 小表袋开关（依赖 front_pocket 挖削嵌入式；
                                           #   打版流程.md：当前口袋是挖削嵌入式时才绘制）
    watch_pocket_mode: str = "facing_intersect"       # 模式：
                                           #   "custom" = 自定义多锚点多形态（现状）
                                           #   "facing_intersect" = 袋贴相交延伸模式（新模式）
    watch_pocket_width: float = 7.5        # 袋口宽 W（facing_intersect 模式，cm，常规 7.0~8.5）
    watch_pocket_taper: float = 0.3        # 两侧向内收倾斜量（facing_intersect 模式，cm；
                                           #   0 = 垂直下落，>0 为梯形微收）
    watch_pocket_offset_from_top: float = 4.0
                                           # 离口袋顶部距离：自前口袋侧缝腰点垂直向下（cm，
                                           #   小表袋绘制.md §2.3 offset_y_from_pocket_top）
    watch_pocket_offset_from_side: float = 3.5
                                           # 离口袋侧边距离：自侧缝水平向内（cm，§2.3
                                           #   offset_x_from_side_seam）
    watch_pocket_rotate_deg: float = 0.0    # 整体旋转角（度，顺时针为正，绕参考点，
                                           #   §2.3/§3.2 global_rotation）
    watch_pocket_points: tuple[tuple[float, float], ...] = (
        (0.0, 0.0), (8.0, 0.0), (7.6, 7.5), (0.4, 7.5))
                                           # 净形锚点（相对参考点 dx/dy，dy 向下为正，≥3 个，顺时针；
                                           #   默认梯形：袋口宽 8、底宽 7.2、高 7.5，
                                           #   taper=(8−7.2)/2=0.4；打版流程.md：锚点最少三个点）
    watch_pocket_edges: tuple = (("line",), ("line",), ("line",), ("line",))
                                           # 边形态列表，个数 = 锚点数（闭合边）：
                                           #   ("line",) 直线 / ("arc", 弧高, 弧顶分位) 弧高式
                                           #   / ("bezier", α°, κ1, β°, κ2) 双手柄贝塞尔
                                           #   （打版流程.md：每段弧线/贝塞尔/直线可控制）
    # —— 门襟（连裁门襟，门襟绘制.md §2.2、§3、§4） ——
    fly: bool = False                    # 门襟绘制开关（可选步骤；连裁门襟上版于前片）
    fly_width: float = 3.8               # 门襟宽 W（常规 YKK 5# 拉链，3.5~4.2）
    fly_length_ratio: float = 0.35       # 开深系数（L = 本值 × 前浪 + fly_length_base，§2.2）
    fly_length_base: float = 2.0         # 开深基值（cm，§2.2）
    fly_turnback: float = 0.25           # 牛仔布折转退层补偿 Δw（腰口顶端内收，§3.1）
    fly_corner_inset: float = 0.8        # 底角圆角内收量（连裁 + 独立共用；角弧半径 R = W − 本值，
                                         #   默认 0.8 -> R=3.0；越大角越紧，须 0<本值<W，§3.2/§5）
    fly_corner_turn: float = 1.0         # 拐点 P_turn 在 J 型角弧上的弧位（90° 角弧比例；
                                         #   1.0 = J 底（默认，角弧终点）；越小拐点越靠上、
                                         #   角弧越短、融合弧越长。过小会要求很大下移量，§3.2）
    fly_blend_drop: float | None = None  # 融合点 P2 较开深 L 的下移量（cm，§3.2.3）；
                                         #   None = 自动（W−R，且不小于拐点所需最小下移量）；
                                         #   手动录入须 ≥ 该最小值，否则抛错（防波浪）
    fly_stitch_inset: float = 0.6        # J 字明线内收（明线 = 顺外边向内等距偏置本值，§4.2 简化；
                                         #   剪口刀口、打枣点等工艺细节暂不绘制，留待工艺/裁切模块）
    # —— 独立门襟（分裁/外接门襟，门襟绘制.md §5；先画后裁，缝份留待裁切模块） ——
    fly_separate: bool = False           # 独立门襟开关：开启后生成独立门襟裁片（左前片
                                         #   不连裁）；fly / fly_separate 任一开启即绘制，
                                         #   fly_separate 优先（互斥形态）
    fly_sep_extra: float = 2.0           # 底部延展量（裁片高 = L + 本值，§5；
                                         #   上部腰口车合量属裁切层缝份）
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
    # -- 腰头裁片（腰头裁片.md §二，独立裁片：净样 -> 缩水 -> 缝边）--
    waistband_front_drop: float | None = None  # 弯腰头弧深量（cm，正数=下口线向下凹 ∪）；None=按侧缝夹角自动推算（§四.分支B），填值则手动覆盖
    waistband_fly_extension: float = 3.5   # 门襟搭门量/宝剑头长（cm，左片前中端外延，§三.3）
    waistband_full_piece: bool = True      # True=整条（后中折线对称）；False=沿后中分两片（本期实现 True）
    waistband_grain: WaistbandGrain = WaistbandGrain.WIDTH
                                           # 腰头经向方向（§五.2）：WIDTH 宽向=经（默认，横裁）/ LENGTH 长向=经（直裁）
    shrinkage_warp: float = 0.0            # 经向缩水率（面料经/warp；0.03 表示 3%，§二.2/§五.2）
    shrinkage_weft: float = 0.0            # 纬向缩水率（面料纬/weft，§二.2/§五.2）
    waistband_seam_allowances: WaistbandSeamAllowances = field(
        default_factory=WaistbandSeamAllowances)
                                           # 四边独立缝份（§二.3/§五.3；缝份不叠加缩水）
    # -- 前口袋裁片缝份（前口袋裁片.md §2；先缩水后缝边，缝份不叠加缩水）--
    front_pocket_facing_seam_allowances: FrontFacingSeamAllowances = field(
        default_factory=FrontFacingSeamAllowances)
                                           # 袋贴裁片三边缝份（waist/inner/side）
    front_patch_seam_allowances: FrontPatchSeamAllowances = field(
        default_factory=FrontPatchSeamAllowances)
                                           # 贴袋裁片缝份（top 内折边 / side 四周缝边）
    front_pocket_shrinkage_warp: float | None = None
                                           # 前口袋裁片（袋贴/贴袋）经向缩水率（None=用全局
                                           #   shrinkage_warp；换布/不同批次时可单独控制，§2.1）
    front_pocket_shrinkage_weft: float | None = None
                                           # 前口袋裁片纬向缩水率（None=用全局 shrinkage_weft）
    # -- 袋布裁片缝份/缩水（口袋布裁片.md §3、§4；先缩水后缝边，缝份不叠加缩水）--
    front_pouch_seam_allowances: PouchSeamAllowances = field(
        default_factory=PouchSeamAllowances)
                                           # 袋布裁片五边缝份（fold/mouth/waist/side/bottom）：
                                           #   对折线 0、袋口 1.0、腰头/侧缝与前片一致、袋底 1.2（§4）
    front_pouch_shrinkage_warp: float = 0.0
                                           # 袋布裁片经向缩水率（口袋布材质独立，§3 强制 0、
                                           #   绝对隔离大身面料缩水；默认 0=不缩水，可单独覆盖）
    front_pouch_shrinkage_weft: float = 0.0
                                           # 袋布裁片纬向缩水率（默认 0=不缩水，§3）
    fit: Fit = Fit.REGULAR
    seam_allowance: float = 1.0            # 默认缝份

    def __post_init__(self) -> None:
        if not 0.0 <= self.delta <= 2.0:
            raise ValueError(f"Δ={self.delta} 超出常规范围 0~2.0 cm")
        if self.waistband_width < 0:
            raise ValueError("腰头宽不能为负数")
        # 腰头裁片参数校验（腰头裁片.md §二）
        if (self.waistband_front_drop is not None
                and self.waistband_front_drop < 0):
            raise ValueError(f"弯腰头弧深量不能为负数（凸向已内置向下凹 ∪，勿传负），得到 {self.waistband_front_drop}")
        if self.waistband_fly_extension < 0:
            raise ValueError(f"门襟搭门量不能为负数，得到 {self.waistband_fly_extension}")
        for name in ("shrinkage_warp", "shrinkage_weft"):
            v = getattr(self, name)
            if not 0.0 <= v < 0.2:
                raise ValueError(f"{name} 须在 [0, 0.2) 内（0.03=3%），得到 {v}")
        sa = self.waistband_seam_allowances
        if not isinstance(sa, WaistbandSeamAllowances):
            raise TypeError("waistband_seam_allowances 须为 WaistbandSeamAllowances")
        for name in ("top", "bottom", "left_end", "right_end"):
            if getattr(sa, name) < 0:
                raise ValueError(f"缝份 {name} 不能为负数，得到 {getattr(sa, name)}")
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
        # 后机头：端点距离/锚点/边形态校验（后机头绘制.md §1、§2）
        if self.back_yoke_cb_dist <= 0:
            raise ValueError(f"机头后浪端点距离必须为正数，得到 {self.back_yoke_cb_dist}")
        if self.back_yoke_side_dist <= 0:
            raise ValueError(f"机头侧缝端点距离必须为正数，得到 {self.back_yoke_side_dist}")
        yanchors = tuple((float(u), float(d)) for u, d in self.back_yoke_mid_anchors)
        for u, d in yanchors:
            if not 0.0 < u < 1.0:
                raise ValueError(f"机头锚点弦上位置须在 (0, 1) 内，得到 {yanchors}")
            if abs(d) > 10.0:
                raise ValueError(f"机头锚点深度绝对值不超过 10.0，得到 {yanchors}")
        if any(yanchors[i + 1][0] <= yanchors[i][0]
               for i in range(len(yanchors) - 1)):
            raise ValueError(f"机头锚点弦上位置须严格递增，得到 {yanchors}")
        yedges: list = []
        if len(self.back_yoke_edges) == 0:
            # 空 edges = 全段直线（打版流程.md：无控制点即直线；省略 edges 即直线连接）
            yedges = [("line",)] * (len(yanchors) + 1)
        else:
            for e in self.back_yoke_edges:
                spec = (e[0],) + tuple(float(x) for x in e[1:])
                if spec[0] == "line":
                    if len(spec) != 1:
                        raise ValueError(f"line 边不带参数，得到 {e}")
                elif spec[0] == "arc":
                    if len(spec) != 3:
                        raise ValueError(f"arc 边须为 (弧高, 弧顶分位)，得到 {e}")
                    if abs(spec[1]) > 10.0:
                        raise ValueError(f"arc 弧高绝对值不超过 10.0，得到 {e}")
                    if not 0.0 < spec[2] < 1.0:
                        raise ValueError(f"arc 弧顶分位须在 (0, 1) 内，得到 {e}")
                elif spec[0] == "bezier":
                    if len(spec) != 5:
                        raise ValueError(f"bezier 边须为 (α°, κ1, β°, κ2)，得到 {e}")
                    if abs(spec[1]) > 90.0 or abs(spec[3]) > 90.0:
                        raise ValueError(f"bezier 夹角建议在 ±90° 内，得到 {e}")
                    if not 0.0 < spec[2] <= 1.0 or not 0.0 < spec[4] <= 1.0:
                        raise ValueError(f"bezier 手柄弦长比须在 (0, 1] 内，得到 {e}")
                else:
                    raise ValueError(f"机头边形态只支持 line / arc / bezier，得到 {e}")
                yedges.append(spec)
            if len(yedges) != len(yanchors) + 1:
                raise ValueError(f"机头边形态个数须为锚点数 + 1（{len(yanchors) + 1}），"
                                 f"得到 {len(yedges)} 个")
        object.__setattr__(self, "back_yoke_mid_anchors", yanchors)
        object.__setattr__(self, "back_yoke_edges", tuple(yedges))
        # 机头裁片缝份/倒圆校验（机头裁片.md §4.1、§2.2.3）
        ysa = self.back_yoke_seam_allowances
        if not isinstance(ysa, YokeSeamAllowances):
            raise TypeError("back_yoke_seam_allowances 须为 YokeSeamAllowances")
        for name in ("top", "bottom", "cb", "side"):
            if getattr(ysa, name) < 0:
                raise ValueError(f"机头缝份 {name} 不能为负数，得到 {getattr(ysa, name)}")
        if self.back_yoke_join_fillet < 0:
            raise ValueError(f"机头拼合倒圆量不能为负数，得到 {self.back_yoke_join_fillet}")
        # 前口袋袋贴/贴袋裁片缝份校验（前口袋裁片.md §2）
        # 机头裁片专用缩水（None=用全局 shrinkage_warp/weft；非 None 须在 [0, 0.2)）
        for name in ("back_yoke_shrinkage_warp", "back_yoke_shrinkage_weft"):
            v = getattr(self, name)
            if v is not None and not 0.0 <= v < 0.2:
                raise ValueError(f"{name} 须在 [0, 0.2) 内（None=用全局，0.03=3%），"
                                 f"得到 {v}")
        fsa = self.front_pocket_facing_seam_allowances
        if not isinstance(fsa, FrontFacingSeamAllowances):
            raise TypeError("front_pocket_facing_seam_allowances 须为 "
                            "FrontFacingSeamAllowances")
        for name in ("waist", "inner", "side"):
            if getattr(fsa, name) < 0:
                raise ValueError(f"袋贴缝份 {name} 不能为负数，得到 {getattr(fsa, name)}")
        psa = self.front_patch_seam_allowances
        if not isinstance(psa, FrontPatchSeamAllowances):
            raise TypeError("front_patch_seam_allowances 须为 "
                            "FrontPatchSeamAllowances")
        for name in ("top", "side"):
            if getattr(psa, name) < 0:
                raise ValueError(f"贴袋缝份 {name} 不能为负数，得到 {getattr(psa, name)}")
        # 前口袋裁片专用缩水（None=用全局 shrinkage_warp/weft；非 None 须在 [0, 0.2)）
        for name in ("front_pocket_shrinkage_warp", "front_pocket_shrinkage_weft"):
            v = getattr(self, name)
            if v is not None and not 0.0 <= v < 0.2:
                raise ValueError(f"{name} 须在 [0, 0.2) 内（None=用全局，0.03=3%），"
                                 f"得到 {v}")
        # 袋布裁片缝份/缩水校验（口袋布裁片.md §3、§4）
        pusa = self.front_pouch_seam_allowances
        if not isinstance(pusa, PouchSeamAllowances):
            raise TypeError("front_pouch_seam_allowances 须为 "
                            "PouchSeamAllowances")
        for name in ("fold", "mouth", "waist", "side", "bottom"):
            if getattr(pusa, name) < 0:
                raise ValueError(f"袋布缝份 {name} 不能为负数，得到 {getattr(pusa, name)}")
        for name in ("front_pouch_shrinkage_warp", "front_pouch_shrinkage_weft"):
            v = getattr(self, name)
            if not 0.0 <= v < 0.2:
                raise ValueError(f"{name} 须在 [0, 0.2) 内（口袋布默认 0=不缩水，§3），"
                                 f"得到 {v}")
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
        if self.front_pocket_p1_dist <= 0:
            raise ValueError(f"P1 弧长距离必须为正数，得到 {self.front_pocket_p1_dist}")
        if self.front_pocket_p2_drop <= 0:
            raise ValueError(f"P2 弧长深度必须为正数，得到 {self.front_pocket_p2_drop}")
        if not 0.0 <= self.front_pocket_dart_width <= 6.0:
            raise ValueError(f"腰头吃省总宽建议在 0~6.0 cm 内（常规 1.5~2.5），"
                             f"得到 {self.front_pocket_dart_width}")
        if not 1.0 <= self.front_pocket_paring_n <= 3.0:
            raise ValueError(f"撇削衰减幂指数 n 建议在 1.0~3.0 内（常规 1.5~2.0），"
                             f"得到 {self.front_pocket_paring_n}")
        if abs(self.front_pocket_mouth_bulge) > 5.0:
            raise ValueError(f"袋口母线弧高绝对值不超过 5.0，得到 {self.front_pocket_mouth_bulge}")
        if not 0.0 < self.front_pocket_mouth_bulge_at < 1.0:
            raise ValueError(f"袋口弧顶位置须在 (0, 1) 内，"
                             f"得到 {self.front_pocket_mouth_bulge_at}")
        if self.front_pocket_mouth_mode not in ("bulge", "tangent", "polyline"):
            raise ValueError(f"袋口净线模式只支持 bulge / tangent / polyline，"
                             f"得到 {self.front_pocket_mouth_mode!r}")
        for name in ("front_pocket_mouth_h1", "front_pocket_mouth_h2"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} 切线柄长必须为正数，"
                                 f"得到 {getattr(self, name)}")
        # 折角列表归一化为元组，逐角校验，位置须严格递增
        corners = tuple((float(u), float(d))
                        for u, d in self.front_pocket_mouth_corners)
        for u, d in corners:
            if not 0.0 < u < 1.0:
                raise ValueError(f"折角位置须在 (0, 1) 内，得到 {corners}")
            if not 0.0 <= d <= 5.0:
                raise ValueError(f"折角内推深度建议在 0~5.0 cm 内，得到 {corners}")
        if any(corners[i + 1][0] <= corners[i][0]
               for i in range(len(corners) - 1)):
            raise ValueError(f"折角位置须按弦上比例严格递增，得到 {corners}")
        object.__setattr__(self, "front_pocket_mouth_corners", corners)
        # 前口袋袋贴（Facing：挖削嵌入式袋口贴布，前口袋绘制.md §三.3.(1)）----
        if not 0.0 < self.front_pocket_facing_width <= 10.0:
            raise ValueError(f"袋贴腰头宽建议在 0~10.0 cm 内（常规 3.0~4.0），"
                             f"得到 {self.front_pocket_facing_width}")
        if self.front_pocket_facing_side_w < 0.0 or self.front_pocket_facing_side_w > 15.0:
            raise ValueError(f"袋贴侧缝端深度须在 0~15.0 cm 内（0 表示与腰头同宽），"
                             f"得到 {self.front_pocket_facing_side_w}")
        if self.front_pocket_facing_mode not in ("tangent", "offset", "bulge"):
            raise ValueError(f"袋贴内边模式只支持 tangent / offset / bulge，"
                             f"得到 {self.front_pocket_facing_mode!r}")
        for name in ("front_pocket_facing_h1", "front_pocket_facing_h2"):
            val = getattr(self, name)
            if val <= 0.0 or val > 20.0:
                raise ValueError(f"{name} 切线柄长须在 0~20.0 cm 内，得到 {val}")
        if abs(self.front_pocket_facing_bulge) > 10.0:
            raise ValueError(f"袋贴内边弧高绝对值不超过 10.0，得到 {self.front_pocket_facing_bulge}")
        if not 0.0 < self.front_pocket_facing_bulge_at < 1.0:
            raise ValueError(f"袋贴内边弧顶位置须在 (0, 1) 内，得到 {self.front_pocket_facing_bulge_at}")
        # 前贴袋：定位/尺寸/形态校验（前贴袋绘制.md §四、§五）
        if self.front_patch_top_drop < 0 or self.front_patch_top_inset < 0:
            raise ValueError("贴袋定位下移量/内移量不能为负数")
        if self.front_patch_width <= 0 or self.front_patch_height <= 0:
            raise ValueError("贴袋袋口宽/袋身高必须为正数")
        if self.front_patch_shape not in ("rectangle", "baker_shield",
                                          "angular", "custom"):
            raise ValueError(f"贴袋净形只支持 rectangle / baker_shield / angular "
                             f"/ custom，得到 {self.front_patch_shape!r}")
        if self.front_patch_bottom_width < 0:
            raise ValueError(f"袋底宽不能为负数，得到 {self.front_patch_bottom_width}")
        eff_bw = self.front_patch_bottom_width or self.front_patch_width
        if not 0.0 <= self.front_patch_tip_depth < self.front_patch_height:
            raise ValueError(f"盾形底尖深度须在 [0, 袋身高) 内，"
                             f"得到 {self.front_patch_tip_depth}")
        if not 0.0 <= self.front_patch_chamfer * 2 <= eff_bw:
            raise ValueError(f"底角斜切量两倍不能超过袋底宽，"
                             f"得到 {self.front_patch_chamfer}")
        if abs(self.front_patch_rotate_deg) > 90.0:
            raise ValueError(f"贴袋旋转角建议在 ±90° 内，"
                             f"得到 {self.front_patch_rotate_deg}")
        # custom 模式：角点 ≥3，边形态个数 = 角点数，逐边校验
        cpts = tuple((float(x), float(y))
                     for x, y in self.front_patch_custom_points)
        cedges = tuple((float(b), float(at))
                       for b, at in self.front_patch_custom_edges)
        if self.front_patch_shape == "custom":
            if len(cpts) < 3:
                raise ValueError(f"custom 净形角点至少 3 个，得到 {len(cpts)} 个")
            if len(cedges) != len(cpts):
                raise ValueError(f"custom 边形态个数须等于角点数 {len(cpts)}，"
                                 f"得到 {len(cedges)} 个")
            for b, at in cedges:
                if abs(b) > 10.0:
                    raise ValueError(f"custom 边弧高绝对值不超过 10.0，得到 {cedges}")
                if b != 0.0 and not 0.0 < at < 1.0:
                    raise ValueError(f"custom 弧边弧顶位置须在 (0, 1) 内，得到 {cedges}")
        object.__setattr__(self, "front_patch_custom_points", cpts)
        object.__setattr__(self, "front_patch_custom_edges", cedges)
        # 后贴袋：定位/尺寸/形态校验（后贴袋绘制.md §一、§二）
        if self.back_patch_inset_x < 0 or self.back_patch_drop_y < 0:
            raise ValueError("后贴袋距后浪线/距约克底线距离不能为负数")
        if self.back_patch_width <= 0 or self.back_patch_height <= 0:
            raise ValueError("后贴袋袋口宽/袋身高必须为正数")
        if self.back_patch_shape not in ("rectangle", "baker_shield",
                                         "angular", "custom"):
            raise ValueError(f"后贴袋净形只支持 rectangle / baker_shield / angular "
                             f"/ custom，得到 {self.back_patch_shape!r}")
        if self.back_patch_bottom_width < 0:
            raise ValueError(f"后贴袋袋底宽不能为负数，得到 {self.back_patch_bottom_width}")
        eff_bw_b = self.back_patch_bottom_width or self.back_patch_width
        if not 0.0 <= self.back_patch_tip_depth < self.back_patch_height:
            raise ValueError(f"后贴袋盾形底尖深度须在 [0, 袋身高) 内，"
                             f"得到 {self.back_patch_tip_depth}")
        if not 0.0 <= self.back_patch_chamfer * 2 <= eff_bw_b:
            raise ValueError(f"后贴袋底角斜切量两倍不能超过袋底宽，"
                             f"得到 {self.back_patch_chamfer}")
        if abs(self.back_patch_rotate_deg) > 90.0:
            raise ValueError(f"后贴袋旋转角建议在 ±90° 内，"
                             f"得到 {self.back_patch_rotate_deg}")
        bpts = tuple((float(x), float(y))
                     for x, y in self.back_patch_custom_points)
        bedges = tuple((float(b), float(at))
                       for b, at in self.back_patch_custom_edges)
        if self.back_patch_shape == "custom":
            if len(bpts) < 3:
                raise ValueError(f"后贴袋 custom 净形角点至少 3 个，得到 {len(bpts)} 个")
            if len(bedges) != len(bpts):
                raise ValueError(f"后贴袋 custom 边形态个数须等于角点数 {len(bpts)}，"
                                 f"得到 {len(bedges)} 个")
            for b, at in bedges:
                if abs(b) > 10.0:
                    raise ValueError(f"后贴袋 custom 边弧高绝对值不超过 10.0，得到 {bedges}")
                if b != 0.0 and not 0.0 < at < 1.0:
                    raise ValueError(f"后贴袋 custom 弧边弧顶位置须在 (0, 1) 内，得到 {bedges}")
        object.__setattr__(self, "back_patch_custom_points", bpts)
        object.__setattr__(self, "back_patch_custom_edges", bedges)
        # 袋布：节点/边形态归一化与校验（袋布绘制.md §三、§六）
        if self.front_pouch_waist_safe < 0 or self.front_pouch_side_safe < 0:
            raise ValueError("袋布安全内延/垂深不能为负数")
        nodes = tuple((float(x), float(y)) for x, y in self.front_pouch_nodes)
        if len(nodes) < 2:
            raise ValueError(f"袋布自定义节点至少 2 个，得到 {len(nodes)} 个")
        edges = []
        for e in self.front_pouch_edges:
            spec = (e[0],) + tuple(float(x) for x in e[1:])
            if spec[0] == "line":
                if len(spec) != 1:
                    raise ValueError(f"line 边不带参数，得到 {e}")
            elif spec[0] == "arc":
                if len(spec) != 3:
                    raise ValueError(f"arc 边须为 (弧高, 弧顶分位)，得到 {e}")
                if abs(spec[1]) > 10.0:
                    raise ValueError(f"arc 弧高绝对值不超过 10.0，得到 {e}")
                if not 0.1 <= spec[2] <= 0.9:
                    raise ValueError(f"arc 弧顶分位须在 [0.1, 0.9] 内，得到 {e}")
            elif spec[0] == "bezier":
                if len(spec) != 5:
                    raise ValueError(f"bezier 边须为 (α°, κ1, β°, κ2)，得到 {e}")
                if abs(spec[1]) > 90.0 or abs(spec[3]) > 90.0:
                    raise ValueError(f"bezier 夹角建议在 ±90° 内，得到 {e}")
                if not 0.0 < spec[2] <= 1.0 or not 0.0 < spec[4] <= 1.0:
                    raise ValueError(f"bezier 手柄弦长比须在 (0, 1] 内，得到 {e}")
            else:
                raise ValueError(f"袋布边形态只支持 line / arc / bezier，得到 {e}")
            edges.append(spec)
        if len(edges) != len(nodes) + 1:
            raise ValueError(f"袋布边形态个数须为节点数 + 1（{len(nodes) + 1}），"
                             f"得到 {len(edges)} 个")
        object.__setattr__(self, "front_pouch_nodes", nodes)
        object.__setattr__(self, "front_pouch_edges", tuple(edges))
        # 小表袋：偏移/旋转/锚点/边形态校验（小表袋绘制.md §2、§4）
        if self.watch_pocket_mode not in ("custom", "facing_intersect"):
            raise ValueError(f"小表袋模式只支持 custom / facing_intersect，"
                             f"得到 {self.watch_pocket_mode!r}")
        if self.watch_pocket_width <= 0:
            raise ValueError(f"小表袋袋口宽必须为正数，得到 {self.watch_pocket_width}")
        if self.watch_pocket_offset_from_top < 0 or self.watch_pocket_offset_from_side < 0:
            raise ValueError("小表袋离口袋顶部/侧边距离不能为负数")
        if abs(self.watch_pocket_rotate_deg) > 90.0:
            raise ValueError(f"小表袋旋转角建议在 ±90° 内，得到 {self.watch_pocket_rotate_deg}")
        wpts = tuple((float(x), float(y)) for x, y in self.watch_pocket_points)
        if len(wpts) < 3:
            raise ValueError(f"小表袋锚点至少 3 个，得到 {len(wpts)} 个")
        wedges = []
        for e in self.watch_pocket_edges:
            spec = (e[0],) + tuple(float(x) for x in e[1:])
            if spec[0] == "line":
                if len(spec) != 1:
                    raise ValueError(f"line 边不带参数，得到 {e}")
            elif spec[0] == "arc":
                if len(spec) != 3:
                    raise ValueError(f"arc 边须为 (弧高, 弧顶分位)，得到 {e}")
                if abs(spec[1]) > 10.0:
                    raise ValueError(f"arc 弧高绝对值不超过 10.0，得到 {e}")
                if not 0.0 < spec[2] < 1.0:
                    raise ValueError(f"arc 弧顶分位须在 (0, 1) 内，得到 {e}")
            elif spec[0] == "bezier":
                if len(spec) != 5:
                    raise ValueError(f"bezier 边须为 (α°, κ1, β°, κ2)，得到 {e}")
                if abs(spec[1]) > 90.0 or abs(spec[3]) > 90.0:
                    raise ValueError(f"bezier 夹角建议在 ±90° 内，得到 {e}")
                if not 0.0 < spec[2] <= 1.0 or not 0.0 < spec[4] <= 1.0:
                    raise ValueError(f"bezier 手柄弦长比须在 (0, 1] 内，得到 {e}")
            else:
                raise ValueError(f"小表袋边形态只支持 line / arc / bezier，得到 {e}")
            wedges.append(spec)
        if len(wedges) != len(wpts):
            raise ValueError(f"小表袋边形态个数须等于锚点数 {len(wpts)}（闭合边），"
                             f"得到 {len(wedges)} 个")
        object.__setattr__(self, "watch_pocket_points", wpts)
        object.__setattr__(self, "watch_pocket_edges", tuple(wedges))
        # 门襟：宽度与开深系数校验（门襟绘制.md §2.2）
        if not 3.0 <= self.fly_width <= 4.5:
            raise ValueError(f"门襟宽 W 建议在 3.5~4.2 cm 内，得到 {self.fly_width}")
        if self.fly_length_ratio <= 0 or self.fly_length_base < 0:
            raise ValueError("门襟开深系数必须为正、基值不能为负")
        for name in ("fly_turnback", "fly_stitch_inset"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} 不能为负数，得到 {getattr(self, name)}")
        if self.fly_turnback >= self.fly_width:
            raise ValueError(f"退层补偿 Δw 须小于门襟宽 W，得到 {self.fly_turnback}")
        if not 0.0 < self.fly_corner_inset < self.fly_width:
            raise ValueError(f"门襟底角圆角内收须在 (0, 门襟宽 W) 内"
                             f"（R = W − 本值），得到 {self.fly_corner_inset}")
        if not 0.0 < self.fly_corner_turn <= 1.0:
            raise ValueError(f"门襟拐点弧位须在 (0, 1] 内（1.0 = J 底），"
                             f"得到 {self.fly_corner_turn}")
        if self.fly_blend_drop is not None and self.fly_blend_drop < 0:
            raise ValueError(f"融合弧下移量不能为负，得到 {self.fly_blend_drop}")
        # 独立门襟：缝份/延展校验（门襟绘制.md §5）
        if self.fly_sep_extra < 0:
            raise ValueError(f"fly_sep_extra 不能为负数，得到 {self.fly_sep_extra}")

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
        if "waistband_grain" in data:
            data["waistband_grain"] = WaistbandGrain(data["waistband_grain"])
        if "fit" in data:
            data["fit"] = Fit(data["fit"].lower())
        if "waistband_seam_allowances" in data:
            data["waistband_seam_allowances"] = WaistbandSeamAllowances.from_dict(
                data["waistband_seam_allowances"])
        if "back_yoke_seam_allowances" in data:
            data["back_yoke_seam_allowances"] = YokeSeamAllowances.from_dict(
                data["back_yoke_seam_allowances"])
        if "front_pocket_facing_seam_allowances" in data:
            data["front_pocket_facing_seam_allowances"] = \
                FrontFacingSeamAllowances.from_dict(
                    data["front_pocket_facing_seam_allowances"])
        if "front_patch_seam_allowances" in data:
            data["front_patch_seam_allowances"] = FrontPatchSeamAllowances.from_dict(
                data["front_patch_seam_allowances"])
        if "front_pouch_seam_allowances" in data:
            data["front_pouch_seam_allowances"] = PouchSeamAllowances.from_dict(
                data["front_pouch_seam_allowances"])
        return cls(**data)
