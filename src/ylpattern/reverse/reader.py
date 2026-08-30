"""工厂 DXF（布衣科技 BUYI-TECH R12/mm）读取层：ezdxf -> FactoryDoc。

本模块是 reverse 包唯一 import ezdxf 的地方（惰性导入，仿
exporters/_dxf_base.require_ezdxf；未安装时 RuntimeError 带安装指引）。

读取口径（.doc/工厂DXF逆向解析.md §1）：
- 块名 ``款号#.件名.码`` 为 GBK 乱码：``fix_mojibake`` 先 latin-1 后
  cp1252 编回字节再 decode('gbk')（5015 有 latin-1 失败案例），失败原样
  返回（结构化解析不依赖中文名成功）；
- 一个块可含 N 个子片：以层 1 闭合折线为种子空间聚类，其余实体按
  bbox 包含/相交归属（机头块 = 后片 + 真机头、匿名块多子片）；
- 块内坐标即铺版绝对坐标（工厂 INSERT 恒等变换），非恒等时告警；
- 头标 6 行 TEXT（层 1）进 DocHeader，SAMPLE SIZE = 基码。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .model import (DocHeader, FactoryDoc, LabeledPoint, OpenLine, PieceMeta,
                    Point, Ring, SubPiece, size_sort_key)


def require_ezdxf():
    """lazy import ezdxf；未安装时抛 RuntimeError（含安装指引）。"""
    try:
        import ezdxf
    except ImportError as exc:
        raise RuntimeError(
            "DXF 反解析需要 ezdxf：请安装 pip install 'ylpattern[dxf]'"
            "（或 pip install 'ezdxf>=1.1'）") from exc
    return ezdxf


def fix_mojibake(s: str) -> str:
    """GBK 乱码还原：latin-1 -> cp1252 双回退编回字节再 decode('gbk')。

    仅对含非 ASCII 的串尝试；解码失败或解出不可打印垃圾时原样返回
    （结构化解析按 ``.`` 三段拆分，不依赖中文名成功）。
    """
    if s.isascii():
        return s
    for enc in ("latin-1", "cp1252"):
        try:
            fixed = s.encode(enc).decode("gbk")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if fixed.isprintable():
            return fixed
    return s


def parse_block_name(raw: str) -> tuple[str, str, str]:
    """块名 -> (款号段, 件名段, 码段)。``5028#..M`` -> ("5028#", "", "M")、
    ``5015#.机头.S`` -> ("5015#", "机头", "S")；段数不足时尽量保件名。"""
    parts = raw.split(".")
    if len(parts) >= 3:
        return parts[0], ".".join(parts[1:-1]), parts[-1]
    if len(parts) == 2:
        return parts[0], parts[1], ""
    return raw, "", ""


_FILENAME_SHRINK = re.compile(
    r"W(\d+(?:\.\d+)?)%\s*[-－]\s*L(\d+(?:\.\d+)?)%", re.IGNORECASE)


def parse_shrinkage_filename(path: str) -> tuple[float | None, float | None]:
    """文件名 ``…W15%-L8%…`` -> (weft=0.15, warp=0.08)。

    W = 横/围度向（X，weft）、L = 直/裤长向（Y，warp）；无标记返回
    (None, None)（回退 Annotation 注记）。
    """
    m = _FILENAME_SHRINK.search(os.path.basename(path))
    if not m:
        return (None, None)
    return (float(m.group(1)) / 100.0, float(m.group(2)) / 100.0)


_ANNOTATION_SHRINK = re.compile(
    r"横\s*[:：]\s*(\d+(?:\.\d+)?)\s*[%％]\s*[,，]\s*"
    r"直\s*[:：]\s*(\d+(?:\.\d+)?)\s*[%％]")


def parse_shrinkage_annotation(text: str) -> tuple[float | None, float | None]:
    """Annotation 注记 ``横:15.0%，直:8.0%`` -> (weft, warp)；无标记
    (None, None)。与文件名双源交叉校验用（measure.Calibration）。"""
    m = _ANNOTATION_SHRINK.search(text)
    if not m:
        return (None, None)
    return (float(m.group(1)) / 100.0, float(m.group(2)) / 100.0)


# ---- 块内实体归集的小工具（均为 mm 域纯几何） ----


def _bbox_of(pts) -> tuple[float, float, float, float]:
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _bbox_overlap(a: tuple[float, float, float, float],
                  b: tuple[float, float, float, float]) -> float:
    """两 bbox 交叠面积（不相交 = 0）。"""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


def _bbox_contains(box: tuple[float, float, float, float],
                   p: Point, margin: float = 5.0) -> bool:
    return (box[0] - margin <= p.x <= box[2] + margin
            and box[1] - margin <= p.y <= box[3] + margin)


def _nearest_seed(pt: Point, seeds: list[tuple[int, Ring]]) -> int:
    """质心最近种子（bbox 包含判定失效时的兜底）。"""
    best, best_d = 0, float("inf")
    for idx, ring in seeds:
        c = ring.centroid()
        d = pt.distance_to(c)
        if d < best_d:
            best, best_d = idx, d
    return best


