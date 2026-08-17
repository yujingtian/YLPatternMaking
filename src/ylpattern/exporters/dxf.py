"""DXF 输出：整张版视图（与 svg.py 同构；R12 / mm，裁床与服装 CAD 口径）。

与 svg.py 的差异：
- 坐标直传不平移：版坐标 Y 向上与 DXF 同向，cm × 10 即可，保留绝对
  坐标便于与 trace/报表对照（SVG 因 Y 向下须翻转，DXF 不用）。
- 曲线按弦高公差 flatten 为 POLYLINE（R12 无 SPLINE；离散口径比 SVG 的
  固定 sample() 更严，满足裁床 0.1mm 级切割精度）。
- 全 ASCII：TEXT 取元素 name（如 ``front.crotch_point``），不取中文
  label——R12 单行 TEXT 跨富怡/ET 易乱码，中文标注留在 SVG。
"""

from __future__ import annotations

from ..draft import DraftSheet
from ..geometry import Point
from . import _dxf_base as base

UNITS_NOTE = "UNITS=MM (DXF R12)"

_LAYERS: dict[str, base.LayerSpec] = {
    "REF":    (8, "DASHED"),       # 参考线（虚线，与 SVG reference 同口径）
    "STRUCT": (7, "CONTINUOUS"),   # 结构直线
    "CURVE":  (7, "CONTINUOUS"),   # 结构曲线（flatten 折线）
    "POINT":  (1, "CONTINUOUS"),   # 关键点（CIRCLE，不依赖 $PDMODE 的 POINT 实体）
    "TEXT":   (7, "CONTINUOUS"),   # 元素名标注 + 单位声明
}


def render_sheet_dxf(sheet: DraftSheet, *,
                     tolerance_cm: float = base.FLATTEN_TOL_CM):
    """把整张版渲染为 R12 DXF 文档（ezdxf Drawing）。"""
    doc = base.new_doc(_LAYERS)
    msp = doc.modelspace()

    def to_mm(p: Point) -> tuple[float, float]:
        return (p.x * base.MM_PER_CM, p.y * base.MM_PER_CM)

    # 直线：role 分层（ref 虚线 / struct 实线），与 svg.py 图层划分同口径
    for line in sheet.lines:
        layer = "REF" if line.role == "ref" else "STRUCT"
        g = line.geom
        msp.add_line(to_mm(g.a), to_mm(g.b), dxfattribs={"layer": layer})
    # 曲线：全部 flatten 为折线；role=="ref" 入 REF 层，否则 CURVE 层
    for cv in sheet.curves:
        layer = "REF" if cv.role == "ref" else "CURVE"
        base.add_polyline(msp, base.flatten_bezier(cv.geom, tolerance_cm),
                          to_mm, layer=layer)
    # 关键点 + 各元素 name 标注
    for pt in sheet.points:
        x, y = to_mm(pt.geom)
        msp.add_circle((x, y), base.DRILL_RADIUS_MM,
                       dxfattribs={"layer": "POINT"})
        base.add_text(msp, pt.name, pt.geom, to_mm)
    for line in sheet.lines:
        base.add_text(msp, line.name, line.geom.a, to_mm)
    # 单位声明：置于全版内容下方 3cm 处（避开原点附近元素）
    ys = [p.geom.y for p in sheet.points]
    ys += [c for ln in sheet.lines for c in (ln.geom.a.y, ln.geom.b.y)]
    note_y = (min(ys) - 3.0) if ys else 0.0
    base.add_text(msp, UNITS_NOTE, Point(0.0, note_y), to_mm)
    base.set_extents(doc)      # 回填 $EXTMIN/$EXTMAX，防老 CAD（ET 08）黑屏
    return doc


def write_sheet_dxf(sheet: DraftSheet, path: str, *,
                    tolerance_cm: float = base.FLATTEN_TOL_CM) -> None:
    # save_doc：R12 兼容清洗（剥 handle/$HANDLING/EZDXF XDATA，防 ET 08 打不开）
    base.save_doc(render_sheet_dxf(sheet, tolerance_cm=tolerance_cm), path)
