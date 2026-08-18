"""后贴袋独立裁片流程：净样提取 -> 缩水 -> 折边缝边（后贴袋裁片.md §1~§5）。

build_back_patch(main_ctx) 从整版 ctx 1:1 完整复制已上版的后贴袋净样边界
（§1 以整版定位印痕为基准提取 Net_Polygon：back.patch_net_seg{i} 闭合链，
rectangle/baker_shield/angular/custom 四形态，custom 弧边保弧拷贝），按
o.back_patch_shape 派发语义边名：
  - rectangle（4 边）        top / side / bottom / side；
  - baker_shield（5 边）     top / side / bottom / bottom / side（底尖两斜边）；
  - angular（6 边）          top / side / bottom / bottom / bottom / side（两斜切）；
  - custom                   N==4 同 rectangle 三类边名；N≠4 其余全 side
                             （任意多边形无法可靠识别底边，同小表袋口径）。

共享收尾：主版坐标 Y 轴反射到裁片局部坐标（X 不翻保后浪侧在右、Y 翻让袋口
在上袋身向下，SVG 正放不镜像）-> 自定向（cutter 外法向要求 shoelace < 0）->
丝缕线（§5：经向与后大片裤长竖向绝对平行；局部变换仅平移 + Y 翻转无旋转，
主片竖向映射后仍竖向，与贴袋在主版上的摆放旋转角无关）-> 缩水（§2 大身
面料全链路：None 回退全局，非 0 才应用）-> 缝边（§2 分区缝份 + §3 袋口
折边 HemTreatment：镜像折线 + 撇势）-> §4 袋口刀口（净样顶端内/外上角
各两刀共 4 刀：沿内/外缝边延长线交毛样外沿一刀 + 沿袋口顶部线延长线交
毛样外沿一刀（落点即折边锚点 P_notch 毛样角点），全部打在缝边上、底部
不打口）；custom 弧袋口无直线镜像轴，自动降级常规法向放缝并记 notes
（无袋口刀口）。自含裁片，非 FlowRunner 编排
（同 watch_pocket_flow.build_watch_pocket 口径）。
"""

from __future__ import annotations

from ..cutter import HemTreatment, add_seam_allowance, apply_shrinkage
from ..draft import DraftContext
from ..geometry import CubicBezier, LineSegment, Point, Vector
from ..pieces import PatternPiece, PieceEdge


# ---------- 几何小工具（与 watch_pocket_flow 同款）----------

def _to_local_geom(g: LineSegment | CubicBezier, origin: Point
                   ) -> LineSegment | CubicBezier:
    """主版坐标 -> 裁片局部坐标：关于过 origin 的水平线反射
    local=(x−origin.x, origin.y−y)。X 不翻（保后浪/侧缝相对方位、避免镜像），
    Y 翻（主版 Y 向上 -> 局部 +Y 朝下，袋口在上、袋身向下），与 piece_svg 的
    Y 向下不翻转口径一致。反射反向（det=−1，翻转绕向），由收尾自定向重新
    正序保 shoelace<0。origin 取袋口近后浪侧顶点 pt1。"""
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
    """丝缕线（§5）：经向 = 后大片裤长竖向 = 局部 Y，与后大片经向矢量绝对平行
    （斜纹连贯、受力防拉伸、洗水缩水方向不偏转）。竖向贯穿裁片
    （bbox 中心 x，上下各留 15% 边距），同 yoke 口径。"""
    xs, ys = [], []
    for e in net_edges:
        for p in _geom_sample(e.geom):
            xs.append(p.x)
            ys.append(p.y)
    cx = (min(xs) + max(xs)) / 2
    y0, y1 = min(ys), max(ys)
    margin = (y1 - y0) * 0.15
    return LineSegment(Point(cx, y0 + margin), Point(cx, y1 - margin))


# ---------- 袋口刀口（§4：延长线交缝边）----------

