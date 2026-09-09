"""腰头裁片流程：提取（真拼合/代数求和）-> 绘制净样 -> 缩水 -> 缝边（腰头裁片.md
§三~§五；v0.9 前后腰弧真拼合 + 整根均匀圆弧）。

build_waistband(main_ctx) 从整版 ctx 提取腰头净长与拼合几何：直腰头=代数求和
（上腰弧已按腰长不变量含省口宽，扣除得缝后净长）；弯腰头=省道绕尖旋转真闭口
-> 前后弧跨侧缝反射拼合 -> 局部系化 ->
整根均匀圆弧（curves.uniform_arc_cubic：同净长+同总转角+后中镜像 C2），
在独立 DraftSheet 局部坐标系绘制腰头净样，经 cutter 三段处理产出
PatternPiece。
自含裁片，非 FlowRunner 编排（提取为标量/几何输入；同 closure.py 口径）。
"""

from __future__ import annotations

import math

from ..cutter import (add_seam_allowance, apply_shrinkage, edge_length,
                      shrink_scale)
from ..draft import DraftContext
from ..draft import curves
from ..formulas import waist as waist_f
from ..geometry import CubicBezier, LineSegment, Point, Vector
from ..params import WaistbandGrain, WaistbandType
from ..pieces import PatternPiece, PieceEdge
from ..steps import waistband_steps as ws
from ..steps.waistband_steps import WaistbandSpec


def _dir(geom: LineSegment | CubicBezier, at_end: bool) -> Vector:
    """几何体端部单位切向（直线取 a->b 整体方向，贝塞尔取端点切线）。"""
    if isinstance(geom, LineSegment):
        v = geom.b - geom.a
    else:
        v = geom.tangent_at(1.0 if at_end else 0.0)
    return v.normalized() if v.length > 0 else Vector(1.0, 0.0)


def _sa_crossing(corner: Point, notch_dir: Vector, sa_tangent: Vector,
                 sa_amt: float, sx: float, sy: float) -> Point:
    """角点刀口的毛样位：刀口线（过 corner 沿 notch_dir）与缝边线（sa_tangent
    所在边沿外法向偏 sa_amt）的交点（腰头裁片.md §四.2 v0.4「沿着…和缝边
    相交的地方」）。

    两线先按缩水比例 (sx, sy) 仿射变换再求交——缩水先于缝边、缝份不叠加缩水
    （§五），各向异性缩水后垂直角点的两线不再正交，故取真交点而非法向平移。
    外法向 = 存储走向切线逆时针转 90°（与 cutter._offset_edge_points 同口径）；
    两线平行（数值退化）回退法向平移一个缝份。
    """
    c = Point(corner.x * sx, corner.y * sy)
    d = Vector(notch_dir.dx * sx, notch_dir.dy * sy).normalized()
    t = Vector(sa_tangent.dx * sx, sa_tangent.dy * sy).normalized()
    n = t.perpendicular()
    off = c + n.scale(sa_amt)
    det = d.dx * t.dy - d.dy * t.dx
    if abs(det) < 1e-9:
        return c + n.scale(sa_amt)
    r = off - c
    u = (r.dx * t.dy - r.dy * t.dx) / det
    return c + d.scale(u)


# ---- 弯腰头几何提取（§四.分支B v0.9：真闭省 + 反射拼合 + 局部系 + 均匀圆弧）----

def _xform_bezier(b: CubicBezier, f) -> CubicBezier:
    """贝塞尔 4 控制点过映射 f（刚体/仿射均保贝塞尔性）。"""
    return CubicBezier(f(b.p0), f(b.p1), f(b.p2), f(b.p3))


def _chain_hit(chain: list[CubicBezier],
               leg: LineSegment) -> tuple[int, float, Point] | None:
    """省腿线段 ∩ 当前链的首个交点（逐段线-贝塞尔求交），返回 (段idx, t, 点)。"""
    for j, b in enumerate(chain):
        r = curves.line_bezier_intersect(leg, b)
        if r is not None:
            return j, r[1], r[0]
    return None


