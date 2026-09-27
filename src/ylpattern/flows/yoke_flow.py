"""后机头/育克裁片流程：净样提取 -> 缩水 -> 缝边 -> 刀口（机头裁片.md §2~§5）。

build_yoke(main_ctx) 从整版 ctx 提取机头四条边界（腰口/底边/后中/侧缝），在主版
坐标系（Y 向上）装配净样闭合轮廓，经 _to_local 180° 旋转变换到裁片局部坐标系
（Y 向下、与腰头裁片同口径、SVG 不翻转即正放），再走 cutter 三段处理产出
PatternPiece。自含裁片，非 FlowRunner 编排（同 waistband_flow.build_waistband 口径）。

两种提取模式（机头裁片.md §2）：
  - 无省（§2.1）：直接复制四条边界围成的封闭区。
  - 有省（§2.2，1~2 省）：省（等腰三角）把机头切成若干片 -> 外侧片绕省尖级联
    旋转闭合拼合（2026-09-27 多省化：单省大省口集中一处折角，育克/腰头拼合后
    局部过弯；拆 2 省把转角摊到两处）-> 每处拼合上下折角 G1 倒圆（§2.2.3；
    退弧量由 PatternOptions.back_yoke_join_fillet 控制：None=自适应
    AUTO_SPAN_* 公式（默认）/ 正数=固定 / 0=不倒圆；倒圆带弧长补偿，
    车缝净长不变）。
  省未穿越机头上下边界或省位沿边界交乱 -> 回退无省提取（告警）。

cutter 负面积约定：净多边形顶点序 P0->PN->X->O（底边->侧缝->腰口->后中）在
本坐标系符号面积为负（180° 旋转变换保向），cutter 外法向正确外扩。
"""

from __future__ import annotations

import math
import sys
from collections.abc import Mapping

from ..cutter import add_seam_allowance, apply_shrinkage
from ..draft import DraftContext, curves
from ..geometry import CubicBezier, LineSegment, Point, Vector
from ..params import WaistbandType
from ..pieces import PatternPiece, PieceEdge


# ---------- 几何小工具 ----------

def _reverse_bezier(b: CubicBezier) -> CubicBezier:
    """反向三次贝塞尔：终点 -> 起点重参数化，弧长不变。"""
    return CubicBezier(b.p3, b.p2, b.p1, b.p0)


def _geom_start(g: LineSegment | CubicBezier) -> Point:
    return g.a if isinstance(g, LineSegment) else g.p0


def _geom_end(g: LineSegment | CubicBezier) -> Point:
    return g.b if isinstance(g, LineSegment) else g.p3


def _geom_length(g: LineSegment | CubicBezier) -> float:
    return g.length if isinstance(g, LineSegment) else g.length()


def _rotate_geom(g: LineSegment | CubicBezier, center: Point, deg: float
                 ) -> LineSegment | CubicBezier:
    """绕 center 旋转 deg 度（控制/端点同步，保贝塞尔性）。"""
    if isinstance(g, LineSegment):
        return LineSegment(g.a.rotate_around(center, deg),
                           g.b.rotate_around(center, deg))
    return CubicBezier(g.p0.rotate_around(center, deg),
                       g.p1.rotate_around(center, deg),
                       g.p2.rotate_around(center, deg),
                       g.p3.rotate_around(center, deg))


def _to_local_geom(g: LineSegment | CubicBezier, origin: Point
                   ) -> LineSegment | CubicBezier:
    """主版坐标 -> 裁片局部坐标：关于 origin 的 180° 旋转变换 local=(origin.x−x, origin.y−y)。

    保向（两轴同翻 det=+1），符号面积符号不变；局部 +Y 朝下（origin 为腰口后中端，
    在主版最高处），与 piece_svg 的 Y 向下不翻转口径一致。
    """
    def f(p: Point) -> Point:
        return Point(origin.x - p.x, origin.y - p.y)
    if isinstance(g, LineSegment):
        return LineSegment(f(g.a), f(g.b))
    return CubicBezier(f(g.p0), f(g.p1), f(g.p2), f(g.p3))


def _to_local_point(p: Point, origin: Point) -> Point:
    return Point(origin.x - p.x, origin.y - p.y)


# ---------- 求交（省腿 ∩ 机头边界）----------

