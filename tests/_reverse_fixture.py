"""合成工厂方言 DXF（reverse 层测试专用；非测试文件，pytest 不收集）。

仿布衣科技 R12/mm 口径（.doc/工厂DXF逆向解析.md §1）：
- 块名 ``款号#.件名.码`` 用 GBK 乱码（``.encode('gbk').decode('latin-1')``，
  与真件一致的回读路径）；
- 层 1 = 毛样闭合折线、14 = 净样闭合折线、8 = 内部开放折线、7 = 丝缕
  LINE、2 = 放码点（带 ``# N`` TEXT 同坐标标注）、4 = 刀口点、3 = 毛边
  采样点；
- 每子片 5 行元数据 TEXT（层 1，自锚点向下 15mm 行距）；
- 模型空间头标 6 行 TEXT（层 1）。

几何全部用测试内手工演算的简单矩形/折线（mm）。
"""

from __future__ import annotations

import ezdxf

_LAYERS = ("1", "2", "3", "4", "7", "8", "14")

META_LINES = ("Piece Name", "Size", "Annotation", "Quantity", "Category")


def moj(s: str) -> str:
    """中文 -> GBK 乱码串（真件块名的回读形态）。"""
    return s.encode("gbk").decode("latin-1")


def _tx(blk, text, x, y, layer="1", height=10.0):
    t = blk.add_text(text, dxfattribs={"layer": layer, "height": height})
    t.set_placement((float(x), float(y)))


def _poly(blk, pts, layer, closed):
    blk.add_polyline2d([(float(x), float(y)) for x, y in pts],
                       close=closed, dxfattribs={"layer": layer})


def write_fixture(path, blocks, *, sample_size="S", style="TST#",
                  annotation="横:15.0%，直:8.0%"):
    """写一份合成工厂 DXF。

    blocks: list of (件名, 码, subs)；sub 为 dict：
      gross / net      闭合折线点列 [(x, y), ...]
      internal         开放折线点列的列表 [[(x, y), ...], ...]（层 8）
      grain            两点 (x, y), (x, y)（层 7 LINE）
      grade            [(x, y, "# N"), ...]（层 2 点 + 同位 TEXT）
      notch            [(x, y), ...]（层 4 点，无标注）
      samples          [(x, y), ...]（层 3 点）
      meta             元数据覆盖 dict（Piece Name/Size/Annotation/
                       Quantity/Category 的子集；缺省自动补全 5 行）
      meta_at          元数据锚点 (x, y)（缺省 = gross 左下角）
    """
    doc = ezdxf.new("R12")
    for name in _LAYERS:
        doc.layers.add(name, color=7)
    msp = doc.modelspace()
    for i, (key, value) in enumerate((
            ("STYLE NAME", style), ("CREATION DATE", "2026/8/29/0/0"),
            ("AUTHOR", "BUYI-TECH"), ("SAMPLE SIZE", sample_size),
            ("GRADE RULE TABLE", f"{style}TEST"), ("UNITS", "METRIC"))):
        _tx(msp, f"{key}: {value}", 0, -30.0 - 15.0 * i)

    for piece_name, size, subs in blocks:
        raw_name = f"{style}.{piece_name}.{size}"
        blk = doc.blocks.new(moj(raw_name))
        for sub in subs:
            _write_sub(blk, raw_name, sub, annotation)
    doc.saveas(str(path))


def _write_sub(blk, raw_name: str, sub: dict, annotation: str) -> None:
    if "gross" in sub:
        _poly(blk, sub["gross"], "1", True)
    if "net" in sub:
        _poly(blk, sub["net"], "14", True)
    for line in sub.get("internal", ()):
        _poly(blk, line, "8", False)
    if "grain" in sub:
        a, b = sub["grain"]
        blk.add_line((float(a[0]), float(a[1])), (float(b[0]), float(b[1])),
                     dxfattribs={"layer": "7"})
    for x, y, label in sub.get("grade", ()):
        blk.add_point((float(x), float(y)), dxfattribs={"layer": "2"})
        _tx(blk, label, x, y, layer="2", height=5.0)
    for x, y in sub.get("notch", ()):
        blk.add_point((float(x), float(y)), dxfattribs={"layer": "4"})
    for x, y in sub.get("samples", ()):
        blk.add_point((float(x), float(y)), dxfattribs={"layer": "3"})
    meta = {"Piece Name": raw_name, "Size": "", "Annotation": annotation,
            "Quantity": "1", "Category": "0"}
    meta.update(sub.get("meta", {}))
    anchor = sub.get("meta_at")
    if anchor is None and "gross" in sub:
        xs = [p[0] for p in sub["gross"]]
        ys = [p[1] for p in sub["gross"]]
        anchor = (min(xs), min(ys) + 20.0)
    if anchor is not None:
        # 元数据值统一 GBK 乱码化（ezdxf R12 会把非 ASCII TEXT 转成
        # \U+XXXX 转义、真件方言是 GBK 乱码字节；reader.fix_mojibake 回读）
        for i, key in enumerate(META_LINES):
            value = moj(meta[key]) if not meta[key].isascii() else meta[key]
            _tx(blk, f"{key}: {value}", anchor[0], anchor[1] - 15.0 * i)
