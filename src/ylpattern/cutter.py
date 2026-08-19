"""裁切层：净样 -> 缩水 -> 缝边（腰头裁片.md §五）。

apply_shrinkage  仿射缩放（经/纬），保持贝塞尔性，刀口同步。
add_seam_allowance  各边按独立缝份沿**外法向**偏移（曲线逐点真法向 offset，
  直线=轴向偏移）；相邻异名边角点取两偏移边切线延伸的交点（miter）连接——
  弯腰头弧线端缝份顺曲线斜出（不再轴对方直角折），直角边 miter 即外角点
  （=原阶梯角，直腰头矩形不变）。同名边（如后中处上下口分段）平滑相接无角点。
  普通 miter 角有尖角限长 miter_limit（默认 1.5）：锐角交点距角点超 max(sa)×
  本值时回退阶梯角（miter 长 = sa/sin(θ/2) 随角变锐无界增长，不限则长尖刺）。
  可选 corner_treatments 指定特定角点改用镜像折角（_mirror_point：缝份翻折后
  与裁片重合，机头内缝顶点 bottom×side 与后中底角 bottom×cb 斜角用之；直角退化即 miter）、
  或不限长自然尖角（"miter"：工艺指定的尖角跟随净样曲线按参数方程多项式自然外推相交，
  绕过 miter_limit 限长——限长是防偶发尖刺的兜底，指定角的尖角是目标形态本身，如前片裆尖）。
可选 hem 指定一条边走袋口折边构造（HemTreatment，后贴袋裁片.md §3/§4）：
  折边自毛样外侧缝边线起翻——锚点 P_notch = 袋口净线延长线 ∩ 侧缝缝边线，
  折边线 = 侧缝缝边线关于袋口线的镜像（翻折后与侧缝折边区重合），顶端撇势
  内收成倒梯形（底 = 毛样全宽）。
  （勿自净角起算：翻盖会窄 2×SA_side，盖不住侧缝折边区。）
  §4 对位刀口不在此层：cutter 只产折边几何（T 顶点 / P_notch 毛样角点），
  刀口点与打口方向由调用方 flow 生成（back_patch_flow._top_hem_notches：
  净口两角沿侧缝边/顶部线延长线交毛样外沿共 4 刀，打在缝边上）。

依赖方向：cutter -> pieces -> geometry（禁止反向）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

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
    缩放保持贝塞尔性（控制点同步缩放）；刀口、丝缕线、内部标记线、定位孔
    同步缩放（内部辅助线随主裁片同比例变换，前片裁片.md §3.3）。
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
    smarks = tuple(_scale_geom(g, sx, sy) for g in piece.marks)
    sdrills = tuple(_scale_point(p, sx, sy) for p in piece.drills)
    out = piece.with_shrunk(shrunk, snotches)
    # 丝缕线随缩水更新（with_shrunk 不带 grain，重建一个）
    return PatternPiece(out.name, out.label, out.net_edges, out.notches,
                        sgrain, out.shrunk_edges, out.shrunk_notches,
                        out.gross_polygon, out.gross_notches,
                        out.notes + (f"缩水：经 {warp*100:.1f}% / 纬 {weft*100:.1f}%",)
                        if warp or weft else out.notes,
                        smarks, sdrills)


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
                 sa_a: float, sa_b: float,
                 miter_limit: float = 1.5) -> Point | None:
    """角点 p 处两偏移边切线延伸的交点（法向缝份 miter）。

    本边偏移末端 = p + n_a·sa_a（n_a = t_a.perpendicular()），沿 t_a 前伸；
    下边偏移首端 = p + n_b·sa_b，沿 t_b 后伸；二者交点即 miter。切线平行（含
    同向）时 det≈0 返回 None，调用方回退阶梯角。直角角点 miter 恰 = 外角点。
    miter_limit：尖角限长——交点距角点超过 max(sa_a,sa_b)×本值（锐角 θ 的
    miter 长 = sa/sin(θ/2) 无界增长）时返回 None 回退阶梯角，避免长尖刺
    （阶梯突出 ≈ sa·√(2−2cosθ) 有界）。1.5 = 内角约 84° 以下转阶梯；直角
    角点 1.414·sa 不受影响。
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
    miter = off_a + t_a.scale(s)
    if miter.distance_to(p) > miter_limit * max(sa_a, sa_b):
        return None
    return miter


