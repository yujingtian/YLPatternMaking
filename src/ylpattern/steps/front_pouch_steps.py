"""袋布绘制步骤：嵌入式前口袋储物袋布大片/小片（袋布绘制.md §一~§五）。

拓扑：袋布 = 固定组合边界（严密拼合裤身腰弧/侧缝弧）+ 自由形态边界
（自定义内部节点链 K1..Kn）：
  大片闭合路径 P_w0 → K1..Kn → P_s0 →（侧缝弧）→ O →（腰弧）→ P_w0
  小片 = 主切口起止点 → K1..Kn（与大片 1:1 重合）→ 沿袋口切削线闭合
边界锚点：
  P_w0 腰缝接触锚点——腰弧上自 P1 朝门襟方向沿弧内延 ΔW_safe
  （实现口径为沿弧弧长，文档 §二.1 写的是 x 偏移，同向等价近似）；
  P_s0 侧缝接触锚点——自 P2 垂直下探 ΔH_safe，落在外缝链
  （外缝弧或其下段大腿外缝弧，按高度自动选择）。
边形态三模式（§三.2）：line 直线 / arc 弧高式（弧高 + 弧顶分位）/
  bezier 双手柄（起止夹角 + 弦长比）。
小片袋口 10mm 内翻止口缝边按先画后裁口径留待裁切层（§五）。
"""

from __future__ import annotations

from ..draft import DraftContext, NamedCurve, NamedLine
from ..draft import curves
from ..geometry import CubicBezier, LineSegment, Point

_STEP = "draw_front_pouch"


def _edge_geom(a: Point, b: Point, spec: tuple) -> LineSegment | CubicBezier:
    """相邻节点间连线（袋布绘制.md §三.2 三种模式）。"""
    mode = spec[0]
    if mode == "line":
        return LineSegment(a, b)
    if mode == "arc":                       # 弧高 + 弧顶分位
        return curves.arc_through(a, b, bulge=spec[1], bulge_at=spec[2])
    # bezier：C1 = A + κ1·L0·û(α)，C2 = B + κ2·L0·û(β)，û 为弦向单位向量旋转
    chord = b - a
    l0 = chord.length
    u = chord.normalized()
    c1 = a + u.rotate(spec[1]).scale(spec[2] * l0)
    c2 = b + u.rotate(spec[3]).scale(spec[4] * l0)
    return CubicBezier(a, c1, c2, b)


def _emit_chain(ctx: DraftContext, prefix: str, pts: list[Point],
                edges: tuple, label_prefix: str) -> None:
    """按边形态列表逐段上版节点链（直线为 NamedLine，弧线为 NamedCurve）。"""
    for i, spec in enumerate(edges, 1):
        a, b = pts[i - 1], pts[i]
        geom = _edge_geom(a, b, spec)
        basis = f"{label_prefix}第 {i} 段（{spec[0]}，袋布绘制.md §三.2）"
        if isinstance(geom, LineSegment):
            ctx.add_line(f"{prefix}_seg{i}", geom, step=_STEP,
                         basis=basis, label=f"{label_prefix}{i}段",
                         role="struct")
        else:
            ctx.add_curve(f"{prefix}_seg{i}", geom, step=_STEP,
                          basis=basis, label=f"{label_prefix}{i}段")


