"""前小表袋独立裁片测试（小表袋裁片.md §一~§四）。

金标（H=96, Δ=1.0, outseam=102，直腰头扣腰头宽 4）：
  模式 A（facing_intersect）：闭合拓扑 pt1→pt2→pt3→pt4→pt1 = 顶边（袋口直线，
  长 = watch_pocket_width）+ 内/外侧边（下延直线）+ 底边（袋贴内边贝塞尔子段，
  方向按角点归一，否则闭合链断裂）；边名 top/side/bottom/side（§4.1 三类缝份）。
  模式 B（custom）：锚点闭合链 1:1 拷贝；N=4 同模式 A 边名，N≠4 非顶边全 side
  （bottom 字段不生效）。
材质口径（§三）：口袋布里料缩水默认 0 绝对隔离大身面料（§3.1）；丝缕竖向
  继承主片径纬向，与小表袋在主版上的摆放旋转角无关（§3.2）。
刀口（§4.2）：袋口两角折边刀口 pt1/pt2 + 底边（模式 A）/最长非顶边（模式 B）
  弧长中点装配对位刀口。
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


def _main_geoms(ctx):
    """主版净样边序列（sheet.get 取 geom，line/curve 混合）。"""
    geoms = []
    i = 1
    while f"front.watch_pocket_seg{i}" in ctx.sheet:
        geoms.append(ctx.sheet.get(f"front.watch_pocket_seg{i}").geom)
        i += 1
    return geoms


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


# ---------- 刀口（§4.2）：折边刀口 + 装配对位刀口 ----------

def test_notches_facing(ctx_facing):
    ctx = ctx_facing
    piece, _ = build_watch_pocket(ctx)
    assert len(piece.notches) == 3
    # 折边刀口：袋口两角（局部化 pt1 = 原点、pt2）
    pt1_local = _to_local(ctx.point("front.watch_pocket_pt1"), ctx)
    pt2_local = _to_local(ctx.point("front.watch_pocket_pt2"), ctx)
    assert any(np.distance_to(pt1_local) < 1e-6 for np in piece.notches)
    assert any(np.distance_to(pt2_local) < 1e-6 for np in piece.notches)
    # 装配对位刀口：底边弧长中点（方向无关，独立复算）
    bottom_main = ctx.curve("front.watch_pocket_seg3")
    mid_local = _to_local(
        bottom_main.point_at_length(bottom_main.length() / 2), ctx)
    assert any(np.distance_to(mid_local) < 1e-6 for np in piece.notches), \
        f"缺少底边中点装配刀口 {mid_local}"


def test_notches_custom_curved():
    """模式 B 装配刀口 = 最长非顶边弧长/参数中点（独立复算，§4.2）。"""
    o = PatternOptions(delta=1.0, front_pocket=True, watch_pocket=True,
                       watch_pocket_mode="custom",
                       watch_pocket_points=[(0, 0), (10, 0), (10, 10), (0, 10)],
                       watch_pocket_edges=[("line",), ("arc", 2.0, 0.5),
                                           ("bezier", 30.0, 0.5, -30.0, 0.5),
                                           ("line",)])
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    piece, _ = build_watch_pocket(ctx)
    assert len(piece.notches) == 3
    pt1_local = _to_local(ctx.point("front.watch_pocket_pt1"), ctx)
    pt2_local = _to_local(ctx.point("front.watch_pocket_pt2"), ctx)
    assert any(np.distance_to(pt1_local) < 1e-6 for np in piece.notches)
    assert any(np.distance_to(pt2_local) < 1e-6 for np in piece.notches)
    g = max(_main_geoms(ctx)[1:], key=edge_length)
    mid_main = (g.point_at(0.5) if isinstance(g, LineSegment)
                else g.point_at_length(g.length() / 2))
    mid_local = _to_local(mid_main, ctx)
    assert any(np.distance_to(mid_local) < 1e-6 for np in piece.notches), \
        f"缺少最长非顶边中点装配刀口 {mid_local}"


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
