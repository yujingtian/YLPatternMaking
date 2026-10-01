"""S2 注入协议测试（schema.build_prompt / build_template + parse 的 S2 半部）。

金标约定：
- 白名单 26 键 = 5 轴 + 10 开关 + 7 枚举 + 4 比例读图（含 mouth_depth 弧深
  伪轴；front_pouch 袋布不在模型面——无判据通道，未分析到不发射），枚举值域
  与 PatternOptions 校验器同源；比例键值域 = parse 浮点窗（K5-d）；
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
    RATIO_KEYS,
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
    assert set(MODEL_KEYS) == set(AXIS_KEYS) | set(SWITCH_KEYS) | \
        set(ENUM_DEFAULTS) | set(RATIO_KEYS)
    assert len(MODEL_KEYS) == 28   # front_pouch 不在模型面（无判据通道）；
    # 比例读图 6 键（K5-d，2026-10-01 扩 p2/小表袋宽/小表袋定位两键）值域
    # = parse 浮点窗（物理窗在 derive 钳制）
    assert MODEL_KEYS["ratio_front_pocket_p1"] == (0.10, 0.90)
    assert MODEL_KEYS["ratio_front_pocket_p2"] == (0.10, 0.90)
    assert MODEL_KEYS["ratio_watch_pocket_width"] == (0.10, 0.90)
    assert MODEL_KEYS["ratio_back_patch_width"] == (0.10, 0.90)
    assert MODEL_KEYS["ratio_watch_pocket_top"] == (0.0, 0.50)
    assert MODEL_KEYS["ratio_watch_pocket_slope"] == (0.0, 0.90)
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
    sentinels = ["等宽直条", "下凹弧线", "弯月弧线", "底中点尖出",
                 "钝角浅尖也算尖", "J 形",
                 "一体裁出", "横向分割线", "第五袋", "卡胯骨", "紧身包腿",
                 "只分档不报数"]
    for s in sentinels:
        assert s in manual, f"手册缺哨兵短语：{s}"
        assert s in prompt, f"prompt 缺哨兵短语：{s}（_CRITERIA 与手册失同步）"


# -- 照片清单（C 照片三类，2026-09-29） ------------------------------------------


def test_prompt_photo_list_renders():
    """photo_meta 注【照片清单】逐张一行：类别 → 重点看清单、用户说明
    「以说明为准」；超 photo_count 截断；缺省 None 不注段——单发
    `agent extract` prompt 逐位不变（硬约束 5）。"""
    measurements = {"waist": 74.0, "hip": 91.0}
    prejudged = prejudge_axes(measurements, {}, None)
    priors = prior_switches()
    meta = [{"category": "front", "note": ""},
            {"category": "back", "note": ""},
            {"category": "other", "note": "袋口特写"}]
    prompt = build_prompt("女款牛仔裤", measurements, prejudged, priors, 3,
                          photo_meta=meta)
    assert "【照片清单（类别为用户标注" in prompt
    assert "以照片为准并在 evidence 说明" in prompt
    assert "第1张 正面平铺：重点看前口袋形态与弧深、门襟、小表袋" in prompt
    assert "第2张 背面平铺：重点看后贴袋形状、育克分割线、后腰省" in prompt
    assert "第3张 其他（用户说明：袋口特写）：以说明为准，重点核实所指特征" in prompt
    # 无说明 other：按画面内容判断；超 photo_count 截断（第 2 条不渲染）
    prompt2 = build_prompt("女款牛仔裤", measurements, prejudged, priors, 1,
                           photo_meta=[{"category": "other"}] + meta[1:])
    assert "第1张 其他：无说明，按画面内容判断" in prompt2
    assert "第2张" not in prompt2
    # 缺省 None：不注段（单发路径）
    plain = build_prompt("女款牛仔裤", measurements, prejudged, priors, 2)
    assert "【照片清单" not in plain


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


# -- 腰头必看项（2026-09-30 特征尺度修复配套） ------------------------------------

def test_prompt_waistband_must_look():
    """必看项点名 waistband_type：口诀 + 辅助图/整照两种读法指引。"""
    measurements = {"waist": 74.0, "hip": 91.0}
    prompt = build_prompt("女款牛仔裤", measurements,
                          prejudge_axes(measurements, {}, None),
                          prior_switches(), 1)
    assert "腰头形态是必看项" in prompt
    assert "一看门襟顶" in prompt and "二看后中" in prompt
    assert "工程自动辅助图" in prompt          # 有辅助图时的读法指引


def test_prompt_back_patch_must_look():
    """必看项点名 back_patch_shape（2026-09-30）：口诀 + 辅助图读法指引。"""
    measurements = {"waist": 74.0, "hip": 91.0}
    prompt = build_prompt("女款牛仔裤", measurements,
                          prejudge_axes(measurements, {}, None),
                          prior_switches(), 1)
    assert "后贴袋形状是必看项" in prompt
    assert "夹角大小不管" in prompt             # 钝角浅尖也算尖的口径进 prompt
    assert "后贴袋区放大图" in prompt           # 有辅助图时的读法指引


def test_prompt_photo_list_renders_crop_entries():
    """辅助图 meta 行渲染：category=other + 工程 note 走既有清单渲染。"""
    measurements = {"waist": 74.0, "hip": 91.0}
    meta = [{"category": "front", "note": ""},
            {"category": "other",
             "note": "工程自动辅助图：正面照的腰头区放大裁剪（非用户上传）"}]
    prompt = build_prompt("女款牛仔裤", measurements,
                          prejudge_axes(measurements, {}, None),
                          prior_switches(), 2, photo_meta=meta)
    assert "第2张 其他（用户说明：工程自动辅助图" in prompt
