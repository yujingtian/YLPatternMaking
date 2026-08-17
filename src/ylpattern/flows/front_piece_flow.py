"""前片独立裁片流程：净样提取 -> 缩水 -> 缝边 -> 刀口投影（前片裁片.md）。

build_front_piece(main_ctx) 从整版 ctx 提取前片大片净样闭合轮廓，三大形态
装配条件矩阵（前片裁片.md §1）：
  - 弯腰头分离（§1.1）：顶边 = 下腰头线子段、前浪自下前中腰点 A′ 起、外缝弧
    截到下侧缝腰点 B′；直腰头顶边 = 上腰弧（B -> A）。统一走
    steps.front_steps.effective_waist，与口袋/门襟/袋贴步骤同源同口径。
  - 挖削嵌入式口袋（§1.2）：外缝弧只保留 臀围端 -> P2 子段，挖削边界 = 袋口
    切削线反向（P2 -> P1′/P1，polyline 链逆序），顶边 = 腰弧自 P1′（有省）/
    P1（无省）起的余段；吃省撇削边 front.pocket_cut_start 属挖除区，不进
    大片边界。
  - 连裁门襟（§1.3）：门襟四元素（顶边/外线/角弧/融合弧）并入链首，前浪自
    融合点 front.fly_tangent 起取余段；独立门襟（fly_separate）与无门襟同形
    （前浪完整链），fly_j_* 参考元素不进边界。
缝边（§2.1/§2.2）：按语义边独立缝宽（FrontSeamAllowances），裆尖（前浪弧
末端 ∩ 下裆缝起点）角部由 front_piece_crotch_corner 开关控制（默认开 =
镜像折角；关闭 = 尖角跟随净样轮廓——两侧缝边按贝塞尔多项式自然外延（延续曲线自身张力与曲率）求首个交点成尖，
不抹圆）。刀口（§2.3）：净样刀口沿外法向延伸投影到毛样外沿
（flow 私有实现不动 cutter 公开 API——投影是各裁片专属工艺策略，yoke 已按
净线延长线交缝边投影（机头裁片.md §5.1）、back_patch 未投影）。缩水（§3.2）：主面料率 front_piece_shrinkage_*
（None 回退全局）。内部辅助线（§3.3）：臀围/膝围/毗围水平线按净边链截断为
marks，随缩水同比例变换（cutter.apply_shrinkage）。
自含裁片，非 FlowRunner 编排（同 build_waistband / build_yoke 口径），
不在 FULL_FLOW 内。
"""

from __future__ import annotations

from collections.abc import Mapping

from ..cutter import add_seam_allowance, apply_shrinkage
from ..draft import DraftContext
from ..draft import curves
from ..formulas import fly as fly_f
from ..geometry import CubicBezier, LineSegment, Point, Vector
from ..params import WaistbandType
from ..pieces import PatternPiece, PieceEdge
from ..steps.front_steps import effective_waist


# ---------- 几何小工具（与 front_pocket_flow 同款反射/反向/采样）----------

