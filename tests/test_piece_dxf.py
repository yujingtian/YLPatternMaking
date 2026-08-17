"""裁片合集 DXF 输出测试（R12/mm 平铺一张；.doc/python工程设计.md §10.3）。

金标（M 同 test_waistband_piece；back_yoke+back_patch 开启使 back_piece
drills/marks 齐全）：
- CUT 层闭合 POLYLINE 每片恰 1 条，顶点数 == gross_polygon 去重后点数；
- Y 翻转：每片 CUT 折线 bbox 高 == 片 bbox 高×10（翻转平移不改尺寸）；
- 平铺不重叠：两片 CUT bbox 在 X 方向有分隔（行内左->右摆放）；
- NET/SHRUNK 互斥：默认全片有缩水态（0 缩水也填充）-> NET 空；
- NOTCH 层每刀口一条 5mm LINE；DRILL 层每孔一个 r=0.5mm CIRCLE；
- TEXT 全 ASCII 且含各 piece.name；写盘后 ezdxf.readfile 回读成功。
ezdxf 缺席时逐条 importorskip。
"""

import math

import pytest

from ylpattern.exporters.piece_dxf import _piece_bounds, render_pieces_dxf
from ylpattern.flows.back_flow import FULL_FLOW
from ylpattern.flows.back_piece_flow import build_back_piece
from ylpattern.flows.runner import FlowRunner
from ylpattern.flows.waistband_flow import build_waistband
from ylpattern.params import Measurements, PatternOptions

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)


@pytest.fixture()
def ctx():
    o = PatternOptions(delta=1.0, back_yoke=True, back_patch=True)
    return FlowRunner(M, o).run(FULL_FLOW)


@pytest.fixture()
def pieces(ctx):
    wb, _ = build_waistband(ctx)
    bp, _ = build_back_piece(ctx)
    return [wb, bp]


def _ents(doc, dxftype: str, layer: str | None = None) -> list:
    msp = doc.modelspace()
    return [e for e in msp if e.dxftype() == dxftype
            and (layer is None or e.dxf.layer == layer)]


def _dedup_closed(pts) -> list:
    """与 add_polyline 同口径：去连续重复点 + 闭合首尾重复点。"""
    out = []
    for p in pts:
        if out and p.distance_to(out[-1]) < 1e-7:
            continue
        out.append(p)
    if len(out) > 1 and out[0].distance_to(out[-1]) < 1e-7:
        out.pop()
    return out


def _doc(pieces):
    pytest.importorskip("ezdxf")
    return render_pieces_dxf(pieces)


# ---------- CUT 裁切轮廓 ----------

def test_cut_closed_per_piece(pieces):
    doc = _doc(pieces)
    cuts = _ents(doc, "POLYLINE", "CUT")
    assert len(cuts) == len(pieces)
    for cut, piece in zip(cuts, pieces):
        assert cut.is_closed
        assert len(list(cut.vertices)) == len(_dedup_closed(piece.gross_polygon))


def test_cut_y_flip_preserves_size(pieces):
    """Y 翻转金标：片 bbox 高×10 == CUT 折线 bbox 高（翻转不改尺寸）。"""
    doc = _doc(pieces)
    cuts = _ents(doc, "POLYLINE", "CUT")
    for cut, piece in zip(cuts, pieces):
        ys = [v.dxf.location.y for v in cut.vertices]
        _x0, _y0, _x1, y1 = _piece_bounds(piece)
        # _piece_bounds 的 y1 为片内最大 y；片高由 gross/net 全内容定，
        # CUT 仅毛样轮廓，故只断言 CUT 自身高度 == 毛样高度×10
        gy = [p.y for p in piece.gross_polygon]
        gross_h = max(gy) - min(gy)
        assert max(ys) - min(ys) == pytest.approx(gross_h * 10, abs=1e-6)


def test_layout_no_overlap(pieces):
    """平铺不重叠：两片 CUT bbox 在 X 方向有分隔（首片先摆、第二片在右）。"""
    doc = _doc(pieces)
    cuts = _ents(doc, "POLYLINE", "CUT")
    boxes = []
    for cut in cuts:
        xs = [v.dxf.location.x for v in cut.vertices]
        ys = [v.dxf.location.y for v in cut.vertices]
        boxes.append((min(xs), min(ys), max(xs), max(ys)))
    (ax0, _ay0, ax1, _ay1), (bx0, _by0, _bx1, _by1) = boxes
    assert bx0 >= ax1                      # 第二片在首片右侧，无交叠
    assert all(y >= -1e-6 for _b in boxes for y in (_b[1], _b[3]))


