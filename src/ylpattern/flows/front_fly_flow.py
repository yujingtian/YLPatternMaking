"""独立门襟裁片流程：净样提取 -> 缩水 -> 缝边 -> 刀口投影（门襟裁片.md §2、§4）。

build_front_fly(main_ctx) 从整版 ctx 提取已上版的独立门襟净样（门襟绘制.md §5，
front.fly_sep_* 叠画于前片），产出两片独立裁片：
  - 单排（单层，§2）：原样提取净样轮廓（腰头线子弧 + 外缘 + 底角 J 型圆弧 +
    底边 + 内边），几何零改动。
  - 双排（对折，§4）：轮廓修正后轴对称展开——去除底角 J 弧，外缘重构为直线、
    强制与内边完全平行且绝对等长（O,T,E,S 成平行四边形），底端一条直线闭合，
    顶端保留腰头线弧；再以内边为对称轴（对折线）镜像展开成完整闭合净样。

工序红线（§1）：提取净样 -> 缩水放缩（主面料经纬，None=回退全局）-> 缩水后
缝边（缝份宽度为绝对值，先缝边后缩水会按比例缩小致止口跑偏）-> 刀口沿外法向
投影至毛样外沿（锚定净样边缘拼接位、打口打在缝边上，§2 Step3 / §4 Step4；
双排对折线两端 O/S 刀口例外：沿对折轴线向外投影并与中心对称线绝对共线，供
车间直接沿直线对折）；丝缕线竖直 = 经向，与前/后片一致（§1 关键约束，防洗水
猫须扭曲）。自含裁片，非 FlowRunner 编排（同 front_pocket_flow /
front_pouch_flow 口径）。
"""

from __future__ import annotations

from collections.abc import Mapping

from ..cutter import add_seam_allowance, apply_shrinkage
from ..draft import DraftContext
from ..geometry import CubicBezier, LineSegment, Point, Vector
from ..pieces import PatternPiece, PieceEdge


# ---------- 几何小工具（与 front_pocket_flow / front_pouch_flow 同款）----------

def _to_local_geom(g: LineSegment | CubicBezier, origin: Point
                   ) -> LineSegment | CubicBezier:
    """主版坐标 -> 裁片局部坐标：关于过 origin 的水平线反射
    local=(x−origin.x, origin.y−y)。X 不翻（保侧缝在左、前浪在右，避免镜像）、
    Y 翻（主版 Y 向上 -> 局部 +Y 朝下，腰头在上、裁片向下），与 piece_svg 的
    Y 向下不翻转口径一致。反射反向（det=−1），由 _finish_fly_piece 自定向
    重新正序保 shoelace<0。origin 取裁片最高端（门襟原点 O）。"""
    def f(p: Point) -> Point:
        return Point(p.x - origin.x, origin.y - p.y)
    if isinstance(g, LineSegment):
        return LineSegment(f(g.a), f(g.b))
    return CubicBezier(f(g.p0), f(g.p1), f(g.p2), f(g.p3))


def _to_local_point(p: Point, origin: Point) -> Point:
    return Point(p.x - origin.x, origin.y - p.y)


def _reverse_geom(g: LineSegment | CubicBezier) -> LineSegment | CubicBezier:
    """反向几何：直线 a,b->b,a；三次贝塞尔 p0,p1,p2,p3->p3,p2,p1,p0（弧长不变）。"""
    if isinstance(g, LineSegment):
        return LineSegment(g.b, g.a)
    return CubicBezier(g.p3, g.p2, g.p1, g.p0)


def _geom_sample(g: LineSegment | CubicBezier, n: int = 32) -> list[Point]:
    return [g.a, g.b] if isinstance(g, LineSegment) else g.sample(n)


def _signed_area(geoms: list[LineSegment | CubicBezier]) -> float:
    """闭合几何链的 shoelace 符号面积（cutter 外法向要求 < 0，同 yoke 口径）。"""
    pts: list[Point] = []
    for g in geoms:
        pts.extend(_geom_sample(g))
    s, n = 0.0, len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        s += a.x * b.y - b.x * a.y
    return s