def draw_front_pouch(ctx: DraftContext) -> NamedLine | NamedCurve | None:
    """前口袋储物袋布（打版流程.md「袋布打版过程」，可选步骤）：
    开关 front_pouch 开启才绘制；依赖前口袋主切口（front_pocket），
    未开则报错。

    大片（§五.1）：P_w0 → K1..Kn → P_s0 → 侧缝弧 → O → 腰弧 → P_w0，
    固定边界取腰弧/外缝弧的精确子段（de Casteljau 细分），与裁片缝线重合；
    自由边界为自定义节点链，逐边形态由 front_pouch_edges 控制。
    小片（§五.2）：与大片同锚点、同节点链（1:1 重合的两层），上沿改经
    侧缝子段（P_s0→P2）→ 袋口切削线（P2→P1′）→ 腰弧子段（P1′→P_w0）
    闭合——节点只与袋布相连，不直连口袋顶点。
    依据：打版流程.md「袋布打版过程」；袋布绘制.md §二、§三、§五。
    """
    o = ctx.options
    if not o.front_pouch:
        return None                         # 开关关闭，可选步骤跳过
    if "front.pocket_p1" not in ctx.sheet:
        raise ValueError("袋布绘制依赖前口袋主切口，请先开启 front_pocket"
                         "（打版流程.md：只有嵌入式口袋才需要绘制袋布）")

    b = ctx.point("front.waist_side_point")     # O：腰侧交点（局部原点）
    w_arc = ctx.curve("front.waistline_arc")
    s_arc = ctx.curve("front.outseam_arc")
    p1 = ctx.point("front.pocket_p1")
    p2 = ctx.point("front.pocket_p2")

    # 边界锚点 P_w0：腰弧上越过 P1 朝门襟沿弧内延 ΔW_safe（§二.1）
    lw = w_arc.length()
    s_w0 = o.front_pocket_p1_dist + o.front_pouch_waist_safe
    if s_w0 >= lw:
        raise ValueError(
            f"腰缝锚点弧长（P1 距禈 {o.front_pocket_p1_dist} + 安全内延 "
            f"{o.front_pouch_waist_safe}）超过腰弧总长 {lw:.2f}")
    t_w0 = w_arc.t_at_length(s_w0)
    p_w0 = w_arc.point_at(t_w0)

    # 边界锚点 P_s0：自 P2 垂直下探 ΔH_safe，落在外缝链上（§二.2）；
    # 高于臀围线在外缝弧，否则在大腿外缝弧（t=0 臀围外缝顶点 → t=1 膝围点）
    y_s0 = p2.y - o.front_pouch_side_safe
    hip_y = ctx.line("front.hip_line").a.y
    # P2 在外缝弧 s_arc 上的参数（t=0 臀围外缝顶点 → t=1 腰外缝顶点 B）
    t_p2 = s_arc.t_at_y(p2.y)
    # 大片侧缝边界 P_s0 → B、小片侧缝边界 P_s0 → P2（均沿外缝链向上）
    large_side_segs: list[tuple[str, CubicBezier]] = []
    small_side_segs: list[CubicBezier] = []
    if y_s0 >= hip_y:
        t_s0 = s_arc.t_at_y(y_s0)
        p_s0 = s_arc.point_at(t_s0)
        large_side_segs.append(("front.pouch_side_edge",
                                _bezier_subrange(s_arc, t_s0, 1.0)))
        small_side_segs.append(_bezier_subrange(s_arc, t_s0, t_p2))
    else:
        upper = ctx.curve("front.outseam_upper")
        t_u = upper.t_at_y(y_s0)
        p_s0 = upper.point_at(t_u)
        # P_s0 → 臀围外缝顶点（大腿外缝弧反向子段），再 → B / → P2（外缝弧子段）
        rev_upper = _reverse_bezier(upper.split(t_u)[0])      # P_s0 → 臀围外缝顶点
        large_side_segs.append(("front.pouch_side_edge_thigh", rev_upper))
        large_side_segs.append(("front.pouch_side_edge_hip", s_arc))
        small_side_segs.append(rev_upper)
        small_side_segs.append(s_arc.split(t_p2)[0])          # 臀围外缝顶点 → P2

    # 自定义内部节点：相对 O 的（dx, dy向下为正）→ 全局坐标
    ks = [Point(b.x + dx, b.y - dy) for dx, dy in o.front_pouch_nodes]

    ctx.add_point("front.pouch_waist_anchor", p_w0,
                  step=_STEP,
                  basis=f"腰弧上越过 P1 沿弧内延 {o.front_pouch_waist_safe}"
                        "（安全内延，袋布绘制.md §二.1）",
                  label="腰缝接触锚点Pw0")
    ctx.add_point("front.pouch_side_anchor", p_s0,
                  step=_STEP,
                  basis=f"自 P2 沿侧缝下探 {o.front_pouch_side_safe}"
                        "（安全垂深，袋布绘制.md §二.2）",
                  label="侧缝接触锚点Ps0")
    for i, k in enumerate(ks, 1):
        ctx.add_point(f"front.pouch_node{i}", k,
                      step=_STEP,
                      basis=f"自定义节点 K{i}（相对 O "
                            f"{o.front_pouch_nodes[i - 1]}，§三.1）",
                      label=f"袋布节点K{i}")

    # 大片：节点链 + 固定边界（侧缝链 P_s0→B → 腰弧 B→P_w0）
    _emit_chain(ctx, "front.pouch_large", [p_w0, *ks, p_s0],
                o.front_pouch_edges, "大片节点链")
    for name, geom in large_side_segs:
        ctx.add_curve(name, geom,
                      step=_STEP,
                      basis="侧缝固定边界：外缝链子段 P_s0→B（与大身侧缝重合，§一）",
                      label="大片侧缝边")
    ctx.add_curve("front.pouch_large_waist_edge", w_arc.split(t_w0)[0],
                  step=_STEP,
                  basis="腰缝固定边界：腰弧 B→P_w0 子段（与大身腰弧重合，§一）",
                  label="大片腰缝边")

    # 小片：与大片同锚点同节点链（1:1 重合），上沿改经侧缝链 P_s0→P2 →
    # 袋口切削线 P2→P1′ → 腰弧 P1→P_w0 闭合（§五.2）——节点只与袋布相连
    _emit_chain(ctx, "front.pouch_small", [p_w0, *ks, p_s0],
                o.front_pouch_edges, "小片节点链")
    for i, geom in enumerate(small_side_segs, 1):
        ctx.add_curve(f"front.pouch_small_side_seg{i}", geom,
                      step=_STEP,
                      basis=f"小片上沿侧缝子段 {i}（与大身侧缝重合，§五.2）",
                      label=f"小片侧缝边{i}")
    # 袋口切削线 P2 → P1′（引用主切口几何并反向）
    for name, rev in _mouth_segments_reversed(ctx):
        ctx.add_curve(f"front.pouch_small_{name}", rev,
                      step=_STEP,
                      basis="袋口切削线（引用主切口几何反向；10mm 止口留待裁切层，§五.2）",
                      label="小片袋口边")
    # 腰弧子段 P1 → P_w0（P1′ 与 P1 同在腰弧上）
    t_p1 = w_arc.t_at_y(p1.y)
    small_waist = _bezier_subrange(w_arc, t_p1, t_w0)
    ctx.add_curve("front.pouch_small_waist_edge", small_waist,
                  step=_STEP,
                  basis="小片上沿腰弧子段 P1→P_w0（与大身腰弧重合，§五.2）",
                  label="小片腰缝边")
    return ctx.sheet.get("front.pouch_large_seg1")


