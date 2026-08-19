"""后机头/育克裁片测试（机头裁片.md §2~§5；直/弯腰头 × 有/无省）。

金标（M 同 test_back_yoke_steps：W=70, H=96, Δ=1.0, outseam=102，直腰头扣腰头宽 4，
默认 back_yoke_cb_dist=4.0 / back_yoke_side_dist=3.0，无锚点 -> 直线下口）：
  - 无省（§2.1）：四条边界（底边/侧缝/腰口/后中）围成封闭区，cutter 序 P0->PN->X->O。
  - 有省（§2.2，1 省 2cm）：右片绕省尖旋转闭合 -> 拼合处上下折角 G1 倒圆；
    同族边（bottom/top）内部所有衔接点切向共线（G1）。
  - 镜像折角（§4.2.1）：内缝顶点（bottom×side）与后中底角（bottom×cb）缝份用
    _mirror_point 而非 miter，相邻缝份翻折后与裁片重合；两角独立开关、直角退化即 miter。
    cutter 序后中角以 (cb,bottom) 出现，逆序键命中时交换 _mirror_point 形参。
断言口径：几何不变量（闭合、G1、外法向外扩、缩水轴向、刀口），不硬编坐标。
"""

import math

import pytest

from ylpattern.cutter import _mirror_point, _miter_point, add_seam_allowance
from ylpattern.exporters.piece_svg import render_piece_svg
from ylpattern.flows.back_flow import FULL_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.flows.yoke_flow import build_yoke
from ylpattern.geometry import CubicBezier, LineSegment, Point, Vector
from ylpattern.params import (Measurements, PatternOptions, YokeSeamAllowances,
                              WaistbandType)
from ylpattern.pieces import PatternPiece, PieceEdge

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)


def _assert_point_approx(a, b, *, abs=1e-3):
    assert a.x == pytest.approx(b.x, abs=abs)
    assert a.y == pytest.approx(b.y, abs=abs)


def _start(g): return g.a if isinstance(g, LineSegment) else g.p0
def _end(g):   return g.b if isinstance(g, LineSegment) else g.p3
def _start_tan(g):
    if isinstance(g, LineSegment):
        v = g.b - g.a
    else:
        v = g.tangent_at(0.0)
    return v.normalized()
def _end_tan(g):
    if isinstance(g, LineSegment):
        v = g.b - g.a
    else:
        v = g.tangent_at(1.0)
    return v.normalized()


def _edges_by_name(piece):
    """按 name 分组、保持轮廓顺序的边字典。"""
    groups: dict[str, list] = {}
    for e in piece.net_edges:
        groups.setdefault(e.name, []).append(e.geom)
    return groups


def _assert_outward(gross, net_edges):
    """毛样 bbox 不窄于净样（外法向正确外扩）。"""
    nxs, nys = [], []
    for e in net_edges:
        pts = [e.geom.a, e.geom.b] if isinstance(e.geom, LineSegment) \
            else e.geom.sample(20)
        nxs += [p.x for p in pts]
        nys += [p.y for p in pts]
    assert max(p.x for p in gross) >= max(nxs) - 1e-9
    assert min(p.x for p in gross) <= min(nxs) + 1e-9
    assert max(p.y for p in gross) >= max(nys) - 1e-9
    assert min(p.y for p in gross) <= min(nys) + 1e-9


@pytest.fixture()
def ctx_straight():
    """直腰头 + 无省（默认 cb/side 距离，无锚点 -> 直线下口）。"""
    o = PatternOptions(delta=1.0, back_yoke=True)
    return FlowRunner(M, o).run(FULL_FLOW)


@pytest.fixture()
def ctx_curved_nodart():
    o = PatternOptions(delta=1.0, back_yoke=True, waistband_type=WaistbandType.CURVED)
    return FlowRunner(M, o).run(FULL_FLOW)


@pytest.fixture()
def ctx_dart():
    """直腰头 + 1 省 2cm（省长 10 > 机头深 ~4，省腿穿越上下边界）。"""
    o = PatternOptions(delta=1.0, back_yoke=True, back_dart=True,
                       back_dart_count=1, back_dart_width=2.0,
                       back_dart_length=10.0)
    return FlowRunner(M, o).run(FULL_FLOW)


