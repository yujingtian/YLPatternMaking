"""S2 注入协议测试（schema.build_prompt / build_template + parse 的 S2 半部）。

金标约定：
- 白名单 22 键 = 5 轴 + 10 开关 + 7 枚举（含 mouth_depth 弧深伪轴；
  front_pouch 袋布不在模型面——无判据通道，未分析到不发射），枚举值域与
  PatternOptions 校验器同源；
- prompt 四级注入齐全（尺寸/预判/先验/判据手册）且内嵌预填模板可被
  parse_model_json 原样解析、sanitize 归一回预填值（prompt<->解析回环）；
- _CRITERIA 与 .doc/参数预测/款式判据手册.md 同源（哨兵短语双向在册）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.extract.parse import parse_model_json, sanitize
from agent.extract.prejudge import prejudge_axes, prior_switches
from agent.extract.schema import (
    AXIS_KEYS,
    ENUM_DEFAULTS,
    MODEL_KEYS,
    SWITCH_KEYS,
    build_prompt,
    build_template,
)

_MANUAL = Path(__file__).parents[1] / ".doc" / "参数预测" / "款式判据手册.md"


def _fixture():
    # 29 码女款 front_rise 31：归一化 31−(29−27)×0.75=29.5 → high（与描述词一致）
    measurements = {"waist": 74.0, "hip": 91.0, "front_rise": 31.0,
                    "hem": 40.0}
    prejudged = prejudge_axes(measurements, {"waist_position": "high"}, 29)
    priors = prior_switches()
    prompt = build_prompt("女款高腰小脚牛仔裤", measurements, prejudged, priors, 2)
    return measurements, prejudged, priors, prompt


# -- 白名单 --------------------------------------------------------------------


def test_model_keys_coverage():
    assert set(MODEL_KEYS) == set(AXIS_KEYS) | set(SWITCH_KEYS) | set(ENUM_DEFAULTS)
    assert len(MODEL_KEYS) == 22   # front_pouch 不在模型面（无判据通道）
    assert MODEL_KEYS["front_pocket_mouth_depth"] == ("shallow", "standard", "deep")


def test_enum_domains_match_engine():
    """与 PatternOptions 校验器同源的值域抽查（options.py L679/708/784/869）。"""
    assert MODEL_KEYS["front_pocket_mouth_mode"] == ("bulge", "tangent", "polyline")
    assert MODEL_KEYS["front_pocket_facing_mode"] == ("tangent", "offset", "bulge")
    assert MODEL_KEYS["watch_pocket_mode"] == ("custom", "facing_intersect")
    assert MODEL_KEYS["back_patch_shape"] == ("rectangle", "baker_shield",
                                              "angular", "custom")
    assert MODEL_KEYS["waistband_type"] == ("straight", "curved")
    assert MODEL_KEYS["fit"] == ("skinny", "slim", "regular", "loose")


# -- prompt 注入 + 模板回环 -----------------------------------------------------


def test_prompt_injections_and_roundtrip():
    measurements, prejudged, priors, prompt = _fixture()
    assert "女款高腰小脚牛仔裤" in prompt
    assert "腰围 74" in prompt and "前浪 31" in prompt      # ①尺寸
    assert "front_rise 31" in prompt                        # ②预判依据
    assert "front_pocket=有" in prompt                      # ③先验
    assert "弯腰头" in prompt and "盾形袋底" in prompt       # ④判据手册
    assert "2 张" in prompt                                 # 照片数
    # 回环：内嵌模板可被 S2 解析器原样吃回
    parsed = parse_model_json(prompt)
    assert set(parsed) == set(MODEL_KEYS)
    obs = sanitize(parsed)
    assert not obs.dropped
    template = build_template(measurements, prejudged, priors)
    for key, entry in obs.entries.items():
        assert entry.value == template[key]["value"]


def test_template_prefill_semantics():
    measurements, prejudged, priors, _ = _fixture()
    template = build_template(measurements, prejudged, priors)
    # 轴=预判（conf 0.6、evidence 带「预判：」）
    assert template["waist_position"]["value"] == "high"
    assert template["waist_position"]["confidence"] == 0.6
    assert template["waist_position"]["evidence"].startswith("预判：")
    # fit 轴映射 wide→loose；无 wide 直接用轴值
    assert template["fit"]["value"] == "skinny"    # hem40/hip91=0.44 → skinny
    # 开关=先验 conf 0.5；back_dart False（K4 有育克默认无省）
    assert template["back_dart"]["value"] is False
    assert template["back_dart"]["confidence"] == 0.5
    # 枚举缺省=引擎默认 conf 0.4
    assert template["waistband_type"]["value"] == "straight"


def test_template_axis_fallback_without_anchors():
    template = build_template({}, prejudge_axes({}, {}), prior_switches())
    assert template["waist_position"]["value"] == "mid"
    assert template["waist_position"]["confidence"] == 0.3
    assert template["fit_level"]["value"] == "regular"


# -- 判据手册同源 ---------------------------------------------------------------


def test_criteria_synchronized_with_manual():
    """手册在册时校验同源：每条判据的哨兵短语必须同时出现在手册与 prompt。"""
    if not _MANUAL.is_file():
        pytest.skip("手册未建")
    manual = _MANUAL.read_text(encoding="utf-8")
    _, _, _, prompt = _fixture()
    sentinels = ["等宽直条", "下凹弧线", "弯月弧线", "底中点尖出", "J 形",
                 "一体裁出", "横向分割线", "第五袋", "卡胯骨", "紧身包腿",
                 "只分档不报数"]
    for s in sentinels:
        assert s in manual, f"手册缺哨兵短语：{s}"
        assert s in prompt, f"prompt 缺哨兵短语：{s}（_CRITERIA 与手册失同步）"


# -- S2 响应解析（parse.py 半部）------------------------------------------------


def test_parse_model_json_fence_prose_and_junk():
    fenced = '说明如下。\n```json\n{"waistband_type": "curved"}\n```\n以上。'
    assert parse_model_json(fenced) == {"waistband_type": "curved"}
    prose = '我认为 {"waistband_type": "curved", "x": "}{\\""} 结论成立'
    assert parse_model_json(prose)["waistband_type"] == "curved"
    with pytest.raises(ValueError):
        parse_model_json("完全没有 JSON 的输出")


def test_sanitize_normalization_and_drops():
    raw = {
        "waistband_type": {"value": "Curved", "confidence": 0.9,
                           "evidence": "腰头上口侧缝处下凹弧线"},
        "watch_pocket": True,                    # 裸值形态
        "back_yoke": {"value": "true"},          # 字符串布尔
        "fit": {"value": "tight", "confidence": 2},   # 值域外 + conf 越界
        "unknown_key": 1,                        # 白名单外
    }
    obs = sanitize(raw)
    assert obs.entries["waistband_type"].value == "curved"
    assert obs.entries["waistband_type"].confidence == 0.9
    assert obs.entries["watch_pocket"].value is True
    assert obs.entries["watch_pocket"].confidence == 0.5
    assert obs.entries["back_yoke"].value is True
    assert "unknown_key" in obs.dropped
    assert any(d.startswith("fit=") for d in obs.dropped)
    assert "fit" not in obs.entries
    # sanitize 的 conf=2 已随值域外整条丢弃，另验夹取：
    obs2 = sanitize({"belt_loop": {"value": False, "confidence": 9}})
    assert obs2.entries["belt_loop"].confidence == 1.0


def test_sanitize_non_dict_raises():
    with pytest.raises(ValueError):
        sanitize([1, 2])
