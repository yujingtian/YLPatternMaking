"""前口袋独立裁片流程：净样提取 -> 缩水 -> 缝边（前口袋裁片.md §一~§三）。

build_front_pocket(main_ctx) 从整版 ctx 提取已上版的前口袋净样边界，按口袋类型
派发：
  - 挖削嵌入式（INSET，front_pocket_facing 开）-> build_front_facing：袋贴裁片，
    外边界（腰弧段 + 外缝弧段）1:1 完美复制前大片，内边 L_inner 闭合截取（§1.1）。
  - 表面外贴式（PATCH，front_patch 开）-> build_front_patch：贴袋裁片，直接拷贝
    净样母线 C(t)（§1.2）。

两条分支共享 _finish_piece：装配命名边 -> 主版坐标 Y 轴反射到裁片局部坐标
（X 不翻保侧缝在左/前浪在右、Y 翻让腰头在上袋身向下，与腰头/机头裁片同口径、
SVG 正放、不镜像）-> 自定向（cutter 外法向要求闭合多边形 shoelace < 0）->
丝缕线（继承大片裤中线垂直方向 = 经向）-> 先缩水后缝边（§2.1）->
装配 PatternPiece + 局部 ctx。自含裁片，非 FlowRunner 编排
（同 waistband_flow.build_waistband / yoke_flow.build_yoke 口径）。
"""

from __future__ import annotations

from ..cutter import add_seam_allowance, apply_shrinkage
from ..draft import DraftContext
from ..geometry import CubicBezier, LineSegment, Point
from ..pieces import PatternPiece, PieceEdge
from ..steps.front_steps import effective_waist


# ---------- 几何小工具（与 yoke_flow 同款 180° 保向变换 / 反向 / 采样）----------

def _to_local_geom(g: LineSegment | CubicBezier, origin: Point
                   ) -> LineSegment | CubicBezier:
    """主版坐标 -> 裁片局部坐标：关于过 origin 的水平线反射
    local=(x−origin.x, origin.y−y)。X 不翻（保侧缝在左、前浪在右，避免镜像）、
    Y 翻（主版 Y 向上 -> 局部 +Y 朝下，腰头在上、袋身向下），与 piece_svg 的
    Y 向下不翻转口径一致。反射反向（det=−1，翻转绕向），由 _finish_piece 自定向
    重新正序保 shoelace<0。origin 取裁片最高端（侧缝腰点/袋口外上角）。"""
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
    """丝缕线：经向 = 大片裤中线垂直方向 = 局部 Y（§2.3 继承大片经纬向）。
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


# ---------- 袋贴内边 / 内部标记收集 ----------

def _collect_facing_inner(ctx: DraftContext) -> list[LineSegment | CubicBezier]:
    """袋贴内边 L_inner（P_fw -> P_fs）：单曲线 front.pocket_facing_inner，
    或 polyline 模式折角链 front.pocket_facing_inner_seg{i}。"""
    if "front.pocket_facing_inner" in ctx.sheet:
        return [ctx.curve("front.pocket_facing_inner")]
    geoms: list[LineSegment | CubicBezier] = []
    i = 1
    while f"front.pocket_facing_inner_seg{i}" in ctx.sheet:
        geoms.append(ctx.line(f"front.pocket_facing_inner_seg{i}"))
        i += 1
    return geoms


def _collect_facing_marks(ctx: DraftContext,
                          has_dart: bool) -> list[LineSegment | CubicBezier]:
    """袋贴内部标记弧线（§1.1 必须保留，作画稿/钻孔标记）：
    袋口主切削线（有省）/ 袋口净线（无省）+ 吃省撇削边（有省时标省位）。"""
    marks: list[LineSegment | CubicBezier] = []
    if "front.pocket_mouth" in ctx.sheet:               # bezier 模式有省切削线
        marks.append(ctx.curve("front.pocket_mouth"))
    elif "front.pocket_mouth_baseline" in ctx.sheet:    # bezier 模式无省净线
        marks.append(ctx.curve("front.pocket_mouth_baseline"))
    elif has_dart:                                      # polyline 模式有省切削段
        i = 1
        while f"front.pocket_mouth_seg{i}" in ctx.sheet:
            marks.append(ctx.line(f"front.pocket_mouth_seg{i}"))
            i += 1
    else:                                               # polyline 模式无省净段
        i = 1
        while f"front.pocket_mouth_baseline_seg{i}" in ctx.sheet:
            marks.append(ctx.line(f"front.pocket_mouth_baseline_seg{i}"))
            i += 1
    if has_dart and "front.pocket_cut_start" in ctx.sheet:
        marks.append(ctx.line("front.pocket_cut_start"))
    return marks


# ---------- 共享收尾：变换 -> 自定向 -> 丝缕 -> 缩水 -> 缝边 ----------

def _finish_piece(main_ctx: DraftContext,
                  edges_main: list[tuple[str, LineSegment | CubicBezier]],
                  notches_main: list[Point],
                  marks_main: list[LineSegment | CubicBezier],
                  origin: Point, *, name: str, label: str, sa) \
        -> tuple[PatternPiece, DraftContext]:
    """装配裁片三态：净样 -> 缩水 -> 缝边（前口袋裁片.md §2）。

    edges_main  主版坐标的命名边（闭合轮廓，有序）；
    sa          缝份对象（dataclass，cutter _sa_amount 按 getattr(边名) 取值）。
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
    # 4. 丝缕线（竖向 = 经向）
    grain = _vertical_grain(net_edges)
    # 5. 净样裁片
    piece = PatternPiece(name, label, net_edges, notches=notches,
                         grain=grain, marks=marks)
    # 6. 先缩水后缝边（缝份不叠加缩水，§2.1）；经向=局部 Y -> Y 吃 warp、X 吃 weft
    #    前口袋裁片专用缩水（None=回退全局 shrinkage_warp/weft）
    warp = (o.front_pocket_shrinkage_warp
            if o.front_pocket_shrinkage_warp is not None else o.shrinkage_warp)
    weft = (o.front_pocket_shrinkage_weft
            if o.front_pocket_shrinkage_weft is not None else o.shrinkage_weft)
    piece = apply_shrinkage(piece, weft, warp)
    piece = add_seam_allowance(piece, sa)
    # 7. 局部 ctx 留命名元素供 trace/调试
    local = DraftContext(main_ctx.measurements, o)
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
    return piece, local


