"""小表袋独立裁片流程：净样提取 -> 缩水屏蔽 -> 缝边（小表袋裁片.md §一~§四）。

build_watch_pocket(main_ctx) 从整版 ctx 提取已上版的小表袋净样边界，按
watch_pocket_mode 派发（§二）：
  - "facing_intersect" 袋贴相交延伸（§2.1）：闭合拓扑 pt1→pt2→pt3→pt4→pt1
    = 顶边（袋口直线）+ 内侧边（下延直线）+ 底边（袋贴内边贝塞尔子段，
    方向按角点归一）+ 外侧边（下延直线）；
  - "custom" 全自定义（§2.2）：ptN 锚点闭合链逐边（line/arc/bezier 混合），
    seg1 命名 top；N==4 时同模式 A 三类边名（top/side/bottom/side），
    N≠4 时其余全部 side（任意多边形无法可靠识别底边，bottom 字段不生效）。

共享 _finish_piece：装配命名边 -> 主版坐标 Y 轴反射到裁片局部坐标
（X 不翻保侧缝在左/前浪在右、Y 翻让袋口在上袋身向下，与前口袋裁片同口径、
SVG 正放、不镜像）-> 自定向（cutter 外法向要求闭合多边形 shoelace < 0）->
丝缕线（§3.2 继承大片方向：局部变换仅平移 + Y 翻转无旋转，主片裤长竖向
映射后仍竖向，与小表袋在主版上的摆放旋转角无关）-> 缩水（§3.1 里料 1:1
强制屏蔽大身面料缩水，默认 0 不缩水）-> 缝边（§4.1 top 折边 2.5 /
side 1.0 / bottom 1.0 与袋贴拼接缝份一致）与刀口（§4.2 袋口两角折边刀口 +
底边/最长边中段装配对位刀口）-> 装配 PatternPiece + 局部 ctx。
自含裁片，非 FlowRunner 编排（同 front_pocket_flow.build_front_pocket 口径）。
"""

from __future__ import annotations

from ..cutter import add_seam_allowance, apply_shrinkage, edge_length
from ..draft import DraftContext
from ..geometry import CubicBezier, LineSegment, Point
from ..pieces import PatternPiece, PieceEdge


# ---------- 几何小工具（与 front_pocket_flow 同款）----------

def _to_local_geom(g: LineSegment | CubicBezier, origin: Point
                   ) -> LineSegment | CubicBezier:
    """主版坐标 -> 裁片局部坐标：关于过 origin 的水平线反射
    local=(x−origin.x, origin.y−y)。X 不翻（保侧缝在左、前浪在右，避免镜像）、
    Y 翻（主版 Y 向上 -> 局部 +Y 朝下，袋口在上、袋身向下），与 piece_svg 的
    Y 向下不翻转口径一致。反射反向（det=−1，翻转绕向），由 _finish_piece
    自定向重新正序保 shoelace<0。origin 取袋口外上角 pt1。"""
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
    """闭合几何链的 shoelace 符号面积（cutter 外法向要求 < 0，同 yoke 口径）。

    各边采样后顺次拼接成多边形；相邻边共享端点（零长段贡献 0），末点经 % 回到
    首点。cutter 外法向 = 走向切线逆时针转 90°，shoelace < 0 时外法向朝外。
    """
    pts: list[Point] = []
    for g in geoms:
        pts.extend(_geom_sample(g))
    s, n = 0.0, len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        s += a.x * b.y - b.x * a.y
    return s


def _vertical_grain(net_edges: tuple[PieceEdge, ...]) -> LineSegment:
    """丝缕线：经向 = 大片裤长竖向方向 = 局部 Y（§3.2 继承主片径纬向；
    局部变换无旋转，主片竖向映射后仍竖向，与小表袋摆放旋转角无关）。
    竖向贯穿裁片（bbox 中心 x，上下各留 15% 边距），同 yoke 口径。"""
    xs, ys = [], []
    for e in net_edges:
        for p in _geom_sample(e.geom):
            xs.append(p.x)
            ys.append(p.y)
    cx = (min(xs) + max(xs)) / 2
    y0, y1 = min(ys), max(ys)
    margin = (y1 - y0) * 0.15
    return LineSegment(Point(cx, y0 + margin), Point(cx, y1 - margin))


