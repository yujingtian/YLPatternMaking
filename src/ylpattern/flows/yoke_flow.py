"""后机头/育克裁片流程：净样提取 -> 缩水 -> 缝边（机头裁片.md §2~§5）。

build_yoke(main_ctx) 从整版 ctx 提取机头四条边界（腰口/底边/后中/侧缝），在主版
坐标系（Y 向上）装配净样闭合轮廓，经 _to_local 180° 旋转变换到裁片局部坐标系
（Y 向下、与腰头裁片同口径、SVG 不翻转即正放），再走 cutter 三段处理产出
PatternPiece。自含裁片，非 FlowRunner 编排（同 waistband_flow.build_waistband 口径）。

两种提取模式（机头裁片.md §2）：
  - 无省（§2.1）：直接复制四条边界围成的封闭区。
  - 有省（§2.2，仅 1 省）：省（等腰三角）把机头切成左右两片 -> 右片绕省尖旋转
    闭合拼合 -> 拼合处上下折角 G1 倒圆（§2.2.3）。
  2 省或省未穿越机头边界 -> 回退无省提取（告警）。

cutter 负面积约定：净多边形顶点序 P0->PN->X->O（底边->侧缝->腰口->后中）在
本坐标系符号面积为负（180° 旋转变换保向），cutter 外法向正确外扩。
"""

from __future__ import annotations

import math
import sys

from ..cutter import add_seam_allowance, apply_shrinkage
from ..draft import DraftContext, curves
from ..geometry import CubicBezier, LineSegment, Point
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
    """线段与三次贝塞尔的交点：采样定位符号变号段 + 二分，再校核交点落在线段内。

    返回 (交点, t_on_bezier)；线段与曲线无交点（或交点不在线段范围内）返回 None。
    """
    d = leg.b - leg.a
    nx, ny = -d.dy, d.dx                           # 线段所在直线的法向量

    def dist(p: Point) -> float:                   # 点到直线的代数距离（法向点积）
        return (p.x - leg.a.x) * nx + (p.y - leg.a.y) * ny

    pts = bez.sample(n)
    dists = [dist(p) for p in pts]
    for i in range(n):
        if dists[i] * dists[i + 1] > 0:
            continue                               # 同侧未跨越直线
        lo, hi = i / n, (i + 1) / n
        flo = dists[i]
        for _ in range(60):                        # 二分逼近法向距离零点
            mid = (lo + hi) / 2
            fm = dist(bez.point_at(mid))
            if abs(fm) <= 1e-12:
                break
            if flo * fm <= 0:
                hi = mid
            else:
                lo = mid
                flo = fm
        t = (lo + hi) / 2
        p = bez.point_at(t)
        # 校核交点在 leg 线段内（沿 leg 方向投影参数 ∈ [0,1]）
        ll = d.dx * d.dx + d.dy * d.dy
        along = ((p.x - leg.a.x) * d.dx + (p.y - leg.a.y) * d.dy) / ll
        if -1e-9 <= along <= 1 + 1e-9:
            return p, t
    return None


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


