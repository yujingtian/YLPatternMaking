"""reverse.measure 合成几何金标测试（不依赖真件/ezdxf）。

头注手工演算（Calibration weft=0.15 / warp=0.08，还原 = mm×0.85/0.92÷10；
全部件只给净样层 14，gross=None 走回退）：

- 前片环 (100,600)(160,600)(175,560)(215,538)(260,528)(320,525)(320,0)
  (100,0)(40,300)(55,450)：裆尖 (40,300)=x 极值；三导线 y=500/300/100；
  前弦：hip 250（左交 (70,500)、右 x=320）、thigh 280（(40,300) 顶点
  恰在线上、经下一条边 t=0 计入）、knee 240（(80,100)）、hem 220.1
  （y=0.5 处左交 x=99.9）；
  顶链角点 3 个：(100,600)−73.3°/(160,600)−69.4°/(320,525)−87.1°，
  腰边段 60、袋口弧 194.6（=5 段 hypot 和：42.72+45.65+46.10+60.07）；
  前浪链 = (100,600)(55,450)(40,300) = 156.626+150.748 = 307.374；
  身侧链 (320,525)->(320,0) = 525。
- 后片环 (620,600)(900,580)(900,0)(620,0)(560,300)(590,450)：hip 弦 304
  （左交 (596,480)）、thigh 340、knee 300、hem 280.1；后浪链
  2*hypot(30,150) = 305.941；身侧 580。导线 CB 端贴环上（真件口径）：
  臀 (596,480)、膝 (600,100)、毗 (560,300)=裆尖顶点。
- 机头环 (640,760)(860,740)(910,680)(630,700)：上口 220.907（CB 端
  (640,760) x 小在前）、下口 280.71；CB 端弧 hypot(10,60) = 60.828、
  侧端弧 hypot(50,60) = 78.102；下口与后片顶边同向量 (280,-20) ->
  拼合 RMS 0、偏移 (760,590)-(770,690) = (-10,-100)，拼回腰 CB
  (640,760)+off = (630,660) -> 臀 CB (596,480)：
  back_intake = 34*0.85/(180*0.92)*15 = 2.6178。
- 腰头环 (0,100)(340,100)(370,50)(20,50)：两长边 340/350，缝边=长边
  350 -> waist 29.75；带宽闭式解 W=(401.081-303.093)/2 = 48.994 ->
  4.507cm；长边 y 变程 0 -> 直腰头；竖直丝缕垂直于长边 -> 不发射 grain。
- 前代融合片（曲边三角，净边与引擎 Ω_facing 同构：顶/右直边 = 腰/外缝
  段、底部大弧 = 袋贴内边；左 flank 为 15° 步进圆弧象限 O=(60,76) r=60
  + 竖直段，弧内转角 15° < 修剪阈 25° < 换向角 C 82.4°/A 90°）
  (0,170)(20,170)(180,170)(180,95)(180,20)(150,16)(120,14)(90,14)
  (60,16)(44.47,18.04)(30,24.04)(17.57,33.57)(8.04,46)(2.04,60.47)
  (0,76) + 层 8 袋口缝线 (20,170)(35,130)(75,108)(120,98)(180,95)
  （=前片袋口弧平移 (-140,-430)，全等 RMS~0）：顶边走链长向 = 160
  （袋口段）、短向 20；袋口侧边 = (180,95)->(180,170) = 75；袋口弦
  P1m(20,170)->P2m(180,95) 负侧游程 = 大弧 [C(180,20)..(0,76),A(0,170)]
  （合成直边与大弧直连、无越弦杂点），折角修剪定 C/A：袋贴腰段 A->P1m
  = 20、侧段 P2m->C = 75。
- 8 键：hip = 2*(250+304)*0.085 = 94.18（若误把毗围当臀围按 2 倍算会
  得 105.4+，精确值断言即陷阱检验）；thigh = (280+340)*0.085 = 52.70；
  knee = 45.90；hem = (220.1+280.1)*0.085 = 42.517；
  waist = 350*0.085 = 29.75（组成式 2*(60+160+220.907)*0.085 = 74.95
  故意失衡 -> 告警行）；
  front_rise = 307.374*0.092+4.507 = 32.786；
  back_rise = (305.941+60.828)*0.092+4.507 = 38.250；
  outseam 前 (525+75)*0.092+4.507 = 59.707、后 (580+78.102)*0.092
  +4.507 = 65.053，mean 62.380。
- 选项：delta 原始 (304-250)/2*0.085 = 2.295 -> 钳 2.0+告警；
  knee/hem_adjust = 60/2*0.085 = 2.55；waist_balance =
  (220.907-220)/2*0.085 = 0.04；rise_adjust = 300*0.092+4.507-
  0.25*94.18 = 8.56；前中内收 = 60*0.085 - 94.18/20 = 0.391，
  adjust = 0.391-0.2*(94.18-29.75)/4 = -2.83；机头深 5.6/7.19；
  无毛样 -> 不发射缝份。
- 挖削口袋参数：p1_dist = 袋口段 160*0.085 = 13.60、p2_drop = 侧边段
  75*0.092 = 6.90；袋口链 (160,600)->(320,525) 还原后弦 P1(13.6,55.2)
  ->P2(27.2,48.3)，L = 15.2506、n̂ = (0.45245,0.89177)，内参考
  (15.3,27.6) 偏负 -> 反号取正：弧高 +2.97 @ 弦位 0.4426；三中间点
  还原后转角 40.14°/17.24°/10.42° 均 ≥8° -> polyline 式，折角表
  (0.18,2.70)/(0.44,2.97)/(0.69,2.06)（弦位/内推深度）。
- 袋贴内边（净边大弧）：腰段 20*0.085 = 1.70（width）、侧段 75*0.092 =
  6.90（side_w）；大弧 A(0,15.64)->C(15.3,1.84)（还原后），L = 20.604、
  n̂ = (0.66985,0.74258)，袋口弦中点 (100,132.5) 还原 (8.5,12.19) 偏正
  侧 -> 背离袋口弦为正：(17.57,33.57) 还原 (1.493,3.088) 偏离 −8.322
  （|.| 最大）-> bulge +8.32 @ 弦位 0.4619（A=腰端 P_fw）；mode=bulge。
  发射换算引擎单位（arc_through 渲染弧高 = 2×bulge、弧顶弦位 =
  0.375·bulge_at+0.3125）：bulge = 8.32/2 = 4.16、bulge_at =
  (0.4619-0.3125)/0.375 = 0.398（extras 存工厂真值不换算）。
"""