def _reverse_bezier(c: CubicBezier) -> CubicBezier:
    """反向三次贝塞尔（p0↔p3、p1↔p2）。"""
    return CubicBezier(c.p3, c.p2, c.p1, c.p0)


def _mouth_segments_reversed(ctx) -> list[tuple[str, CubicBezier]]:
    """主切口切削线段（弧线或折角多段直线），统一反向为 P2→P1′ 的曲线列表。

    直线段升阶为退化的三次贝塞尔（控制点与端点重合），便于统一上版为
    NamedCurve。
    """
    out: list[tuple[str, CubicBezier]] = []
    if "front.pocket_mouth" in ctx.sheet:
        out.append(("mouth_seg1", _reverse_bezier(ctx.curve("front.pocket_mouth"))))
        return out
    i = 1
    segs: list[LineSegment] = []
    while f"front.pocket_mouth_seg{i}" in ctx.sheet:
        segs.append(ctx.line(f"front.pocket_mouth_seg{i}"))
        i += 1
    # 折角链 P1′→…→P2 反向为 P2→…→P1′
    for j, seg in enumerate(reversed(segs), 1):
        a, b = seg.b, seg.a
        out.append((f"mouth_seg{j}", CubicBezier(a, a, b, b)))
    return out


def _bezier_subrange(c: CubicBezier, ta: float, tb: float) -> CubicBezier:
    """取曲线参数 [ta, tb] 子段（两次 split 组合）。"""
    if ta <= 0.0 and tb >= 1.0:
        return c
    if ta <= 0.0:
        return c.split(tb)[0]
    if tb >= 1.0:
        return c.split(ta)[1]
    _, second = c.split(ta)
    return second.split((tb - ta) / (1.0 - ta))[0]
