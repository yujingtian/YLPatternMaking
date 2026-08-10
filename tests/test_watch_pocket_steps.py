"""前小表袋步骤测试（小表袋绘制.md §2~§4；打版流程.md「小表袋绘制」）。

金标（H=96, Δ=1.0, outseam=102，直腰头扣腰头宽 4，腰线 y=98）：
  以前口袋侧缝腰点 B 为基准，参考点（袋口外上角）= B + (+3.5, −4.0)
  （+X 朝内侧缝 = 裤片内部，"离口袋侧边"水平向内取 +；"离口袋顶部"垂直向下取 −）。
  默认梯形锚点（袋口宽 8、底宽 7.2、高 7.5，taper 0.4）：
    pt1 = 参考点、pt2 = 参考点+(8,0)、pt3 = 参考点+(7.6,−7.5)、pt4 = 参考点+(0.4,−7.5)。
  依赖前口袋挖削嵌入式（front_pocket）；缝边不在绘制阶段（先画后裁）。
"""

import pytest

from ylpattern.flows.front_flow import FRONT_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.params import Measurements, PatternOptions, WaistbandType

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
O = PatternOptions(delta=1.0, front_pocket=True, watch_pocket=True)


@pytest.fixture()
def ctx():
    return FlowRunner(M, O).run(FRONT_FLOW)


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
                       watch_pocket_rotate_deg=90.0)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    a = ctx.point("front.watch_pocket_pt1")
    p2 = ctx.point("front.watch_pocket_pt2")
    assert p2.x == pytest.approx(a.x)
    assert p2.y == pytest.approx(a.y - 8.0)


def test_watch_pocket_custom_edges():
    # 4 锚点 + line/arc/bezier/line 四段（打版流程.md：每段弧线/贝塞尔/直线可控制）
    o = PatternOptions(delta=1.0, front_pocket=True, watch_pocket=True,
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
    # seg3 bezier（NamedCurve，端点 + 控制点构造校验：C1=A+κ1·L0·û(α)）
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


def test_watch_pocket_depends_on_front_pocket():
    # 未开 front_pocket：报错（打版流程.md：当前口袋是挖削嵌入式时才绘制）
    o = PatternOptions(delta=1.0, watch_pocket=True)
    with pytest.raises(ValueError, match="依赖前口袋主切口"):
        FlowRunner(M, o).run(FRONT_FLOW)


def test_watch_pocket_skipped_by_default():
    ctx = FlowRunner(M, PatternOptions(delta=1.0, front_pocket=True)).run(FRONT_FLOW)
    assert "front.watch_pocket_seg1" not in ctx.sheet


def test_watch_pocket_no_seam_allowance(ctx):
    # 先画后裁：绘制阶段只上版净样，毛样（缝份外拓）元素不存在
    assert "front.watch_pocket_cut_seg1" not in ctx.sheet


def test_watch_pocket_curved_waistband():
    # 弯腰头：基准 = 下侧缝腰点 B′（与 INSET/袋布同一 effective_waist 基准）
    o = PatternOptions(delta=1.0, front_pocket=True, watch_pocket=True,
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