def _to_local_geom(g: LineSegment | CubicBezier, origin: Point
                   ) -> LineSegment | CubicBezier:
    """主版坐标 -> 裁片局部坐标：关于过 origin 的水平线反射
    local=(x−origin.x, origin.y−y)。X 不翻（保侧缝在左、前浪在右，避免镜像）、
    Y 翻（主版 Y 向上 -> 局部 +Y 朝下，腰头在上、裤身向下），与 piece_svg 的
    Y 向下不翻转口径一致。反射反向（det=−1），由 build_front_piece 自定向
    重新正序保 shoelace<0。origin = 侧缝腰点（B 直腰头 / B′ 弯腰头）。"""
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
    """丝缕线：经向 = 大片裤中线垂直方向 = 局部 Y（§3.1 继承全局纱向）。
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


def _sa_for(name: str, sa) -> float:
    """语义边缝份（与 cutter._sa_amount 同口径的鸭子类型分派）。"""
    if isinstance(sa, Mapping):
        return float(sa.get(name, 0.0))
    return float(getattr(sa, name, 0.0))


# ---------- 净边装配（§1 条件矩阵，主版自然 CW 序）----------

def _rise_edges(ctx: DraftContext, o, *, curved: bool
                ) -> list[tuple[str, LineSegment | CubicBezier]]:
    """前浪区链首（门襟无/独立形态）：直腰头自 A 起（前中斜线 + 裆弯弧）；
    弯腰头自 A′ 起（沿前浪量腰头宽 W 剥离腰头，§1.1）——A′ 在斜线段上时取
    斜线余段、在裆弯弧上（W ≥ 斜线长）时取弧子段、恰在臀围内缝点时斜线余段
    零长跳过。"""
    slant = ctx.line("front.rise_slant")
    curve = ctx.curve("front.rise_curve")
    if not curved:
        return [("rise", slant), ("rise", curve)]
    a_sub = ctx.point("front.lower_waist_center_point")   # A′（前浪 ∩ 下腰头线）
    b = ctx.point("front.hip_inner_point")
    rem = o.waistband_width - slant.length
    if rem < -1e-9:                       # A′ 在前中斜线段上：余段 + 完整裆弯弧
        return [("rise", LineSegment(a_sub, b)), ("rise", curve)]
    if rem > 1e-9:                        # A′ 在裆弯弧上：弧子段到裆尖
        return [("rise", curves.bezier_subrange(
            curve, curve.t_at_length(rem), 1.0))]
    return [("rise", curve)]              # rem == 0：A′ = 臀围内缝点


def _fly_rise_edges(ctx: DraftContext, o, *, curved: bool
                    ) -> list[tuple[str, LineSegment | CubicBezier]]:
    """连裁门襟区链首（§1.3）：门襟四元素（顶边/外线/角弧/融合弧）+ 前浪自
    融合点 fly_tangent 起的余段。余段定位与 front_fly_steps 同式同源：
    s_t = walk + L + extend（walk = W 弯腰头 / 0 直腰头；extend 由
    fly_blend_drop 或公式自动值同款重算），rem = s_t − 前中斜线长分三支
    （斜线余段 / 裆弯弧子段 / 恰在拐点零长跳过）。"""
    m = ctx.measurements
    edges = [("fly_top", ctx.line("front.fly_top_edge")),
             ("fly_outer", ctx.line("front.fly_outer_edge")),
             ("fly_bottom", ctx.curve("front.fly_corner_arc")),
             ("fly_bottom", ctx.curve("front.fly_bottom_arc"))]
    slant = ctx.line("front.rise_slant")
    curve = ctx.curve("front.rise_curve")
    b = ctx.point("front.hip_inner_point")
    p2 = ctx.point("front.fly_tangent")
    walk = o.waistband_width if curved else 0.0
    L = fly_f.fly_length(m.front_rise, o.fly_length_ratio, o.fly_length_base)
    R = fly_f.fly_corner_radius(o.fly_width, o.fly_corner_inset)
    extend_min = fly_f.fly_blend_extend_min(o.fly_width, R, o.fly_corner_turn)
    extend = (max(fly_f.fly_blend_extend(o.fly_width, R), extend_min)
              if o.fly_blend_drop is None else o.fly_blend_drop)
    rem = walk + L + extend - slant.length
    if rem < -1e-9:                       # 融合点在前中斜线段上
        edges += [("rise", LineSegment(p2, b)), ("rise", curve)]
    elif rem > 1e-9:                      # 融合点在裆弯弧上
        edges.append(("rise", curves.bezier_subrange(
            curve, curve.t_at_length(rem), 1.0)))
    else:                                 # 融合点 = 臀围内缝点
        edges.append(("rise", curve))
    return edges


def _mouth_edges(ctx: DraftContext) -> list[tuple[str, LineSegment | CubicBezier]]:
    """袋口挖削边（§1.2，主版 CW 序 P2 -> P1′/P1）：bezier 模式切削线单边反向；
    polyline 模式切削段链逆序逐段反向。dw=0 时切削线即净线（同元素）。"""
    if "front.pocket_mouth" in ctx.sheet:
        return [("mouth", _reverse_geom(ctx.curve("front.pocket_mouth")))]
    segs: list[LineSegment] = []
    i = 1
    while f"front.pocket_mouth_seg{i}" in ctx.sheet:
        segs.append(ctx.line(f"front.pocket_mouth_seg{i}"))
        i += 1
    return [("mouth", _reverse_geom(g)) for g in reversed(segs)]


def _net_edges(ctx: DraftContext, o, *, curved: bool, has_fly: bool,
               has_pocket: bool, w_arc: CubicBezier, s_side: float
               ) -> list[tuple[str, LineSegment | CubicBezier]]:
    """主版坐标净边装配（自然 CW 序）：前浪区（链首）-> 下裆缝（下行）->
    脚口 -> 外缝（上行）-> 侧缝弧上段 -> 袋口挖削边（如有）-> 顶边腰弧。"""
    edges = (_fly_rise_edges(ctx, o, curved=curved) if has_fly
             else _rise_edges(ctx, o, curved=curved))
    edges += [("inseam", ctx.curve("front.inseam_upper")),
              ("inseam", ctx.curve("front.inseam_lower")),
              ("hem", _reverse_geom(ctx.curve("front.hem"))),
              ("side", _reverse_geom(ctx.curve("front.outseam_lower"))),
              ("side", _reverse_geom(ctx.curve("front.outseam_upper")))]
    # 侧缝弧上段：无口袋截到侧缝腰点 B/B′（弯腰头即下腰头剥离线，§1.1；
    # t_end = s_side 与步骤层 t_at_length 同式同源），有口袋截到袋口侧缝
    # 锚点 P2（以上区段由挖削边界接管，§1.2）
    s_arc = ctx.curve("front.outseam_arc")
    t_end = s_arc.t_at_length(
        s_side - o.front_pocket_p2_drop if has_pocket else s_side)
    edges.append(("side", curves.bezier_subrange(s_arc, 0.0, t_end)))
    if has_pocket:
        edges += _mouth_edges(ctx)
    # 顶边腰弧：无口袋全弧（b -> A/A′），有口袋自 P1′（有省）/P1（无省）起
    # 的余段（t_at_length 同步骤层口径，端点差 <1e-9）
    t_start = 0.0
    if has_pocket:
        t_start = w_arc.t_at_length(
            o.front_pocket_p1_dist
            + (o.front_pocket_dart_width if o.front_pocket_dart_width > 0
               else 0.0))
    edges.append(("waist", curves.bezier_subrange(w_arc, t_start, 1.0)))
    return edges


# ---------- 刀口（§2.3）----------

def _fly_zipper_stop(ctx: DraftContext, o) -> Point:
    """拉链止口刀口：门襟外缘链（外线 -> 角弧 -> 融合弧）自顶外角下行开深
    L 处（与 front_fly_steps 同一 L 公式）。"""
    L = fly_f.fly_length(ctx.measurements.front_rise,
                         o.fly_length_ratio, o.fly_length_base)
    return curves.point_along_chain(
        (ctx.line("front.fly_outer_edge"),
         ctx.curve("front.fly_corner_arc"),
         ctx.curve("front.fly_bottom_arc")), L)


def _notches(ctx: DraftContext, o, *, has_fly: bool, has_pocket: bool,
             sa_hem: float) -> list[Point]:
    """净样刀口集（主版坐标，§2.3 关键对位位置；角点本身已是净边顶点不重复）：
    膝围双刀口（防扭脚，绝对精准）、臀围刀口、袋口 P2/P1′（对位）、拉链止口
    （连裁）、裤口卷边起折双刀口（明示卷边高度 = 缝宽）、毗围刀口（毗围线
    存在时；d=0 时内端 = 裆尖角点跳过）。"""
    pts = [ctx.point("front.knee_outseam_point"),
           ctx.point("front.knee_inseam_point"),
           ctx.point("front.hip_outseam_point")]
    if has_pocket:
        pts.append(ctx.point("front.pocket_p2"))
        pts.append(ctx.point("front.pocket_p1_transfer"
                             if "front.pocket_p1_transfer" in ctx.sheet
                             else "front.pocket_p1"))
    if has_fly:
        pts.append(_fly_zipper_stop(ctx, o))
    pts.append(ctx.curve("front.outseam_lower").point_at_y(sa_hem))
    pts.append(ctx.curve("front.inseam_lower").point_at_y(sa_hem))
    if "front.thigh_line" in ctx.sheet:
        pts.append(ctx.point("front.thigh_outseam_point"))
        if "front.thigh_inseam_point" in ctx.sheet:   # d=0 时内端 = 裆尖角点
            pts.append(ctx.point("front.thigh_inseam_point"))
    return pts


# ---------- 内部辅助线（§3.3 marks）----------

def _clip_h_line(chain: list[LineSegment | CubicBezier], y: float
                 ) -> LineSegment | None:
    """水平辅助线 y 按净边链折线采样裁剪截断（§3.3）：取与链的全部交点 x 的
    min/max 连成净样范围内线段（前片横向贯穿，正常两交点；角点/切点触线等
    奇异情形 min/max 容忍）。无两个交点返回 None。"""
    xs: list[float] = []
    for g in chain:
        pts = _geom_sample(g, 64)
        for a, b in zip(pts, pts[1:]):
            if (a.y - y) * (b.y - y) < 0:
                xs.append(a.x + (b.x - a.x) * (y - a.y) / (b.y - a.y))
            elif a.y == y:
                xs.append(a.x)
    if len(xs) < 2:
        return None
    return LineSegment(Point(min(xs), y), Point(max(xs), y))


def _internal_marks(ctx: DraftContext,
                    chain: list[LineSegment | CubicBezier]
                    ) -> list[LineSegment | CubicBezier]:
    """内部辅助线（§3.3）：臀围线、膝围线恒有，毗围线存在时（大腿围录入）
    追加——均按净边链截断为 marks（主版坐标，随主裁片同步局部化/缩水）。"""
    marks: list[LineSegment] = []
    for name in ("front.hip_line", "front.knee_line", "front.thigh_line"):
        if name not in ctx.sheet:
            continue
        seg = _clip_h_line(chain, ctx.line(name).a.y)
        if seg is not None:
            marks.append(seg)
    return marks


# ---------- 刀口法向投影（§2.3 延伸投影）----------

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
    命中多条边（P2、臀围点等）时法向取各边外法向均值（角平分方向）；无命中
    回退全链最近边（数值兜底）。shoelace<0 走向下切线逆时针 90° 即朝外，
    与 cutter 外扩同约定。"""
    scored = [(*_edge_distance_tangent(e.geom, p), e.name) for e in edges]
    near = [s for s in scored if s[0] <= 1e-6]
    if not near:
        near = [min(scored, key=lambda s: s[0])]
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
    """刀口 p 沿外法向 n 的射线与毛样折线的最近交点（§2.3 法向延伸投影）；
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


def _project_notches(piece: PatternPiece, sa, notch_type: str) -> PatternPiece:
    """净样刀口沿外法向延伸投影到毛样外沿，整体替换 gross_notches（§2.3）。

    载体边基于缩水后净边（无缩水退化净样，与 cutter base 同口径）；缝合线位
    刀口（shrunk_notches）保留不丢信息，piece_svg 三级回退自动取毛样刀口。
    刀口类型仅记 notes（I/V 型几何差异由输出层绘制，同 back_patch 先例）。"""
    base = piece.shrunk_edges or piece.net_edges
    notches = piece.shrunk_notches or piece.notches
    if not notches or not piece.gross_polygon:
        return piece
    projected = []
    for p in notches:
        n, amt = _notch_normal(base, p, sa)
        projected.append(_project_notch(p, n, amt, piece.gross_polygon))
    note = (f"刀口：{notch_type} 型 ×{len(projected)}，净样刀口沿外法向"
            "投影至毛样外沿（前片裁片.md §2.3）",)
    return piece.with_gross(piece.gross_polygon, tuple(projected),
                            piece.notes + note)


# ---------- 主入口 ----------

def build_front_piece(main_ctx: DraftContext
                      ) -> tuple[PatternPiece, DraftContext]:
    """整版跑完后构建前片独立裁片：净样 -> 缩水 -> 缝边 -> 刀口投影
    （前片裁片.md §1~§3）。

    返回 (PatternPiece, 局部 DraftContext)：前者供 SVG 输出，后者含命名元素
    供 trace/调试。需完整整版（提取已上版净样轮廓；--until 中断的中间版无
    front.hem 时抛 ValueError）。"""
    o = main_ctx.options
    if "front.hem" not in main_ctx.sheet:
        raise ValueError(
            "前片裁片需完整整版：front.hem 未上版（--until 中断的中间版"
            "不含完整前片轮廓）")
    curved = o.waistband_type is WaistbandType.CURVED
    has_fly = "front.fly_top_edge" in main_ctx.sheet   # 连裁门襟（独立为 fly_sep_*）
    has_pocket = "front.pocket_p1" in main_ctx.sheet
    b, w_arc, s_side = effective_waist(main_ctx)
    sa = o.front_piece_seam_allowances

    edges_main = _net_edges(main_ctx, o, curved=curved, has_fly=has_fly,
                            has_pocket=has_pocket, w_arc=w_arc, s_side=s_side)
    notches_main = _notches(main_ctx, o, has_fly=has_fly, has_pocket=has_pocket,
                            sa_hem=sa.hem)
    marks_main = _internal_marks(main_ctx, [g for _, g in edges_main])

    # 1. 主版 -> 局部（Y 轴反射：X 不翻避镜像、Y 翻让腰头在上），origin = 侧缝腰点
    origin = b
    local_named = [(n, _to_local_geom(g, origin)) for n, g in edges_main]
    # 2. 自定向：shoelace > 0 则反转（边序 + 每条 geom 反向），目标 < 0 保 cutter 外扩
    if _signed_area([g for _, g in local_named]) > 0:
        local_named = [(n, _reverse_geom(g)) for n, g in reversed(local_named)]
    net_edges = tuple(PieceEdge(n, g) for n, g in local_named)
    # 3. 刀口、标记同步到局部坐标（内部线方向无关渲染，不随边界反转）
    notches = tuple(_to_local_point(p, origin) for p in notches_main)
    marks = tuple(_to_local_geom(g, origin) for g in marks_main)
    # 4. 丝缕线（竖向 = 经向，§3.1 继承全局纱向）
    grain = _vertical_grain(net_edges)
    # 5. 净样裁片
    piece = PatternPiece("front_piece", "前片裁片", net_edges,
                         notches=notches, grain=grain, marks=marks)
    # 6. 先缩水后缝边（缝份不叠加缩水）：主面料率 None 回退全局；
    #    经向 = 局部 Y -> Y 吃 warp、X 吃 weft（换序传参，同 front_pocket 口径）
    warp = (o.front_piece_shrinkage_warp
            if o.front_piece_shrinkage_warp is not None else o.shrinkage_warp)
    weft = (o.front_piece_shrinkage_weft
            if o.front_piece_shrinkage_weft is not None else o.shrinkage_weft)
    piece = apply_shrinkage(piece, weft, warp)
    # 7. 缝边：裆尖（前浪弧末端 ∩ 下裆缝起点）角部两态（§2.2）——
    #    镜像折角（front_piece_crotch_corner=True，默认）：键序 (折线边, 被镜像边)
    #    = (rise, inseam)，前浪缝份翻折贴向下裆缝时**折线是前浪缝本身**
    #    （非下裆缝），下裆缝侧缝份边界关于前浪折线镜像，翻折后与裁片重合、
    #    补偿裆尖缺肉（cutter 双向查键，链序 (inseam, rise) 逆序命中时
    #    _mirror_point 形参自动交换。直角退化即 miter）；
    #    False=纯尖角跟随净样："miter" 不限长尖角自然相交——两侧缝边按贝塞尔多项式自然外延（延续曲线自身张力与曲率）求首个交点成尖
    #    （cutter._natural_join_sharp/_extrapolate_offset），裆尖尖角保留、
    #    不抹圆（尖角是该角的工艺目标形态；直筒等尖裆切线
    #    miter 长 >1.5·缝宽会触发默认限长回退阶梯角——台阶断点不圆顺，
    #    故显式声明绕过限长）
    if o.front_piece_crotch_corner:
        corners = {("rise", "inseam"): "mirror"}
    else:
        corners = {("rise", "inseam"): "miter"}   # 纯尖角跟随净样（不限长）
    piece = add_seam_allowance(piece, sa, corners)
    # 8. 刀口法向投影到毛样外沿（§2.3，专属工艺策略）
    piece = _project_notches(piece, sa, o.front_piece_notch_type)
    # 9. 局部 ctx 留命名元素供 trace/调试
    local = DraftContext(main_ctx.measurements, o)
    step = "build_front_piece"
    for i, e in enumerate(net_edges):
        if isinstance(e.geom, LineSegment):
            local.add_line(f"front_piece.edge{i}", e.geom, step=step,
                           basis=f"前片裁片 净样边 {e.name}",
                           label=f"{e.name}边{i}")
        else:
            local.add_curve(f"front_piece.edge{i}", e.geom, step=step,
                            basis=f"前片裁片 净样边 {e.name}",
                            label=f"{e.name}边{i}")
    return piece, local
