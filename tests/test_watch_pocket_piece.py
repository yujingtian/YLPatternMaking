"""前小表袋独立裁片测试（小表袋裁片.md §一~§四）。

金标（H=96, Δ=1.0, outseam=102，直腰头扣腰头宽 4）：
  模式 A（facing_intersect）：闭合拓扑 pt1→pt2→pt3→pt4→pt1 = 顶边（袋口直线，
  长 = watch_pocket_width）+ 内/外侧边（下延直线）+ 底边（袋贴内边贝塞尔子段，
  方向按角点归一，否则闭合链断裂）；边名 top/side/bottom/side（§4.1 三类缝份）。
  模式 B（custom）：锚点闭合链 1:1 拷贝；N=4 同模式 A 边名，N≠4 非顶边全 side
  （bottom 字段不生效）。
材质口径（§三）：口袋布里料缩水默认 0 绝对隔离大身面料（§3.1）；丝缕竖向
  继承主片径纬向，与小表袋在主版上的摆放旋转角无关（§3.2）。
刀口（§4.2 v1.2）：袋口外上角/内上角各 2 刀共 4 刀——净样位 pt1/pt2
  （缝合线位），毛样位 = 顶点顺着缝边延长线交袋口缝边、顺着顶部线延长线
  交侧缝缝边（同前口袋 PATCH 每角 2 刀口径），严格落在毛样外沿上；
  中段装配对位刀口已按新数量规范移除。
断言口径：几何不变量 + 独立复算（不硬编坐标），同 test_pouch_piece。
"""

import pytest

from ylpattern.cutter import edge_length
from ylpattern.exporters.piece_svg import render_piece_svg
from ylpattern.flows.front_flow import FRONT_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.flows.watch_pocket_flow import build_watch_pocket
from ylpattern.geometry import CubicBezier, LineSegment, Point
from ylpattern.params import (Measurements, PatternOptions,
                              WatchPocketSeamAllowances)

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


def _to_local(p: Point, ctx) -> Point:
    """主版 -> 裁片局部（Y 反射，origin=pt1 袋口外上角）。"""
    origin = ctx.point("front.watch_pocket_pt1")
    return Point(p.x - origin.x, origin.y - p.y)


@pytest.fixture()
def ctx_facing():
    """模式 A：袋贴相交延伸（袋贴 tangent 内边 + 袋口定宽 7.5 + 旋转 5°）。"""
    o = PatternOptions(
        delta=1.0, front_pocket=True, front_pocket_facing=True,
        front_pocket_facing_mode="tangent", watch_pocket=True,
        watch_pocket_mode="facing_intersect", watch_pocket_width=7.5,
        watch_pocket_taper=0.3, watch_pocket_rotate_deg=5.0)
    return FlowRunner(M, o).run(FRONT_FLOW)


@pytest.fixture()
def ctx_custom():
    """模式 B：全自定义（默认梯形 4 锚点全直线）。"""
    o = PatternOptions(delta=1.0, front_pocket=True, watch_pocket=True,
                       watch_pocket_mode="custom")
    return FlowRunner(M, o).run(FRONT_FLOW)


# ---------- 几何不变量（模式 A 闭合链成立 = 底边方向归一正确） ----------

def test_facing_geometry_invariants(ctx_facing):
    piece, _ = build_watch_pocket(ctx_facing)
    _assert_closed(piece)
    assert _signed_area(piece) < 0           # 自定向：cutter 外法向正确外扩
    _assert_outward(piece)
    assert piece.gross_polygon               # 毛样已生成
    render_piece_svg(piece)                  # SVG 不报错


def test_custom_geometry_invariants(ctx_custom):
    piece, _ = build_watch_pocket(ctx_custom)
    _assert_closed(piece)
    assert _signed_area(piece) < 0
    _assert_outward(piece)
    assert piece.gross_polygon
    render_piece_svg(piece)


def test_custom_curved_geometry_invariants():
    """曲线边变体（arc/bezier 混合，§2.2 任意多边形闭合净形）。"""
    o = PatternOptions(delta=1.0, front_pocket=True, watch_pocket=True,
                       watch_pocket_mode="custom",
                       watch_pocket_points=[(0, 0), (10, 0), (10, 10), (0, 10)],
                       watch_pocket_edges=[("line",), ("arc", 2.0, 0.5),
                                           ("bezier", 30.0, 0.5, -30.0, 0.5),
                                           ("line",)])
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    piece, _ = build_watch_pocket(ctx)
    _assert_closed(piece)
    assert _signed_area(piece) < 0
    _assert_outward(piece)
    render_piece_svg(piece)


