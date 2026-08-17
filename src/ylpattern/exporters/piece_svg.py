"""裁片 SVG 输出：独立裁片视图（腰头裁片.md §五.4，独立 SVG）。

与整版 svg.py 的区别：裁片局部坐标系 **Y 向下**（与 SVG 同向），渲染时
仅缩放平移、不翻转。图层：gross 毛样（实线，最终裁切线）/ shrunk_net
含缩水净样（虚线；缩水时唯一内轮廓基准）/ net 净样（淡虚线；**仅在未缩水时
绘制**，已缩水则省略——两条内轮廓虚线并存易误读）/ notches 刀口（红）/
grain 丝缕线（蓝）/ drills 定位孔（红空心圈，后片裁片.md §6 定位图层）。
"""

from __future__ import annotations

from ..geometry import CubicBezier, LineSegment, Point
from ..pieces import PatternPiece, PieceEdge

SCALE = 10.0    # px / cm
MARGIN = 40.0   # 画布边距 px

_STYLE = """<style>
  .netline   { stroke: #bbb; stroke-width: 0.8; fill: none; stroke-dasharray: 3 3; }
  .shrunkline{ stroke: #888; stroke-width: 1.0; fill: none; stroke-dasharray: 6 3; }
  .grossline { stroke: #2c3e50; stroke-width: 1.6; fill: none; }
  .markline  { stroke: #16a085; stroke-width: 0.9; fill: none; stroke-dasharray: 2 2; }
  .notch     { stroke: #c0392b; stroke-width: 1.2; fill: none; }
  .notchpt   { fill: #c0392b; }
  .grain     { stroke: #2980b9; stroke-width: 1.0; fill: none; }
  .drill    { stroke: #c0392b; stroke-width: 1.2; fill: none; }
  .label     { fill: #2c3e50; font: 12px monospace; }
  .small     { fill: #666; font: 9px monospace; }
</style>"""


def _edge_points(edge: PieceEdge) -> list[Point]:
    g = edge.geom
    if isinstance(g, LineSegment):
        return [g.a, g.b]
    return g.sample(48)


def _geom_points(g: LineSegment | CubicBezier) -> list[Point]:
    """几何（直线/曲线）采样为点序列（marks 等无 PieceEdge 包装的几何用）。"""
    if isinstance(g, LineSegment):
        return [g.a, g.b]
    return g.sample(48)


def _bounds(piece: PatternPiece) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for p in piece.gross_polygon:
        xs.append(p.x); ys.append(p.y)
    for e in piece.net_edges:
        for p in _edge_points(e):
            xs.append(p.x); ys.append(p.y)
    for p in piece.notches:
        xs.append(p.x); ys.append(p.y)
    for p in piece.drills:
        xs.append(p.x); ys.append(p.y)
    if piece.grain is not None:
        xs += [piece.grain.a.x, piece.grain.b.x]
        ys += [piece.grain.a.y, piece.grain.b.y]
    if not xs:
        xs, ys = [0.0], [0.0]
    return min(xs), min(ys), max(xs), max(ys)