@pytest.fixture()
def ctx_curved_dart():
    o = PatternOptions(delta=1.0, back_yoke=True, waistband_type=WaistbandType.CURVED,
                       back_dart=True, back_dart_count=1, back_dart_width=2.0,
                       back_dart_length=10.0)
    return FlowRunner(M, o).run(FULL_FLOW)


# ---------- 无省：闭合 / 边名 / 局部坐标 / 负面积 ----------

def test_no_dart_net_edges_closed(ctx_straight):
    """无省净样边闭合：边 i 末端 == 边 i+1 首端（首末闭合）。"""
    piece, _ = build_yoke(ctx_straight)
    es = piece.net_edges
    n = len(es)
    assert n >= 4
    for i in range(n):
        _assert_point_approx(_end(es[i].geom), _start(es[(i + 1) % n].geom))


def test_no_dart_four_named_edges(ctx_straight):
    """无省四条命名边按 cutter 序 P0->PN->X->O：bottom/side/top/cb。"""
    piece, _ = build_yoke(ctx_straight)
    names = [e.name for e in piece.net_edges]
    # 起于 bottom、终于 cb；side、top 各出现一次（bottom 单段直线时仅 1 条）
    assert names[0] == "bottom"
    assert names[-1] == "cb"
    assert "side" in names and "top" in names
    assert names.count("side") == 1
    assert names.count("cb") == 1


def test_local_origin_at_zero(ctx_straight):
    """局部坐标原点（后中腰口端）映射到 (0,0)：cb 边首端 == (0,0)。"""
    piece, _ = build_yoke(ctx_straight)
    groups = _edges_by_name(piece)
    cb = groups["cb"][0]
    # cb 在 cutter 序末端，其首端 = origin（_to_local 后为 0,0）
    _assert_point_approx(_start(cb), Point(0.0, 0.0))


def test_grain_vertical(ctx_straight):
    """经向 = 局部 Y（后片裤长向）：丝缕线竖向（两端 x 相同）。"""
    piece, _ = build_yoke(ctx_straight)
    g = piece.grain
    assert g is not None
    assert g.a.x == pytest.approx(g.b.x)
    assert g.a.y != pytest.approx(g.b.y)


def test_net_negative_area(ctx_straight):
    """cutter 负面积约定：净样多边形符号面积为负（外法向正确外扩的前提）。"""
    piece, _ = build_yoke(ctx_straight)
    poly = []
    for e in piece.net_edges:
        g = e.geom
        poly += [g.a, g.b] if isinstance(g, LineSegment) else g.sample(20)
    s = 0.0
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        s += (a.x * b.y - b.x * a.y)
    assert s < 0


# ---------- 有省：闭合 / 边数增加 / G1 圆顺 / 刀口 ----------

def test_dart_net_edges_closed(ctx_dart):
    piece, _ = build_yoke(ctx_dart)
    es = piece.net_edges
    for i in range(len(es)):
        _assert_point_approx(_end(es[i].geom), _start(es[(i + 1) % len(es)].geom))


def test_dart_inserts_fillet_edges(ctx_straight, ctx_dart):
    """有省时 bottom/top 同族边各插入倒圆三件组（>无省的 1 条）。"""
    piece_n, _ = build_yoke(ctx_straight)
    piece_d, _ = build_yoke(ctx_dart)
    gn = _edges_by_name(piece_n)
    gd = _edges_by_name(piece_d)
    # 无省 bottom/top 各 1 条；有省各 >= 3（tin+fillet+tout）
    assert len(gd["bottom"]) >= 3
    assert len(gd["top"]) >= 3
    assert len(gd["bottom"]) > len(gn["bottom"])
    assert len(gd["top"]) > len(gn["top"])


