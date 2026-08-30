"""工厂 DXF 反解析中间数据模型（.doc/工厂DXF逆向解析.md）。

reader.py 产出、geomops/identify/measure 消费的中间表示；本模块不
import ezdxf（唯一碰 ezdxf 的是 reader）。

单位约定：几何全程 **mm**（DXF 原生域），仅 measure.py 发射时换算成品
cm。Point 复用 geometry 的不可变点（类型单位无关，此处承载 mm 坐标；
注意其运算限制：``Point - Point -> Vector``、不支持 ``Point - Vector``）。

口径依据：块 = 款号#.件名.码（GBK 乱码名经 reader 还原）；一个块可含
N 个子片（空间聚类拆分，如机头块 = 后片 + 真机头）；层 1 = 毛样闭合
折线、层 14 = 净样闭合折线（**已含缩水放大**）、层 8 = 内部线（缝线/
折线/水平辅助线）、层 7 = 丝缕线、层 2 = 放码点（基码块带 ``# N``
TEXT 标注）、层 3 = 毛边密采样（诊断用）、层 4 = 刀口类点。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterator

from ..geometry import Point

_EPS = 1e-9  # mm 域几何容差（顶点重合/水平判定）


def _dist(a: Point, b: Point) -> float:
    return math.hypot(b.x - a.x, b.y - a.y)


@dataclass(frozen=True)
class Ring:
    """闭合折线（层 1 毛样 / 层 14 净样）。首尾不重复（构造时去重）；
    ``segments()`` 环绕收口。ET 导出把弧离散成密顶点、无 bulge，弧长
    即分段求和。"""

    pts: tuple[Point, ...]
    layer: str = ""

    def __post_init__(self) -> None:
        if len(self.pts) >= 2:
            a, b = self.pts[0], self.pts[-1]
            if abs(a.x - b.x) < _EPS and abs(a.y - b.y) < _EPS:
                object.__setattr__(self, "pts", self.pts[:-1])
        if len(self.pts) < 3:
            raise ValueError(f"闭合折线至少 3 个有效顶点，得到 {len(self.pts)}")

    # ---- 基础量 ----

    def bbox(self) -> tuple[float, float, float, float]:
        """(xmin, ymin, xmax, ymax)。"""
        xs = [p.x for p in self.pts]
        ys = [p.y for p in self.pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def segments(self) -> Iterator[tuple[Point, Point]]:
        """顶点 i -> i+1 环绕迭代（含收口段）。"""
        n = len(self.pts)
        for i in range(n):
            yield self.pts[i], self.pts[(i + 1) % n]

    def _cumulative(self) -> list[float]:
        """累计弧长表（长度 n+1，首 0 尾全长）。"""
        out = [0.0]
        for a, b in self.segments():
            out.append(out[-1] + _dist(a, b))
        return out

    def total_length(self) -> float:
        return self._cumulative()[-1]

    perimeter = total_length        # 别名（毛样/净样环周长口径）

    def length_at(self, idx: int) -> float:
        """沿环绕方向累计到顶点 idx 的弧长（idx 可为负，Python 序）。"""
        cum = self._cumulative()
        n = len(self.pts)
        idx %= n
        return cum[idx]

    def area(self) -> float:
        """有符号面积的绝对值（shoelace）。"""
        s = 0.0
        for a, b in self.segments():
            s += a.x * b.y - b.x * a.y
        return abs(s) / 2.0

    def centroid(self) -> Point:
        """面积加权质心（退化取顶点均值）。"""
        a = 0.0
        cx = cy = 0.0
        for p, q in self.segments():
            cross = p.x * q.y - q.x * p.y
            a += cross
            cx += (p.x + q.x) * cross
            cy += (p.y + q.y) * cross
        if abs(a) < _EPS:
            xs = [p.x for p in self.pts]
            ys = [p.y for p in self.pts]
            return Point(sum(xs) / len(xs), sum(ys) / len(ys))
        a /= 2.0
        return Point(cx / (6.0 * a), cy / (6.0 * a))

    # ---- 弧长参数化（跨码对应禁用索引匹配，用等弧长重采样） ----

    def resample(self, n: int) -> list[Point]:
        """等弧长重采样 n 点（含起点 pts[0]，环绕一圈均分）。"""
        if n < 1:
            raise ValueError(f"重采样点数须 ≥ 1，得到 {n}")
        cum = self._cumulative()
        total = cum[-1]
        if total < _EPS:
            return [self.pts[0]] * n
        out: list[Point] = []
        seg_i = 0
        for k in range(n):
            s = total * k / n
            while seg_i + 1 < len(cum) and cum[seg_i + 1] < s:
                seg_i += 1
            a, b = self.pts[seg_i], self.pts[(seg_i + 1) % len(self.pts)]
            seg_len = cum[seg_i + 1] - cum[seg_i]
            t = 0.0 if seg_len < _EPS else (s - cum[seg_i]) / seg_len
            out.append(a.lerp(b, t))
        return out

    def point_at(self, s: float) -> Point:
        """弧长 s 处的点（s 超界按环绕取模）。"""
        cum = self._cumulative()
        total = cum[-1]
        s = s % total if total > _EPS else 0.0
        seg_i = 0
        while seg_i + 1 < len(cum) and cum[seg_i + 1] < s:
            seg_i += 1
        a, b = self.pts[seg_i], self.pts[(seg_i + 1) % len(self.pts)]
        seg_len = cum[seg_i + 1] - cum[seg_i]
        t = 0.0 if seg_len < _EPS else (s - cum[seg_i]) / seg_len
        return a.lerp(b, t)


@dataclass(frozen=True)
class OpenLine:
    """开放折线（层 8 内部线 / 层 7 丝缕线 / LINE 实体）。"""

    pts: tuple[Point, ...]
    layer: str = ""

    def __post_init__(self) -> None:
        if len(self.pts) < 2:
            raise ValueError(f"开放折线至少 2 点，得到 {len(self.pts)}")

    def length(self) -> float:
        return sum(_dist(a, b) for a, b in zip(self.pts, self.pts[1:]))

    def bbox(self) -> tuple[float, float, float, float]:
        xs = [p.x for p in self.pts]
        ys = [p.y for p in self.pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def slope_deg(self) -> float:
        """首尾弦角（度，自 +X 逆时针；近水平导线 ≈ 0/180）。"""
        a, b = self.pts[0], self.pts[-1]
        return math.degrees(math.atan2(b.y - a.y, b.x - a.x))

    def midpoint(self) -> Point:
        return self.pts[0].midpoint(self.pts[-1])


@dataclass(frozen=True)
class LabeledPoint:
    """带标注的点：层 2 放码点 / 层 4 刀口点（label = "# N"，仅基码块有）。"""

    pt: Point
    label: str | None = None


@dataclass(frozen=True)
class PieceMeta:
    """块内 5 行元数据 TEXT（层 1）：Piece Name / Size / Annotation /
    Quantity / Category；Annotation 含缩水注记「横:15.0%，直:8.0%」。"""

    piece_name: str = ""
    size: str = ""
    annotation: str = ""
    quantity: int = 1
    category: int = 0


@dataclass
class SubPiece:
    """一个物理裁片。块可含多子片（reader 空间聚类拆分）；块内坐标即
    铺版绝对坐标（工厂 INSERT 恒等变换），跨片可直接做全局几何。"""

    block_key: str                  # GBK 还原后的块名 "5015#.机头.S"
    sub_index: int                  # 块内子片序（空间聚类序）
    name_hint: str                  # 块名件名段（匿名块 = ""）
    meta: PieceMeta = field(default_factory=PieceMeta)
    gross: Ring | None = None       # 层 1 毛样环
    net: Ring | None = None         # 层 14 净样环（已含缩水放大）
    internals: tuple[OpenLine, ...] = ()      # 层 8
    grain: OpenLine | None = None   # 层 7
    grade_points: tuple[LabeledPoint, ...] = ()   # 层 2
    notch_points: tuple[LabeledPoint, ...] = ()   # 层 4
    boundary_samples: tuple[Point, ...] = ()      # 层 3（诊断用）

    def net_or_gross(self) -> Ring:
        """净样优先，缺净样回退毛样（测量一律用净样层 14 口径）。"""
        if self.net is not None:
            return self.net
        if self.gross is not None:
            return self.gross
        raise ValueError(f"子片 {self.block_key}#{self.sub_index} 无净/毛样环")

    def net_bbox(self) -> tuple[float, float, float, float]:
        return self.net_or_gross().bbox()


@dataclass(frozen=True)
class DocHeader:
    """模型空间头标 6 行 TEXT（层 1，ASCII 标签）。"""

    style_name: str = ""
    creation_date: str = ""
    author: str = ""
    sample_size: str = ""           # 基码（SAMPLE SIZE）
    grade_rule_table: str = ""      # 含原始订单名（GBK 还原后）
    units: str = "METRIC"


# 码序排序：已知字母码按成衣惯例，纯数字码按数值，未知按名追加
_CANON_SIZES = ("XXS", "XS", "S", "M", "L", "XL", "XXL", "2XL", "3XL",
                "4XL", "5XL")


def size_sort_key(label: str) -> tuple[int, int, str]:
    """码标签排序键：已知字母码按惯例序、数字码按值、未知按名字典序
    追加在最后（仅排序用，不做任何数值档差猜测）。"""
    if label in _CANON_SIZES:
        return (0, _CANON_SIZES.index(label), label)
    if label.isdigit():
        return (1, int(label), label)
    return (2, 0, label)


@dataclass
class FactoryDoc:
    """一份工厂 DXF 的完整反解析中间表示。"""

    path: str
    header: DocHeader = field(default_factory=DocHeader)
    pieces: list[SubPiece] = field(default_factory=list)
    sizes: tuple[str, ...] = ()     # 块名码后缀去重（canonical 排序）
    warnings: list[str] = field(default_factory=list)

    def by_block(self, name_hint: str, size: str) -> list[SubPiece]:
        """按件名段 + 码取子片（匿名块 name_hint=""）。"""
        return [p for p in self.pieces
                if p.name_hint == name_hint and _size_of(p) == size]

    def by_size(self, size: str) -> list[SubPiece]:
        return [p for p in self.pieces if _size_of(p) == size]

    def piece_counts(self) -> dict[tuple[str, str], int]:
        """(件名段, 码) -> 子片数（探查/报告用）。"""
        out: dict[tuple[str, str], int] = {}
        for p in self.pieces:
            key = (p.name_hint, _size_of(p))
            out[key] = out.get(key, 0) + 1
        return out


def _size_of(p: SubPiece) -> str:
    """子片码标签：块名尾段，缺失回退元数据 Size 行。"""
    tail = p.block_key.rsplit(".", 1)[-1] if "." in p.block_key else ""
    if tail and (tail in _CANON_SIZES or tail.isdigit()):
        return tail
    return p.meta.size or tail
