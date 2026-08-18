"""前口袋袋布独立裁片测试（口袋布裁片.md §2~§6）。

一片式对折：底层=大片原样复制，面层=小片沿内边 P_w0-K1 镜像挖袋口，对折边为内部
折叠线。断言口径：几何不变量（闭合、shoelace<0 自定向、外法向外扩、镜像对称性、
袋口挖削弧线、缩水=0、刀口、丝缕竖向），不硬编坐标。cutter 外法向要求闭合多边形
shoelace<0（同 test_front_pocket_piece / test_yoke_piece 口径）。

镜像对称性在裁片局部坐标下检验：局部折叠轴 = (0,0)->local_K1（局部变换为关于过
P_w0 水平线的反射，与主版 P_w0-K1 镜像共轭，故面层 = 底层关于局部折叠轴的镜像）。
"""

import pytest

from ylpattern.exporters.piece_svg import render_piece_svg
from ylpattern.flows.front_flow import FRONT_FLOW
from ylpattern.flows.front_pouch_flow import build_front_pouch
from ylpattern.flows.runner import FlowRunner
from ylpattern.geometry import CubicBezier, LineSegment, Point
from ylpattern.params import (Measurements, PatternOptions, PouchSeamAllowances,
                              WaistbandType)

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)


def _start(g): return g.a if isinstance(g, LineSegment) else g.p0
def _end(g):   return g.b if isinstance(g, LineSegment) else g.p3
def _sample(g, n=32):
    return [g.a, g.b] if isinstance(g, LineSegment) else g.sample(n)


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


def _edges_by_name(piece):
    groups: dict[str, list] = {}
    for e in piece.net_edges:
        groups.setdefault(e.name, []).append(e.geom)
    return groups


def _reflect_point(p: Point, axis_a: Point, axis_b: Point) -> Point:
    """点关于直线 axis_a->axis_b 的轴对称镜像（与流程同口径）。"""
    d = axis_b - axis_a
    if d.length == 0:
        return p
    ap = p - axis_a
    t = (ap.dx * d.dx + ap.dy * d.dy) / (d.dx * d.dx + d.dy * d.dy)
    proj = axis_a + d.scale(t)
    return proj + (proj - p)


def _reflect_geom(g, axis_a, axis_b):
    if isinstance(g, LineSegment):
        return LineSegment(_reflect_point(g.a, axis_a, axis_b),
                           _reflect_point(g.b, axis_a, axis_b))
    return CubicBezier(_reflect_point(g.p0, axis_a, axis_b),
                       _reflect_point(g.p1, axis_a, axis_b),
                       _reflect_point(g.p2, axis_a, axis_b),
                       _reflect_point(g.p3, axis_a, axis_b))


def _to_local(p: Point, origin: Point) -> Point:
    """主版 -> 裁片局部（Y 反射，origin=P_w0）：local=(x−origin.x, origin.y−y)。"""
    return Point(p.x - origin.x, origin.y - p.y)


def _local_axis(ctx):
    """局部折叠轴两端：(0,0) -> local_K1。"""
    p_w0 = ctx.point("front.pouch_waist_anchor")
    k1 = ctx.point("front.pouch_node1")
    return Point(0.0, 0.0), _to_local(k1, p_w0), p_w0, k1


@pytest.fixture()
def ctx_dart():
    """直腰头 + 有省 + 袋布。"""
    o = PatternOptions(delta=1.0, front_pocket=True, front_pouch=True,
                       front_pocket_dart_width=1.5)
    return FlowRunner(M, o).run(FRONT_FLOW)


@pytest.fixture()
def ctx_nodart():
    """直腰头 + 无省 + 袋布（默认 front_pocket_dart_width=2.0，显式置 0）。"""
    o = PatternOptions(delta=1.0, front_pocket=True, front_pouch=True,
                       front_pocket_dart_width=0.0)
    return FlowRunner(M, o).run(FRONT_FLOW)


@pytest.fixture()
def ctx_curved():
    """弯腰头 + 有省 + 袋布。"""
    o = PatternOptions(delta=1.0, front_pocket=True, front_pouch=True,
                       front_pocket_dart_width=1.5,
                       waistband_type=WaistbandType.CURVED)
    return FlowRunner(M, o).run(FRONT_FLOW)


# ---------- 几何不变量 ----------

def test_dart_geometry_invariants(ctx_dart):
    piece, _ = build_front_pouch(ctx_dart)
    _assert_closed(piece)
    assert _signed_area(piece) < 0           # 自定向：cutter 外法向正确外扩
    _assert_outward(piece)
    assert piece.gross_polygon               # 毛样已生成
    render_piece_svg(piece)                  # SVG 不报错