from __future__ import annotations

import pytest

from ylpattern.geometry import Point
from ylpattern.reverse.measure import (Calibration, body_geometry,
                                       measure_8, measure_options)
from ylpattern.reverse.model import OpenLine, Ring, SubPiece

CALIB = Calibration(weft=0.15, warp=0.08, source="测试")


def _ring(*pts: tuple[float, float]) -> Ring:
    return Ring(tuple(Point(x, y) for x, y in pts))


def _line(*pts: tuple[float, float]) -> OpenLine:
    return OpenLine(tuple(Point(x, y) for x, y in pts))


def _sub(key: str, ring: Ring, internals=(), grain=None) -> SubPiece:
    return SubPiece(block_key=key, sub_index=0,
                    name_hint=key.split(".")[-2] if "." in key else key,
                    net=ring, internals=internals, grain=grain)


FRONT = _ring((100, 600), (160, 600), (175, 560), (215, 538), (260, 528),
              (320, 525), (320, 0), (100, 0), (40, 300), (55, 450))
BACK = _ring((620, 600), (900, 580), (900, 0), (620, 0), (560, 300),
             (590, 450))
YOKE = _ring((640, 760), (860, 740), (910, 680), (630, 700))
BAND = _ring((0, 100), (340, 100), (370, 50), (20, 50))
POUCH = _ring((0, 170), (20, 170), (180, 170), (180, 95), (180, 20),
              (150, 16), (120, 14), (90, 14), (60, 16), (44.47, 18.04),
              (30, 24.04), (17.57, 33.57), (8.04, 46), (2.04, 60.47),
              (0, 76))
MOUTH_ARC = _line((20, 170), (35, 130), (75, 108), (120, 98), (180, 95))

H_GUIDES = (_line((30, 500), (320, 500)), _line((40, 300), (320, 300)),
            _line((30, 100), (320, 100)))
B_GUIDES = (_line((596, 480), (920, 480)), _line((560, 300), (920, 300)),
            _line((600, 100), (920, 100)))


