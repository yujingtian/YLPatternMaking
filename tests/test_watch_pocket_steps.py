"""前小表袋步骤测试（小表袋绘制.md §2~§4；打版流程.md「小表袋绘制」）。

金标（H=96, Δ=1.0, outseam=102，直腰头扣腰头宽 4，腰线 y=98）：
  以前口袋侧缝腰点 B 为基准，参考点（袋口外上角）= B + (+3.5, −4.0)
  （+X 朝内侧缝 = 裤片内部，"离口袋侧边"水平向内取 +；"离口袋顶部"垂直向下取 −）。
  双模式支持：
    1. custom 模式：梯形/多边形自由锚点 + 逐边 line/arc/bezier 形态
       （全局默认模式为 facing_intersect，本文件 custom 分支均显式指定）；
    2. facing_intersect 模式：袋口定宽，左右侧边向下延伸与袋贴内边 front.pocket_facing_inner 相交，
       底边取袋贴内边子段（NamedCurve）闭合。
  依赖说明：
    - 均依赖前口袋主切口（front_pocket）；
    - facing_intersect 模式额外强依赖袋贴绘制（front_pocket_facing）。
"""

import pytest

from ylpattern.draft import curves
from ylpattern.flows.front_flow import FRONT_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.params import Measurements, PatternOptions, WaistbandType

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
# 分支 A（custom）测试夹具：全局默认 watch_pocket_mode 已是 facing_intersect
# （强依赖袋贴），custom 分支须显式指定
O = PatternOptions(delta=1.0, front_pocket=True, watch_pocket=True,
                   watch_pocket_mode="custom")


@pytest.fixture()
def ctx():
    return FlowRunner(M, O).run(FRONT_FLOW)


# ==============================================================================
# 分支 A：custom 模式（独立全自定义多锚点模式）测试
# ==============================================================================

def test_watch_pocket_anchor(ctx):
    # 参考点（pt1，默认首锚点 dx=dy=0）= B + (+3.5, −4.0)
    b = ctx.point("front.waist_side_point")
    a = ctx.point("front.watch_pocket_pt1")
    assert a.x == pytest.approx(b.x + 3.5)
    assert a.y == pytest.approx(b.y - 4.0)
    assert a.x > b.x                       # 在侧缝内侧


def test_watch_pocket_default_net(ctx):
    a = ctx.point("front.watch_pocket_pt1")
    p2 = ctx.point("front.watch_pocket_pt2")
    p3 = ctx.point("front.watch_pocket_pt3")
    p4 = ctx.point("front.watch_pocket_pt4")
    assert p2.x == pytest.approx(a.x + 8.0)
    assert p2.y == pytest.approx(a.y)
    assert p3.x == pytest.approx(a.x + 7.6)
    assert p3.y == pytest.approx(a.y - 7.5)
    assert p4.x == pytest.approx(a.x + 0.4)
    assert p4.y == pytest.approx(a.y - 7.5)
    # 4 段闭合，结构线
    for i in range(1, 5):
        ctx.line(f"front.watch_pocket_seg{i}")
        assert ctx.sheet.get(f"front.watch_pocket_seg{i}").role == "struct"
    # 闭合边 seg4 = pt4 -> pt1
    assert (ctx.line("front.watch_pocket_seg4").a,
            ctx.line("front.watch_pocket_seg4").b) == (p4, a)


def test_watch_pocket_rotation():
    # 绕参考点顺时针 90°：(8,0) -> (0,−8)
    o = PatternOptions(delta=1.0, front_pocket=True, watch_pocket=True,
                       watch_pocket_mode="custom",
                       watch_pocket_rotate_deg=90.0)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    a = ctx.point("front.watch_pocket_pt1")
    p2 = ctx.point("front.watch_pocket_pt2")
    assert p2.x == pytest.approx(a.x)
    assert p2.y == pytest.approx(a.y - 8.0)


