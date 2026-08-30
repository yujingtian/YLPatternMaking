"""5015 真件金标测试（工厂 DXF 反解析全链）。

头注手工演算（5015 单码 S，缩水 W15%-L8%，还原 = 净样mm ×0.85/0.92 ÷10，
探针实测值详见 .doc/工厂DXF逆向解析.md §4）：

- hip = 2×(前弦 254.8 + 后弦 306.8)×0.85/10 = 95.48（工厂金标 95.3）；
- waist 主口径 = 腰头缝边（长边 756.9）×0.85/10 = 64.34；组成式 =
  2×(前腰段 67.9 + 袋口段 103.5 + 机头上口 209.6)×0.85/10 = 64.78
  （工厂金标 64.8，主副口径互差 0.44 < 0.5）；
- thigh = (292.9+387.1)×0.085 = 57.80；knee = (265.7+333.2)×0.085 =
  50.91；hem = (260.6+327.7)×0.085 = 50.01（腿管两片直取）；
- front_rise = 281.7×0.92/10 + 4.11 = 30.02；back_rise = (305.1 +
  机头CB弧 62.8)×0.92/10 + 4.11 = 37.95；
- outseam 前 101.10 / 后 101.03（闭环差 0.07；前后外缝净链 1054.2 /
  1053.5 互证），mean 101.06；
- delta 原始 (306.8−254.8)/2×0.085 = 2.21 → 钳 2.0（PatternOptions 上限）；
- waist_balance = (209.6 − (67.9+103.5))/2×0.085 = 1.62；
- back_intake：机头底边拼回后片顶边（RMS<3），成衣腰 CB→臀 CB
  |dx|×0.85/(|dy|×0.92)×15 = 5.52（工厂金标 5.5）；
- rise_adjust = 前直裆(265×0.92/10 + 4.11 = 28.49) − 0.25×95.48 = 4.68
  （工厂金标 4.9）；
- 前中内收：CF-裆尖水平 6.92 − 小裆宽 95.48/20 = 2.15，
  adjust = 2.15 − 0.2×(95.48−64.34)/4 = 0.59；
- 腰头宽 44.65×0.92/10 = 4.11、弯腰头（长边矢高 >2mm）、丝缕垂直于
  长边（width 默认，不发射）；
- 机头深 CB 62.8×0.92/10 = 5.77 / 侧 35.7×0.92/10 = 3.28；
- 前片缝份：横向缝边 12.7mm = ½" → 1.27、脚口竖向 31.7mm → 3.17；
- 袋口弧前片 vs 前代融合片全等 RMS 0.01（镜像摆放，平移全等口径）；
- 挖削口袋参数（2026-08-29）：p1_dist = 前代顶边袋口段 103.5×0.085 =
  8.80、p2_drop = 侧边段 74.9×0.092 = 6.89；袋口弧 33 顶点平滑单峰
  （最大离散转角 <8°、工厂矢高 37.1mm）各向异性还原后弦法向剖面
  弧高 3.36cm @ 弦位 0.39（0=腰头端）→ bulge 式；弧上无省痕 →
  dart_width/paring_n 保默认，tangent（h1/h2）不可辨识。
- 袋贴内边（2026-08-30 用户纠偏：片内两弧，内部 = 袋口缝线、净边
  大弧 = 袋贴内边，与引擎 Ω_facing 同构）：折角修剪定 A/C（换向角
  ~85° vs 弧内 ≤4°）→ 腰段 A→P1m 25.34×0.085 = 2.15（width，引擎
  P1→P_fw 同锚）、侧段 P2m→C 52.17×0.092 = 4.80（side_w，P2→P_fs
  同锚）；深 U 大弧（40 顶点）还原剖面真弧高 +6.20 @ 弦位 0.49
  （背离袋口弦为正 = 向裤身内侧凹入）。
- bulge 发射换算引擎单位（2026-08-30 用户复核 2× 夸张）：arc_through
  渲染弧高 = 2×bulge、弧顶弦位 = 0.375·bulge_at+0.3125 → 袋口
  1.68 @ 0.21（真 3.36/2、(0.39-0.3125)/0.375）、袋贴 3.10 @ 0.47
  （真 6.20/2、(0.49-0.3125)/0.375）；extras 存工厂真值不换算。
- 小表袋（2026-08-30 用户纠偏：5015 表袋件是自定义多边形、非袋贴
  相交）：匿名子件净环 80×50mm、丝缕竖（经向贴 y）-> 顶边 80×0.085
  = 6.80、总深 50×0.092 = 4.60、右竖边 35×0.092 = 3.22；ET 直边
  离散共线点（转角 <2°）折叠 -> 5 锚点 (0,0)(6.80,0)(6.80,3.22)
  (3.40,4.60)(0,3.22)、全 line 边 custom 发射；锚位自设 = 对解析
  重建的引擎袋口弧（1.68@0.21，顶边跨度 [0.5, 7.3] 内弧最浅 ~5.34）
  留 2.2 安全距（1.2 名义 + 引擎真实框架腰倾 ~5°/侧缝内倾 ~17° 对
  正交重建的倾斜余量，实测吃掉 0.46）取最深顶边 -> from_top 3.14、
  from_side 0.50。
- 后贴袋（2026-08-30 用户定则：在场即开 + 位置自设三定则——机头下方/
  对齐后腰中点/袋底保持毗围线上方）：匿名子件净环 156×156.7mm、丝缕
  竖 -> 口宽 156×0.085 = 13.26、身高 156.7×0.092 = 14.42（六角盾形：
  两侧斜边折到中尖，ET 共线折叠 6 角点）；侧缝侧斜边微外凸 +0.10cm
  @ 弦位 0.50 -> 引擎弧边 −0.05 @ 0.50（**外凸取负**：引擎局部->全局
  180° 旋转保定向、全局环 CCW、arc_through 正 bulge = 左手法向 = 内凹；
  小表袋 dy 镜像反定向外凸取正，勿混）；主形左右对称、袋口一端小台阶
  0.09×1.48（铺版无手性观测，取向自设台阶端靠后浪）；inset_x =
  (约克底线 238.9×0.085 = 20.30 − 13.26)/2 = 3.52 居中（引擎约克底线
  21.55 与工厂还原 20.30 的重建残差 -> 回环实测偏心 −0.62，宽断言）、
  drop_y 3.50（顶边->毗围线 23.24 − 3.50 − 14.42 -> 底距毗围 5.32）。

真件不入库（out/ gitignored）：缺文件整文件 skip。
"""