def test_nodart_geometry_invariants(ctx_nodart):
    piece, _ = build_front_pouch(ctx_nodart)
    _assert_closed(piece)
    assert _signed_area(piece) < 0
    _assert_outward(piece)
    render_piece_svg(piece)


def test_curved_geometry_invariants(ctx_curved):
    piece, _ = build_front_pouch(ctx_curved)
    _assert_closed(piece)
    assert _signed_area(piece) < 0
    _assert_outward(piece)
    render_piece_svg(piece)


# ---------- 边结构：底层（原样）＋ 面层（镜像）各语义边齐备 ----------

def test_edge_structure(ctx_dart):
    piece, _ = build_front_pouch(ctx_dart)
    groups = _edges_by_name(piece)
    # 默认 2 节点 -> 节点链 2 段（跳 seg1 折叠边），底层/面层各 2
    assert len(groups["bottom"]) == 2
    assert len(groups["bottom_m"]) == 2
    # 侧缝：默认 side_safe=8 -> 低于臀围线两段，底层/面层级数一致
    assert len(groups["side"]) >= 1
    assert len(groups["side_m"]) == len(groups["side"])
    # 腰弧：底层/面层各 1
    assert len(groups["waist"]) == 1 and len(groups["waist_m"]) == 1
    # 袋口：仅面层 1（无底层同名对边，故不加 _m 后缀）
    assert len(groups["mouth"]) == 1


# ---------- 镜像对称性：面层各边 = 底层对应边关于局部折叠轴的镜像 ----------

def test_node_chain_symmetry(ctx_dart):
    """面层节点链 = 底层节点链沿折叠轴镜像（节点链为自由边界，两侧严格对称）。"""
    ctx = ctx_dart
    piece, _ = build_front_pouch(ctx)
    a0, a1, _, _ = _local_axis(ctx)
    groups = _edges_by_name(piece)
    bottom_pts = [p for g in groups["bottom"] for p in _sample(g)]
    top_pts = [p for g in groups["bottom_m"] for p in _sample(g)]
    mirrored = [_reflect_point(p, a0, a1) for p in bottom_pts]
    # 点集互检（顺序/方向无关）
    for pm in mirrored:
        assert min(pm.distance_to(pt) for pt in top_pts) < 1e-3, \
            f"镜像节点 {pm} 不在面层节点链上"
    for pt in top_pts:
        assert min(pt.distance_to(pm) for pm in mirrored) < 1e-3, \
            f"面层节点 {pt} 不在底层节点链镜像上"


def test_waist_symmetry(ctx_dart):
    """面层腰弧边 = 底层腰弧边镜像的子段（底层 b->P_w0 更长，面层 P1″->P_w0 是其镜像
    前缀；故镜像面层腰弧点全部落在底层腰弧上）。底层腰弧为长曲线，密集采样比对。"""
    ctx = ctx_dart
    piece, _ = build_front_pouch(ctx)
    a0, a1, _, _ = _local_axis(ctx)
    groups = _edges_by_name(piece)
    waist = groups["waist"][0]
    waist_dense = _sample(waist, 400)
    top_waist_pts = [p for g in groups["waist_m"] for p in _sample(g, 16)]
    # 镜像面层腰弧 -> 应落在底层腰弧上（P1′->P_w0 ⊂ b->P_w0）
    mirrored_top = [_reflect_point(p, a0, a1) for p in top_waist_pts]
    for pm in mirrored_top:
        assert min(pm.distance_to(p) for p in waist_dense) < 0.05, \
            f"镜像面层腰弧点 {pm} 不在底层腰弧上"


# ---------- 袋口挖削：面层袋口 = 袋口弧线（有省 C_cut / 无省净线）的镜像 ----------

def test_mouth_is_mirrored_cut_line(ctx_dart):
    """有省：面层袋口边 = 镜像(切削线 C_cut = front.pocket_mouth)。"""
    ctx = ctx_dart
    piece, _ = build_front_pouch(ctx)
    p_w0, k1 = ctx.point("front.pouch_waist_anchor"), ctx.point("front.pouch_node1")
    mouth_main = ctx.curve("front.pocket_mouth")          # C_cut（P1′->P2）
    # 主版袋口点 -> 镜像（P_w0-K1）-> 局部（与面层 mouth 边同坐标系比对）
    mouth_pts_main = _sample(mouth_main)
    mirrored_local_pts = [_to_local(_reflect_point(p, p_w0, k1), p_w0)
                          for p in mouth_pts_main]
    top_mouth_pts = [p for g in _edges_by_name(piece)["mouth"] for p in _sample(g)]
    for pm in mirrored_local_pts:
        assert min(pm.distance_to(pt) for pt in top_mouth_pts) < 1e-3, \
            f"镜像袋口点 {pm} 不在面层袋口边上"
    for pt in top_mouth_pts:
        assert min(pt.distance_to(pm) for pm in mirrored_local_pts) < 1e-3, \
            f"面层袋口点 {pt} 不在镜像切削线上"


