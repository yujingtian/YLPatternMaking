"""前片独立裁片测试（前片裁片.md §1~§3）。

金标（W=70, H=96, K=46, B=36, 前浪 25, 后浪 33, 裤长 102, 大腿围 58，
Δ=1.0 默认；腰头 2 形态 × 口袋 3 形态 × 门襟 3 形态 = 18 组合）：
  §1 净边装配条件矩阵：闭合（1e-6）、shoelace<0（cutter 外法向）、
    waist 末点 == A（直腰头）/A′（弯腰头，下腰头线剥离，§1.1）；
    口袋挖削：side 弧段末点 == P2、mouth 链末点 == P1′（有省）/P1（无省），
    P1（有省时）不上版边界（挖除区撇削边 pocket_cut_start 排除，§1.2）；
    连裁门襟：fly 四元素并入链首、毛样右界外扩（门襟延伸包含，§1.3）；
    独立门襟与无门襟同形（fly_sep_* 为叠画元素不进边界）。
  §2.1 边长独立复算（从 ctx 元素 t_at_length/bezier_subrange 同式重算，不硬编）。
  §2.2 裆尖角部：True = mirror（== _mirror_point 复算角点）、False = 纯
    尖角跟随净样（== _natural_join_sharp 复算外延链 ∈ 毛样：两侧缝边按
    贝塞尔多项式自然外延求交成尖，裆尖尖角保留、无阶梯断点、不抹圆）。
  §2.3 刀口法向投影：全部 ∈ 毛样外沿（1e-6）；膝围双刀口距净点 == sa_side
    且 ⟂ 切线（绝对精准）；拉链止口 == 外缘链 point_along_chain(L)；
    刀口数按矩阵（膝2+臀1+脚口2+毗围1 基底，口袋 +2、连裁 +1、d>0 毗围内端 +1）。
  §3.1 丝缕竖向；§3.2 缩水 None 回退全局 / 局部生效；§3.3 内部辅助线：
    臀/膝/毗围水平线截断（端点 ∈ 净边链、fly 组臀线右端落门襟外线），
    marks 随缩水同比例变换（净样 /(1-weft, 1-warp)）。
断言口径：几何不变量 + 独立复算，同 test_back_patch_piece。
"""

import itertools

import pytest

from ylpattern.cutter import _miter_point, _mirror_point, edge_length
from ylpattern.exporters.piece_svg import render_piece_svg
from ylpattern.flows.back_flow import FULL_FLOW
from ylpattern.flows.front_piece_flow import build_front_piece
from ylpattern.flows.runner import FlowRunner
from ylpattern.geometry import CubicBezier, LineSegment, Point, Vector
from ylpattern.params import (FrontSeamAllowances, Measurements,
                              PatternOptions, WaistbandType)
from ylpattern.steps.front_steps import effective_waist

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
M_NO_THIGH = Measurements(waist=70, hip=96, knee=46, hem=36,
                          front_rise=25, back_rise=33, outseam=102)

SA = FrontSeamAllowances()                      # 默认缝份金标


def _start(g): return g.a if isinstance(g, LineSegment) else g.p0
def _end(g):   return g.b if isinstance(g, LineSegment) else g.p3
def _sample(g, n=32):
    return [g.a, g.b] if isinstance(g, LineSegment) else g.sample(n)
def _tan(g, at_end):
    v = (g.b - g.a) if isinstance(g, LineSegment) else g.tangent_at(1.0 if at_end else 0.0)
    return v.normalized()


def _run(m=M, **kw):
    return FlowRunner(m, PatternOptions(**kw)).run(FULL_FLOW)


def _build(m=M, **kw):
    ctx = _run(m, **kw)
    piece, local = build_front_piece(ctx)
    return ctx, piece, local


def _b(ctx):
    """局部原点：直腰头 B / 弯腰头 B′（与 effective_waist 同口径）。"""
    curved = ctx.options.waistband_type is WaistbandType.CURVED
    return ctx.point("front.lower_waist_side_point" if curved
                     else "front.waist_side_point")


def _loc(p, b):
    return Point(p.x - b.x, b.y - p.y)


def _signed_area(piece) -> float:
    poly = []
    for e in piece.net_edges:
        poly += _sample(e.geom)
    s = 0.0
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        s += a.x * b.y - b.x * a.y
    return s


