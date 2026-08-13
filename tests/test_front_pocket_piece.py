"""前口袋独立裁片测试（前口袋裁片.md §一~§三；INSET 袋贴 / PATCH 贴袋）。

金标（M 同 test_pocket_facing_steps：W=70, H=96, Δ=1.0, outseam=102）：
  - INSET 袋贴：三段边界（腰弧 waist / 内边 inner / 外缝弧 side）1:1 复制前大片，
    闭合截取；内部保留袋口净线/切削线 + 吃省边（§1.1）；刀口标袋口净线起止端点（§2.2）。
  - PATCH 贴袋：净样母线 C(t) 直接拷贝（§1.2）；seg1=袋口 top 折边、其余=四周 side 缝边；
    刀口 = 各净角点（四周折边指示）。
断言口径：几何不变量（闭合、shoelace<0 自定向、外法向外扩、缩水轴向、刀口、丝缕竖向），
不硬编坐标。cutter 外法向要求闭合多边形 shoelace<0（同 test_yoke_piece 口径）。
"""

import pytest

from ylpattern.exporters.piece_svg import render_piece_svg
from ylpattern.flows.front_flow import FRONT_FLOW
from ylpattern.flows.front_pocket_flow import (build_front_facing,
                                               build_front_patch,
                                               build_front_pocket)
from ylpattern.flows.runner import FlowRunner
from ylpattern.geometry import CubicBezier, LineSegment, Point
from ylpattern.params import (FrontFacingSeamAllowances,
                              FrontPatchSeamAllowances, Measurements,
                              PatternOptions, WaistbandType)

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)


def _start(g): return g.a if isinstance(g, LineSegment) else g.p0
def _end(g):   return g.b if isinstance(g, LineSegment) else g.p3


def _sample(g, n=20):
    return [g.a, g.b] if isinstance(g, LineSegment) else g.sample(n)


def _assert_point_approx(a, b, *, abs=1e-3):
    assert a.x == pytest.approx(b.x, abs=abs)
    assert a.y == pytest.approx(b.y, abs=abs)


def _edges_by_name(piece):
    groups: dict[str, list] = {}
    for e in piece.net_edges:
        groups.setdefault(e.name, []).append(e.geom)
    return groups


def _signed_area(piece) -> float:
    poly = []
    for e in piece.net_edges:
        poly += _sample(e.geom)
    s = 0.0
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        s += a.x * b.y - b.x * a.y
    return s


def _assert_outward(gross, net_edges):
    """毛样 bbox 不窄于净样（外法向正确外扩）。"""
    nxs, nys = [], []
    for e in net_edges:
        for p in _sample(e.geom):
            nxs.append(p.x)
            nys.append(p.y)
    assert max(p.x for p in gross) >= max(nxs) - 1e-9
    assert min(p.x for p in gross) <= min(nxs) + 1e-9
    assert max(p.y for p in gross) >= max(nys) - 1e-9
    assert min(p.y for p in gross) <= min(nys) + 1e-9


@pytest.fixture()
def ctx_facing():
    """直腰头 + 有省 + 袋贴（tangent 模式）。侧缝深用默认（=袋贴宽 3.5，
    不超外缝弧臀围端可用弧长）。"""
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       front_pocket_facing_mode="tangent",
                       front_pocket_facing_width=3.5)
    return FlowRunner(M, o).run(FRONT_FLOW)


@pytest.fixture()
def ctx_facing_curved():
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       front_pocket_facing_mode="tangent",
                       waistband_type=WaistbandType.CURVED)
    return FlowRunner(M, o).run(FRONT_FLOW)


@pytest.fixture()
def ctx_facing_nodart():
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       front_pocket_facing_mode="tangent",
                       front_pocket_dart_width=0.0)
    return FlowRunner(M, o).run(FRONT_FLOW)


@pytest.fixture()
def ctx_patch_rect():
    o = PatternOptions(delta=1.0, front_patch=True, front_patch_shape="rectangle",
                       front_patch_width=14.0, front_patch_height=15.0)
    return FlowRunner(M, o).run(FRONT_FLOW)


@pytest.fixture()
def ctx_patch_shield():
    o = PatternOptions(delta=1.0, front_patch=True, front_patch_shape="baker_shield",
                       front_patch_width=14.0, front_patch_height=15.0,
                       front_patch_tip_depth=2.5, front_patch_bottom_width=12.0)
    return FlowRunner(M, o).run(FRONT_FLOW)


# ---------- INSET 袋贴：闭合 / 边名 / 自定向 / 丝缕 / 刀口 / 标记 ----------

def test_facing_net_edges_closed(ctx_facing):
    piece, _ = build_front_facing(ctx_facing)
    es = piece.net_edges
    n = len(es)
    assert n >= 3
    for i in range(n):
        _assert_point_approx(_end(es[i].geom), _start(es[(i + 1) % n].geom))


def test_facing_named_edges(ctx_facing):
    piece, _ = build_front_facing(ctx_facing)
    groups = _edges_by_name(piece)
    assert "waist" in groups and "inner" in groups and "side" in groups


