"""后贴袋（表面外贴式 PATCH）步骤测试（后贴袋绘制.md §一~§三；打版流程.md「后贴袋绘制」）。

金标（M 同 test_back_steps / test_back_yoke_steps：H=96, Δ=1.0, outseam=102，
直腰头扣腰头宽 4，腰线 y=98；后浪闭合目标 33−4=29）：
  默认 back_yoke 开启（D_cb=4.0、D_side=3.0）-> 育克底线后浪端点 origin（yoke_cb_point）、
  侧缝端点 pn（yoke_side_point）已上版。后贴袋原点 O = origin（育克底线 ∩ 后浪线）；
  局部系 û = origin->pn（自后浪朝侧缝）、v̂ = û 下方法向（朝脚口）。
  定位点 P0 = O + inset_x·û + drop_y·v̂（默认 4.5 / 3.5），
  |P0−O| = √(4.5²+3.5²) = √32.5 ≈ 5.7009（û⊥v̂）。
  矩形净形（W=14, H=16, θ=0）：net[0]=P0、net[1]=P0+14·û、net[2]=P0+14·û+16·v̂、
  net[3]=P0+16·v̂；袋口 net[0]->net[1] ∥ 约克底线（origin->pn，默认平行约克底线≈后腰线）。
  旋转 θ=90°（顺时针）：(u,v)->(−v,u)，net[1] 落到 P0+14·v̂（正下方）、
  net[3] 落到 P0−16·û（朝后浪侧），边长不变（刚性旋转）。
"""

import math

import pytest

from ylpattern.flows.back_flow import FULL_FLOW
from ylpattern.flows.runner import FlowRunner
from ylpattern.params import Measurements, PatternOptions, WaistbandType

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
O = PatternOptions(delta=1.0, back_yoke=True, back_patch=True)


def _uv(ctx):
    """独立重建局部系：û 自后浪朝侧缝（沿约克底线）、v̂ 向下（入裤身）。"""
    origin = ctx.point("back.yoke_cb_point")
    pn = ctx.point("back.yoke_side_point")
    u_hat = (pn - origin).normalized()
    v_hat = u_hat.perpendicular()
    if v_hat.dy > 0:
        v_hat = v_hat.scale(-1)
    return origin, pn, u_hat, v_hat


def _cross(a, b):
    return a.dx * b.dy - a.dy * b.dx


def _dot(a, b):
    return a.dx * b.dx + a.dy * b.dy


@pytest.fixture()
def ctx():
    return FlowRunner(M, O).run(FULL_FLOW)


def test_back_patch_skipped_by_default():
    # 可选步骤：默认开关关闭，不上版任何后贴袋元素
    ctx = FlowRunner(M, PatternOptions(delta=1.0, back_yoke=True)).run(FULL_FLOW)
    assert "back.patch_net_seg1" not in ctx.sheet
    assert "back.patch_anchor" not in ctx.sheet


def test_back_patch_requires_yoke():
    # 依赖后机头：back_yoke 关闭时无育克底线原点，整步抛错
    o = PatternOptions(delta=1.0, back_patch=True)  # back_yoke 默认关闭
    with pytest.raises(ValueError, match="依赖后机头"):
        FlowRunner(M, o).run(FULL_FLOW)


def test_back_patch_anchor(ctx):
    origin, pn, u_hat, v_hat = _uv(ctx)
    anchor = ctx.point("back.patch_anchor")
    # P0 = O + inset_x·û + drop_y·v̂；û⊥v̂ -> |P0−O| = √(inset²+drop²)
    assert origin.distance_to(anchor) == pytest.approx(
        math.sqrt(O.back_patch_inset_x ** 2 + O.back_patch_drop_y ** 2))
    # 在原点下方（v̂ 朝脚口）、朝侧缝一侧（û 自后浪朝侧缝，后浪在高端 x）
    assert anchor.y < origin.y
    assert anchor.x < origin.x
    # 沿 û 分量 = inset_x、沿 v̂ 分量 = drop_y（独立投影校验）
    delta = anchor - origin
    assert _dot(delta, u_hat) == pytest.approx(O.back_patch_inset_x)
    assert _dot(delta, v_hat) == pytest.approx(O.back_patch_drop_y)


def test_back_patch_rectangle_net(ctx):
    origin, pn, u_hat, v_hat = _uv(ctx)
    p0 = ctx.point("back.patch_net_pt1")
    net = [ctx.point(f"back.patch_net_pt{i}") for i in range(1, 5)]
    w, h = O.back_patch_width, O.back_patch_height
    # 边长：上边 W、左边 H、对角 √(W²+H²)（θ=0 刚性矩形）
    assert net[0].distance_to(net[1]) == pytest.approx(w)
    assert net[0].distance_to(net[3]) == pytest.approx(h)
    assert net[0].distance_to(net[2]) == pytest.approx(math.hypot(w, h))
    # 袋口 net[0]->net[1] ∥ 约克底线 origin->pn（默认平行约克底线）
    assert _cross(net[1] - net[0], pn - origin) == pytest.approx(0.0, abs=1e-9)
    # 左边 net[0]->net[3] ⊥ 约克底线
    assert _dot(net[1] - net[0], pn - origin) > 0          # 同向
    assert _dot(net[3] - net[0], pn - origin) == pytest.approx(0.0, abs=1e-9)
    # 左边朝下（v̂ 向脚口）：net[3] 在 net[0] 下方
    assert net[3].y < net[0].y
    # 净样四段闭环，结构线
    for i in range(1, 5):
        assert ctx.sheet.get(f"back.patch_net_seg{i}").role == "struct"
    seg1 = ctx.line("back.patch_net_seg1")
    assert (seg1.a, seg1.b) == (net[0], net[1])