def test_mouth_is_mirrored_baseline(ctx_nodart):
    """无省：面层袋口边 = 镜像(袋口净线 = front.pocket_mouth_baseline)。"""
    ctx = ctx_nodart
    piece, _ = build_front_pouch(ctx)
    p_w0, k1 = ctx.point("front.pouch_waist_anchor"), ctx.point("front.pouch_node1")
    baseline = ctx.curve("front.pocket_mouth_baseline")   # 净线（P1->P2）
    baseline_pts = _sample(baseline)
    mirrored_local_pts = [_to_local(_reflect_point(p, p_w0, k1), p_w0)
                          for p in baseline_pts]
    top_mouth_pts = [p for g in _edges_by_name(piece)["mouth"] for p in _sample(g)]
    for pm in mirrored_local_pts:
        assert min(pm.distance_to(pt) for pt in top_mouth_pts) < 1e-3
    for pt in top_mouth_pts:
        assert min(pt.distance_to(pm) for pm in mirrored_local_pts) < 1e-3
    # 无省时切削线 = 净线
    assert ctx.curve("front.pocket_mouth").p0.distance_to(baseline.p0) < 1e-9


def test_mouth_closes_dart(ctx_dart):
    """面层腰弧边起于省顶 P1′（镜像 P1″），与袋口切削线终端严合，省口闭合（§2.2）。"""
    ctx = ctx_dart
    piece, _ = build_front_pouch(ctx)
    p_w0, k1 = ctx.point("front.pouch_waist_anchor"), ctx.point("front.pouch_node1")
    p1m_local = _to_local(_reflect_point(
        ctx.point("front.pocket_p1_transfer"), p_w0, k1), p_w0)
    mouth_pts = [p for g in _edges_by_name(piece)["mouth"] for p in _sample(g)]
    waist_m_pts = [p for g in _edges_by_name(piece)["waist_m"] for p in _sample(g)]
    assert min(p1m_local.distance_to(p) for p in mouth_pts) < 1e-3
    assert min(p1m_local.distance_to(p) for p in waist_m_pts) < 1e-3


# ---------- 缩水：口袋布默认 0，绝对隔离大身面料（§3） ----------

def test_no_shrinkage_by_default(ctx_dart):
    piece, _ = build_front_pouch(ctx_dart)
    assert piece.shrunk_edges == ()      # 默认 0 -> 跳过 apply_shrinkage


def test_shrinkage_applied_when_set():
    o = PatternOptions(delta=1.0, front_pocket=True, front_pouch=True,
                       front_pouch_shrinkage_warp=0.03, front_pouch_shrinkage_weft=0.02)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    piece, _ = build_front_pouch(ctx)
    assert piece.shrunk_edges            # 非 0 -> 应用缩水
    assert any("缩水" in n for n in piece.notes)


# ---------- 辅助线（§5）：前口袋弧线（+有省省弧线）作底层画稿对位标记 ----------

def _marks_pts(piece):
    return [p for g in piece.marks for p in _sample(g)]


def test_marks_pocket_arcs(ctx_dart):
    """有省：marks = 折叠线 + 前口袋弧线（净线）+ 口袋省弧线（切削线），局部坐标。"""
    ctx = ctx_dart
    piece, _ = build_front_pouch(ctx)
    p_w0 = ctx.point("front.pouch_waist_anchor")
    mpts = _marks_pts(piece)
    for name in ("front.pocket_mouth_baseline", "front.pocket_mouth"):
        for p in _sample(ctx.curve(name)):
            lp = _to_local(p, p_w0)
            assert min(lp.distance_to(q) for q in mpts) < 1e-3, \
                f"{name} 点 {lp} 不在 marks 上"
    # 折叠线标记保留：两端 (0,0) 与 local_K1
    k1_local = _to_local(ctx.point("front.pouch_node1"), p_w0)
    assert any(q.distance_to(Point(0.0, 0.0)) < 1e-6 for q in mpts)
    assert any(q.distance_to(k1_local) < 1e-6 for q in mpts)


def test_marks_nodart_no_dart_arc(ctx_nodart):
    """无省：省弧线免上版（切削线=净线重合），marks = 折叠线 + 前口袋弧线。"""
    ctx = ctx_nodart
    piece, _ = build_front_pouch(ctx)
    assert len(piece.marks) == 2      # 默认 bulge 模式：折叠线 + 净线单曲线
    p_w0 = ctx.point("front.pouch_waist_anchor")
    mpts = _marks_pts(piece)
    for p in _sample(ctx.curve("front.pocket_mouth_baseline")):
        lp = _to_local(p, p_w0)
        assert min(lp.distance_to(q) for q in mpts) < 1e-3