def _close_back_darts(arc: CubicBezier, ctx: DraftContext, o
                      ) -> tuple[list[CubicBezier], list[int], Point]:
    """后省按 A->B 物理序逐个绕尖旋转闭口（§三 v0.7 真闭口）。

    每次在**当前链**上求省腿线 ∩ 弧（腿存的是省尖->省口弦点，闭口点=腿线
    与弧的交点），切除两交点间的省口弧段，远侧（B 侧）子链绕省尖旋转使远腿
    贴合近腿；后续省的腿/尖先经累计旋转变换再求交（物理等价的共轭复合）。
    臀围外缝点同步返回变换后位置（侧缝线随闭口物理移动，供拼合用）。
    交点缺失/次序异常抛 ValueError（可溯源，不静默忽略）。闭口处折角不进
    裁片形状——均匀圆弧只取链的净长与末切向（v0.9 口径）。
    """
    chain: list[CubicBezier] = [arc]
    ids: list[int] = []
    pend_c: list[Point] = []
    pend_deg: list[float] = []

    def _moved(p: Point) -> Point:
        for c, d in zip(pend_c, pend_deg):
            p = p.rotate_around(c, d)
        return p

    hip = ctx.point("back.hip_outseam_point")
    for i in range(1, o.back_dart_count + 1):
        if f"back.dart{i}_leg_inner" not in ctx.sheet:
            continue
        if o.back_dart_width[i - 1] <= 0:
            continue
        leg_in = ctx.line(f"back.dart{i}_leg_inner")
        leg_out = ctx.line(f"back.dart{i}_leg_outer")
        apex = _moved(leg_in.a)
        hit_a = _chain_hit(chain, LineSegment(apex, _moved(leg_in.b)))
        hit_b = _chain_hit(chain, LineSegment(apex, _moved(leg_out.b)))
        if hit_a is None or hit_b is None:
            raise ValueError(f"后省 {i} 省腿与腰弧链无交点（闭口失败）")
        (k1, t1, p_near), (k2, t2, p_far) = sorted((hit_a, hit_b),
                                                   key=lambda h: (h[0], h[1]))
        # 远侧旋转使远腿贴合近腿（θ = v_far -> v_near 的有向角）
        v_far = p_far - apex
        v_near = p_near - apex
        cross = v_far.dx * v_near.dy - v_far.dy * v_near.dx
        dot = v_far.dx * v_near.dx + v_far.dy * v_near.dy
        deg = math.degrees(math.atan2(cross, dot))
        near = [curves.bezier_subrange(chain[j], 0.0, 1.0) for j in range(k1)]
        near.append(curves.bezier_subrange(chain[k1], 0.0, t1))
        far = [curves.bezier_subrange(chain[k1], t2, 1.0)]
        far += [chain[j] for j in range(k1 + 1, len(chain))]
        far = [_xform_bezier(b, lambda p: p.rotate_around(apex, deg))
               for b in far]
        chain = near + far
        pend_c.append(apex)
        pend_deg.append(deg)
        ids.append(i)
    return chain, ids, _moved(hip)


def _close_pocket_dart(arc: CubicBezier, ctx: DraftContext, o
                       ) -> tuple[list[CubicBezier], bool]:
    """前口袋吃省 C1 闭口（§三 v0.7）：切 P1/P1′ 间弧段，前中侧刚体变换
    （旋转对齐切向后平移 P1′->P1），侧缝侧不动。

    切点取上腰头线法足（front.pocket_p1_top / pocket_p1_transfer_top——
    弯腰头+吃省时 P1/P1′ 本体在下腰头线上、距上腰弧约一个腰头宽，
    垂直延长线与上腰弧的法足才是腰头裁片的省位，t_of_point 复参）；
    守卫同现行 front_w 代数口径（front_pocket 开且省宽>0 且元素在版）。
    """
    if not (o.front_pocket and o.front_pocket_dart_width > 0):
        return [arc], False
    if ("front.pocket_p1_top" not in ctx.sheet
            or "front.pocket_p1_transfer_top" not in ctx.sheet):
        return [arc], False
    p1 = ctx.point("front.pocket_p1_top")
    p1t = ctx.point("front.pocket_p1_transfer_top")
    ta = curves.t_of_point(arc, p1)
    tb = curves.t_of_point(arc, p1t)
    if not (0.0 < ta < tb < 1.0):
        raise ValueError("前口袋吃省 P1/P1′ 不在腰弧内侧序异常（闭口失败）")
    near = curves.bezier_subrange(arc, 0.0, ta)
    far = curves.bezier_subrange(arc, tb, 1.0)
    d0 = math.degrees(math.atan2(arc.tangent_at(ta).dy, arc.tangent_at(ta).dx))
    d1 = math.degrees(math.atan2(arc.tangent_at(tb).dy, arc.tangent_at(tb).dx))
    deg = d0 - d1

    def _f(p: Point) -> Point:
        return p.rotate_around(p1t, deg) + (p1 - p1t)

    return [near, _xform_bezier(far, _f)], True