def _edge_unit(g: LineSegment | CubicBezier, at_end: bool) -> Vector:
    """边首端/末端的单位切向（沿链走向）：直线取端点方向、贝塞尔取端点导数，
    零长兜底 (1,0)（同 cutter._unit_tangent 口径）。"""
    if isinstance(g, LineSegment):
        v = g.b - g.a
    else:
        v = g.tangent_at(1.0 if at_end else 0.0)
    return v.normalized() if v.length > 0 else Vector(1.0, 0.0)


def _edge_start(g: LineSegment | CubicBezier) -> Point:
    return g.a if isinstance(g, LineSegment) else g.p0


def _edge_end(g: LineSegment | CubicBezier) -> Point:
    return g.b if isinstance(g, LineSegment) else g.p3


def _ray_hit(p: Point, d: Vector,
             poly: tuple[Point, ...]) -> tuple[Point, Vector] | None:
    """射线 p+s·d 与闭合毛样折线的最近正距交点 + 该处缝边内法向（§4）。

    刀口 = 净边延长线与缝边（毛样外沿）的交点，取最近者（s 最小）；
    s<=1e-6 弃（起点即贴边：侧缝缝份 0 时顶部线延长线交点退回袋口净角，
    无缝边可打）。打口方向 = 交点处缝边段的内法向（垂直缝边向内、指向
    折线质心侧：顶边刀口即经向竖直向下，P_notch 角刀口沿袋口线向内）。
    """
    cx = sum(q.x for q in poly) / len(poly)
    cy = sum(q.y for q in poly) / len(poly)
    best: tuple[float, Point, Vector] | None = None
    for i in range(len(poly)):
        c, e = poly[i], poly[(i + 1) % len(poly)]
        f = e - c
        if f.length < 1e-12:
            continue
        det = d.dx * f.dy - d.dy * f.dx
        if abs(det) < 1e-12:               # 延长线与该缝边段平行
            continue
        r = c - p
        s = (r.dx * f.dy - r.dy * f.dx) / det
        u = (r.dx * d.dy - r.dy * d.dx) / det
        if s <= 1e-6 or not (-1e-9 <= u <= 1.0 + 1e-9):
            continue
        if best is None or s < best[0] - 1e-12:
            hit = p + d.scale(s)
            n = f.normalized().perpendicular()
            if n.dx * (cx - hit.x) + n.dy * (cy - hit.y) < 0.0:
                n = n.scale(-1.0)
            best = (s, hit, n)
    return None if best is None else (best[1], best[2])


def _top_hem_notches(piece: PatternPiece) -> PatternPiece:
    """§4 袋口刀口（2026-08-19 用户口径）：净样顶端内/外上角各两刀共 4 刀，
    全部打在缝边（毛样外沿）上、底部不打口——

      内上角（近后浪 pt1）/ 外上角（近侧缝 pt2）各发两条延长线：
      沿**侧缝边延长线**（内缝边/外缝边方向越角延长）交毛样外沿一刀；
      沿**袋口顶部线延长线**（背离袋口段方向）交毛样外沿一刀，落点即
      折边锚点 P_notch 毛样角点（两刀分别标记袋口双折车缝时折边线与
      侧缝折线在缝边上的穿越点）。
    打口方向 = 交点处缝边内法向（_ray_hit：顶边刀口即经向竖直向下，
    平行 Grainline_Vector；P_notch 角刀口垂直侧缝缝边沿袋口线向内）。
    整体替换 gross_notches（同门襟 _project_notches 口径；缝合线位刀口
    保留在 shrunk_notches 不丢信息，piece_svg 三级回退取毛样刀口）。
    """
    base = piece.shrunk_edges or piece.net_edges
    n = len(base)
    j = next(i for i, e in enumerate(base) if e.name == "top")
    top = base[j].geom
    a, b = _edge_start(top), _edge_end(top)
    t_h = _edge_unit(top, False)                     # 袋口走向 a->b
    # a 侧缝边延长 = 前侧边到达切向自 a 越角直行；b 侧 = 后侧边出发切向反向
    rays = ((a, _edge_unit(base[(j - 1) % n].geom, True)),
            (a, t_h.scale(-1.0)),
            (b, _edge_unit(base[(j + 1) % n].geom, False).scale(-1.0)),
            (b, t_h))
    pts: list[Point] = []
    dirs: list[Vector] = []
    for p, d in rays:
        hit = _ray_hit(p, d, piece.gross_polygon)
        if hit is not None:
            pts.append(hit[0])
            dirs.append(hit[1])
    note = (f"刀口：袋口 ×{len(pts)}，净口两角沿内/外缝边及顶部线延长线交"
            "毛样外沿（打在缝边上、垂直缝边向内打口，底部不打口；"
            "后贴袋裁片.md §4）",)
    return piece.with_gross(piece.gross_polygon, tuple(pts),
                            piece.notes + note, notch_dirs=tuple(dirs))


