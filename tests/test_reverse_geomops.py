"""reverse.geomops 金标测试（纯几何，mm 域）。

头注手工演算：
- 矩形环 R = (0,0),(100,0),(100,50),(0,50)：周长 300、面积 5000。
  - 水平线 y=25（a=(-10,25), b=(110,25)）穿环交点 x=0/100 -> 弦宽 100；
  - 斜线 y=x（a=(-10,-10), b=(110,110)）交 (0,0)/(50,50) -> 弦宽 50√2
    ≈ 70.7107；
  - chain_above(25)：入口 (100,25) -> (100,50) -> (0,50) -> (0,25)，
    链长 25+100+25 = 150；
  - chain_between(0,2) = (0,0)->(100,0)->(100,50) 长 150；环绕
    chain_between(2,0) 长 150；两段合计 = 周长 300。
  - strip_width：100x40 条带（(0,0),(100,0),(100,40),(0,40)）半周 140、
    面积 4000，W^2-140W+4000=0 -> W=(140-60)/2 = 40。
- 五边形 P = (0,0),(100,0),(100,50),(50,80),(0,50)：chain_above(25) 的
  上链 = (100,25)->(100,50)->(50,80)->(0,50)->(0,25)，链长 = 25+
  2*sqrt(50^2+30^2)+25 = 50+2*58.3095 ≈ 166.619；y 极值点 = (50,80)。
- 缝份：净样 (10,5)-(100,50) 在毛样 (0,0)-(110,60) 内，各顶点最小距
  [5,5,10,10]（下边距 5、上边距 10）。
- 半圆环带（外 R=100、内 r=60、180 度、每 5 度离散）：中线长 80π、
  面积 = W*80π，精确带宽 40（同心圆弧带闭式解精确成立，离散弦近似
  收敛，容差 0.05）。
- 刚体平移：A=[(0,0),(10,0),(10,10)] 整体平移 (5,7) -> RMS 0；末点
  再偏 1mm（dst 末点 x+1）-> 质心平移偏 (1/3,0)，逐点残差
  (1/3,1/3,2/3) -> RMS = sqrt(2)/3 ≈ 0.4714。
- 顶点漂移：矩形 4 顶点 vs 同矩形每边插中点 8 顶点，等弧长重采样后
  对齐点距 ≈ 0（<0.5）；与不同尺寸矩形 (0,0)-(120,50) 差距大（>10）。
- 角点：五边形前 5 点作开链，i=1 (100,0) 转角 +90、i=2 (100,50) 转角
  59.04（atan2(30,-50)=149.04 与 90 之差）、i=3 (50,80) 转角 +61.92
  （-298.08 环绕 +360）；阈值 65° 只剩 (100,0)，阈值 50° 三个全中。
- 梯形带（腰头形态，下长上短）：底 (0,0)-(760,0)、顶 (740,40)-(20,40)，
  斜端陡段（|dx|=10<|dy|=20）：两条长边 760 / 720；环绕起点平移后
  合并结果不变。
- 机头形态（顶弧下凹 + 斜两端）：顶边 4 段各 hypot(25,2)=25.0799
  合计 100.3197、底边 100；ymax 首达顶点 (100,50) 在顶游程首。
- 开链重采样：链 (0,0)-(30,0)-(30,40)（长 70）重采样 8 点，步距 10，
  各点 (0/10/20/30,0) + (30, 10..40)。
- 全等：直线链平移 RMS 0；镜像摆放（reverse 后平移）同样 RMS 0；
  折线中点抬高 5mm 的异形 RMS > 1。
"""

from __future__ import annotations

import math

import pytest

from ylpattern.geometry import Point, Vector
from ylpattern.reverse.geomops import (arc_pair, chain_above, chain_between,
                                       chain_between_shorter,
                                       chain_congruence_rms, chain_length_mm,
                                       chord_profile, chord_span_mm,
                                       corner_turns,
                                       extreme_point, line_ring_intersections,
                                       nearest_vertex, point_ring_nearest,
                                       point_segment_distance, resample_chain,
                                       rigid_fit_offset, ring_gap_best,
                                       shallow_run_at_extreme, slope_between,
                                       strip_long_edges, strip_width_mm,
                                       vertex_gaps)