def _mapping() -> dict[str, SubPiece]:
    return {
        "front_body": _sub("t.front.S", FRONT, H_GUIDES),
        "back_body": _sub("t.back.S", BACK, B_GUIDES),
        "yoke": _sub("t.yoke.S", YOKE),
        "waistband": _sub("t.band.S", BAND,
                          grain=_line((175, 40), (175, 110))),
        "fused_pocket": _sub("t.pouch.S", POUCH, (MOUTH_ARC,)),
    }


# ---- 导线识别与身片锚定 ----

def test_body_geometry_guides_and_anchors():
    fg = body_geometry(_mapping()["front_body"], "front")
    # 三导线按 y 序分类：低=膝、中=毗（端点贴裆尖）、高=臀
    assert fg.knee.midpoint().y == pytest.approx(100.0)
    assert fg.thigh.midpoint().y == pytest.approx(300.0)
    assert fg.hip.midpoint().y == pytest.approx(500.0)
    assert fg.crotch_tip == Point(40, 300)
    assert fg.cb_side == "min"
    assert fg.waist_cb == Point(100, 600)
    assert fg.waist_side == Point(320, 525)          # 袋口侧端
    bg = body_geometry(_mapping()["back_body"], "back")
    assert bg.waist_cb == Point(620, 600)
    assert bg.waist_side == Point(900, 580)


def test_body_geometry_rejects_bad_guide_structure():
    sub = _sub("t.x.S", FRONT, internals=H_GUIDES[:2])
    with pytest.raises(Exception):                    # ReverseError/ValueError
        body_geometry(sub, "front")
    # 毗围线端点不贴裆尖 -> 拒绝（毗/臀误配防线）
    bad = (_line((30, 500), (320, 500)), _line((30, 300), (320, 301)),
           _line((30, 100), (320, 100)))
    with pytest.raises(Exception):
        body_geometry(_sub("t.x.S", FRONT, internals=bad), "front")


# ---- 8 键测量 ----

def test_measure_8_girths():
    ms = measure_8("S", _mapping(), CALIB)
    v = ms.values
    assert v["hip"] == pytest.approx(94.18, abs=0.02)    # 2*(250+304)*0.085
    assert v["thigh"] == pytest.approx(52.70, abs=0.02)  # (280+340)*0.085
    assert v["knee"] == pytest.approx(45.90, abs=0.02)
    assert v["hem"] == pytest.approx(42.517, abs=0.02)
    assert v["waist"] == pytest.approx(29.75, abs=0.02)  # 缝边 350*0.085
    # 组成式失衡告警（合成件故意不一致）
    assert any("组成式" in t for t in ms.trace)
    assert ms.extras["waist_composition_cm"] == \
        pytest.approx(74.95, abs=0.05)


def test_measure_8_rises_outseam_and_extras():
    ms = measure_8("S", _mapping(), CALIB)
    v = ms.values
    assert v["front_rise"] == pytest.approx(32.786, abs=0.02)
    assert v["back_rise"] == pytest.approx(38.250, abs=0.02)
    assert v["outseam"] == pytest.approx(62.380, abs=0.02)
    assert ms.extras["front_waist_part_mm"] == pytest.approx(60.0, abs=0.1)
    assert ms.extras["pocket_bridge_mm"] == pytest.approx(160.0, abs=0.1)
    assert ms.extras["pocket_side_mm"] == pytest.approx(75.0, abs=0.1)
    assert ms.extras["yoke_top_mm"] == pytest.approx(220.907, abs=0.1)
    assert ms.extras["yoke_cb_arc_mm"] == pytest.approx(60.828, abs=0.1)
    assert ms.extras["yoke_side_arc_mm"] == pytest.approx(78.102, abs=0.1)
    assert ms.extras["mouth_congruence_rms"] < 0.5     # 平移全等
    # 袋口弧剖面（还原空间：x*0.085 / y*0.092）
    assert ms.extras["mouth_sagitta_cm"] == pytest.approx(2.97, abs=0.01)
    assert ms.extras["mouth_peak_at"] == pytest.approx(0.4426, abs=0.01)
    assert len(ms.extras["mouth_corners"]) == 3        # 三折角均 ≥8°
    # 袋贴内边（净边大弧：腰段/侧段/剖面）
    assert ms.extras["facing_waist_mm"] == pytest.approx(20.0, abs=0.1)
    assert ms.extras["facing_side_mm"] == pytest.approx(75.0, abs=0.1)
    assert ms.extras["facing_sagitta_cm"] == pytest.approx(8.32, abs=0.01)
    assert ms.extras["facing_peak_at"] == pytest.approx(0.4619, abs=0.01)


