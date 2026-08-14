"""前口袋袋布独立裁片流程：净样提取 -> 缩水 -> 缝边（口袋布裁片.md §2~§6）。

build_front_pouch(main_ctx) 从整版 ctx 提取已上版的大片（底层）+ 小片（面层）净样
边界，以袋布内边（P_w0->K1 连线）为对称轴，将面层镜像生成面层、与大片（底层原样
复制）拼合成一片式对折裁片。面层镜像后即沿袋口弧线挖削（小片上版时上沿已走袋口切削
线：有省=切削线 C_cut / 无省=净线，镜像即得，免布尔运算）。缩水率默认 0（口袋布材质
独立，§3 绝对隔离大身面料）。自含裁片，非 FlowRunner 编排（同 front_pocket_flow /
yoke_flow 口径）。

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
from ..geometry import CubicBezier, LineSegment, Point
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

    # 刀口（§5）：折叠对位 P_w0/K1 + 袋口起止 P1″/P2′（镜像；有省 P1′=省顶、无省 P1）
    has_dart = o.front_pocket_dart_width > 0
    p1_src = "front.pocket_p1_transfer" if has_dart else "front.pocket_p1"
    p1m = _reflect_point(main_ctx.point(p1_src), p_w0, k1)
    p2m = _reflect_point(main_ctx.point("front.pocket_p2"), p_w0, k1)
    notches = tuple(_to_local_point(p, origin) for p in (p_w0, k1, p1m, p2m))

    # 标记：折叠线 P_w0->K1（画稿折叠指示，净样坐标，不随边界反转）
    marks = (_to_local_geom(LineSegment(p_w0, k1), origin),)

    # 丝缕（§6）：竖向=经（继承大片裤中线方向）
    grain = _vertical_grain(net_edges)

    piece = PatternPiece("front_pouch", "前口袋袋布裁片", net_edges,
                         notches=notches, grain=grain, marks=marks)

    # 缩水（§3）：口袋布默认 0=不缩水，绝对隔离大身面料；非 0 才应用
    warp = o.front_pouch_shrinkage_warp
    weft = o.front_pouch_shrinkage_weft
    if warp or weft:
        piece = apply_shrinkage(piece, weft, warp)

    # 缝边（§4）：sa dict 含 _m 变体同值；对折线 fold=0（内部边，周界不使用）
    sa_obj = o.front_pouch_seam_allowances
    sa = {"bottom": sa_obj.bottom, "bottom_m": sa_obj.bottom,
          "side": sa_obj.side, "side_m": sa_obj.side,
          "waist": sa_obj.waist, "waist_m": sa_obj.waist,
          "mouth": sa_obj.mouth}
    piece = add_seam_allowance(piece, sa)

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
