"""后贴袋独立裁片测试（后贴袋裁片.md §1~§5）。

金标（H=96, Δ=1.0, outseam=102，back_yoke+back_patch 开）：
  §1 净样 1:1 完整复制：四形态闭合链从整版 back.patch_net_seg{i} 拷贝，
  袋口 top 边长 = back_patch_width（摆放旋转角不改变长度）；
  边名派发：rectangle 1/2/1、baker_shield 1/2/2（底尖两斜边）、
  angular 1/2/3（两斜切）、custom N==4 同 rectangle、N≠4 非顶边全 side。
  §3/§4 hem 金标独立复算（从 net_edges 重建 t_h/N/镜像方向，不硬编坐标）：
  锚点 P_notch = 袋口净线延长线 ∩ 侧缝缝边线（侧边外法向偏移 sa_side，
  折边自毛样外侧缝边线起翻、翻盖全宽 = 毛样宽），
  T = M + t_h·|taper|（M = P_notch 沿镜像方向上行 sa_top）。
  §2 缩水：大身面料全链路（None 回退全局，区别于小表袋里料 0 隔离）。
  §5 丝缕竖向 = 后大片经向（与摆放旋转角无关）。
断言口径：几何不变量 + 独立复算，同 test_watch_pocket_piece。
"""

import pytest

from ylpattern.cutter import edge_length
from ylpattern.exporters.piece_svg import render_piece_svg
from ylpattern.flows.back_flow import FULL_FLOW
from ylpattern.flows.back_patch_flow import build_back_patch
from ylpattern.flows.runner import FlowRunner
from ylpattern.geometry import CubicBezier, LineSegment, Point, Vector
from ylpattern.params import (BackPatchSeamAllowances, Measurements,
                              PatternOptions)

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)


def _start(g): return g.a if isinstance(g, LineSegment) else g.p0
def _end(g):   return g.b if isinstance(g, LineSegment) else g.p3
def _sample(g, n=32):
    return [g.a, g.b] if isinstance(g, LineSegment) else g.sample(n)


def _run(**kw) -> PatternOptions:
    """整版跑完返回 ctx（back_yoke+back_patch 基线 + 覆写）。"""
    o = PatternOptions(delta=1.0, back_yoke=True, back_patch=True, **kw)
    return FlowRunner(M, o).run(FULL_FLOW)


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
    """毛样 bbox 不窄于净样（外法向正确外扩；折边侧向下外扩 sa_top）。"""
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


# ---------- hem 金标独立复算（§3/§4，从 net_edges 重建，不硬编坐标） ----------

def _hem_golden(piece, sa: BackPatchSeamAllowances, taper: float):
    """独立复算 (T1, T2, P_notch_a, P_notch_b)，公式同后贴袋裁片.md §3/§4。

    袋口 a→b（链序，shoelace<0 外法向外扩）：t_h 切线、N 外法向；
    锚点 P_notch = 袋口净线延长线 ∩ 侧缝缝边线（侧边沿外法向偏移 sa_side）
    ——折边自毛样外侧缝边线起翻，翻盖全宽 = 毛样宽；E = 角点处指向袋内的
    侧边方向 -> 镜像方向 D = E − 2(E·N)N（D·N>0）；
    M = P_notch + D·(sa_top/(D·N))（距袋口线 sa_top），T = M ± t_h·|taper|。
    """
    ne = piece.net_edges
    j = next(i for i, e in enumerate(ne) if e.name == "top")
    top = ne[j].geom
    assert isinstance(top, LineSegment)
    a, b = top.a, top.b
    t = (b - a).normalized()
    n = t.perpendicular()

    prev, nxt = ne[(j - 1) % len(ne)].geom, ne[(j + 1) % len(ne)].geom
    assert isinstance(prev, LineSegment) and isinstance(nxt, LineSegment)

    def mirror(e: Vector) -> Vector:
        k = -2.0 * (e.dx * n.dx + e.dy * n.dy)
        return Vector(e.dx + n.dx * k, e.dy + n.dy * k)

    def m_point(anchor: Point, e_in: Vector) -> Point:
        d = mirror(e_in)
        return anchor + d.scale(sa.top / (d.dx * n.dx + d.dy * n.dy))

    def p_notch(corner: Point, side: LineSegment) -> Point:
        """袋口净线（过 corner 方向 t）∩ 侧缝缝边线（侧边偏移 sa.side）。"""
        ts = (side.b - side.a).normalized()
        ns = ts.perpendicular()                 # 侧边外法向（链序同口径）
        o = corner + ns.scale(sa.side)
        # o + u·ts = corner + v·t -> 解 2x2 线性方程
        det = t.dx * ts.dy - t.dy * ts.dx
        v = ((o.x - corner.x) * ts.dy - (o.y - corner.y) * ts.dx) / det
        return corner + t.scale(v)

    pa, pb = p_notch(a, prev), p_notch(b, nxt)
    # E_a：前侧边末端切线取反（自 a 指向袋内）；E_b：后侧边首端切线
    e_a = (prev.a - prev.b).normalized()
    e_b = (nxt.b - nxt.a).normalized()
    t1 = m_point(pa, e_a) + t.scale(abs(taper))
    t2 = m_point(pb, e_b) + t.scale(-abs(taper))
    return t1, t2, pa, pb