from ylpattern.reverse.model import Ring

R = Ring((Point(0, 0), Point(100, 0), Point(100, 50), Point(0, 50)))
P5 = Ring((Point(0, 0), Point(100, 0), Point(100, 50), Point(50, 80),
           Point(0, 50)))


# ---- 点-边界距离 ----

def test_point_segment_distance():
    assert point_segment_distance(Point(5, 7), Point(0, 0),
                                  Point(10, 0)) == pytest.approx(7.0)
    assert point_segment_distance(Point(15, 0), Point(0, 0),
                                  Point(10, 0)) == pytest.approx(5.0)   # 钳到端点
    assert point_segment_distance(Point(-3, 4), Point(0, 0),
                                  Point(10, 0)) == pytest.approx(5.0)
    assert point_segment_distance(Point(5, 0), Point(0, 0),
                                  Point(10, 0)) == pytest.approx(0.0)


def test_vertex_gaps_and_nearest():
    gross = Ring((Point(0, 0), Point(110, 0), Point(110, 60), Point(0, 60)))
    net = Ring((Point(10, 5), Point(100, 5), Point(100, 50), Point(10, 50)))
    assert vertex_gaps(gross, net) == pytest.approx([5.0, 5.0, 10.0, 10.0])
    assert nearest_vertex(net, Point(99, 6)) == 1


# ---- 导线弦宽 ----

def test_line_ring_intersections_sorted_along_direction():
    pts = line_ring_intersections(R, Point(50, -10), Point(50, 60))
    assert [(p.x, p.y) for p in pts] == pytest.approx([(50.0, 0.0),
                                                       (50.0, 50.0)])


def test_chord_span_horizontal_and_tilted():
    assert chord_span_mm(R, Point(-10, 25), Point(110, 25)) == \
        pytest.approx(100.0)
    assert chord_span_mm(R, Point(-10, -10), Point(110, 110)) == \
        pytest.approx(50.0 * math.sqrt(2.0))
    assert chord_span_mm(R, Point(-10, 80), Point(110, 80)) is None  # 没切到


# ---- 链提取 ----

def test_chain_above_rect_and_pentagon():
    chain = chain_above(R, 25.0)
    assert chain_length_mm(chain) == pytest.approx(150.0)
    assert chain_above(R, 60.0) == []                        # 全在下方
    pent = chain_above(P5, 25.0)
    expect = 50.0 + 2.0 * math.hypot(50.0, 30.0)
    assert chain_length_mm(pent) == pytest.approx(expect)    # ≈ 166.619


def test_chain_between_and_arc_pair():
    assert chain_length_mm(chain_between(R, 0, 2)) == pytest.approx(150.0)
    assert chain_length_mm(chain_between(R, 2, 0)) == pytest.approx(150.0)
    fwd, bwd = arc_pair(R, 0, 2)
    assert chain_length_mm(fwd) + chain_length_mm(bwd) == \
        pytest.approx(R.perimeter())                         # 两段合周长 300
    # 严格 > 口径：切割线恰过顶点（无严格上方顶点/交点）返回空
    assert chain_above(R, 50.0) == []


# ---- 条带带宽 ----

def test_strip_width_rect_and_half_annulus():
    rect = Ring((Point(0, 0), Point(100, 0), Point(100, 40), Point(0, 40)))
    assert strip_width_mm(rect) == pytest.approx(40.0)
    # 半圆环带：外 R=100、内 r=60、每 5 度离散（同心弧带精确解 W=40）
    outer, inner = [], []
    for k in range(37):                       # 0..180 度
        a = math.radians(5.0 * k)
        outer.append(Point(100.0 * math.cos(a), 100.0 * math.sin(a)))
        inner.append(Point(60.0 * math.cos(a), 60.0 * math.sin(a)))
    band = Ring(tuple(outer + inner[::-1]))
    assert strip_width_mm(band) == pytest.approx(40.0, abs=0.05)