def _assert_closed(piece, *, tol=1e-6):
    ne = piece.net_edges
    for i in range(len(ne)):
        a = _end(ne[i].geom)
        b = _start(ne[(i + 1) % len(ne)].geom)
        assert a.distance_to(b) < tol, f"轮廓在边 {i} 处断开：{a} -> {b}"


def _assert_outward(piece):
    """毛样 bbox 不窄于净样（外法向正确外扩）。"""
    nxs, nys = [], []
    for e in piece.net_edges:
        for p in _sample(e.geom):
            nxs.append(p.x); nys.append(p.y)
    gxs = [p.x for p in piece.gross_polygon]
    gys = [p.y for p in piece.gross_polygon]
    assert max(gxs) >= max(nxs) - 1e-9
    assert min(gxs) <= min(nxs) + 1e-9
    assert max(gys) >= max(nys) - 1e-9
    assert min(gys) <= min(nys) + 1e-9


def _seg_dist(p, a, b):
    v = b - a
    l2 = v.dx * v.dx + v.dy * v.dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p.x - a.x) * v.dx + (p.y - a.y) * v.dy) / l2))
    return p.distance_to(a + v.scale(t))


def _chain_dist(p, geoms, n=256, tol=1e-3):
    """点到净边链折线（n 密采样）的距离（marks 端点 ∈ 链上用）。"""
    best = float("inf")
    for g in geoms:
        pts = _sample(g, n)
        for a, b in zip(pts, pts[1:]):
            best = min(best, _seg_dist(p, a, b))
    assert best < tol, f"点 {p} 距净边链 {best:.2e} 超差"


def _edges_by_name(piece):
    groups: dict[str, list] = {}
    for e in piece.net_edges:
        groups.setdefault(e.name, []).append(e.geom)
    return groups


WBS = [WaistbandType.STRAIGHT, WaistbandType.CURVED]
PKS = [({}, "无口袋"),
       ({"front_pocket": True, "front_pocket_dart_width": 0.0}, "口袋无省"),
       ({"front_pocket": True}, "口袋有省")]      # 默认 dw=2.0
FLS = [({}, "无门襟"), ({"fly": True}, "连裁门襟"), ({"fly_separate": True}, "独立门襟")]
COMBOS = [(wb, {**pk, **fl}, f"{wb.name}-{pkid}-{flid}")
          for wb, (pk, pkid), (fl, flid)
          in itertools.product(WBS, PKS, FLS)]


def _expected_notch_count(pk_kw, fly_on):
    base = 6          # 膝围×2 + 臀围 + 脚口×2 + 毗围外缝点（thigh=58 录入）
    return base + (2 if pk_kw.get("front_pocket") else 0) + (1 if fly_on else 0)


# ---------- §1 条件矩阵：18 组合闭合/定向/结构/渲染 ----------

@pytest.mark.parametrize("wb,kw,cid", COMBOS,
                         ids=[c[2] for c in COMBOS])
def test_matrix_closure_structure(wb, kw, cid):
    """18 组合：闭合 1e-6、shoelace<0、毛样 bbox ⊇ 净样、毛样/刀口非空、
    边名结构（waist/side/hem/inseam 恒定段数、rise ∈ {1,2}、mouth 段数、
    fly_* 仅连裁）、刀口数按矩阵、render 冒烟。"""
    ctx, piece, local = _build(waistband_type=wb, **kw)
    _assert_closed(piece)
    assert _signed_area(piece) < 0
    _assert_outward(piece)
    assert len(piece.gross_polygon) >= 3
    assert len(piece.gross_notches) == _expected_notch_count(
        kw, ctx.options.fly and not ctx.options.fly_separate)

    names = [e.name for e in piece.net_edges]
    g = _edges_by_name(piece)
    assert {"waist", "rise", "inseam", "hem", "side"} <= set(names)
    assert len(g["waist"]) == 1
    assert len(g["side"]) == 3                 # 侧缝弧上段 + 大腿弧 + 小腿弧
    assert len(g["inseam"]) == 2
    assert len(g["hem"]) == 1
    assert len(g["rise"]) in (1, 2)
    fly_on = ctx.options.fly and not ctx.options.fly_separate
    if fly_on:
        assert len(g["fly_top"]) == 1 and len(g["fly_outer"]) == 1
        assert len(g["fly_bottom"]) == 2       # 角弧 + 融合弧同名 G1 平滑续接
    else:
        assert not any(n.startswith("fly_") for n in names)
    if kw.get("front_pocket"):
        assert len(g["mouth"]) == 1            # bulge 模式默认单边
    else:
        assert "mouth" not in g

    assert render_piece_svg(piece) .startswith("<svg")
    # 局部 ctx 命名元素（trace/调试用）
    assert sum(1 for _ in local.sheet) == len(piece.net_edges)
    for i in range(len(piece.net_edges)):
        assert f"front_piece.edge{i}" in local.sheet