# ---------- 边结构：三类语义边齐备（§4.1） ----------

def test_edge_names_facing(ctx_facing):
    piece, _ = build_watch_pocket(ctx_facing)
    groups = _edges_by_name(piece)
    assert len(groups["top"]) == 1           # 袋口顶边（折边缝份 2.5）
    assert len(groups["side"]) == 2          # 内/外侧边（常规缝份 1.0）
    assert len(groups["bottom"]) == 1        # 底边（与袋贴拼接缝份一致）
    assert isinstance(groups["top"][0], LineSegment)
    assert isinstance(groups["bottom"][0], CubicBezier)   # 袋贴内边贝塞尔子段


def test_edge_names_custom_quad(ctx_custom):
    """N=4：同模式 A 三类边名（bottom 字段消费）。"""
    piece, _ = build_watch_pocket(ctx_custom)
    groups = _edges_by_name(piece)
    assert len(groups["top"]) == 1
    assert len(groups["side"]) == 2
    assert len(groups["bottom"]) == 1


def test_edge_names_custom_tri():
    """N≠4：非顶边全部 side，无 bottom 命名边（bottom 字段不生效）。"""
    o = PatternOptions(delta=1.0, front_pocket=True, watch_pocket=True,
                       watch_pocket_mode="custom",
                       watch_pocket_points=[(0, 0), (6, 0), (3, 7)],
                       watch_pocket_edges=[("line",), ("line",), ("line",)])
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    piece, _ = build_watch_pocket(ctx)
    groups = _edges_by_name(piece)
    assert len(groups["top"]) == 1
    assert len(groups["side"]) == 2
    assert "bottom" not in groups


# ---------- 净样 1:1：顶边长 = 袋口设计净宽（§二） ----------

def test_top_edge_length_facing(ctx_facing):
    piece, _ = build_watch_pocket(ctx_facing)
    assert edge_length(_edges_by_name(piece)["top"][0]) \
        == pytest.approx(7.5, abs=1e-3)      # 旋转不变长度


def test_top_edge_length_custom(ctx_custom):
    piece, _ = build_watch_pocket(ctx_custom)
    assert edge_length(_edges_by_name(piece)["top"][0]) \
        == pytest.approx(8.0, abs=1e-3)      # 默认锚点 (0,0)->(8,0)


# ---------- 模式 A 底边严格顺接袋贴内边（§2.1） ----------

def test_bottom_lies_on_facing_inner(ctx_facing):
    ctx = ctx_facing
    piece, _ = build_watch_pocket(ctx)
    facing = ctx.curve("front.pocket_facing_inner")
    facing_local = [_to_local(p, ctx) for p in facing.sample(400)]
    bottom_pts = _sample(_edges_by_name(piece)["bottom"][0], 64)
    for pb in bottom_pts:
        assert min(pb.distance_to(p) for p in facing_local) < 0.05, \
            f"底边点 {pb} 不在袋贴内边上"


# ---------- 刀口（§4.2 v1.2）：袋口两角折边刀口打在缝边上 ----------

def _poly_dist(p: Point, poly) -> float:
    """点到闭合折线的最短距离（刀口在毛样外沿上的判据）。"""
    best = float("inf")
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        ex, ey = b.x - a.x, b.y - a.y
        l2 = ex * ex + ey * ey
        t = (0.0 if l2 == 0.0 else
             max(0.0, min(1.0, ((p.x - a.x) * ex + (p.y - a.y) * ey) / l2)))
        dx, dy = p.x - a.x - t * ex, p.y - a.y - t * ey
        best = min(best, (dx * dx + dy * dy) ** 0.5)
    return best


def _tangent(g, at_end: bool):
    v = (g.b - g.a) if isinstance(g, LineSegment) else \
        g.tangent_at(1.0 if at_end else 0.0)
    return v.normalized()


def _line_cross(p, d, q, e):
    """直线 (p,方向 d) ∩ 直线 (q,方向 e)（独立复算延长线交点）。"""
    det = d.dx * e.dy - d.dy * e.dx
    assert abs(det) > 1e-9, "两线平行，测试夹具异常"
    s = ((q.x - p.x) * e.dy - (q.y - p.y) * e.dx) / det
    return p + d.scale(s)


