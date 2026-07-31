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
  .pt       { fill: #c0392b; }
  .ptlabel  { fill: #c0392b; font: 9px monospace; }
  .curve    { stroke: #2c3e50; stroke-width: 1.5; fill: none; }
</style>"""


def _sy(y: float, top: float) -> float:
    """版坐标 y → SVG 坐标（翻转）。"""
    return top - y * SCALE


def render_sheet(sheet: DraftSheet) -> str:
    """把整张版渲染为 SVG 文本。"""
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

    def sx(x: float) -> float:
        return x * SCALE + ox

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}">',
        _STYLE,
        '<rect width="100%" height="100%" fill="white"/>',
    ]

    # 图层：参考线
    parts.append('<g id="reference">')
    for line in sheet.lines:
        a, b = line.geom.a, line.geom.b
        parts.append(
            f'<line class="refline" x1="{sx(a.x):.1f}" y1="{_sy(a.y, top):.1f}" '
            f'x2="{sx(b.x):.1f}" y2="{_sy(b.y, top):.1f}"/>')
        text = line.label or line.name
        if abs(a.x - b.x) < 1e-9:
            # 竖线：标注沿线中点竖排，避免与水平线标注在角点重叠
            mx, my = sx(a.x), _sy((a.y + b.y) / 2, top)
            parts.append(
                f'<text class="reflabel" x="{mx + 4:.1f}" y="{my:.1f}" '
                f'transform="rotate(-90 {mx + 4:.1f} {my:.1f})" '
                f'text-anchor="middle">{text}</text>')
        else:
            # 水平线：标注放在左端上方
            parts.append(
                f'<text class="reflabel" x="{sx(a.x) + 4:.1f}" '
                f'y="{_sy(a.y, top) - 3:.1f}">{text}</text>')
    parts.append('</g>')

    # 图层：曲线
    if sheet.curves:
        parts.append('<g id="curves">')
        for cv in sheet.curves:
            pts = " ".join(f"{sx(p.x):.1f},{_sy(p.y, top):.1f}"
                           for p in cv.geom.sample())
            parts.append(f'<polyline class="curve" points="{pts}"/>')
        parts.append('</g>')

    # 图层：关键点
    parts.append('<g id="elements">')
    for pt in sheet.points:
        x, y = sx(pt.geom.x), _sy(pt.geom.y, top)
        parts.append(f'<circle class="pt" cx="{x:.1f}" cy="{y:.1f}" r="2.5"/>')
        parts.append(f'<text class="ptlabel" x="{x + 5:.1f}" y="{y - 5:.1f}">'
                     f'{pt.label or pt.name}</text>')
    parts.append('</g>')

    parts.append('</svg>')
    return "\n".join(parts)


def write_sheet_svg(sheet: DraftSheet, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(render_sheet(sheet))