def test_dart_g1_smooth_within_groups(ctx_dart):
    """同族边（bottom/top）内部所有衔接点切向共线（G1，倒圆 + 链切分皆平滑）。"""
    piece, _ = build_yoke(ctx_dart)
    for name in ("bottom", "top"):
        geoms = _edges_by_name(piece)[name]
        for i in range(len(geoms) - 1):
            te = _end_tan(geoms[i])
            ts = _start_tan(geoms[i + 1])
            cross = te.dx * ts.dy - te.dy * ts.dx
            assert abs(cross) < 1e-6, f"{name} 衔接 {i} 切向不共线 cross={cross}"


def test_dart_join_notches(ctx_dart):
    """有省刀口：拼合线两端（C_in 底边侧、St_in 腰口侧）+ 后中点。"""
    piece, _ = build_yoke(ctx_dart)
    # 1 省 -> C_in + St_in + 后中 = 3 刀口
    assert len(piece.notches) >= 3


# ---------- 刀口毛样位（§5.1 净线延长线交缝边）----------

def _poly_min_dist(poly, p) -> float:
    """点到闭合折线的最小距离。"""
    best = float("inf")
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        ex, ey = b.x - a.x, b.y - a.y
        ll = ex * ex + ey * ey
        t = max(0.0, min(1.0, ((p.x - a.x) * ex + (p.y - a.y) * ey) / ll)) if ll else 0.0
        best = min(best, p.distance_to(Point(a.x + ex * t, a.y + ey * t)))
    return best


def _walk_corners(base):
    """cutter 序相邻异名边角点：(角点, 入边末切向, 出边首切向)。"""
    out = []
    n = len(base)
    for i in range(n):
        a, b = base[i], base[(i + 1) % n]
        if a.name != b.name:
            out.append((_end(a.geom), _end_tan(a.geom), _start_tan(b.geom)))
    return out


def test_corner_notches_count_no_dart(ctx_straight):
    """无省毛样刀口 = 4 角 × 2 + 后中 = 9，全部落在毛样外沿。"""
    piece, _ = build_yoke(ctx_straight)
    assert len(piece.gross_notches) == 9
    for q in piece.gross_notches:
        assert _poly_min_dist(piece.gross_polygon, q) < 1e-6


def test_corner_notches_count_curved(ctx_curved_nodart):
    """弯腰头无省同口径：4 角 × 2 + 后中 = 9（腰口换下腰头弧，角点拓扑不变）。"""
    piece, _ = build_yoke(ctx_curved_nodart)
    assert len(piece.gross_notches) == 9
    for q in piece.gross_notches:
        assert _poly_min_dist(piece.gross_polygon, q) < 1e-6


def test_corner_notches_on_extension_rays(ctx_straight):
    """角刀口顺净线延长线（§5.1）：与角点连线分别平行入边末切向 / 出边首切向
    反向，且指向毛样外侧（沿净样线的延长线向外侧缝边打出）。"""
    piece, _ = build_yoke(ctx_straight)
    base = piece.shrunk_edges or piece.net_edges
    corners = _walk_corners(base)
    assert len(corners) == 4
    gross = piece.gross_notches[:8]        # 前 8 个 = 角刀口（行走序、每角 2 刀）
    for (p, t_a, t_b), q_in, q_out in zip(corners, gross[0::2], gross[1::2]):
        for q, d in ((q_in, t_a), (q_out, t_b.scale(-1.0))):
            v = q - p
            cross = v.dx * d.dy - v.dy * d.dx
            assert abs(cross) < 1e-6, f"刀口不在净线延长线上 cross={cross}"
            assert v.dx * d.dx + v.dy * d.dy > 0, "刀口在延长线反方向"


def test_cb_notch_at_seam_allowance(ctx_straight):
    """后中刀口毛样位：cb 净中点沿外法向平移一个 cb 缝份（直线边解析精确，
    同腰头后中「垂线交缝边」口径）。"""
    piece, _ = build_yoke(ctx_straight)
    base = piece.shrunk_edges or piece.net_edges
    cb = next(e.geom for e in base if e.name == "cb")
    mid = Point((_start(cb).x + _end(cb).x) / 2, (_start(cb).y + _end(cb).y) / 2)
    n = _start_tan(cb).perpendicular()     # 外法向（cutter 外扩同约定）
    sa_cb = ctx_straight.options.back_yoke_seam_allowances.cb
    q = piece.gross_notches[-1]            # 末位 = 后中（行走序角刀口在前）
    _assert_point_approx(q, mid + n.scale(sa_cb))


