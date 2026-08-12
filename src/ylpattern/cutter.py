"""裁切层：净样 -> 缩水 -> 缝边（腰头裁片.md §五）。

apply_shrinkage  仿射缩放（经/纬），保持贝塞尔性，刀口同步。
add_seam_allowance  各边按独立缝份沿**外法向**偏移（曲线逐点真法向 offset，
  直线=轴向偏移）；相邻异名边角点取两偏移边切线延伸的交点（miter）连接——
  弯腰头弧线端缝份顺曲线斜出（不再轴对方直角折），直角边 miter 即外角点
  （=原阶梯角，直腰头矩形不变）。同名边（如后中处上下口分段）平滑相接无角点。

依赖方向：cutter -> pieces -> geometry（禁止反向）。
"""

from __future__ import annotations

from .geometry import CubicBezier, LineSegment, Point, Vector
from .pieces import PieceEdge, PatternPiece
from .params import WaistbandSeamAllowances


# 各语义边的缝份量（腰头裁片.md §五.3）：方向由边几何的外法向决定，此处只给量
def _sa_amount(name: str, sa: WaistbandSeamAllowances) -> float:
    if name == "bottom":
        return sa.bottom
    if name == "top":
        return sa.top
    if name == "left_end":
        return sa.left_end
    if name == "right_end":
        return sa.right_end
    return 0.0                       # 折线边（如后中）不外扩


def _edge_start(g: LineSegment | CubicBezier) -> Point:
    return g.a if isinstance(g, LineSegment) else g.p0


def _edge_end(g: LineSegment | CubicBezier) -> Point:
    return g.b if isinstance(g, LineSegment) else g.p3


def edge_length(g: LineSegment | CubicBezier) -> float:
    """边长（LineSegment.length 为属性、CubicBezier.length() 为方法，API 不一）。"""
    return g.length if isinstance(g, LineSegment) else g.length()


def _unit_tangent(g: LineSegment | CubicBezier, at_end: bool) -> Vector:
    """边首端/末端的单位切线（沿逆时针走向）。"""
    if isinstance(g, LineSegment):
        v = g.b - g.a
    else:
        v = g.tangent_at(1.0 if at_end else 0.0)
    return v.normalized() if v.length > 0 else Vector(1.0, 0.0)


def _scale_point(p: Point, sx: float, sy: float) -> Point:
    return Point(p.x * sx, p.y * sy)


def _scale_geom(g: LineSegment | CubicBezier,
                sx: float, sy: float) -> LineSegment | CubicBezier:
    if isinstance(g, LineSegment):
        return LineSegment(_scale_point(g.a, sx, sy), _scale_point(g.b, sx, sy))
    return CubicBezier(_scale_point(g.p0, sx, sy), _scale_point(g.p1, sx, sy),
                       _scale_point(g.p2, sx, sy), _scale_point(g.p3, sx, sy))


def apply_shrinkage(piece: PatternPiece, warp: float, weft: float
                    ) -> PatternPiece:
    """应用经/纬向缩水（§五.2）：x·(1+warp)、y·(1+weft) 仿射缩放。

    缩放保持贝塞尔性（控制点同步缩放）；刀口、丝缕线同步偏移。
    返回填充 shrunk_edges / shrunk_notches 的新裁片。
    """
    sx, sy = 1.0 + warp, 1.0 + weft
    shrunk = tuple(PieceEdge(e.name, _scale_geom(e.geom, sx, sy))
                   for e in piece.net_edges)
    snotches = tuple(_scale_point(p, sx, sy) for p in piece.notches)
    sgrain = None
    if piece.grain is not None:
        sgrain = LineSegment(_scale_point(piece.grain.a, sx, sy),
                             _scale_point(piece.grain.b, sx, sy))
    out = piece.with_shrunk(shrunk, snotches)
    # 丝缕线随缩水更新（with_shrunk 不带 grain，重建一个）
    return PatternPiece(out.name, out.label, out.net_edges, out.notches,
                        sgrain, out.shrunk_edges, out.shrunk_notches,
                        out.gross_polygon, out.gross_notches,
                        out.notes + (f"缩水：经 {warp*100:.1f}% / 纬 {weft*100:.1f}%",)
                        if warp or weft else out.notes)


def _edge_points(edge: PieceEdge) -> list[Point]:
    """边采样为点序列（直线取端点；曲线采样 32 段）。"""
    g = edge.geom
    if isinstance(g, LineSegment):
        return [g.a, g.b]
    return g.sample(32)