def _in_poly(poly, p, tol=1e-9):
    return any(q.distance_to(p) < tol for q in poly)


# ---------- 几何不变量（四形态） ----------

@pytest.mark.parametrize("shape", ["rectangle", "baker_shield", "angular"])
def test_geometry_invariants(shape):
    piece, _ = build_back_patch(_run(back_patch_shape=shape))
    _assert_closed(piece)
    assert _signed_area(piece) < 0           # 自定向：cutter 外法向外扩
    _assert_outward(piece)
    assert piece.gross_polygon
    render_piece_svg(piece)


@pytest.mark.parametrize("points,edges", [
    (((0, 0), (14, 0), (14, 16), (0, 16)), ((0, 0),) * 4),        # N==4
    (((0, 0), (14, 0), (15, 8), (7, 18), (0, 15)), ((0, 0),) * 5)  # N==5
])
def test_custom_geometry_invariants(points, edges):
    piece, _ = build_back_patch(_run(
        back_patch_shape="custom",
        back_patch_custom_points=points, back_patch_custom_edges=edges))
    _assert_closed(piece)
    assert _signed_area(piece) < 0
    _assert_outward(piece)
    render_piece_svg(piece)


# ---------- 边结构：语义边名派发（§1 形态路由） ----------

def test_edge_names_rectangle():
    piece, _ = build_back_patch(_run())
    g = _edges_by_name(piece)
    assert len(g["top"]) == 1 and len(g["side"]) == 2 and len(g["bottom"]) == 1


def test_edge_names_baker_shield():
    piece, _ = build_back_patch(_run(back_patch_shape="baker_shield"))
    g = _edges_by_name(piece)
    assert len(g["top"]) == 1 and len(g["side"]) == 2 and len(g["bottom"]) == 2


def test_edge_names_angular():
    piece, _ = build_back_patch(_run(back_patch_shape="angular"))
    g = _edges_by_name(piece)
    assert len(g["top"]) == 1 and len(g["side"]) == 2 and len(g["bottom"]) == 3


def test_edge_names_custom_quad():
    """custom N==4：同 rectangle 三类边名（bottom 字段消费）。"""
    piece, _ = build_back_patch(_run(
        back_patch_shape="custom",
        back_patch_custom_points=((0, 0), (14, 0), (14, 16), (0, 16)),
        back_patch_custom_edges=((0, 0),) * 4))
    g = _edges_by_name(piece)
    assert len(g["top"]) == 1 and len(g["side"]) == 2 and len(g["bottom"]) == 1


def test_edge_names_custom_penta():
    """custom N≠4：非顶边全 side，无 bottom 命名边。"""
    piece, _ = build_back_patch(_run(
        back_patch_shape="custom",
        back_patch_custom_points=((0, 0), (14, 0), (15, 8), (7, 18), (0, 15)),
        back_patch_custom_edges=((0, 0),) * 5))
    g = _edges_by_name(piece)
    assert len(g["top"]) == 1 and len(g["side"]) == 4 and "bottom" not in g


# ---------- 净样 1:1：袋口边长 = 设计净宽（摆放旋转不改变，§1） ----------

def test_top_edge_length_rotated():
    """rotate 6° 摆放：净样仍 1:1，袋口长 = back_patch_width。"""
    piece, _ = build_back_patch(_run(back_patch_rotate_deg=6.0))
    assert edge_length(_edges_by_name(piece)["top"][0]) \
        == pytest.approx(14.0, abs=1e-3)


def test_top_edge_length_custom():
    piece, _ = build_back_patch(_run(
        back_patch_shape="custom",
        back_patch_custom_points=((0, 0), (12.5, 0), (12.5, 15), (0, 15)),
        back_patch_custom_edges=((0, 0),) * 4))
    assert edge_length(_edges_by_name(piece)["top"][0]) \
        == pytest.approx(12.5, abs=1e-3)