def test_dart_notches_projected_to_gross(ctx_dart):
    """有省毛样刀口 = 4 角 × 2 + 后中 + 省位 2 刀 = 11，省位刀口落毛样外沿。"""
    piece, _ = build_yoke(ctx_dart)
    assert len(piece.gross_notches) == 11
    for q in piece.gross_notches[-2:]:
        assert _poly_min_dist(piece.gross_polygon, q) < 1e-6


def test_dart_negative_area(ctx_dart):
    piece, _ = build_yoke(ctx_dart)
    poly = []
    for e in piece.net_edges:
        g = e.geom
        poly += [g.a, g.b] if isinstance(g, LineSegment) else g.sample(20)
    s = 0.0
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        s += (a.x * b.y - b.x * a.y)
    assert s < 0


def test_curved_dart_builds(ctx_curved_dart):
    """弯腰头 + 有省：完整构建不抛错、闭合、G1。"""
    piece, _ = build_yoke(ctx_curved_dart)
    es = piece.net_edges
    for i in range(len(es)):
        _assert_point_approx(_end(es[i].geom), _start(es[(i + 1) % len(es)].geom))
    for name in ("bottom", "top"):
        geoms = _edges_by_name(piece)[name]
        for i in range(len(geoms) - 1):
            cross = (_end_tan(geoms[i]).dx * _start_tan(geoms[i + 1]).dy
                     - _end_tan(geoms[i]).dy * _start_tan(geoms[i + 1]).dx)
            assert abs(cross) < 1e-6


# ---------- 缩水（§3：经向=局部 Y）----------

def test_shrinkage_axes():
    """缩水：经向=局部 Y -> Y 吃 warp、X 吃 weft（apply_shrinkage 形参 1 控 X、2 控 Y）。"""
    o = PatternOptions(delta=1.0, back_yoke=True,
                       shrinkage_warp=0.03, shrinkage_weft=0.02)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, _ = build_yoke(ctx)
    sx, sy = 1.02, 1.03      # X=纬 1+weft、Y=经 1+warp
    # cb 边末端（P0 局部坐标，x/y 多半均非零）双轴校验
    nb = _end(_edges_by_name(piece)["cb"][0])
    sb = _end(piece.shrunk_edges[[e.name for e in piece.net_edges].index("cb")].geom)
    assert sb.x == pytest.approx(nb.x * sx)
    assert sb.y == pytest.approx(nb.y * sy)
    # 刀口同步缩放
    for n, s in zip(piece.notches, piece.shrunk_notches):
        assert s.x == pytest.approx(n.x * sx)
        assert s.y == pytest.approx(n.y * sy)


def test_shrinkage_dedicated_overrides_global():
    """机头专用缩水（back_yoke_shrinkage_warp/weft 非 None）覆盖全局值。

    全局 shrinkage_warp/weft=0，专用字段非 0 时裁片按专用值缩水（换布单独控制）。
    """
    o = PatternOptions(delta=1.0, back_yoke=True,
                       shrinkage_warp=0.0, shrinkage_weft=0.0,
                       back_yoke_shrinkage_warp=0.05,
                       back_yoke_shrinkage_weft=0.04)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, _ = build_yoke(ctx)
    sx, sy = 1.04, 1.05      # X=纬 1+weft(0.04)、Y=经 1+warp(0.05)
    nb = _end(_edges_by_name(piece)["cb"][0])
    sb = _end(piece.shrunk_edges[[e.name for e in piece.net_edges].index("cb")].geom)
    assert sb.x == pytest.approx(nb.x * sx)
    assert sb.y == pytest.approx(nb.y * sy)