def _top_corner_extension_hits(piece, sa):
    """袋口两角各 2 刀毛样位（独立复算，§4.2 v1.2）：顺着缝边延长线（角点
    沿入边末端切向）交出边缝份边界线、顺着顶部线反向延长（角点沿出边首端
    切向反向）交入边缝份边界线（与 flow 的射线求交同构不同径，金标口径）。"""
    base = piece.shrunk_edges or piece.net_edges
    n = len(base)
    j = [i for i, e in enumerate(base) if e.name == "top"][0]
    top = base[j]
    amt = {"top": sa.top, "side": sa.side, "bottom": sa.bottom}
    outs = []
    for in_e, out_e, corner in ((base[(j - 1) % n], top, _start(top.geom)),
                                (top, base[(j + 1) % n], _end(top.geom))):
        t_in, t_out = _tangent(in_e.geom, True), _tangent(out_e.geom, False)
        # 顺着缝边延长：角点沿入边切向射线 ∩ 出边缝份边界线
        s_out = corner + t_out.perpendicular().scale(amt[out_e.name])
        outs.append(_line_cross(corner, t_in, s_out, t_out))
        # 顺着顶部线反向延长：角点沿出边反向切向射线 ∩ 入边缝份边界线
        s_in = corner + t_in.perpendicular().scale(amt[in_e.name])
        outs.append(_line_cross(corner, t_out.scale(-1.0), s_in, t_in))
    return outs


def test_notches_facing(ctx_facing):
    """§4.2 v1.2：净样刀口 = 袋口两角（缝合线位）×2；毛样刀口 ×4 = 外/内
    上角各 2 刀——顺着缝边延长线交袋口缝边、顺着顶部线延长线交侧缝缝边
    （独立复算解析交点），且严格落在毛样外沿上。"""
    ctx = ctx_facing
    piece, _ = build_watch_pocket(ctx)
    assert len(piece.notches) == 2          # 无中段装配对位刀口（v1.2 移除）
    pt1_local = _to_local(ctx.point("front.watch_pocket_pt1"), ctx)
    pt2_local = _to_local(ctx.point("front.watch_pocket_pt2"), ctx)
    assert any(np.distance_to(pt1_local) < 1e-6 for np in piece.notches)
    assert any(np.distance_to(pt2_local) < 1e-6 for np in piece.notches)
    assert len(piece.gross_notches) == 4
    for g, m in zip(piece.gross_notches,
                    _top_corner_extension_hits(piece, WatchPocketSeamAllowances())):
        assert g.distance_to(m) < 1e-6, f"折边刀口 {g} 不在延长线交点 {m}"
        assert _poly_dist(g, piece.gross_polygon) < 1e-6, \
            f"折边刀口 {g} 不在毛样外沿缝边上"


def _top_corner_extension_rays(piece):
    """袋口两角延长射线 (角点, 方向) ×4，发射序与 flow 一致（独立复算切向）：
    每角顺着缝边延长（入边末端切向）+ 顺着顶部线反向延长（出边首端切向取反）。"""
    base = piece.shrunk_edges or piece.net_edges
    n = len(base)
    j = [i for i, e in enumerate(base) if e.name == "top"][0]
    top = base[j]
    rays = []
    for in_e, out_e, corner in ((base[(j - 1) % n], top, _start(top.geom)),
                                (top, base[(j + 1) % n], _end(top.geom))):
        t_in, t_out = _tangent(in_e.geom, True), _tangent(out_e.geom, False)
        rays.append((corner, t_in))               # 顺着缝边延长
        rays.append((corner, t_out.scale(-1.0)))  # 顺着顶部线反向延长
    return rays