def _mirror_point(p: Point, t_a: Vector, t_b: Vector,
                  sa_a: float, sa_b: float) -> Point | None:
    """角点 p 处镜像折角（真反折角）：被镜像边缝份边界**整条线**关于折线边
    净缝线（过 p、方向 t_a）轴对称后，与折线边缝份边界相交（机头裁片.md
    §镜像折角；后片裁片.md §2 反折角防缺角缺肉）。

    折线边缝份沿折线车缝后翻折，翻折轴 = 折线边净缝线本身。把被镜像边缝份
    边界线整条关于该轴轴对称（R(v) = 2(v·t̂a)t̂a − v：锚点 off_b -> p +
    sa_b·R(n_b)、方向 t_b -> R(t_b)），与折线边缝份边界（过 off_a、方向
    t_a）交于 M——则 M 翻折后的像恰落在被镜像边毛缝边界上（像距被镜像边
    净线 = sa_b），翻折边缘与裁片轮廓严丝合缝、不缺肉。仅镜像方向、锚点
    不动（旧实现）在斜角处翻折落点距净线 sa_b·|cos∠(n_b,t_a)| < sa_b，
    短缺 |缺量| 有界但真实存在。直角角点 n_b ∥ t_a，R(n_b) = n_b 锚点不动、
    R(t_b) = −t_b 同线，退化即 miter；仅斜角（后浪裆尖约 65°、机头侧缝
    倾角）才与 miter 相异。镜像线与折线边缝份边界平行时返回 None，调用方
    回退 miter。
    """
    ta = t_a.normalized()
    n_a = t_a.perpendicular()
    n_b = t_b.perpendicular()
    off_a = p + n_a.scale(sa_a)
    # 被镜像边缝份边界整条关于折线（过 p、方向 t_a）轴对称：锚点与方向同步镜像
    kb = 2.0 * (n_b.dx * ta.dx + n_b.dy * ta.dy)
    kt = 2.0 * (t_b.dx * ta.dx + t_b.dy * ta.dy)
    n_b_m = Vector(ta.dx * kb - n_b.dx, ta.dy * kb - n_b.dy)
    t_b_m = Vector(ta.dx * kt - t_b.dx, ta.dy * kt - t_b.dy)
    off_b_m = p + n_b_m.scale(sa_b)
    d = off_b_m - off_a
    det = t_a.dx * t_b_m.dy - t_a.dy * t_b_m.dx
    if abs(det) < 1e-9:
        return None
    s = (d.dx * t_b_m.dy - d.dy * t_b_m.dx) / det
    return off_a + t_a.scale(s)


def _axis_cross(p: Point, t_p: Vector, c: Point, t_c: Vector) -> Point | None:
    """过 p 沿 t_p 的直线与翻折轴（过 c、方向 t_c）的交点，仅在交点位于 p
    前方（s > 1e-6）时返回：被镜像边缝份边界延伸至翻折轴的穿越点 X。X 在
    轴上（与角点等高），X -> M 段恰沿镜像线，翻折后整段像落在被镜像边毛缝
    边界上；被镜像边缝边线也因此画到角点等高处（自然端点 = 角点法向投影
    点，因倾角低 sa·sin∠，直接连弦会缺角部三角料）。平行（无交点）或交点
    在后方返回 None，调用方保持旧直连行为。"""
    det = t_p.dx * t_c.dy - t_p.dy * t_c.dx
    if abs(det) < 1e-9:
        return None
    d = c - p
    s = (d.dx * t_c.dy - d.dy * t_c.dx) / det
    if s <= 1e-6:
        return None
    return p + t_p.scale(s)