def _line_line_intersect(leg: LineSegment, geom: LineSegment
                         ) -> tuple[Point, float] | None:
    """两线段交点：返回 (交点, t_on_geom)，要求交点在两线段参数 [0,1] 内。"""
    d1 = leg.b - leg.a
    d2 = geom.b - geom.a
    denom = d1.dx * d2.dy - d1.dy * d2.dx
    if abs(denom) < 1e-12:
        return None                                # 平行/共线
    diff = geom.a - leg.a
    t = (diff.dx * d2.dy - diff.dy * d2.dx) / denom   # leg 上参数
    u = (diff.dx * d1.dy - diff.dy * d1.dx) / denom   # geom 上参数
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return geom.point_at(u), u
    return None


def _line_bezier_intersect(leg: LineSegment, bez: CubicBezier, *, n: int = 256
                           ) -> tuple[Point, float] | None:
    """线段与三次贝塞尔求交（已提升至 curves.line_bezier_intersect，此处薄委托）。"""
    return curves.line_bezier_intersect(leg, bez, n=n)


def _seg_geom_intersect(leg: LineSegment, geom: LineSegment | CubicBezier
                        ) -> tuple[Point, float] | None:
    """省腿线段 ∩ 一条边界几何（直线/贝塞尔）：返回 (交点, t_on_geom) 或 None。"""
    if isinstance(geom, LineSegment):
        return _line_line_intersect(leg, geom)
    return _line_bezier_intersect(leg, geom)


def _chain_cross(chain: list, leg: LineSegment
                 ) -> tuple[int, float, Point] | None:
    """省腿 ∩ 边界链（P0->PN 有序）：返回 (段索引, 段上 t, 交点) 或 None。

    省腿穿越链一次，落在某一段内；逐段求交取首个命中。
    """
    for idx, geom in enumerate(chain):
        res = _seg_geom_intersect(leg, geom)
        if res is not None:
            pt, t = res
            return idx, t, pt
    return None


def _split_geom_at(geom: LineSegment | CubicBezier, t: float
                   ) -> tuple[LineSegment | CubicBezier, LineSegment | CubicBezier]:
    """几何在参数 t 处切成 (前段 [0,t], 后段 [t,1])。"""
    if isinstance(geom, LineSegment):
        pt = geom.point_at(t)
        return LineSegment(geom.a, pt), LineSegment(pt, geom.b)
    return curves.bezier_subrange(geom, 0.0, t), curves.bezier_subrange(geom, t, 1.0)


def _chain_prefix(chain: list, cross: tuple[int, float, Point]) -> list:
    """链首 -> cross 交点（含所在段截到 t）。"""
    idx, t, _ = cross
    out = list(chain[:idx])
    pre, _ = _split_geom_at(chain[idx], t)
    out.append(pre)
    return out


def _chain_suffix(chain: list, cross: tuple[int, float, Point]) -> list:
    """cross 交点 -> 链尾（含所在段从 t 起）。"""
    idx, t, _ = cross
    _, suf = _split_geom_at(chain[idx], t)
    return [suf] + list(chain[idx + 1:])


# ---------- 弧长量取 / 倒圆 ----------

def _point_at_arc(g: LineSegment | CubicBezier, s: float) -> Point:
    if isinstance(g, LineSegment):
        return g.a + (g.b - g.a).normalized().scale(s)
    return g.point_at_length(s)


def _tangent_at_arc(g: LineSegment | CubicBezier, s: float):
    """弧长 s 处的单位切线（沿走向）。"""
    if isinstance(g, LineSegment):
        return (g.b - g.a).normalized()
    return g.tangent_at(g.t_at_length(s)).normalized()


def _trim_end(g: LineSegment | CubicBezier, delta: float):
    """末端沿弧长退 delta（用于倒圆入边收缩）。"""
    L = _geom_length(g)
    if delta <= 0:
        return g
    if delta >= L:
        delta = L * 0.5
    if isinstance(g, LineSegment):
        return LineSegment(g.a, g.b + (g.a - g.b).normalized().scale(delta))
    return curves.bezier_subrange(g, 0.0, g.t_at_length(L - delta))