# ---------- §1.1/§1.2/§1.3 端点金标（链首 waist / P2 / P1′/P1 / fly_top）----------
# 片上存向 = 自定向后的 CW 序：[waist: A/A′->P1′/B, mouth: P1′->P2,
#   side arc: P2/B->hip, side 上/下段, hem, inseam 下/上段, rise: crotch->A/A′
#   （连裁时 rise 余段后接 fly_bottom/fly_outer/fly_top 环回 A/A′）]

@pytest.mark.parametrize("wb,kw,cid", COMBOS, ids=[c[2] for c in COMBOS])
def test_endpoint_golden(wb, kw, cid):
    ctx, piece, _ = _build(waistband_type=wb, **kw)
    b = _b(ctx)
    curved = wb is WaistbandType.CURVED
    a_name = "front.lower_waist_center_point" if curved else "front.rise_top_point"
    a_pt = _loc(ctx.point(a_name), b)          # A（直腰头裤身顶边）/ A′（弯腰头）

    ne = list(piece.net_edges)
    wi = next(i for i, e in enumerate(ne) if e.name == "waist")
    waist = ne[wi].geom
    prev = ne[(wi - 1) % len(ne)]              # 环回边：rise 末段 / fly_top
    assert _start(waist).distance_to(a_pt) < 1e-9
    assert _end(prev.geom).distance_to(a_pt) < 1e-9
    assert prev.name == ("fly_top" if (kw.get("fly") and not kw.get("fly_separate"))
                         else "rise")
    # waist 末点 = 局部原点 B/B′（无口袋）或袋口顶锚 P1′/P1（有口袋）
    top_end = _end(waist)
    nxt = ne[(wi + 1) % len(ne)]
    hip_out = _loc(ctx.point("front.hip_outseam_point"), b)

    if kw.get("front_pocket"):
        p2 = _loc(ctx.point("front.pocket_p2"), b)
        p1_name = ("front.pocket_p1_transfer"
                   if ctx.options.front_pocket_dart_width > 0 else "front.pocket_p1")
        p1 = _loc(ctx.point(p1_name), b)
        assert top_end.distance_to(p1) < 1e-9
        assert nxt.name == "mouth" and _start(nxt.geom).distance_to(p1) < 1e-9
        mi = wi + 1 + len(_edges_by_name(piece)["mouth"]) - 1
        assert _end(ne[mi].geom).distance_to(p2) < 1e-9
        arc = ne[(mi + 1) % len(ne)]           # 紧随 mouth 的侧缝弧上段
        assert arc.name == "side" and _start(arc.geom).distance_to(p2) < 1e-9
        assert _end(arc.geom).distance_to(hip_out) < 1e-9
        if ctx.options.front_pocket_dart_width > 0:
            # 有省：P1 属挖除区（pocket_cut_start 撇削边），不得出现在边界
            cut = _loc(ctx.point("front.pocket_p1"), b)
            for e in piece.net_edges:
                for p in _sample(e.geom, 16):
                    assert p.distance_to(cut) > 0.5
    else:
        assert top_end.distance_to(Point(0.0, 0.0)) < 1e-9   # B/B′ 局部原点
        assert nxt.name == "side" and _start(nxt.geom).distance_to(top_end) < 1e-9
        assert _end(nxt.geom).distance_to(hip_out) < 1e-9
        assert "mouth" not in _edges_by_name(piece)


# ---------- §2.1 边长独立复算（从 ctx 元素同式重算，不硬编坐标）----------