def test_back_patch_parallel_to_yoke(ctx):
    # 打版流程.md：默认平行后腰线 -- 袋口沿约克底线方向（育克与腰线近似平行）
    origin, pn, u_hat, v_hat = _uv(ctx)
    p1, p2 = ctx.point("back.patch_net_pt1"), ctx.point("back.patch_net_pt2")
    assert _cross(p2 - p1, pn - origin) == pytest.approx(0.0, abs=1e-9)


def test_back_patch_baker_shield():
    o = PatternOptions(delta=1.0, back_yoke=True, back_patch=True,
                       back_patch_shape="baker_shield",
                       back_patch_bottom_width=12.0,
                       back_patch_tip_depth=2.5)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    p0 = ctx.point("back.patch_net_pt1")
    # 五边形：底中尖点为 net[4]（局部 V3=(W/2, H+tip)），共 5 角
    assert "back.patch_net_pt6" not in ctx.sheet
    assert "back.patch_net_seg5" in ctx.sheet
    assert "back.patch_net_seg6" not in ctx.sheet
    origin, pn, u_hat, v_hat = _uv(ctx)
    bi = (o.back_patch_width - o.back_patch_bottom_width) / 2  # = 1
    # net[2] = V2=(W-bi, H)：沿 û 投影 = W-bi、沿 v̂ = H
    p2 = ctx.point("back.patch_net_pt3")  # V2 是第 3 个顶点
    assert _dot(p2 - p0, u_hat) == pytest.approx(o.back_patch_width - bi)
    assert _dot(p2 - p0, v_hat) == pytest.approx(o.back_patch_height)
    # 尖点 net[4] = V3=(W/2, H+tip)：最深处（v 最大）
    tip = ctx.point("back.patch_net_pt4")
    assert _dot(tip - p0, u_hat) == pytest.approx(o.back_patch_width / 2)
    assert _dot(tip - p0, v_hat) == pytest.approx(
        o.back_patch_height + o.back_patch_tip_depth)
    assert tip.y < p0.y - o.back_patch_height   # 尖点低于袋底


def test_back_patch_angular():
    o = PatternOptions(delta=1.0, back_yoke=True, back_patch=True,
                       back_patch_shape="angular", back_patch_chamfer=2.0)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    p0 = ctx.point("back.patch_net_pt1")
    # 六边形：共 6 角
    assert "back.patch_net_pt7" not in ctx.sheet
    assert "back.patch_net_seg6" in ctx.sheet
    origin, pn, u_hat, v_hat = _uv(ctx)
    w, h, c = o.back_patch_width, o.back_patch_height, o.back_patch_chamfer
    # V1=(W,0)->V2=(W,H-c)：右边长 = H-c
    p1 = ctx.point("back.patch_net_pt2")
    p2 = ctx.point("back.patch_net_pt3")
    assert p1.distance_to(p2) == pytest.approx(h - c)
    # V2->V3 斜切段：长 = c·√2
    p3 = ctx.point("back.patch_net_pt4")
    assert p2.distance_to(p3) == pytest.approx(c * math.sqrt(2))


def test_back_patch_rotation():
    # 绕 P0 顺时针 90°：(u,v)->(−v,u)，net[1] 落正下方、net[3] 朝后浪侧，边长不变
    o = PatternOptions(delta=1.0, back_yoke=True, back_patch=True,
                       back_patch_rotate_deg=90.0)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    origin, pn, u_hat, v_hat = _uv(ctx)
    p0 = ctx.point("back.patch_net_pt1")
    p1 = ctx.point("back.patch_net_pt2")  # 局部 V1=(W,0) -> (0,W)
    p3 = ctx.point("back.patch_net_pt4")  # 局部 V3=(0,H) -> (−H,0)
    w, h = o.back_patch_width, o.back_patch_height
    # 边长保持（刚性旋转）
    assert p0.distance_to(p1) == pytest.approx(w)
    assert p0.distance_to(p3) == pytest.approx(h)
    # net[1] = P0 + W·v̂（正下方，⊥ 约克底线）
    assert _dot(p1 - p0, pn - origin) == pytest.approx(0.0, abs=1e-9)
    assert p1.y < p0.y
    # net[3] = P0 − H·û（朝后浪侧，∥ 约克底线反向）
    assert _cross(p3 - p0, pn - origin) == pytest.approx(0.0, abs=1e-9)
    assert _dot(p3 - p0, pn - origin) < 0


