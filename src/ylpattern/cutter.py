"""裁切层：净样 -> 缩水 -> 缝边（腰头裁片.md §五）。

apply_shrinkage  仿射缩放（经/纬），保持贝塞尔性，刀口同步。
add_seam_allowance  各边按独立缝份沿**外法向**偏移（曲线逐点真法向 offset，
  直线=轴向偏移）；相邻异名边角点取两偏移边切线延伸的交点（miter）连接——
  弯腰头弧线端缝份顺曲线斜出（不再轴对方直角折），直角边 miter 即外角点
  （=原阶梯角，直腰头矩形不变）。同名边（如后中处上下口分段）平滑相接无角点。
  可选 corner_treatments 指定特定角点改用镜像折角（_mirror_point：缝份翻折后
  与裁片重合，机头内缝顶点 bottom×side 与后中底角 bottom×cb 斜角用之；直角退化即 miter）。

依赖方向：cutter -> pieces -> geometry（禁止反向）。
"""

from __future__ import annotations

from collections.abc import Mapping

from .geometry import CubicBezier, LineSegment, Point, Vector
from .pieces import PieceEdge, PatternPiece
from .params import WaistbandSeamAllowances


# 各语义边的缝份量（§五.3）：方向由边几何的外法向决定，此处只给量。
# sa 鸭子类型：Mapping（如机头 {top,bottom,cb,side}）-> .get(name,0.0)；
#   WaistbandSeamAllowances 等命名属性对象 -> getattr(name,0.0)
#   （其字段名即边名 top/bottom/left_end/right_end）。未知边名返回 0（折线边不外扩）。
def _sa_amount(name: str, sa: "Mapping[str, float] | WaistbandSeamAllowances") -> float:
    if isinstance(sa, Mapping):
        return float(sa.get(name, 0.0))
    return float(getattr(sa, name, 0.0))


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
    """应用缩水（§五.2）：x·(1+warp)、y·(1+weft) 仿射缩放。

    两个参数语义为**沿裁片局部 X/Y 轴**的缩水率（形参命名 warp/weft 仅为腰头
    长向=经的默认场景）；当裁片经向方向不同（如腰头宽向=经）时，由调用方把面料
    经/纬率换序后传入（见 flows/waistband_flow.build_waistband）。
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


def _offset_edge_points(edge: PieceEdge,
                        sa: "Mapping[str, float] | WaistbandSeamAllowances"
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


def _mirror_point(p: Point, t_a: Vector, t_b: Vector,
                  sa_a: float, sa_b: float) -> Point | None:
    """角点 p 处镜像折角：侧缝缝份边界线取原侧缝切线关于底边缝折线垂线的
    轴对称镜像，再与底边缝份边界相交（机头裁片.md §镜像折角）。

    底边缝份沿底边（方向 t_a）车缝后向上/下翻折，翻折轴即底边缝折线 t_a，其垂线
    n_a = t_a.perpendicular() 为对称轴。侧缝缝份边界线的**倾角**取原侧缝切线 t_b
    关于 n_a 的镜像 t_b' = 2(t_b·n_a)n_a − t_b（仅改方向，锚点仍 off_b）——翻折后
    缝份边缘恰与裁片轮廓重合。直角角点 t_b' = t_b（向量与其平行轴的镜像不变），
    退化即 miter；仅斜角（如机头侧缝倾角）才与 miter 相异。镜像线与底边缝份边界
    平行时返回 None，调用方回退 miter。
    """
    n_a = t_a.perpendicular()
    n_b = t_b.perpendicular()
    off_a = p + n_a.scale(sa_a)
    off_b = p + n_b.scale(sa_b)
    k = 2.0 * (t_b.dx * n_a.dx + t_b.dy * n_a.dy)
    t_b_m = Vector(n_a.dx * k - t_b.dx, n_a.dy * k - t_b.dy)
    d = off_b - off_a
    det = t_a.dx * t_b_m.dy - t_a.dy * t_b_m.dx
    if abs(det) < 1e-9:
        return None
    s = (d.dx * t_b_m.dy - d.dy * t_b_m.dx) / det
    return off_a + t_a.scale(s)


def add_seam_allowance(piece: PatternPiece,
                       sa: "Mapping[str, float] | WaistbandSeamAllowances",
                       corner_treatments: "Mapping[tuple[str, str], str] | None" = None
                       ) -> PatternPiece:
    """各边按独立缝份沿外法向偏移生成毛样（§五.3，真法向 offset + miter 角）。

    基底为 shrunk_edges（无缩水时退化为 net_edges）。各边点序列沿外法向偏移；
    相邻异名边角点 p 处取两偏移边切线延伸交点（miter）连接——弯腰头弧端缝份
    顺曲线斜出、直角边 miter=外角点（直腰头矩形角不变）。切线平行时回退阶梯角
    （外角点 = p + n_a·sa_a + n_b·sa_b）。同名边（后中处上下口分段）平滑相接。
    毛样刀口 = 缩水后刀口（刀口标缝合线，缝份另裁）。

    sa 鸭子类型：Mapping（机头等边名→缝份映射）或 WaistbandSeamAllowances
    （字段名即边名）；详见 _sa_amount。

    corner_treatments：可选 {(折线边, 被镜像边): 算法名}，指定特定异名边角点改用
    非 miter 折角。**键首元素 = 缝份翻折的折线边**（如底边 bottom），次元素 = 被镜像
    边（如侧缝 side / 后中 cb）。mirror 非对称：角点在 cutter 序可能以任一顺序出现，
    故两种顺序的键都查；逆序命中时折线边 = 下边，_mirror_point 形参须交换（t_a/sa_a
    传折线边、t_b/sa_b 传被镜像边）。目前支持 ``"mirror"``（_mirror_point，缝份翻折
    重合）；未列出或列其它值仍走 miter。机头内缝顶点（bottom, side）与后中底角
    （bottom, cb）用 mirror 使相邻缝份翻折后与裁片重合；直角角点 mirror 退化即 miter，
    故仅斜角相异。
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
        # mirror 非对称：键 (折线边, 被镜像边)，首元素为翻折折线边。角点在 cutter
        # 序可能以 (本边,下边) 或其逆序出现，两种键都查；逆序命中则折线边=下边，
        # _mirror_point 形参交换（t_a/sa_a 传下边=折线、t_b/sa_b 传本边=被镜像）。
        ct = corner_treatments or {}
        treatment = ct.get((edge.name, nxt.name))
        fold_is_edge = True
        if treatment is None:
            treatment = ct.get((nxt.name, edge.name))
            fold_is_edge = False
        if treatment == "mirror":
            if fold_is_edge:
                miter = _mirror_point(corner, t_a, t_b, sa_a, sa_b)
            else:
                miter = _mirror_point(corner, t_b, t_a, sa_b, sa_a)
            if miter is None:               # 镜像退化（平行）回退 miter
                miter = _miter_point(corner, t_a, t_b, sa_a, sa_b)
        else:
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

    notes = piece.notes + (_sa_notes(sa),)
    return piece.with_gross(tuple(poly), tuple(base_notches), notes)


def _sa_notes(sa: "Mapping[str, float] | WaistbandSeamAllowances") -> str:
    """缝份记录串（按 sa 内容泛化）：Mapping 列 key:value，WSA 用中文边名。"""
    if isinstance(sa, Mapping):
        items = ", ".join(f"{k} {v}" for k, v in sa.items())
        return f"缝边：{items}"
    # WaistbandSeamAllowances：保留原有中文边名口径
    return (f"缝边：上口 {sa.top} / 下口 {sa.bottom} / "
            f"左端 {sa.left_end} / 右端 {sa.right_end}")