def _trim_start(g: LineSegment | CubicBezier, delta: float):
    """首端沿弧长退 delta（用于倒圆出边收缩）。"""
    L = _geom_length(g)
    if delta <= 0:
        return g
    if delta >= L:
        delta = L * 0.5
    if isinstance(g, LineSegment):
        return LineSegment(g.a + (g.b - g.a).normalized().scale(delta), g.b)
    return curves.bezier_subrange(g, g.t_at_length(delta), 1.0)


# 自适应倒圆公式常量（§2.2.3 折角前后区间重新拟合；back_yoke_join_fillet=None 时生效）：
# δ_auto = clamp(AUTO_SPAN_RATIO × min(拼合点两侧邻边弧长), AUTO_SPAN_MIN, AUTO_SPAN_MAX)
# 量级标定：省宽 3.76 / 省​​长 10.5 → 拼合转角 ~20°、邻边 ~8cm → δ≈1.6，转角摊在 ~3.3cm
# 弧段上肉眼圆顺（固定 0.4 只摊 0.8cm、渲染对比与不倒圆无差别，见决策日志 2026-09-21）。
AUTO_SPAN_RATIO = 0.2
AUTO_SPAN_MIN = 1.0
AUTO_SPAN_MAX = 3.0


def _auto_fillet_delta(geom_in: LineSegment | CubicBezier,
                       geom_out: LineSegment | CubicBezier) -> float:
    """自适应退弧量：拼合点两侧邻边弧长按 AUTO_SPAN_* 公式取值（§2.2.3）。"""
    span = AUTO_SPAN_RATIO * min(_geom_length(geom_in), _geom_length(geom_out))
    return max(AUTO_SPAN_MIN, min(AUTO_SPAN_MAX, span))


def _g1_fillet(geom_in: LineSegment | CubicBezier,
               geom_out: LineSegment | CubicBezier, delta: float
               ) -> tuple[LineSegment | CubicBezier, CubicBezier, LineSegment | CubicBezier]:
    """两同族边在连接点（geom_in 末端 == geom_out 首端）处 G1 倒圆（§2.2.3）。

    入/出边各沿弧长退 d=delta（钳制不超半长），插三次贝塞尔，端切向与两侧边一致。
    长度补偿（§2.2.3 第三条）：手柄长 h 二分解出，使倒圆弧长恰等于被 trim 掉的 2d，
    拼合前后车缝净长不变。返回 (收缩后的入边, 倒圆贝塞尔, 收缩后的出边)。
    d=0 时倒圆退化为连接两点（h 取极小量避免退化，不做补偿）。
    """
    L_in = _geom_length(geom_in)
    L_out = _geom_length(geom_out)
    d = min(delta, L_in / 2, L_out / 2)
    tin = _trim_end(geom_in, d)
    tout = _trim_start(geom_out, d)
    P = _geom_end(tin)                              # 入边收缩后末端
    Q = _geom_start(tout)                           # 出边收缩后首端
    t_in = _tangent_at_arc(geom_in, L_in - d)       # 入边末端切向
    t_out = _tangent_at_arc(geom_out, d)            # 出边首端切向

    def _fillet(h: float) -> CubicBezier:
        return CubicBezier(P, P + t_in.scale(h), Q + t_out.scale(-h), Q)

    if d > 0:
        # h 单调增弧长：h→0 退化为弦（< 2d），h=d 时约等于 2d（差随转角增大）。
        # 区间 [0, 4d] 二分至弧长 = 2d（容差 1e-4 cm，~50 次收敛）。
        target = 2.0 * d
        lo, hi = 0.0, 4.0 * d
        for _ in range(50):
            mid = (lo + hi) / 2.0
            if _fillet(mid).length() < target:
                lo = mid
            else:
                hi = mid
        fillet = _fillet((lo + hi) / 2.0)
    else:
        fillet = _fillet(0.05)
    return tin, fillet, tout


def _snap_geom_start(geom: LineSegment | CubicBezier, target: Point):
    """把几何首端移到 target（同步平移 p1/保持首端切向方向）。

    仅动首端相关控制点，末端不变 -> 不影响与下游边的连接（传播安全），用于左右片
    拼合时把旋转后右片的 join 顶点对齐到左片 join 顶点。
    """
    if isinstance(geom, LineSegment):
        return LineSegment(target, geom.b)
    shift = target - geom.p0
    return CubicBezier(target, geom.p1 + shift, geom.p2, geom.p3)