def test_no_shrinkage_shrunk_equals_net(ctx_straight):
    piece, _ = build_yoke(ctx_straight)
    for n, s in zip(piece.net_edges, piece.shrunk_edges):
        _assert_point_approx(_end(n.geom), _end(s.geom))


# ---------- 缝边（§4：外法向外扩）----------

def test_seam_allowance_outward(ctx_straight):
    """缝边外扩：gross 在两轴上均不窄于净样（外法向正确）。"""
    sa = YokeSeamAllowances(top=1.0, bottom=1.2, cb=1.0, side=1.0)
    o = PatternOptions(delta=1.0, back_yoke=True, back_yoke_seam_allowances=sa)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, _ = build_yoke(ctx)
    net_xs, net_ys, gx, gy = [], [], [], []
    for e in piece.net_edges:
        g = e.geom
        pts = [g.a, g.b] if isinstance(g, LineSegment) else g.sample(20)
        net_xs += [p.x for p in pts]
        net_ys += [p.y for p in pts]
    gx = [p.x for p in piece.gross_polygon]
    gy = [p.y for p in piece.gross_polygon]
    assert max(gx) >= max(net_xs) - 1e-9
    assert min(gx) <= min(net_xs) + 1e-9
    assert max(gy) >= max(net_ys) - 1e-9
    assert min(gy) <= min(net_ys) + 1e-9


def test_seam_allowance_zero_matches_net(ctx_straight):
    """缝份全 0：gross 边界 == 净样边界（不外扩）。"""
    sa = YokeSeamAllowances(top=0, bottom=0, cb=0, side=0)
    o = PatternOptions(delta=1.0, back_yoke=True, back_yoke_seam_allowances=sa)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    piece, _ = build_yoke(ctx)
    net_xs, net_ys = [], []
    for e in piece.net_edges:
        g = e.geom
        pts = [g.a, g.b] if isinstance(g, LineSegment) else g.sample(20)
        net_xs += [p.x for p in pts]
        net_ys += [p.y for p in pts]
    gx = [p.x for p in piece.gross_polygon]
    gy = [p.y for p in piece.gross_polygon]
    assert max(gx) == pytest.approx(max(net_xs), abs=1e-6)
    assert min(gx) == pytest.approx(min(net_xs), abs=1e-6)
    assert max(gy) == pytest.approx(max(net_ys), abs=1e-6)
    assert min(gy) == pytest.approx(min(net_ys), abs=1e-6)


# ---------- 独立 SVG（§5）----------

def test_svg_render(ctx_straight):
    piece, _ = build_yoke(ctx_straight)
    svg = render_piece_svg(piece)
    assert svg.startswith("<svg")
    assert "gross" in svg
    assert "net" in svg
    assert "grain" in svg
    assert "后育克裁片" in svg


def test_svg_with_dart_notch(ctx_dart):
    piece, _ = build_yoke(ctx_dart)
    svg = render_piece_svg(piece)
    assert svg.startswith("<svg")
    assert "notch" in svg


# ---------- 选项校验 / 多省回退 ----------

def test_options_validation():
    with pytest.raises(ValueError):
        PatternOptions(delta=1.0, back_yoke=True,
                       back_yoke_seam_allowances=YokeSeamAllowances(top=-1.0))
    with pytest.raises(ValueError):
        PatternOptions(delta=1.0, back_yoke=True,
                       back_yoke_seam_allowances=YokeSeamAllowances(bottom=-0.1))
    with pytest.raises(ValueError):
        PatternOptions(delta=1.0, back_yoke=True, back_yoke_join_fillet=-0.5)
    with pytest.raises(ValueError, match="back_yoke_shrinkage_warp"):
        PatternOptions(delta=1.0, back_yoke=True, back_yoke_shrinkage_warp=0.5)
    with pytest.raises(ValueError, match="back_yoke_shrinkage_weft"):
        PatternOptions(delta=1.0, back_yoke=True, back_yoke_shrinkage_weft=-0.1)