# ---------- hem 金标（§3 撇势倒梯形 + §4 P_notch 对位刀口） ----------

def test_hem_golden_independent_recompute():
    """独立复算 T1/T2/P_notch ×2：全部出现在毛样上（公式级金标）。"""
    o = PatternOptions(delta=1.0, back_yoke=True, back_patch=True,
                       back_patch_rotate_deg=6.0)     # 旋转摆放也成立
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, _ = build_back_patch(ctx)
    t1, t2, pa, pb = _hem_golden(piece, o.back_patch_seam_allowances,
                                 o.back_patch_top_hem_taper)
    assert _in_poly(piece.gross_polygon, t1), f"折边顶点 T1 {t1} 不在毛样上"
    assert _in_poly(piece.gross_polygon, t2), f"折边顶点 T2 {t2} 不在毛样上"
    assert any(n.distance_to(pa) < 1e-9 for n in piece.gross_notches), \
        f"P_notch(后浪侧) {pa} 不在毛样刀口中"
    assert any(n.distance_to(pb) < 1e-9 for n in piece.gross_notches), \
        f"P_notch(侧缝侧) {pb} 不在毛样刀口中"
    # 倒梯形顶边（折边线）∥ 袋口净线
    t_vec = t2 - t1
    top = _edges_by_name(piece)["top"][0]
    t_h = (top.b - top.a).normalized()
    assert abs(t_vec.dx * t_h.dy - t_vec.dy * t_h.dx) < 1e-9


def test_hem_taper_differential():
    """撇势差分金标：taper −0.15 -> −0.30，折边顶边缩短 2·Δ = 0.30。"""
    widths = []
    for taper in (-0.15, -0.30):
        o = PatternOptions(delta=1.0, back_yoke=True, back_patch=True,
                           back_patch_top_hem_taper=taper)
        piece, _ = build_back_patch(FlowRunner(M, o).run(FULL_FLOW))
        t1, t2, _, _ = _hem_golden(piece, o.back_patch_seam_allowances, taper)
        assert _in_poly(piece.gross_polygon, t1)
        assert _in_poly(piece.gross_polygon, t2)
        widths.append(t1.distance_to(t2))
    assert widths[0] - widths[1] == pytest.approx(0.30, abs=1e-9)


def test_hem_taper_zero_m_points_on_gross():
    """taper=0：T=M（自 P_notch 沿镜像方向上行 sa_top 即折边顶点），恰在毛样上。"""
    o = PatternOptions(delta=1.0, back_yoke=True, back_patch=True,
                       back_patch_top_hem_taper=0.0)
    piece, _ = build_back_patch(FlowRunner(M, o).run(FULL_FLOW))
    t1, t2, _, _ = _hem_golden(piece, o.back_patch_seam_allowances, 0.0)
    assert _in_poly(piece.gross_polygon, t1), f"折边顶点 {t1} 不在毛样上"
    assert _in_poly(piece.gross_polygon, t2), f"折边顶点 {t2} 不在毛样上"


def test_notch_type_geometry_unchanged():
    """刀口 V/I 型只进 notes，不改位置几何（§4：类型是工艺标注）。"""
    o_v = PatternOptions(delta=1.0, back_yoke=True, back_patch=True)
    o_i = PatternOptions(delta=1.0, back_yoke=True, back_patch=True,
                         back_patch_notch_type="I", back_patch_notch_depth=0.5)
    p_v, _ = build_back_patch(FlowRunner(M, o_v).run(FULL_FLOW))
    p_i, _ = build_back_patch(FlowRunner(M, o_i).run(FULL_FLOW))
    assert p_i.gross_polygon == p_v.gross_polygon
    assert p_i.gross_notches == p_v.gross_notches
    assert any("I 型 深 0.5" in note for note in p_i.notes)


# ---------- custom 弧袋口降级（§3 无直线镜像轴） ----------

def test_custom_curved_top_degrades():
    piece, _ = build_back_patch(_run(
        back_patch_shape="custom",
        back_patch_custom_points=((0, 0), (14, 0), (15, 8), (7, 18), (0, 15)),
        back_patch_custom_edges=((1.2, 0.5), (0, 0), (0, 0), (0, 0), (0, 0))))
    assert isinstance(_edges_by_name(piece)["top"][0], CubicBezier)
    assert any("降级" in note for note in piece.notes)
    # 刀口仅净角点：无 P_notch 追加
    assert len(piece.gross_notches) == len(piece.net_edges)


