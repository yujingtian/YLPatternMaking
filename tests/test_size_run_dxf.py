"""多码推码 DXF（render_size_run_dxf / write_size_run_dxf）测试（推码方案步 3）。

金标（结构测试，同批裁片复用于三码——块结构/摆放与几何内容无关）：
- 块数 = Σ各码片数、块名 {片名}-G{NN}-{码} 全命中（跨码不冲突、g 码
  跨码同号——排料方式 A 同片型模板各码共用一个 g 码）；
- Sample Size = 基码（ET08 底部尺码栏数据源）；
- Category 码内 0 起重置（同片名跨码 Category 相同，ET08 参考件口径）；
- 带间不重叠：码 A 带 maxY + 8cm <= 码 B 带 minY（带沿 Y 叠放、间距
  BAND_GAP_CM）、首带贴原点（对照 _layout + _piece_bounds 精确重建
  各 INSERT 插入点）；
- 多码时每带一条码标 TEXT "SIZE {码}"（层 1，人读辅助）；
- 写盘回读成功、$EXTMIN/$EXTMAX 非 ±1e20 哨兵值、文件头 999 注释组、
  R12 清洗后无 group 5。
ezdxf 缺席时逐条 importorskip。
"""

import pytest

from ylpattern.exporters import piece_codes
from ylpattern.exporters.piece_dxf import (BAND_GAP_CM, PIECE_GAP_CM,
                                           _layout, _piece_bounds,
                                           render_size_run_dxf,
                                           write_size_run_dxf)
from ylpattern.flows.back_flow import FULL_FLOW
from ylpattern.flows.back_piece_flow import build_back_piece
from ylpattern.flows.runner import FlowRunner
from ylpattern.flows.waistband_flow import build_waistband
from ylpattern.params import Measurements, PatternOptions

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)

SIZES = ("28", "30", "32")
BASE = "30"


@pytest.fixture(scope="module")
def pieces():
    o = PatternOptions(delta=1.0, back_yoke=True, back_patch=True)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    wb, _ = build_waistband(ctx)
    bp, _ = build_back_piece(ctx)
    return [wb, bp]


@pytest.fixture(scope="module")
def doc(pieces):
    pytest.importorskip("ezdxf")
    return render_size_run_dxf([(s, pieces) for s in SIZES],
                               sample_size=BASE)


def _texts(space) -> list[str]:
    return [e.dxf.text for e in space if e.dxftype() == "TEXT"]


def _inserts(msp) -> dict[str, tuple[float, float]]:
    """块名 -> 插入点 (x_mm, y_mm)。"""
    return {e.dxf.name: (e.dxf.insert.x, e.dxf.insert.y) for e in msp
            if e.dxftype() == "INSERT"}


def test_block_count_and_names(doc, pieces):
    """① 块数 = Σ各码片数、块名 {片名}-G{NN}-{码} 全命中。"""
    blocks = [b.name for b in doc.blocks
              if not b.name.startswith(("*", "_"))]   # 剔匿名/标准箭头块
    assert len(blocks) == len(SIZES) * len(pieces)
    for s in SIZES:
        assert f"WAISTBAND-G05-{s}" in blocks
        assert f"BACK_PIECE-G02-{s}" in blocks


def test_gcode_same_across_sizes_unique_within(doc, pieces):
    """排料方式 A 多码口径：同一片型模板各码共用一个 g 码（跨码同号），
  每码内编号唯一（all-or-nothing 判定前提）；块名回读按对接正则复算
  (码号, g 码) 与渲染意图一致。"""
    blocks = [b.name for b in doc.blocks
              if not b.name.startswith(("*", "_"))]
    for s in SIZES:
        codes = set()
        for piece in pieces:
            m = piece_codes.parse_block_code(
                f"{piece.name.upper()}-G{piece_codes.gcode_for(piece.name):02d}-{s}")
            assert m == (s, piece_codes.gcode_for(piece.name))
            codes.add(m[1])
        assert len(codes) == len(pieces)
    # 跨码同号：同片名各码块剥出同一 g 码
    from collections import Counter
    g_per_piece = Counter(
        piece_codes.parse_block_code(n)[1] for n in blocks)
    for piece in pieces:
        g = piece_codes.gcode_for(piece.name)
        assert g_per_piece[g] == len(SIZES)


