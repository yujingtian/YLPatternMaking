"""排料编号模块（exporters/piece_codes.py）单元金标（对接文档
《母版DXF编号植入对接文档_2026-09.md》口径）。

- 赋码表：collect_pieces 全部片名登记且 g 码码内不冲突（facing/patch
  同槽 g04、fly_single/double 分占 g08/g11）；未登记名 raise；
- code_text：码号纯数字带 "-{size}"、否则只出 g 码；块名回读正则
  parse_block_code 与块名构造互逆；
- inch_size_label：腰围 cm -> 英寸档 round 半进位（防 banker 舍入）；
- label_anchor：凸片 = 质心；L 形凹片（质心落片外）取扫描线最宽内条带
  中点（在片内且 != 质心）；退化输入质心兜底；
- nest 契约：belt_loop 过滤、numMap 数量、labels 中文名。
"""

import pytest

from ylpattern.exporters import piece_codes
from ylpattern.pieces import PatternPiece, PieceEdge
from ylpattern.geometry import LineSegment, Point


# ---------- 赋码表 ----------

def test_gcode_table_complete_and_consistent():
    """数量表覆盖赋码表全部键（belt_loop 除外——不进 numMap），g 码在
    两表间不冲突；front_facing 与 front_patch 同槽 g04。"""
    assert set(piece_codes.PIECE_QUANTITIES) \
        <= set(piece_codes.PIECE_GCODES)
    assert piece_codes.PIECE_GCODES["front_facing"] \
        == piece_codes.PIECE_GCODES["front_patch"] == 4
    # 同码互斥对只允许 facing/patch（fly_single/double 可同场须分码）
    vals = list(piece_codes.PIECE_GCODES.values())
    assert len(vals) == len(set(vals)) + 1      # 恰一对同码（facing/patch）


def test_gcode_for_unknown_raises():
    with pytest.raises(ValueError, match="未登记排料 g 码"):
        piece_codes.gcode_for("mystery_piece")


# ---------- 文本与正则 ----------

def test_code_text():
    assert piece_codes.code_text(5, "30") == "g05-30"
    assert piece_codes.code_text(11, "28") == "g11-28"
    assert piece_codes.code_text(5, "-") == "g05"       # 单码常规导出


def test_parse_block_code_roundtrip():
    """块名构造 <-> 对接正则回读互逆（含小写 g/# 前缀与一/三位数字）。"""
    assert piece_codes.parse_block_code("WAISTBAND-G05-30") == ("30", 5)
    assert piece_codes.parse_block_code("WAISTBAND-G5-38") == ("38", 5)
    assert piece_codes.parse_block_code("前片g03.30") == ("30", 3)
    assert piece_codes.parse_block_code("袋#7.36") == ("36", 7)
    assert piece_codes.parse_block_code("WAISTBAND-30") == ("30", None)
    assert piece_codes.parse_block_code("WAISTBAND-G05--") == (None, None)


def test_is_numeric_and_assert_labels():
    assert piece_codes.is_numeric_size("30")
    assert piece_codes.is_numeric_size("028")
    assert not piece_codes.is_numeric_size("-")
    assert not piece_codes.is_numeric_size("M")
    assert not piece_codes.is_numeric_size("３０")        # 全角数字不放行
    with pytest.raises(ValueError, match="纯数字.*'M'.*'XL'"):
        piece_codes.assert_numeric_labels(["28", "M", "XL", "30"])
    piece_codes.assert_numeric_labels(["28", "30"])     # 全数字不抛


def test_inch_size_label():
    assert piece_codes.inch_size_label(74.0) == "29"     # 29.13 -> 29
    assert piece_codes.inch_size_label(68.0) == "27"     # 26.77 -> 27
    assert piece_codes.inch_size_label(71.12) == "28"    # 28.0 -> 28
    assert piece_codes.inch_size_label(67.31) == "27"    # 26.5 半进位（防 banker 舍 26）


# ---------- 锚点算法 ----------

SQUARE = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
# L 形（右上一角缺口）：质心 (46.7, 46.7) 落在缺口内（片外）
ELL = [(0.0, 0.0), (100.0, 0.0), (100.0, 40.0), (40.0, 40.0),
       (40.0, 100.0), (0.0, 100.0)]


def test_point_in_polygon():
    assert piece_codes.point_in_polygon((50.0, 50.0), SQUARE)
    assert not piece_codes.point_in_polygon((150.0, 50.0), SQUARE)
    assert piece_codes.point_in_polygon((20.0, 20.0), ELL)
    assert not piece_codes.point_in_polygon((70.0, 70.0), ELL)   # 缺口


def test_label_anchor_convex_uses_centroid():
    x, y = piece_codes.label_anchor(SQUARE)
    assert (x, y) == (50.0, 50.0)


def test_label_anchor_concave_strip_midpoint():
    """凹片质心 (46.7,46.7) 在缺口内（片外）-> 扫描线 y=bbox 中点(50)
    与两竖边交于 x=0/40，唯一内条带 [0,40] 中点 (20,50)。"""
    ax, ay = piece_codes.label_anchor(ELL)
    assert piece_codes.point_in_polygon((ax, ay), ELL)
    assert (ax, ay) == (20.0, 50.0)
    assert (ax, ay) != (46.7, 46.7)                       # != 质心


def test_label_anchor_degenerate_falls_back_centroid():
    """退化（点数 <3 射线法无多边形可言）：质心兜底、不抛错。"""
    pts = [(0.0, 0.0), (10.0, 10.0)]
    assert piece_codes.label_anchor(pts) == (5.0, 5.0)
    assert piece_codes.label_anchor([]) == (0.0, 0.0)


# ---------- nest 契约 ----------

def _piece(name: str, label: str) -> PatternPiece:
    edge = PieceEdge(name="e", geom=LineSegment(Point(0, 0), Point(10, 0)))
    return PatternPiece(name=name, label=label,
                        net_edges=(edge,), shrunk_edges=(),
                        gross_polygon=(Point(0, 0), Point(10, 0), Point(0, 10)))


def test_nest_pieces_filters_belt_loop():
    ps = [_piece("front_piece", "前片"), _piece("belt_loop", "裤耳"),
          _piece("watch_pocket", "小表袋")]
    got = piece_codes.nest_pieces(ps)
    assert [p.name for p in got] == ["front_piece", "watch_pocket"]


def test_nest_num_map_and_labels():
    ps = piece_codes.nest_pieces([
        _piece("front_piece", "前片"), _piece("back_piece", "后片"),
        _piece("front_fly_single", "门襟"), _piece("belt_loop", "裤耳"),
        _piece("watch_pocket", "小表袋")])
    assert piece_codes.nest_num_map(ps) == {"g01": 2, "g02": 2, "g08": 1,
                                            "g09": 1}
    assert piece_codes.nest_labels(ps) == {"g01": "前片", "g02": "后片",
                                           "g08": "门襟", "g09": "小表袋"}
    with pytest.raises(ValueError, match="未登记排料 g 码"):
        piece_codes.nest_num_map([_piece("mystery", "?")])