def test_measure_8_missing_role_raises():
    m = _mapping()
    del m["yoke"]
    from ylpattern.reverse.errors import ReverseError
    with pytest.raises(ReverseError):
        measure_8("S", m, CALIB)


# ---- 层 2 选项 ----

def test_measure_options_values():
    ms = measure_8("S", _mapping(), CALIB)
    opts, warns = measure_options("S", _mapping(), ms, CALIB)
    assert opts["delta"] == 2.0                        # 原始 2.295 钳制
    assert any("2.29" in w or "2.30" in w for w in warns)
    assert opts["knee_adjust"] == pytest.approx(2.55, abs=0.02)
    assert opts["hem_adjust"] == pytest.approx(2.55, abs=0.02)
    assert opts["waist_balance"] == pytest.approx(0.04, abs=0.02)
    assert opts["back_intake"] == pytest.approx(2.62, abs=0.05)
    assert opts["rise_adjust"] == pytest.approx(8.56, abs=0.05)
    assert opts["front_intake_adjust"] == pytest.approx(-2.83, abs=0.05)
    assert opts["waistband_width"] == pytest.approx(4.51, abs=0.02)
    assert opts["waistband_type"] == "straight"
    assert "waistband_grain" not in opts               # 垂直长边 = width 默认
    assert opts["back_yoke_cb_dist"] == pytest.approx(5.60, abs=0.02)
    assert opts["back_yoke_side_dist"] == pytest.approx(7.19, abs=0.02)
    assert opts["shrinkage_weft"] == pytest.approx(0.15)
    assert opts["shrinkage_warp"] == pytest.approx(0.08)
    assert "front_piece_seam_allowances" not in opts  # 无毛样不发射
    # 结构开关：裁片在场即开（识别观测）；合成映射只有 yoke/前代
    assert opts["back_yoke"] is True and opts["front_pocket"] is True
    assert opts["front_pocket_facing"] is True
    assert opts["front_pouch"] is False        # 袋布不在工厂 DXF，不推断
    assert opts["belt_loop"] is False
    assert "watch_pocket" not in opts and "back_patch" not in opts
    assert "fly_separate" not in opts                  # 无门襟片不发射
    assert opts["thigh_limit"] is True                 # 毗围线在（52.7>0）
    assert any("毗围" in w for w in warns)
    # 挖削口袋参数：P1/P2 锚点 + 袋口形态族（折角在 -> polyline）
    assert opts["front_pocket_p1_dist"] == pytest.approx(13.60, abs=0.01)
    assert opts["front_pocket_p2_drop"] == pytest.approx(6.90, abs=0.01)
    assert opts["front_pocket_mouth_mode"] == "polyline"
    corners = opts["front_pocket_mouth_corners"]
    assert [(round(t, 2), round(d, 2)) for t, d in corners] == [
        (0.18, 2.70), (0.44, 2.97), (0.69, 2.06)]
    assert "front_pocket_mouth_bulge" not in opts       # 折线式不发射弧高
    # 袋贴内边族（净边大弧量测，与引擎 Ω_facing 同构）
    assert opts["front_pocket_facing_width"] == pytest.approx(1.70, abs=0.01)
    assert opts["front_pocket_facing_side_w"] == pytest.approx(6.90, abs=0.01)
    assert opts["front_pocket_facing_mode"] == "bulge"
    # 发射为引擎单位：真弧高 8.32/2、弧顶弦位 0.4619 映射 (f-0.3125)/0.375
    assert opts["front_pocket_facing_bulge"] == pytest.approx(4.16, abs=0.02)
    assert opts["front_pocket_facing_bulge_at"] == pytest.approx(0.40, abs=0.01)
    assert any("袋贴内边 = 前代净边大弧" in w for w in warns)
    # 不可观测项披露：吃省/撇削单弧不可分离、tangent 不可辨识
    assert any("dart_width" in w and "不可分离" in w for w in warns)
    assert any("tangent" in w for w in warns)