def _vertical_grain(net_edges: tuple[PieceEdge, ...]) -> LineSegment:
    """丝缕线：经向 = 大片裤中线垂直方向 = 局部 Y（门襟裁片.md §1 丝缕同步：
    与前/后片经向绝对一致）。竖向贯穿裁片（bbox 中心 x，上下各留 15% 边距），
    同 front_pocket_flow 口径。"""
    xs, ys = [], []
    for e in net_edges:
        for p in _geom_sample(e.geom):
            xs.append(p.x)
            ys.append(p.y)
    cx = (min(xs) + max(xs)) / 2
    y0, y1 = min(ys), max(ys)
    margin = (y1 - y0) * 0.15
    return LineSegment(Point(cx, y0 + margin), Point(cx, y1 - margin))


def _reflect_point(p: Point, axis_a: Point, axis_b: Point) -> Point:
    """点 p 关于直线 axis_a->axis_b 的轴对称镜像（双排对折轴，门襟裁片.md §4）。

    proj = A + d·((p−A)·d/|d|²) 为 p 在直线上的正投影，镜像 P′ = 2·proj − p。
    """
    d = axis_b - axis_a
    if d.length == 0:
        return p
    ap = p - axis_a
    t = (ap.dx * d.dx + ap.dy * d.dy) / (d.dx * d.dx + d.dy * d.dy)
    proj = axis_a + d.scale(t)
    return proj + (proj - p)                  # 2·proj − p（Point + Vector）


def _reflect_geom(g: LineSegment | CubicBezier,
                  axis_a: Point, axis_b: Point) -> LineSegment | CubicBezier:
    """直线/贝塞尔关于直线的轴对称镜像（控制点同步镜像，保贝塞尔性）。"""
    if isinstance(g, LineSegment):
        return LineSegment(_reflect_point(g.a, axis_a, axis_b),
                           _reflect_point(g.b, axis_a, axis_b))
    return CubicBezier(_reflect_point(g.p0, axis_a, axis_b),
                       _reflect_point(g.p1, axis_a, axis_b),
                       _reflect_point(g.p2, axis_a, axis_b),
                       _reflect_point(g.p3, axis_a, axis_b))


# ---------- 刀口法向投影（§2 Step3 / §4 Step4，与前/后片同款 flow 私有实现）----------

def _sa_for(name: str, sa) -> float:
    """语义边缝份（与 cutter._sa_amount 同口径的鸭子类型分派）。"""
    if isinstance(sa, Mapping):
        return float(sa.get(name, 0.0))
    return float(getattr(sa, name, 0.0))


def _edge_distance_tangent(g: LineSegment | CubicBezier, p: Point
                           ) -> tuple[float, Vector]:
    """点 p 到边 geom 的（距离, 单位切线）：直线参数投影 clamp、贝塞尔 64
    采样最近点（切线取采样点处，与 cutter 采样口径同级精度）。"""
    if isinstance(g, LineSegment):
        v = g.b - g.a
        if v.length == 0:
            return p.distance_to(g.a), Vector(1.0, 0.0)
        t = max(0.0, min(1.0, ((p.x - g.a.x) * v.dx + (p.y - g.a.y) * v.dy)
                       / (v.dx * v.dx + v.dy * v.dy)))
        q = g.a + v.scale(t)
        return p.distance_to(q), v.normalized()
    pts = g.sample(64)
    best_i, best_d = 0, float("inf")
    for i, q in enumerate(pts):
        d = p.distance_to(q)
        if d < best_d:
            best_i, best_d = i, d
    return best_d, g.tangent_at(best_i / 64).normalized()


