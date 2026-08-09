"""门襟（连裁门襟）步骤测试（门襟绘制.md §2.1~§4）。

金标（H=96, Δ=1.0, front_rise=25, 默认 fly_*）：
  开深 L = 0.35×25 + 2.0 = 10.75；门襟宽 W = 3.8；Δw = 0.25；
  底角圆角内收 inset = 0.8（R = W−inset = 3.0，连裁/独立共用）；拐点弧位 turn = 1.0
  （J 底，默认）；融合下移 drop = None（自动取 W−R = 0.8）；明线内收 = 0.6。
  局部坐标（原点 O = 前浪∩裤身顶边，X 外凸、Y 沿前浪下行）：
    顶外角 T = (W−Δw, 0) = (3.55, 0)（§6 JSON waist_top_outer 同值）；
    角弧起点 P1 = (W, L−R) = (3.8, 7.75)（§3.2 J 型角弧）；
    拐点 P_turn = J 底 = (W−R, L) = (0.8, 10.75)（turn=1.0：90° 角弧终点，切向水平，§3.2）；
    融合点 P2 = 前浪底弧上自 O 量取 L+(W−R) = 11.55 处（裆弯弧，§3.2.3）；
    J 字明线 = 顺外边向内等距偏置 0.6 的虚线：
      (3.55−0.6, 0) = (2.95, 0) → (3.8−0.6, 7.75) = (3.2, 7.75)。
  拉链止口刀口、打枣点等工艺细节暂不绘制（§4，留待工艺/裁切模块）。
  直腰头 O = 前浪顶点 A；弯腰头 O = 下前中腰点 A'（裤身顶边），
  P2 自前浪顶点 A 沿前浪量取 腰头宽 + L + (W−R)。
"""

import pytest

from ylpattern.draft import curves
from ylpattern.flows.front_flow import FRONT_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.formulas import fly as fly_f
from ylpattern.params import Measurements, PatternOptions, WaistbandType

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
O = PatternOptions(delta=1.0, fly=True)


@pytest.fixture()
def ctx():
    return FlowRunner(M, O).run(FRONT_FLOW)


def _local(ctx, p):
    """全局点 → 门襟局部坐标（X 外凸、Y 沿前浪下行，相对门襟原点 O）。"""
    o_pt = ctx.point("front.fly_origin")
    yd = ctx.line("front.rise_slant").direction
    xd = yd.perpendicular()
    v = p - o_pt
    return (v.dx * xd.dx + v.dy * xd.dy, v.dx * yd.dx + v.dy * yd.dy)


def test_fly_skipped_by_default():
    # 可选步骤：默认开关关闭，不上版任何门襟元素
    ctx = FlowRunner(M, PatternOptions(delta=1.0)).run(FRONT_FLOW)
    assert "front.fly_bottom_arc" not in ctx.sheet
    assert "front.fly_origin" not in ctx.sheet


def test_fly_length_formula():
    # 公式层金标：L = 0.35 × 前浪 + 2.0（§2.2；front_rise=25 → 10.75）
    assert fly_f.fly_length(25) == pytest.approx(10.75)
    assert fly_f.fly_length(25, ratio=0.4, base=1.5) == pytest.approx(11.5)


def test_fly_corner_turn_point_formula():
    # 拐点 P_turn 及切向（局部 X 外凸、Y 沿前浪下行；W=3.8, L=10.75, R=3.0）
    # turn=1.0（J 底，θ=90°）：(W−R, L)=(0.8,10.75)，切向 (−1,0) 水平朝前浪
    (px, py), (tdx, tdy) = fly_f.fly_corner_turn_point(3.8, 10.75, 3.0, 1.0)
    assert (px, py) == (pytest.approx(0.8), pytest.approx(10.75))
    assert (tdx, tdy) == (pytest.approx(-1.0), pytest.approx(0.0))
    # turn=0.5（θ=45°）：(W−R+R/√2, L−R+R/√2)，切向 (−1/√2, 1/√2)
    (px, py), (tdx, tdy) = fly_f.fly_corner_turn_point(3.8, 10.75, 3.0, 0.5)
    s2 = 3 * 2 ** -0.5
    assert (px, py) == (pytest.approx(0.8 + s2), pytest.approx(7.75 + s2))
    assert (tdx, tdy) == (pytest.approx(-2 ** -0.5), pytest.approx(2 ** -0.5))