def test_sample_size_is_base(doc):
    """② Sample Size = 基码。"""
    headers = [t for t in _texts(doc.modelspace())
               if t.startswith("Sample Size:")]
    assert headers == [f"Sample Size: {BASE}"]


def test_category_resets_per_size(doc):
    """③ Category 码内 0 起重置（同片名跨码相同）。"""
    for s in SIZES:
        for piece_name, expect in (("WAISTBAND-G05", "0"),
                                    ("BACK_PIECE-G02", "1")):
            cats = [t for t in _texts(doc.blocks.get(f"{piece_name}-{s}"))
                    if t.startswith("Category:")]
            assert cats == [f"Category: {expect}"]


def test_band_stacking(doc, pieces):
    """④ 带沿 Y 叠放：对照 _layout/_piece_bounds 精确重建各 INSERT 插入点；
    带间距 = BAND_GAP_CM、首带贴原点。"""
    placements = _layout(pieces, PIECE_GAP_CM)
    exp_bottom = {}
    band_y = 0.0
    for s in SIZES:
        band_h = 0.0
        for piece, _offx, offy in placements:
            _x0, y0, _x1, y1 = _piece_bounds(piece)
            band_h = max(band_h, offy + (y1 - y0))
        exp_bottom[s] = band_y
        band_y += band_h + BAND_GAP_CM
    ins = _inserts(doc.modelspace())
    for s in SIZES:
        for piece, offx, offy in placements:
            name = (f"{piece.name.upper()}"
                    f"-G{piece_codes.gcode_for(piece.name):02d}-{s}")
            assert name in ins, name
            assert ins[name][0] == pytest.approx(offx * 10)
            assert ins[name][1] == pytest.approx((exp_bottom[s] + offy) * 10)
    # 首带贴原点（带内首行 offy = 0，插入点 y = 0）
    assert min(y for _x, y in ins.values()) == pytest.approx(0.0)
    # 带间距 = BAND_GAP_CM（下一带底 − 上一带顶）
    for s, s_next in zip(SIZES, SIZES[1:]):
        band_h = max(offy + (_piece_bounds(p)[3] - _piece_bounds(p)[1])
                     for p, _x, offy in placements)
        assert exp_bottom[s_next] - (exp_bottom[s] + band_h) == \
            pytest.approx(BAND_GAP_CM)


def test_size_band_labels(doc):
    """⑤ 多码时每带一条码标 TEXT（层 1）。"""
    msp = doc.modelspace()
    for s in SIZES:
        labels = [e for e in msp if e.dxftype() == "TEXT"
                  and e.dxf.text == f"SIZE {s}"]
        assert len(labels) == 1
        assert labels[0].dxf.layer == "1"


def test_write_and_readback(pieces, tmp_path):
    """⑦ 写盘回读 + 999 头 + R12 清洗无 group 5 + $EXTMIN 覆盖全带。"""
    ezdxf = pytest.importorskip("ezdxf")
    path = tmp_path / "run.dxf"
    write_size_run_dxf([(s, pieces) for s in SIZES], str(path),
                       sample_size=BASE)
    doc = ezdxf.readfile(str(path))
    assert abs(doc.header["$EXTMIN"][1]) < 1e19
    assert abs(doc.header["$EXTMAX"][1]) < 1e19
    # $EXTMAX 覆盖全带：>= 末带顶边（band_total 含末带后的带间距，扣除）
    band_total = 0.0
    for s in SIZES:
        band_total += max(offy + (_piece_bounds(p)[3] - _piece_bounds(p)[1])
                          for p, _x, offy in _layout(pieces, PIECE_GAP_CM)) \
            + BAND_GAP_CM
    assert doc.header["$EXTMAX"][1] + 1e-6 >= (band_total - BAND_GAP_CM) * 10
    with open(path, encoding="ascii") as fp:
        lines = fp.readlines()
    assert lines[0].strip() == "999"          # AAMA 注释组在文件最前
    # R12 兼容清洗：无 handle（group 5）
    assert not any(ln.rstrip("\r\n") == "  5" for ln in lines)