def test_facing_negative_area(ctx_facing):
    """自定向：shoelace < 0（cutter 外法向正确外扩的前提，同 yoke 口径）。"""
    piece, _ = build_front_facing(ctx_facing)
    assert _signed_area(piece) < 0


def test_facing_grain_vertical(ctx_facing):
    """丝缕线竖向（经向 = 大片裤中线垂直方向 = 局部 Y，§2.3）。"""
    piece, _ = build_front_facing(ctx_facing)
    g = piece.grain
    assert g is not None
    assert g.a.x == pytest.approx(g.b.x)
    assert g.a.y != pytest.approx(g.b.y)


def test_facing_notches_two_endpoints(ctx_facing):
    """刀口 = 袋口净线起止端点 P1′/P1 + P2（§2.2 INSET 袋贴刀口）。"""
    piece, _ = build_front_facing(ctx_facing)
    assert len(piece.notches) == 2


def test_facing_marks_present_with_dart(ctx_facing):
    """有省：内部标记含袋口切削线 + 吃省边（§1.1 必须保留）。"""
    piece, _ = build_front_facing(ctx_facing)
    assert len(piece.marks) >= 2


def test_facing_marks_no_dart(ctx_facing_nodart):
    """无省：内部标记仅袋口净线（无吃省边）。"""
    piece, _ = build_front_facing(ctx_facing_nodart)
    assert len(piece.marks) == 1
    assert len(piece.notches) == 2


def test_facing_curved_builds(ctx_facing_curved):
    """弯腰头袋贴：完整构建不抛错、闭合、自定向。"""
    piece, _ = build_front_facing(ctx_facing_curved)
    es = piece.net_edges
    for i in range(len(es)):
        _assert_point_approx(_end(es[i].geom), _start(es[(i + 1) % len(es)].geom))
    assert _signed_area(piece) < 0


def test_facing_polyline_mode_closed():
    """polyline 模式内边为折角链 segN：闭合 + 自定向。"""
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       front_pocket_mouth_mode="polyline",
                       front_pocket_mouth_corners=[(0.4, 1.2), (0.7, 0.8)])
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    piece, _ = build_front_facing(ctx)
    es = piece.net_edges
    for i in range(len(es)):
        _assert_point_approx(_end(es[i].geom), _start(es[(i + 1) % len(es)].geom))
    assert _signed_area(piece) < 0


# ---------- PATCH 贴袋：闭合 / 边名 / 刀口 / 标记 ----------

def test_patch_net_edges_closed(ctx_patch_rect):
    piece, _ = build_front_patch(ctx_patch_rect)
    es = piece.net_edges
    n = len(es)
    assert n >= 3
    for i in range(n):
        _assert_point_approx(_end(es[i].geom), _start(es[(i + 1) % n].geom))


def test_patch_named_edges(ctx_patch_rect):
    """seg1=袋口 top 折边，其余=四周 side 缝边（§2.2）。自定向可能反转边序，
    故按名字集合校验（缝份按 getattr(边名) 取值，与顺序无关）。"""
    piece, _ = build_front_patch(ctx_patch_rect)
    names = [e.name for e in piece.net_edges]
    assert names.count("top") == 1
    assert all(n == "side" for n in names if n != "top")


def test_patch_notches_corners(ctx_patch_rect):
    """刀口 = 四周折边指示（各净角点，§2.2 PATCH 贴袋刀口）。rectangle 4 角。"""
    piece, _ = build_front_patch(ctx_patch_rect)
    assert len(piece.notches) == 4


def test_patch_marks_empty(ctx_patch_rect):
    """贴袋无内部标记弧线（§1.2 直接拷贝净样母线）。"""
    piece, _ = build_front_patch(ctx_patch_rect)
    assert piece.marks == ()


def test_patch_negative_area(ctx_patch_rect):
    piece, _ = build_front_patch(ctx_patch_rect)
    assert _signed_area(piece) < 0


def test_patch_shield_closed_and_notches(ctx_patch_shield):
    """baker_shield 5 角：闭合 + 5 刀口。"""
    piece, _ = build_front_patch(ctx_patch_shield)
    es = piece.net_edges
    for i in range(len(es)):
        _assert_point_approx(_end(es[i].geom), _start(es[(i + 1) % len(es)].geom))
    assert len(piece.notches) == 5


# ---------- 缩水（经向=局部 Y；apply_shrinkage(weft, warp)）----------

def test_shrinkage_axes():
    """缩水：经向=局部 Y -> Y 吃 warp、X 吃 weft；关于局部原点 (0,0) 仿射缩放。"""
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       shrinkage_warp=0.03, shrinkage_weft=0.02)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    piece, _ = build_front_facing(ctx)
    sx, sy = 1.02, 1.03      # X=纬 1+weft、Y=经 1+warp
    for ne, se in zip(piece.net_edges, piece.shrunk_edges):
        for npt, spt in zip(_sample(ne.geom), _sample(se.geom)):
            assert spt.x == pytest.approx(npt.x * sx, abs=1e-6)
            assert spt.y == pytest.approx(npt.y * sy, abs=1e-6)