def test_calibration_conflict_and_missing():
    from ylpattern.reverse.errors import ReverseError
    from ylpattern.reverse.measure import Calibration
    from ylpattern.reverse.model import FactoryDoc, PieceMeta
    doc = FactoryDoc(path="out/x W15%-L8%.dxf")
    doc.pieces.append(SubPiece(block_key="a", sub_index=0, name_hint="a",
                               meta=PieceMeta(annotation="横:12.0%，直:8.0%")))
    with pytest.raises(ReverseError):                  # 双源冲突
        Calibration.from_doc(doc)
    doc2 = FactoryDoc(path="out/plain.dxf")
    with pytest.raises(ReverseError):                  # 无源
        Calibration.from_doc(doc2)


# ---- 小表袋 custom 形状量测（_watch_shape/_watch_anchor） ----
# 手工演算（Calibration weft=0.15/warp=0.08，还原 x ×0.85/y ×0.92 ÷10）：
# - V 底五边形（5015 同形，mm）：顶 (0,500)(80,500)、右竖边 (80,480)
#   共线离散、谷 (40,450)、左 (0,465) -> 还原 (0,0)(6.80,0)(6.80,3.22)
#   (3.40,4.60)(0,3.22)（80×0.085=6.80、35×0.092=3.22、50×0.092=4.60），
#   共线点转角 0° < 2° 折叠 -> 5 锚点全 line；
# - 右竖边外鼓 4mm 圆弧（半径 (45²+4·4²)/(8·4) ≈ 65.3、步角 ~1.7° <
#   折叠阈）-> 段内弦高还原 4×0.085 = 0.34cm ≥0.1 发射 arc 边：
#   引擎 bulge = 0.34/2 = 0.17（arc_through 渲染弧高 = 2×bulge）、
#   弧顶弦位 0.5 -> bulge_at (0.5−0.3125)/0.375 = 0.5；dy 向下镜像
#   取右手法向号（外凸 +x 为正）；
# - 光板矩形 120×82 丝缕横：顶边还原 120×0.092 = 11.04 > 0.9×8.80 ->
#   对折片缝态两读不自设；能放下的 60×82：顶 5.52、深 82×0.085=6.97；
# - 锚位（5015 几何 p1 8.80/p2 6.89/顶宽 6.80/引擎 1.68@0.21）：
#   跨度 [0.5, 7.3] 弧最浅 ~5.34 − 安全距 2.2 = 3.14；直线袋口
#   （bulge 0）弦深 ~0.98 − 2.2 < 0.3 -> 放不下 None。

_V_PENTAGON = ((0.0, 0.0), (6.8, 0.0), (6.8, 3.22), (3.4, 4.6), (0.0, 3.22))


def test_watch_shape_v_pentagon_collinear_collapse():
    from ylpattern.reverse.measure import Calibration, _watch_shape
    calib = Calibration(weft=0.15, warp=0.08, source="测试")
    grain = _line((10, 400), (10, 470))              # 竖向丝缕（经向贴 y）
    # 正向环：自右竖边中间点起（顶边游程不在首位，考验回转定位）
    fwd = _sub("t.w.S", _ring((80, 480), (80, 465), (40, 450), (0, 465),
                              (0, 500), (80, 500)), grain=grain)
    pts, edges, w, bad = _watch_shape(fwd, 8.8, calib)
    assert bad is None
    assert tuple(tuple(round(v, 2) for v in p) for p in pts) == _V_PENTAGON
    assert tuple(edges) == (("line",),) * 5
    assert w == pytest.approx(6.8, abs=0.01)
    # 反向环：顶边 x 较小端是环序终点 -> 整体重排，锚仍 min-x、dx 恒非负
    rev = _sub("t.w.S", _ring((80, 480), (80, 500), (0, 500), (0, 465),
                              (40, 450), (80, 465)), grain=grain)
    pts2, edges2, _, bad2 = _watch_shape(rev, 8.8, calib)
    assert bad2 is None
    assert tuple(tuple(round(v, 2) for v in p) for p in pts2) == _V_PENTAGON
    assert tuple(edges2) == (("line",),) * 5
    assert all(dx >= 0.0 for dx, _ in pts2)