def _place_front_chain(front_chain: list[CubicBezier], hip_front: Point,
                       Bb: Point, hip_back: Point) -> list[CubicBezier]:
    """前腰弧链跨侧缝反射拼合到后弧 B 端（§四.分支B v0.7 真拼合）。

    ① θ = 前后真实侧缝线（腰点 B->臀围外缝点弦向，结构稳定）夹角，前链绕
    B_front 旋转 θ 令两缝线平行；② 平移 B_front->B_back 令两缝线重合；
    ③ 跨后片侧缝线反射 v' = 2(v·sb)sb − v——纸样沿缝翻折贴合（物理平摊
    缝拼合）。同侧仅旋转拼合是退化口径（旧 _auto_drop，前中折返 ~150°、
    矢高仅还原约三成），跨缝反射后接缝折角 ~8° 不进裁片形状——均匀弧只取
    净长与末切向（v0.9；拼合细节实测探针 out/probe_join.py）。
    """
    Bf = front_chain[0].p0
    af = math.atan2(hip_front.y - Bf.y, hip_front.x - Bf.x)
    ab = math.atan2(hip_back.y - Bb.y, hip_back.x - Bb.x)
    deg = math.degrees(ab - af)
    shift = Bb - Bf
    sb = Vector(hip_back.x - Bb.x, hip_back.y - Bb.y).normalized()

    def _f(p: Point) -> Point:
        q = p.rotate_around(Bf, deg) + shift
        v = q - Bb
        d = v.dx * sb.dx + v.dy * sb.dy
        return Bb + Vector(2 * d * sb.dx - v.dx, 2 * d * sb.dy - v.dy)

    return [_xform_bezier(b, _f) for b in front_chain]


def extract_waistband_spec(main_ctx: DraftContext) -> WaistbandSpec:
    """从整版 ctx 提取腰头净长与拼合几何（腰头裁片.md §三/§四.分支B v0.9）。

    口径：直/弯腰头统一读上腰弧 ``front/back.waistline_arc``（用户指引阶段4/3；
    弯腰头下腰弧为贴身边，差 <0.5cm，容忍）。直腰头=代数求和（省宽仅扣长，
    零改动；上腰弧已按腰长不变量含省口宽）；弯腰头=后省绕尖真闭口 -> 前口袋吃省 C1 闭口 -> 跨侧缝反射拼合
    -> 局部系化（origin=后中、X̂=后弧起切向 ⟂ 后中斜线 ⇒ 局部 y 轴 ∥ 后中
    缝=镜像轴、Ŷ=垂向中朝下者）-> 整根均匀圆弧（curves.uniform_arc_cubic：
    弧长=闭省后链实长（净长锁形）、总转角=链末切向角（「保持拼合的弯曲」
    ——sag/裆深经它传入）、起端切向恒水平（后中镜像 C1/C2）；曲率全弧
    均匀，端点位置派生——独立带状裁片端点无装配语义），l_* = 闭省后链实长。
    """
    o = main_ctx.options
    front_arc = main_ctx.curve("front.waistline_arc")   # t=0 侧缝 B -> t=1 前中 A
    back_arc = main_ctx.curve("back.waistline_arc")     # t=0 后中 A -> t=1 侧缝 B

    if o.waistband_type is not WaistbandType.CURVED:
        # 直腰头：代数求和——上腰弧已按腰长不变量含省口宽，扣除得缝后净长
        back_w = sum(o.back_dart_width[i - 1]
                     for i in range(1, o.back_dart_count + 1)
                     if f"back.dart{i}_leg_inner" in main_ctx.sheet
                     and o.back_dart_width[i - 1] > 0)
        front_w = waist_f.pocket_dart_takeup(o.front_pocket,
                                             o.front_pocket_dart_width)
        l_front = front_arc.length() - front_w
        l_back = back_arc.length() - back_w
        return WaistbandSpec(l_front=l_front, l_back=l_back,
                             l_half=l_front + l_back)

    # 弯腰头：真闭省 -> 反射拼合 -> 局部系 -> 整根均匀圆弧
    back_chain, _dart_ids, hip_back_moved = _close_back_darts(
        back_arc, main_ctx, o)
    front_chain, _pocket_dart = _close_pocket_dart(front_arc, main_ctx, o)
    Bb = back_chain[-1].p3
    front_chain = _place_front_chain(front_chain,
                                     main_ctx.point("front.hip_outseam_point"),
                                     Bb, hip_back_moved)
    origin = back_chain[0].p0
    X = back_chain[0].tangent_at(0.0).normalized()
    Yc = Vector(-X.dy, X.dx)
    Y = Yc if Yc.dy < 0 else Vector(X.dy, -X.dx)

    def _local(p: Point) -> Point:
        v = p - origin
        return Point(v.dx * X.dx + v.dy * X.dy, v.dx * Y.dx + v.dy * Y.dy)

    back_chain = [_xform_bezier(b, _local) for b in back_chain]
    front_chain = [_xform_bezier(b, _local) for b in front_chain]
    l_back = sum(b.length() for b in back_chain)
    l_front = sum(b.length() for b in front_chain)
    # v0.9 整根均匀圆弧：同净长 + 同总转角（链末切向，「保持拼合的弯曲」）
    # + 后中原点水平切向（镜像 C2），曲率全弧均匀摊开——后段与前段同弯度
    # （v0.8 拟合忠实保留拼合链「平后段+侧缝肘弯」，小 sag 时后段视觉近直）
    t_end = front_chain[-1].tangent_at(1.0)
    turn = math.degrees(math.atan2(t_end.dy, t_end.dx))
    arc = curves.uniform_arc_cubic(l_back + l_front, turn)
    return WaistbandSpec(
        l_front=l_front, l_back=l_back, l_half=l_front + l_back,
        bottom_arc=arc)


