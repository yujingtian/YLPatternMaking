"""SVG 输出：整张版视图，分图层（reference / elements）。

坐标处理：版坐标 Y 向上、单位 cm；SVG Y 向下、单位 px。
缩放比例 SCALE = 10 px/cm，渲染时统一翻转。
"""

from __future__ import annotations

from ..draft import DraftSheet
from ..draft.elements import NamedPoint, NamedLine, NamedCurve

SCALE = 10.0   # px / cm
MARGIN = 30.0  # 画布边距 px

_STYLE = """<style>
  .refline  { stroke: #999; stroke-width: 0.8; stroke-dasharray: 5 4; }
  .reflabel { fill: #888; font: 9px monospace; }
  .structline { stroke: #2c3e50; stroke-width: 1.5; fill: none; }
  .structlabel { fill: #2c3e50; font: 9px monospace; }
  .pt       { fill: #c0392b; }
  .ptlabel  { fill: #c0392b; font: 9px monospace; }
  .curve    { stroke: #2c3e50; stroke-width: 1.5; fill: none; }
  .curveref { stroke: #999; stroke-width: 0.8; fill: none; stroke-dasharray: 5 4; }
</style>"""


def _sy(y: float, top: float) -> float:
    """版坐标 y → SVG 坐标（翻转）。"""
    return top - y * SCALE


def compute_view(sheet: DraftSheet) -> tuple[float, float, float, float]:
    """整版画布几何：按内容包围盒返回 (width, height, top, ox)。

    正向变换：sx(x) = x*SCALE + ox，sy(y) = top − y*SCALE（Y 翻转）；
    逆变换（px → 版坐标 cm）：x_cm = (px − ox)/SCALE，y_cm = (top − py)/SCALE。
    render_sheet 与 web 端（把手 px↔cm 换算）共用本函数，保证两处不漂移。
    """
    xs: list[float] = []
    ys: list[float] = []
    for line in sheet.lines:
        xs += [line.geom.a.x, line.geom.b.x]
        ys += [line.geom.a.y, line.geom.b.y]
    for pt in sheet.points:
        xs.append(pt.geom.x)
        ys.append(pt.geom.y)
    for cv in sheet.curves:
        for p in cv.geom.sample():
            xs.append(p.x)
            ys.append(p.y)
    if not xs:
        xs, ys = [0.0], [0.0]

    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    top = MARGIN + y1 * SCALE
    width = (x1 - x0) * SCALE + 2 * MARGIN
    height = (y1 - y0) * SCALE + 2 * MARGIN
    ox = MARGIN - x0 * SCALE  # x 方向平移
    return width, height, top, ox


def render_sheet(sheet: DraftSheet, show_labels: bool = True) -> str:
    """把整张版渲染为 SVG 文本。

    show_labels=False 隐藏全部文字标注（options.show_labels 总开关）：
    参考线名/结构线名/关键点名不绘制，线与点照常，画布尺寸不变。

    元素身份：每条线/曲线/点带 id="{元素名}"（name 全版唯一，DraftSheet
    强制），文字标注带 data-name——供 web 端把手/命中定位元素（二期拖拽）。
    根元素 data-scale/data-ox/data-top 全精度下发画布变换常量。
    """
    width, height, top, ox = compute_view(sheet)

    def sx(x: float) -> float:
        return x * SCALE + ox

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" '
        f'data-scale="{SCALE}" data-ox="{ox:.10g}" data-top="{top:.10g}">',
        _STYLE,
        '<rect width="100%" height="100%" fill="white"/>',
    ]

    # 图层：参考线
    parts.append('<g id="reference">')
    for line in sheet.lines:
        if line.role != "ref":
            continue
        a, b = line.geom.a, line.geom.b
        parts.append(
            f'<line id="{line.name}" class="refline" '
            f'x1="{sx(a.x):.1f}" y1="{_sy(a.y, top):.1f}" '
            f'x2="{sx(b.x):.1f}" y2="{_sy(b.y, top):.1f}"/>')
        if show_labels:
            text = line.label or line.name
            if abs(a.x - b.x) < 1e-9:
                # 竖线：标注沿线中点竖排，避免与水平线标注在角点重叠
                mx, my = sx(a.x), _sy((a.y + b.y) / 2, top)
                parts.append(
                    f'<text class="reflabel" data-name="{line.name}" '
                    f'x="{mx + 4:.1f}" y="{my:.1f}" '
                    f'transform="rotate(-90 {mx + 4:.1f} {my:.1f})" '
                    f'text-anchor="middle">{text}</text>')
            else:
                # 水平线：标注放在左端上方
                parts.append(
                    f'<text class="reflabel" data-name="{line.name}" '
                    f'x="{sx(a.x) + 4:.1f}" '
                    f'y="{_sy(a.y, top) - 3:.1f}">{text}</text>')
    parts.append('</g>')

    # 图层：结构线（实线，压在参考线之上）
    struct_lines = [ln for ln in sheet.lines if ln.role == "struct"]
    if struct_lines:
        parts.append('<g id="struct">')
        for line in struct_lines:
            a, b = line.geom.a, line.geom.b
            parts.append(
                f'<line id="{line.name}" class="structline" '
                f'x1="{sx(a.x):.1f}" y1="{_sy(a.y, top):.1f}" '
                f'x2="{sx(b.x):.1f}" y2="{_sy(b.y, top):.1f}"/>')
            if show_labels:
                text = line.label or line.name
                mx, my = sx((a.x + b.x) / 2), _sy((a.y + b.y) / 2, top)
                parts.append(
                    f'<text class="structlabel" data-name="{line.name}" '
                    f'x="{mx + 4:.1f}" y="{my - 4:.1f}">{text}</text>')
        parts.append('</g>')

    # 图层：曲线（struct 实线 / ref 虚线，与直线同口径）
    if sheet.curves:
        parts.append('<g id="curves">')
        for cv in sheet.curves:
            cls = "curveref" if cv.role == "ref" else "curve"
            pts = " ".join(f"{sx(p.x):.1f},{_sy(p.y, top):.1f}"
                           for p in cv.geom.sample())
            parts.append(f'<polyline id="{cv.name}" class="{cls}" '
                         f'points="{pts}"/>')
        parts.append('</g>')

    # 图层：关键点
    parts.append('<g id="elements">')
    for pt in sheet.points:
        x, y = sx(pt.geom.x), _sy(pt.geom.y, top)
        parts.append(f'<circle id="{pt.name}" class="pt" '
                     f'cx="{x:.1f}" cy="{y:.1f}" r="2.5"/>')
        if show_labels:
            parts.append(f'<text class="ptlabel" data-name="{pt.name}" '
                         f'x="{x + 5:.1f}" y="{y - 5:.1f}">'
                         f'{pt.label or pt.name}</text>')
    parts.append('</g>')

    parts.append('</svg>')
    return "\n".join(parts)


def write_sheet_svg(sheet: DraftSheet, path: str,
                    show_labels: bool = True) -> None:
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(render_sheet(sheet, show_labels=show_labels))
