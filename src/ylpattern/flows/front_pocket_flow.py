"""前口袋独立裁片流程：净样提取 -> 缩水 -> 缝边 -> 刀口投影（前口袋裁片.md §一~§三）。

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
刀口投影（§2.2，flow 私有策略不动 cutter 公开 API，同机头/前片先例：
袋贴袋口净线端点沿切线延长线交缝边、净样线位 + 缝边位成对；贴袋各净角点
沿相邻净边延长线交缝边，每角 2 刀折边指示）->
装配 PatternPiece + 局部 ctx。自含裁片，非 FlowRunner 编排
（同 waistband_flow.build_waistband / yoke_flow.build_yoke 口径）。
"""

from __future__ import annotations

from collections.abc import Mapping

from ..cutter import add_seam_allowance, apply_shrinkage, shrink_scale
from ..draft import DraftContext
from ..geometry import CubicBezier, LineSegment, Point, Vector
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


# ---------- 刀口毛样位（§2.2 切线延长线 / 净线延长线交缝边）----------

def _geom_end(g: LineSegment | CubicBezier) -> Point:
    return g.b if isinstance(g, LineSegment) else g.p3


def _geom_tangent(g: LineSegment | CubicBezier, at_end: bool) -> Vector:
    """边首/末端沿走向的单位切线（直线取向量、贝塞尔取端点导矢；零向兜底
    水平），同机头 _edge_tangent 口径。"""
    v = (g.b - g.a) if isinstance(g, LineSegment) else g.tangent_at(1.0 if at_end else 0.0)
    return v.normalized() if v.length > 1e-12 else Vector(1.0, 0.0)


def _sa_for(name: str, sa) -> float:
    """语义边缝份（与 cutter._sa_amount 同口径的鸭子类型分派，同前片 _sa_for）。"""
    if isinstance(sa, Mapping):
        return float(sa.get(name, 0.0))
    return float(getattr(sa, name, 0.0))


def _ray_hit_poly(p: Point, d: Vector, poly: tuple[Point, ...]) -> Point | None:
    """点 p 沿 d 射线与毛样折线的最近交点（s>0；d 为任意非零向量，非仅法向）。

    同机头/前片求交口径：s 沿射线、u 沿折线段，取最近命中；无命中返回 None
    （调用方回退）。
    """
    best: float | None = None
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        ex, ey = b.x - a.x, b.y - a.y
        det = ex * d.dy - ey * d.dx
        if abs(det) < 1e-12:
            continue                               # 射线与折线段平行
        rx, ry = a.x - p.x, a.y - p.y
        s = (ex * ry - ey * rx) / det
        u = (d.dx * ry - d.dy * rx) / det
        if s > 1e-9 and -1e-9 <= u <= 1.0 + 1e-9 \
                and (best is None or s < best):
            best = s
    return p + d.scale(best) if best is not None else None


def _project_notches(piece: PatternPiece, sa,
                     dirs: list[Vector] | None = None) -> PatternPiece:
    """刀口投影至缝边、整体替换毛样刀口（§2.2，flow 私有工艺策略，同机头
    §5.1 / 前片 §2.3 先例——投影规则是本裁片专属，不动 cutter 公开 API）。

    dirs 给出（INSET 袋贴）：袋口净线两端切线延长方向，与净刀口一一对应——
    每端成对上刀（净样线位 + 沿口袋弧线切线延长线交外侧缝边位，I/V 型刀口）；
    dirs 为 None（PATCH 贴袋）：各净角点沿相邻净边延长线交缝边，每角 2 刀
    （入边延长线交出边缝份、出边反向延长线交入边缝份，标顶部内折线两端与
    四周缝边折角；贴袋净边除袋口外同名 side，几何折角处同名相接仍须上刀，
    故不按边名跳过）。交点在毛样折线上求取（缩水 -> 缝边后的权威几何）；
    射线无命中回退沿射线平移一个缝份（退化防御，袋贴回退净点本身）。
    """
    base = piece.shrunk_edges or piece.net_edges
    poly = piece.gross_polygon
    net_pts = piece.shrunk_notches or piece.notches
    if dirs is not None:
        gross: list[Point] = []
        for p, d in zip(net_pts, dirs):
            q = _ray_hit_poly(p, d, poly)
            gross.append(p)                  # 净样线位（§2.2 同时打在净样线上）
            gross.append(q if q is not None else p)
        note = (f"刀口：袋口净线端点沿切线延长线交缝边（净样线+缝边成对）"
                f" ×{len(net_pts)}（前口袋裁片.md §2.2 INSET）",)
    else:
        gross = []
        n = len(base)
        for i in range(n):
            a, b = base[i], base[(i + 1) % n]
            p = _geom_end(a.geom)             # 角点（a 末端 == b 首端）
            t_a = _geom_tangent(a.geom, True)     # 入边末端切向（延长线方向）
            t_b = _geom_tangent(b.geom, False)    # 出边首端切向（反向延长方向）
            for d, sa_amt in ((t_a, _sa_for(b.name, sa)),
                              (t_b.scale(-1.0), _sa_for(a.name, sa))):
                q = _ray_hit_poly(p, d, poly)
                gross.append(q if q is not None else p + d.scale(sa_amt))
        note = (f"刀口：各净角点沿净线延长线交缝边（每角 2 刀折边指示）"
                f" ×{len(gross)}（前口袋裁片.md §2.2 PATCH）",)
    return piece.with_gross(poly, tuple(gross), piece.notes + note)


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