@pytest.mark.parametrize("wb,kw,cid", COMBOS, ids=[c[2] for c in COMBOS])
def test_edge_lengths(wb, kw, cid):
    from ylpattern.draft import curves
    from ylpattern.formulas import fly as fly_f
    ctx, piece, _ = _build(waistband_type=wb, **kw)
    o = ctx.options
    curved = wb is WaistbandType.CURVED
    _, w_arc, s_side = effective_waist(ctx)
    s_arc = ctx.curve("front.outseam_arc")
    has_pk = bool(kw.get("front_pocket"))
    has_fly = o.fly and not o.fly_separate
    g = _edges_by_name(piece)

    def total(name):
        return sum(edge_length(x) for x in g[name])

    # 侧缝弧上段：无口袋截到 B/B′、有口袋截到 P2（t_at_length 同步骤层口径）
    t_end = s_arc.t_at_length(s_side - (o.front_pocket_p2_drop if has_pk else 0.0))
    assert total("side") == pytest.approx(
        edge_length(curves.bezier_subrange(s_arc, 0.0, t_end))
        + edge_length(ctx.curve("front.outseam_upper"))
        + edge_length(ctx.curve("front.outseam_lower")), abs=1e-6)

    # 顶边腰弧：无口袋全弧；口袋自 P1′（有省）/P1（无省）起余段
    dw = o.front_pocket_dart_width if has_pk else 0.0
    s_start = 0.0 if not has_pk else o.front_pocket_p1_dist + (dw if dw > 0 else 0.0)
    assert total("waist") == pytest.approx(
        edge_length(curves.bezier_subrange(w_arc, w_arc.t_at_length(s_start), 1.0))
        if s_start > 0 else edge_length(w_arc), abs=1e-6)

    # 袋口挖削边 = 切削线原长（反向弧长不变）
    if has_pk:
        assert total("mouth") == pytest.approx(
            edge_length(ctx.curve("front.pocket_mouth")), abs=1e-6)

    # 前浪区：总长 = 前浪全长 − 链首剥离量（弯腰头 W / 连裁门襟 s_t = walk+L+extend）
    slant, curve = ctx.line("front.rise_slant"), ctx.curve("front.rise_curve")
    full = edge_length(slant) + edge_length(curve)
    if has_fly:
        L = fly_f.fly_length(ctx.measurements.front_rise,
                             o.fly_length_ratio, o.fly_length_base)
        R = fly_f.fly_corner_radius(o.fly_width, o.fly_corner_inset)
        ext_min = fly_f.fly_blend_extend_min(o.fly_width, R, o.fly_corner_turn)
        extend = (max(fly_f.fly_blend_extend(o.fly_width, R), ext_min)
                  if o.fly_blend_drop is None else o.fly_blend_drop)
        s_t = (o.waistband_width if curved else 0.0) + L + extend
    else:
        s_t = o.waistband_width if curved else 0.0
    assert total("rise") == pytest.approx(
        full - s_t, abs=1e-3 if has_fly else 1e-6)   # 连裁余段经弧长反推 t，64 折线量化 ~4e-5

    assert total("inseam") == pytest.approx(
        edge_length(ctx.curve("front.inseam_upper"))
        + edge_length(ctx.curve("front.inseam_lower")), abs=1e-6)
    assert total("hem") == pytest.approx(edge_length(ctx.curve("front.hem")), abs=1e-6)


# ---------- §1.3 连裁门襟：门襟延伸包含 + 独立门襟同形 + 拉链止口 ----------

@pytest.mark.parametrize("wb", WBS, ids=[w.name for w in WBS])
def test_fly_merge_and_separate(wb):
    from ylpattern.draft import curves
    from ylpattern.formulas import fly as fly_f
    ctx_none, p_none, _ = _build(waistband_type=wb)
    ctx_fly, p_fly, _ = _build(waistband_type=wb, fly=True)
    ctx_sep, p_sep, _ = _build(waistband_type=wb, fly_separate=True)
    # 连裁门襟并入边界 → 净样新增门襟条面积（毛样右界被裆尖折角支配，不比 x）
    assert abs(_signed_area(p_fly)) > abs(_signed_area(p_none)) + 3.0
    assert p_fly.gross_polygon != p_none.gross_polygon
    # 独立门襟为叠画元素，不进前片边界：净边与无门襟完全一致
    assert [(e.name, e.geom) for e in p_sep.net_edges] == \
           [(e.name, e.geom) for e in p_none.net_edges]
    # 拉链止口刀口 = 门襟外缘链（外线→角弧→融合弧）自顶外角下行开深 L（§2.3）
    o = ctx_fly.options
    L = fly_f.fly_length(ctx_fly.measurements.front_rise,
                         o.fly_length_ratio, o.fly_length_base)
    stop = curves.point_along_chain(
        (ctx_fly.line("front.fly_outer_edge"),
         ctx_fly.curve("front.fly_corner_arc"),
         ctx_fly.curve("front.fly_bottom_arc")), L)
    b = _b(ctx_fly)
    expect = _loc(stop, b)
    # 净样刀口位（shrunk_notches 保留缝合线位）；gross 位 = 沿法向投影外移 ~缝宽
    assert min(p.distance_to(expect) for p in p_fly.shrunk_notches) < 1e-9