def _collect_notches(ctx: DraftContext) -> tuple[Point, ...]:
    """收集腰头净样刀口点（§四.2 v0.4：后中 -> 左下 -> 左上 -> 右下 -> 右上）。"""
    names = ("wb.notch_back_center", "wb.notch_left_bottom",
             "wb.notch_left_top", "wb.notch_right_bottom", "wb.notch_right_top")
    return tuple(ctx.point(n) for n in names if n in ctx.sheet)


def _project_corner_notches(piece: PatternPiece, local: DraftContext,
                            sx: float, sy: float) -> PatternPiece:
    """净样刀口换算至缝边位、整体替换毛样刀口（§四.2 v0.4，flow 私有
    工艺策略，同前/后片 _project_notches 先例；方向不同——非外法向投影，
    而是文档指定的角点邻边走向）：

    下顶点沿**腰头宽线**（端封边方向）交下口缝边线；上顶点沿**腰头线**
    （上口切向）交端头缝边线；后中沿**原点垂线**（后中宽度方向 = 下口线
    起端法向）交下口缝边线。载体为局部 sheet 净样几何（角点/切向；弯/直
    腰头边名同构恒 8 项——均匀弧起端切向恒 = X̂ 水平（uniform_arc_cubic 构造
    保证），「原点垂线」语义不变），缩水比例由 _sa_crossing 内仿射变换施加，
    与 cutter 缩水->缝边顺序一致。
    """
    o = local.options
    sa = o.waistband_seam_allowances
    right_end = local.line("wb.right_end")
    left_end = local.line("wb.left_end")
    bottom_right = local.sheet.get("wb.bottom_right").geom
    top_right = local.sheet.get("wb.top_right").geom
    # 左端相邻腰头线/下口线段：fly>0 取搭门段；fly=0 搭门段零长（切向退化，
    # 装配时已滤除），退回左半本体同点相接端（bottom_left 起端 / top_left 末端）
    if o.waistband_fly_extension > 1e-9:
        top_line = local.sheet.get("wb.top_fly").geom
        bottom_line = local.sheet.get("wb.bottom_fly").geom
        t_top, t_bottom = _dir(top_line, True), _dir(bottom_line, False)
    else:
        t_top = _dir(local.sheet.get("wb.top_left").geom, True)
        t_bottom = _dir(local.sheet.get("wb.bottom_left").geom, False)
    t_back = _dir(bottom_right, False)            # 下口线后中起端切向（水平）
    gross = (
        # 后中：原点垂线（起端切向法向）∩ 下口缝边
        _sa_crossing(Point(0, 0), t_back.perpendicular(), t_back,
                     sa.bottom, sx, sy),
        # 右下顶点：宽线（right_end 走向）∩ 下口缝边（bottom_right 前中末端切向）
        _sa_crossing(right_end.a, _dir(right_end, False),
                     _dir(bottom_right, True), sa.bottom, sx, sy),
        # 右上顶点：腰头线（top_right 起端切向）∩ 右端缝边（right_end 走向）
        _sa_crossing(right_end.b, _dir(top_right, False),
                     _dir(right_end, False), sa.right_end, sx, sy),
        # 左上顶点：腰头线（top_fly 末端/top_left 末端切向）∩ 左端缝边
        _sa_crossing(left_end.a, t_top, _dir(left_end, False),
                     sa.left_end, sx, sy),
        # 左下顶点：宽线（left_end 走向）∩ 下口缝边（bottom_fly 起/bottom_left 起）
        _sa_crossing(left_end.b, _dir(left_end, False), t_bottom,
                     sa.bottom, sx, sy),
    )
    return piece.with_gross(
        piece.gross_polygon, gross,
        piece.notes + ("刀口：后中/四角净线交缝边位 ×5（腰头裁片.md §四.2 v0.4）",))


