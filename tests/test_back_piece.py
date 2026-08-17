"""后片独立裁片测试（后片裁片.md §1~§5）。

金标（W=70, H=96, K=46, B=36, 前浪 25, 后浪 33, 裤长 102, 大腿围 58，
Δ=1.0 默认；腰头 2 形态 × 机头 有/无 = 4 组合，机头开启时另测贴袋/后省）：
  §1 净边装配条件矩阵：闭合（1e-6）、shoelace<0（cutter 外法向）、
    链首 = cb_top 局部点（有 yoke = P0 / 无 yoke = A 直 / O′ 弯）；
    有 yoke：top = 机头下口线链（P0->PN）、无 waist；无 yoke：waist =
    腰口弧反向（B->A / X'->O'）、无 top；
    side = 侧缝下行链自 PN/X'/B 起后缀（三段同名）、cb = 后浪链自 P0/A/O'
    起后缀反向（斜线+弧两段同名）。
  §2 边长独立复算（从 ctx 元素弧长同式重算，不硬编）：side = 全链 − d_side、
    cb = 全链 − d_cb（d = W 弯腰头下移 + D_端点距离，与 back_yoke_steps 量取
    口径同源）；§2.2 浪尖角部：True = mirror（== _mirror_point 复算角点，
    折线边 = 后浪缝）、False = 纯尖角跟随净样（== _natural_join_sharp 复算
    外延链 ∈ 毛样）。
  §4 刀口法向投影：全部 ∈ 毛样外沿（1e-6）；膝围双刀口距净点 == sa 且 ⟂ 切线；
    刀口数按矩阵（膝2+臀2+浪尖1+卷边2+横裆2+后中1 基底，毗围 +1、口袋 +1、
    d>0 毗围内端 +1）。
  §5 内部线/定位孔：臀围/横裆/膝围（+毗围）水平线截断（端点 ∈ 净边链、
    主版高度 Y 翻转）；贴袋：顶线 mark + 上端两顶点 drills + 口袋对位刀口
    ∈ 侧缝链；后省穿越上边界：省腿裁片内子段进 marks + stderr 告警。
  §3 缩水 None 回退全局 / 局部生效（净边/刀口/marks/drills 同比例
    ×(1+weft, 1+warp)）。
断言口径：几何不变量 + 独立复算，同 test_front_piece。
"""

import itertools

import pytest

from ylpattern.cutter import _mirror_point, _natural_join_sharp, edge_length
from ylpattern.exporters.piece_svg import render_piece_svg
from ylpattern.flows.back_flow import FULL_FLOW
from ylpattern.flows.back_piece_flow import build_back_piece
from ylpattern.flows.runner import FlowRunner
from ylpattern.geometry import CubicBezier, LineSegment, Point
from ylpattern.params import (BackSeamAllowances, Measurements,
                              PatternOptions, WaistbandType)

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
M_NO_THIGH = Measurements(waist=70, hip=96, knee=46, hem=36,
                          front_rise=25, back_rise=33, outseam=102)

SA = BackSeamAllowances()                      # 默认缝份金标


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
    piece, local = build_back_piece(ctx)
    return ctx, piece, local


def _cb_top(ctx):
    """局部原点：有 yoke = P0 / 无 yoke = A 直腰头 / O′ 弯腰头。"""
    o = ctx.options
    if o.back_yoke:
        return ctx.point("back.yoke_cb_point")
    if o.waistband_type is WaistbandType.CURVED:
        return ctx.point("back.lower_waist_center_point")
    return ctx.point("back.rise_top_point")


def _loc(p, b):
    return Point(p.x - b.x, b.y - p.y)


def _signed_area(piece) -> float:
    poly = []
    for e in piece.net_edges:
        poly += _sample(e.geom)
    s = 0.0
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % n] if (n := len(poly)) else poly[i]
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
    """点到净边链折线（n 密采样）的距离（marks/刀口 ∈ 链上用）。"""
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
YKS = [(False, "无机头"), (True, "有机头")]
COMBOS = [(wb, yk, f"{wb.name}-{'yoke' if yk else 'noyoke'}")
          for wb, (yk, _) in itertools.product(WBS, YKS)]