# ---------- §2.2 裆尖镜像折角（True 态） ----------

@pytest.mark.parametrize("wb", WBS, ids=[w.name for w in WBS])
def test_crotch_corner_treatment(wb):
    ctx, p_mirror, _ = _build(waistband_type=wb, front_piece_crotch_corner=True)
    b = _b(ctx)
    c = _loc(ctx.point("front.crotch_vertex"), b)      # 裆尖（前浪末端 ∩ 下裆缝起点）
    ne = list(p_mirror.net_edges)
    # 链序 [.., inseam_lower, inseam_upper, rise, ..]：inseam_upper 末端 == rise 首端 == c
    iu = next(i for i, e in enumerate(ne)
              if e.name == "inseam" and _end(e.geom).distance_to(c) < 1e-9)
    ri = (iu + 1) % len(ne)
    assert ne[ri].name == "rise"
    assert _start(ne[ri].geom).distance_to(c) < 1e-9
    t_a, t_b = _tan(ne[iu].geom, True), _tan(ne[ri].geom, False)

    def nearest_vertex(piece, q):
        return min(p.distance_to(q) for p in piece.gross_polygon)

    exp_m = _mirror_point(c, t_b, t_a, SA.rise, SA.inseam)
    if exp_m is not None:                              # 平行退化回退 miter 则另算
        # 折线 = 前浪（前浪缝份翻折、折轴为前浪缝本身，非下裆缝）：
        # _mirror_point 首参组传 rise 切线/缝宽，被镜像边 = inseam
        assert nearest_vertex(p_mirror, exp_m) < 1e-9


# ---------- §2.2 裆尖纯尖角跟随净样（False 态，"miter" 自然相交） ----------