def test_watch_pocket_custom_edges():
    # 4 锚点 + line/arc/bezier/line 四段
    o = PatternOptions(delta=1.0, front_pocket=True, watch_pocket=True,
        watch_pocket_mode="custom",
        watch_pocket_points=[(0, 0), (10, 0), (10, 10), (0, 10)],
        watch_pocket_edges=[("line",), ("arc", 2.0, 0.5),
                            ("bezier", 30.0, 0.5, -30.0, 0.5), ("line",)])
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    a = ctx.point("front.watch_pocket_pt1")
    p2 = ctx.point("front.watch_pocket_pt2")
    p3 = ctx.point("front.watch_pocket_pt3")
    p4 = ctx.point("front.watch_pocket_pt4")
    # seg1 直线（NamedLine）
    assert ctx.line("front.watch_pocket_seg1").a == a
    # seg2 arc（NamedCurve，端点吻合）
    arc = ctx.curve("front.watch_pocket_seg2")
    assert arc.p0 == p2
    assert arc.p3 == p3
    # seg3 bezier（NamedCurve，端点 + 控制点构造校验）
    bz = ctx.curve("front.watch_pocket_seg3")
    assert bz.p0 == p3
    assert bz.p3 == p4
    chord = p4 - p3
    l0 = chord.length
    u = chord.normalized()
    exp_c1 = p3 + u.rotate(30.0).scale(0.5 * l0)
    exp_c2 = p4 + u.rotate(-30.0).scale(0.5 * l0)
    assert bz.p1.x == pytest.approx(exp_c1.x, abs=1e-9)
    assert bz.p1.y == pytest.approx(exp_c1.y, abs=1e-9)
    assert bz.p2.x == pytest.approx(exp_c2.x, abs=1e-9)
    assert bz.p2.y == pytest.approx(exp_c2.y, abs=1e-9)


# ==============================================================================
# 分支 B：facing_intersect 模式（袋贴相交延伸模式）测试
# ==============================================================================

def test_watch_pocket_facing_intersect_construction():
    # 开启袋贴 + 相交模式
    o = PatternOptions(
        delta=1.0,
        front_pocket=True,
        front_pocket_facing=True,
        front_pocket_facing_mode="tangent",
        watch_pocket=True,
        watch_pocket_mode="facing_intersect",
        watch_pocket_width=7.5,
        watch_pocket_offset_from_top=3.0,
        watch_pocket_offset_from_side=2.5,
        watch_pocket_taper=0.3,
        watch_pocket_rotate_deg=5.0,
    )
    ctx = FlowRunner(M, o).run(FRONT_FLOW)

    # 1. 验证 4 个特征点存在
    pt1 = ctx.point("front.watch_pocket_pt1")  # 外上角
    pt2 = ctx.point("front.watch_pocket_pt2")  # 内上角
    pt3 = ctx.point("front.watch_pocket_pt3")  # 内下交点
    pt4 = ctx.point("front.watch_pocket_pt4")  # 外下交点

    # 袋口宽约束（pt1 -> pt2 距离 = width）
    assert pt1.distance_to(pt2) == pytest.approx(7.5, abs=1e-3)

    # 2. 验证 4 条边拓扑
    seg1 = ctx.line("front.watch_pocket_seg1")   # 顶边（直线）
    seg2 = ctx.line("front.watch_pocket_seg2")   # 内侧边（直线）
    seg3 = ctx.curve("front.watch_pocket_seg3")  # 底边（顺接袋贴弧线）
    seg4 = ctx.line("front.watch_pocket_seg4")   # 外侧边（直线）

    assert (seg1.a, seg1.b) == (pt1, pt2)
    assert (seg2.a, seg2.b) == (pt2, pt3)
    assert (seg4.a, seg4.b) == (pt4, pt1)

    # 3. 验证底边弧线（seg3）两端与交点吻合
    assert (seg3.p0.distance_to(pt3) < 1e-6 and seg3.p3.distance_to(pt4) < 1e-6) or \
           (seg3.p0.distance_to(pt4) < 1e-6 and seg3.p3.distance_to(pt3) < 1e-6)

    # 4. 验证底边交点确实落在袋贴内边弧线上
    # 口径：法足投影距离（交点由 ray_intersect_bezier 在曲线上二分求得，
    # 投影应≈0）；旧 sample(256) 最近采样点口径受采样间距影响——交点落在
    # 两采样点之间时 0.006 级误报，并非几何误差
    facing_curve = ctx.curve("front.pocket_facing_inner")
    for pt in (pt3, pt4):
        foot = curves.foot_on_bezier(facing_curve, pt)
        assert pt.distance_to(foot) == pytest.approx(0.0, abs=1e-6)