def _expected_notch_count(piece_thigh=True, has_patch=False):
    base = 10      # 膝×2 + 臀×2 + 浪尖 + 卷边×2 + 横裆×2 + 后中拼接
    return base + (1 if piece_thigh else 0) + (1 if has_patch else 0)


# ---------- §1 条件矩阵：4 组合闭合/定向/结构/渲染 ----------

@pytest.mark.parametrize("wb,yk,cid", COMBOS, ids=[c[2] for c in COMBOS])
def test_matrix_closure_structure(wb, yk, cid):
    """4 组合：闭合 1e-6、shoelace<0、毛样 bbox ⊇ 净样、毛样/刀口非空、
    边名结构（top/waist 互斥、side 三段、inseam 两段、hem 一段、cb 两段）、
    刀口数按矩阵、render 冒烟。"""
    ctx, piece, local = _build(waistband_type=wb, back_yoke=yk)
    _assert_closed(piece)
    assert _signed_area(piece) < 0
    _assert_outward(piece)
    assert len(piece.gross_polygon) >= 3
    assert len(piece.gross_notches) == _expected_notch_count()

    names = [e.name for e in piece.net_edges]
    g = _edges_by_name(piece)
    assert {"side", "inseam", "hem", "cb"} <= set(names)
    if yk:
        assert "top" in names and "waist" not in names
        assert len(g["top"]) == 1                      # 默认无锚点：直线一段
    else:
        assert "waist" in names and "top" not in names
        assert len(g["waist"]) == 1
    assert len(g["side"]) == 3                         # 髋腰残段 + 大腿弧 + 小腿弧
    assert len(g["inseam"]) == 2
    assert len(g["hem"]) == 1
    assert len(g["cb"]) == 2                           # 斜线残段反向 + 裆弯弧反向

    assert render_piece_svg(piece).startswith("<svg")
    assert sum(1 for _ in local.sheet) == len(piece.net_edges)
    for i in range(len(piece.net_edges)):
        assert f"back_piece.edge{i}" in local.sheet


# ---------- §1 端点金标（链首链尾 == cb_top 局部点；top 两端 == P0/PN）----------

@pytest.mark.parametrize("wb,yk,cid", COMBOS, ids=[c[2] for c in COMBOS])
def test_endpoint_golden(wb, yk, cid):
    ctx, piece, _ = _build(waistband_type=wb, back_yoke=yk)
    b = _cb_top(ctx)
    ne = piece.net_edges
    # 局部自然序（主版 CCW 反射为 CW，shoelace<0 无反转）：链首 = cb_top
    assert _start(ne[0].geom).distance_to(Point(0.0, 0.0)) < 1e-9
    assert _end(ne[-1].geom).distance_to(Point(0.0, 0.0)) < 1e-9
    assert _loc(b, b) == Point(0.0, 0.0)              # origin 自身
    if yk:
        g = _edges_by_name(piece)
        # top 链 P0->PN：首段起 == P0 局部点、末段止 == PN 局部点
        assert _start(g["top"][0]).distance_to(Point(0.0, 0.0)) < 1e-9
        pn = _loc(ctx.point("back.yoke_side_point"), b)
        assert _end(g["top"][-1]).distance_to(pn) < 1e-9


# ---------- §2.1 边长独立复算（从 ctx 元素同式重算，不硬编）----------