def _notch_normal(edges: tuple[PieceEdge, ...], p: Point, sa
                  ) -> tuple[Vector, float]:
    """刀口 p 的（外法向, 所在边缝份）：与 p 距离 ≤1e-6 的边为命中——角点
    命中多条边时**不取法向均值（角平分），按斜率取 |dy| 最大的纵向主边外
    法向**：均值恰把刀口投到缝边角顶点上（凸角 = miter 顶点、反射角 = 裁剪
    交点），角顶点两侧折线不共线、ET 按裁切折线顶点吸附挂刀口符号时切线
    方向无法判定，渲染成十字孤立点（2026-08 DXF 报障）；主边外法向把刀口
    落在该边缝边线段上（段中，或与 miter 共线的顶点，切线唯一可判）。直角
    角点（内边×底边 S、外缘×底边 E）取到纵向边；对折线端点 O/S 不经此函数
    ——_project_notches 的 axis_pair 沿对折轴线投影（2026-08 口径：与中心
    对称线绝对共线）。无命中回退全链最近边（数值兜底）。shoelace<0 走向
    切线逆时针 90° 即朝外，与 cutter 外扩同约定。"""
    scored = [(*_edge_distance_tangent(e.geom, p), e.name) for e in edges]
    near = [s for s in scored if s[0] <= 1e-6]
    if not near:
        near = [min(scored, key=lambda s: s[0])]
    if len(near) > 1:
        _d, tan, name = max(near, key=lambda s: abs(s[1].dy))
        return tan.perpendicular(), _sa_for(name, sa)
    nx = ny = 0.0
    for _d, tan, _name in near:
        n = tan.perpendicular()
        nx += n.dx
        ny += n.dy
    normal = Vector(nx, ny)
    _, ref_tan, ref_name = min(near, key=lambda s: s[0])
    if normal.length <= 1e-12:            # 对向法向相消（数值奇异）回退单边
        normal = ref_tan.perpendicular()
    return normal.normalized(), _sa_for(ref_name, sa)


def _project_notch(p: Point, n: Vector, sa_amt: float,
                   poly: tuple[Point, ...]) -> Point:
    """刀口 p 沿外法向 n 的射线与毛样折线的最近交点（法向延伸投影）；
    无命中（折线数值开缝）回退法向平移一个缝份。"""
    best_s: float | None = None
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        ex, ey = b.x - a.x, b.y - a.y
        det = ex * n.dy - ey * n.dx
        if abs(det) < 1e-12:
            continue
        rx, ry = a.x - p.x, a.y - p.y
        s = (ex * ry - ey * rx) / det
        u = (n.dx * ry - n.dy * rx) / det
        if s > 1e-9 and -1e-9 <= u <= 1.0 + 1e-9 \
                and (best_s is None or s < best_s):
            best_s = s
    if best_s is None:
        return p + n.scale(sa_amt)
    return p + n.scale(best_s)


def _project_notches(piece: PatternPiece, sa,
                     axis_pair: tuple[int, int] | None = None) -> PatternPiece:
    """净样刀口沿外法向延伸投影到毛样外沿，整体替换 gross_notches（§2 Step3）。

    刀口锚定净样边缘的拼接对位位置（读取前片关键节点：单排内边开深 L 前浪
    对位点、双排对折线两端 O/S 与外缘开深 L 点），打口打在缝边外沿（毛样
    裁切线）——ET 等服装 CAD 按裁切折线顶点吸附挂接刀口符号，净样位刀口不在
    折线上不显示、也无法指导裁床打口。载体边基于缩水后净边（无缩水退化
    净样，与 cutter base 同口径）；缝合线位刀口（shrunk_notches）保留不丢
    信息，piece_svg 三级回退自动取毛样刀口（同前/后片先例）。

    axis_pair（双排对折线两端 O/S 刀口索引，§4 Step4）：两端刀口**放弃
    外法向，沿对折轴线向外延伸投影**（2026-08 用户口径：刀口须与中心对称
    线绝对共线，符合车间直接沿直线对折的工业习惯——主边外法向带前浪斜度
    必然歪斜）。轴向取缩水后刀口对 O->S（无缩水退化净样，与载体边同口径）；
    打口方向（gross_notch_dirs，指向裁片内部）同为轴向、指向对端，出口层
    显式渲染不再按折线切线自推。落点 = 轴线与毛样外沿交点：无缩水时镜像
    对称、轴线恰过缝边顶点（上端反射角裁剪交点、下端凸角 miter 顶点），
    属工艺指定落点；有缩水（各向异性缩放破坏镜像对称）时落顶点旁侧段中。"""
    base = piece.shrunk_edges or piece.net_edges
    notches = piece.shrunk_notches or piece.notches
    if not notches or not piece.gross_polygon:
        return piece
    axis = None
    if axis_pair is not None:
        axis = (notches[axis_pair[1]] - notches[axis_pair[0]]).normalized()
    projected: list[Point] = []
    dirs: list[Vector | None] = [None] * len(notches)
    for k, p in enumerate(notches):
        if axis is not None and k in axis_pair:
            top = k == axis_pair[0]
            outward = axis.scale(-1.0) if top else axis
            projected.append(_project_notch(
                p, outward, _sa_for("top" if top else "bottom", sa),
                piece.gross_polygon))
            dirs[k] = axis if top else axis.scale(-1.0)
        else:
            projected.append(
                _project_notch(p, *_notch_normal(base, p, sa),
                               piece.gross_polygon))
    note = (f"刀口：×{len(projected)}，净样刀口沿外法向投影至毛样外沿"
            "（门襟裁片.md §2 Step3 / §4 Step4）",)
    if axis is not None:
        note += ("对折线两端刀口沿轴线投影、与中心对称线共线（§4 Step4）",)
    return piece.with_gross(piece.gross_polygon, tuple(projected),
                            piece.notes + note, notch_dirs=tuple(dirs))