def test_back_patch_custom_mode():
    # 全自定义：4 角点 + 第 2 边弧线（弧高 2、弧顶 0.5），其余直线
    o = PatternOptions(delta=1.0, back_yoke=True, back_patch=True,
                       back_patch_shape="custom",
                       back_patch_custom_points=[(0, 0), (14, 0),
                                                  (14, 16), (0, 16)],
                       back_patch_custom_edges=[(0, 0.5), (2, 0.5),
                                                 (0, 0.5), (0, 0.5)])
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    origin, pn, u_hat, v_hat = _uv(ctx)
    p0 = ctx.point("back.patch_net_pt1")
    # net[2] = V2=(W,H)（第 3 个顶点）：沿 û = W、沿 v̂ = H
    p2 = ctx.point("back.patch_net_pt3")
    assert _dot(p2 - p0, u_hat) == pytest.approx(14.0)
    assert _dot(p2 - p0, v_hat) == pytest.approx(16.0)
    # 直线边 NamedLine、弧线边 NamedCurve 且端点吻合
    assert ctx.line("back.patch_net_seg1").a == p0
    arc = ctx.curve("back.patch_net_seg2")
    p1 = ctx.point("back.patch_net_pt2")
    assert arc.p0 == p1 and arc.p3 == p2


def test_back_patch_curved_waistband():
    # 弯腰头：机头自下腰头量取，后贴袋原点仍取机头后浪端点，定位正常
    o = PatternOptions(delta=1.0, back_yoke=True, back_patch=True,
                       waistband_type=WaistbandType.CURVED)
    ctx = FlowRunner(M, o).run(FULL_FLOW)
    origin = ctx.point("back.yoke_cb_point")
    anchor = ctx.point("back.patch_anchor")
    assert "back.patch_net_seg1" in ctx.sheet
    assert "back.patch_net_seg4" in ctx.sheet
    assert anchor.y < origin.y                   # 定位点在原点下方
    # 矩形四角仍满足边长
    p0 = ctx.point("back.patch_net_pt1")
    assert p0.distance_to(ctx.point("back.patch_net_pt2")) == pytest.approx(
        o.back_patch_width)


def test_back_patch_no_seam_allowance_at_draft_stage(ctx):
    # 先画后裁：绘制阶段只上版净样，毛样（缝份外拓）元素不存在
    assert "back.patch_cut_seg1" not in ctx.sheet


def test_back_patch_options_validation():
    with pytest.raises(ValueError, match="距后浪线/距约克底线"):
        PatternOptions(back_patch=True, back_patch_inset_x=-1.0)
    with pytest.raises(ValueError, match="袋口宽/袋身高"):
        PatternOptions(back_patch=True, back_patch_width=0.0)
    with pytest.raises(ValueError, match="后贴袋净形只支持"):
        PatternOptions(back_patch=True, back_patch_shape="circle")
    with pytest.raises(ValueError, match="袋底宽不能为负数"):
        PatternOptions(back_patch=True, back_patch_bottom_width=-1.0)
    with pytest.raises(ValueError, match="旋转角"):
        PatternOptions(back_patch=True, back_patch_rotate_deg=120.0)
    with pytest.raises(ValueError, match="底尖深度"):
        PatternOptions(back_patch=True, back_patch_tip_depth=99.0)
    with pytest.raises(ValueError, match="斜切量两倍"):
        PatternOptions(back_patch=True, back_patch_shape="angular",
                       back_patch_chamfer=8.0)
    with pytest.raises(ValueError, match="至少 3 个"):
        PatternOptions(back_patch=True, back_patch_shape="custom",
                       back_patch_custom_points=[(0, 0), (1, 0)],
                       back_patch_custom_edges=[(0, 0.5), (0, 0.5)])
    with pytest.raises(ValueError, match="个数须等于角点数"):
        PatternOptions(back_patch=True, back_patch_shape="custom",
                       back_patch_custom_points=[(0, 0), (1, 0), (0, 1)],
                       back_patch_custom_edges=[(0, 0.5)])
    with pytest.raises(ValueError, match="弧顶位置须在"):
        PatternOptions(back_patch=True, back_patch_shape="custom",
                       back_patch_custom_points=[(0, 0), (1, 0), (0, 1)],
                       back_patch_custom_edges=[(0, 0.5), (2, 1.5), (0, 0.5)])


def test_back_patch_custom_edges_normalized():
    # 边形态归一化为元组（与前贴袋同口径）
    o = PatternOptions(delta=1.0, back_yoke=True, back_patch=True,
                       back_patch_shape="custom",
                       back_patch_custom_points=[(0, 0), (1, 0), (0, 1)],
                       back_patch_custom_edges=[(0, 0.5), (2.0, 0.5), (0, 0.5)])
    assert o.back_patch_custom_points == ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))
    assert o.back_patch_custom_edges == ((0.0, 0.5), (2.0, 0.5), (0.0, 0.5))