@pytest.mark.parametrize("wb,yk,cid", COMBOS, ids=[c[2] for c in COMBOS])
def test_edge_lengths(wb, yk, cid):
    from ylpattern.draft import curves
    ctx, piece, _ = _build(waistband_type=wb, back_yoke=yk)
    o = ctx.options
    curved = wb is WaistbandType.CURVED
    hw = ctx.curve("back.outseam_hip_waist")
    slant, curve = ctx.line("back.rise_slant"), ctx.curve("back.rise_curve")
    # 侧缝/后浪下行链全长的剥离量：与 back_yoke_steps 量取口径同源
    # （有 yoke = D_端点 + 弯腰头下移 W；无 yoke = 弯腰头下移 W / 0）
    d_cb = (o.waistband_width if curved else 0.0) \
        + (o.back_yoke_cb_dist if yk else 0.0)
    d_side = (o.waistband_width if curved else 0.0) \
        + (o.back_yoke_side_dist if yk else 0.0)
    g = _edges_by_name(piece)

    def total(name):
        return sum(edge_length(x) for x in g[name])

    assert total("side") == pytest.approx(
        edge_length(hw) + edge_length(ctx.curve("back.outseam_upper"))
        + edge_length(ctx.curve("back.outseam_lower")) - d_side, abs=1e-3)
    assert total("cb") == pytest.approx(
        edge_length(slant) + edge_length(curve) - d_cb, abs=1e-3)
    assert total("inseam") == pytest.approx(
        edge_length(ctx.curve("back.inseam_upper"))
        + edge_length(ctx.curve("back.inseam_lower")), abs=1e-6)
    assert total("hem") == pytest.approx(edge_length(ctx.curve("back.hem")), abs=1e-6)
    if yk:
        # top = 机头下口线原链长（1:1 复制）
        seg1 = ctx.sheet.get("back.yoke_bottom_seg1").geom
        assert total("top") == pytest.approx(edge_length(seg1), abs=1e-6)
        assert curves  # noqa: B018（保持与 ctx 元素同式重算的引用一致性）


# ---------- §2.2 浪尖角部两态 ----------

@pytest.mark.parametrize("wb,yk,cid", COMBOS, ids=[c[2] for c in COMBOS])
def test_crotch_corner_treatment(wb, yk, cid):
    """True：浪尖 mirror 折角（== _mirror_point 复算角点，折线边 = 后浪缝，
    后浪缝份翻折贴向内侧缝时折轴为后浪缝本身，同前片裆尖先例）。"""
    ctx, p_mirror, _ = _build(waistband_type=wb, back_yoke=yk,
                              back_piece_crotch_corner=True)
    b = _cb_top(ctx)
    c = _loc(ctx.point("back.crotch_vertex"), b)   # 浪尖（后浪弧末端 ∩ 内缝起点）
    ne = list(p_mirror.net_edges)
    # 链序 [.., inseam_upper, cb_curve, cb_slant, ..]：inseam 末端 == cb 首端 == c
    iu = next(i for i, e in enumerate(ne)
              if e.name == "inseam" and _end(e.geom).distance_to(c) < 1e-9)
    ci = (iu + 1) % len(ne)
    assert ne[ci].name == "cb"
    assert _start(ne[ci].geom).distance_to(c) < 1e-9
    t_a, t_b = _tan(ne[iu].geom, True), _tan(ne[ci].geom, False)

    def nearest_vertex(piece, q):
        return min(p.distance_to(q) for p in piece.gross_polygon)

    exp_m = _mirror_point(c, t_b, t_a, SA.cb, SA.inseam)
    if exp_m is not None:                          # 平行退化回退 miter 则另算
        assert nearest_vertex(p_mirror, exp_m) < 1e-9


@pytest.mark.parametrize("wb,yk,cid", COMBOS, ids=[c[2] for c in COMBOS])
def test_crotch_miter_corner(wb, yk, cid):
    """False：浪尖走 "miter" 不限长纯尖角自然相交（不抹圆）--两侧缝边按
    贝塞尔多项式自然外延求首个交点成尖（== _natural_join_sharp 同式复算
    链逐点 ∈ 毛样）；净样与 mirror 态一致、毛样互异。"""
    ctx, p_mit, _ = _build(waistband_type=wb, back_yoke=yk,
                           back_piece_crotch_corner=False)
    _, p_mir, _ = _build(waistband_type=wb, back_yoke=yk,
                         back_piece_crotch_corner=True)
    b = _cb_top(ctx)
    c = _loc(ctx.point("back.crotch_vertex"), b)
    ne = list(p_mit.net_edges)
    iu = next(i for i, e in enumerate(ne)
              if e.name == "inseam" and _end(e.geom).distance_to(c) < 1e-9)
    ci = (iu + 1) % len(ne)
    assert ne[ci].name == "cb"

    def nearest(piece, q):
        return min(p.distance_to(q) for p in piece.gross_polygon)

    exp = _natural_join_sharp(ne[iu].geom, ne[ci].geom, SA.inseam, SA.cb)
    assert exp is not None, "浪尖多项式外延必相交"
    for q in exp:
        assert nearest(p_mit, q) < 1e-9
    assert [(e.name, e.geom) for e in p_mit.net_edges] == \
           [(e.name, e.geom) for e in p_mir.net_edges]
    assert p_mit.gross_polygon != p_mir.gross_polygon
    _assert_closed(p_mit)
    assert _signed_area(p_mit) < 0
    _assert_outward(p_mit)
    render_piece_svg(p_mit)                         # 渲染冒烟