def test_fly_blend_extend_min_formula():
    # 防波浪最小下移量（W=3.8, R=3.0）
    # turn=1.0（J 底）-> 0（任意正下移都不波浪）
    assert fly_f.fly_blend_extend_min(3.8, 3.0, 1.0) == pytest.approx(0.0)
    # turn=0.5（θ=45°）-> W − 2R + R√2 = 3.8 − 6 + 3√2 ≈ 2.043
    assert fly_f.fly_blend_extend_min(3.8, 3.0, 0.5) == pytest.approx(3.8 - 6 + 3 * 2 ** 0.5)
    # turn 越小（拐点越靠上）-> 所需下移越大
    assert fly_f.fly_blend_extend_min(3.8, 3.0, 0.3) > fly_f.fly_blend_extend_min(3.8, 3.0, 0.5)


def test_fly_origin_straight(ctx):
    # 直腰头：O = 前浪顶点 A（裤身顶边即上腰弧）
    assert ctx.point("front.fly_origin") == ctx.point("front.rise_top_point")


def test_fly_key_points_local(ctx):
    # 局部坐标金标（直腰头，与 §6 JSON 一致）
    tx, ty = _local(ctx, ctx.point("front.fly_top_outer"))
    assert (tx, ty) == (pytest.approx(3.55), pytest.approx(0.0))     # (W−Δw, 0)
    p1x, p1y = _local(ctx, ctx.point("front.fly_start"))
    assert (p1x, p1y) == (pytest.approx(3.8), pytest.approx(7.75))    # (W, L−R)
    tx2, ty2 = _local(ctx, ctx.point("front.fly_turn"))
    assert (tx2, ty2) == (pytest.approx(0.8), pytest.approx(10.75))   # J 底 (W−R, L)
    p2x, p2y = _local(ctx, ctx.point("front.fly_tangent"))
    assert p2y == pytest.approx(11.55, abs=0.01)                    # L + (W−R)（裆弯弧微偏）
    assert p2x < 0.05                                                 # 裆弯弧微凸（近前浪轴）


def test_fly_tangent_on_rise_straight(ctx):
    # P2 = 自 O(=A) 沿前浪（斜线 + 裆弯弧）量取 L + (W−R) = 11.55 的切点
    chain = (ctx.line("front.rise_slant"), ctx.curve("front.rise_curve"))
    assert ctx.point("front.fly_tangent") == curves.point_along_chain(chain, 11.55)