# ---- 极值 / 刚体拟合 / 斜率 ----

def test_extreme_point():
    assert extreme_point(P5, "y", "max") == Point(50, 80)
    assert extreme_point(P5, "x", "min") == Point(0, 0)
    with pytest.raises(ValueError):
        extreme_point(P5, "z", "max")


def test_rigid_fit_offset():
    a = [Point(0, 0), Point(10, 0), Point(10, 10)]
    b = [Point(5, 7), Point(15, 7), Point(15, 17)]
    off, rms = rigid_fit_offset(a, b)
    assert (off.dx, off.dy) == pytest.approx((5.0, 7.0))
    assert rms == pytest.approx(0.0, abs=1e-9)
    c = [Point(5, 7), Point(15, 7), Point(16, 17)]           # 末点偏 1mm
    _, rms2 = rigid_fit_offset(a, c)
    assert rms2 == pytest.approx(math.sqrt(2.0) / 3.0)        # ≈ 0.4714
    with pytest.raises(ValueError):
        rigid_fit_offset(a, b[:2])


def test_slope_between():
    assert slope_between(Point(0, 0), Point(10, 20)) == pytest.approx(0.5)
    assert math.isinf(slope_between(Point(0, 0), Point(10, 0)))


# ---- 顶点漂移下的重采样对应 ----

def test_ring_gap_best_under_vertex_drift():
    dense = Ring((Point(0, 0), Point(50, 0), Point(100, 0), Point(100, 25),
                  Point(100, 50), Point(50, 50), Point(0, 50), Point(0, 25)))
    assert ring_gap_best(R, dense, n=64) < 0.5                # 同形 ≈ 0
    other = Ring((Point(0, 0), Point(120, 0), Point(120, 50), Point(0, 50)))
    assert ring_gap_best(R, other, n=64) > 10.0               # 尺寸不同


# ---- 角点 / 条带分解 / 开链重采样 ----

def test_corner_turns_thresholds():
    chain = list(P5.pts)                    # 五边形作开链（端点不计角）
    turns65 = corner_turns(chain, 65.0)
    assert [(i, da) for i, _, da in turns65] == [(1, pytest.approx(90.0))]
    turns50 = corner_turns(chain, 50.0)
    assert [i for i, _, _ in turns50] == [1, 2, 3]
    assert [da for _, _, da in turns50] == pytest.approx(
        [90.0, 59.04, 61.92], abs=0.01)


def test_strip_long_edges_trapezoid_band():
    band = Ring((Point(0, 0), Point(380, 0), Point(760, 0), Point(750, 20),
                 Point(740, 40), Point(700, 40), Point(20, 40), Point(10, 20)))
    e1, e2 = strip_long_edges(band)
    lengths = sorted((chain_length_mm(e1), chain_length_mm(e2)), reverse=True)
    assert lengths == pytest.approx([760.0, 720.0])
    # 环绕起点平移（首尾缓段跨缝合并）：同形同长边
    rotated = Ring(tuple(list(band.pts)[3:] + list(band.pts)[:3]))
    f1, f2 = strip_long_edges(rotated)
    assert sorted((chain_length_mm(f1), chain_length_mm(f2)), reverse=True) \
        == pytest.approx([760.0, 720.0])
    with pytest.raises(ValueError):        # 无两条长边（45° 菱形整环一游程）
        strip_long_edges(Ring((Point(50, 0), Point(100, 50), Point(50, 100),
                              Point(0, 50))))


def test_chain_between_shorter():
    assert chain_length_mm(chain_between_shorter(R, 0, 1)) == \
        pytest.approx(100.0)               # 前向 100 vs 后向 200


