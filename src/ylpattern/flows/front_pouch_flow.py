"""前口袋袋布独立裁片流程：净样提取 -> 缩水 -> 缝边 -> 刀口投影（口袋布裁片.md §2~§6）。

build_front_pouch(main_ctx) 从整版 ctx 提取已上版的大片（底层）+ 小片（面层）净样
边界，以袋布内边（P_w0->K1 连线）为对称轴，将面层镜像生成面层、与大片（底层原样
复制）拼合成一片式对折裁片。面层镜像后即沿袋口弧线挖削（小片上版时上沿已走袋口切削
线：有省=切削线 C_cut / 无省=净线，镜像即得，免布尔运算）。缩水率默认 0（口袋布材质
独立，§3 绝对隔离大身面料）。自含裁片，非 FlowRunner 编排（同 front_pocket_flow /
yoke_flow 口径）。

辅助线与刀口（§5）：底层（未挖削完整侧）上版前口袋弧线（设计净线）作画稿对位
标记，有省时另上口袋省弧线（切削线 C_cut）；刀口只打在缝边（毛样）上（§5.1）--
底层袋口弧线两端沿切线延长线越过净边入缝份、交毛样外沿（§5.2 完整边缘强制打口），
面层挖削侧免打口（§5.3，沿袋口翻折压线不依赖刀口对位）。

闭合拓扑（单闭合轮廓，对折边 P_w0-K1 为内部折叠线不在周界上）：
  底层非折叠边 K1->…->P_s0->b->P_w0（大片原样复制，§2.1）
  ＋ 面层非折叠边反转 P_w0->P1″->P2′->P_s0′->…->K1（小片沿 P_w0-K1 镜像后反转，§2.2）
其中 P1″/P2′/P_s0′/K2′… 为 P1′(或 P1)/P2/P_s0/K2… 关于 P_w0-K1 的镜像点。

省道闭合：小片袋口切削线终于省顶 P1′，而小片腰弧边起于 P1（front_pouch_steps 现
口径），二者间为张开的省口 P1′->P1。面层为「折叠省道后的真实拼合」（§2.2 有省沿
C_cut 挖削），故面层腰弧边须取 P1′->P_w0（省顶至 P_w0）以闭合省口--本流程用腰弧
弧长精确细分重建该子段，不复用小片 P1->P_w0 腰弧边。
"""

from __future__ import annotations

from ..cutter import add_seam_allowance, apply_shrinkage
from ..draft import DraftContext, curves
from ..geometry import CubicBezier, LineSegment, Point, Vector
from ..pieces import PatternPiece, PieceEdge
from ..steps.front_steps import effective_waist


# ---------- 几何小工具（与 front_pocket_flow / yoke_flow 同款变换 / 反向 / 采样）----------