# ---------- 分支 A：挖削嵌入式（INSET）袋贴裁片 ----------

def build_front_facing(main_ctx: DraftContext) -> tuple[PatternPiece, DraftContext]:
    """挖削嵌入式袋贴裁片（§1.1）：完美复制腰弧段 + 外缝弧段，内边 L_inner 闭合。

    闭合拓扑 Ω_facing：腰弧 [O->P_fw]（完美复制）+ L_inner [P_fw->P_fs] +
    外缝弧 [P_fs->O]（完美复制）；O = 有效腰口侧缝腰点。外边界与前大片 1:1
    吻合，拼合无错位。内部保留袋口净线/切削线与吃省边（§1.1），刀口标袋口净线
    起止端点（§2.2）。局部原点 = O（侧缝腰点）。
    """
    o = main_ctx.options
    origin, _, _ = effective_waist(main_ctx)            # O = 侧缝腰点
    has_dart = o.front_pocket_dart_width > 0
    waist_edge = main_ctx.curve("front.pocket_facing_waist_edge")      # O->P_fw
    outseam_edge = main_ctx.curve("front.pocket_facing_outseam_edge")  # P_fs->O
    inner_geoms = _collect_facing_inner(main_ctx)                      # P_fw->P_fs
    edges_main = ([("waist", waist_edge)]
                  + [("inner", g) for g in inner_geoms]
                  + [("side", outseam_edge)])
    # 刀口：袋口净线（主切口线）起止端点 P1'/P1、P2（§2.2 INSET 袋贴刀口）
    p1_name = "front.pocket_p1_transfer" if has_dart else "front.pocket_p1"
    notches_main = [main_ctx.point(p1_name), main_ctx.point("front.pocket_p2")]
    marks_main = _collect_facing_marks(main_ctx, has_dart)
    return _finish_piece(main_ctx, edges_main, notches_main, marks_main, origin,
                         name="front_facing", label="前口袋袋贴裁片",
                         sa=o.front_pocket_facing_seam_allowances)


# ---------- 分支 B：表面外贴式（PATCH）贴袋裁片 ----------

def build_front_patch(main_ctx: DraftContext) -> tuple[PatternPiece, DraftContext]:
    """表面外贴式贴袋裁片（§1.2）：直接拷贝净样母线 C(t)。

    前大片保持 100% 完整，贴袋为独立裁片；净样 front.patch_net_seg{i} 闭合链即
    外轮廓。seg1（袋口）命名 top 取内折边缝份，其余命名 side 取四周缝份（§2.2）。
    刀口 = 各净角点（四周折边指示）。局部原点 = 袋口外上角（front.patch_net_pt1）。
    """
    o = main_ctx.options
    origin = main_ctx.point("front.patch_net_pt1")      # 袋口外上角
    edges_main: list[tuple[str, LineSegment | CubicBezier]] = []
    i = 1
    while f"front.patch_net_seg{i}" in main_ctx.sheet:
        g = main_ctx.sheet.get(f"front.patch_net_seg{i}").geom
        edges_main.append(("top" if i == 1 else "side", g))
        i += 1
    # 刀口：四周外拓缝边交界处的折边指示刀口（§2.2 PATCH 贴袋刀口）
    notches_main: list[Point] = []
    j = 1
    while f"front.patch_net_pt{j}" in main_ctx.sheet:
        notches_main.append(main_ctx.point(f"front.patch_net_pt{j}"))
        j += 1
    return _finish_piece(main_ctx, edges_main, notches_main, [], origin,
                         name="front_patch", label="前贴袋裁片",
                         sa=o.front_patch_seam_allowances)


# ---------- 主入口 ----------

def build_front_pocket(main_ctx: DraftContext) -> tuple[PatternPiece, DraftContext]:
    """整版跑完后构建前口袋独立裁片：净样 -> 缩水 -> 缝边（前口袋裁片.md §一~§三）。

    按口袋类型派发：front_pocket_facing 开 -> 袋贴裁片（INSET）；否则 front_patch
    开 -> 贴袋裁片（PATCH）。返回 (PatternPiece, 局部 DraftContext)：前者供 SVG
    输出，后者含命名元素供 trace/调试。需完整整版（提取已上版净样边界）。
    """
    o = main_ctx.options
    if o.front_pocket_facing:
        return build_front_facing(main_ctx)
    if o.front_patch:
        return build_front_patch(main_ctx)
    raise ValueError("前口袋裁片需先开启 front_pocket_facing（挖削嵌入式袋贴）"
                     "或 front_patch（表面外贴式贴袋）")