def test_shallow_run_at_extreme_yoke_shape():
    yoke = Ring((Point(0, 0), Point(100, 0), Point(104, 25), Point(100, 50),
                 Point(75, 48), Point(50, 46), Point(25, 48), Point(0, 50),
                 Point(-4, 25)))
    top = shallow_run_at_extreme(yoke, "top")
    assert chain_length_mm(top) == pytest.approx(4.0 * math.hypot(25.0, 2.0))
    assert top[0] == Point(100, 50) and top[-1] == Point(0, 50)
    bottom = shallow_run_at_extreme(yoke, "bottom")
    assert chain_length_mm(bottom) == pytest.approx(100.0)
    with pytest.raises(ValueError):
        shallow_run_at_extreme(yoke, "left")


def test_resample_chain_open_polyline():
    chain = [Point(0, 0), Point(30, 0), Point(30, 40)]        # 长 70
    pts = resample_chain(chain, 8)                             # 步距 10
    assert [(p.x, p.y) for p in pts] == pytest.approx(
        [(0, 0), (10, 0), (20, 0), (30, 0),
         (30, 10), (30, 20), (30, 30), (30, 40)])
    with pytest.raises(ValueError):
        resample_chain(chain, 1)


def test_chain_congruence_rms_translation_and_mirror():
    a = [Point(0, 0), Point(10, 0), Point(20, 0)]
    shifted = [Point(5, 7), Point(15, 7), Point(25, 7)]
    assert chain_congruence_rms(a, shifted) == pytest.approx(0.0, abs=1e-9)
    mirrored = [Point(25, 7), Point(15, 7), Point(5, 7)]      # 镜像摆放
    assert chain_congruence_rms(a, mirrored) == pytest.approx(0.0, abs=1e-9)
    bent = [Point(5, 7), Point(15, 12), Point(25, 7)]         # 异形
    assert chain_congruence_rms(a, bent) > 1.0


def test_point_ring_nearest():
    assert point_ring_nearest(Point(50, 70), R) == Point(50, 50)
    assert point_ring_nearest(Point(120, 25), R) == Point(100, 25)
    assert point_ring_nearest(Point(-10, 60), R) == Point(0, 50)   # 角外


def test_chord_profile_smooth_and_cornered():
    """弦法向剖面：弧高/弧顶弦位/折角表（头注演算见上，t=链首端 0）。

    - 平滑弧 (0,0),(25,3),(50,4.5),(75,3),(100,0)：段向 6.84°/3.43°/
      -3.43°/-6.84°，逐转角 3.41°/6.86°/3.41° 均 <8° -> 无折角；
      弦 (0,0)->(100,0)、n̂=(0,1)，弧高 4.5 @ 弦位 0.5；
    - 帐篷链 (0,0),(50,10),(100,0)：转角 22.62° -> 折角 (0.5, 10)；
    - 内参考在弦另一侧 (50,-5) -> 同链弧高翻号 -10（向片内为正口径）；
    - 退化零长弦 -> (0, 0, [])。
    """
    smooth = [Point(x, y) for x, y in
              ((0, 0), (25, 3), (50, 4.5), (75, 3), (100, 0))]
    sag, at, corners = chord_profile(smooth, Point(50, 5))
    assert sag == pytest.approx(4.5, abs=1e-9)
    assert at == pytest.approx(0.5, abs=1e-9)
    assert corners == []
    tent = [Point(0, 0), Point(50, 10), Point(100, 0)]
    sag, at, corners = chord_profile(tent, Point(50, 5))
    assert sag == pytest.approx(10.0, abs=1e-9)
    assert at == pytest.approx(0.5, abs=1e-9)
    assert corners == [(0.5, 10.0)]
    sag_flip, _, _ = chord_profile(tent, Point(50, -5))
    assert sag_flip == pytest.approx(-10.0, abs=1e-9)     # 内侧在下方翻号
    assert chord_profile([Point(3, 3)], Point(0, 0)) == (0.0, 0.0, [])
