"""前贴袋（表面外贴式 PATCH）步骤测试（前口袋绘制.md §四、§五）。

金标（H=96, Δ=1.0, outseam=102，直腰头扣腰头宽 4，腰线 y=98）：
  腰外缝顶点 B ≈ (4.3606, 98)（腰长 17.5 闭合推出）。
  袋口外上角 A = B + (+inset, −drop) = (4.3606+2, 98−10) = (6.3606, 88)
  （+X 朝内侧缝 = 裤片内部，"自侧缝向内"取 +）。
  矩形净形（w=14, h=15）：(6.3606, 88) → (20.3606, 88) →
    (20.3606, 73) → (6.3606, 73)。
  盾形底尖：(6.3606+7, 73−2.5) = (13.3606, 70.5)。
  缝边/缩水不在绘制阶段：只上版净样（先画后裁，裁切层统一加）。
"""

import pytest

from ylpattern.flows.front_flow import FRONT_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.params import Measurements, PatternOptions

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
O = PatternOptions(delta=1.0, front_patch=True)


@pytest.fixture()
def ctx():
    return FlowRunner(M, O).run(FRONT_FLOW)


def test_patch_anchor(ctx):
    # 袋口外上角 = 腰外缝顶点 + (+2, −10)（+X 朝裤片内部）
    b = ctx.point("front.waist_side_point")
    a = ctx.point("front.patch_net_pt1")
    assert a.x == pytest.approx(b.x + 2.0)
    assert a.y == pytest.approx(b.y - 10.0)
    # 贴袋整体在侧缝内侧（x 大于侧缝点）
    assert a.x > b.x


def test_patch_rectangle_net(ctx):
    a = ctx.point("front.patch_net_pt1")
    net = [ctx.point(f"front.patch_net_pt{i}") for i in range(1, 5)]
    # 手工金标：宽 14 向内、高 15 向下
    assert net[1].x == pytest.approx(a.x + 14.0)
    assert net[1].y == pytest.approx(a.y)
    assert net[2].x == pytest.approx(a.x + 14.0)
    assert net[2].y == pytest.approx(a.y - 15.0)
    assert net[3].x == pytest.approx(a.x)
    assert net[3].y == pytest.approx(a.y - 15.0)
    # 净样四段闭环，结构线
    for i in range(1, 5):
        seg = ctx.line(f"front.patch_net_seg{i}")
        assert ctx.sheet.get(f"front.patch_net_seg{i}").role == "struct"
    seg1 = ctx.line("front.patch_net_seg1")
    assert (seg1.a, seg1.b) == (net[0], net[1])


def test_patch_no_seam_allowance_at_draft_stage(ctx):
    # 先画后裁：绘制阶段只上版净样，毛样（缝份外拓）元素不存在
    assert "front.patch_cut_seg1" not in ctx.sheet


def test_patch_baker_shield():
    o = PatternOptions(delta=1.0, front_patch=True,
                       front_patch_shape="baker_shield",
                       front_patch_tip_depth=2.5)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    a = ctx.point("front.patch_net_pt1")
    # 五边形：底中尖点额外加深 2.5
    tip = ctx.point("front.patch_net_pt4")
    assert tip.x == pytest.approx(a.x + 14.0 / 2)
    assert tip.y == pytest.approx(a.y - 15.0 - 2.5)
    assert "front.patch_net_pt6" not in ctx.sheet  # 共 5 角
    # 净样五段
    assert "front.patch_net_seg5" in ctx.sheet
    assert "front.patch_net_seg6" not in ctx.sheet


def test_patch_angular():
    o = PatternOptions(delta=1.0, front_patch=True,
                       front_patch_shape="angular", front_patch_chamfer=2.0)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    a = ctx.point("front.patch_net_pt1")
    # 六边形：两底角各斜切 2.0
    pts = [ctx.point(f"front.patch_net_pt{i}") for i in range(1, 7)]
    assert pts[2].y == pytest.approx(a.y - 15.0 + 2.0)   # 内下角上收
    assert pts[3].x == pytest.approx(a.x + 14.0 - 2.0)   # 底边内收
    assert pts[4].x == pytest.approx(a.x + 2.0)
    assert pts[5].y == pytest.approx(a.y - 15.0 + 2.0)


def test_patch_skipped_by_default():
    ctx = FlowRunner(M, PatternOptions(delta=1.0)).run(FRONT_FLOW)
    assert "front.patch_net_seg1" not in ctx.sheet