@dataclass
class _RawMeta:
    """块内一组 5 行元数据 TEXT（Piece Name 行开组）。"""

    insert: Point
    fields: dict[str, str]

    def to_meta(self) -> PieceMeta:
        try:
            qty = int(self.fields.get("Quantity", "1").strip() or 1)
        except ValueError:
            qty = 1
        try:
            cat = int(self.fields.get("Category", "0").strip() or 0)
        except ValueError:
            cat = 0
        return PieceMeta(piece_name=self.fields.get("Piece Name", ""),
                         size=self.fields.get("Size", ""),
                         annotation=self.fields.get("Annotation", ""),
                         quantity=qty, category=cat)


_META_PREFIXES = ("Piece Name", "Size", "Annotation", "Quantity", "Category")


def read_dxf(path: str) -> FactoryDoc:
    """读工厂 DXF -> FactoryDoc（只读，绝不回写源文件）。"""
    ezdxf = require_ezdxf()
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()

    out = FactoryDoc(path=path)
    out.header = _read_header(msp)
    _check_inserts(msp, out)

    for block in doc.blocks:
        if block.name[:1] in ("*", "$", "_"):
            continue
        _read_block(block, out)

    # 码集合：块名尾段按件名段去重计数——真码列会跨多个件名重复出现
    # （或等于头标基码），孤立尾段（件名误含点等）不认为是码
    tail_hints: dict[str, set[str]] = {}
    for p in out.pieces:
        tail = p.block_key.rsplit(".", 1)[-1] if "." in p.block_key else ""
        if tail:
            tail_hints.setdefault(tail, set()).add(p.name_hint)
    sizes = {t for t, hints in tail_hints.items() if len(hints) >= 2}
    if out.header.sample_size:
        sizes.add(out.header.sample_size)
    out.sizes = tuple(sorted((s for s in sizes if s), key=size_sort_key))
    return out


def _read_header(msp) -> DocHeader:
    """模型空间 6 行头标 TEXT（层 1，``KEY: value``）。"""
    fields: dict[str, str] = {}
    for e in msp:
        if e.dxftype() != "TEXT" or e.dxf.layer != "1":
            continue
        text = fix_mojibake(e.dxf.text)
        if ":" not in text:
            continue
        key, _, value = text.partition(":")
        key = key.strip()
        if key in ("STYLE NAME", "CREATION DATE", "AUTHOR", "SAMPLE SIZE",
                   "GRADE RULE TABLE", "UNITS"):
            fields[key] = fix_mojibake(value.strip())
    return DocHeader(style_name=fields.get("STYLE NAME", ""),
                     creation_date=fields.get("CREATION DATE", ""),
                     author=fields.get("AUTHOR", ""),
                     sample_size=fields.get("SAMPLE SIZE", ""),
                     grade_rule_table=fields.get("GRADE RULE TABLE", ""),
                     units=fields.get("UNITS", "METRIC"))


def _check_inserts(msp, out: FactoryDoc) -> None:
    """INSERT 恒等变换校验：块内坐标即绝对坐标的前提。非恒等（缩放/
    旋转）只告警不中断（铺版重复插桩与解析无关）。"""
    for e in msp:
        if e.dxftype() != "INSERT":
            continue
        if abs(getattr(e.dxf, "xscale", 1.0) - 1.0) > 1e-9 \
                or abs(getattr(e.dxf, "yscale", 1.0) - 1.0) > 1e-9 \
                or abs(getattr(e.dxf, "rotation", 0.0)) > 1e-9:
            out.warnings.append(
                f"INSERT '{fix_mojibake(e.dxf.name)}' 非恒等变换"
                "（缩放/旋转），块内坐标可能非绝对坐标")
            break