def render_piece_svg(piece: PatternPiece) -> str:
    """把裁片渲染为独立 SVG 文本。"""
    x0, y0, x1, y1 = _bounds(piece)
    width = (x1 - x0) * SCALE + 2 * MARGIN
    height = (y1 - y0) * SCALE + 2 * MARGIN
    ox = MARGIN - x0 * SCALE
    oy = MARGIN - y0 * SCALE

    def sx(x: float) -> float:
        return x * SCALE + ox

    def sy(y: float) -> float:
        return y * SCALE + oy          # Y 向下不翻转

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}">',
        _STYLE,
        '<rect width="100%" height="100%" fill="white"/>',
    ]

    # 净样（淡虚线；已缩水时省略——未缩水净样对裁切/缝纫无意义，
    # 只留 shrunk_net 一条内轮廓基准线，避免两条虚线并存误读）
    if not piece.shrunk_edges:
        parts.append('<g id="net">')
        for e in piece.net_edges:
            pts = " ".join(f"{sx(p.x):.1f},{sy(p.y):.1f}" for p in _edge_points(e))
            parts.append(f'<polyline class="netline" points="{pts}"/>')
        parts.append('</g>')

    # 含缩水净样（虚线）
    if piece.shrunk_edges:
        parts.append('<g id="shrunk">')
        for e in piece.shrunk_edges:
            pts = " ".join(f"{sx(p.x):.1f},{sy(p.y):.1f}" for p in _edge_points(e))
            parts.append(f'<polyline class="shrunkline" points="{pts}"/>')
        parts.append('</g>')

    # 毛样（实线，最终裁切线）
    if piece.gross_polygon:
        pts = " ".join(f"{sx(p.x):.1f},{sy(p.y):.1f}" for p in piece.gross_polygon)
        parts.append('<g id="gross">')
        parts.append(f'<polygon class="grossline" points="{pts}"/>')
        parts.append('</g>')

    # 内部标记弧线（净样坐标，如袋贴袋口净线/省弧线，前口袋裁片.md §1.1）
    if piece.marks:
        parts.append('<g id="marks">')
        for g in piece.marks:
            pts = " ".join(f"{sx(p.x):.1f},{sy(p.y):.1f}" for p in _geom_points(g))
            parts.append(f'<polyline class="markline" points="{pts}"/>')
        parts.append('</g>')

    # 丝缕线（双向箭头）
    if piece.grain is not None:
        a, b = piece.grain.a, piece.grain.b
        parts.append('<g id="grain">')
        parts.append(f'<line class="grain" x1="{sx(a.x):.1f}" y1="{sy(a.y):.1f}" '
                     f'x2="{sx(b.x):.1f}" y2="{sy(b.y):.1f}"/>')
        # 箭头（两端小三角）
        for end, back in ((a, b), (b, a)):
            d = (back - end)
            if d.length == 0:
                continue
            u = d.normalized()
            n = u.perpendicular()
            tip = end
            base = end + u.scale(-0.3)
            p1 = base + n.scale(0.12)
            p2 = base + n.scale(-0.12)
            parts.append(
                f'<polygon class="grain" points="{sx(tip.x):.1f},{sy(tip.y):.1f} '
                f'{sx(p1.x):.1f},{sy(p1.y):.1f} {sx(p2.x):.1f},{sy(p2.y):.1f}"/>')
        parts.append(f'<text class="small" x="{sx(a.x):.1f}" '
                     f'y="{sy(a.y) - 5:.1f}">经向</text>')
        parts.append('</g>')

    # 定位孔（红空心小圈，内部点标记；后片裁片.md §6 定位图层 Drill）
    if piece.drills:
        parts.append('<g id="drills">')
        for p in piece.drills:
            parts.append(f'<circle class="drill" cx="{sx(p.x):.1f}" '
                         f'cy="{sy(p.y):.1f}" r="2"/>')
        parts.append('</g>')

    # 刀口（红色短垂线 + 点）
    parts.append('<g id="notches">')
    for p in piece.gross_notches or piece.shrunk_notches or piece.notches:
        parts.append(f'<line class="notch" x1="{sx(p.x):.1f}" y1="{sy(p.y):.1f}" '
                     f'x2="{sx(p.x):.1f}" y2="{sy(p.y) + 4:.1f}"/>')
        parts.append(f'<circle class="notchpt" cx="{sx(p.x):.1f}" '
                     f'cy="{sy(p.y):.1f}" r="2"/>')
    parts.append('</g>')

    # 标注
    parts.append(f'<text class="label" x="{MARGIN:.0f}" y="{MARGIN - 10:.0f}">'
                 f'{piece.label}</text>')
    # 净长宽信息（取 net 边界）
    nx = [p.x for e in piece.net_edges for p in _edge_points(e)]
    ny = [p.y for e in piece.net_edges for p in _edge_points(e)]
    if nx:
        info = (f"净长 {max(nx) - min(nx):.2f} × 净宽 {max(ny) - min(ny):.2f} cm"
                f"（半片 {piece.net_edges and '×2 镜像' or ''}）")
        parts.append(f'<text class="small" x="{MARGIN:.0f}" '
                     f'y="{height - MARGIN + 8:.0f}">{info}</text>')

    parts.append('</svg>')
    return "\n".join(parts)


def write_piece_svg(piece: PatternPiece, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(render_piece_svg(piece))