@pytest.mark.parametrize("wb", WBS, ids=[w.name for w in WBS])
def test_crotch_miter_corner(wb):
    """False：裆尖走 "miter" 不限长纯尖角自然相交（不抹圆）——两侧缝边
    按贝塞尔多项式自然外延（延续曲线自身张力与曲率）求首个交点成尖
    （== _natural_join_sharp 同式复算链逐点 ∈ 毛样）——角部形态
    与净样轮廓一致，无圆弧过渡点（毛样无距裆尖 == 缝宽的等距弧顶点）、
    无阶梯角断点（尖裆转角大时切线 miter 长 >1.5·缝宽会触发
    默认限长回退阶梯角，本态显式声明尖角为工艺目标形态、绕过限长）。"""
    from ylpattern.cutter import _natural_join_sharp
    ctx, p_mit, _ = _build(waistband_type=wb, front_piece_crotch_corner=False)
    _, p_mir, _ = _build(waistband_type=wb, front_piece_crotch_corner=True)
    b = _b(ctx)
    c = _loc(ctx.point("front.crotch_vertex"), b)
    ne = list(p_mit.net_edges)
    iu = next(i for i, e in enumerate(ne)
              if e.name == "inseam" and _end(e.geom).distance_to(c) < 1e-9)
    ri = (iu + 1) % len(ne)
    assert ne[ri].name == "rise"
    t_a, t_b = _tan(ne[iu].geom, True), _tan(ne[ri].geom, False)

    def nearest(piece, q):
        return min(p.distance_to(q) for p in piece.gross_polygon)

    # 同式复算：自然相交延续链逐点在毛样上，交点成尖（尖角为工艺指定形态）
    exp = _natural_join_sharp(ne[iu].geom, ne[ri].geom,
                              SA.inseam, SA.rise)
    assert exp is not None, "裆尖多项式外延必相交"
    for q in exp:
        assert nearest(p_mit, q) < 1e-9
    apex = exp[len(exp) // 2] if len(exp) % 2 else max(
        exp, key=lambda q: q.distance_to(c))
    # 尖角保留：交尖距裆尖 > 缝宽；且小于切线 miter 长（自然弧相交更近）
    assert apex.distance_to(c) > max(SA.inseam, SA.rise) + 0.05
    # 无阶梯角断点：阶梯角会多出 outer = c+n_a·sa_a+n_b·sa_b 台阶点
    step = c + t_a.perpendicular().scale(SA.inseam) \
        + t_b.perpendicular().scale(SA.rise)
    assert nearest(p_mit, step) > 1e-9
    # 无圆弧过渡：毛样除偏移端点外无距裆尖 == 缝宽的等距弧顶点
    sa_eq = [p for p in p_mit.gross_polygon
             if abs(p.distance_to(c) - SA.rise) < 1e-6]
    assert all(p.distance_to(c + t_a.perpendicular().scale(SA.inseam)) < 1e-9
               or p.distance_to(c + t_b.perpendicular().scale(SA.rise)) < 1e-9
               for p in sa_eq)
    # 与 mirror 态互异（斜角 mirror ≠ miter）、净样一致；不变量保持
    m_pt = _mirror_point(c, t_b, t_a, SA.rise, SA.inseam)
    if m_pt is not None:
        assert nearest(p_mit, m_pt) > 0.1
    assert [(e.name, e.geom) for e in p_mit.net_edges] == \
           [(e.name, e.geom) for e in p_mir.net_edges]
    assert p_mit.gross_polygon != p_mir.gross_polygon
    _assert_closed(p_mit)
    assert _signed_area(p_mit) < 0
    _assert_outward(p_mit)
    render_piece_svg(p_mit)                           # 渲染冒烟


# ---------- §2.3 刀口法向投影 ----------

@pytest.mark.parametrize("wb,kw,cid", COMBOS, ids=[c[2] for c in COMBOS])
def test_notch_projection(wb, kw, cid):
    ctx, piece, _ = _build(waistband_type=wb, **kw)
    poly = piece.gross_polygon
    b = _b(ctx)
    # 全部刀口落在毛样外沿（真点-线段距离；脚口角点刀口限定所在边投影，
    # 落点在 side/inseam 毛样缝边上，用户口径 2026-08）
    for p in piece.gross_notches:
        d = min(_seg_dist(p, poly[i], poly[(i + 1) % len(poly)])
                for i in range(len(poly)))
        assert d < 1e-6, f"刀口 {p} 距毛样外沿 {d:.2e}"
    # 膝围双刀口（防扭脚，绝对精准）：距净点 == 所在边缝宽（侧缝 1.5 / 下裆 1.0）
    # 且 ⟂ 该边切线（主版切线 → 局部 Y 翻转）
    for pt_name, tan_src, sa_amt in (
            ("front.knee_outseam_point", "front.outseam_upper", SA.side),
            ("front.knee_inseam_point", "front.inseam_upper", SA.inseam)):
        knee = _loc(ctx.point(pt_name), b)
        notch = min(piece.gross_notches, key=lambda p: p.distance_to(knee))
        d = notch - knee
        assert abs(d.length - sa_amt) < 1e-6
        t_main = _tan(ctx.curve(tan_src), True)        # 主版切线 → 局部 Y 翻转
        t_loc = LineSegment(Point(0, 0), Point(t_main.dx, -t_main.dy)).direction
        assert abs(d.dx * t_loc.dx + d.dy * t_loc.dy) < 1e-6
    # 缝合线位刀口保留（shrunk_notches = 净样刀口，不丢信息）
    assert len(piece.shrunk_notches) == len(piece.gross_notches)
    assert any("刀口" in n for n in piece.notes)