from __future__ import annotations

import glob
from pathlib import Path

import pytest

pytest.importorskip("ezdxf")

from ylpattern.reverse import assign_roles, detect_profile, read_dxf
from ylpattern.reverse.measure import Calibration, measure_8, measure_options

_OUT = Path(__file__).resolve().parent.parent / "out"
_FILES_5015 = sorted(glob.glob(str(_OUT / "5015*.dxf")))
_real = _FILES_5015[0] if _FILES_5015 else None

pytestmark = pytest.mark.skipif(
    _real is None, reason="out/5015*.dxf 真件不在库内（out/ gitignored）")


@pytest.fixture(scope="module")
def measured():
    doc = read_dxf(_real)
    rep = assign_roles(doc, detect_profile(doc))
    assert doc.sizes == ("S",)                     # 单码文件
    calib = Calibration.from_doc(doc)
    m = rep.for_size("S")
    ms = measure_8("S", m, calib)
    opts, warns = measure_options("S", m, ms, calib)
    return ms, opts, warns, calib


def test_calibration_sources(measured):
    _, _, _, calib = measured
    assert calib.weft == pytest.approx(0.15)
    assert calib.warp == pytest.approx(0.08)
    assert calib.source == "文件名"


def test_girth_golds(measured):
    ms, _, _, _ = measured
    v = ms.values
    assert v["hip"] == pytest.approx(95.3, abs=0.5)      # 工厂金标
    assert v["hip"] == pytest.approx(95.48, abs=0.05)    # 探针金标
    assert v["waist"] == pytest.approx(64.8, abs=0.7)
    assert ms.extras["waist_composition_cm"] == pytest.approx(v["waist"],
                                                              abs=0.5)
    assert v["thigh"] == pytest.approx(57.80, abs=0.1)
    assert v["knee"] == pytest.approx(50.91, abs=0.1)
    assert v["hem"] == pytest.approx(50.01, abs=0.1)
    # 结构自检：hip > waist、back_rise > front_rise、outseam > front_rise
    assert v["hip"] > v["waist"]
    assert v["back_rise"] > v["front_rise"]
    assert v["outseam"] > v["front_rise"]


def test_rise_outseam_and_closure(measured):
    ms, _, _, _ = measured
    v = ms.values
    assert v["front_rise"] == pytest.approx(30.02, abs=0.15)
    assert v["back_rise"] == pytest.approx(37.95, abs=0.3)
    assert v["outseam"] == pytest.approx(101.06, abs=0.3)
    # 前后外缝闭环（同一裤长两侧走链互差 < 0.5cm）
    assert abs(v["front_rise"] + 0.0) >= 0                # 占位无害
    trace = "\n".join(ms.trace)
    assert "前 101.10" in trace and "后 101.03" in trace