def _snap_geom_end(geom: LineSegment | CubicBezier, target: Point):
    """把几何末端移到 target（同步平移 p2/保持末端切向方向）。"""
    if isinstance(geom, LineSegment):
        return LineSegment(geom.a, target)
    shift = target - geom.p3
    return CubicBezier(geom.p0, geom.p1, geom.p2 + shift, target)


# ---------- 下口边界链收集 ----------

def _collect_bottom_chain(ctx: DraftContext) -> list:
    """机头下口线段链 back.yoke_bottom_seg{i}（P0->PN 有序，line/arc/bezier）。"""
    geoms = []
    i = 1
    while f"back.yoke_bottom_seg{i}" in ctx.sheet:
        geoms.append(ctx.sheet.get(f"back.yoke_bottom_seg{i}").geom)
        i += 1
    return geoms


def _chain_between(chain: list, cross_out: tuple, cross_in: tuple) -> list | None:
    """两穿越点之间的链段（cross_out -> cross_in，段序 P0->PN）。

    cross_out 须沿链先于 cross_in（段索引/段上 t 字典序），否则返回 None
    （调用方回退无省——省位交乱）。两穿越点同段时取该段子区间 (t1, t2)。
    """
    i1, t1, _ = cross_out
    i2, t2, _ = cross_in
    if i1 > i2 or (i1 == i2 and t1 > t2):
        return None
    if i1 == i2:
        g = chain[i1]
        if isinstance(g, LineSegment):
            return [LineSegment(g.point_at(t1), g.point_at(t2))]
        return [curves.bezier_subrange(g, t1, t2)]
    out: list = []
    _, suf = _split_geom_at(chain[i1], t1)
    out.append(suf)
    out.extend(chain[i1 + 1:i2])
    pre, _ = _split_geom_at(chain[i2], t2)
    out.append(pre)
    return out


def _detect_darts(ctx: DraftContext) -> list:
    """检测已上版的后省（省号升序 = 后中 -> 侧缝，PatternOptions 上限 2）：
    每省 (省号, 省尖, 内侧腿, 外侧腿)；空表 = 无省。"""
    out = []
    for i in (1, 2):
        if f"back.dart{i}_apex" not in ctx.sheet:
            continue
        apex = ctx.point(f"back.dart{i}_apex")
        leg_inner = ctx.line(f"back.dart{i}_leg_inner")  # LineSegment(省尖, p_in)
        leg_outer = ctx.line(f"back.dart{i}_leg_outer")  # LineSegment(省尖, p_out)
        out.append((i, apex, leg_inner, leg_outer))
    return out


# ---------- 净样装配（主版坐标系）----------

def _assemble_no_dart(bottom_chain: list, side_geom: CubicBezier,
                      top_arc: CubicBezier, cb_geom: LineSegment
                      ) -> list[tuple[str, object]]:
    """无省净样边（cutter 序 P0->PN->X->O）：底边链 / 侧缝 / 腰口（反向）/ 后中。"""
    edges: list[tuple[str, object]] = []
    for g in bottom_chain:
        edges.append(("bottom", g))
    edges.append(("side", side_geom))
    edges.append(("top", _reverse_bezier(top_arc)))     # X -> origin
    edges.append(("cb", cb_geom))
    return edges