@pytest.mark.parametrize("wb", WBS, ids=[w.name for w in WBS])
def test_hem_notches_aligned_with_hem_line(wb):
    """脚口双刀口与净样脚口线对齐（内外侧缝 ∩ 脚口线角点，用户口径 2026-08：
    不与卷边宽关联），**打在内外缝毛样缝边上**——净样刀口 = 角点局部点；
    毛样刀口 = 角点沿所在 side/inseam 边外法向外移该边缝宽且 ⟂ 该边切线
    （同膝围双刀口绝对精准口径）。"""
    ctx, piece, _ = _build(waistband_type=wb)
    b = _b(ctx)
    for pt_name, tan_src, sa_amt in (
            ("front.hem_outseam_point", "front.outseam_lower", SA.side),
            ("front.hem_inseam_point", "front.inseam_lower", SA.inseam)):
        corner = _loc(ctx.point(pt_name), b)
        assert min(p.distance_to(corner) for p in piece.shrunk_notches) < 1e-9
        notch = min(piece.gross_notches, key=lambda p: p.distance_to(corner))
        d = notch - corner
        assert abs(d.length - sa_amt) < 1e-6
        t_main = _tan(ctx.curve(tan_src), True)   # 净边脚口端切线 → 局部 Y 翻转
        t_loc = LineSegment(Point(0, 0), Point(t_main.dx, -t_main.dy)).direction
        assert abs(d.dx * t_loc.dx + d.dy * t_loc.dy) < 1e-6


def test_thigh_inseam_notch_extra():
    """毗围实测下移 d>0：毗围内端点非角点，追加为刀口（§2.3）。"""
    _, p0, _ = _build()                                 # d=0：内端 = 裆尖角点跳过
    _, p1, _ = _build(thigh_measure_offset=2.54)
    assert len(p1.gross_notches) == len(p0.gross_notches) + 1


# ---------- §3.3 内部辅助线 marks ----------

@pytest.mark.parametrize("wb", WBS, ids=[w.name for w in WBS])
def test_internal_marks(wb):
    ctx, piece, _ = _build(waistband_type=wb)
    b = _b(ctx)
    assert len(piece.marks) == 3                        # 臀围 + 膝围 + 毗围（thigh=58）
    geoms = [e.geom for e in piece.net_edges]
    ys = {"front.hip_line": None, "front.knee_line": None, "front.thigh_line": None}
    for i, mk in enumerate(piece.marks):
        assert isinstance(mk, LineSegment)
        assert mk.a.y == pytest.approx(mk.b.y)          # 局部水平
        y_main = ctx.line(list(ys)[i]).a.y
        assert mk.a.y == pytest.approx(b.y - y_main)    # 主版水平线 Y 翻转
        _chain_dist(mk.a, geoms)
        _chain_dist(mk.b, geoms)
    # 无大腿围录入：毗围线不存在，marks = 2
    _, p_no, _ = _build(m=M_NO_THIGH)
    assert len(p_no.marks) == 2


@pytest.mark.parametrize("wb", WBS, ids=[w.name for w in WBS])
def test_hip_mark_clips_to_fly_region(wb):
    """连裁门襟组：臀围线右端截断到门襟区边界（底角弧/前浪余段），且因门襟
    外凸比无门襟组更靠前中（+X）——门襟底缘在臀围线之上，不与外线相交。"""
    ctx_fly, p_fly, _ = _build(waistband_type=wb, fly=True)
    _, p_none, _ = _build(waistband_type=wb)
    b = _b(ctx_fly)
    hip_y = ctx_fly.line("front.hip_line").a.y

    def hip_right(piece):
        mk = next(m for m in piece.marks
                  if abs(m.a.y - (b.y - hip_y)) < 1e-9)
        return mk.a if mk.a.x > mk.b.x else mk.b

    right = hip_right(p_fly)
    fly_chain = [e.geom for e in p_fly.net_edges
                 if e.name in ("rise", "fly_bottom", "fly_outer", "fly_top")]
    _chain_dist(right, fly_chain)                     # ∈ 门襟区净边链
    assert right.x > hip_right(p_none).x              # 门襟外凸推右截断点


# ---------- §3.2 缩水（None 回退全局 / 局部生效 / marks 同变换）----------