def test_notches_custom_curved():
    """§4.2 v1.2 模式 B（line/arc/bezier 混合边）：毛样刀口 ×4 均严格落在
    毛样外沿上、且各与袋口角沿切向延长线共线（弧切向倾斜交点可远离角，
    距离无界不设角域，共线 + 外沿即"顺着延长线交缝边"的完整判据）。"""
    o = PatternOptions(delta=1.0, front_pocket=True, watch_pocket=True,
                       watch_pocket_mode="custom",
                       watch_pocket_points=[(0, 0), (10, 0), (10, 10), (0, 10)],
                       watch_pocket_edges=[("line",), ("arc", 2.0, 0.5),
                                           ("bezier", 30.0, 0.5, -30.0, 0.5),
                                           ("line",)])
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    piece, _ = build_watch_pocket(ctx)
    assert len(piece.notches) == 2
    assert len(piece.gross_notches) == 4
    for g, (corner, d) in zip(piece.gross_notches,
                              _top_corner_extension_rays(piece)):
        assert _poly_dist(g, piece.gross_polygon) < 1e-6, \
            f"折边刀口 {g} 不在毛样外沿缝边上"
        cross = (g.x - corner.x) * d.dy - (g.y - corner.y) * d.dx
        assert abs(cross) < 1e-6, f"折边刀口 {g} 不在角 {corner} 延长线上"
        assert (g.x - corner.x) * d.dx + (g.y - corner.y) * d.dy > 0, \
            f"折边刀口 {g} 在角 {corner} 延长线反向"


# ---------- 丝缕（§3.2）：竖向 = 经，继承主片（与摆放旋转角无关） ----------

def test_grain_vertical(ctx_facing):
    piece, _ = build_watch_pocket(ctx_facing)      # rotate 5° 仍竖向
    assert piece.grain is not None
    assert abs(piece.grain.a.x - piece.grain.b.x) < 1e-9   # 竖向：两端 x 相同


def test_grain_vertical_custom(ctx_custom):
    piece, _ = build_watch_pocket(ctx_custom)
    assert piece.grain is not None
    assert abs(piece.grain.a.x - piece.grain.b.x) < 1e-9


# ---------- 缩水（§3.1）：里料默认 0，绝对隔离大身面料 ----------

def test_no_shrinkage_by_default(ctx_facing):
    piece, _ = build_watch_pocket(ctx_facing)
    assert piece.shrunk_edges == ()      # 默认 0 -> 跳过 apply_shrinkage


def test_shrinkage_applied_when_set():
    o = PatternOptions(delta=1.0, front_pocket=True, watch_pocket=True,
                       watch_pocket_mode="custom",
                       watch_pocket_shrinkage_warp=0.03,
                       watch_pocket_shrinkage_weft=0.02)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    piece, _ = build_watch_pocket(ctx)
    assert piece.shrunk_edges            # 非 0 -> 应用缩水
    assert any("缩水" in n for n in piece.notes)


# ---------- 缝份（§4.1）：顶边折边 / 侧底常规 ----------

def test_seam_allowance_config():
    sa = WatchPocketSeamAllowances()
    assert sa.top == 2.5                 # 折边/双折边明线车缝（2.0~2.5 取上限）
    assert sa.side == 1.0
    assert sa.bottom == 1.0              # 默认与袋贴 inner 一致


def test_gross_extends_top_by_hem(ctx_facing):
    """顶边折边 2.5 明显大于侧/底 1.0：毛样沿袋口方向外扩量约 2.5（§4.1）。"""
    piece, _ = build_watch_pocket(ctx_facing)
    top = _edges_by_name(piece)["top"][0]
    n_ys = [p.y for e in piece.net_edges for p in _sample(e.geom)]
    # 局部 Y 向下、袋口在上：顶边净样 y = min；毛样最小 y 应低出约 2.5（1.5~3.5 内）
    top_y = min(p.y for p in _sample(top))
    drop = top_y - min(p.y for p in piece.gross_polygon)
    assert 1.5 < drop < 3.5, f"袋口折边外扩量异常：{drop}"


# ---------- 开关守卫 ----------

def test_requires_watch_pocket():
    o = PatternOptions(delta=1.0, front_pocket=True)   # 未开 watch_pocket
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    with pytest.raises(ValueError, match="先开启 watch_pocket"):
        build_watch_pocket(ctx)


def test_facing_mode_requires_facing():
    """模式 A 无袋贴：步骤层守卫（front.pocket_facing_inner 不存在）。"""
    o = PatternOptions(delta=1.0, front_pocket=True, watch_pocket=True,
                       watch_pocket_mode="facing_intersect")
    with pytest.raises(ValueError,
                       match="袋贴相交模式要求先开启袋贴绘制"):
        FlowRunner(M, o).run(FRONT_FLOW)