# ---------- 净样收集（主版坐标）----------

def _collect_facing_intersect(ctx: DraftContext) \
        -> tuple[list[tuple[str, LineSegment | CubicBezier]], list[Point]]:
    """模式 A 净样收集（§2.1）：四边界封闭图形 pt1→pt2→pt3→pt4→pt1。

    底边方向归一：seg3 = bezier_subrange(袋贴内边, min(t1,t2), max(t1,t2))
    恒从参数小端跑向大端，t 序随袋形不定；按角点距离归一到 p0≈pt3、p3≈pt4
    （_reverse_geom 弧长不变），使闭合序成立且装配刀口弧长中点从固定端起量。
    刀口（§4.2）：袋口两角折边刀口 pt1/pt2 + 底边弧长中点装配对位刀口。
    """
    pt1 = ctx.point("front.watch_pocket_pt1")   # 外上角
    pt2 = ctx.point("front.watch_pocket_pt2")   # 内上角
    pt3 = ctx.point("front.watch_pocket_pt3")   # 内下交点
    pt4 = ctx.point("front.watch_pocket_pt4")   # 外下交点
    seg1 = ctx.line("front.watch_pocket_seg1")  # 顶边 pt1→pt2
    seg2 = ctx.line("front.watch_pocket_seg2")  # 内侧边 pt2→pt3
    seg3 = ctx.curve("front.watch_pocket_seg3")  # 底边（袋贴内边子段，方向不定）
    seg4 = ctx.line("front.watch_pocket_seg4")  # 外侧边 pt4→pt1
    if seg3.p0.distance_to(pt3) > seg3.p0.distance_to(pt4):
        seg3 = _reverse_geom(seg3)
    edges_main: list[tuple[str, LineSegment | CubicBezier]] = [
        ("top", seg1), ("side", seg2), ("bottom", seg3), ("side", seg4)]
    notches_main = [pt1, pt2, seg3.point_at_length(seg3.length() / 2)]
    return edges_main, notches_main


def _collect_custom(ctx: DraftContext) \
        -> tuple[list[tuple[str, LineSegment | CubicBezier]], list[Point]]:
    """模式 B 净样收集（§2.2）：ptN 锚点闭合链逐边拷贝（line/arc/bezier 混合，
    sheet.get 取 geom 避免类型不符）。

    边名：seg1 = 顶边 top（首锚点即袋口外上角，dy 向下为正的口径保证）；
    N==4 时同模式 A 三类边名，N≠4 时其余全部 side。
    刀口（§4.2）：袋口两角折边刀口 pt1/pt2 + 最长非顶边中点（直线参数中点、
    曲线弧长中点）装配对位刀口。
    """
    geoms: list[LineSegment | CubicBezier] = []
    i = 1
    while f"front.watch_pocket_seg{i}" in ctx.sheet:
        geoms.append(ctx.sheet.get(f"front.watch_pocket_seg{i}").geom)
        i += 1
    n = len(geoms)
    names = (["top", "side", "bottom", "side"] if n == 4
             else ["top"] + ["side"] * (n - 1))
    edges_main = list(zip(names, geoms))
    g = max(geoms[1:], key=edge_length)
    mid = (g.point_at(0.5) if isinstance(g, LineSegment)
           else g.point_at_length(g.length() / 2))
    notches_main = [ctx.point("front.watch_pocket_pt1"),
                    ctx.point("front.watch_pocket_pt2"),
                    mid]
    return edges_main, notches_main


# ---------- 共享收尾：变换 -> 自定向 -> 丝缕 -> 缩水 -> 缝边 ----------