def test_watch_shape_arc_edge_engine_units():
    import math
    from ylpattern.reverse.measure import Calibration, _watch_shape
    calib = Calibration(weft=0.15, warp=0.08, source="测试")
    grain = _line((10, 400), (10, 470))
    # 右竖边 (80,500)->(80,455) 外鼓 4mm 圆弧（24 步、步角 ~1.7° < 2° 折叠阈）
    chord, sag = 45.0, 4.0
    R = (chord ** 2 + 4 * sag ** 2) / (8 * sag)
    cx, cy = 80.0 - (R - sag), 500.0 - chord / 2
    a_top = math.asin((chord / 2) / R)
    bow = [(cx + R * math.cos(a_top * (1 - 2 * i / 24)),
            cy + R * math.sin(a_top * (1 - 2 * i / 24))) for i in range(25)]
    ring_pts = [(0, 500), (80, 500), *bow, (40, 450), (0, 465)]
    pts, edges, _, bad = _watch_shape(_sub("t.w.S", _ring(*ring_pts),
                                           grain=grain), 8.8, calib)
    assert bad is None
    assert len(pts) == 5                             # 弧内离散点全折叠
    assert edges[1] == ("arc", pytest.approx(0.17, abs=0.01), 0.5)
    assert all(e == ("line",) for i, e in enumerate(edges) if i != 1)


def test_watch_shape_fold_rect_and_undiagnosable():
    from ylpattern.reverse.measure import Calibration, _watch_shape
    calib = Calibration(weft=0.15, warp=0.08, source="测试")
    grain_h = _line((0, 100), (100, 100))            # 横向丝缕（经向贴 x）
    # 光板矩形 120×82：还原顶边 120×0.092 = 11.04 > 0.9×8.80 -> 对折两读
    *_, bad = _watch_shape(_sub("t.w.S", _ring((0, 100), (120, 100),
                                               (120, 18), (0, 18)),
                                grain=grain_h), 8.8, calib)
    assert bad is not None and "对折" in bad
    # 能放下的矩形 60×82：custom 4 锚点全 line（顶 5.52、深 6.97）
    pts, edges, w, bad = _watch_shape(
        _sub("t.w.S", _ring((0, 100), (60, 100), (60, 18), (0, 18)),
             grain=grain_h), 8.8, calib)
    assert bad is None and len(pts) == 4
    assert all(e == ("line",) for e in edges)
    assert w == pytest.approx(5.52, abs=0.01)
    assert pts[-1] == pytest.approx((0.0, 6.97), abs=0.01)
    # 无丝缕线：织物轴向不可定
    *_, bad2 = _watch_shape(_sub("t.w.S", _ring((0, 100), (60, 100),
                                                (60, 18), (0, 18))), 8.8, calib)
    assert bad2 is not None and "丝缕" in bad2


def test_watch_anchor_fit_and_too_shallow():
    from ylpattern.reverse.measure import _watch_anchor
    assert _watch_anchor(8.8, 6.89, 6.8, 1.68, 0.21) == pytest.approx(3.14, abs=0.05)
    assert _watch_anchor(8.8, 6.89, 6.8, 0.0, 0.5) is None   # 弦深 0.98 放不下


# —— 后贴袋 custom 形状/定位（2026-08-30 用户定则：在场即开 + 位置自设
#    三定则）。手工演算（Calibration weft=0.15/warp=0.08，丝缕竖 ->
#    u = mm×0.085、v = mm×0.092）：六角盾形 A(100,600) B(300,600)
#    C(280,440) D(200,400) E(120,440) F(110,560) —— 口宽 200×0.085 =
#    17.00、身高 200×0.092 = 18.40、C = (15.30,14.72)、E = (1.70,14.72)、
#    D = (8.50,18.40)、F = (0.85,3.68)；主形镜像对称（A<->B、C<->E、D
#    自映）、F 无镜像对应（最近 B 距 3.78 > 0.3）-> 单小台阶披露 ——

_PATCH_HEX = ((0.0, 0.0), (17.0, 0.0), (15.3, 14.72), (8.5, 18.4),
              (1.7, 14.72), (0.85, 3.68))