# ---------- 净样收集（主版坐标，§1 完整复制）----------

# 各形态语义边名模板（seg1 恒为袋口 top；baker_shield 底尖两斜边 /
# angular 两斜切边均为 bottom；custom 多边形无可靠底边识别）
_EDGE_NAMES: dict[str, list[str] | None] = {
    "rectangle": ["top", "side", "bottom", "side"],
    "baker_shield": ["top", "side", "bottom", "bottom", "side"],
    "angular": ["top", "side", "bottom", "bottom", "bottom", "side"],
    "custom": None,                       # 按段数现场派发（N==4 / N≠4）
}


def _collect_net(ctx: DraftContext) \
        -> tuple[list[tuple[str, LineSegment | CubicBezier]], list[Point]]:
    """净样收集（§1）：back.patch_net_seg{i} 闭合链逐边 1:1 拷贝
    （sheet.get 取 geom，line/arc 混边不判类型）；角点仅收袋口两角
    pt1/pt2（seg1 端点）作净样折边指示刀口，底部角点不打口（§4）。"""
    geoms: list[LineSegment | CubicBezier] = []
    i = 1
    while f"back.patch_net_seg{i}" in ctx.sheet:
        geoms.append(ctx.sheet.get(f"back.patch_net_seg{i}").geom)
        i += 1
    shape = ctx.options.back_patch_shape
    names = _EDGE_NAMES[shape]
    if names is None:                      # custom：N==4 三类边名，N≠4 全 side
        names = (["top", "side", "bottom", "side"] if len(geoms) == 4
                 else ["top"] + ["side"] * (len(geoms) - 1))
    if len(names) != len(geoms):
        raise ValueError(f"后贴袋 {shape} 形态应 {len(names)} 段净边，"
                         f"整版上版 {len(geoms)} 段（步骤层形态路由变更？）")
    notches: list[Point] = []
    j = 1
    while f"back.patch_net_pt{j}" in ctx.sheet:
        notches.append(ctx.point(f"back.patch_net_pt{j}"))
        j += 1
    return list(zip(names, geoms)), notches[:2]


# ---------- 主入口 ----------