def _extrapolate_offset(g: LineSegment | CubicBezier, at_end: bool,
                        sa: float, max_dist: float) -> list[Point]:
    """外延偏移：多项式外推贝塞尔曲线（t>1 或 t<0），自然延续原曲线的加速度与曲率。
    避免固定圆弧曲率导致的平直或鼓包，实现打版软件原生的顺滑交接。"""
    ds = 0.5  # 采样步长（0.5单元格/毫米），保证打点足够细腻以求得精确交点
    steps = max(10, int(max_dist / ds))
    
    if isinstance(g, LineSegment):
        t_dir = (g.b - g.a).normalized()
        if t_dir.length == 0.0:
            t_dir = Vector(1.0, 0.0)
        n = t_dir.perpendicular()
        bp = g.b if at_end else g.a
        travel = t_dir if at_end else t_dir.scale(-1.0)
        return [bp + travel.scale(k * ds) + n.scale(sa) for k in range(steps + 1)]

    # 对于贝塞尔，基于端点速度估算参数 t 的步长 dt
    v0 = g.tangent_at(1.0 if at_end else 0.0)
    speed = v0.length
    if speed < 1e-6:
        speed = 100.0
    dt = (ds / speed) * (1.0 if at_end else -1.0)
    
    pts = []
    t = 1.0 if at_end else 0.0
    for _ in range(steps + 1):
        mt = 1.0 - t
        
        # 精确计算外推多项式坐标 B(t)
        p_x = (mt**3)*g.p0.x + 3*(mt**2)*t*g.p1.x + 3*mt*(t**2)*g.p2.x + (t**3)*g.p3.x
        p_y = (mt**3)*g.p0.y + 3*(mt**2)*t*g.p1.y + 3*mt*(t**2)*g.p2.y + (t**3)*g.p3.y
        
        # 精确计算外推处的一阶导数 B'(t) 以获取最真实的法向
        d1x = 3*(mt**2)*(g.p1.x-g.p0.x) + 6*mt*t*(g.p2.x-g.p1.x) + 3*(t**2)*(g.p3.x-g.p2.x)
        d1y = 3*(mt**2)*(g.p1.y-g.p0.y) + 6*mt*t*(g.p2.y-g.p1.y) + 3*(t**2)*(g.p3.y-g.p2.y)
        
        sp = (d1x**2 + d1y**2)**0.5
        if sp > 1e-12:
            nx, ny = -d1y/sp, d1x/sp
        else:
            nx, ny = 0.0, 0.0
            
        pts.append(Point(p_x + nx*sa, p_y + ny*sa))
        t += dt
        
    return pts


def _seg_cross(a: Point, b: Point, c: Point, d: Point) -> Point | None:
    ex, ey = b.x - a.x, b.y - a.y
    fx, fy = d.x - c.x, d.y - c.y
    det = ex * fy - ey * fx
    if abs(det) < 1e-12:
        return None
    rx, ry = c.x - a.x, c.y - a.y
    s = (rx * fy - ry * fx) / det
    u = (rx * ey - ry * ex) / det
    if -1e-12 <= s <= 1.0 + 1e-12 and -1e-12 <= u <= 1.0 + 1e-12:
        return Point(a.x + s * ex, a.y + s * ey)
    return None


def _natural_join_sharp(g_a: LineSegment | CubicBezier,
                        g_b: LineSegment | CubicBezier,
                        sa_a: float, sa_b: float
                        ) -> tuple[Point, ...] | None:
    """两边通过贝塞尔多项式自然外延求交，返回完整的圆顺连线轨迹防折角。"""
    # 放宽外延搜索距离，确保能在远端相交（留足安全余量）
    max_len = 4.0 * max(sa_a, sa_b) + 20.0
    
    # 贝塞尔参数方程外推能够完美延续曲线本身的张力、加速度和真实弧度
    A = _extrapolate_offset(g_a, True, sa_a, max_len)
    B = _extrapolate_offset(g_b, False, sa_b, max_len)
    
    hit = None
    for i in range(len(A) - 1):
        for j in range(len(B) - 1):
            x = _seg_cross(A[i], A[i + 1], B[j], B[j + 1])
            if x is not None:
                hit = (i, j, x)
                break
        if hit is not None:
            break
            
    if hit is None:
        return None
        
    i, j, x = hit
    
    # 拼接平滑轨迹：A的末端外延 -> 自然滑向交点x -> 顺滑切入B的起端外延
    res = []
    res.extend(A[1:i+1])
    res.append(x)
    res.extend(B[1:j+1][::-1]) 
    return tuple(res)


@dataclass(frozen=True)
class HemTreatment:
    """袋口折边构造参数（后贴袋裁片.md §3/§4）。

    edge  折边边名（袋口，如 "top"，须在裁片边名中唯一）；
    taper 撇势（≤0；折边顶点沿袋口方向向内平移 |本值|，防折后毛边外露）。
    毛样折边链：P_notch_a -> T_a ->（顶边平行袋口距 sa_top）-> T_b ->
    P_notch_b；锚点 P_notch = 侧缝缝边线与袋口净线延长线的交点（由角点
    miter 时折边侧 sa 传 0 自动得出；作毛样角点锚定折边起翻，亦是 flow 层
    袋口顶部线延长刀口的落点，§4）——折边自毛样外侧
    缝边线起翻，翻盖全宽 = 毛样宽，翻折后恰与侧缝折边区重合；自净角起算
    翻盖会窄 2×SA_side，侧缝处盖不住缺量。
    前提（_hem_feasible 预扫描，不满足整条降级常规法向放缝）：袋口为直线、
    前后相邻异名、sa_top > 0、两侧边与袋口不近平行。
    """
    edge: str
    taper: float = 0.0


