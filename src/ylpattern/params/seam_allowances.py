"""各裁片独立缝份 dataclass（字段名 = 裁片语义边名，cutter._sa_amount 鸭子类型按名取值）。

自 options.py 拆出（2026-08）：PatternOptions 字段区的 default_factory 与
from_file 的 TOML 子表 -> dataclass 转换仍引用本模块，options.py 顶部
re-export 维持 `from .options import XxxSeamAllowances` 兼容。
"""

from __future__ import annotations

from dataclasses import dataclass


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
class FlySeamAllowances:
    """独立门襟裁片缝份（cm，门襟裁片.md §1；先缩水后缝边，缝份不叠加缩水）。

    单排（单层）语义边：top 腰口（车入腰头，腰头线子弧）/ outer 外缘（外缘直线 +
    底角 J 型圆弧 + 底边的 G1 连续链，三段同名共用本值）/ inner 内边（与前浪
    缝合线重合）；bottom 仅双排（对折）消费（去底角弧后的底端直线闭合边）。
    双排镜像边加 _m 后缀异名（top_m/outer_m/bottom_m）：缝份值与基边同组共用
    本值；cutter 对折接缝（对折线两端 O/S）正常 miter，反射角交点自动裁剪。
    """

    top: float = 1.0
    outer: float = 1.0
    bottom: float = 1.0
    inner: float = 1.0

    @classmethod
    def from_dict(cls, d: dict) -> "FlySeamAllowances":
        return cls(top=float(d.get("top", 1.0)),
                   outer=float(d.get("outer", 1.0)),
                   bottom=float(d.get("bottom", 1.0)),
                   inner=float(d.get("inner", 1.0)))


@dataclass(frozen=True)
class WatchPocketSeamAllowances:
    """小表袋裁片缝份（cm，小表袋裁片.md §4.1）。

    小表袋为缝于袋布上的贴袋：top 袋口折边（向反面折转、双折边明线车缝，
    常规 2.0~2.5）/ side 两侧常规缝边。bottom 与袋贴拼接侧一致：仅模式 A
    （facing_intersect，底边=袋贴内边子段）与 custom 四边闭合按底边消费；
    custom N≠4 多边形无可靠底边识别，全走 side（bottom 不生效）。
    """

    top: float = 2.5
    side: float = 1.0
    bottom: float = 1.0     # 默认恰与袋贴 inner 一致（§4.1 拼接缝份口径）

    @classmethod
    def from_dict(cls, d: dict) -> "WatchPocketSeamAllowances":
        return cls(top=float(d.get("top", 2.5)),
                   side=float(d.get("side", 1.0)),
                   bottom=float(d.get("bottom", 1.0)))


@dataclass(frozen=True)
class BackPatchSeamAllowances:
    """后贴袋裁片缝份（cm，后贴袋裁片.md §2）。

    后贴袋为缝于后大片表面的折边口袋：top 袋口折边（双折，§2 示例 25mm=2.5）/
    side 两侧常规缝边 / bottom 底边常规缝边（§2 示例 10mm=1.0）。bottom 仅
    rectangle、baker_shield/angular 底边链与 custom 四边闭合按底边消费；
    custom N≠4 多边形无可靠底边识别，全走 side（bottom 不生效，同小表袋口径）。
    """

    top: float = 2.5
    side: float = 1.0
    bottom: float = 1.0

    @classmethod
    def from_dict(cls, d: dict) -> "BackPatchSeamAllowances":
        return cls(top=float(d.get("top", 2.5)),
                   side=float(d.get("side", 1.0)),
                   bottom=float(d.get("bottom", 1.0)))


@dataclass(frozen=True)
class FrontSeamAllowances:
    """前片裁片各边独立缝份（cm，前片裁片.md §2.1）。

    前片四周缝合工艺各不相同，按语义边独立设置（字段名 = 裁片边名，cutter
    按名取值）：waist 装腰缝 / rise 前浪缝（斜线+裆弯弧两段同名平滑续接）/
    inseam 下裆缝（大腿+小腿两段同名）/ side 侧缝（小腿+大腿+腰臀弧三段
    同名）/ hem 裤口卷边（折边量）/ mouth 袋口挖削边（接袋贴，有省/无省
    切削线，polyline 折角链同名多段）/ fly_* 连裁门襟三边（顶边车入腰头、
    外缘接拉链、底角弧+融合弧同名 "fly_bottom" G1 平滑续接）。
    """

    waist: float = 1.0
    rise: float = 1.0
    inseam: float = 1.0
    side: float = 1.5
    hem: float = 2.5
    mouth: float = 1.0
    fly_top: float = 1.0
    fly_outer: float = 1.0
    fly_bottom: float = 1.0

    @classmethod
    def from_dict(cls, d: dict) -> "FrontSeamAllowances":
        return cls(waist=float(d.get("waist", 1.0)),
                   rise=float(d.get("rise", 1.0)),
                   inseam=float(d.get("inseam", 1.0)),
                   side=float(d.get("side", 1.5)),
                   hem=float(d.get("hem", 2.5)),
                   mouth=float(d.get("mouth", 1.0)),
                   fly_top=float(d.get("fly_top", 1.0)),
                   fly_outer=float(d.get("fly_outer", 1.0)),
                   fly_bottom=float(d.get("fly_bottom", 1.0)))


@dataclass(frozen=True)
class BackSeamAllowances:
    """后片裁片各边独立缝份（cm，后片裁片.md §2）。

    后片四周缝合工艺各不相同，按语义边独立设置（字段名 = 裁片边名，cutter
    按名取值）：top 拼机头缝（机头开启时上边）/ waist 装腰缝（无机头时上边）/
    cb 后浪缝（后中斜线+大裆弯弧两段同名平滑续接）/ inseam 内侧缝（大腿+小腿
    两段同名）/ side 外侧缝（髋腰+大腿+小腿三段同名）/ hem 脚口折边（卷边量）。
    """

    top: float = 1.0
    waist: float = 1.0
    cb: float = 1.0
    inseam: float = 1.0
    side: float = 1.5
    hem: float = 2.5

    @classmethod
    def from_dict(cls, d: dict) -> "BackSeamAllowances":
        return cls(top=float(d.get("top", 1.0)),
                   waist=float(d.get("waist", 1.0)),
                   cb=float(d.get("cb", 1.0)),
                   inseam=float(d.get("inseam", 1.0)),
                   side=float(d.get("side", 1.5)),
                   hem=float(d.get("hem", 2.5)))
