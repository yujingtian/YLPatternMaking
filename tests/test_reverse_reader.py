"""reverse.reader 金标测试。

头注手工演算（mm 域）：
- 单片块：毛样矩形 (0,0)-(100,50) -> 周长 300、面积 5000；净样
  (5,5)-(95,45)；内部线 (10,25)-(90,25) 长 80；放码点 (50,25) 带标注
  "# 1"。
- 融合块（机头）：后片矩形 (0,0)-(300,200)、机头矩形 (0,300)-(280,340)，
  空间相隔 100mm -> 拆 2 子片，子片序自下而上；净样按 bbox 交叠各归
  各主；后片内部导线 (10,100)-(290,100) 归后片子片。
- 码集合：件名 {甲,乙} 共享码 S/M 各 2 件 -> sizes=('S','M')（canonical
  序）；件名丙孤立尾段 X 不入码集合。
"""

from __future__ import annotations

import pytest

ezdxf = pytest.importorskip("ezdxf")

from ylpattern.reverse import (fix_mojibake, parse_block_name,
                               parse_shrinkage_annotation,
                               parse_shrinkage_filename, read_dxf)

from _reverse_fixture import write_fixture

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


# ---- 纯函数 ----

def test_mojibake_fix():
    assert fix_mojibake("机头".encode("gbk").decode("latin-1")) == "机头"
    assert fix_mojibake("*Model_Space") == "*Model_Space"      # ASCII 直通
    assert fix_mojibake("Ã") == "Ã"      # 编不回 GBK 的串原样返回


def test_parse_block_name():
    assert parse_block_name("5028#..M") == ("5028#", "", "M")
    assert parse_block_name("5015#.机头.S") == ("5015#", "机头", "S")
    style, name, size = parse_block_name("无点块名")
    assert (style, size) == ("无点块名", "")
    assert name == ""


def test_parse_shrinkage_filename(tmp_path):
    p = tmp_path / "5015#五代款W15%-L8%.dxf"
    assert parse_shrinkage_filename(str(p)) == (0.15, 0.08)
    assert parse_shrinkage_filename(str(tmp_path / "w7%-l14%.dxf")) == (0.07, 0.14)
    assert parse_shrinkage_filename(str(tmp_path / "无标记.dxf")) == (None, None)


def test_parse_shrinkage_annotation():
    assert parse_shrinkage_annotation("Annotation: 横:15.0%，直:8.0%") == (0.15, 0.08)
    assert parse_shrinkage_annotation("横:7%，直:14%") == (0.07, 0.14)
    assert parse_shrinkage_annotation("无注记") == (None, None)


# ---- read_dxf 结构 ----

def test_read_single_piece(tmp_path):
    path = tmp_path / "one.dxf"
    write_fixture(path, [("前", "S", [{
        "gross": [(0, 0), (100, 0), (100, 50), (0, 50)],
        "net": [(5, 5), (95, 5), (95, 45), (5, 45)],
        "internal": [[(10, 25), (90, 25)]],
        "grain": ((50, 5), (50, 45)),
        "grade": [(50, 25, "# 1")],
        "notch": [(10, 25)],
        "samples": [(0, 0), (100, 0)],
        "meta": {"Size": "S", "Quantity": "2"},
    }])])
    doc = read_dxf(str(path))
    assert doc.header.sample_size == "S"
    assert doc.header.author == "BUYI-TECH"
    assert len(doc.pieces) == 1
    p = doc.pieces[0]
    assert p.name_hint == "前"
    assert p.gross.layer == "1" and p.net.layer == "14"
    assert p.gross.perimeter() == pytest.approx(300.0)
    assert p.gross.area() == pytest.approx(5000.0)
    assert p.net.bbox() == pytest.approx((5, 5, 95, 45))
    assert len(p.internals) == 1 and p.internals[0].length() == pytest.approx(80.0)
    assert p.grain is not None and p.grain.layer == "7"
    assert len(p.grade_points) == 1
    assert p.grade_points[0].label == "# 1"
    assert p.grade_points[0].pt.x == pytest.approx(50.0)
    assert len(p.notch_points) == 1
    assert len(p.boundary_samples) == 2
    assert p.meta.size == "S" and p.meta.quantity == 2
    assert doc.sizes == ("S",)


def test_fused_block_two_subs(tmp_path):
    path = tmp_path / "fused.dxf"
    write_fixture(path, [("机头", "S", [
        {   # 子片 0：后片（下）
            "gross": [(0, 0), (300, 0), (300, 200), (0, 200)],
            "net": [(5, 5), (295, 5), (295, 195), (5, 195)],
            "internal": [[(10, 100), (290, 100)]],
            "meta": {"Quantity": "2"},
        },
        {   # 子片 1：真机头（上，空间相隔 100mm）
            "gross": [(0, 300), (280, 300), (280, 340), (0, 340)],
            "net": [(5, 305), (275, 305), (275, 335), (5, 335)],
            "meta": {"Quantity": "2"},
        },
    ])])
    doc = read_dxf(str(path))
    assert len(doc.pieces) == 2
    back, yoke = doc.pieces        # sub_index 自下而上
    assert back.sub_index == 0 and yoke.sub_index == 1
    assert back.name_hint == "机头" == yoke.name_hint
    assert back.gross.bbox() == pytest.approx((0, 0, 300, 200))
    assert back.net.bbox() == pytest.approx((5, 5, 295, 195))
    assert yoke.gross.bbox() == pytest.approx((0, 300, 280, 340))
    assert yoke.net.bbox() == pytest.approx((5, 305, 275, 335))
    assert len(back.internals) == 1 and len(yoke.internals) == 0
    assert back.meta.quantity == 2 and yoke.meta.quantity == 2


def test_anonymous_block_name_hint(tmp_path):
    path = tmp_path / "anon.dxf"
    write_fixture(path, [("", "S", [{
        "gross": [(0, 0), (100, 0), (100, 100), (0, 100)],
        "net": [(5, 5), (95, 5), (95, 95), (5, 95)],
    }])])
    doc = read_dxf(str(path))
    assert len(doc.pieces) == 1
    assert doc.pieces[0].name_hint == ""
    assert doc.by_block("", "S") == doc.pieces


def test_sizes_detection_canonical_order(tmp_path):
    path = tmp_path / "sizes.dxf"
    rect = {"gross": [(0, 0), (50, 0), (50, 30), (0, 30)],
            "net": [(2, 2), (48, 2), (48, 28), (2, 28)]}
    blocks = [("甲", "S", [rect]), ("乙", "S", [rect]),
              ("甲", "M", [rect]), ("乙", "M", [rect]),
              ("丙", "X", [rect])]     # 孤立尾段，不入码集合
    write_fixture(path, blocks, sample_size="M")
    doc = read_dxf(str(path))
    assert doc.sizes == ("S", "M")
    assert doc.by_size("M") and len(doc.by_size("M")) == 2