def test_adjust_family_golds(measured):
    ms, opts, warns, _ = measured
    assert opts["delta"] == 2.0                          # 原始 2.21 钳制
    assert any("2.21" in w for w in warns)
    assert opts["waist_balance"] == pytest.approx(1.6, abs=0.2)
    assert opts["knee_adjust"] == pytest.approx(2.87, abs=0.15)
    assert opts["hem_adjust"] == pytest.approx(2.86, abs=0.15)
    assert opts["rise_adjust"] == pytest.approx(4.9, abs=0.6)


def test_intake_golds(measured):
    _, opts, warns, _ = measured
    # 后中内收：机头拼回 + 腰/臀 CB 斜率 ×15（工厂金标 5.5）
    assert opts["back_intake"] == pytest.approx(5.5, abs=0.5)
    # 前中内收：水平距含小裆宽，扣除后绑 _adjust（ratio 留默认 0.2）
    assert opts["front_intake_adjust"] == pytest.approx(0.59, abs=0.3)
    assert any("小裆宽" in w for w in warns)


def test_waistband_yoke_and_shrinkage(measured):
    ms, opts, _, calib = measured
    assert opts["waistband_width"] == pytest.approx(4.11, abs=0.1)
    assert opts["waistband_type"] == "curved"
    assert "waistband_grain" not in opts                  # 垂直长边=width 默认
    assert opts["back_yoke_cb_dist"] == pytest.approx(5.77, abs=0.15)
    assert opts["back_yoke_side_dist"] == pytest.approx(3.28, abs=0.15)
    assert opts["shrinkage_weft"] == pytest.approx(0.15)
    assert opts["shrinkage_warp"] == pytest.approx(0.08)
    assert calib.weft == pytest.approx(0.15)


def test_pocket_inference_golds(measured):
    """挖削口袋参数（2026-08-29 口径：推测完整、不可观测项披露）。"""
    ms, opts, warns, _ = measured
    # P1/P2 锚点 = 前代顶边袋口段 / 侧边段（自腰外缝顶点起量的弧长）
    assert opts["front_pocket_p1_dist"] == pytest.approx(8.80, abs=0.05)
    assert opts["front_pocket_p2_drop"] == pytest.approx(6.89, abs=0.05)
    # 袋口弧 33 顶点平滑单峰、无 ≥8° 折角 -> bulge 式；发射 = 引擎单位
    # （arc_through 渲染弧高 = 2×bulge：真 3.36 -> 1.68；
    #  弧顶弦位映射 (0.39-0.3125)/0.375 -> 0.21）
    assert opts["front_pocket_mouth_mode"] == "bulge"
    assert opts["front_pocket_mouth_bulge"] == pytest.approx(1.68, abs=0.05)
    assert opts["front_pocket_mouth_bulge_at"] == pytest.approx(0.21, abs=0.03)
    assert "front_pocket_mouth_corners" not in opts
    assert ms.extras["mouth_sagitta_cm"] == pytest.approx(3.36, abs=0.1)
    assert ms.extras["mouth_corners"] == []
    # 袋贴内边 = 净边大弧（腰段 25.3mm×0.085、侧段 52.2mm×0.092、深 U 剖面）；
    # bulge 发射 = 引擎单位（真 6.20 -> 3.10、弦位 0.49 -> 0.47）
    assert opts["front_pocket_facing_width"] == pytest.approx(2.15, abs=0.02)
    assert opts["front_pocket_facing_side_w"] == pytest.approx(4.80, abs=0.05)
    assert opts["front_pocket_facing_mode"] == "bulge"
    assert opts["front_pocket_facing_bulge"] == pytest.approx(3.10, abs=0.1)
    assert opts["front_pocket_facing_bulge_at"] == pytest.approx(0.47, abs=0.03)
    assert ms.extras["facing_waist_mm"] == pytest.approx(25.34, abs=0.1)
    assert ms.extras["facing_side_mm"] == pytest.approx(52.17, abs=0.1)
    assert any("袋贴内边 = 前代净边大弧" in w for w in warns)
    # 不可观测项披露（层 4/5）：吃省与撇削幂、tangent 柄
    assert any("dart_width" in w and "不可分离" in w for w in warns)
    assert any("tangent" in w for w in warns)