def _dot(a: Vector, b: Vector) -> float:
    return a.dx * b.dx + a.dy * b.dy


def _mirror_dir(e: Vector, n: Vector) -> Vector:
    """镜像方向：袋内切线 e 关于袋口线（法向 n）的镜像 e − 2(e·n)n（单位向量）。

    折边沿此方向上行，翻折（折轴 = 袋口线）后恰与袋身侧边重合（§3.2）。"""
    k = -2.0 * _dot(e, n)
    return Vector(e.dx + n.dx * k, e.dy + n.dy * k)


def _hem_feasible(edge: PieceEdge, prev: PieceEdge, nxt: PieceEdge,
                  sa: "Mapping[str, float] | WaistbandSeamAllowances") -> bool:
    """折边构造可行性（预扫描与主循环共用同一判据，防两处判据漂移断链）。

    袋口须为直线（弧袋口无镜像轴）且非零长、前后相邻异名（同名平滑续接无
    角点可做台阶）、折边缝份 > 0、两侧边切线与袋口法向分量 |E·N| > 1e-6
    （侧边与袋口近平行时折线/刀口无界远飞，且 miter det≈0 同源退化）。
    """
    if not isinstance(edge.geom, LineSegment):
        return False
    if edge_length(edge.geom) <= 1e-9:
        return False
    if prev.name == edge.name or nxt.name == edge.name:
        return False
    if _sa_amount(edge.name, sa) <= 0.0:
        return False
    n_hat = _unit_tangent(edge.geom, False).perpendicular()
    e_a = _unit_tangent(prev.geom, True).scale(-1.0)   # a 角处指向袋内
    e_b = _unit_tangent(nxt.geom, False)               # b 角处指向袋内
    return (abs(_dot(e_a, n_hat)) > 1e-6
            and abs(_dot(e_b, n_hat)) > 1e-6)


def _hem_points(a: Point, b: Point, prev: PieceEdge, nxt: PieceEdge,
                sa, sa_top: float, taper: float) -> tuple[Point, Point]:
    """袋口折边撇势顶点 (T_a, T_b)（后贴袋裁片.md §3，锚点 = P_notch）。

    折边自毛样外侧缝边线起翻：锚点 P_notch = 袋口净线延长线 ∩ 侧缝缝边线
    （侧边沿外法向偏移 sa_side，§4 交点；与角点 miter 同一口径复用
    _miter_point 折边侧 sa=0），自 P_notch 沿镜像方向（_mirror_dir = 侧缝
    缝边线关于袋口线的镜像方向）上行至距袋口线 sa_top 处得 M，再沿袋口
    向内平移 |taper| 得 T；袋口缝边轮廓为倒梯形（底 = 毛样全宽
    P_notch_a→P_notch_b，顶 = 平行袋口距 sa_top、两端内收 |taper|）。
    自净角起算翻盖会窄 2×SA_side，侧缝折边区盖不住缺量。
    """
    t_h = (b - a).normalized()
    n_hat = t_h.perpendicular()          # 袋口外法向（shoelace<0 朝外=折边侧）
    t_prev = _unit_tangent(prev.geom, True)
    t_nxt = _unit_tangent(nxt.geom, False)
    p_a = _miter_point(a, t_prev, t_h, _sa_amount(prev.name, sa), 0.0,
                       miter_limit=float("inf"))
    p_b = _miter_point(b, t_h, t_nxt, 0.0, _sa_amount(nxt.name, sa),
                       miter_limit=float("inf"))
    if p_a is None:                      # 近平行防御（预扫描已排除，兜底回净角）
        p_a = a
    if p_b is None:
        p_b = b
    d_a = _mirror_dir(t_prev.scale(-1.0), n_hat)
    d_b = _mirror_dir(t_nxt, n_hat)
    m_a = p_a + d_a.scale(sa_top / _dot(d_a, n_hat))
    m_b = p_b + d_b.scale(sa_top / _dot(d_b, n_hat))
    shift = abs(taper)
    return m_a + t_h.scale(shift), m_b + t_h.scale(-shift)