def test_two_darts_fallback_no_error():
    """2 省：当前仅支持 1 省 -> 回退无省提取（不抛错，产出无省结构）。"""
    o = PatternOptions(delta=1.0, back_yoke=True, back_dart=True,
                       back_dart_count=2, back_dart_width=[2.0, 2.0],
                       back_dart_length=10.0)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    assert "back.dart2_apex" in ctx.sheet          # 确有 2 省
    piece, _ = build_yoke(ctx)                       # 回退无省，不抛错
    # 无省结构：bottom/top 各 1 段（无倒圆三件组）
    groups = _edges_by_name(piece)
    assert len(groups["bottom"]) == 1
    assert len(groups["top"]) == 1


def test_curved_no_dart_builds(ctx_curved_nodart):
    """弯腰头无省：完整构建不抛错。"""
    piece, _ = build_yoke(ctx_curved_nodart)
    assert piece.gross_polygon
    es = piece.net_edges
    for i in range(len(es)):
        _assert_point_approx(_end(es[i].geom), _start(es[(i + 1) % len(es)].geom))


# ---------- 镜像折角（§镜像折角：bottom×side 缝份翻折重合）----------

def test_mirror_point_right_angle_equals_miter():
    """直角角点：侧缝切线与对称轴 n_a 平行 -> 镜像不变 -> 退化即 miter。"""
    p = Point(0.0, 0.0)
    t_a, t_b = Vector(1.0, 0.0), Vector(0.0, 1.0)   # 90° 角
    m = _mirror_point(p, t_a, t_b, 1.0, 1.0)
    mit = _miter_point(p, t_a, t_b, 1.0, 1.0)
    _assert_point_approx(m, Point(-1.0, 1.0))        # 演算：off_a=(0,1)、交 x=-1
    _assert_point_approx(m, mit)


def test_mirror_point_slanted_differs_from_miter():
    """斜角（60° 侧缝）镜像 = 侧缝缝份边界**整条线**关于底边净缝线轴对称
    （锚点 + 方向同步镜像，2026-08-19 真反折角）；与 miter 相异。"""
    p = Point(0.0, 0.0)
    t_a = Vector(1.0, 0.0)
    t_b = Vector(0.5, math.sqrt(3) / 2)              # 60° 斜侧缝
    m = _mirror_point(p, t_a, t_b, 1.0, 1.0)
    mit = _miter_point(p, t_a, t_b, 1.0, 1.0)
    # 演算（cutter._mirror_point 真反折角）：miter=(-1/√3, 1)；
    # 镜像锚点 off_b=(−√3/2,1/2) 轴对称至 (−√3/2,−1/2)、方向 (0.5,−√3/2)，
    # 交底边缝份边界 y=1 于 mirror=(−√3, 1)；翻折像 (−√3,−1) 恰落侧缝
    # 毛边线（off_b + t_b·(−√3)），缝份翻折不缺肉
    _assert_point_approx(mit, Point(-1.0 / math.sqrt(3), 1.0))
    _assert_point_approx(m, Point(-math.sqrt(3), 1.0))
    assert m.x != pytest.approx(mit.x)


def _quad_piece(side_top):
    """机头样四边形 P0->PN->X->O（负面积）：side_top=PN 侧缝上端 X，控制侧缝倾角。"""
    P0, PN, O = Point(0.0, 5.0), Point(6.0, 5.0), Point(0.0, 0.0)
    edges = (PieceEdge("bottom", LineSegment(P0, PN)),
             PieceEdge("side", LineSegment(PN, side_top)),
             PieceEdge("top", LineSegment(side_top, O)),
             PieceEdge("cb", LineSegment(O, P0)))
    return PatternPiece("test", "测试", edges)


