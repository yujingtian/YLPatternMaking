"""裁片合集 DXF 输出测试（AAMA/ASTMA 口径：R12/mm、数字图层、块结构；
.doc/python工程设计.md §10.3）。

金标（M 同 test_waistband_piece；back_yoke+back_patch 开启使 back_piece
drills/marks 齐全）：
- 每片一个 BLOCK + msp 恰一个同名 INSERT（插入点 = 平铺偏移）；
- 图层为 AAMA 数字层：层 "1" CUT 闭合 POLYLINE 每片恰 1 条、顶点数 ==
  gross_polygon 去重后点数；"8" NET/SHRUNK/MARK；NOTCH 层 "4" 每刀口一个
  POINT 且附组码 30（Z=1.524）与组码 50（开口角度）；DRILL 层 "13" 每孔
  一个 POINT（CAD 自动渲染钻孔符号）；
- Y 翻转：每片 CUT 折线 bbox 高 == 毛样高×10（翻转不改尺寸）；
- 平铺不重叠：两片 INSERT+CUT bbox 在 X 方向有分隔（行内左->右摆放）；
- AAMA 信息文本：块中央三行 PIECE/SIZE/QTY；片名 TEXT 全 ASCII；
- 写盘后 ezdxf.readfile 回读成功、$EXTMIN 非 ±1e20 哨兵值、文件头有
  999 AAMA 注释组。
ezdxf 缺席时逐条 importorskip。
"""


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


def _doc(pieces):
    pytest.importorskip("ezdxf")
    return render_pieces_dxf(pieces)


def _ents(doc, dxftype: str, layer: str | None = None) -> list:
    """收集全部块内 + msp 实体（裁片图元在 BLOCK 里，msp 只有 INSERT
    与全局声明 TEXT）。"""
    out = []
    spaces = [b for b in doc.blocks if not b.name.startswith("*")]
    spaces.append(doc.modelspace())
    for space in spaces:
        for e in space:
            if e.dxftype() == dxftype \
                    and (layer is None or e.dxf.layer == layer):
                out.append(e)
    return out


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


# ---------- 块结构（AAMA 核心要求） ----------

def test_block_per_piece_with_insert(pieces):
    doc = _doc(pieces)
    inserts = [e for e in doc.modelspace() if e.dxftype() == "INSERT"]
    assert len(inserts) == len(pieces)
    # 块名与片名对应（ASCII 大写化），每块被引用恰一次
    names = [e.dxf.name for e in inserts]
    assert len(set(names)) == len(names)
    for piece in pieces:
        assert sum(1 for n in names
                   if n == piece.name.upper()) == 1


def test_blockref_at_layout_offset(pieces):
    """首片插入点贴原点（套料惯例），msp 内除 INSERT/TEXT 外无散线。"""
    doc = _doc(pieces)
    msp = doc.modelspace()
    inserts = [e for e in msp if e.dxftype() == "INSERT"]
    assert inserts[0].dxf.insert.x == pytest.approx(0.0)
    assert inserts[0].dxf.insert.y == pytest.approx(0.0)
    assert {e.dxftype() for e in msp} <= {"INSERT", "TEXT"}


# ---------- CUT 裁切轮廓（AAMA 数字层 1） ----------

def test_cut_closed_per_piece(pieces):
    doc = _doc(pieces)
    cuts = _ents(doc, "POLYLINE", "1")
    assert len(cuts) == len(pieces)
    for cut, piece in zip(cuts, pieces):
        assert cut.is_closed
        assert len(list(cut.vertices)) == len(_dedup_closed(piece.gross_polygon))


def test_cut_y_flip_preserves_size(pieces):
    """Y 翻转金标：毛样高×10 == CUT 折线 bbox 高（翻转不改尺寸）。"""
    doc = _doc(pieces)
    cuts = _ents(doc, "POLYLINE", "1")
    for cut, piece in zip(cuts, pieces):
        ys = [v.dxf.location.y for v in cut.vertices]
        gy = [p.y for p in piece.gross_polygon]
        gross_h = max(gy) - min(gy)
        assert max(ys) - min(ys) == pytest.approx(gross_h * 10, abs=1e-6)


def test_layout_no_overlap(pieces):
    """平铺不重叠：每片 bbox = 块内 CUT bbox + INSERT 插入点，两片在 X
    方向有分隔（首片先摆、第二片在右）。"""
    doc = _doc(pieces)
    inserts = [e for e in doc.modelspace() if e.dxftype() == "INSERT"]
    boxes = []
    for e in inserts:
        cuts = [p for p in doc.blocks.get(e.dxf.name)
                if p.dxftype() == "POLYLINE" and p.dxf.layer == "1"]
        assert len(cuts) == 1
        xs = [v.dxf.location.x + e.dxf.insert.x for v in cuts[0].vertices]
        ys = [v.dxf.location.y + e.dxf.insert.y for v in cuts[0].vertices]
        boxes.append((min(xs), min(ys), max(xs), max(ys)))
    (ax0, _ay0, ax1, _ay1), (bx0, _by0, _bx1, _by1) = boxes
    assert bx0 >= ax1                      # 第二片在首片右侧，无交叠
    assert all(y >= -1e-6 for _b in boxes for y in (_b[1], _b[3]))