# ---------- §4 刀口法向投影 ----------

@pytest.mark.parametrize("wb,yk,cid", COMBOS, ids=[c[2] for c in COMBOS])
def test_notch_projection(wb, yk, cid):
    ctx, piece, _ = _build(waistband_type=wb, back_yoke=yk)
    poly = piece.gross_polygon
    # 全部刀口落在毛样外沿（真点-线段距离）
    for p in piece.gross_notches:
        d = min(_seg_dist(p, poly[i], poly[(i + 1) % len(poly)])
                for i in range(len(poly)))
        assert d < 1e-6, f"刀口 {p} 距毛样外沿 {d:.2e}"
    # 膝围双刀口（最关键上下对位点，绝对精准）：距净点 == 所在边缝宽
    # （侧缝 1.5 / 内缝 1.0）且 ⟂ 该边切线（主版切线 -> 局部 Y 翻转）
    b = _cb_top(ctx)
    for pt_name, tan_src, sa_amt in (
            ("back.knee_outseam_point", "back.outseam_upper", SA.side),
            ("back.knee_inseam_point", "back.inseam_upper", SA.inseam)):
        knee = _loc(ctx.point(pt_name), b)
        notch = min(piece.gross_notches, key=lambda p: p.distance_to(knee))
        d = notch - knee
        assert abs(d.length - sa_amt) < 1e-6
        t_main = _tan(ctx.curve(tan_src), True)
        t_loc = LineSegment(Point(0, 0), Point(t_main.dx, -t_main.dy)).direction
        assert abs(d.dx * t_loc.dx + d.dy * t_loc.dy) < 1e-6
    # 缝合线位刀口保留（shrunk_notches = 净样刀口，不丢信息）
    assert len(piece.shrunk_notches) == len(piece.gross_notches)
    assert any("刀口" in n for n in piece.notes)


def test_thigh_notches():
    """无大腿围录入：毗围刀口不存在（10 个）；d>0：毗围内端点非角点 +1。"""
    _, p_no, _ = _build(m=M_NO_THIGH)
    assert len(p_no.gross_notches) == 10
    _, p0, _ = _build()                             # d=0：内端 = 浪尖角点跳过
    _, p1, _ = _build(thigh_measure_offset=2.54)
    assert len(p0.gross_notches) == 11
    assert len(p1.gross_notches) == 12


# ---------- §5 内部辅助线 / 贴袋引用 / 后省 ----------

@pytest.mark.parametrize("wb,yk,cid", COMBOS, ids=[c[2] for c in COMBOS])
def test_internal_marks(wb, yk, cid):
    ctx, piece, _ = _build(waistband_type=wb, back_yoke=yk)
    b = _cb_top(ctx)
    assert len(piece.marks) == 3          # 臀围 + 膝围 + 毗围（thigh=58；横裆线不画）
    geoms = [e.geom for e in piece.net_edges]
    names = ("back.hip_line", "back.knee_line")
    for mk, name in zip(piece.marks, names):
        assert isinstance(mk, LineSegment)
        assert mk.a.y == pytest.approx(mk.b.y)       # 局部水平
        assert mk.a.y == pytest.approx(b.y - ctx.line(name).a.y)  # 主版 Y 翻转
        _chain_dist(mk.a, geoms)
        _chain_dist(mk.b, geoms)
    # 横裆线不进 marks（毗围斜量线即其测量基准）；其高度交点仍进 §4 刀口
    crotch_y = ctx.line("back.crotch_line").a.y
    assert not any(isinstance(m, LineSegment) and m.a.y == m.b.y
                   and m.a.y == pytest.approx(b.y - crotch_y)
                   for m in piece.marks)
    # 毗围线 = 真实测量线 1:1 拷贝（斜量线，两端点在净边上；d=0 时与横裆线
    # 高度接近但为斜线，不叠影）
    thigh = piece.marks[2]
    tl = ctx.line("back.thigh_line")
    assert thigh.a.distance_to(_loc(tl.a, b)) < 1e-9
    assert thigh.b.distance_to(_loc(tl.b, b)) < 1e-9
    assert thigh.a.y != pytest.approx(thigh.b.y)     # 斜线（外缝点高、裆端低）
    _chain_dist(thigh.a, geoms)
    _chain_dist(thigh.b, geoms)
    # 无大腿围录入：毗围线不存在，marks = 2
    _, p_no, _ = _build(m=M_NO_THIGH)
    assert len(p_no.marks) == 2