def test_patch_shape_shield_hexagon_and_step():
    from ylpattern.reverse.measure import Calibration, _patch_shape
    calib = Calibration(weft=0.15, warp=0.08, source="测试")
    grain = _line((200, 700), (200, 780))           # 竖向丝缕（经向贴 y）
    # 正向环（自底尖起，袋口游程不在环序首位，考验回转定位）
    fwd = _sub("t.p.S", _ring((200, 400), (120, 440), (110, 560), (100, 600),
                              (300, 600), (280, 440)), grain=grain)
    pts, edges, w, h, asym, bad = _patch_shape(fwd, calib)
    assert bad is None
    assert tuple(tuple(round(v, 2) for v in p) for p in pts) == _PATCH_HEX
    assert tuple(edges) == ((0.0, 0.5),) * 6        # 直边六角、边数=角点闭合
    assert w == pytest.approx(17.0, abs=0.01)
    assert h == pytest.approx(18.4, abs=0.01)
    assert asym is not None and "小台阶" in asym    # F 无镜像对应 -> 披露
    assert all(u >= 0.0 for u, _ in pts)
    # 反向环（袋口 x 小端为环序终点）-> 整体重排，锚仍 min-x、口边先行
    rev = _sub("t.p.S", _ring((200, 400), (280, 440), (300, 600), (100, 600),
                              (110, 560), (120, 440)), grain=grain)
    pts2, edges2, _, _, _, bad2 = _patch_shape(rev, calib)
    assert bad2 is None
    assert tuple(tuple(round(v, 2) for v in p) for p in pts2) == _PATCH_HEX
    assert tuple(edges2) == ((0.0, 0.5),) * 6


def test_patch_shape_arc_edge_negative_bulge():
    """外凸弧边取负（引擎局部->全局 180° 旋转保定向、全局环 CCW、
    arc_through 正 bulge = 内凹）：侧缝侧斜边 B->C 外凸 4mm 抛物线离散
    （26 点逐段转角 <2° 不留角）-> 还原弧高 +0.34cm @ 弦位 0.50 ->
    引擎 (−0.17, 0.50)。"""
    from ylpattern.reverse.measure import Calibration, _patch_shape
    calib = Calibration(weft=0.15, warp=0.08, source="测试")
    grain = _line((200, 700), (200, 780))
    bow = [(300 - 20 * t + 16.0 * t * (1.0 - t), 600 - 160 * t)
           for t in (i / 26.0 for i in range(27))]  # 峰值外凸 4mm
    ring = _ring((100, 600), *bow, (200, 400), (120, 440), (110, 560))
    pts, edges, w, _, _, bad = _patch_shape(_sub("t.p.S", ring, grain=grain),
                                            calib)
    assert bad is None
    assert len(pts) == 6                            # 离散弧段全部折叠
    assert edges[0] == (0.0, 0.5)
    assert edges[1][0] == pytest.approx(-0.17, abs=0.02)
    assert edges[1][1] == pytest.approx(0.5, abs=0.05)
    assert all(e == (0.0, 0.5) for i, e in enumerate(edges) if i != 1)
    # 无丝缕线：织物轴向不可定
    *_, bad2 = _patch_shape(_sub("t.p.S", _ring((0, 100), (60, 100), (60, 18),
                                                (0, 18))), calib)
    assert bad2 is not None and "丝缕" in bad2


def test_patch_place_rules():
    from ylpattern.reverse.measure import _patch_place
    # 常态：居中 + 默认 drop 3.5，袋底距毗围 23.24−3.5−14.42 = 5.32
    assert _patch_place(20.3, 23.24, 13.26, 14.42) == (3.52, 3.5, None)
    # drop 3.5 放不下 -> 上提到 cap = 17.0−14.42−0.5 = 2.08（仍 ≥0.5）
    inset, drop, note = _patch_place(20.3, 17.0, 13.26, 14.42)
    assert drop == pytest.approx(2.08, abs=0.01) and note is None
    # 连 0.5 都放不下 -> 钳 0.5 并披露越毗围线 14.42+0.5−14.0 = 0.92
    inset, drop, note = _patch_place(20.3, 14.0, 13.26, 14.42)
    assert drop == 0.5 and note is not None and "越毗围线" in note
    # 袋口宽贴满约克底线 -> inset 钳 0.5 不贴后浪
    inset, drop, note = _patch_place(20.3, 23.0, 20.0, 14.0)
    assert inset == 0.5 and note is not None and "不贴后浪" in note