def build_waistband(main_ctx: DraftContext) -> tuple[PatternPiece, DraftContext]:
    """整版跑完后构建腰头裁片：净样 -> 缩水 -> 缝边（腰头裁片.md §五）。

    返回 (PatternPiece, 局部 DraftContext)：前者供 SVG 输出，后者含命名元素
    供 trace/调试。
    """
    o = main_ctx.options
    spec = extract_waistband_spec(main_ctx)

    local = DraftContext(main_ctx.measurements, o)
    ws.draw_wb_bottom(local, spec)
    ws.draw_wb_top(local, spec)
    ws.draw_wb_ends(local, spec)
    ws.draw_wb_notches(local, spec)
    ws.draw_wb_grain(local, spec)

    # 装配净样边（逆时针顺序，语义边名用于缝边外扩；弯/直同构恒 8 项）
    # fly_extension=0 等退化情形产生零长搭门边（首尾重合，无切线、令缝边偏移触发
    # 零向量归一化）——装配时即滤除；其相邻有效边本在同点相接，跳过后闭合不受影响
    net_edges = tuple(
        PieceEdge(role, g) for name, role in ws.EDGE_ORDER
        if (g := local.sheet.get(name).geom) and edge_length(g) > 1e-9)
    notches = _collect_notches(local)
    grain = local.line("wb.grain")
    piece = PatternPiece("waistband", "腰头裁片", net_edges,
                         notches=notches, grain=grain,
                         frame="local")          # 旋转局部系（X̂=后弧切向），
                                                # 3D 试穿只随标量导出（§10.11）

    # 裁切三段：缩水 -> 缝边（缝份不叠加缩水，§五）
    # 缩水率按面料经/纬（warp/weft）给；映射到腰头局部 X/Y 轴由经向方向决定
    # （§五.2）：LENGTH 长向(X)=经 -> X 吃 warp；WIDTH 宽向(Y)=经 -> Y 吃 warp
    # 腰头裁片专用缩水（None=用全局；shrinkage_rates 含总开关收缩）
    if o.waistband_grain is WaistbandGrain.LENGTH:
        x_rate, y_rate = o.shrinkage_rates(o.waistband_shrinkage_warp,
                                           o.waistband_shrinkage_weft)
    else:  # WIDTH（默认）
        y_rate, x_rate = o.shrinkage_rates(o.waistband_shrinkage_warp,
                                           o.waistband_shrinkage_weft)
    piece = apply_shrinkage(piece, x_rate, y_rate)
    piece = add_seam_allowance(piece, o.waistband_seam_allowances)
    # 四角刀口换算至缝边位（§四.2 v0.4）：缝边交点须在缩水后几何上求取，
    # 故在缩水->缝边两段之后整体替换毛样刀口
    piece = _project_corner_notches(piece, local,
                                    shrink_scale(x_rate), shrink_scale(y_rate))
    return piece, local