# ---------- 共享收尾：变换 -> 自定向 -> 丝缕 -> 缩水 -> 缝边 -> 刀口投影 ----------

def _finish_fly_piece(main_ctx: DraftContext,
                      edges_main: list[tuple[str, LineSegment | CubicBezier]],
                      notches_main: list[Point],
                      marks_main: list[LineSegment | CubicBezier],
                      origin: Point, local: DraftContext, *,
                      name: str, label: str,
                      sa: dict[str, float],
                      fold_axis: tuple[int, int] | None = None) -> PatternPiece:
    """装配裁片三态：净样 -> 缩水 -> 缝边（门襟裁片.md §1 工序）。

    edges_main  主版坐标的命名边（闭合轮廓，有序）；sa 为边名->缝份 dict
    （cutter _sa_amount 按边名取值；双排镜像边加 _m 后缀异名、缝份值与
    基边同组，对折接缝 O/S 正常 miter，反射角由 cutter 裁剪）。
    fold_axis  对折线两端刀口索引对（双排传 (0,1)）：该两刀口沿对折轴线
    向外投影、打口方向沿轴（§4 Step4，与中心对称线绝对共线）；单排 None。
    """
    o = main_ctx.options
    # 1. 主版 -> 局部（Y 轴反射：X 不翻避镜像、Y 翻让腰头在上）
    local_named = [(n, _to_local_geom(g, origin)) for n, g in edges_main]
    # 2. 自定向：shoelace > 0 则反转（边序 + 每条 geom 反向），目标 < 0 保 cutter 外扩
    if _signed_area([g for _, g in local_named]) > 0:
        local_named = [(n, _reverse_geom(g)) for n, g in reversed(local_named)]
    net_edges = tuple(PieceEdge(n, g) for n, g in local_named)
    # 3. 刀口、标记同步到局部坐标（标记不随边界反转：内部线方向无关渲染）
    notches = tuple(_to_local_point(p, origin) for p in notches_main)
    marks = tuple(_to_local_geom(g, origin) for g in marks_main)
    # 4. 丝缕线（竖向 = 经向，与前/后片一致）
    grain = _vertical_grain(net_edges)
    # 5. 净样裁片
    piece = PatternPiece(name, label, net_edges, notches=notches,
                         grain=grain, marks=marks)
    # 6. 先缩水后缝边（缝份不叠加缩水，§1）；经向=局部 Y -> Y 吃 warp、X 吃 weft；
    #    门襟裁片专用缩水（None=回退全局 shrinkage_warp/weft，主面料口径）
    warp = (o.fly_shrinkage_warp
            if o.fly_shrinkage_warp is not None else o.shrinkage_warp)
    weft = (o.fly_shrinkage_weft
            if o.fly_shrinkage_weft is not None else o.shrinkage_weft)
    piece = apply_shrinkage(piece, weft, warp)
    # miter_limit 2.0：门襟拐角（腰口×外缘 T、底边×内边 S 等）内角约 82°，
    # miter 长约 1.52×max(sa) 恰超默认限 1.5 回退阶梯角——缝边拐角凸出一个
    # 缝份量台阶，内边（前浪线）缝边目检"不直"（DXF 报障即此）；2.0 = 内角
    # 60° 以下才回退阶梯，82° 常规服装拐角正常 miter（同 front_pouch_flow
    # 显式传 miter_limit 先例，不动 cutter 全局默认）。
    piece = add_seam_allowance(piece, sa, miter_limit=2.0)
    piece = _project_notches(piece, sa, fold_axis)
    # 7. 局部 ctx 留命名元素供 trace/调试（两片共用一个 ctx，键名不冲突）
    step = f"build_{name}"
    for i, e in enumerate(net_edges):
        if isinstance(e.geom, LineSegment):
            local.add_line(f"{name}.edge{i}", e.geom, step=step,
                           basis=f"{label} 净样边 {e.name}",
                           label=f"{e.name}边{i}")
        else:
            local.add_curve(f"{name}.edge{i}", e.geom, step=step,
                            basis=f"{label} 净样边 {e.name}",
                            label=f"{e.name}边{i}")
    return piece