def test_watch_pocket_facing_intersect_requires_facing():
    # 处于 facing_intersect 模式但未开启袋贴：必须报错
    o = PatternOptions(
        delta=1.0,
        front_pocket=True,
        front_pocket_facing=False,  # 未开袋贴
        watch_pocket=True,
        watch_pocket_mode="facing_intersect"
    )
    with pytest.raises(ValueError, match="袋贴相交模式要求先开启袋贴绘制"):
        FlowRunner(M, o).run(FRONT_FLOW)


# ==============================================================================
# 通用依赖、边界与校验测试
# ==============================================================================

def test_watch_pocket_depends_on_front_pocket():
    # 未开 front_pocket：报错
    o = PatternOptions(delta=1.0, watch_pocket=True)
    with pytest.raises(ValueError, match="依赖前口袋主切口"):
        FlowRunner(M, o).run(FRONT_FLOW)


def test_watch_pocket_skipped_by_default():
    ctx = FlowRunner(M, PatternOptions(delta=1.0, front_pocket=True)).run(FRONT_FLOW)
    assert "front.watch_pocket_seg1" not in ctx.sheet


def test_watch_pocket_no_seam_allowance(ctx):
    # 先画后裁：绘制阶段无毛样
    assert "front.watch_pocket_cut_seg1" not in ctx.sheet


def test_watch_pocket_curved_waistband():
    # 弯腰头：基准 = 下侧缝腰点 B′（custom 分支，模式须显式指定）
    o = PatternOptions(delta=1.0, front_pocket=True, watch_pocket=True,
                       watch_pocket_mode="custom",
                       waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    b_sub = ctx.point("front.lower_waist_side_point")
    a = ctx.point("front.watch_pocket_pt1")
    assert a.x == pytest.approx(b_sub.x + 3.5)
    assert a.y == pytest.approx(b_sub.y - 4.0)


def test_watch_pocket_options_validation():
    with pytest.raises(ValueError, match="不能为负数"):
        PatternOptions(watch_pocket=True, watch_pocket_offset_from_top=-1.0)
    with pytest.raises(ValueError, match="旋转角"):
        PatternOptions(watch_pocket=True, watch_pocket_rotate_deg=120.0)
    with pytest.raises(ValueError, match="小表袋模式只支持"):
        PatternOptions(watch_pocket=True, watch_pocket_mode="invalid_mode")
    with pytest.raises(ValueError, match="小表袋袋口宽必须为正数"):
        PatternOptions(watch_pocket=True, watch_pocket_width=0.0)
    with pytest.raises(ValueError, match="至少 3 个"):
        PatternOptions(watch_pocket=True, watch_pocket_points=[(0, 0), (1, 0)])
    with pytest.raises(ValueError, match="个数须等于锚点数"):
        PatternOptions(watch_pocket=True, watch_pocket_points=[(0, 0), (1, 0), (0, 1)],
                       watch_pocket_edges=[("line",), ("line",)])
    with pytest.raises(ValueError, match="边形态只支持"):
        PatternOptions(watch_pocket=True, watch_pocket_points=[(0, 0), (1, 0), (0, 1)],
                       watch_pocket_edges=[("line",), ("zigzag",), ("line",)])
    with pytest.raises(ValueError, match="arc 弧顶分位"):
        PatternOptions(watch_pocket=True, watch_pocket_points=[(0, 0), (1, 0), (0, 1)],
                       watch_pocket_edges=[("line",), ("arc", 2.0, 1.5), ("line",)])
    with pytest.raises(ValueError, match="bezier 手柄弦长比"):
        PatternOptions(watch_pocket=True, watch_pocket_points=[(0, 0), (1, 0), (0, 1)],
                       watch_pocket_edges=[("line",), ("bezier", 30, 0.5, -30, 1.5),
                                           ("line",)])