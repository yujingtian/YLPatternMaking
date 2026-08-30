"""风格档案：把块名/匿名子片映射到测量角色（特化两款，非通用框架）。

档案是纯数据 + 可选谓词打分（``SubSpec.check(sub) -> 0..1``）；识别
算法（面积降序对位、计数失配告警）在 identify.py，两款共用。注册表
``register/get_profile`` 供 detect_profile 按款号查档案。

口径（.doc/工厂DXF逆向解析.md §3）：
- 块内多子片按**净面积降序**对位到 SubSpec 序（机头块 = 后片 + 真机头
  是唯一的多子片命名块，后片面积远大）；
- 匿名块（件名空）子片同样按面积降序对位（5015：后贴袋 > 表袋）；
- 5028 匿名 ×5 语义未知，仅细条（bbox 长短比 ≥3）标 unknown_strip
  告警，不入测量。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .model import SubPiece

# 角色标识（测量只依赖前六个：front_body/back_body/yoke/waistband/
# fused_pocket + 匿名两件；其余识别出但不入测量）
ROLE_IDS = (
    "front_body",     # 前片大片（块「前」）
    "back_body",      # 后片大片（机头块面积大子片——陷阱：藏在机头块里）
    "yoke",           # 真机头（机头块面积小子片）
    "waistband",      # 腰头独立裁片（块「腰」，可 1 环含左右两根）
    "fused_pocket",   # 前代块 = 袋贴+袋身融合方片（袋口弧是片内层 8 线）
    "back_patch",     # 后贴袋（匿名块面积大子片）
    "watch_pocket",   # 小表袋（匿名块面积小子片 / 5028 命名块「火机袋」）
    "front_fly_single",   # 单排门襟（识别不入测量）
    "front_fly_double",   # 双排门襟（识别不入测量）
    "belt_loop",      # 裤耳（识别不入测量）
    "unknown_strip",  # 匿名细条（警告，不入测量不入选项）
)


@dataclass(frozen=True)
class SubSpec:
    """一个子片角色占位：按净面积降序排列在块映射里。"""

    role: str
    note: str = ""
    check: Callable[[SubPiece], float] | None = None   # 0..1 打分


def _near_square_with_arc(sub: SubPiece) -> float:
    """前代融合方片确认：净 bbox 近方 + 片内 100~200mm 层 8 袋口弧。

    5015 实测 129x127mm、袋口弧 162.6mm；5028 前代同构。
    """
    x0, y0, x1, y1 = sub.net_bbox()
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return 0.0
    aspect = w / h
    has_arc = any(100.0 <= ln.length() <= 200.0 for ln in sub.internals)
    return 1.0 if (0.7 <= aspect <= 1.4 and has_arc) else 0.4


def _back_body_check(sub: SubPiece) -> float:
    """后片大片：净 bbox 高 ≥600mm（5015/5028 均 ~960mm）。"""
    x0, y0, x1, y1 = sub.net_bbox()
    return 1.0 if (y1 - y0) >= 600.0 else 0.3


def _yoke_check(sub: SubPiece) -> float:
    """真机头：净 bbox 高 ≤150mm（5015 ~65、5028 ~67）。"""
    x0, y0, x1, y1 = sub.net_bbox()
    return 1.0 if (y1 - y0) <= 150.0 else 0.3


def _waistband_check(sub: SubPiece) -> float:
    """腰头条带：长短边比 ≥4 且带宽 ≤120mm（5015 净 744x43）。"""
    x0, y0, x1, y1 = sub.net_bbox()
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return 0.0
    long_short = max(w, h) / min(w, h)
    return 1.0 if (long_short >= 4.0 and min(w, h) <= 120.0) else 0.4


@dataclass(frozen=True)
class StyleProfile:
    """一款工厂 DXF 的识别档案。"""

    key: str                          # 款号数字（"5015"）
    description: str
    block_map: dict[str, tuple[SubSpec, ...]]      # 件名 -> 子片角色序
    anonymous: tuple[SubSpec, ...] = ()            # 匿名块子片角色序
    strip_aspect: float | None = None    # 未识别子片长短边比超此值 -> unknown_strip
    notes: tuple[str, ...] = field(default=())


_REGISTRY: dict[str, StyleProfile] = {}


def register(profile: StyleProfile) -> None:
    """登记档案（模块级调用；同 key 后写覆盖）。"""
    _REGISTRY[profile.key] = profile


def get_profile(key: str) -> StyleProfile | None:
    return _REGISTRY.get(key)


def known_profiles() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def by_name_blocks() -> tuple[SubSpec, ...]:
    """两款共用的命名小块角色序（识别不入测量）。"""
    return (SubSpec("front_fly_double", "双排门襟"),
            SubSpec("front_fly_single", "单排门襟"),
            SubSpec("belt_loop", "裤耳连裁"))