# ---------- 单排（单层）门襟裁片 ----------

def _build_fly_single(main_ctx: DraftContext,
                      local: DraftContext) -> PatternPiece:
    """单排（单层）门襟裁片（门襟裁片.md §2）：原样提取已上版净样，几何零改动。

    闭合拓扑（O 起）：腰头线子弧（top，O->T）+ 外缘 G1 链（outer，T->c_start 直线 +
    c_start->c_end 底角 J 型圆弧 + c_end->S 底边）+ 内边（inner，S->O，与前浪缝合线
    重合）。外缘三段为步骤层构造的精确 G1 连续链（圆弧首柄 ∥ 外缘、末柄 ∥ 底边），
    必须**同名 outer**：cutter 异名相邻边遇平行切线（det=0）回退阶梯角，缝边会在
    G1 接缝处凸出一个缝份量的尖刺；同名边平滑相接无角点（同腰头后中/袋布底边口径）。
    刀口（§2 Step3）：内边开深 L 处（拉链止口/前浪对位点，供车缝对位），
    收尾沿内边外法向投影至毛样外沿（打在缝边上）。
    """
    o = main_ctx.options
    top_edge = main_ctx.curve("front.fly_sep_top_edge")      # T -> O（腰头线子弧）
    outer_edge = main_ctx.line("front.fly_sep_outer_edge")   # T -> c_start
    corner = main_ctx.curve("front.fly_sep_corner")          # c_start -> c_end（J 型底角）
    bottom_edge = main_ctx.line("front.fly_sep_bottom_edge")  # c_end -> S
    inner_edge = main_ctx.line("front.fly_sep_inner_edge")   # S -> O
    edges_main = [("top", _reverse_geom(top_edge)),          # O -> T
                  ("outer", outer_edge), ("outer", corner), ("outer", bottom_edge),
                  ("inner", inner_edge)]
    # 刀口：内边开深 L 处（L = 裁片高 h − 底部延展量，与步骤层同口径）
    o_pt = main_ctx.point("front.fly_origin")
    y_dir = main_ctx.line("front.rise_slant").direction
    L = inner_edge.length - o.fly_sep_extra
    notch = o_pt + y_dir.scale(L)
    sa_obj = o.fly_seam_allowances
    return _finish_fly_piece(main_ctx, edges_main, [notch], [], o_pt, local,
                             name="front_fly_single", label="单排门襟裁片（单层）",
                             sa={"top": sa_obj.top, "outer": sa_obj.outer,
                                 "inner": sa_obj.inner})


# ---------- 双排（对折）门襟裁片 ----------