def test_fly_origin_and_tangent_curved():
    # 弯腰头：O = 下前中腰点 A'（裤身顶边为下腰头线）；
    # P2 自前浪顶点 A 沿前浪量取 腰头宽 + L + (W−R)（A' 已在 A 之下 W 处）
    o = PatternOptions(delta=1.0, fly=True, waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    assert ctx.point("front.fly_origin") == ctx.point("front.lower_waist_center_point")
    chain = (ctx.line("front.rise_slant"), ctx.curve("front.rise_curve"))
    assert ctx.point("front.fly_tangent") == curves.point_along_chain(
        chain, o.waistband_width + 11.55)


def test_fly_outline_structure(ctx):
    # 轮廓四段：顶边 O→T、外线 T→P1、角弧 P1→P_turn、融合弧 P_turn→P2，均为结构线（实线）
    assert ctx.line("front.fly_top_edge").a == ctx.point("front.fly_origin")
    assert ctx.line("front.fly_top_edge").b == ctx.point("front.fly_top_outer")
    assert ctx.line("front.fly_outer_edge").a == ctx.point("front.fly_top_outer")
    assert ctx.line("front.fly_outer_edge").b == ctx.point("front.fly_start")
    corner = ctx.curve("front.fly_corner_arc")
    assert corner.point_at(0) == ctx.point("front.fly_start")
    assert corner.point_at(1) == ctx.point("front.fly_turn")
    arc = ctx.curve("front.fly_bottom_arc")
    assert arc.point_at(0) == ctx.point("front.fly_turn")
    assert arc.point_at(1) == ctx.point("front.fly_tangent")
    assert ctx.sheet.get("front.fly_top_edge").role == "struct"
    assert ctx.sheet.get("front.fly_outer_edge").role == "struct"
    assert ctx.sheet.get("front.fly_corner_arc").role == "struct"   # 实线轮廓
    assert ctx.sheet.get("front.fly_bottom_arc").role == "struct"


def test_fly_complete_j_reference_default(ctx):
    # 默认 turn=1.0（拐点=J 底）：完整 J 型参考只剩 J 底边（虚线 ref），
    # 角弧余段退化不绘制；J 底边 = J 底 → 前浪@L（沿 −X，长 W−R）
    assert "front.fly_j_arc_rest" not in ctx.sheet          # turn=1.0 无余段
    edge = ctx.sheet.get("front.fly_j_bottom_edge")
    assert edge.role == "ref"                                # 虚线参考
    o_pt = ctx.point("front.fly_origin")
    yd = ctx.line("front.rise_slant").direction
    xd = yd.perpendicular()
    j_bottom = ctx.curve("front.fly_corner_arc").point_at(1)  # 拐点=J 底（turn=1.0）
    assert edge.geom.a.distance_to(j_bottom) < 1e-6          # J 底边起 = J 底
    v = edge.geom.b - o_pt
    assert abs(v.dx * xd.dx + v.dy * xd.dy) < 1e-6          # 终在前浪轴上（局部 X=0）
    assert abs(v.dx * yd.dx + v.dy * yd.dy - 10.75) < 0.02  # 前浪@L


def test_fly_complete_j_reference_custom_turn():
    # turn=0.5：完整 J 型参考 = 角弧余段（拐点→J 底，虚线）+ J 底边（J 底→前浪@L，虚线）；
    # 与实线角弧在拐点 G1、与 J 底边在 J 底 G1（完整 J 型一笔顺滑）
    o = PatternOptions(delta=1.0, fly=True, fly_corner_turn=0.5)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    rest = ctx.sheet.get("front.fly_j_arc_rest")
    edge = ctx.sheet.get("front.fly_j_bottom_edge")
    assert rest.role == "ref" and edge.role == "ref"
    assert rest.geom.point_at(0).distance_to(ctx.point("front.fly_turn")) < 1e-6
    o_pt = ctx.point("front.fly_origin")
    yd = ctx.line("front.rise_slant").direction
    xd = yd.perpendicular()
    end = rest.geom.point_at(1)
    v = end - o_pt
    assert abs(v.dx * xd.dx + v.dy * xd.dy - 0.8) < 1e-6     # J 底局部 X = W−R
    assert abs(v.dx * yd.dx + v.dy * yd.dy - 10.75) < 1e-6   # J 底局部 Y = L
    # G1：实线角弧末切向 == 虚线余段首切向
    solid = ctx.curve("front.fly_corner_arc").tangent_at(1).normalized()
    dash0 = rest.geom.tangent_at(0).normalized()
    assert solid.dx * dash0.dx + solid.dy * dash0.dy == pytest.approx(1.0)
    # G1：虚线余段末切向 == J 底边方向（水平 −X，平弧 J 字倒角）
    dash1 = rest.geom.tangent_at(1).normalized()
    bedir = (edge.geom.b - edge.geom.a).normalized()
    assert dash1.dx * bedir.dx + dash1.dy * bedir.dy == pytest.approx(1.0)


def test_fly_corner_arc_g1(ctx):
    # 完整 J 型角弧：起弧切线 ∥ 门襟外线方向、收弧切线 = J 底切向（水平朝前浪，§3.2）
    corner = ctx.curve("front.fly_corner_arc")
    outer_dir = ctx.line("front.fly_outer_edge").direction
    t0 = corner.tangent_at(0).normalized()
    t1 = corner.tangent_at(1).normalized()
    assert t0.dx * outer_dir.dx + t0.dy * outer_dir.dy == pytest.approx(1.0)
    # J 底切向 = 局部 −X（水平朝前浪）-> 全局
    yd = ctx.line("front.rise_slant").direction
    xd = yd.perpendicular()
    assert t1.dx * (-xd.dx) + t1.dy * (-xd.dy) == pytest.approx(1.0)


def test_fly_bottom_arc_g1(ctx):
    # 融合弧：起弧切线 = J 底切向（角弧末切向）、收弧切线 = P2 处前浪切向（两端 G1，§3.2.3）
    arc = ctx.curve("front.fly_bottom_arc")
    corner = ctx.curve("front.fly_corner_arc")
    turn_dir = corner.tangent_at(1).normalized()
    t0 = arc.tangent_at(0).normalized()
    assert t0.dx * turn_dir.dx + t0.dy * turn_dir.dy == pytest.approx(1.0)
    # P2 落在裆弯弧上 -> 末切向 = P2 处前浪弧切向（重算同步骤口径）
    o = ctx.options
    m = ctx.measurements
    rise_slant = ctx.line("front.rise_slant")
    rise_curve = ctx.curve("front.rise_curve")
    L = fly_f.fly_length(m.front_rise, o.fly_length_ratio, o.fly_length_base)
    rem = L + fly_f.fly_blend_extend(
        o.fly_width, fly_f.fly_corner_radius(o.fly_width, o.fly_corner_inset)) - rise_slant.length
    rise_tan = rise_curve.tangent_at(rise_curve.t_at_length(rem)).normalized()
    t1 = arc.tangent_at(1).normalized()
    assert t1.dx * rise_tan.dx + t1.dy * rise_tan.dy == pytest.approx(1.0)


def test_fly_bottom_arc_monotonic_no_wave(ctx):
    # 融合弧自 J 底单调下行融入前浪底弧（无波浪：旧版 P2 过浅致下坠后回升，§3.2.3）
    arc = ctx.curve("front.fly_bottom_arc")
    o_pt = ctx.point("front.fly_origin")
    yd = ctx.line("front.rise_slant").direction
    prev_y = -1e9
    for i in range(11):
        v = arc.point_at(i / 10) - o_pt
        y = v.dx * yd.dx + v.dy * yd.dy          # 局部深度
        assert y >= prev_y - 1e-6                 # 单调非减（无回升波浪）
        prev_y = y
    # P2 落在开深 L 之下（融合弧下移 W−R = 0.8）
    _, p2y = _local(ctx, ctx.point("front.fly_tangent"))
    assert p2y > 10.75


def test_fly_j_stitch(ctx):
    # J 字明线：顺门襟外边向内等距偏置 inset = 0.6 的直虚线（参考线，§4.2 简化）
    # 起点 = 顶外角 T 内收 (3.55−0.6, 0) = (2.95, 0)；
    # 终点 = 角弧起点 P1 内收 (3.8−0.6, 7.75) = (3.2, 7.75)
    s = ctx.line("front.fly_j_stitch")
    sx, sy = _local(ctx, s.a)
    ex, ey = _local(ctx, s.b)
    assert (sx, sy) == (pytest.approx(2.95), pytest.approx(0.0))
    assert (ex, ey) == (pytest.approx(3.2), pytest.approx(7.75))
    assert ctx.sheet.get("front.fly_j_stitch").role == "ref"


def _assert_blend_monotonic(ctx):
    """融合弧自拐点单调下行（局部 Y 非减），无波浪。"""
    o_pt = ctx.point("front.fly_origin")
    yd = ctx.line("front.rise_slant").direction
    blend = ctx.curve("front.fly_bottom_arc")
    prev = -1e9
    for i in range(11):
        v = blend.point_at(i / 10) - o_pt
        y = v.dx * yd.dx + v.dy * yd.dy
        assert y >= prev - 1e-6, f"融合弧回升（波浪）at t={i/10}: y={y} < prev={prev}"
        prev = y


def test_fly_custom_turn_auto_drop_monotonic():
    # turn=0.5（拐点 45°）+ drop=None：自动下移取 max(W−R, 防波浪最小值)=2.043，
    # 融合弧单调下行无波浪；P2 在 L+2.043 处（前浪底弧）
    o = PatternOptions(delta=1.0, fly=True, fly_corner_turn=0.5)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    _assert_blend_monotonic(ctx)
    _, p2y = _local(ctx, ctx.point("front.fly_tangent"))
    assert p2y == pytest.approx(10.75 + 2.043, abs=0.02)    # L + extend_min


def test_fly_custom_turn_manual_drop_monotonic():
    # turn=0.5 + drop=3.0（≥ 最小值 2.043）：手动下移，融合弧单调无波浪；P2 在 L+3.0
    o = PatternOptions(delta=1.0, fly=True, fly_corner_turn=0.5, fly_blend_drop=3.0)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    _assert_blend_monotonic(ctx)
    _, p2y = _local(ctx, ctx.point("front.fly_tangent"))
    assert p2y == pytest.approx(13.75, abs=0.02)            # L + 3.0


def test_fly_blend_drop_too_shallow_raises():
    # turn=0.5（需 ≥2.043）+ drop=0.5：过浅，步骤抛错防波浪（校验在步骤层，
    # 因防波浪最小值依赖 formulas，params 层不反向依赖 formulas）
    with pytest.raises(ValueError, match="防波浪"):
        FlowRunner(M, PatternOptions(delta=1.0, fly=True,
                                     fly_corner_turn=0.5,
                                     fly_blend_drop=0.5)).run(FRONT_FLOW)


def test_fly_options_validation():
    with pytest.raises(ValueError, match="门襟宽"):
        PatternOptions(fly_width=5.0)
    with pytest.raises(ValueError, match="不能为负数"):
        PatternOptions(fly_turnback=-0.1)
    with pytest.raises(ValueError, match="退层补偿"):
        PatternOptions(fly_turnback=3.8)
    with pytest.raises(ValueError, match="圆角内收"):
        PatternOptions(fly_corner_inset=3.8)              # >= W
    with pytest.raises(ValueError, match="圆角内收"):
        PatternOptions(fly_corner_inset=0.0)              # <= 0
    with pytest.raises(ValueError, match="拐点弧位"):
        PatternOptions(fly_corner_turn=1.5)
    with pytest.raises(ValueError, match="拐点弧位"):
        PatternOptions(fly_corner_turn=0.0)
    with pytest.raises(ValueError, match="不能为负"):
        PatternOptions(fly_blend_drop=-0.5)


# ---------- 独立门襟（门襟绘制.md §5） ----------
# 金标（直腰头，front_rise=25，默认 fly_sep_*）：
#   L = 10.75；裁片净宽 = W = 3.8（缝边/缩水留待裁切模块）；裁片高 = L + 2.0 = 12.75；
#   圆角半径 R = W − 0.8 = 3.0。
#   外缝顶点：沿**腰头线**（直腰头 = 上腰弧，弯腰头 = 下腰头线）自 O 量取
#   裁片净宽 3.8；顶边 = 腰头线子弧（弧长 = 3.8，与前片腰头线重合）。
#   缝份边自 O 沿前浪方向下行 12.75；裁片叠在前片上（伸入前片内侧）。

@pytest.fixture()
def ctx_sep():
    o = PatternOptions(delta=1.0, fly=True, fly_separate=True)
    return FlowRunner(M, o).run(FRONT_FLOW)


def test_fly_separate_skips_cut_on(ctx_sep):
    # 独立门襟：不画连裁门襟元素，改画独立裁片
    assert "front.fly_bottom_arc" not in ctx_sep.sheet
    assert "front.fly_outer_edge" not in ctx_sep.sheet
    assert "front.fly_sep_inner_edge" in ctx_sep.sheet


def test_fly_separate_enables_without_fly():
    # fly=False 但 fly_separate=True：独立门襟独立启用、照常绘制
    o = PatternOptions(delta=1.0, fly=False, fly_separate=True)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    assert "front.fly_sep_inner_edge" in ctx.sheet
    assert "front.fly_bottom_arc" not in ctx.sheet   # 连裁元素不出现


def test_fly_separate_outer_vertex_on_waistline(ctx_sep):
    # 外缝顶点在腰头线上（直腰头 = 上腰弧），沿腰头线自 O 量取裁片净宽 3.8
    w_arc = ctx_sep.curve("front.waistline_arc")
    t = ctx_sep.point("front.fly_sep_top_outer")
    tt = w_arc.t_at_length(w_arc.length() - 3.8)          # 弧长反查（不依赖 y 单调）
    assert w_arc.point_at(tt).distance_to(t) < 1e-6       # 在腰头线上
    # 顶边 = 腰头线子弧：起点 = 外缝顶点、终点 = O，弧长 = 裁片净宽
    top = ctx_sep.curve("front.fly_sep_top_edge")
    assert top.point_at(0).distance_to(t) < 1e-6        # 起点 = 外缝顶点
    assert top.point_at(1).distance_to(ctx_sep.point("front.fly_origin")) < 1e-6
    assert top.length() == pytest.approx(3.8, abs=1e-3)


def test_fly_separate_overlaid_on_front(ctx_sep):
    # 叠在前片上：外缝顶点沿腰头线向侧缝方向 = 伸入前片内侧（局部 X < 0）
    o_pt = ctx_sep.point("front.fly_origin")
    yd = ctx_sep.line("front.rise_slant").direction
    xd = yd.perpendicular()
    v = ctx_sep.point("front.fly_sep_top_outer") - o_pt
    assert v.dx * xd.dx + v.dy * xd.dy < 0.0


def test_fly_separate_outline(ctx_sep):
    # 轮廓：外缘/底边/缝份边为结构线；缝份边自 O 沿前浪方向下行裁片高 12.75
    o_pt = ctx_sep.point("front.fly_origin")
    for name in ("front.fly_sep_outer_edge", "front.fly_sep_bottom_edge",
                 "front.fly_sep_inner_edge"):
        assert ctx_sep.sheet.get(name).role == "struct"
    inner = ctx_sep.line("front.fly_sep_inner_edge")
    assert inner.b == o_pt                                # 缝份边上端 = O
    assert inner.length == pytest.approx(12.75)           # 裁片高 = L + 2.0
    yd = ctx_sep.line("front.rise_slant").direction
    d = inner.direction
    assert abs(d.dx * yd.dx + d.dy * yd.dy) == pytest.approx(1.0)   # ∥ 前浪


def test_fly_separate_corner_g1(ctx_sep):
    # 底角 90° 圆角：起弧切线 ∥ 前浪方向（+Y），G1 连续；两端接外缘/底边
    corner = ctx_sep.curve("front.fly_sep_corner")
    yd = ctx_sep.line("front.rise_slant").direction
    t0 = corner.tangent_at(0).normalized()
    assert t0.dx * yd.dx + t0.dy * yd.dy == pytest.approx(1.0)        # ∥ 前浪
    assert corner.point_at(0) == ctx_sep.line("front.fly_sep_outer_edge").b
    assert corner.point_at(1) == ctx_sep.line("front.fly_sep_bottom_edge").a


def test_fly_separate_origin_curved():
    # 弯腰头：原点 O 取下前中腰点 A'，外缝顶点落在**下腰头线**上
    o = PatternOptions(delta=1.0, fly=True, fly_separate=True,
                       waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    assert ctx.point("front.fly_origin") == ctx.point("front.lower_waist_center_point")
    w_arc = ctx.curve("front.lower_waistline_arc")
    tt = w_arc.t_at_length(w_arc.length() - 3.8)
    assert w_arc.point_at(tt).distance_to(
        ctx.point("front.fly_sep_top_outer")) < 1e-6


def test_fly_separate_options_validation():
    # fly_corner_inset 与连裁共用校验；fly_sep_extra 不能为负
    with pytest.raises(ValueError, match="圆角内收"):
        PatternOptions(fly_corner_inset=3.8)
    with pytest.raises(ValueError, match="不能为负数"):
        PatternOptions(fly_sep_extra=-1.0)