def test_shrinkage_dedicated_overrides_global():
    """前口袋专用缩水（front_pocket_shrinkage_warp/weft 非 None）覆盖全局值。

    全局 shrinkage_warp/weft=0，专用字段非 0 时裁片按专用值缩水（换布单独控制）。
    """
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       shrinkage_warp=0.0, shrinkage_weft=0.0,
                       front_pocket_shrinkage_warp=0.05,
                       front_pocket_shrinkage_weft=0.04)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    piece, _ = build_front_facing(ctx)
    sx, sy = 1.04, 1.05      # X=纬 1+weft(0.04)、Y=经 1+warp(0.05)
    for ne, se in zip(piece.net_edges, piece.shrunk_edges):
        for npt, spt in zip(_sample(ne.geom), _sample(se.geom)):
            assert spt.x == pytest.approx(npt.x * sx, abs=1e-6)
            assert spt.y == pytest.approx(npt.y * sy, abs=1e-6)


def test_no_shrinkage_shrunk_equals_net(ctx_facing):
    piece, _ = build_front_facing(ctx_facing)
    for n, s in zip(piece.net_edges, piece.shrunk_edges):
        _assert_point_approx(_end(n.geom), _end(s.geom))


# ---------- 缝边（§2：外法向外扩）----------

def test_seam_allowance_outward_facing(ctx_facing):
    piece, _ = build_front_facing(ctx_facing)
    _assert_outward(piece.gross_polygon, piece.net_edges)


def test_seam_allowance_outward_patch(ctx_patch_rect):
    piece, _ = build_front_patch(ctx_patch_rect)
    _assert_outward(piece.gross_polygon, piece.net_edges)


def test_seam_allowance_zero_matches_net():
    """缝份全 0：gross 边界 == 净样边界（不外扩）。"""
    sa = FrontFacingSeamAllowances(waist=0, inner=0, side=0)
    o = PatternOptions(delta=1.0, front_pocket=True, front_pocket_facing=True,
                       front_pocket_facing_seam_allowances=sa)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    piece, _ = build_front_facing(ctx)
    nxs, nys = [], []
    for e in piece.net_edges:
        for p in _sample(e.geom):
            nxs.append(p.x)
            nys.append(p.y)
    gx = [p.x for p in piece.gross_polygon]
    gy = [p.y for p in piece.gross_polygon]
    assert max(gx) == pytest.approx(max(nxs), abs=1e-6)
    assert min(gx) == pytest.approx(min(nxs), abs=1e-6)
    assert max(gy) == pytest.approx(max(nys), abs=1e-6)
    assert min(gy) == pytest.approx(min(nys), abs=1e-6)


# ---------- 派发 / SVG / 选项校验 ----------

def test_build_front_pocket_dispatch_facing(ctx_facing):
    piece, _ = build_front_pocket(ctx_facing)
    assert piece.name == "front_facing"


def test_build_front_pocket_dispatch_patch(ctx_patch_rect):
    piece, _ = build_front_pocket(ctx_patch_rect)
    assert piece.name == "front_patch"


def test_build_front_pocket_no_pocket_raises():
    o = PatternOptions(delta=1.0)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    with pytest.raises(ValueError, match="先开启"):
        build_front_pocket(ctx)


def test_facing_svg_render(ctx_facing):
    piece, _ = build_front_facing(ctx_facing)
    svg = render_piece_svg(piece)
    assert svg.startswith("<svg")
    assert "gross" in svg and "net" in svg and "grain" in svg
    assert "marks" in svg            # 内部标记弧线层
    assert "袋贴" in svg


def test_patch_svg_render(ctx_patch_rect):
    piece, _ = build_front_patch(ctx_patch_rect)
    svg = render_piece_svg(piece)
    assert svg.startswith("<svg")
    assert "贴袋" in svg


def test_options_validation():
    with pytest.raises(ValueError, match="袋贴缝份"):
        PatternOptions(front_pocket_facing_seam_allowances=
                       FrontFacingSeamAllowances(waist=-1.0))
    with pytest.raises(ValueError, match="贴袋缝份"):
        PatternOptions(front_patch_seam_allowances=
                       FrontPatchSeamAllowances(top=-0.5))
    with pytest.raises(TypeError):
        PatternOptions(front_pocket_facing_seam_allowances="bad")
    with pytest.raises(TypeError):
        PatternOptions(front_patch_seam_allowances="bad")
    with pytest.raises(ValueError, match="front_pocket_shrinkage_warp"):
        PatternOptions(front_pocket_shrinkage_warp=0.5)
    with pytest.raises(ValueError, match="front_pocket_shrinkage_weft"):
        PatternOptions(front_pocket_shrinkage_weft=-0.1)


def test_seam_allowances_from_dict():
    sa = FrontFacingSeamAllowances.from_dict({"waist": 1.5, "inner": 0.8, "side": 1.2})
    assert (sa.waist, sa.inner, sa.side) == (1.5, 0.8, 1.2)
    ps = FrontPatchSeamAllowances.from_dict({"top": 4.0, "side": 1.0})
    assert (ps.top, ps.side) == (4.0, 1.0)