def _build_fly_double(main_ctx: DraftContext,
                      local: DraftContext) -> PatternPiece:
    """双排（对折）门襟裁片（门襟裁片.md §4）：轮廓修正后轴对称展开。

    轮廓修正（§4 Step1）：去除底角 J 弧；外缘重构为直线 T->E（E = T + 前浪方向·h
    重算，未上版），与内边（O->S）同沿前浪方向**严格平行且绝对等长 h**（O,T,E,S
    成平行四边形，天然满足平行化约束）；底端 E->S 直线闭合；顶端保留腰头线弧。
    镜像展开（§4 Step2）：以**内边 O->S 为对称轴（对折线）**镜像半边成完整闭合
    净样，对折线为内部折叠线不在周界上（同袋布对折边口径）。刀口（§4 Step4）：
    对折线上下两端点 O/S（必含）+ 开深 L 对位点（投影到周界外缘）。标记：对折线
    画稿折叠指示。
    """
    o = main_ctx.options
    o_pt = main_ctx.point("front.fly_origin")                # O（对折线上端点）
    s_bot = main_ctx.point("front.fly_sep_bottom_inner")     # S（对折线下端点）
    t_top = main_ctx.point("front.fly_sep_top_outer")        # T（外缝顶点）
    top_edge = main_ctx.curve("front.fly_sep_top_edge")      # T -> O（顶端保留腰弧）
    y_dir = main_ctx.line("front.rise_slant").direction
    h = main_ctx.line("front.fly_sep_inner_edge").length     # 裁片高 = L + 延展量
    e_bot = t_top + y_dir.scale(h)                           # E（外缘下端，重算）
    # 镜像半边（对折轴 O->S）：E_m/T_m 镜像点，腰弧控制点同步镜像后反转成 T_m->O。
    # 镜像边用 _m 后缀**异名**：对折接缝 O/S 交 cutter 正常 miter——同名跳过角点
    # 处理时，O 为反射角（两腰弧谷底对接、切线突变），两条偏移链越过交点的采样
    # 尾段互相穿越 + 桥接段 = 顶部缝边三线交错自交（2026-08 DXF 报障）；异名
    # miter 交点 + cutter 反射角裁剪（越交点采样点裁去）后顶部缝边为过交点的
    # 单一连续线。对折线两端 O/S 刀口沿轴线向外投影（fold_axis，§4 Step4：
    # 主边外法向带前浪斜度必然歪斜，刀口须与中心对称线绝对共线供车间直线
    # 对折）；打口方向沿轴写 gross_notch_dirs，出口层不再按折线切线自推。
    e_m = _reflect_point(e_bot, o_pt, s_bot)
    t_m = _reflect_point(t_top, o_pt, s_bot)
    top_m = _reverse_geom(_reflect_geom(_reverse_geom(top_edge), o_pt, s_bot))
    edges_main = [("top", _reverse_geom(top_edge)),          # O -> T
                  ("outer", LineSegment(t_top, e_bot)),      # 外缘直线（平行等长）
                  ("bottom", LineSegment(e_bot, s_bot)),     # 底端直线闭合
                  ("bottom_m", LineSegment(s_bot, e_m)),
                  ("outer_m", LineSegment(e_m, t_m)),
                  ("top_m", top_m)]                          # T_m -> O
    # 刀口：对折线两端点 O/S + 开深 L 对位点（外缘上同深度，供车缝对位）
    L = h - o.fly_sep_extra
    notches = [o_pt, s_bot, t_top + y_dir.scale(L)]
    marks = [LineSegment(o_pt, s_bot)]                       # 对折线画稿标记
    sa_obj = o.fly_seam_allowances
    return _finish_fly_piece(main_ctx, edges_main, notches, marks, o_pt, local,
                             name="front_fly_double", label="双排门襟裁片（对折）",
                             sa={"top": sa_obj.top, "top_m": sa_obj.top,
                                 "outer": sa_obj.outer, "outer_m": sa_obj.outer,
                                 "bottom": sa_obj.bottom,
                                 "bottom_m": sa_obj.bottom},
                             fold_axis=(0, 1))


# ---------- 主入口 ----------

def build_front_fly(main_ctx: DraftContext
                    ) -> tuple[PatternPiece, PatternPiece | None, DraftContext]:
    """整版跑完后构建独立门襟裁片：单排（单层）+ 双排（对折），
    净样 -> 缩水 -> 缝边 -> 刀口投影（门襟裁片.md §2、§4）。

    返回 (单排片, 双排片 | None（fly_sep_double=False 时）, 局部 DraftContext)：
    前两者供 SVG 输出，后者含两片命名元素（front_fly_single.edge{i} /
    front_fly_double.edge{i}）供 trace/调试。需完整整版（提取已上版净样边界）。
    """
    o = main_ctx.options
    if not o.fly_separate:
        raise ValueError("门襟裁片需先开启 fly_separate（独立门襟）")
    if "front.fly_sep_top_edge" not in main_ctx.sheet:
        raise ValueError("门襟裁片依赖门襟绘制步骤，请先开启 fly_separate")
    local = DraftContext(main_ctx.measurements, o)
    single = _build_fly_single(main_ctx, local)
    double = _build_fly_double(main_ctx, local) if o.fly_sep_double else None
    return single, double, local
