"""DXF 输出：全部独立裁片平铺合一张（与 piece_svg.py 同构；R12 / mm）。

与 piece_svg.py 的差异：
- 多片共一张图：shelf 行装箱平铺（行宽上限 ROW_LIMIT_CM、片间距
  PIECE_GAP_CM），行内底边对齐；多片共用同一组功能图层（裁床惯例：
  全部裁切线在同一层），裁片间靠 TEXT piece.name 区分。
- 坐标：裁片局部系 **Y 向下**，变换 X=(x-x0+offx)*10、Y=(y1-y+offy)*10
  ——翻转后 DXF（Y 向上）显示与 SVG 屏幕视觉逐点重合，手性不变
  （裁片不镜像，裁床切出的物理片与 SVG 打印件一致）；片 bbox 平移到
  (offx, offy) 处、首片左下角贴全局原点（套料惯例）。
- 刀口 = 毛样外沿该点处垂直轮廓向内的 NOTCH_LEN_CM 短线（POINT 实体
  裁床难识别，不用）；丝缕线省略箭头仅 LINE + TEXT "GRAIN"。
- 全 ASCII：标注取 piece.name 与净长宽数字，中文 label 留在 SVG。
"""

from __future__ import annotations

from collections.abc import Sequence

from ..geometry import Point, Vector
from ..pieces import PatternPiece
from . import _dxf_base as base

PIECE_GAP_CM = 3.0      # 平铺片间距
ROW_LIMIT_CM = 200.0    # 行宽上限（典型裁床门幅内）

UNITS_NOTE = "UNITS=MM (DXF R12)"

_LAYERS: dict[str, base.LayerSpec] = {
    "CUT":    (7, "CONTINUOUS"),   # 毛样裁切轮廓（闭合折线）
    "NET":    (8, "DASHED"),       # 净样（仅未缩水时，同 piece_svg 规则）
    "SHRUNK": (3, "DASHED"),       # 含缩水净样（缩水时唯一内轮廓基准）
    "MARK":   (4, "DASHED"),       # 内部标记线（袋口净线/省弧/辅助线）
    "GRAIN":  (5, "CONTINUOUS"),   # 丝缕线
    "DRILL":  (1, "CONTINUOUS"),   # 定位孔
    "NOTCH":  (1, "CONTINUOUS"),   # 刀口刻线（法向向内短线）
    "TEXT":   (7, "CONTINUOUS"),   # 片名/净长宽/单位声明
}


def _piece_bounds(piece: PatternPiece) -> tuple[float, float, float, float]:
    """裁片全内容 bbox（含 marks/drills，DXF 输出应完整；比 piece_svg 的
    _bounds 口径更宽，供平铺布局用）。"""
    xs: list[float] = []
    ys: list[float] = []

    def add(p: Point) -> None:
        xs.append(p.x)
        ys.append(p.y)

    for p in piece.gross_polygon:
        add(p)
    for edges in (piece.net_edges, piece.shrunk_edges):
        for e in edges:
            for p in base.flatten_geom(e.geom):
                add(p)
    for g in piece.marks:
        for p in base.flatten_geom(g):
            add(p)
    for p in piece.notches + piece.shrunk_notches + piece.gross_notches:
        add(p)
    for p in piece.drills:
        add(p)
    if piece.grain is not None:
        add(piece.grain.a)
        add(piece.grain.b)
    if not xs:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), min(ys), max(xs), max(ys)


def _layout(pieces: Sequence[PatternPiece], gap_cm: float
            ) -> list[tuple[PatternPiece, float, float]]:
    """shelf 行装箱：按传入顺序左->右摆放，行内底边对齐（bbox 下沿同高），
    累计行宽超 ROW_LIMIT_CM 换行，行高取该行最高片。返回 (piece, offx, offy)。"""
    placements: list[tuple[PatternPiece, float, float]] = []
    x = 0.0
    y = 0.0
    row_h = 0.0
    for piece in pieces:
        x0, _y0, x1, y1 = _piece_bounds(piece)
        w = x1 - x0
        h = y1 - _y0
        if placements and x + w > ROW_LIMIT_CM:
            x = 0.0
            y += row_h + gap_cm
            row_h = 0.0
        placements.append((piece, x, y))
        x += w + gap_cm
        row_h = max(row_h, h)
    return placements


def _notch_segment(p: Point, polygon: tuple[Point, ...]
                   ) -> tuple[Point, Point]:
    """刀口刻线：p 在毛样轮廓上，取垂直轮廓、指向裁片内部（质心方向）
    的 NOTCH_LEN_CM 短线；轮廓缺失/退化时回退竖直向下（局部系 Y 向下，
    与 piece_svg 刀口 y+4px 向下同口径）。"""
    n = len(polygon)
    if n < 3:
        return p, p + Vector(0.0, base.NOTCH_LEN_CM)
    idx = min(range(n), key=lambda i: p.distance_to(polygon[i]))
    tangent = polygon[(idx + 1) % n] - polygon[(idx - 1) % n]
    if tangent.length < 1e-12:
        normal = Vector(0.0, 1.0)
    else:
        normal = tangent.normalized().perpendicular()
    cx = sum(q.x for q in polygon) / n
    cy = sum(q.y for q in polygon) / n
    inward = Vector(cx - p.x, cy - p.y)
    if inward.dx * normal.dx + inward.dy * normal.dy < 0.0:
        normal = Vector(-normal.dx, -normal.dy)
    return p, p + normal.scale(base.NOTCH_LEN_CM)