def _reflect_point(p: Point, axis_a: Point, axis_b: Point) -> Point:
    """点 p 关于直线 axis_a->axis_b 的轴对称镜像（口袋布裁片.md §2.1）。

    proj = A + d·((p−A)·d/|d|²) 为 p 在直线上的正投影，镜像 P′ = 2·proj − p。
    用 Point+Vector / Point−Point 口径（Point−Vector 不支持，见 geometry.point）。
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


def _reverse_geom(g: LineSegment | CubicBezier) -> LineSegment | CubicBezier:
    """反向几何：直线 a,b->b,a；三次贝塞尔 p0,p1,p2,p3->p3,p2,p1,p0（弧长不变）。"""
    if isinstance(g, LineSegment):
        return LineSegment(g.b, g.a)
    return CubicBezier(g.p3, g.p2, g.p1, g.p0)


def _to_local_geom(g: LineSegment | CubicBezier, origin: Point
                   ) -> LineSegment | CubicBezier:
    """主版坐标 -> 裁片局部坐标：关于过 origin 的水平线反射
    local=(x−origin.x, origin.y−y)。X 不翻（避镜像）、Y 翻（主版 Y 向上 -> 局部 +Y
    朝下，腰头在上、袋身向下），与 piece_svg 的 Y 向下不翻转口径一致。反射反向
    （det=−1），由调用方自定向重新正序保 shoelace<0。"""
    def f(p: Point) -> Point:
        return Point(p.x - origin.x, origin.y - p.y)
    if isinstance(g, LineSegment):
        return LineSegment(f(g.a), f(g.b))
    return CubicBezier(f(g.p0), f(g.p1), f(g.p2), f(g.p3))


def _to_local_point(p: Point, origin: Point) -> Point:
    return Point(p.x - origin.x, origin.y - p.y)


def _geom_sample(g: LineSegment | CubicBezier, n: int = 32) -> list[Point]:
    return [g.a, g.b] if isinstance(g, LineSegment) else g.sample(n)


def _signed_area(geoms: list[LineSegment | CubicBezier]) -> float:
    """闭合几何链的 shoelace 符号面积（cutter 外法向要求 < 0，同 yoke/front_pocket 口径）。"""
    pts: list[Point] = []
    for g in geoms:
        pts.extend(_geom_sample(g))
    s, n = 0.0, len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        s += a.x * b.y - b.x * a.y
    return s


def _vertical_grain(net_edges: tuple[PieceEdge, ...]) -> LineSegment:
    """丝缕线：经向 = 大片裤中线垂直方向 = 局部 Y（§6 继承大片经纬向）。
    竖向贯穿裁片（bbox 中心 x，上下各留 15% 边距），同 front_pocket_flow 口径。"""
    xs, ys = [], []
    for e in net_edges:
        for p in _geom_sample(e.geom):
            xs.append(p.x)
            ys.append(p.y)
    cx = (min(xs) + max(xs)) / 2
    y0, y1 = min(ys), max(ys)
    margin = (y1 - y0) * 0.15
    return LineSegment(Point(cx, y0 + margin), Point(cx, y1 - margin))


# ---------- 袋口弧线收集与刀口投影（§5；同 front_pocket_flow 私有策略口径）----------

def _collect_mouth_chain(ctx: DraftContext, *, cut: bool
                         ) -> list[LineSegment | CubicBezier]:
    """袋口弧线链（主版坐标）：cut=True 取切削线 C_cut（口袋省弧线，P1′->P2）、
    False 取设计净线（前口袋弧线，P1->P2）。bezier 模式单曲线
    front.pocket_mouth[_baseline]、polyline 模式折角链 …_segN。"""
    single, prefix = (("front.pocket_mouth", "front.pocket_mouth_seg") if cut
                      else ("front.pocket_mouth_baseline",
                            "front.pocket_mouth_baseline_seg"))
    if single in ctx.sheet:
        return [ctx.curve(single)]
    chain: list[LineSegment | CubicBezier] = []
    i = 1
    while f"{prefix}{i}" in ctx.sheet:
        chain.append(ctx.line(f"{prefix}{i}"))
        i += 1
    return chain


def _geom_tangent(g: LineSegment | CubicBezier, at_end: bool) -> Vector:
    """边首/末端沿走向的单位切线（直线取向量、贝塞尔取端点导矢；零向兜底
    水平），同 front_pocket_flow._geom_tangent 口径。"""
    v = ((g.b - g.a) if isinstance(g, LineSegment)
         else g.tangent_at(1.0 if at_end else 0.0))
    return v.normalized() if v.length > 1e-12 else Vector(1.0, 0.0)


def _ray_hit_poly(p: Point, d: Vector, poly: tuple[Point, ...]) -> Point | None:
    """点 p 沿 d 射线与毛样折线的最近交点（s>0；d 为任意非零向量）。

    同 front_pocket_flow._ray_hit_poly 求交口径：s 沿射线、u 沿折线段，取最近
    命中；无命中返回 None（调用方回退沿射线平移一个缝份）。"""
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


# ---------- 净样边界收集（主版坐标，K1->P_w0 走向；跳过 seg1=P_w0->K1 折叠边）----------

def _collect_large_edges(ctx: DraftContext
                         ) -> list[tuple[str, LineSegment | CubicBezier]]:
    """大片非折叠命名边（底层，原样复制，§2.1）：
    节点链 seg2..segN（bottom）+ 侧缝链（side）+ 腰弧 b->P_w0（waist）。"""
    edges: list[tuple[str, LineSegment | CubicBezier]] = []
    i = 2
    while f"front.pouch_large_seg{i}" in ctx.sheet:
        edges.append(("bottom", ctx.sheet.get(f"front.pouch_large_seg{i}").geom))
        i += 1
    if "front.pouch_side_edge" in ctx.sheet:           # P_s0 高于臀围线：单段外缝弧
        edges.append(("side", ctx.sheet.get("front.pouch_side_edge").geom))
    else:                                               # 低于臀围线：大腿外缝 + 外缝弧两段
        for name in ("front.pouch_side_edge_thigh", "front.pouch_side_edge_hip"):
            edges.append(("side", ctx.sheet.get(name).geom))
    edges.append(("waist", ctx.sheet.get("front.pouch_large_waist_edge").geom))
    return edges


def _collect_small_edges(ctx: DraftContext
                         ) -> list[tuple[str, LineSegment | CubicBezier]]:
    """小片非折叠命名边（面层，已挖袋口，§2.2 / §五.2；不含腰弧边）：
    节点链 seg2..segN（bottom）+ 侧缝 P_s0->P2（side）+ 袋口切削线 P2->P1′（mouth）。
    腰弧边 P1′->P_w0 由 _build_top_waist 重建（闭合省口，见模块 docstring）。"""
    edges: list[tuple[str, LineSegment | CubicBezier]] = []
    i = 2
    while f"front.pouch_small_seg{i}" in ctx.sheet:
        edges.append(("bottom", ctx.sheet.get(f"front.pouch_small_seg{i}").geom))
        i += 1
    i = 1
    while f"front.pouch_small_side_seg{i}" in ctx.sheet:
        edges.append(("side", ctx.sheet.get(f"front.pouch_small_side_seg{i}").geom))
        i += 1
    i = 1
    while f"front.pouch_small_mouth_seg{i}" in ctx.sheet:
        edges.append(("mouth", ctx.sheet.get(f"front.pouch_small_mouth_seg{i}").geom))
        i += 1
    return edges


def _build_top_waist(ctx: DraftContext) -> CubicBezier:
    """面层腰弧边 P1′->P_w0（§2.2 折叠省道后的真实拼合，闭合省口 P1′->P1）。

    沿有效腰弧 w_arc 按弧长精确细分：P1′ 在弧长 P1 距离 + 吃省宽、P_w0 在 P1 距离 +
    安全内延。无省时吃省宽=0，P1′=P1，与小片腰弧边一致。用 t_at_length（非 t_at_y，
    腰弧近水平 t_at_y 无法区分 P1/P1′）与 draw_front_pocket 的 P1′=point_at_length 口径
    一致，确保与袋口切削线终端 P1′ 严合。
    """
    o = ctx.options
    _, w_arc, _ = effective_waist(ctx)
    s_p1p = o.front_pocket_p1_dist + o.front_pocket_dart_width   # P1′ 弧长
    s_w0 = o.front_pocket_p1_dist + o.front_pouch_waist_safe     # P_w0 弧长
    return curves.bezier_subrange(w_arc, w_arc.t_at_length(s_p1p),
                                  w_arc.t_at_length(s_w0))


# ---------- 主入口 ----------

def build_front_pouch(main_ctx: DraftContext) -> tuple[PatternPiece, DraftContext]:
    """整版跑完后构建前口袋袋布独立裁片：净样 -> 缩水 -> 缝边（口袋布裁片.md §2~§6）。

    一片式对折：底层=大片原样复制，面层=小片沿内边 P_w0-K1 镜像（小片已挖袋口），
    两者以对折边 P_w0-K1 为内部折叠线拼合成单闭合轮廓。袋口挖削弧线有省取切削线
    C_cut、无省取净线（小片上版已定，镜像即得）；面层腰弧边取 P1′->P_w0 闭合省口。
    辅助线：底层上前口袋弧线（净线）恒上版、有省另上省弧线（C_cut，§5 画稿对位）；
    刀口：底层完整侧弧线端点沿切线延长线投至缝边（§5.1/§5.2），挖削侧免打口（§5.3）。
    缩水默认 0（§3 口袋布材质独立）。返回 (PatternPiece, 局部 DraftContext)：前者供
    SVG 输出，后者含命名元素供调试。需完整整版（提取已上版的大片/小片净样边界）。
    """
    o = main_ctx.options
    if not o.front_pouch:
        raise ValueError("袋布裁片需先开启 front_pouch（依赖前口袋主切口）")
    if "front.pouch_large_seg1" not in main_ctx.sheet:
        raise ValueError("袋布裁片依赖袋布绘制步骤，请先开启 front_pouch")

    # 对称轴（折叠轴）= 袋布内边 P_w0 -> K1（§2.1）
    p_w0 = main_ctx.point("front.pouch_waist_anchor")
    k1 = main_ctx.point("front.pouch_node1")

    # 底层 = 大片原样复制（K1->P_w0）；面层 = 小片（K1->P_w0，已挖袋口）+ 重建腰弧边
    large_edges = _collect_large_edges(main_ctx)
    small_edges = _collect_small_edges(main_ctx)
    small_edges.append(("waist", _build_top_waist(main_ctx)))    # P1′->P_w0 闭合省口

    # 面层沿 P_w0-K1 镜像 -> 整表反转成 P_w0->K1，命名加 _m 后缀
    # （折叠点 P_w0、K1 处异名边 waist/waist_m、bottom_m/bottom 强制 miter，避免同名录边
    #   跳过 miter 致折叠角缝份缺量，同 yoke 镜像折角口径）。袋口 mouth 仅面层独有、
    #   无底层同名对边，不加后缀以匹配 sa 字典的 mouth 键取缝份。
    mirrored = [(name, _reflect_geom(g, p_w0, k1)) for name, g in small_edges]
    mirrored_rev = [((name if name == "mouth" else name + "_m"),
                     _reverse_geom(g)) for name, g in reversed(mirrored)]

    # 合并单闭合轮廓（K1->…->P_w0->…->K1），对折边 P_w0-K1 为内部折叠线不在周界
    edges_main = large_edges + mirrored_rev

    # 主版 -> 局部（Y 反射，origin=P_w0 折叠顶点）-> 自定向（shoelace<0 保 cutter 外扩）
    origin = p_w0
    local_named = [(n, _to_local_geom(g, origin)) for n, g in edges_main]
    if _signed_area([g for _, g in local_named]) > 0:
        local_named = [(n, _reverse_geom(g)) for n, g in reversed(local_named)]
    net_edges = tuple(PieceEdge(n, g) for n, g in local_named)

    # 袋口弧线（主版坐标，§5 画稿对位/刀口基准）：前口袋弧线（设计净线 P1->P2）
    # 恒取；有省另取口袋省弧线（切削线 C_cut P1′->P2，无省时与净线重合免重复）
    has_dart = o.front_pocket_dart_width > 0
    arc_net = _collect_mouth_chain(main_ctx, cut=False)
    arc_cut = _collect_mouth_chain(main_ctx, cut=True) if has_dart else []

    # 刀口源（§5.1/§5.2）：底层未挖削完整侧，袋口弧线端点沿切线延长方向越过净边
    # 入缝份（首端取链首切线反向、末端取链末切线正向，同袋贴 _mouth_extension_dirs
    # 口径）；面层挖削侧免打口（§5.3）。sa 量仅作射线无命中的回退步长。
    sa_obj = o.front_pouch_seam_allowances
    notch_src: list[tuple[Point, Vector, float]] = [
        (main_ctx.point("front.pocket_p1"),                    # 腰头端 -> 腰缝边
         _geom_tangent(arc_net[0], False).scale(-1.0), sa_obj.waist),
    ]
    if has_dart:
        notch_src.append(
            (main_ctx.point("front.pocket_p1_transfer"),       # 省顶端 -> 腰缝边
             _geom_tangent(arc_cut[0], False).scale(-1.0), sa_obj.waist))
    notch_src.append(
        (main_ctx.point("front.pocket_p2"),                    # 侧缝端 -> 侧缝边
         _geom_tangent(arc_net[-1], True), sa_obj.side))
    notches = tuple(_to_local_point(p, origin) for p, _, _ in notch_src)

    # 标记：折叠线 P_w0->K1 + 袋口弧线辅助线（前口袋弧线恒有、省弧线有省才有，
    # 净样坐标，不随边界反转；SVG markline / DXF 层 8 内部画线）
    marks = ((_to_local_geom(LineSegment(p_w0, k1), origin),)
             + tuple(_to_local_geom(g, origin) for g in arc_net + arc_cut))

    # 丝缕（§6）：竖向=经（继承大片裤中线方向）
    grain = _vertical_grain(net_edges)

    piece = PatternPiece("front_pouch", "前口袋袋布裁片", net_edges,
                         notches=notches, grain=grain, marks=marks)

    # 缩水（§3）：口袋布默认 0=不缩水，绝对隔离大身面料；非 0 才应用
    warp = o.front_pouch_shrinkage_warp
    weft = o.front_pouch_shrinkage_weft
    if warp or weft:
        piece = apply_shrinkage(piece, weft, warp)

    # 缝边（§4）：sa dict 含 _m 变体同值；对折线 fold=0（内部边，周界不使用）。
    # miter 放宽为不限长：袋底×侧缝约 71° 锐角取两偏移线交点的标准 miter 尖角
    # （底部缝边延长线与侧边缝边线自然斜出，阶梯角反成多余折角）
    sa = {"bottom": sa_obj.bottom, "bottom_m": sa_obj.bottom,
          "side": sa_obj.side, "side_m": sa_obj.side,
          "waist": sa_obj.waist, "waist_m": sa_obj.waist,
          "mouth": sa_obj.mouth}
    piece = add_seam_allowance(piece, sa, miter_limit=float("inf"))

    # 刀口投影至缝边（§5.1 打口基准面=毛样缝边，不在净样线上）：切线延长方向经
    # 局部反射（Y 翻）+ 缩水缩放（局部 X 吃纬、Y 吃经，与刀口点同一仿射链，同
    # 前口袋裁片 §2.2 口径），自（缩水后）净刀口点沿射线交毛样折线，整体替换
    # 毛样刀口；射线无命中回退沿射线平移一个缝份（退化防御）。
    sx, sy = 1.0 + o.front_pouch_shrinkage_weft, 1.0 + o.front_pouch_shrinkage_warp
    gross_notches = []
    for p_base, (_, d_main, sa_amt) in zip(piece.gross_notches, notch_src):
        d = Vector(d_main.dx * sx, -d_main.dy * sy)
        q = _ray_hit_poly(p_base, d, piece.gross_polygon)
        gross_notches.append(q if q is not None else p_base + d.scale(sa_amt))
    piece = piece.with_gross(
        piece.gross_polygon, tuple(gross_notches),
        piece.notes + (f"刀口：底层完整侧袋口弧线端点沿切线延长线交缝边"
                       f" ×{len(gross_notches)}（口袋布裁片.md §5.1/§5.2；"
                       "挖削侧免打口 §5.3）",))

    # 局部 ctx 留命名元素供 trace/调试
    local = DraftContext(main_ctx.measurements, o)
    step = "build_front_pouch"
    for i, e in enumerate(net_edges):
        if isinstance(e.geom, LineSegment):
            local.add_line(f"pouch.edge{i}", e.geom, step=step,
                           basis=f"袋布净样边 {e.name}", label=f"袋布{e.name}边{i}")
        else:
            local.add_curve(f"pouch.edge{i}", e.geom, step=step,
                            basis=f"袋布净样边 {e.name}", label=f"袋布{e.name}边{i}")
    return piece, local