def _read_block(block, out: FactoryDoc) -> None:
    """单块 -> 子片列表（空间聚类），并入 doc.pieces。"""
    name = fix_mojibake(block.name)
    _, name_hint, _ = parse_block_name(name)

    gross: list[Ring] = []
    nets: list[Ring] = []
    opens: list[OpenLine] = []
    points: dict[str, list[LabeledPoint]] = {"2": [], "3": [], "4": []}
    point_coords: dict[str, list[Point]] = {"2": [], "3": [], "4": []}
    labels: dict[str, list[tuple[Point, str]]] = {"2": [], "4": []}
    meta_texts: list[tuple[Point, str]] = []
    ignored = 0

    for e in block:
        t = e.dxftype()
        if t == "POLYLINE":
            pts = tuple(Point(v.dxf.location.x, v.dxf.location.y)
                        for v in e.vertices)
            if len(pts) < 2:
                continue
            if e.dxf.layer in ("1", "14") and e.is_closed:
                ring = Ring(pts, layer=e.dxf.layer)
                (gross if e.dxf.layer == "1" else nets).append(ring)
            else:
                opens.append(OpenLine(pts, layer=e.dxf.layer))
        elif t == "LINE":
            opens.append(OpenLine(
                (Point(e.dxf.start.x, e.dxf.start.y),
                 Point(e.dxf.end.x, e.dxf.end.y)), layer=e.dxf.layer))
        elif t == "POINT":
            layer = e.dxf.layer
            if layer in points:
                pt = Point(e.dxf.location.x, e.dxf.location.y)
                points[layer].append(LabeledPoint(pt))
                point_coords[layer].append(pt)
        elif t == "TEXT":
            text = fix_mojibake(e.dxf.text)
            pt = Point(e.dxf.insert.x, e.dxf.insert.y)
            if e.dxf.layer == "1" and text.split(":")[0].strip() in _META_PREFIXES:
                meta_texts.append((pt, text))
            elif e.dxf.layer in labels and text.lstrip().startswith("#"):
                labels[e.dxf.layer].append((pt, text.strip()))
        else:
            ignored += 1
    if ignored:
        out.warnings.append(f"块 '{name}' 忽略 {ignored} 个非白名单实体")

    # 种子：层 1 毛样环（缺毛样时净样环兜底）
    seeds: list[Ring] = gross if gross else nets
    if not seeds:
        if opens or any(points.values()):
            out.warnings.append(f"块 '{name}' 无闭合折线种子，跳过")
        return
    boxes = [r.bbox() for r in seeds]

    # 点标注就近配对（层 2/4 的 "# N" TEXT 与 POINT 同坐标落位）
    labeled: dict[str, list[LabeledPoint]] = {}
    for layer, entries in labels.items():
        tagged = list(points[layer])
        for tpt, text in entries:
            best_i, best_d = None, 5.0
            for i, lp in enumerate(tagged):
                d = tpt.distance_to(lp.pt)
                if d < best_d:
                    best_i, best_d = i, d
            if best_i is not None:
                tagged[best_i] = LabeledPoint(tagged[best_i].pt, text)
        labeled[layer] = tagged

    # 元数据分组：Piece Name 行开组，同组其余 4 行按邻近并入
    metas = _group_metas(meta_texts)

    subs: list[SubPiece] = []
    order = sorted(range(len(seeds)), key=lambda i: (boxes[i][1], boxes[i][0]))
    for sub_index, seed_i in enumerate(order):
        def pick(pt: Point) -> int:
            """bbox 包含 -> 该种子；否则质心最近。"""
            hits = [j for j, b in enumerate(boxes) if _bbox_contains(b, pt)]
            if len(hits) == 1:
                return hits[0]
            return _nearest_seed(pt, list(enumerate(seeds)))

        sub = SubPiece(block_key=name, sub_index=sub_index, name_hint=name_hint)
        sub.gross = seeds[seed_i] if gross else None
        sub.internals = tuple(
            ln for ln in opens
            if ln.layer == "8" and pick(ln.midpoint()) == seed_i)
        sub.grain = next((ln for ln in opens
                          if ln.layer == "7" and pick(ln.midpoint()) == seed_i),
                         None)
        sub.grade_points = tuple(
            lp for lp in labeled.get("2", []) if pick(lp.pt) == seed_i)
        sub.notch_points = tuple(
            lp for lp in labeled.get("4", []) if pick(lp.pt) == seed_i)
        sub.boundary_samples = tuple(
            p for p in point_coords.get("3", []) if pick(p) == seed_i)
        if nets:
            assigned = [j for j, r in enumerate(nets)
                        if _pick_net(r, boxes, seeds) == seed_i]
            if len(assigned) == 1:
                sub.net = nets[assigned[0]]
            elif seed_i < len(nets):
                sub.net = nets[seed_i]  # 数量对齐兜底（按种子序）
            else:
                sub.net = None
        meta_best = [m for m in metas if pick(m.insert) == seed_i]
        sub.meta = (meta_best[0].to_meta() if meta_best
                    else PieceMeta(piece_name=name))
        subs.append(sub)

    out.pieces.extend(subs)


def _pick_net(ring: Ring, boxes, seeds) -> int:
    """净样环归属：bbox 交叠面积最大者优先，全零回退质心最近。"""
    rb = ring.bbox()
    scores = [_bbox_overlap(rb, b) for b in boxes]
    if max(scores) > 0.0:
        return scores.index(max(scores))
    return _nearest_seed(ring.centroid(), list(enumerate(seeds)))


def _group_metas(meta_texts: list[tuple[Point, str]]) -> list[_RawMeta]:
    """5 行元数据 TEXT 分组：Piece Name 行开组，其后 60mm 内同行并入。"""
    groups: list[_RawMeta] = []
    for pt, text in sorted(meta_texts, key=lambda t: (t[0].y, t[0].x)):
        key = text.split(":")[0].strip()
        value = text.partition(":")[2].strip()
        if key == "Piece Name" or not groups:
            groups.append(_RawMeta(insert=pt, fields={key: value}))
            continue
        last = groups[-1]
        if abs(pt.y - last.insert.y) <= 60.0 and key not in last.fields:
            last.fields[key] = value
        else:
            groups.append(_RawMeta(insert=pt, fields={key: value}))
    return groups