# ---------- 内轮廓三态 / 刀口 / 定位孔（数字层） ----------

def test_net_shrunk_exclusive(pieces):
    """默认全片有缩水态（0 缩水也填充 shrunk_edges）-> SHRUNK 与 NET 同落
    层 8，条数 = 各片 shrunk_edges 之和；内部画线 MARK 亦落层 8（ET 08
    实测层 8 显示最稳），另计各片 marks 之和。"""
    doc = _doc(pieces)
    assert all(p.shrunk_edges for p in pieces)
    expect = sum(len(p.shrunk_edges) for p in pieces)
    expect_marks = sum(len(p.marks) for p in pieces)
    assert len(_ents(doc, "POLYLINE", "8")) == expect + expect_marks


def test_notches_points(pieces):
    """刀口 = 层 4 POINT（层 3 存普通轮廓顶点/放码点，层 4 才是刀口专属
    层），且必须附组码 30（Z=1.524，缺省 CAD 不识别）与组码 50（开口
    角度，取刀口内法向在 mm 输出系方向）；层内不杂 LINE/TEXT；三态回退
    链同 piece_svg。"""
    doc = _doc(pieces)
    points = _ents(doc, "POINT", "4")
    expect = sum(len(p.gross_notches or p.shrunk_notches or p.notches)
                 for p in pieces)
    assert expect > 0
    assert len(points) == expect
    for e in points:
        assert e.dxf.location.z == pytest.approx(1.524)  # 组码 30
        assert -360.0 <= e.dxf.angle <= 360.0            # 组码 50 必在
    # 层 4 不杂其他实体（LINE 刻线/伴随 TEXT 均禁止）
    assert len(_ents(doc, "LINE", "4")) == 0
    assert len(_ents(doc, "TEXT", "4")) == 0


def test_drills_points(pieces):
    """定位孔 = 层 13 单纯 POINT（CAD 读 AAMA 见层 13 POINT 自动渲染标准、
    不受缩放影响的钻孔符号；真实 CIRCLE r=0.5mm 过小不可见）；
    back_piece 含后贴袋定位孔。"""
    doc = _doc(pieces)
    points = _ents(doc, "POINT", "13")
    bp = pieces[1]
    assert bp.drills                                    # back_patch 开启 -> 有钻孔
    assert len(points) == sum(len(p.drills) for p in pieces)
    assert len(_ents(doc, "CIRCLE", "13")) == 0


def test_grain_line_and_text(pieces):
    doc = _doc(pieces)
    assert pieces[0].grain is not None                  # 腰头丝缕线必在
    assert len(_ents(doc, "LINE", "7")) >= 1
    texts = {e.dxf.text for e in _ents(doc, "TEXT")}
    assert "GRAIN" in texts


# ---------- AAMA 信息文本与文件回读 ----------

def test_aama_info_texts(pieces):
    doc = _doc(pieces)
    texts = [e.dxf.text for e in _ents(doc, "TEXT")]
    for piece in pieces:
        assert f"PIECE: {piece.name}" in texts
    assert "SIZE: -" in texts and "QTY: 1" in texts


def test_text_ascii_and_names(pieces):
    doc = _doc(pieces)
    texts = [e.dxf.text for e in _ents(doc, "TEXT")]
    assert all(t.isascii() for t in texts)
    names = set(texts)
    for p in pieces:
        assert p.name in names
    assert "ANSI/AAMA" in names


def test_extents_backfilled(pieces):
    """$EXTMIN/$EXTMAX 已按 INSERT 展开回填实体 bbox（非 ±1e20 哨兵值，
    防 ET08 黑屏）。"""
    doc = _doc(pieces)
    extmin, extmax = doc.header["$EXTMIN"], doc.header["$EXTMAX"]
    assert abs(extmin[0]) < 1e19 and abs(extmax[0]) < 1e19
    # 与布局对照：首片贴原点、X 范围覆盖全部插入点
    inserts = [e for e in doc.modelspace() if e.dxftype() == "INSERT"]
    assert extmin[0] <= min(e.dxf.insert.x for e in inserts) + 1e-6
    assert extmax[0] >= max(e.dxf.insert.x for e in inserts) - 1e-6


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
    # 999 AAMA 注释组在文件最前
    with open(path, encoding="ascii") as f:
        first = f.readline().strip()
        body = f.read().replace("\r\n", "\n")
    assert first == "999"
    # R12 兼容清洗：无 handle（group 5）、无 $HANDLING/$HANDSEED、无 1001
    # XDATA--ezdxf 恒写这三样，ET 08 等老软件解析易打不开（对照大货 DXF
    # 一个 group 5 都没有）
    assert "\n  5\n" not in body
    assert "$HANDLING" not in body and "$HANDSEED" not in body
    assert "\n1001\n" not in body