# ---------- 内轮廓三态 / 刀口 / 定位孔 ----------

def test_net_shrunk_exclusive(pieces):
    """默认全片有缩水态（0 缩水也填充 shrunk_edges）-> SHRUNK 齐、NET 空。"""
    doc = _doc(pieces)
    assert all(p.shrunk_edges for p in pieces)
    assert len(_ents(doc, "POLYLINE", "NET")) == 0
    expect = sum(len(p.shrunk_edges) for p in pieces)
    assert len(_ents(doc, "POLYLINE", "SHRUNK")) == expect


def test_notches_inward_lines(pieces):
    """NOTCH 层每刀口一条 LINE、长度 = 5mm。"""
    doc = _doc(pieces)
    lines = _ents(doc, "LINE", "NOTCH")
    expect = sum(len(p.gross_notches or p.shrunk_notches or p.notches)
                 for p in pieces)
    assert expect > 0
    assert len(lines) == expect
    for e in lines:
        d = math.hypot(e.dxf.end.x - e.dxf.start.x, e.dxf.end.y - e.dxf.start.y)
        assert d == pytest.approx(5.0, abs=1e-6)


def test_drills_circles(pieces):
    """DRILL 层每孔一个 r=0.5mm CIRCLE；back_piece 含后贴袋定位孔（非空）。"""
    doc = _doc(pieces)
    circles = _ents(doc, "CIRCLE", "DRILL")
    bp = pieces[1]
    assert bp.drills                                    # back_patch 开启 -> 有钻孔
    assert len(circles) == sum(len(p.drills) for p in pieces)
    for c in circles:
        assert c.dxf.radius == pytest.approx(0.5)


def test_grain_line_and_text(pieces):
    doc = _doc(pieces)
    assert pieces[0].grain is not None                  # 腰头丝缕线必在
    assert len(_ents(doc, "LINE", "GRAIN")) >= 1
    texts = {e.dxf.text for e in _ents(doc, "TEXT")}
    assert "GRAIN" in texts


# ---------- 标注与文件回读 ----------

def test_text_ascii_and_names(pieces):
    doc = _doc(pieces)
    texts = [e.dxf.text for e in _ents(doc, "TEXT")]
    assert all(t.isascii() for t in texts)
    names = set(texts)
    for p in pieces:
        assert p.name in names
    assert "UNITS=MM (DXF R12)" in names


def test_extents_backfilled(pieces):
    """$EXTMIN/$EXTMAX 已回填实体 bbox（ezdxf R12 默认 ±1e20 哨兵值，
    老 CAD 如 ET 2008 拿它做初始视图 -> 黑屏）。"""
    doc = _doc(pieces)
    extmin, extmax = doc.header["$EXTMIN"], doc.header["$EXTMAX"]
    assert abs(extmin[0]) < 1e19 and abs(extmax[0]) < 1e19
    xs = [v.dxf.location.x for c in _ents(doc, "POLYLINE", "CUT")
          for v in c.vertices]
    ys = [v.dxf.location.y for c in _ents(doc, "POLYLINE", "CUT")
          for v in c.vertices]
    assert extmin[0] <= min(xs) + 1e-6 and extmax[0] >= max(xs) - 1e-6
    assert extmin[1] <= min(ys) + 1e-6 and extmax[1] >= max(ys) - 1e-6


def test_write_roundtrip(pieces, tmp_path):
    ezdxf = pytest.importorskip("ezdxf")
    from ylpattern.exporters.piece_dxf import write_pieces_dxf
    path = tmp_path / "pieces.dxf"
    write_pieces_dxf(pieces, str(path))
    doc = ezdxf.readfile(str(path))
    assert doc.dxfversion == "AC1009"
    # 文件级断言：saveas 的 update_all 用 msp.dxf 覆写 header 范围变量，
    # 必须设到布局属性，否则写盘回读仍是 ±1e20 哨兵值（ET08 黑屏）
    assert abs(doc.header["$EXTMIN"][0]) < 1e19
    assert abs(doc.header["$EXTMAX"][0]) < 1e19