def _finish_piece(main_ctx: DraftContext,
                  edges_main: list[tuple[str, LineSegment | CubicBezier]],
                  notches_main: list[Point],
                  origin: Point) -> tuple[PatternPiece, DraftContext]:
    """装配裁片三态：净样 -> 缩水 -> 缝边（小表袋裁片.md §三、§四）。"""
    o = main_ctx.options
    # 1. 主版 -> 局部（Y 轴反射：X 不翻避镜像、Y 翻让袋口在上）
    local_named = [(n, _to_local_geom(g, origin)) for n, g in edges_main]
    # 2. 自定向：shoelace > 0 则反转（边序 + 每条 geom 反向），目标 < 0 保 cutter 外扩
    if _signed_area([g for _, g in local_named]) > 0:
        local_named = [(n, _reverse_geom(g)) for n, g in reversed(local_named)]
    net_edges = tuple(PieceEdge(n, g) for n, g in local_named)
    # 3. 刀口同步到局部坐标（独立点不随边界反转：物理点相同）
    notches = tuple(_to_local_point(p, origin) for p in notches_main)
    # 4. 丝缕线（竖向 = 经向，§3.2）
    grain = _vertical_grain(net_edges)
    # 5. 净样裁片
    piece = PatternPiece("watch_pocket", "小表袋裁片", net_edges,
                         notches=notches, grain=grain)
    # 6. 缩水（§3.1）：口袋布里料材质独立，默认 0=不缩水，绝对隔离大身
    #    面料；非 0 才应用。竖向丝缕 -> Y 吃 warp、X 吃 weft
    warp, weft = o.watch_pocket_shrinkage_warp, o.watch_pocket_shrinkage_weft
    if warp or weft:
        piece = apply_shrinkage(piece, weft, warp)
    piece = add_seam_allowance(piece, o.watch_pocket_seam_allowances)
    # 7. 局部 ctx 留命名元素供 trace/调试
    local = DraftContext(main_ctx.measurements, o)
    step = "build_watch_pocket"
    for i, e in enumerate(net_edges):
        if isinstance(e.geom, LineSegment):
            local.add_line(f"watch_pocket.edge{i}", e.geom, step=step,
                           basis=f"小表袋裁片净样边 {e.name}（小表袋裁片.md §二）",
                           label=f"{e.name}边{i}")
        else:
            local.add_curve(f"watch_pocket.edge{i}", e.geom, step=step,
                            basis=f"小表袋裁片净样边 {e.name}（小表袋裁片.md §二）",
                            label=f"{e.name}边{i}")
    return piece, local


# ---------- 主入口 ----------

def build_watch_pocket(main_ctx: DraftContext) \
        -> tuple[PatternPiece, DraftContext]:
    """整版跑完后构建小表袋独立裁片：净样 -> 缩水 -> 缝边（小表袋裁片.md §一）。

    按 watch_pocket_mode 派发模式 A（袋贴相交延伸）/ 模式 B（全自定义）
    净样收集，共享 _finish_piece 完成三态装配。返回 (PatternPiece, 局部
    DraftContext)：前者供 SVG 输出，后者含命名元素供 trace/调试。
    需完整整版（提取已上版净样边界）。
    """
    o = main_ctx.options
    if not o.watch_pocket:
        raise ValueError("小表袋裁片需先开启 watch_pocket"
                         "（依赖 front_pocket 挖削嵌入式主切口）")
    if "front.watch_pocket_seg1" not in main_ctx.sheet:
        raise ValueError("小表袋裁片依赖小表袋绘制步骤，请先开启 watch_pocket")
    if o.watch_pocket_mode == "facing_intersect":
        edges_main, notches_main = _collect_facing_intersect(main_ctx)
    else:                                          # "custom"
        edges_main, notches_main = _collect_custom(main_ctx)
    origin = main_ctx.point("front.watch_pocket_pt1")   # 袋口外上角
    return _finish_piece(main_ctx, edges_main, notches_main, origin)