def test_patch_bottom_width_angular():
    # 袋底宽独立于袋口宽：底边两侧对称内收 (14−10)/2 = 2
    o = PatternOptions(delta=1.0, front_patch=True,
                       front_patch_shape="angular",
                       front_patch_bottom_width=10.0,
                       front_patch_chamfer=2.0)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    a = ctx.point("front.patch_net_pt1")
    pts = [ctx.point(f"front.patch_net_pt{i}") for i in range(1, 7)]
    assert pts[2].x == pytest.approx(a.x + 14.0 - 2.0)   # 内下角左收 2
    assert pts[3].x == pytest.approx(a.x + 14.0 - 2.0 - 2.0)  # 再斜切 2
    assert pts[4].x == pytest.approx(a.x + 2.0 + 2.0)    # 外底角右收 2 再斜切
    assert pts[5].x == pytest.approx(a.x + 2.0)


def test_patch_rotation():
    # 绕袋口外上角顺时针旋转 90°：(w, 0) → (0, −w)，(0, −h) → (−h, 0)
    o = PatternOptions(delta=1.0, front_patch=True,
                       front_patch_rotate_deg=90.0)
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    a = ctx.point("front.patch_net_pt1")
    p2 = ctx.point("front.patch_net_pt2")
    p4 = ctx.point("front.patch_net_pt4")
    assert p2.x == pytest.approx(a.x)
    assert p2.y == pytest.approx(a.y - 14.0)
    assert p4.x == pytest.approx(a.x - 15.0)
    assert p4.y == pytest.approx(a.y)


def test_patch_custom_mode():
    # 全自定义：4 角点（袋身向下）+ 第 2 边弧线（弧高 2、弧顶 0.5），其余直线
    o = PatternOptions(delta=1.0, front_patch=True,
                       front_patch_shape="custom",
                       front_patch_custom_points=[(0, 0), (10, 0),
                                                  (10, -12), (0, -12)],
                       front_patch_custom_edges=[(0, 0.5), (2, 0.5),
                                                 (0, 0.5), (0, 0.5)])
    ctx = FlowRunner(M, o).run(FRONT_FLOW)
    a = ctx.point("front.patch_net_pt1")
    # 角点 = 锚点 + 相对坐标
    p3 = ctx.point("front.patch_net_pt3")
    assert p3.x == pytest.approx(a.x + 10.0)
    assert p3.y == pytest.approx(a.y - 12.0)
    # 直线边为 NamedLine，弧线边为 NamedCurve 且端点吻合
    assert ctx.line("front.patch_net_seg1").a == a
    arc = ctx.curve("front.patch_net_seg2")
    assert arc.p0 == ctx.point("front.patch_net_pt2")
    assert arc.p3 == p3
    # 弧高方向（左手法向）：右边界向下，左手法向朝 +x（外侧），弧中点外鼓
    assert arc.point_at(0.5).x > a.x + 10.0


def test_patch_custom_validation():
    with pytest.raises(ValueError, match="至少 3 个"):
        PatternOptions(front_patch_shape="custom",
                       front_patch_custom_points=[(0, 0), (1, 0)],
                       front_patch_custom_edges=[(0, 0.5), (0, 0.5)])
    with pytest.raises(ValueError, match="个数须等于角点数"):
        PatternOptions(front_patch_shape="custom",
                       front_patch_custom_points=[(0, 0), (1, 0), (0, 1)],
                       front_patch_custom_edges=[(0, 0.5)])
    with pytest.raises(ValueError, match="弧顶位置须在"):
        PatternOptions(front_patch_shape="custom",
                       front_patch_custom_points=[(0, 0), (1, 0), (0, 1)],
                       front_patch_custom_edges=[(0, 0.5), (2, 1.5), (0, 0.5)])


def test_patch_options_validation():
    with pytest.raises(ValueError, match="下移量/内移量"):
        PatternOptions(front_patch_top_drop=-1.0)
    with pytest.raises(ValueError, match="袋口宽/袋身高"):
        PatternOptions(front_patch_width=0.0)
    with pytest.raises(ValueError, match="贴袋净形只支持"):
        PatternOptions(front_patch_shape="circle")
    with pytest.raises(ValueError, match="袋底宽不能为负数"):
        PatternOptions(front_patch_bottom_width=-1.0)
    with pytest.raises(ValueError, match="旋转角"):
        PatternOptions(front_patch_rotate_deg=120.0)
    with pytest.raises(ValueError, match="底尖深度"):
        PatternOptions(front_patch_tip_depth=99.0)
    with pytest.raises(ValueError, match="斜切量两倍"):
        PatternOptions(front_patch_chamfer=8.0)