# ---------- 丝缕（§5）：竖向 = 后大片经向（与摆放旋转无关） ----------

def test_grain_vertical_rotated():
    piece, _ = build_back_patch(_run(back_patch_rotate_deg=8.0))
    assert piece.grain is not None
    assert abs(piece.grain.a.x - piece.grain.b.x) < 1e-9


# ---------- 缩水（§2 大身面料全链路：None 回退全局） ----------

def test_no_shrinkage_by_default():
    """全局缩水 0 且局部 None：跳过 apply_shrinkage。"""
    piece, _ = build_back_patch(_run())
    assert piece.shrunk_edges == ()


def test_shrinkage_local():
    o = PatternOptions(delta=1.0, back_yoke=True, back_patch=True,
                       back_patch_shrinkage_warp=0.03,
                       back_patch_shrinkage_weft=0.02)
    piece, _ = build_back_patch(FlowRunner(M, o).run(FULL_FLOW))
    assert piece.shrunk_edges
    assert any("缩水" in note for note in piece.notes)


def test_shrinkage_fallback_global():
    """局部 None + 全局非 0：回退全局（大身面料全链路口径，§2）。"""
    o_local = PatternOptions(delta=1.0, back_yoke=True, back_patch=True,
                             back_patch_shrinkage_warp=0.03,
                             back_patch_shrinkage_weft=0.02)
    o_global = PatternOptions(delta=1.0, back_yoke=True, back_patch=True,
                              shrinkage_warp=0.03, shrinkage_weft=0.02)
    p_local, _ = build_back_patch(FlowRunner(M, o_local).run(FULL_FLOW))
    p_global, _ = build_back_patch(FlowRunner(M, o_global).run(FULL_FLOW))
    assert p_global.shrunk_edges
    assert p_global.gross_polygon == p_local.gross_polygon   # 回退等价


# ---------- 局部 ctx 命名元素（trace/调试口径） ----------

def test_local_ctx_named_edges():
    _, local = build_back_patch(_run())
    ne = local.sheet
    i = 0
    while f"back_patch.edge{i}" in ne:
        i += 1
    assert i == 4                                   # rectangle 净边 4 段


# ---------- 开关守卫 ----------

def test_requires_back_patch_switch():
    o = PatternOptions(delta=1.0, back_yoke=True)   # 未开 back_patch
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    with pytest.raises(ValueError, match="先开启 back_patch"):
        build_back_patch(ctx)


def test_requires_patch_drawn():
    """--until 中断在后贴袋绘制之前：净样未上版，build 守卫拦截。"""
    o = PatternOptions(delta=1.0, back_yoke=True, back_patch=True)
    ctx = FlowRunner(M, o).run(FULL_FLOW, until="draw_back_yoke")
    assert "back.patch_net_seg1" not in ctx.sheet
    with pytest.raises(ValueError, match="依赖后贴袋绘制步骤"):
        build_back_patch(ctx)


def test_requires_yoke_switch():
    """back_patch 开但未开 back_yoke：步骤层守卫直接抛错（依赖育克定位）。"""
    o = PatternOptions(delta=1.0, back_patch=True)
    with pytest.raises(ValueError, match="开启 back_yoke"):
        FlowRunner(M, o).run(FULL_FLOW)


# ---------- 选项校验（__post_init__） ----------

def test_options_validation():
    with pytest.raises(ValueError, match="撇势"):
        PatternOptions(back_patch=True, back_patch_top_hem_taper=0.2)
    with pytest.raises(ValueError, match="刀口"):
        PatternOptions(back_patch=True, back_patch_notch_type="X")
    with pytest.raises(ValueError, match="刀口"):
        PatternOptions(back_patch=True, back_patch_notch_depth=-0.1)
    with pytest.raises(ValueError, match="缝份"):
        PatternOptions(back_patch=True,
                       back_patch_seam_allowances=BackPatchSeamAllowances(
                           top=-1.0))
    with pytest.raises(ValueError, match="back_patch_shrinkage_warp"):
        PatternOptions(back_patch=True, back_patch_shrinkage_warp=0.25)


def test_seam_allowance_defaults():
    sa = BackPatchSeamAllowances()
    assert sa.top == 2.5                 # 袋口折边双折（§2 示例 25mm）
    assert sa.side == 1.0
    assert sa.bottom == 1.0
