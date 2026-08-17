"""整版 DXF 输出测试（R12/mm；.doc/python工程设计.md §10.3 DXF 小节）。

金标（M 同 test_waistband_piece：W=70, H=96, Δ=1.0, outseam=102）：
- flatten：控制点共线恰 [p0, p3] 2 点；tolerance=0 细分到深度上限
  2^12 段 = 4097 点；1/4 圆贝塞尔（k=0.5523, r=10cm）折线长与真弧长
  双侧差 < 0.05cm（k 舍入使贝塞尔自身略长于圆弧，不能单侧断言）。
- 整版：dxfversion == "AC1009"（R12）；LINE/POLYLINE/CIRCLE 实体数与
  sheet.lines/curves/points 一一对应；TEXT = lines+points+1（含 UNITS）；
  首线端点坐标 = cm×10 精确换算；REF 层 DASHED 线型。
ezdxf 缺席时：flatten/报错分支仍可跑，建档用例逐条 importorskip。
"""

import math
import sys

import pytest

from ylpattern.exporters._dxf_base import (FLATTEN_TOL_CM, MAX_FLATTEN_DEPTH,
                                           flatten_bezier, require_ezdxf)
from ylpattern.flows.back_flow import FULL_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.geometry import CubicBezier, Point
from ylpattern.params import Measurements, PatternOptions

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)


@pytest.fixture()
def ctx():
    return FlowRunner(M, PatternOptions(delta=1.0)).run(FULL_FLOW)


def _ents(doc, dxftype: str, layer: str | None = None) -> list:
    msp = doc.modelspace()
    return [e for e in msp if e.dxftype() == dxftype
            and (layer is None or e.dxf.layer == layer)]


# ---------- flatten 金标（无需 ezdxf） ----------

def test_flatten_collinear_is_two_endpoints():
    """控制点共线（真实直线）：恰返回 [p0, p3]。"""
    b = CubicBezier(Point(0, 0), Point(1, 1), Point(2, 2), Point(3, 3))
    pts = flatten_bezier(b)
    assert len(pts) == 2
    assert pts[0] == b.p0 and pts[-1] == b.p3


def test_flatten_zero_tolerance_hits_depth_cap():
    """tolerance=0：细分到深度上限而非死递归，恰 2^12+1 点、首尾守恒。"""
    b = CubicBezier(Point(0, 0), Point(0, 5), Point(10, 5), Point(10, 0))
    pts = flatten_bezier(b, 0.0)
    assert len(pts) == 2 ** MAX_FLATTEN_DEPTH + 1
    assert pts[0] == b.p0 and pts[-1] == b.p3


def test_flatten_quarter_circle_length_golden():
    """1/4 圆贝塞尔（k=0.5523, r=10cm）：折线长与真弧长差 < 0.05cm。

    双侧口径：k=0.5523 为 0.5522847… 的舍入，该贝塞尔自身弧长略大于
    真圆弧，折线长（弦 < 贝塞尔弧长）可以落在 πr/2 之上，不能单侧断言。
    """
    r, k = 10.0, 0.5523
    b = CubicBezier(Point(r, 0), Point(r, k * r), Point(k * r, r), Point(0, r))
    pts = flatten_bezier(b, FLATTEN_TOL_CM)
    length = sum(pts[i].distance_to(pts[i + 1]) for i in range(len(pts) - 1))
    arc = math.pi / 2 * r
    assert abs(length - arc) < 0.05


def test_require_ezdxf_missing_message(monkeypatch):
    """ezdxf 未安装：RuntimeError 带安装指引（ylpattern[dxf]）。"""
    monkeypatch.setitem(sys.modules, "ezdxf", None)
    with pytest.raises(RuntimeError, match=r"ylpattern\[dxf\]"):
        require_ezdxf()


# ---------- 整版 DXF（需 ezdxf） ----------

def test_sheet_dxf_version_and_entity_counts(ctx):
    ezdxf = pytest.importorskip("ezdxf")
    from ylpattern.exporters.dxf import render_sheet_dxf
    doc = render_sheet_dxf(ctx.sheet)
    assert doc.dxfversion == "AC1009"                       # R12
    assert len(_ents(doc, "LINE")) == len(ctx.sheet.lines)
    assert len(_ents(doc, "POLYLINE")) == len(ctx.sheet.curves)
    assert len(_ents(doc, "CIRCLE")) == len(ctx.sheet.points)
    assert len(_ents(doc, "TEXT")) == len(ctx.sheet.lines) \
        + len(ctx.sheet.points) + 1                          # +1 UNITS 声明


def test_sheet_dxf_line_mm_golden(ctx):
    """首条线端点坐标 = cm×10 精确换算（mm、直传不翻转）。"""
    pytest.importorskip("ezdxf")
    from ylpattern.exporters.dxf import render_sheet_dxf
    doc = render_sheet_dxf(ctx.sheet)
    e0 = _ents(doc, "LINE")[0]                               # 线最先写入
    g = ctx.sheet.lines[0].geom
    assert e0.dxf.start.x == pytest.approx(g.a.x * 10)
    assert e0.dxf.start.y == pytest.approx(g.a.y * 10)
    assert e0.dxf.end.x == pytest.approx(g.b.x * 10)
    assert e0.dxf.end.y == pytest.approx(g.b.y * 10)


def test_sheet_dxf_layers(ctx):
    ezdxf = pytest.importorskip("ezdxf")
    from ylpattern.exporters.dxf import render_sheet_dxf
    doc = render_sheet_dxf(ctx.sheet)
    assert doc.layers.get("REF").dxf.linetype == "DASHED"    # setup=True 已载入
    assert doc.layers.get("STRUCT").dxf.color == 7
    # 全部 TEXT ASCII（R12 编码约束）
    assert all(e.dxf.text.isascii() for e in _ents(doc, "TEXT"))
    texts = {e.dxf.text for e in _ents(doc, "TEXT")}
    assert "UNITS=MM (DXF R12)" in texts
    assert ctx.sheet.points[0].name in texts                 # 点 name 标注


def test_sheet_dxf_extents_backfilled(ctx):
    """$EXTMIN/$EXTMAX 已回填真实范围（ezdxf R12 默认 ±1e20 哨兵值，老 CAD
    如 ET 2008 用它做初始视图，哨兵值致打开黑屏）。"""
    pytest.importorskip("ezdxf")
    from ylpattern.exporters.dxf import render_sheet_dxf
    doc = render_sheet_dxf(ctx.sheet)
    extmin, extmax = doc.header["$EXTMIN"], doc.header["$EXTMAX"]
    assert abs(extmin[0]) < 1e19 and abs(extmax[0]) < 1e19
    g = ctx.sheet.lines[0].geom
    assert extmin[0] <= min(g.a.x, g.b.x) * 10 + 1e-6
    assert extmax[1] >= max(g.a.y, g.b.y) * 10 - 1e-6


def test_sheet_dxf_write_roundtrip(ctx, tmp_path):
    ezdxf = pytest.importorskip("ezdxf")
    from ylpattern.exporters.dxf import write_sheet_dxf
    path = tmp_path / "sheet.dxf"
    write_sheet_dxf(ctx.sheet, str(path))
    doc = ezdxf.readfile(str(path))
    assert doc.dxfversion == "AC1009"
    # 文件级断言：saveas 的 update_all 会用 msp.dxf 覆写 header，必须
    # 把范围设到布局属性上，否则写盘回读仍是 ±1e20 哨兵值（ET08 黑屏）
    assert abs(doc.header["$EXTMIN"][0]) < 1e19
    assert abs(doc.header["$EXTMAX"][0]) < 1e19
