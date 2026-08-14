"""独立门襟裁片流程：净样提取 -> 缩水 -> 缝边（门襟裁片.md §2、§4）。

build_front_fly(main_ctx) 从整版 ctx 提取已上版的独立门襟净样（门襟绘制.md §5，
front.fly_sep_* 叠画于前片），产出两片独立裁片：
  - 单排（单层，§2）：原样提取净样轮廓（腰头线子弧 + 外缘 + 底角 J 型圆弧 +
    底边 + 内边），几何零改动。
  - 双排（对折，§4）：轮廓修正后轴对称展开——去除底角 J 弧，外缘重构为直线、
    强制与内边完全平行且绝对等长（O,T,E,S 成平行四边形），底端一条直线闭合，
    顶端保留腰头线弧；再以内边为对称轴（对折线）镜像展开成完整闭合净样。

工序红线（§1）：提取净样 -> 缩水放缩（主面料经纬，None=回退全局）-> 缩水后
缝边与刀口（缝份宽度为绝对值，先缝边后缩水会按比例缩小致止口跑偏）；丝缕线
竖直 = 经向，与前/后片一致（§1 关键约束，防洗水猫须扭曲）。自含裁片，非
FlowRunner 编排（同 front_pocket_flow / front_pouch_flow 口径）。
"""

from __future__ import annotations

from ..cutter import add_seam_allowance, apply_shrinkage
from ..draft import DraftContext
from ..geometry import CubicBezier, LineSegment, Point
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


# ---------- 共享收尾：变换 -> 自定向 -> 丝缕 -> 缩水 -> 缝边 ----------

def _finish_fly_piece(main_ctx: DraftContext,
                      edges_main: list[tuple[str, LineSegment | CubicBezier]],
                      notches_main: list[Point],
                      marks_main: list[LineSegment | CubicBezier],
                      origin: Point, local: DraftContext, *,
                      name: str, label: str,
                      sa: dict[str, float]) -> PatternPiece:
    """装配裁片三态：净样 -> 缩水 -> 缝边（门襟裁片.md §1 工序）。

    edges_main  主版坐标的命名边（闭合轮廓，有序）；sa 为边名->缝份 dict
    （镜像边 _m 取对应基名值，cutter _sa_amount 按边名取值）。
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
    piece = add_seam_allowance(piece, sa)
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
    刀口（§2 Step3）：内边开深 L 处（拉链止口/前浪对位点，供车缝对位）。
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
    # 镜像半边（对折轴 O->S）：E_m/T_m 镜像点，腰弧控制点同步镜像后反转成 T_m->O
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
                                 "bottom_m": sa_obj.bottom})


# ---------- 主入口 ----------

def build_front_fly(main_ctx: DraftContext
                    ) -> tuple[PatternPiece, PatternPiece | None, DraftContext]:
    """整版跑完后构建独立门襟裁片：单排（单层）+ 双排（对折），
    净样 -> 缩水 -> 缝边（门襟裁片.md §2、§4）。

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