def add_seam_allowance(piece: PatternPiece,
                       sa: "Mapping[str, float] | WaistbandSeamAllowances",
                       corner_treatments: "Mapping[tuple[str, str], str] | None" = None,
                       miter_limit: float = 1.5,
                       hem: HemTreatment | None = None
                       ) -> PatternPiece:
    """各边按独立缝份沿外法向偏移生成毛样（§五.3，真法向 offset + miter 角）。

    基底为 shrunk_edges（无缩水时退化为 net_edges）。各边点序列沿外法向偏移；
    相邻异名边角点 p 处取两偏移边切线延伸交点（miter）连接——弯腰头弧端缝份
    顺曲线斜出、直角边 miter=外角点（直腰头矩形角不变）。切线平行时回退阶梯角
    （外角点 = p + n_a·sa_a + n_b·sa_b）。同名边（后中处上下口分段）平滑相接。
    反射角（内角 >180°，边界谷底）时 miter 交点落在两边偏移曲线途中，偏移链
    越过交点的采样尾/头部点被裁去（防两偏移链角部自交，门襟双排对折线顶端
    两腰弧接缝即此；凸角交点在偏移端点之外，裁剪条件自然不触发，行为不变）。
    miter_limit：尖角限长，普通 miter 角点交点距角点超 max(sa)×本值时同样回退
    阶梯角（锐角 miter 长 = sa/sin(θ/2) 无界增长，袋布袋底×侧缝约 71° 角在
    side 缝份调大时长成尖刺，即此坑）；mirror 角（工艺翻折重合）不受限。
    毛样刀口 = 缩水后刀口（刀口标缝合线，缝份另裁）。

    sa 鸭子类型：Mapping（机头等边名→缝份映射）或 WaistbandSeamAllowances
    （字段名即边名）；详见 _sa_amount。

    corner_treatments：可选 {(折线边, 被镜像边): 算法名}，指定特定异名边角点
    改用非 miter 折角。**键首元素 = 缝份翻折的折线边**（如底边 bottom），次元素 =
    被镜像边（如侧缝 side / 后中 cb）。mirror 非对称：角点在 cutter 序可能以任一顺序
    出现，故两种顺序的键都查；逆序命中时折线边 = 下边，_mirror_point 形参须交换
    （t_a/sa_a 传折线边、t_b/sa_b 传被镜像边）。目前支持 ``"mirror"``（_mirror_point，
    缝份翻折重合）与 ``"miter"``（不限长自然尖角——工艺指定的尖角跟随净样曲线
    按参数方程多项式自然外推相交，绕过 miter_limit，如前片裆尖）；
    "miter" 对键序对称。未列出或列其它值仍走限长 miter。
    机头内缝顶点（bottom, side）与后中底角（bottom, cb）用 mirror 使相邻缝份翻折后
    与裁片重合；直角角点 mirror 退化即 miter，故仅斜角相异。

    hem：可选 HemTreatment，指定一条边（袋口）走折边构造（后贴袋裁片.md §3）：
    该边不发常规偏移，改发 [T_a, T_b] 折边顶点（_hem_points：锚点 P_notch =
    袋口净线延长线 ∩ 侧缝缝边线，折边自毛样外侧缝边线起翻、翻盖全宽 = 毛样宽，
    镜像折线 + 撇势内收成倒梯形）；与相邻边的角点 miter 时折边侧 sa 按 0 传，
    交点即锚点 P_notch（作毛样角点，亦是 flow 层袋口顶部线延长刀口的落点，
    §4）——该角为规范指定构造，不限长、不走 corner_treatments。本函数不发
    袋口对位刀口（§4 刀口由调用方 flow 生成，见 back_patch_flow._top_hem_
    notches：净口两角沿侧缝边/顶部线延长线交毛样外沿共 4 刀，打在缝边上）。
    可行性由 _hem_feasible 预扫描统一判定，不可行整条降级常规法向放缝
    （默认 None，现有裁片行为不变）。
    """
    base = piece.shrunk_edges or piece.net_edges
    base_notches = piece.shrunk_notches or piece.notches
    if not base:
        return piece

    n = len(base)
    # 折边可行性预扫描（后贴袋裁片.md §3）：与主循环共用 _hem_feasible 判据，
    # 不可行整条降级常规法向放缝（防"角点已按折边发射、边却常规偏移"断链）
    hem_ok = False
    if hem is not None:
        for j, hedge in enumerate(base):
            if hedge.name == hem.edge:
                hem_ok = _hem_feasible(hedge, base[(j - 1) % n],
                                       base[(j + 1) % n], sa)
                break
    poly: list[Point] = []
    pending_head_trim: tuple[Point, Vector] | None = None
    first_run_len = 0              # 首边偏移链长度（环回角裁头上界）
    for i, edge in enumerate(base):
        nxt = base[(i + 1) % n]
        run_start = len(poly)      # 本边偏移链发射起点（反射角裁尾下界）
        if hem_ok and edge.name == hem.edge:
            # 折边链（§3）：T_a -> T_b；两端锚点 P_notch 由前后角点 miter 发射
            # （折边自毛样外侧缝边线起翻，翻盖全宽 = 毛样宽，拓扑凸链无台阶）
            sa_top = _sa_amount(edge.name, sa)
            t_pt_a, t_pt_b = _hem_points(edge.geom.a, edge.geom.b,
                                         base[(i - 1) % n], nxt,
                                         sa, sa_top, hem.taper)
            for p in (t_pt_a, t_pt_b):
                if not poly or poly[-1] != p:
                    poly.append(p)
        else:
            lead = pending_head_trim
            pending_head_trim = None
            for p in _offset_edge_points(edge, sa):
                # 反射角裁头（见角点段注释）：交点之前的偏移点裁去防自交
                if lead is not None and _dot(p - lead[0], lead[1]) < -1e-9:
                    continue
                if not poly or poly[-1] != p:
                    poly.append(p)
        if i == 0:
            first_run_len = len(poly)
        # 角点：与下一条异名边 -> miter（或平行回退阶梯）
        if nxt.name == edge.name:
            continue
        hem_a = hem_ok and edge.name == hem.edge   # 本边为折边边
        hem_b = hem_ok and nxt.name == hem.edge    # 下边为折边边
        sa_a = 0.0 if hem_a else _sa_amount(edge.name, sa)
        sa_b = 0.0 if hem_b else _sa_amount(nxt.name, sa)
        if sa_a == 0.0 and sa_b == 0.0:
            continue
        corner = _edge_end(edge.geom)       # 角点（本边末端 = 下边首端）
        t_a = _unit_tangent(edge.geom, True)
        t_b = _unit_tangent(nxt.geom, False)
        if hem_a or hem_b:
            # P_notch（§3 折边锚点）：折边侧缝份边界退化为袋口净线本身
            # （off = 角点），与相邻侧缝缝边线的交点即台阶角。规范指定构造
            # 而非偶发尖刺（长度 = sa/sin∠ 有界，近平行已被预扫描排除），
            # 不限长、不走 corner_treatments；作毛样角点发射，亦是 flow 层
            # 顶部线延长刀口的落点（§4，back_patch_flow._top_hem_notches）。
            miter = _miter_point(corner, t_a, t_b, sa_a, sa_b,
                                 miter_limit=float("inf"))
            if miter is not None and (not poly or miter != poly[-1]):
                poly.append(miter)
            continue
        # mirror 非对称：键 (折线边, 被镜像边)，首元素为翻折折线边。角点在 cutter
        # 序可能以 (本边,下边) 或其逆序出现，两种键都查；逆序命中则折线边=下边，
        # _mirror_point 形参交换（t_a/sa_a 传下边=折线、t_b/sa_b 传本边=被镜像）。
        ct = corner_treatments or {}
        treatment = ct.get((edge.name, nxt.name))
        fold_is_edge = True
        if treatment is None:
            treatment = ct.get((nxt.name, edge.name))
            fold_is_edge = False
        cross = None
        if treatment == "mirror":
            if fold_is_edge:
                miter = _mirror_point(corner, t_a, t_b, sa_a, sa_b)
            else:
                miter = _mirror_point(corner, t_b, t_a, sa_b, sa_a)
            if miter is None:               # 镜像退化（平行）回退 miter
                miter = _miter_point(corner, t_a, t_b, sa_a, sa_b)
            elif fold_is_edge and sa_b > 0.0:
                # 真反折角补全：被镜像边 = 下边，其缝份边界自偏移起点沿本边
                # 方向延伸至翻折轴（折线边净缝切线过角点）穿越点 X
                off_b0 = corner + t_b.perpendicular().scale(sa_b)
                cross = _axis_cross(off_b0, t_b, corner, t_a)
            elif not fold_is_edge and sa_a > 0.0:
                # 被镜像边 = 本边：其缝份边界自偏移链头沿走向延伸至翻折轴
                cross = _axis_cross(poly[-1], t_a, corner, t_b)
        elif treatment == "miter":
            # 不限长自然尖角（前片裆尖等）：尖角是该角的工艺目标形态（缝边跟随净样
            # 曲线自然延伸交接），非偶发尖刺，绕过 miter_limit。
            # 接收多项式外推返回的整段平滑轨迹防折角
            join_path = _natural_join_sharp(edge.geom, nxt.geom, sa_a, sa_b)
            if join_path is not None:
                for jp in join_path:
                    if not poly or jp != poly[-1]:
                        poly.append(jp)
                continue  # 轨迹已完整覆盖该角点，直接 continue 处理下一条边
            else:
                miter = _miter_point(corner, t_a, t_b, sa_a, sa_b, float("inf"))
        else:
            miter = _miter_point(corner, t_a, t_b, sa_a, sa_b, miter_limit)
        if miter is not None:
            # 反射角裁剪：内角 >180°（边界谷底，如门襟双排对折线顶端两腰弧
            # 接缝）时 miter 交点落在两边偏移曲线**途中**，偏移链越过交点的
            # 采样尾/头部点在交点另一侧——不裁则两偏移链在角部自交（DXF 目检
            # 缝边多线交错即此）。裁尾：本边链中沿走向越过交点的尾部点；
            # 裁头：下边链起点侧交点之前的头部点（环回角在循环后就地裁首边）。
            # 凸角交点在两边偏移端点之外，两条件自然不触发，行为不变；
            # sa=0 的净样点链不参与（裁剪只对真偏移链有意义）。
            if sa_a > 0.0:
                while (len(poly) > run_start
                       and _dot(poly[-1] - miter, t_a) > 1e-9):
                    poly.pop()
            # 被镜像边 = 下边的 mirror 角：头部裁剪/环回裁剪基准改 X（X 沿
            # t_b 在 M 后方，按 M 裁会漏裁 X 与 M 之间的采样点、与补插的 X
            # 成折返乱序）；其余角点无 X，基准仍为 M，行为不变
            head_ref = cross if (cross is not None and fold_is_edge) else miter
            if sa_b > 0.0:
                if i + 1 < n:
                    pending_head_trim = (head_ref, t_b)
                else:              # 环回角：下一条是首边，偏移链已在 poly 头部
                    k = 0
                    while (k < first_run_len and k < len(poly) - 1
                           and _dot(poly[k] - head_ref, t_b) < -1e-9):
                        k += 1
                    if k:
                        del poly[:k]
            if (cross is not None and not fold_is_edge
                    and cross != poly[-1] and cross != miter):
                poly.append(cross)      # 被镜像边 = 本边：X 插在 M 之前
            if miter != poly[-1]:
                poly.append(miter)
            if cross is not None and fold_is_edge and cross != poly[-1]:
                poly.append(cross)      # 被镜像边 = 下边：X 插在 M 之后
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
    if hem_ok:
        notes = notes + (f"袋口折边：镜像折线+撇势 {hem.taper}"
                         "（后贴袋裁片.md §3；§4 袋口刀口由 flow 层生成）",)
    # 毛样刀口 = 缩水后刀口（方向 None 出口层自推）；hem 折边不发刀口
    return piece.with_gross(tuple(poly), tuple(base_notches), notes)


def _sa_notes(sa: "Mapping[str, float] | WaistbandSeamAllowances") -> str:
    """缝份记录串（按 sa 内容泛化）：Mapping 列 key:value，WSA 用中文边名，
    其他命名属性缝份 dataclass（袋贴/贴袋…）泛化列出 字段名 值。"""
    if isinstance(sa, Mapping):
        items = ", ".join(f"{k} {v}" for k, v in sa.items())
        return f"缝边：{items}"
    if isinstance(sa, WaistbandSeamAllowances):
        # 保留原有中文边名口径
        return (f"缝边：上口 {sa.top} / 下口 {sa.bottom} / "
                f"左端 {sa.left_end} / 右端 {sa.right_end}")
    items = ", ".join(f"{k} {v}" for k, v in vars(sa).items())
    return f"缝边：{items}"