@pytest.mark.parametrize("wb", WBS, ids=[w.name for w in WBS])
def test_shrinkage(wb):
    # 默认无缩水：shrunk == net 坐标、notes 无缩水记录
    _, p0, _ = _build(waistband_type=wb)
    for e_net, e_sh in zip(p0.net_edges, p0.shrunk_edges):
        assert e_net.name == e_sh.name
        assert _start(e_net.geom) == _start(e_sh.geom)
        assert _end(e_net.geom) == _end(e_sh.geom)
    assert not any("缩水" in n for n in p0.notes)
    # 局部缩水生效：净边/刀口/丝缕/marks 同比例（X 吃纬 1/0.98、Y 吃经 1/0.97）
    _, p1, _ = _build(waistband_type=wb,
                      front_piece_shrinkage_warp=0.03,
                      front_piece_shrinkage_weft=0.02)
    assert any("缩水" in n for n in p1.notes)
    for e_net, e_sh in zip(p0.net_edges, p1.shrunk_edges):
        assert _start(e_net.geom).x / 0.98 == pytest.approx(_start(e_sh.geom).x)
        assert _start(e_net.geom).y / 0.97 == pytest.approx(_start(e_sh.geom).y)
    for m0, m1 in zip(p0.marks, p1.marks):
        assert m0.a.x / 0.98 == pytest.approx(m1.a.x)
        assert m0.a.y / 0.97 == pytest.approx(m1.a.y)
    # None 回退全局：与全局率直出等价
    _, p2, _ = _build(waistband_type=wb, shrinkage_warp=0.03, shrinkage_weft=0.02)
    assert p2.gross_polygon == p1.gross_polygon


# ---------- §3.1 丝缕 / 守卫 / 选项校验 ----------

def test_grain_vertical():
    _, piece, _ = _build()
    assert piece.grain.a.x == pytest.approx(piece.grain.b.x)
    ys = [p.y for e in piece.net_edges for p in _sample(e.geom)]
    assert (piece.grain.b.y - piece.grain.a.y) >= 0.7 * (max(ys) - min(ys))


def test_guard_until_interrupt():
    """--until 中断在前片轮廓完成前：净样未上版，build 守卫拦截。"""
    ctx = FlowRunner(M, PatternOptions()).run(FULL_FLOW, until="draw_front_rise")
    with pytest.raises(ValueError, match="完整整版"):
        build_front_piece(ctx)


def test_options_validation_and_defaults():
    sa = FrontSeamAllowances()
    assert (sa.waist, sa.rise, sa.inseam) == (1.0, 1.0, 1.0)
    assert sa.side == 1.5 and sa.hem == 2.5
    assert (sa.mouth, sa.fly_top, sa.fly_outer, sa.fly_bottom) == (1.0,) * 4
    assert FrontSeamAllowances.from_dict(
        {"side": 2.0}).side == 2.0
    o = PatternOptions()
    assert o.front_piece_crotch_corner is True
    assert o.front_piece_notch_type == "I"
    assert o.front_piece_shrinkage_warp is None
    with pytest.raises(TypeError):
        PatternOptions(front_piece_seam_allowances={"side": 1.0})
    with pytest.raises(ValueError):
        PatternOptions(front_piece_seam_allowances=FrontSeamAllowances(side=-1))
    with pytest.raises(ValueError):
        PatternOptions(front_piece_notch_type="X")
    with pytest.raises(ValueError):
        PatternOptions(front_piece_shrinkage_warp=0.25)


# ---------- polyline 袋口模式（mouth 折角链逆序） ----------

def test_polyline_mouth_chain():
    """polyline 模式：mouth 折角链与主版切削段几何逐段全等（自然序两次反向
    抵消 → 片上即主版方向），端点 P1′/P2。"""
    corners = ((0.4, 1.0), (0.7, 0.8))
    ctx, piece, _ = _build(front_pocket=True,
                           front_pocket_mouth_mode="polyline",
                           front_pocket_mouth_corners=corners)
    g = _edges_by_name(piece)
    assert len(g["mouth"]) == len(corners) + 1
    b = _b(ctx)
    p2 = _loc(ctx.point("front.pocket_p2"), b)
    p1r = _loc(ctx.point("front.pocket_p1_transfer"), b)  # 默认 dw=2.0 有省
    assert _start(g["mouth"][0]).distance_to(p1r) < 1e-9
    assert _end(g["mouth"][-1]).distance_to(p2) < 1e-9
    for i, geom in enumerate(g["mouth"]):
        seg = ctx.line(f"front.pocket_mouth_seg{i + 1}")
        assert _start(geom) == _loc(seg.a, b) and _end(geom) == _loc(seg.b, b)