def _assemble_darts(darts: list, bottom_chain: list, side_geom: CubicBezier,
                    top_arc: CubicBezier, cb_geom: LineSegment, delta: float | None
                    ) -> tuple[list[tuple[str, object]], list[Point]] | None:
    """有省（1~2 省）净样边：逐省切开 -> 外侧片绕省尖级联旋转闭合 ->
    每处拼合 G1 倒圆（§2.2）。

    闭省自最外侧省向最内侧省推进：先闭省 n（侧缝侧片绕 apex_n 转 θ_n），
    再闭省 n-1（其外侧全部片绕 apex_{n-1} 转 θ_{n-1}）……旋转复合
    g1∘g2 = g2'∘g1（g2' = g1 g2 g1⁻¹ 仍为绕 g1(apex_2) 的旋转），故第 k 片
    （省 k 与省 k+1 之间）的旋转链 pend_k = [(apex_k, θ_k)] + pend_{k-1}、
    后中侧第 0 片不动——与腰头裁片 pend 链（内→外逐省在移动系重交叉）结果
    同位，此处免重交叉、全部穿越点在原始边界一次求出。
    delta：float=固定退弧量；None=逐拼合点自适应（AUTO_SPAN_* 公式，§2.2.3）；
    0=不倒圆。倒圆带弧长补偿（fillet 弧长 = 2d，车缝净长不变）。
    返回 (edges, notches) 或 None（省腿未穿越上下边界/省位沿边界交乱 ->
    调用方回退无省）。
    """
    n = len(darts)

    # 每省：上下边界穿越点 + 闭合旋转角（把 (p_out-apex) 转到 (p_in-apex) 的
    # 有向角；等腰省 -> p_out 精确落 p_in，穿越点随之重合）
    info = []
    for _i, apex, leg_inner, leg_outer in darts:
        cin = _chain_cross(bottom_chain, leg_inner)
        cout = _chain_cross(bottom_chain, leg_outer)
        sin = _seg_geom_intersect(leg_inner, top_arc)
        sout = _seg_geom_intersect(leg_outer, top_arc)
        if cin is None or cout is None or sin is None or sout is None:
            return None                               # 省未切穿机头 -> 回退无省
        v_out = leg_outer.b - apex
        v_in = leg_inner.b - apex
        theta = math.degrees(math.atan2(
            v_out.dx * v_in.dy - v_out.dy * v_in.dx,
            v_out.dx * v_in.dx + v_out.dy * v_in.dy))
        info.append((apex, theta, cin, cout, sin[1], sout[1]))

    # 省位序守卫：省腿穿越点须沿底边链/腰口弧参数严格递增（省 1 靠后中；
    # 交错/重合 -> 回退无省）
    for _apex, _th, cin, cout, t_in, t_out in info:
        if (cin[0], cin[1]) >= (cout[0], cout[1]) or t_in >= t_out:
            return None
    for k in range(1, n):
        if (info[k - 1][3][0], info[k - 1][3][1]) >= (info[k][2][0], info[k][2][1]) \
                or info[k - 1][5] >= info[k][4]:
            return None

    # 分片旋转链：pend_0 = []（后中侧固定）；pend_k = [(apex_k, θ_k)] + pend_{k-1}
    pends: list[list] = [[]]
    for k in range(n):
        pends.append([(info[k][0], info[k][1])] + pends[k])

    def _rot(geoms: list, pend: list) -> list:
        for center, deg in pend:
            geoms = [_rotate_geom(g, center, deg) for g in geoms]
        return geoms

    # 底边分片（链序 P0->PN）：0 片 = P0->C_in1（固定）；k 片 = C_out_k->C_in_{k+1}；
    # n 片 = C_out_n->PN（侧缝侧，旋转最重）
    bottom_pieces = [_chain_prefix(bottom_chain, info[0][2])]
    for k in range(1, n):
        mid = _chain_between(bottom_chain, info[k - 1][3], info[k][2])
        if mid is None:
            return None
        bottom_pieces.append(_rot(mid, pends[k]))
    bottom_pieces.append(
        _rot(_chain_suffix(bottom_chain, info[n - 1][3]), pends[n]))

    # 腰口分片（弧参数 O->X 切片后反转成边序 X->O）：0 片 = St_in1->origin（固定）；
    # k 片 = St_in_{k+1}->St_out_k；n 片 = X->St_out_n；侧缝随 n 片旋转
    top_arc_pieces = []
    for k in range(n + 1):
        t_lo = info[k - 1][5] if k >= 1 else 0.0
        t_hi = info[k][4] if k <= n - 1 else 1.0
        top_arc_pieces.append(_rot(
            [_reverse_bezier(curves.bezier_subrange(top_arc, t_lo, t_hi))],
            pends[k]))
    top_edge_order = list(reversed(top_arc_pieces))  # [n 片, ..., 0 片]
    side_r = _rot([side_geom], pends[n])[0]

    # 对齐拼合顶点（端点平移、保切向、不传至下游连接）：底边链序右侧片首端
    # 吸附左侧片末端；腰口边序左侧片末端吸附右侧片首端（同单省口径——
    # 旋转侧重合于不动侧的拼合锚点，残余浮点误差吸掉）
    for k in range(1, n + 1):
        bottom_pieces[k][0] = _snap_geom_start(
            bottom_pieces[k][0], _geom_end(bottom_pieces[k - 1][-1]))
    for j in range(n):
        top_edge_order[j][-1] = _snap_geom_end(
            top_edge_order[j][-1], _geom_start(top_edge_order[j + 1][0]))

    # 拼合线刀口（标省位，取拼合前几何的锚点——落点或其倒圆区内，
    # _project_notches_to_sa 按最近边载向投影）：底边取左侧片末端、腰口取
    # 右侧片首端（均为不动侧锚点）
    notches = [_geom_end(bottom_pieces[k - 1][-1]) for k in range(1, n + 1)]
    notches += [_geom_start(top_edge_order[n - k + 1][0]) for k in range(1, n + 1)]

    edges: list[tuple[str, object]] = []

    def _append_joined(name: str, pieces_edge_order: list):
        """同族边多片顺接：相邻片连接点 G1 倒圆（delta>0）；delta=0 直接顺接。

        delta=None 时逐连接点自适应（两侧邻边弧长按 AUTO_SPAN_* 公式，§2.2.3）。
        """
        flat: list = list(pieces_edge_order[0])
        for segs in pieces_edge_order[1:]:
            d_eff = (delta if delta is not None
                     else _auto_fillet_delta(flat[-1], segs[0]))
            if d_eff > 0:
                tin, fillet, tout = _g1_fillet(flat[-1], segs[0], d_eff)
                flat[-1] = tin
                flat.append(fillet)
                flat.append(tout)
                flat.extend(segs[1:])
            else:
                flat.extend(segs)
        edges.extend((name, g) for g in flat)

    # 底边：P0->…->PN（片间倒圆）
    _append_joined("bottom", bottom_pieces)
    # 侧缝：PN' -> X（旋转后）
    edges.append(("side", side_r))
    # 腰口：X -> …->origin（片间倒圆）
    _append_joined("top", top_edge_order)
    # 后中：origin -> P0
    edges.append(("cb", cb_geom))
    return edges, notches