def _g1_fillet(geom_in: LineSegment | CubicBezier,
               geom_out: LineSegment | CubicBezier, delta: float
               ) -> tuple[LineSegment | CubicBezier, CubicBezier, LineSegment | CubicBezier]:
    """两同族边在连接点（geom_in 末端 == geom_out 首端）处 G1 倒圆（§2.2.3）。

    入/出边各沿弧长退 d=delta（钳制不超半长），插三次贝塞尔，端切向与两侧边一致。
    返回 (收缩后的入边, 倒圆贝塞尔, 收缩后的出边)。d=0 时倒圆退化为连接两点。
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
    h = d if d > 0 else 0.05                        # 手柄长（d=0 给极小量避免退化）
    fillet = CubicBezier(P, P + t_in.scale(h), Q + t_out.scale(-h), Q)
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


def _detect_dart(ctx: DraftContext):
    """检测已上版的后省：返回 (省号, 省尖, 内侧腿, 外侧腿) / None（无省）/
    "fallback"（2 省回退无省提取）。"""
    drawn = [i for i in (1, 2) if f"back.dart{i}_apex" in ctx.sheet]
    if not drawn:
        return None
    if len(drawn) >= 2:
        return "fallback"
    i = drawn[0]
    apex = ctx.point(f"back.dart{i}_apex")
    leg_inner = ctx.line(f"back.dart{i}_leg_inner")     # LineSegment(省尖, p_in)
    leg_outer = ctx.line(f"back.dart{i}_leg_outer")     # LineSegment(省尖, p_out)
    return i, apex, leg_inner, leg_outer


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


def _assemble_dart(dart, bottom_chain: list, side_geom: CubicBezier,
                   top_arc: CubicBezier, cb_geom: LineSegment, delta: float
                   ) -> tuple[list[tuple[str, object]], list[Point]] | None:
    """有省（1 省）净样边：切开 -> 右片绕省尖旋转闭合 -> 拼合处 G1 倒圆（§2.2）。

    返回 (edges, notches) 或 None（省腿未穿越上下边界 -> 调用方回退无省）。
    """
    _i, apex, leg_inner, leg_outer = dart
    p_in = leg_inner.b                                # 省口内侧（后中侧）
    p_out = leg_outer.b                               # 省口外侧（侧缝侧）

    # 上下边界穿越点
    cin = _chain_cross(bottom_chain, leg_inner)
    cout = _chain_cross(bottom_chain, leg_outer)
    sin = _seg_geom_intersect(leg_inner, top_arc)
    sout = _seg_geom_intersect(leg_outer, top_arc)
    if cin is None or cout is None or sin is None or sout is None:
        return None                                   # 省未切穿机头 -> 回退无省
    C_in = cin[2]
    St_in, t_st_in = sin
    _St_out, t_st_out = sout

    # 旋转角：把 (p_out-apex) 转到 (p_in-apex) 的有向角（等腰省 -> p_out 精确落 p_in）
    v_out = p_out - apex
    v_in = p_in - apex
    theta = math.degrees(math.atan2(
        v_out.dx * v_in.dy - v_out.dy * v_in.dx,
        v_out.dx * v_in.dx + v_out.dy * v_in.dy))

    # 右子轮廓（侧缝侧，旋转闭合）
    bottom_right = [_rotate_geom(g, apex, theta)
                    for g in _chain_suffix(bottom_chain, cout)]   # C_out->PN 旋后
    side_r = _rotate_geom(side_geom, apex, theta)                 # PN->X 旋后
    top_right_sub_r = _rotate_geom(
        curves.bezier_subrange(top_arc, t_st_out, 1.0), apex, theta)  # St_out->X 旋后
    top_right = [_reverse_bezier(top_right_sub_r)]                # X->St_out 旋后

    # 左子轮廓（后中侧，固定）
    bottom_left = _chain_prefix(bottom_chain, cin)                # P0->C_in
    top_left = _reverse_bezier(
        curves.bezier_subrange(top_arc, 0.0, t_st_in))            # St_in->origin

    # 对齐拼合顶点（端点平移、保切向、不传至下游连接）
    bottom_right[0] = _snap_geom_start(bottom_right[0], C_in)     # C_out' -> C_in
    top_right[-1] = _snap_geom_end(top_right[-1], St_in)          # St_out' -> St_in

    edges: list[tuple[str, object]] = []

    def _join(name: str, left_geoms: list, right_geoms: list):
        """同族边在 join 点 G1 倒圆拼接（delta>0）；delta=0 直接顺接。"""
        if delta > 0:
            tin, fillet, tout = _g1_fillet(left_geoms[-1], right_geoms[0], delta)
            for g in left_geoms[:-1]:
                edges.append((name, g))
            edges.append((name, tin))
            edges.append((name, fillet))
            edges.append((name, tout))
            for g in right_geoms[1:]:
                edges.append((name, g))
        else:
            for g in left_geoms:
                edges.append((name, g))
            for g in right_geoms:
                edges.append((name, g))

    # 底边：左下口 + 倒圆(C) + 右下口（均 bottom，cutter 平滑相接）
    _join("bottom", bottom_left, bottom_right)
    # 侧缝：PN' -> Xr（旋转后）
    edges.append(("side", side_r))
    # 腰口：右上口 + 倒圆(St) + 左上口（均 top）
    _join("top", top_right, [top_left])
    # 后中：origin -> P0
    edges.append(("cb", cb_geom))

    notches = [C_in, St_in]        # 拼合线两端刀口（标省位）
    return edges, notches


# ---------- 主入口 ----------

def build_yoke(main_ctx: DraftContext) -> tuple[PatternPiece, DraftContext]:
    """整版跑完后构建后机头/育克裁片：净样 -> 缩水 -> 缝边（机头裁片.md §2~§5）。

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
    dart = _detect_dart(main_ctx)
    notches_back: list[Point] = []
    if dart == "fallback":
        print("警告：后机头裁片当前仅支持 1 省，检测到多省 -> 回退无省提取",
              file=sys.stderr)
        edges_back = _assemble_no_dart(bottom_chain, side_geom, top_arc, cb_geom)
    elif dart is None:
        edges_back = _assemble_no_dart(bottom_chain, side_geom, top_arc, cb_geom)
    else:
        res = _assemble_dart(dart, bottom_chain, side_geom, top_arc, cb_geom,
                             o.back_yoke_join_fillet)
        if res is None:
            print("警告：后省未穿越机头上下边界（省在机头内部不分割）-> 回退无省提取",
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
                         notches=local_notches, grain=grain)

    # 裁切三段：缩水 -> 缝边（缝份不叠加缩水，§5）
    # 经向=局部 Y（后片裤长向）-> Y 吃 warp、X 吃 weft（同腰头 WIDTH 映射：
    # apply_shrinkage 形参 1 控 X、2 控 Y）
    # 机头裁片专用缩水（None=回退全局 shrinkage_warp/weft）
    warp = (o.back_yoke_shrinkage_warp
            if o.back_yoke_shrinkage_warp is not None else o.shrinkage_warp)
    weft = (o.back_yoke_shrinkage_weft
            if o.back_yoke_shrinkage_weft is not None else o.shrinkage_weft)
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
