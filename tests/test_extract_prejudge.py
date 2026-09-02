"""轴预判金标（prejudge.py：B 表锚点，代码算好档位交 S2 确认）。

手工演算（K1 女表 / K8 初版）：
- 女表分带（归一化后）：≤20 低 / 20~23 中低 / 23~26 中 / 26~29 中高 / ≥29 高，
  带边界归上带（23→中、26→中高、29→高），20 归低。
- 男表：<23 低 / 23~26 中低（表 23~25，缺口归上带前） / 26~28 中 / 28~31 中高 /
  ≥31 高。
- 放码归一化：norm = front_rise − (码−基准)×0.75（女基准 27、男 31）。
- body_shape：臀腰差 ≥25 或 W/H≤0.75 → curvy；<18 → straight；其余 standard。
- fit：脚口/臀围 skinny<0.45 / slim<0.50 / regular<0.56 / loose<0.65 / wide≥0.65
  （0.45→slim、0.50→regular、0.56→loose、0.65→wide，边界归上带）。
"""

from __future__ import annotations

import pytest

from agent.extract.prejudge import (
    prejudge_axes,
    prior_switches,
    waist_position_band,
)


def _axes(m, hints=None, label=None):
    return prejudge_axes(m, hints or {}, label)


# -- K1 腰位五带（女表） --------------------------------------------------------


@pytest.mark.parametrize("front_rise,expected", [
    (20.0, "low"),        # ≤20 归低（显式）
    (20.1, "mid_low"),
    (22.5, "mid_low"),
    (23.0, "mid"),        # 带边界归上带
    (26.0, "mid_high"),
    (28.5, "mid_high"),
    (29.0, "high"),
    (30.0, "high"),
])
def test_female_waist_bands(front_rise, expected):
    band, ev = waist_position_band(front_rise, "female", None)
    assert band == expected
    assert "女表" in ev


# -- K1 腰位五带（男表） --------------------------------------------------------


@pytest.mark.parametrize("front_rise,expected", [
    (22.9, "low"),
    (23.0, "mid_low"),
    (25.5, "mid_low"),    # 表 23~25，25~26 缺口并入中低
    (26.0, "mid"),
    (27.5, "mid"),
    (28.0, "mid_high"),
    (30.5, "mid_high"),   # 表 28~30，30~31 缺口并入中高
    (31.0, "high"),
])
def test_male_waist_bands(front_rise, expected):
    band, ev = waist_position_band(front_rise, "male", None)
    assert band == expected
    assert "男表" in ev


# -- 放码归一化 ----------------------------------------------------------------


def test_normalization_small_label():
    """front_rise 28.5 + 女款 24 码：norm=28.5−(24−27)×0.75=30.75 → high。"""
    band, ev = waist_position_band(28.5, "female", 24)
    assert band == "high"
    assert "30.75" in ev and "归一化" in ev


def test_normalization_large_label():
    """front_rise 28.5 + 女款 30 码：norm=28.5−3×0.75=26.25 → mid_high。"""
    band, _ = waist_position_band(28.5, "female", 30)
    assert band == "mid_high"


def test_male_label_uses_male_base():
    """男款 34 码：norm=31−(34−31)×0.75=28.75 → mid_high。"""
    band, _ = waist_position_band(31.0, "male", 34)
    assert band == "mid_high"


def test_no_label_no_normalization():
    """码号未知不归一化：front_rise 26 → mid_high。"""
    band, ev = waist_position_band(26.0, "female", None)
    assert band == "mid_high"
    assert "归一化" not in ev


# -- gender 轴 -----------------------------------------------------------------


def test_gender_from_hint():
    val, ev = _axes({}, {"gender": "male"})["gender"]
    assert val == "male"
    assert "描述词" in ev


def test_gender_from_size_label():
    assert _axes({}, {}, 31)["gender"][0] == "male"
    assert _axes({}, {}, 27)["gender"][0] == "female"


def test_gender_default_female():
    val, ev = _axes({})["gender"]
    assert val == "female"
    assert "默认" in ev


# -- body_shape（K8 初版） ------------------------------------------------------


@pytest.mark.parametrize("w,h,expected", [
    (70, 95, "curvy"),     # 差 25
    (68, 92, "curvy"),     # 差 24 但 W/H=0.739 ≤0.75
    (74, 91, "straight"),  # 差 17 <18
    (70, 90, "standard"),  # 差 20
])
def test_body_shape(w, h, expected):
    axes = _axes({"waist": w, "hip": h})
    assert axes["body_shape"][0] == expected
    assert "臀腰差" in axes["body_shape"][1]


def test_body_shape_needs_both():
    assert "body_shape" not in _axes({"waist": 70})


# -- fit_level（K8 初版） -------------------------------------------------------


@pytest.mark.parametrize("hem,hip,expected", [
    (40, 100, "skinny"),
    (45, 100, "slim"),     # 0.45 边界归上带
    (47, 100, "slim"),     # examples 金标锚例 0.47
    (50, 100, "regular"),
    (52, 100, "regular"),
    (56, 100, "loose"),
    (58, 100, "loose"),
    (65, 100, "wide"),
    (66, 100, "wide"),
])
def test_fit_ratio(hem, hip, expected):
    axes = _axes({"hem": hem, "hip": hip})
    assert axes["fit_level"][0] == expected


def test_fit_hem_ge_knee_wide():
    """脚口≥膝围 → wide（喇叭特例，比例再小也是）。"""
    axes = _axes({"hem": 40, "knee": 39, "hip": 100})
    assert axes["fit_level"][0] == "wide"
    assert "喇叭特例" in axes["fit_level"][1]


def test_fit_fallback_to_hint():
    axes = _axes({}, {"fit_level": "skinny"})
    assert axes["fit_level"] == ("skinny", "描述词「skinny」（无脚口/臀围锚点）")


# -- stretch / 冲突 / 先验 ------------------------------------------------------


def test_stretch_default_low():
    val, ev = _axes({})["stretch"]
    assert val == "low"
    assert "缺省" in ev


def test_stretch_from_hint():
    assert _axes({}, {"stretch": "none"})["stretch"][0] == "none"


def test_waist_conflict_number_wins():
    """front_rise 22.5（中低）vs 描述词「高腰」→ 数字锚点优先并留痕。"""
    axes = _axes({"front_rise": 22.5}, {"waist_position": "high"})
    assert axes["waist_position"][0] == "mid_low"
    assert "不一致" in axes["waist_position"][1]


def test_prior_switches():
    """D 表部件惯例：经典五袋全配 + 连裁需证据 + 有育克默认无后腰省（K4）。

    front_pouch 不在先验表：内部件照片看不到、描述侧无判据词，
    未分析到不发射（走引擎默认 False，用户口径 2026-09-02）。
    """
    assert prior_switches() == {
        "front_pocket": True, "front_pocket_facing": True,
        "watch_pocket": True, "back_patch": True, "back_yoke": True,
        "belt_loop": True, "fly": True, "fly_separate": True,
        "front_patch": False, "back_dart": False,
    }