def _render_piece_into(msp, piece: PatternPiece, to_mm: base.ToMm,
                       tolerance_cm: float) -> None:
    """单片写入（图层顺序同 piece_svg：CUT/NET/SHRUNK/MARK/GRAIN/DRILL/NOTCH）。"""
    # 毛样（最终裁切线，闭合）
    if piece.gross_polygon:
        base.add_polyline(msp, piece.gross_polygon, to_mm,
                          layer="CUT", closed=True)
    # 净样（淡虚线；已缩水时省略——同 piece_svg，只留一条内轮廓基准线）
    if not piece.shrunk_edges:
        for e in piece.net_edges:
            base.add_polyline(msp, base.flatten_geom(e.geom, tolerance_cm),
                              to_mm, layer="NET")
    if piece.shrunk_edges:
        for e in piece.shrunk_edges:
            base.add_polyline(msp, base.flatten_geom(e.geom, tolerance_cm),
                              to_mm, layer="SHRUNK")
    # 内部标记线（净样坐标，如袋口净线/省弧/围度辅助线）
    for g in piece.marks:
        base.add_polyline(msp, base.flatten_geom(g, tolerance_cm),
                          to_mm, layer="MARK")
    # 丝缕线（省略箭头）
    if piece.grain is not None:
        msp.add_line(to_mm(piece.grain.a), to_mm(piece.grain.b),
                     dxfattribs={"layer": "GRAIN"})
        base.add_text(msp, "GRAIN", piece.grain.a, to_mm, height_mm=2.0)
    # 定位孔
    for q in piece.drills:
        x, y = to_mm(q)
        msp.add_circle((x, y), base.DRILL_RADIUS_MM,
                       dxfattribs={"layer": "DRILL"})
    # 刀口（三态回退链同 piece_svg；法向向内短线）
    for q in piece.gross_notches or piece.shrunk_notches or piece.notches:
        a, b = _notch_segment(q, piece.gross_polygon)
        msp.add_line(to_mm(a), to_mm(b), dxfattribs={"layer": "NOTCH"})


def render_pieces_dxf(pieces: Sequence[PatternPiece], *,
                      tolerance_cm: float = base.FLATTEN_TOL_CM,
                      gap_cm: float = PIECE_GAP_CM):
    """把全部裁片平铺渲染为一张 R12 DXF 文档（ezdxf Drawing）。"""
    doc = base.new_doc(_LAYERS)
    msp = doc.modelspace()
    for piece, offx, offy in _layout(pieces, gap_cm):
        x0, y0, _x1, y1 = _piece_bounds(piece)

        def to_mm(p: Point, x0=x0, y1=y1, offx=offx, offy=offy
                  ) -> tuple[float, float]:
            return ((p.x - x0 + offx) * base.MM_PER_CM,
                    (y1 - p.y + offy) * base.MM_PER_CM)

        _render_piece_into(msp, piece, to_mm, tolerance_cm)
        # 片名 + 净长宽标注：置于片 bbox 上沿之上（局部系 y 向上为负）
        net_pts = [q for e in piece.net_edges
                   for q in base.flatten_geom(e.geom, tolerance_cm)]
        base.add_text(msp, piece.name, Point(x0, y0 - 0.8), to_mm)
        if net_pts:
            nw = max(q.x for q in net_pts) - min(q.x for q in net_pts)
            nh = max(q.y for q in net_pts) - min(q.y for q in net_pts)
            base.add_text(msp, f"NET {nw * 10:.0f}x{nh * 10:.0f}MM",
                          Point(x0, y0 - 1.8), to_mm)
    # 单位声明：全局原点下方（全部内容 y >= 0，不与任何片重叠）
    def _mm(p: Point) -> tuple[float, float]:
        return (p.x * base.MM_PER_CM, p.y * base.MM_PER_CM)

    base.add_text(msp, UNITS_NOTE, Point(0.0, -1.0), _mm)
    base.set_extents(doc)      # 回填 $EXTMIN/$EXTMAX，防老 CAD（ET 08）黑屏
    return doc


def write_pieces_dxf(pieces: Sequence[PatternPiece], path: str, *,
                     tolerance_cm: float = base.FLATTEN_TOL_CM,
                     gap_cm: float = PIECE_GAP_CM) -> None:
    render_pieces_dxf(pieces, tolerance_cm=tolerance_cm,
                      gap_cm=gap_cm).saveas(path)
