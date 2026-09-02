"""S1 描述解析金标（parse.py：正则+同义词典+尺码换算，纯代码不走模型）。

覆盖：全半角/别名/连接词、单位换算（显式寸英寸 / 无单位英寸带）、
W/H 拉丁式、码号换算 29→74、同义词典命中（含长词优先/否定前缀/连裁反向）、
evidence 摘录格式。
"""

from __future__ import annotations

import pytest

from agent.extract.parse import parse_describe


# -- 尺寸正则 ------------------------------------------------------------------


def test_basic_full_set():
    """七键全中（中文别名、全半角逗号分隔）。"""
    r = parse_describe("腰围74，臀围91，前浪28，后浪33，裤长102，膝围36，脚口33")
    assert r.measurements == {"waist": 74.0, "hip": 91.0, "front_rise": 28.0,
                              "back_rise": 33.0, "outseam": 102.0,
                              "knee": 36.0, "hem": 33.0}


def test_fullwidth_digits_and_colon():
    """全角数字/小数点/冒号归一化后命中。"""
    r = parse_describe("腰围：７４．５")
    assert r.measurements["waist"] == 74.5


def test_connector_words():
    """「约为/大约/是」等连接词有界跳过。"""
    r = parse_describe("臀围约为91 膝围大概 36")
    assert r.measurements.get("hip") == 91.0
    assert r.measurements.get("knee") == 36.0


def test_inch_explicit_unit():
    """显式寸/英寸 → ×2.54 圆整 0.1。"""
    r = parse_describe("腰围29寸")
    assert r.measurements["waist"] == pytest.approx(73.7)   # 29×2.54=73.66


def test_inch_no_unit_band():
    """无单位小数值落英寸带 → 换算；29×2.54=73.66→73.7。"""
    r = parse_describe("waist 28")
    assert r.measurements["waist"] == pytest.approx(71.1)   # 28×2.54=71.12
    assert "英寸带" in r.evidence["waist"]


def test_cm_no_unit_out_of_band():
    """无单位大数值（带外）按 cm：前浪 28 是常规 cm 量级。"""
    r = parse_describe("前浪 28")
    assert r.measurements["front_rise"] == 28.0


def test_front_rise_inch_band():
    """前浪 11 落英寸带（9~16）→ 27.9。"""
    r = parse_describe("前浪11")
    assert r.measurements["front_rise"] == pytest.approx(27.9)


def test_latin_W_and_H():
    """W74/H91 拉丁式：大数值直接 cm。"""
    r = parse_describe("W74 H91")
    assert r.measurements.get("waist") == 74.0
    assert r.measurements.get("hip") == 91.0
    assert r.size_label is None


# -- 尺码换算 ------------------------------------------------------------------


def test_size_label_convert_to_waist():
    """29码 无显式腰围 → waist=round(29×2.54)=74，evidence 注换算式。"""
    r = parse_describe("29码 高腰小脚")
    assert r.size_label == 29
    assert r.measurements["waist"] == 74.0
    assert "29码×2.54" in r.evidence["waist"]


def test_size_label_no_override_explicit():
    """显式腰围在场时码号不覆盖：腰围29寸 + 29码 → waist 73.7、label 29。"""
    r = parse_describe("腰围29寸 29码")
    assert r.size_label == 29
    assert r.measurements["waist"] == pytest.approx(73.7)


def test_W29_is_label_not_waist():
    """W29（小数值）是码号不是腰围 cm。"""
    r = parse_describe("W29 高腰")
    assert r.size_label == 29
    assert r.measurements["waist"] == 74.0
    assert r.evidence["waist"].startswith("尺码换算")


def test_size_label_out_of_range_ignored():
    """码号合理带 20~48 之外忽略（如「尺码165」身高误写）。"""
    r = parse_describe("尺码165")
    assert r.size_label is None
    assert "waist" not in r.measurements


# -- 同义词典 ------------------------------------------------------------------


def test_hints_full_sentence():
    """「女款高腰微弹小脚牛仔裤」→ 四轴倾向 + 命中词记录。"""
    r = parse_describe("女款高腰微弹小脚牛仔裤，腰围74")
    assert r.hints["gender"] == "female"
    assert r.hints["waist_position"] == "high"
    assert r.hints["stretch"] == "low"           # 微弹→low，不误触「弹力」
    assert r.hints["fit_level"] == "skinny"
    assert r.hint_words["fit_level"] == "小脚"


def test_hint_long_word_priority():
    """「中高腰」命中 mid_high 而非 high（同位长词优先 + 最早出现）。"""
    r = parse_describe("中高腰直筒")
    assert r.hints["waist_position"] == "mid_high"
    assert r.hints["fit_level"] == "regular"


def test_hint_negation():
    """否定前缀：没有小表袋 → watch_pocket off；正向 → on。"""
    r = parse_describe("没有小表袋")
    assert r.hints.get("watch_pocket") == "off"
    assert parse_describe("带小表袋").hints["watch_pocket"] == "on"


def test_hint_fly_separate_liancai():
    """连裁词 → fly_separate off（语义反向组）。"""
    r = parse_describe("门襟连裁")
    assert r.hints.get("fly_separate") == "off"


def test_mom_jeans_cross_axis():
    """妈妈裤跨轴：waist_position=high + fit_level=loose（A 表）。"""
    r = parse_describe("妈妈裤")
    assert r.hints["waist_position"] == "high"
    assert r.hints["fit_level"] == "loose"


def test_evidence_snippet_format():
    """尺寸 evidence 落「描述摘录」原文。"""
    r = parse_describe("腰围74cm")
    assert "描述摘录" in r.evidence["waist"]
    assert "74" in r.evidence["waist"]


def test_empty_describe():
    """无数字无款式词：零编造（尺寸/码号空）。"""
    r = parse_describe("好看的女裤")
    assert r.measurements == {}
    assert r.size_label is None
    assert r.hints == {"gender": "female"}