def _offset_edge_points(edge: PieceEdge, sa: WaistbandSeamAllowances
                        ) -> list[Point]:
    """边各采样点沿外法向偏移缝份（曲线逐点真法向、直线=整体平移=轴向）。

    外法向 = 走向切线逆时针转 90°（Vector.perpendicular）：逆时针走向下，腰头
    下口外法向朝下、上口朝上、左端朝左、右端朝右，与§五.3 一致。缝份为 0 时
    返回原采样点。
    """
    amt = _sa_amount(edge.name, sa)
    g = edge.geom
    if amt == 0.0:
        return _edge_points(edge)
    if isinstance(g, LineSegment):
        v = g.b - g.a
        if v.length == 0.0:               # 零长退化边无切线，不偏移（防御其他来源退化边）
            return []
        nv = v.normalized().perpendicular().scale(amt)
        return [g.a + nv, g.b + nv]
    pts = g.sample(32)
    return [p + g.tangent_at(i / 32).perpendicular().scale(amt)
            for i, p in enumerate(pts)]


def _miter_point(p: Point, t_a: Vector, t_b: Vector,
                 sa_a: float, sa_b: float) -> Point | None:
    """角点 p 处两偏移边切线延伸的交点（法向缝份 miter）。

    本边偏移末端 = p + n_a·sa_a（n_a = t_a.perpendicular()），沿 t_a 前伸；
    下边偏移首端 = p + n_b·sa_b，沿 t_b 后伸；二者交点即 miter。切线平行（含
    同向）时 det≈0 返回 None，调用方回退阶梯角。直角角点 miter 恰 = 外角点。
    """
    n_a = t_a.perpendicular()
    n_b = t_b.perpendicular()
    off_a = p + n_a.scale(sa_a)
    off_b = p + n_b.scale(sa_b)
    d = off_b - off_a                       # 解 s·t_a + u·t_b = d 中的 s
    det = t_a.dx * t_b.dy - t_a.dy * t_b.dx
    if abs(det) < 1e-9:
        return None
    s = (d.dx * t_b.dy - d.dy * t_b.dx) / det
    return off_a + t_a.scale(s)


def add_seam_allowance(piece: PatternPiece,
                       sa: WaistbandSeamAllowances) -> PatternPiece:
    """各边按独立缝份沿外法向偏移生成毛样（§五.3，真法向 offset + miter 角）。

    基底为 shrunk_edges（无缩水时退化为 net_edges）。各边点序列沿外法向偏移；
    相邻异名边角点 p 处取两偏移边切线延伸交点（miter）连接——弯腰头弧端缝份
    顺曲线斜出、直角边 miter=外角点（直腰头矩形角不变）。切线平行时回退阶梯角
    （外角点 = p + n_a·sa_a + n_b·sa_b）。同名边（后中处上下口分段）平滑相接。
    毛样刀口 = 缩水后刀口（刀口标缝合线，缝份另裁）。
    """
    base = piece.shrunk_edges or piece.net_edges
    base_notches = piece.shrunk_notches or piece.notches
    if not base:
        return piece

    n = len(base)
    poly: list[Point] = []
    for i, edge in enumerate(base):
        for p in _offset_edge_points(edge, sa):
            if not poly or poly[-1] != p:
                poly.append(p)
        # 角点：与下一条异名边 -> miter（或平行回退阶梯）
        nxt = base[(i + 1) % n]
        if nxt.name == edge.name:
            continue
        sa_a = _sa_amount(edge.name, sa)
        sa_b = _sa_amount(nxt.name, sa)
        if sa_a == 0.0 and sa_b == 0.0:
            continue
        corner = _edge_end(edge.geom)       # 角点（本边末端 = 下边首端）
        t_a = _unit_tangent(edge.geom, True)
        t_b = _unit_tangent(nxt.geom, False)
        miter = _miter_point(corner, t_a, t_b, sa_a, sa_b)
        if miter is not None:
            if miter != poly[-1]:
                poly.append(miter)
        else:
            # 切线平行回退：阶梯角（外角点 + 下边偏移起点）
            n_a = t_a.perpendicular()
            n_b = t_b.perpendicular()
            outer = corner + n_a.scale(sa_a) + n_b.scale(sa_b)
            nxt_start = corner + n_b.scale(sa_b)
            if outer != poly[-1] and outer != nxt_start:
                poly.append(outer)
            if nxt_start != poly[-1]:
                poly.append(nxt_start)

    # 去除与首点重合的末点（闭合多边形不重复首点）
    if len(poly) > 1 and poly[-1] == poly[0]:
        poly.pop()

    notes = piece.notes + (
        f"缝边：上口 {sa.top} / 下口 {sa.bottom} / 左端 {sa.left_end} / 右端 {sa.right_end}",)
    return piece.with_gross(tuple(poly), tuple(base_notches), notes)