def _mouth_extension_dirs(ctx: DraftContext,
                          has_dart: bool) -> list[Vector]:
    """袋口净线（主切口线）两端的切线延长方向（§2.2 INSET：刀口顺着口袋
    弧线的切线延长线直至与外侧缝边相交）。

    与袋贴净刀口 [P1′/P1, P2] 一一对应：首端取链首切线反向（越过腰头端
    锚点延入腰头缝份）、末端取链末切线正向（越过 P2 延入侧缝缝份）。
    bezier 模式单曲线（切削线/净线）、polyline 模式折角链，两端各取端切线。
    """
    if "front.pocket_mouth" in ctx.sheet:               # bezier 有省切削线
        chain = [ctx.curve("front.pocket_mouth")]
    elif "front.pocket_mouth_baseline" in ctx.sheet:    # bezier 无省净线
        chain = [ctx.curve("front.pocket_mouth_baseline")]
    else:                                                # polyline 折角链
        prefix = ("front.pocket_mouth_seg" if has_dart
                  else "front.pocket_mouth_baseline_seg")
        chain = []
        i = 1
        while f"{prefix}{i}" in ctx.sheet:
            chain.append(ctx.line(f"{prefix}{i}"))
            i += 1
    return [_geom_tangent(chain[0], False).scale(-1.0),   # 越过 P1′/P1 延长
            _geom_tangent(chain[-1], True)]               # 越过 P2 延长


# ---------- 共享收尾：变换 -> 自定向 -> 丝缕 -> 缩水 -> 缝边 ----------

def _finish_piece(main_ctx: DraftContext,
                  edges_main: list[tuple[str, LineSegment | CubicBezier]],
                  notches_main: list[Point],
                  marks_main: list[LineSegment | CubicBezier],
                  origin: Point, *, name: str, label: str, sa,
                  notch_dirs_main: list[Vector] | None = None
                  ) -> tuple[PatternPiece, DraftContext]:
    """装配裁片三态：净样 -> 缩水 -> 缝边 -> 刀口投影（前口袋裁片.md §2）。

    edges_main       主版坐标的命名边（闭合轮廓，有序）；
    sa               缝份对象（dataclass，cutter _sa_amount 按 getattr(边名) 取值）；
    notch_dirs_main  刀口延伸方向（主版坐标向量，与 notches_main 一一对应；
                     给出 = INSET 袋贴沿袋口切线延长线投影；None = PATCH 贴袋
                     沿各净角点相邻净边延长线投影）。
    """
    o = main_ctx.options
    # 1. 主版 -> 局部（Y 轴反射：X 不翻避镜像、Y 翻让腰头在上）
    local_named = [(n, _to_local_geom(g, origin)) for n, g in edges_main]
    # 2. 自定向：shoelace > 0 则反转（边序 + 每条 geom 反向），目标 < 0 保 cutter 外扩
    if _signed_area([g for _, g in local_named]) > 0:
        local_named = [(n, _reverse_geom(g)) for n, g in reversed(local_named)]
    net_edges = tuple(PieceEdge(n, g) for n, g in local_named)
    # 3. 刀口、标记同步到局部坐标（标记不随边界反转：内部线方向无关渲染）；
    #    方向向量经同一反射翻 Y（缩水缩放在第 6 步后叠加，保持与刀口点/标记线
    #    同一仿射链，投影方向仍是缩水后袋口弧线的切线方向）
    notches = tuple(_to_local_point(p, origin) for p in notches_main)
    dirs_local = (None if notch_dirs_main is None
                  else [Vector(d.dx, -d.dy) for d in notch_dirs_main])
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
    # 7. 刀口投影至缝边（§2.2）：方向向量叠加缩水仿射（X 吃 weft、Y 吃 warp，
    #    同刀口点/标记线变换口径——各向异性缩放会转动方向，须映射后才与
    #    缩水后袋口弧线切线一致），再沿射线交毛样折线
    if dirs_local is not None:
        dirs_final = [Vector(d.dx * shrink_scale(weft),
                             d.dy * shrink_scale(warp)) for d in dirs_local]
        piece = _project_notches(piece, sa, dirs_final)
    else:
        piece = _project_notches(piece, sa)
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
    起止端点、沿切线延长线投至缝边（§2.2）。局部原点 = O（侧缝腰点）。
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
    # 刀口：袋口净线（主切口线）起止端点 P1'/P1、P2（§2.2 INSET 袋贴刀口），
    # 延伸方向顺着口袋弧线切线延长线直至交外侧缝边（净样线位 + 缝边位成对）
    p1_name = "front.pocket_p1_transfer" if has_dart else "front.pocket_p1"
    notches_main = [main_ctx.point(p1_name), main_ctx.point("front.pocket_p2")]
    notch_dirs_main = _mouth_extension_dirs(main_ctx, has_dart)
    marks_main = _collect_facing_marks(main_ctx, has_dart)
    return _finish_piece(main_ctx, edges_main, notches_main, marks_main, origin,
                         name="front_facing", label="前口袋袋贴裁片",
                         sa=o.front_pocket_facing_seam_allowances,
                         notch_dirs_main=notch_dirs_main)


# ---------- 分支 B：表面外贴式（PATCH）贴袋裁片 ----------

def build_front_patch(main_ctx: DraftContext) -> tuple[PatternPiece, DraftContext]:
    """表面外贴式贴袋裁片（§1.2）：直接拷贝净样母线 C(t)。

    前大片保持 100% 完整，贴袋为独立裁片；净样 front.patch_net_seg{i} 闭合链即
    外轮廓。seg1（袋口）命名 top 取内折边缝份，其余命名 side 取四周缝份（§2.2）。
    刀口 = 各净角点沿相邻净边延长线投影至缝边（每角 2 刀折边指示：顶部内折线
    两端 + 四周缝边折角）。局部原点 = 袋口外上角（front.patch_net_pt1）。
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