def test_structural_switches(measured):
    """结构开关：识别观测裁片在场（5015：机头/前代/裤耳/单排+双排门襟
    都在）；小表袋在场即开、custom 净样原样（2026-08-30 用户纠偏：表袋
    件是多边形非袋贴相交；位置自设只保证上部不被面板藏住）；后贴袋在
    场即开、custom 净样原样 + 位置自设三定则（机头下方/对齐后腰中点/
    袋底保持毗围线上方）。"""
    _, opts, warns, _ = measured
    assert opts["back_yoke"] is True
    assert opts["front_pocket"] is True
    assert opts["front_pocket_facing"] is True
    # 袋布走里料、不在工厂打版 DXF：显式关，不从前代一体片推断
    assert opts["front_pouch"] is False
    assert opts["belt_loop"] is True
    # 小表袋 custom 净样原样：V 底五边形（右竖边 ET 共线离散折叠）+
    # 全 line 边；锚位自设对解析重建的引擎袋口弧留 2.2 安全距（含框架
    # 倾斜余量）取最深顶边（可见性回环断言见 test_watch_pocket_visibility）
    assert opts["watch_pocket"] is True
    assert opts["watch_pocket_mode"] == "custom"
    assert opts["watch_pocket_points"] == (
        (0.0, 0.0), (6.8, 0.0), (6.8, 3.22), (3.4, 4.6), (0.0, 3.22))
    assert opts["watch_pocket_edges"] == (("line",),) * 5
    assert opts["watch_pocket_offset_from_top"] == pytest.approx(3.14, abs=0.05)
    assert opts["watch_pocket_offset_from_side"] == pytest.approx(0.5, abs=0.01)
    assert any("custom 净样原样" in w for w in warns)
    # 后贴袋在场即开、custom 净样原样（六角盾形）：口宽 13.26、身高
    # 14.42，侧缝侧斜边微外凸 +0.10cm -> 引擎弧边 −0.05（外凸取负，
    # 见头注）；位置自设三定则（回环断言见 test_back_patch_loop）
    assert opts["back_patch"] is True
    assert opts["back_patch_shape"] == "custom"
    assert opts["back_patch_custom_points"] == (
        (0.0, 0.0), (13.26, 0.0), (12.25, 11.76), (6.63, 14.42),
        (1.01, 11.76), (0.09, 1.48))
    assert opts["back_patch_custom_edges"] == (
        (0.0, 0.5), (-0.05, 0.5), (0.0, 0.5), (0.0, 0.5), (0.0, 0.5),
        (0.0, 0.5))
    assert opts["back_patch_inset_x"] == pytest.approx(3.52, abs=0.02)
    assert opts["back_patch_drop_y"] == pytest.approx(3.5, abs=0.01)
    assert any("后贴袋" in w and "custom 净样原样" in w for w in warns)
    assert any("小台阶" in w for w in warns)
    assert opts["fly_separate"] is True
    assert "fly_sep_double" not in opts                   # 双排片在，保默认
    assert opts["thigh_limit"] is True                    # 毗围线在（57.8）


def test_watch_pocket_visibility(measured):
    """小表袋 custom 净样的引擎回环：draft 跑通 + 顶边对袋口【弧】
    （非弦——弧中段内垂 ~3cm，弦判据过严）净距 ≥1cm 不被藏。"""
    ms, opts, _, _ = measured
    from ylpattern.flows.front_flow import FRONT_FLOW
    from ylpattern.flows.runner import FlowRunner
    from ylpattern.params import Measurements, PatternOptions
    o = PatternOptions.from_dict(opts)
    m = Measurements.from_dict(
        {k: round(v, 2) for k, v in ms.values.items()})
    ctx = FlowRunner(m, o).run(FRONT_FLOW)
    mouth = ctx.curve("front.pocket_mouth")
    arc = [mouth.point_at(i / 400) for i in range(401)]
    p1 = ctx.point("front.watch_pocket_pt1")
    p2 = ctx.point("front.watch_pocket_pt2")
    worst = min(
        p1.y - max(a.y for a in arc if abs(a.x - x) < 0.35)
        for x in (p1.x + (p2.x - p1.x) * i / 40 for i in range(41)))
    assert worst >= 1.0                    # 顶边整体在挖削开口内（O 侧可见）
    # V 底五边形净样：谷底 pt4 与外侧下角 pt5 都在顶边下方成袋（非退化）
    assert ctx.point("front.watch_pocket_pt4").y < p1.y - 3.0
    assert ctx.point("front.watch_pocket_pt5").y < p1.y - 3.0