def build_back_patch(main_ctx: DraftContext) \
        -> tuple[PatternPiece, DraftContext]:
    """整版跑完后构建后贴袋独立裁片：净样 -> 缩水 -> 折边缝边（后贴袋裁片.md）。

    §1 净样：从整版定位印痕 1:1 完整复制四形态净样（custom 弧边保弧）；
    §2 缩水：大身面料全链路（back_patch_shrinkage_warp/weft，None=回退全局
    shrinkage_warp/weft，非 0 才应用；竖向丝缕 -> Y 吃 warp、X 吃 weft）；
    §2 缝边：BackPatchSeamAllowances 分区缝份（top 折边 / side / bottom）；
    §3 袋口折边：HemTreatment("top", back_patch_top_hem_taper) 镜像折线 +
    撇势；§4 袋口刀口：净样顶端内/外上角各两刀共 4 刀（沿内/外缝边延长线
    及袋口顶部线延长线交毛样外沿，落点含折边锚点 P_notch；打在缝边上、
    垂直缝边向内打口、底部不打口，整体替换 gross_notches）；刀口类型/深度
    不改位置几何，记 notes（back_patch_notch_type / notch_depth）。custom
    弧袋口（seg1 为贝塞尔）无直线镜像轴：降级常规法向放缝并记 notes
    （无袋口刀口）。
    §5 丝缕：竖向（与后大片经向绝对平行）。
    返回 (PatternPiece, 局部 DraftContext)：前者供 SVG 输出，后者含命名元素
    供 trace/调试。需完整整版（提取已上版净样边界，依赖 back_yoke 定位）。
    """
    o = main_ctx.options
    if not o.back_patch:
        raise ValueError("后贴袋裁片需先开启 back_patch"
                         "（依赖 back_yoke 育克底线定位）")
    if "back.patch_net_seg1" not in main_ctx.sheet:
        raise ValueError("后贴袋裁片依赖后贴袋绘制步骤（须先开启 back_yoke"
                         "与 back_patch 跑完整版）")

    edges_main, notches_main = _collect_net(main_ctx)
    origin = main_ctx.point("back.patch_net_pt1")   # 袋口近后浪侧顶点

    # 1. 主版 -> 局部（Y 轴反射）-> 自定向（目标 shoelace<0 保 cutter 外扩）
    local_named = [(n, _to_local_geom(g, origin)) for n, g in edges_main]
    if _signed_area([g for _, g in local_named]) > 0:
        local_named = [(n, _reverse_geom(g)) for n, g in reversed(local_named)]
    net_edges = tuple(PieceEdge(n, g) for n, g in local_named)
    notches = tuple(_to_local_point(p, origin) for p in notches_main)
    grain = _vertical_grain(net_edges)

    # 袋口折边决策（§3）：直线袋口走 HemTreatment；custom 弧袋口无直线
    # 镜像轴，降级常规法向放缝（cutter 静默降级，此处显式记 notes）
    top = next(e for e in net_edges if e.name == "top")
    if isinstance(top.geom, LineSegment):
        hem = HemTreatment("top", o.back_patch_top_hem_taper)
        extra_notes: tuple[str, ...] = ()
    else:
        hem = None
        extra_notes = ("custom 弧袋口无直线镜像轴：折边降级常规法向放缝"
                       "（无撇势台阶/袋口刀口）",)
    notes = ((f"刀口：{o.back_patch_notch_type} 型 深 "
              f"{o.back_patch_notch_depth}cm（后贴袋裁片.md §4）",)
             + extra_notes)
    piece = PatternPiece("back_patch", "后贴袋裁片", net_edges,
                         notches=notches, grain=grain, notes=notes)

    # 2. 缩水（§2，大身面料 None 回退全局；竖向丝缕 -> Y 吃 warp）
    warp = (o.back_patch_shrinkage_warp
            if o.back_patch_shrinkage_warp is not None else o.shrinkage_warp)
    weft = (o.back_patch_shrinkage_weft
            if o.back_patch_shrinkage_weft is not None else o.shrinkage_weft)
    if warp or weft:
        piece = apply_shrinkage(piece, weft, warp)

    # 3. 缝边 + 袋口折边（§2~§3）+ §4 袋口刀口（直线袋口：净口两角沿
    # 内/外缝边及顶部线延长线交毛样外沿共 4 刀，底部不打口）
    piece = add_seam_allowance(piece, o.back_patch_seam_allowances, hem=hem)
    if hem is not None:
        piece = _top_hem_notches(piece)

    # 4. 局部 ctx 留命名元素供 trace/调试
    local = DraftContext(main_ctx.measurements, o)
    step = "build_back_patch"
    for i, e in enumerate(net_edges):
        if isinstance(e.geom, LineSegment):
            local.add_line(f"back_patch.edge{i}", e.geom, step=step,
                           basis=f"后贴袋裁片净样边 {e.name}（后贴袋裁片.md §1）",
                           label=f"{e.name}边{i}")
        else:
            local.add_curve(f"back_patch.edge{i}", e.geom, step=step,
                            basis=f"后贴袋裁片净样边 {e.name}（后贴袋裁片.md §1）",
                            label=f"{e.name}边{i}")
    return piece, local