def test_add_seam_allowance_mirror_slanted_corner_differs():
    """斜角（bottom×side）镜像折角 != miter：毛样在 PN 角相异；仍外扩包住净样。"""
    sa = {"top": 1.0, "bottom": 1.2, "cb": 1.0, "side": 1.0}
    base = _quad_piece(Point(5.0, 0.0))               # 侧缝斜（PN->X 向左上）
    g_mit = add_seam_allowance(base, sa).gross_polygon
    g_mir = add_seam_allowance(base, sa,
                               {("bottom", "side"): "mirror"}).gross_polygon
    assert g_mir != g_mit
    nxs, nys = [0.0, 6.0, 5.0, 0.0], [5.0, 5.0, 0.0, 0.0]
    for g in (g_mir, g_mit):
        assert max(p.x for p in g) >= max(nxs) - 1e-9
        assert min(p.x for p in g) <= min(nxs) + 1e-9
        assert max(p.y for p in g) >= max(nys) - 1e-9
        assert min(p.y for p in g) <= min(nys) + 1e-9


def test_add_seam_allowance_mirror_right_angle_equals_miter():
    """直角（侧缝竖直）镜像退化即 miter：毛样与纯 miter 完全相同。"""
    sa = {"top": 1.0, "bottom": 1.2, "cb": 1.0, "side": 1.0}
    base = _quad_piece(Point(6.0, 0.0))               # 侧缝竖直 -> bottom×side 直角
    g_mit = add_seam_allowance(base, sa).gross_polygon
    g_mir = add_seam_allowance(base, sa,
                               {("bottom", "side"): "mirror"}).gross_polygon
    assert len(g_mir) == len(g_mit)
    for a, b in zip(g_mir, g_mit):
        _assert_point_approx(a, b)


def test_add_seam_allowance_mirror_cb_corner_swap():
    """后中底角 (bottom×cb) 斜角镜像：cutter 序以 (cb,bottom) 出现，逆序键
    ("bottom","cb") 命中时 cutter 交换 _mirror_point 形参；与 miter 相异且外扩。"""
    sa = {"top": 1.0, "bottom": 1.2, "cb": 1.0, "side": 1.0}
    # cb 边斜（O->P0）、side 竖直（PN 直角）：仅 cb 角为斜角
    P0, PN, X, O = Point(0.0, 5.0), Point(6.0, 5.0), Point(6.0, 0.0), Point(1.0, 0.0)
    edges = (PieceEdge("bottom", LineSegment(P0, PN)),
             PieceEdge("side", LineSegment(PN, X)),
             PieceEdge("top", LineSegment(X, O)),
             PieceEdge("cb", LineSegment(O, P0)))
    base = PatternPiece("test", "测试", edges)
    g_mit = add_seam_allowance(base, sa).gross_polygon
    g_mir = add_seam_allowance(base, sa,
                               {("bottom", "cb"): "mirror"}).gross_polygon
    assert g_mir != g_mit                          # 后中底角折角不同
    _assert_outward(g_mir, base.net_edges)
    _assert_outward(g_mit, base.net_edges)


def test_yoke_corner_mirror_side_option():
    """back_yoke_side_corner_mirror：仅侧缝角开/关 -> 毛样相异，均外扩。"""
    def _gross(side, cb):
        o = PatternOptions(delta=1.0, back_yoke=True,
                           back_yoke_side_corner_mirror=side,
                           back_yoke_cb_corner_mirror=cb)
        ctx = FlowRunner(M, o).run(FULL_FLOW)
        piece, _ = build_yoke(ctx)
        return piece.gross_polygon, piece.net_edges
    g_on, net = _gross(True, False)
    g_off, _ = _gross(False, False)
    assert g_on != g_off                            # 侧缝角折角不同
    _assert_outward(g_on, net)
    _assert_outward(g_off, net)


def test_yoke_corner_mirror_cb_option():
    """back_yoke_cb_corner_mirror：仅后中角开/关 -> 毛样相异，均外扩。"""
    def _gross(side, cb):
        o = PatternOptions(delta=1.0, back_yoke=True,
                           back_yoke_side_corner_mirror=side,
                           back_yoke_cb_corner_mirror=cb)
        ctx = FlowRunner(M, o).run(FULL_FLOW)
        piece, _ = build_yoke(ctx)
        return piece.gross_polygon, piece.net_edges
    g_on, net = _gross(False, True)
    g_off, _ = _gross(False, False)
    assert g_on != g_off                            # 后中角折角不同
    _assert_outward(g_on, net)
    _assert_outward(g_off, net)