@pytest.mark.parametrize("wb", WBS, ids=[w.name for w in WBS])
def test_patch_refs(wb):
    """贴袋开启：顶线 mark + 上端两顶点 drills + 口袋对位刀口 ∈ 侧缝链。"""
    ctx, piece, _ = _build(waistband_type=wb, back_yoke=True, back_patch=True)
    b = _cb_top(ctx)
    assert len(piece.drills) == 2
    assert piece.drills[0] == _loc(ctx.point("back.patch_net_pt1"), b)
    assert piece.drills[1] == _loc(ctx.point("back.patch_net_pt2"), b)
    # 顶线 mark = 主版净样 1:1 拷贝（局部化）
    top = ctx.sheet.get("back.patch_net_seg1").geom
    assert any(_start(m).distance_to(_loc(_start(top), b)) < 1e-9
               and _end(m).distance_to(_loc(_end(top), b)) < 1e-9
               for m in piece.marks)
    # 口袋对位刀口 = 顶线延长 ∩ 侧缝（净边链上）；刀口数 +1
    assert len(piece.gross_notches) == _expected_notch_count(has_patch=True)
    pocket = max(piece.shrunk_notches,
                 key=lambda p: p.distance_to(Point(0.0, 0.0)))
    side_geoms = _edges_by_name(piece)["side"]
    _chain_dist(pocket, side_geoms, tol=5e-3)      # 采样交点量化容差


@pytest.mark.parametrize("wb", WBS, ids=[w.name for w in WBS])
def test_dart_crossing_marks_and_warning(wb, capsys):
    """后省穿越上边界：边界按图提取 + stderr 告警一次 + 省腿裁片内子段进
    marks；省尖在上边界之上（浅省）：无告警、无省腿 marks。省腿子段按
    "与省腿线段共线近距"识别（毗围斜量线亦非水平，勿按水平与否判）。"""

    def dart_stubs(ctx, piece):
        b = _cb_top(ctx)
        stubs = []
        for i in (1, 2):
            if f"back.dart{i}_apex" not in ctx.sheet:
                continue
            for leg in (f"back.dart{i}_leg_inner", f"back.dart{i}_leg_outer"):
                lg = ctx.line(leg)
                la, lb = _loc(lg.a, b), _loc(lg.b, b)   # 省腿主版 -> 局部
                for m in piece.marks:
                    if isinstance(m, LineSegment) and \
                            _seg_dist(_start(m), la, lb) < 0.2 \
                            and _seg_dist(_end(m), la, lb) < 0.2:
                        stubs.append(m)
        return stubs

    ctx_d, p_deep, _ = _build(waistband_type=wb, back_yoke=True, back_dart=True)
    assert "警告" in capsys.readouterr().err
    assert len(dart_stubs(ctx_d, p_deep)) == 2
    capsys.readouterr()                             # 清空
    ctx_s, p_shallow, _ = _build(waistband_type=wb, back_yoke=True,
                                 back_dart=True, back_dart_length=2.0)
    assert "警告" not in capsys.readouterr().err
    assert not dart_stubs(ctx_s, p_shallow)


# ---------- §3 缩水（None 回退全局 / 局部生效 / marks+drills 同变换）----------