# ---------- 刀口毛样位（§5.1 净线延长线交缝边）----------

def _edge_tangent(g: LineSegment | CubicBezier, at_end: bool) -> Vector:
    """边首/末端沿走向的单位切线（直线取向量、贝塞尔取端点导矢；零向兜底水平）。"""
    v = (g.b - g.a) if isinstance(g, LineSegment) else g.tangent_at(1.0 if at_end else 0.0)
    return v.normalized() if v.length > 1e-12 else Vector(1.0, 0.0)


def _ray_hit_poly(p: Point, d: Vector, poly: tuple[Point, ...]) -> Point | None:
    """点 p 沿 d 射线与毛样折线的最近交点（s>0；d 为任意单位向量，非仅法向）。

    同前片 _project_notch 求交口径：s 沿射线、u 沿折线段，取最近命中；无命中
    返回 None（调用方回退）。
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


def _nearest_edge_tangent(base: tuple[PieceEdge, ...], p: Point) -> Vector:
    """p 最近边在最近点处的走向切向（直线参数投影 clamp、贝塞尔 64 采样，同前片
    _notch_normal 载边口径）。净刀口（后中/省位）都在边链上或其倒圆区内，
    最近边即其载体边。"""
    best_d, best_t = float("inf"), Vector(1.0, 0.0)
    for e in base:
        g = e.geom
        if isinstance(g, LineSegment):
            v = g.b - g.a
            if v.length == 0.0:
                continue
            t = max(0.0, min(1.0, ((p.x - g.a.x) * v.dx + (p.y - g.a.y) * v.dy)
                          / (v.dx * v.dx + v.dy * v.dy)))
            d = p.distance_to(g.a + v.scale(t))
            if d < best_d:
                best_d, best_t = d, v.normalized()
        else:
            for i in range(65):
                d = p.distance_to(g.point_at(i / 64))
                if d < best_d:
                    tan = g.tangent_at(i / 64)
                    if tan.length > 1e-12:
                        best_d, best_t = d, tan.normalized()
    return best_t


def _project_notches_to_sa(piece: PatternPiece, sa: Mapping[str, float]
                          ) -> PatternPiece:
    """角点刀口与净刀口换算至缝边位、整体替换毛样刀口（§5.1，flow 私有工艺
    策略，同腰头/前片先例——投影规则是本裁片专属，不动 cutter 公开 API）。

    角点刀口（§5.1 净样角点刀口）每角 2 刀：入边净线延长线交出边缝份边界、
    出边净线反向延长线交入边缝份边界——两交点完整标出相邻两缝的真实起止，
    确保车缝尺寸与净样 100% 吻合。净样刀口（后中、有省拼合线 C_in/St_in）
    沿所在边外法向交缝份边界（后中同腰头 §四.2.1「垂线交缝边」口径）。

    交点在毛样折线上求取（缩水 -> 缝边后的权威几何），自动兼容镜像折角；
    射线无命中回退沿射线平移一个缝份（退化防御，缝份 0 时退化为净点本身）。
    """
    base = piece.shrunk_edges or piece.net_edges
    net_notches = piece.shrunk_notches or piece.notches
    poly = piece.gross_polygon
    corners: list[Point] = []
    n = len(base)
    for i in range(n):
        a, b = base[i], base[(i + 1) % n]
        if a.name == b.name:
            continue                          # 同名边平滑续接无角点
        p = _geom_end(a.geom)                 # 角点（a 末端 == b 首端）
        t_a = _edge_tangent(a.geom, True)     # 入边末端切向（延长线方向）
        t_b = _edge_tangent(b.geom, False)    # 出边首端切向（反向延长线方向）
        for d, sa_amt in ((t_a, sa.get(b.name, 0.0)),
                          (t_b.scale(-1.0), sa.get(a.name, 0.0))):
            q = _ray_hit_poly(p, d, poly)
            corners.append(q if q is not None else p + d.scale(sa_amt))
    mid: list[Point] = []
    for p in net_notches:
        t = _nearest_edge_tangent(base, p)
        q = _ray_hit_poly(p, t.perpendicular(), poly)
        mid.append(q if q is not None else p)
    gross = tuple(corners + mid)
    note = (f"刀口：净样角点 ×{len(corners)}（净线延长线交缝边）+ 净刀口法向"
            f"交缝边 ×{len(mid)}（机头裁片.md §5.1）",)
    return piece.with_gross(poly, gross, piece.notes + note)


# ---------- 主入口 ----------

def build_yoke(main_ctx: DraftContext) -> tuple[PatternPiece, DraftContext]:
    """整版跑完后构建后机头/育克裁片：净样 -> 缩水 -> 缝边 -> 刀口（机头裁片.md §2~§5）。

    返回 (PatternPiece, 局部 DraftContext)：前者供 SVG 输出，后者含命名元素供调试。
    """
    o = main_ctx.options
    curved = o.waistband_type is WaistbandType.CURVED
    W = o.waistband_width

    # 四条边界提取（主版坐标，Y 向上）
    P0 = main_ctx.point("back.yoke_cb_point")
    PN = main_ctx.point("back.yoke_side_point")
    hw = main_ctx.curve("back.outseam_hip_waist")                   # t=0 臀 -> t=1 腰 X
    if curved:
        origin = main_ctx.point("back.lower_waist_center_point")    # O'
        top_arc = main_ctx.curve("back.lower_waistline_arc")        # O'->X'
        d_side_total = W + o.back_yoke_side_dist
        t_side_top = hw.t_at_length(hw.length() - W)                # X'（下腰头侧点）
    else:
        origin = main_ctx.point("back.rise_top_point")              # O
        top_arc = main_ctx.curve("back.waistline_arc")              # O->X
        d_side_total = o.back_yoke_side_dist
        t_side_top = 1.0                                            # X
    t_pn = hw.t_at_length(hw.length() - d_side_total)
    side_geom = curves.bezier_subrange(hw, t_pn, t_side_top)        # PN -> X/X'
    cb_geom = LineSegment(origin, P0)
    # 下口链：已上版的 yoke_bottom_seg{i}（P0->PN 有序）；空 anchors+edges 时未上版，
    # 回退为直线 P0->PN（打版流程.md：无控制点即直线，back_yoke_steps 不存该段）
    bottom_chain = _collect_bottom_chain(main_ctx) or [LineSegment(P0, PN)]

    # 净样装配（主版坐标）+ 省处理
    darts = _detect_darts(main_ctx)
    notches_back: list[Point] = []
    if not darts:
        edges_back = _assemble_no_dart(bottom_chain, side_geom, top_arc, cb_geom)
    else:
        res = _assemble_darts(darts, bottom_chain, side_geom, top_arc, cb_geom,
                              o.back_yoke_join_fillet)
        if res is None:
            print("警告：后省未穿越机头上下边界或省位交乱 -> 回退无省提取",
                  file=sys.stderr)
            edges_back = _assemble_no_dart(bottom_chain, side_geom, top_arc, cb_geom)
        else:
            edges_back, notches_back = res

    # 后中刀口（左右对称片拼合中心，§5.1）；有省另加拼合线刀口
    notches_back.append(origin.lerp(P0, 0.5))

    # 变换到裁片局部坐标（180° 保向旋转 -> Y 向下）
    local_edges = [PieceEdge(name, _to_local_geom(g, origin))
                   for name, g in edges_back]
    local_notches = tuple(_to_local_point(p, origin) for p in notches_back)

    # 丝缕线（局部坐标，经向=局部 Y=后片裤长向，§3.1 关联布纹）：竖向贯穿
    xs = [p.x for e in local_edges for p in _edge_sample(e.geom)]
    ys = [p.y for e in local_edges for p in _edge_sample(e.geom)]
    cx = (min(xs) + max(xs)) / 2
    y0, y1 = min(ys), max(ys)
    margin = (y1 - y0) * 0.15
    grain = LineSegment(Point(cx, y0 + margin), Point(cx, y1 - margin))

    piece = PatternPiece("back_yoke", "后育克裁片", tuple(local_edges),
                         notches=local_notches, grain=grain,
                         origin=origin, frame="rot180")

    # 裁切三段：缩水 -> 缝边（缝份不叠加缩水，§5）
    # 经向=局部 Y（后片裤长向）-> Y 吃 warp、X 吃 weft（同腰头 WIDTH 映射：
    # apply_shrinkage 形参 1 控 X、2 控 Y）
    # 机头裁片专用缩水（None=回退全局 shrinkage_warp/weft）
    warp, weft = o.shrinkage_rates(o.back_yoke_shrinkage_warp,
                                   o.back_yoke_shrinkage_weft)
    piece = apply_shrinkage(piece, weft, warp)
    sa = {"top": o.back_yoke_seam_allowances.top,
          "bottom": o.back_yoke_seam_allowances.bottom,
          "cb": o.back_yoke_seam_allowances.cb,
          "side": o.back_yoke_seam_allowances.side}
    # 镜像折角（键 = (折线边, 被镜像边)，首元素 bottom 为翻折折线边）：内缝顶点
    # (bottom, side) 与后中底角 (bottom, cb) 各自独立开关，使相邻缝份翻折后与裁片
    # 重合（机头裁片.md §4.2.1）。两角均斜角，镜像与 miter 相异；cutter 序后中角以
    # (cb, bottom) 出现，逆序键命中时 cutter 自动交换 _mirror_point 形参。
    corners = {}
    if o.back_yoke_side_corner_mirror:
        corners[("bottom", "side")] = "mirror"
    if o.back_yoke_cb_corner_mirror:
        corners[("bottom", "cb")] = "mirror"
    piece = add_seam_allowance(piece, sa, corners or None)
    # 刀口毛样位（§5.1）：净样角点沿净线延长线交缝边、净刀口（后中/省位）沿
    # 外法向交缝边，整体替换毛样刀口（缝合线位净刀口保留在 shrunk_notches）
    piece = _project_notches_to_sa(piece, sa)

    # 局部 ctx 留命名元素供 trace/调试
    local = DraftContext(main_ctx.measurements, o)
    for i, e in enumerate(local_edges):
        if isinstance(e.geom, LineSegment):
            local.add_line(f"yoke.edge{i}", e.geom, step="build_yoke",
                           basis=f"机头净样边 {e.name}", label=f"机头{e.name}边{i}")
        else:
            local.add_curve(f"yoke.edge{i}", e.geom, step="build_yoke",
                            basis=f"机头净样边 {e.name}", label=f"机头{e.name}边{i}")
    return piece, local


def _edge_sample(g: LineSegment | CubicBezier) -> list[Point]:
    if isinstance(g, LineSegment):
        return [g.a, g.b]
    return g.sample(24)