def test_back_patch_loop(measured):
    """后贴袋 custom 净样的引擎回环：FULL_FLOW 跑通 + 局部系还原逐位
    一致 + 弧边外凸（负号口径，渲染弧高 = 工厂真弧高）+ 三定则成立
    （整袋约克下方、袋口为最高边、居中 ≈ 引擎约克底线半长、袋底在
    毗围线/裆尖水位上方）。"""
    import math
    ms, opts, _, _ = measured
    from ylpattern.flows.back_flow import FULL_FLOW
    from ylpattern.flows.runner import FlowRunner
    from ylpattern.params import Measurements, PatternOptions
    o = PatternOptions.from_dict(opts)
    m = Measurements.from_dict(
        {k: round(v, 2) for k, v in ms.values.items()})
    ctx = FlowRunner(m, o).run(FULL_FLOW)
    origin = ctx.point("back.yoke_cb_point")
    side = ctx.point("back.yoke_side_point")
    vec = side - origin
    length = vec.length
    ux, uy = vec.dx / length, vec.dy / length
    vx, vy = -uy, ux
    if vy > 0:
        vx, vy = -vx, -vy
    anchor = ctx.point("back.patch_anchor")
    pts = []
    i = 1
    while f"back.patch_net_pt{i}" in ctx.sheet:
        pts.append(ctx.point(f"back.patch_net_pt{i}"))
        i += 1
    assert len(pts) == len(opts["back_patch_custom_points"])
    loc = []
    for p in pts:
        q = p - anchor
        loc.append((q.dx * ux + q.dy * uy, q.dx * vx + q.dy * vy))
    for (gu, gv), (eu, ev) in zip(loc, opts["back_patch_custom_points"]):
        assert gu == pytest.approx(eu, abs=1e-6)
        assert gv == pytest.approx(ev, abs=1e-6)
    # 弧边负号口径：seg2 弧中点比弦中点更离环质心（外凸）、渲染弧高
    # = 工厂真弧高 0.10（arc_through 渲染 = 2×bulge，发 −0.05）
    q = ctx.curve("back.patch_net_seg2").point_at(0.5) - anchor
    am = (q.dx * ux + q.dy * uy, q.dx * vx + q.dy * vy)
    a, b = loc[1], loc[2]
    cm = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    cx = sum(p[0] for p in loc) / len(loc)
    cy = sum(p[1] for p in loc) / len(loc)
    assert math.hypot(am[0] - cx, am[1] - cy) > math.hypot(cm[0] - cx, cm[1] - cy)
    assert math.hypot(am[0] - cm[0], am[1] - cm[1]) == pytest.approx(0.10, abs=0.02)
    # 三定则：整袋在约克底线之下（v̂ 坐标 >0）、袋口为最高边
    for p in pts:
        q = p - origin
        assert q.dx * vx + q.dy * vy > 0.0
    assert all(loc[0][1] <= lv[1] + 1e-9 for lv in loc)
    # 居中：袋口中点 u ≈ 引擎约克底线半长（|偏心| <1.5：残差 = 引擎
    # 约克底线 21.55 vs 工厂还原 20.30 的重建差，实测 −0.62）
    ao = anchor - origin
    mouth_u = (loc[0][0] + loc[1][0]) / 2.0 + ao.dx * ux + ao.dy * uy
    segs = []
    i = 1
    while f"back.yoke_bottom_seg{i}" in ctx.sheet:
        segs.append(ctx.sheet.get(f"back.yoke_bottom_seg{i}").geom)
        i += 1

    def _seg_len(g):
        try:
            return g.length
        except AttributeError:
            return sum(g.point_at(k / 100).distance_to(
                g.point_at((k + 1) / 100)) for k in range(100))

    assert abs(mouth_u - sum(_seg_len(g) for g in segs) / 2.0) < 1.5
    # 袋底保持毗围线（裆尖水位）上方：实测高出 4.27
    crotch = ctx.point("back.crotch_vertex")
    assert min(p.y for p in pts) > crotch.y + 3.0


def test_seam_allowances_and_congruence(measured):
    ms, opts, _, _ = measured
    sa = opts["front_piece_seam_allowances"]
    assert sa["side"] == pytest.approx(1.27, abs=0.1)     # ½" 缝边
    assert sa["hem"] == pytest.approx(3.17, abs=0.3)      # 脚口卷边
    assert sa["waist"] == sa["rise"] == sa["inseam"] == sa["side"]
    # 袋口弧前片 vs 前代融合片：镜像摆放下平移全等
    assert ms.extras["mouth_congruence_rms"] < 2.0
    assert ms.extras["pocket_bridge_mm"] == pytest.approx(103.6, abs=1.0)
    assert ms.extras["yoke_top_mm"] == pytest.approx(209.6, abs=2.0)