@pytest.mark.parametrize("wb,yk,cid", COMBOS, ids=[c[2] for c in COMBOS])
def test_shrinkage(wb, yk, cid):
    # 默认无缩水：shrunk == net 坐标、notes 无缩水记录（统一开贴袋以对齐
    # marks/drills 结构）
    _, p0, _ = _build(waistband_type=wb, back_yoke=yk, back_patch=yk)
    for e_net, e_sh in zip(p0.net_edges, p0.shrunk_edges):
        assert e_net.name == e_sh.name
        assert _start(e_net.geom) == _start(e_sh.geom)
        assert _end(e_net.geom) == _end(e_sh.geom)
    assert not any("缩水" in n for n in p0.notes)
    # 贴袋依赖机头定位：drills 仅 yoke 组合有（back_patch=yk 已带依赖语义）
    assert len(p0.drills) == (2 if yk else 0)
    # 局部缩水生效：净边/刀口/丝缕/marks/drills 同比例（X 吃纬 1.02、Y 吃经 1.03）
    _, p1, _ = _build(waistband_type=wb, back_yoke=yk, back_patch=yk,
                      back_piece_shrinkage_warp=0.03,
                      back_piece_shrinkage_weft=0.02)
    assert any("缩水" in n for n in p1.notes)
    for e_net, e_sh in zip(p0.net_edges, p1.shrunk_edges):
        assert _start(e_net.geom).x * 1.02 == pytest.approx(_start(e_sh.geom).x)
        assert _start(e_net.geom).y * 1.03 == pytest.approx(_start(e_sh.geom).y)
    for m0, m1 in zip(p0.marks, p1.marks):
        assert m0.a.x * 1.02 == pytest.approx(m1.a.x)
        assert m0.a.y * 1.03 == pytest.approx(m1.a.y)
    assert len(p1.drills) == len(p0.drills)
    for d0, d1 in zip(p0.drills, p1.drills):
        assert d1.x == pytest.approx(d0.x * 1.02)
        assert d1.y == pytest.approx(d0.y * 1.03)
    # None 回退全局：与全局率直出等价
    _, p2, _ = _build(waistband_type=wb, back_yoke=yk, back_patch=yk,
                      shrinkage_warp=0.03, shrinkage_weft=0.02)
    assert p2.gross_polygon == p1.gross_polygon


# ---------- 丝缕 / 守卫 / 选项校验 ----------

def test_grain_vertical():
    _, piece, _ = _build()
    assert piece.grain.a.x == pytest.approx(piece.grain.b.x)
    ys = [p.y for e in piece.net_edges for p in _sample(e.geom)]
    assert (piece.grain.b.y - piece.grain.a.y) >= 0.7 * (max(ys) - min(ys))


def test_guard_until_interrupt():
    """--until 中断在后片轮廓完成前：净样未上版，build 守卫拦截。"""
    ctx = FlowRunner(M, PatternOptions()).run(FULL_FLOW, until="draw_back_rise")
    with pytest.raises(ValueError, match="完整整版"):
        build_back_piece(ctx)


def test_guard_yoke_on_but_incomplete():
    """back_yoke 开启但机头步骤未执行（--until 截断）：守卫拦截。"""
    ctx = FlowRunner(M, PatternOptions(back_yoke=True)).run(
        FULL_FLOW, until="draw_back_darts")
    with pytest.raises(ValueError, match="back.yoke_cb_point"):
        build_back_piece(ctx)


def test_options_validation_and_defaults():
    sa = BackSeamAllowances()
    assert (sa.top, sa.waist, sa.cb, sa.inseam) == (1.0, 1.0, 1.0, 1.0)
    assert sa.side == 1.5 and sa.hem == 2.5
    assert BackSeamAllowances.from_dict({"side": 2.0}).side == 2.0
    o = PatternOptions()
    assert o.back_piece_crotch_corner is True
    assert o.back_piece_notch_type == "I"
    assert o.back_piece_shrinkage_warp is None
    with pytest.raises(TypeError):
        PatternOptions(back_piece_seam_allowances={"side": 1.0})
    with pytest.raises(ValueError):
        PatternOptions(back_piece_seam_allowances=BackSeamAllowances(side=-1))
    with pytest.raises(ValueError):
        PatternOptions(back_piece_notch_type="X")
    with pytest.raises(ValueError):
        PatternOptions(back_piece_shrinkage_warp=0.25)