def test_marks_polyline_chain():
    """polyline 折角模式：辅助线/刀口切线走折角链（多段直线）不断链。"""
    o = PatternOptions(delta=1.0, front_pocket=True, front_pouch=True,
                       front_pocket_dart_width=1.5,
                       front_pocket_mouth_mode="polyline",
                       front_pocket_mouth_corners=((0.4, 1.2), (0.7, 0.8)))
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    piece, _ = build_front_pouch(ctx)
    p_w0 = ctx.point("front.pouch_waist_anchor")
    mpts = _marks_pts(piece)
    i = 1
    while f"front.pocket_mouth_baseline_seg{i}" in ctx.sheet:
        for p in _sample(ctx.line(f"front.pocket_mouth_baseline_seg{i}")):
            lp = _to_local(p, p_w0)
            assert min(lp.distance_to(q) for q in mpts) < 1e-3
        i += 1
    _assert_closed(piece)
    assert _signed_area(piece) < 0
    assert all(_point_to_poly_dist(q, piece.gross_polygon) < 1e-6
               for q in piece.gross_notches)


# ---------- 刀口（§5.1/§5.2）：底层完整侧袋口弧线端点沿切线延长线交缝边 ----------

def _point_to_poly_dist(p: Point, poly) -> float:
    """点到闭合折线的最短距离（点到各段投影取最小）。"""
    best = float("inf")
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        ex, ey = b.x - a.x, b.y - a.y
        ll = ex * ex + ey * ey
        t = 0.0 if ll < 1e-18 else max(
            0.0, min(1.0, ((p.x - a.x) * ex + (p.y - a.y) * ey) / ll))
        q = Point(a.x + ex * t, a.y + ey * t)
        best = min(best, p.distance_to(q))
    return best


def test_notches_dart(ctx_dart):
    """有省：净刀口 = P1/P1′/P2（底层端点；挖削侧免打口 §5.3，无镜像点）；
    毛样刀口全部落在缝边（毛样折线）上且离净样线约一个缝份（§5.1）。"""
    ctx = ctx_dart
    piece, _ = build_front_pouch(ctx)
    p_w0 = ctx.point("front.pouch_waist_anchor")
    expected = [_to_local(ctx.point(n), p_w0) for n in
                ("front.pocket_p1", "front.pocket_p1_transfer",
                 "front.pocket_p2")]
    assert len(piece.notches) == 3
    for exp in expected:
        assert any(np.distance_to(exp) < 1e-6 for np in piece.notches), \
            f"缺少净刀口 {exp}"
    assert len(piece.gross_notches) == 3
    net_pts = [p for e in piece.net_edges for p in _sample(e.geom)]
    for q in piece.gross_notches:
        assert _point_to_poly_dist(q, piece.gross_polygon) < 1e-6, \
            f"毛样刀口 {q} 不在缝边（毛样折线）上"
        assert min(q.distance_to(p) for p in net_pts) > 0.3, \
            f"毛样刀口 {q} 贴着净样线，不在缝边上"


def test_notches_nodart(ctx_nodart):
    """无省：净刀口 = P1/P2（无省顶 P1′），毛样刀口在缝边上。"""
    ctx = ctx_nodart
    piece, _ = build_front_pouch(ctx)
    p_w0 = ctx.point("front.pouch_waist_anchor")
    expected = [_to_local(ctx.point(n), p_w0)
                for n in ("front.pocket_p1", "front.pocket_p2")]
    assert len(piece.notches) == 2
    for exp in expected:
        assert any(np.distance_to(exp) < 1e-6 for np in piece.notches)
    assert len(piece.gross_notches) == 2
    for q in piece.gross_notches:
        assert _point_to_poly_dist(q, piece.gross_polygon) < 1e-6


# ---------- 丝缕（§6）：竖向=经，继承大片裤中线方向 ----------

def test_grain_vertical(ctx_dart):
    piece, _ = build_front_pouch(ctx_dart)
    assert piece.grain is not None
    assert abs(piece.grain.a.x - piece.grain.b.x) < 1e-9   # 竖向：两端 x 相同


# ---------- 缝份（§4）：袋口放常规缝边，对折线 0 ----------

def test_seam_allowance_config():
    sa = PouchSeamAllowances()
    assert sa.fold == 0.0
    assert sa.mouth == 1.0
    assert sa.bottom == 1.2


# ---------- 开关守卫 ----------

def test_requires_front_pouch():
    o = PatternOptions(delta=1.0, front_pocket=True)   # 未开 front_pouch
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    with pytest.raises(ValueError, match="先开启 front_pouch"):
        build_front_pouch(ctx)
