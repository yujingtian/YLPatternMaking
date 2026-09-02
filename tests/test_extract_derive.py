"""⑤ merge + derive + families 金标测试（全部手工演算，测试即文档）。

手工演算记录（公式：derive.py 头注；H_v = (H×0.25 + rise_adjust)×2/3，
rise_adjust 低−2.75/中低−1.0/中+0.75/中高+2.25/高+3.75）：

K2 前中（基准带中值 + 四维修正，clamp 3.5）：
- 中高腰 2.0 + 沙漏(无 d→+0.5) + 高弹 −0.5 + 紧身 +0.2 = 2.2（实战案例）
- 低腰 0.25 + 平腹 0.5 + 无弹 0.2 + 男 −0.5 = 0.45
- 高腰 3.0 + 阔腿 −0.2 = 2.8
- 高腰 3.0 + 沙漏(d=30→+1.0) + 无弹 0.2 = 4.2 → clamp 3.5（拉链刚性硬上限）
- ratio 记账：abs 2.0 ÷ ((91−74)/4=4.25) = 0.4706

K3 后中（X 锚点 5→2.0/15→3.0/20→3.5/25→4.5，d>25 封顶 4.0）：
- d=26 低腰：4.5→封顶 4.0→−0.5 = 3.5（实战案例 15:3.5）
- d=15→3.0；d=20→3.5；d=25→4.5；d=10→2.5；d=30→封顶 4.0
- d=20 有弹：3.5−0.5 = 3.0（降半档案例）；d=24 高腰：4.3+0.5 = 4.8
- d=5 低腰 1.5（下限）；d=25 高腰 5.0（极限 5）
- H95 低腰 H_v = (23.75−2.75)×2/3 = 14.0 → ② = 14×3.5/15 = 3.2667

K4 余量排除法（R=(H−W)/2，弹力 ×0.75）：
- 案例算式：13.0 − 1.5 − 3.5 − 1.0 − 3.0 = 4.0（yoke_residual 纯算式）
- 溢余：W70 H82 R=6 − ①1.25 − ②2.55 − ③0.8 − ④3.5 = −2.1 → 无省浅育克
- 有育克 ⑤>0：约克省载体 = back_dart 三键，单省宽=⑤（闭口仅 1 省，
  用户口径 2026-09-02；「有育克默认无后腰省」指成品形态）
- 无育克单省：W70 H92 R=11 − ①1.25 − ②4.1167 − ③1.0 − ④3.5 = 1.1333
- 无育克双省：W69 H95 R=13 − ①0.85 − ②3.2667 − ③1.0 − ④4.75 = 3.1333
  → count=2 width=1.5667
- delta 大差：standard 1.0+0.5=1.5；curvy 1.35+0.5=1.85（clamp 2.0 内）
"""

from __future__ import annotations

import pytest

from agent.extract.derive import (
    KeyMeta,
    back_intake_abs,
    back_intake_x,
    curvy_waist_balance,
    dart_balance,
    derive_all,
    enforce_dependencies,
    front_crotch_adjust_for,
    front_intake_abs,
    front_intake_ratio,
    hip_waist_height_est,
    merge,
    resolve_delta,
    rise_adjust_for,
    stretch_adjusts,
    yoke_residual,
)
from agent.extract.parse import Observation, ObservationEntry
from agent.extract.prejudge import prejudge_axes, prior_switches


def _axes(**kw) -> dict[str, str]:
    base = {"waist_position": "mid", "gender": "female",
            "body_shape": "standard", "fit_level": "regular", "stretch": "low"}
    base.update(kw)
    return base


def _entry(value, conf=0.9, ev="看见具体视觉特征"):
    return ObservationEntry(value, conf, ev)


def _m(w, h):
    return {"waist": float(w), "hip": float(h)}


# -- K2 前中内收 -----------------------------------------------------------------


def test_k2_golden_cases():
    # 实战案例：中高腰沙漏高弹紧身女款（无尺寸 → 沙漏修正取 0.5 底）
    v, ev = front_intake_abs({}, _axes(waist_position="mid_high",
                                       body_shape="curvy", stretch="high",
                                       fit_level="skinny"))
    assert v == pytest.approx(2.2)
    assert "基准 mid_high 带中值 2.0" in ev
    # 低腰平腹无弹直筒男款
    v, _ = front_intake_abs(
        {}, _axes(waist_position="low", body_shape="straight", stretch="none",
                  gender="male"))
    assert v == pytest.approx(0.45)
    # 高腰阔腿
    v, _ = front_intake_abs({}, _axes(waist_position="high", fit_level="wide"))
    assert v == pytest.approx(2.8)
    # 硬上限 3.5（拉链刚性）：3.0 + 沙漏(d=30→+1.0) + 无弹 0.2 = 4.2 → 3.5
    v, _ = front_intake_abs(_m(65, 95), _axes(waist_position="high",
                                              body_shape="curvy",
                                              stretch="none"))
    assert v == pytest.approx(3.5)
    # 沙漏按臀腰差超 25 连续上插：d=26 → +0.6
    v, _ = front_intake_abs(_m(66, 92), _axes(waist_position="mid_high",
                                              body_shape="curvy"))
    assert v == pytest.approx(2.6)


def test_k2_ratio_accounting():
    ratio, absv, ev = front_intake_ratio(_m(74, 91),
                                         _axes(waist_position="mid_high"))
    assert absv == pytest.approx(2.0)
    assert ratio == pytest.approx(2.0 / 4.25)
    assert "ratio" in ev
    # 臀腰差过小 → ratio 回退 None（引擎默认 0.2）
    ratio, _, ev = front_intake_ratio(_m(73, 74), _axes())
    assert ratio is None
    assert "回退" in ev


# -- K3 后中内收 -----------------------------------------------------------------


@pytest.mark.parametrize("waist,hip,axes,expected", [
    (69, 95, {"waist_position": "low"}, 3.5),     # 实战案例 d=26 低腰
    (70, 85, {}, 3.0),                            # d=15
    (70, 90, {}, 3.5),                            # d=20
    (70, 95, {}, 4.5),                            # d=25
    (70, 80, {}, 2.5),                            # d=10
    (65, 95, {}, 4.0),                            # d=30 → §3 封顶移交育克
    (70, 90, {"stretch": "high"}, 3.0),           # 降半档 3.5→3
    (70, 94, {"waist_position": "high"}, 4.8),    # 高腰 +0.5
    (70, 75, {"waist_position": "low"}, 1.5),     # 下限
    (70, 95, {"waist_position": "high"}, 5.0),    # 极限 5
])
def test_k3_golden_x(waist, hip, axes, expected):
    x, ev = back_intake_x(_m(waist, hip), _axes(**axes))
    assert x == pytest.approx(expected)
    assert "K3" in ev


def test_k3_absolute_via_hv():
    assert hip_waist_height_est({"hip": 95.0},
                                _axes(waist_position="low")) == \
        pytest.approx(14.0)
    absv, x, ev = back_intake_abs(_m(69, 95), _axes(waist_position="low"))
    assert x == pytest.approx(3.5)
    assert absv == pytest.approx(14.0 * 3.5 / 15.0)
    assert "H_v" in ev


# -- K4 余量排除法 ---------------------------------------------------------------


def test_k4_case_arithmetic():
    """文档实战案例（W66 H92 中高腰）的渠道分配算式：⑤ = 4.0。"""
    assert yoke_residual(13.0, 1.5, 3.5, 1.0, 3.0) == pytest.approx(4.0)


def test_k4_surplus_no_dart():
    """小差款渠道溢余（residual<0）：无省 + 浅育克警示。"""
    plan = dart_balance(_m(70, 82), _axes(), yoke_on=True)
    assert plan.r_total == pytest.approx(6.0)
    assert plan.channels["①前中"] == pytest.approx(1.25)
    assert plan.channels["②后中"] == pytest.approx(2.55)
    assert plan.channels["③袋口"] == pytest.approx(0.8)
    assert plan.channels["④侧缝目标"] == pytest.approx(3.5)
    assert plan.yoke_takeup == pytest.approx(0.0)
    assert not plan.dart_on
    assert "低于常规带" in plan.yoke_note


def test_k4_no_yoke_single_dart():
    """无育克 H−W=22：缺额 1.1333 → 单省。"""
    plan = dart_balance(_m(70, 92), _axes(), yoke_on=False)
    assert plan.channels["②后中"] == pytest.approx(4.11667, abs=1e-4)
    assert plan.dart_count == 1
    assert plan.dart_width == pytest.approx(1.13333, abs=1e-4)


def test_k4_no_yoke_double_dart():
    """无育克大差（d=26 低腰 curvy）：缺额 3.1333 → 双省 1.5667。"""
    plan = dart_balance(_m(69, 95), _axes(waist_position="low",
                                          body_shape="curvy"), yoke_on=False)
    assert plan.channels["①前中"] == pytest.approx(0.85)
    assert plan.channels["②后中"] == pytest.approx(3.26667, abs=1e-4)
    assert plan.channels["④侧缝目标"] == pytest.approx(4.75)
    assert plan.dart_count == 2
    assert plan.dart_width == pytest.approx(1.56667, abs=1e-4)
    assert "双省" in plan.evidence


def test_k4_stretch_absorption():
    plan = dart_balance(_m(70, 90), _axes(stretch="high"), yoke_on=True)
    assert plan.r_total == pytest.approx(7.5)   # 10×0.75


def test_k4_yoke_transfer_dart():
    """有育克 ⑤>0：约克省载体 = 后腰省三键（back_yoke_steps §3 约克转移量）
    ——单省、宽=⑤ 全额（引擎闭口仅 1 省，多省回退无省提取）；成品无可见省道。"""
    plan = dart_balance(_m(69, 94), _axes(waist_position="low",
                                          body_shape="curvy"), yoke_on=True)
    assert plan.yoke_takeup > 0.5
    assert plan.dart_on
    assert plan.dart_count == 1
    assert plan.dart_width == pytest.approx(plan.yoke_takeup)
    assert "约克省" in plan.evidence
    # ⑤ 超带上限：省口钳 5.0 并披露溢出，不切第二省（闭口仅 1 省）
    big = dart_balance(_m(60, 100), _axes(waist_position="mid",
                                          body_shape="curvy"), yoke_on=True)
    assert big.dart_width <= 5.0 and big.dart_count == 1
    assert "溢出" in big.yoke_note


# -- C 表其余框架键 --------------------------------------------------------------


def test_rise_adjust_bands():
    assert rise_adjust_for(_axes(waist_position="low")) == -2.75
    assert rise_adjust_for(_axes(waist_position="mid_low")) == -1.0
    assert rise_adjust_for(_axes(waist_position="mid")) == 0.75
    assert rise_adjust_for(_axes(waist_position="mid_high")) == 2.25
    assert rise_adjust_for(_axes(waist_position="high")) == 3.75


def test_delta_routing():
    assert resolve_delta(_axes(gender="male"), {})[0] == 0.6
    assert resolve_delta(_axes(body_shape="curvy"), {})[0] == 1.35
    assert resolve_delta(_axes(stretch="high"), {})[0] == 0.4
    assert resolve_delta(_axes(fit_level="loose"), {})[0] == 0.25
    assert resolve_delta(_axes(fit_level="wide"), {})[0] == 0.25
    assert resolve_delta(_axes(), {})[0] == 1.0
    # 男款优先于体型
    assert resolve_delta(_axes(gender="male", body_shape="curvy"), {})[0] == 0.6
    # 大差侧缝前移 +0.5（d=26）
    assert resolve_delta(_axes(), _m(69, 95))[0] == 1.5
    assert resolve_delta(_axes(body_shape="curvy"), _m(69, 95))[0] == 1.85


def test_curvy_waist_balance_rules():
    assert curvy_waist_balance(_axes(body_shape="curvy", fit_level="skinny"))[0] \
        == -0.5
    assert curvy_waist_balance(_axes(body_shape="curvy", fit_level="slim"))[0] \
        == -0.5
    assert curvy_waist_balance(_axes(body_shape="curvy"))[0] == 0.0
    assert curvy_waist_balance(_axes())[0] == 0.0


def test_stretch_and_crotch_adjusts():
    assert stretch_adjusts(_axes(stretch="high"))[:3] == (-0.35, 0.75, 0.75)
    assert stretch_adjusts(_axes(fit_level="loose", stretch="none"))[:3] == \
        (0.25, 1.0, 1.0)
    assert stretch_adjusts(_axes())[:3] == (0.0, 1.0, 1.0)
    assert front_crotch_adjust_for(_axes(fit_level="skinny"))[0] == -0.75
    assert front_crotch_adjust_for(_axes(fit_level="slim"))[0] == -0.4
    assert front_crotch_adjust_for(_axes())[0] == 0.0


# -- merge 三源裁决 --------------------------------------------------------------


def _merged(obs=None, measurements=None, prejudged=None, priors=None,
            hints=None, label=None):
    return merge(obs or Observation(), measurements or {},
                 prejudged or {}, priors if priors is not None
                 else prior_switches(), hints or {}, label)


def test_merge_baseline_prejudged():
    m = _merged(prejudged={"stretch": ("low", "缺省")})
    assert m.axes["stretch"].value == "low"
    assert m.axes["stretch"].source == "预判"
    # 无锚点轴走惯例回退（与模板 _AXIS_FALLBACK 同源）
    assert m.axes["waist_position"].value == "mid"
    assert m.axes["waist_position"].confidence == 0.3
    # 开关默认先验
    assert m.switches["watch_pocket"].value is True
    assert m.switches["back_dart"].value is False
    # fit 枚举轴映射 wide→loose
    m2 = _merged(prejudged={"fit_level": ("wide", "锚")})
    assert m2.enums["fit"].value == "loose"


def test_merge_photo_override_rules():
    obs = Observation(entries={"waistband_type": _entry("curved")})
    m = _merged(obs=obs)
    assert m.enums["waistband_type"].value == "curved"
    assert m.enums["waistband_type"].source == "照片"
    # 低置信拒绝
    obs = Observation(entries={"waistband_type": _entry("curved", conf=0.4)})
    assert _merged(obs=obs).enums["waistband_type"].value == "straight"
    # 无 evidence 拒绝
    obs = Observation(entries={"waistband_type": _entry("curved", ev="  ")})
    assert _merged(obs=obs).enums["waistband_type"].value == "straight"


def test_merge_dictionary_beats_photo():
    """A 表：描述词典命中优先于照片（开关侧）。"""
    obs = Observation(entries={"watch_pocket": _entry(True)})
    m = _merged(obs=obs, hints={"watch_pocket": "off"})
    assert m.switches["watch_pocket"].value is False
    assert m.switches["watch_pocket"].source == "描述"


def test_merge_number_anchor_beats_dictionary():
    """B 表：数字锚点轴（front_rise）词典也不可推翻。"""
    m = _merged(measurements={"front_rise": 22.5},
                prejudged={"waist_position": ("mid_low", "锚点")},
                hints={"waist_position": "high"})
    assert m.axes["waist_position"].value == "mid_low"


def test_merge_unanchored_axis_dictionary_wins():
    m = _merged(prejudged={"stretch": ("low", "缺省")},
                hints={"stretch": "high"})
    assert m.axes["stretch"].value == "high"
    assert m.axes["stretch"].source == "描述"


# -- 依赖链收口 ------------------------------------------------------------------


def test_enforce_dependencies():
    # 贴袋依赖机头：照片关机头但贴袋先验开 → 强制开机头
    m = _merged(obs=Observation(entries={"back_yoke": _entry(False)}))
    notes = enforce_dependencies(m)
    assert m.switches["back_yoke"].value is True
    assert m.switches["back_yoke"].source == "派生"
    assert any("back_yoke" in n for n in notes)
    # 小表袋配套包：强制袋贴
    m = _merged(obs=Observation(entries={"front_pocket_facing": _entry(False)}))
    enforce_dependencies(m)
    assert m.switches["front_pocket_facing"].value is True
    # 主切口关闭 → 下游全关（front_pouch 缺席不强制：不在先验表即引擎默认 False）
    m = _merged(obs=Observation(entries={"front_pocket": _entry(False)}))
    enforce_dependencies(m)
    for k in ("front_pocket_facing", "watch_pocket"):
        assert m.switches[k].value is False
    assert "front_pouch" not in m.switches
    # 独立门襟优先 → fly 强制开
    m = _merged(priors={**prior_switches(), "fly": False})
    enforce_dependencies(m)
    assert m.switches["fly"].value is True


# -- derive_all 总装（回环手算金标） ---------------------------------------------


def _derive(measurements, size_label, hints=None, obs=None):
    prejudged = prejudge_axes(measurements, hints or {}, size_label)
    merged = merge(obs or Observation(), measurements, prejudged,
                   prior_switches(), hints or {}, size_label)
    out = derive_all(measurements, merged, size_label)
    return merged, out


def test_derive_all_curvy_high_rise():
    """W66 H92 fr31 hem50 size27 → high/curvy/slim（手算见模块头注）：
    ①3.5(clamp) ②5.35 ③1.0 ④4.75 R13 → 溢余 → 浅育克无省。"""
    measurements = {"waist": 66.0, "hip": 92.0, "front_rise": 31.0,
                    "hem": 42.0}   # 42/92=0.4565 → slim（触发 curvy 联动 −0.5）
    merged, out = _derive(measurements, 27)
    assert merged.axes["waist_position"].value == "high"
    assert merged.axes["body_shape"].value == "curvy"
    assert merged.axes["fit_level"].value == "slim"
    # 弯曲框架 9
    assert out["front_intake_ratio"].value == pytest.approx(0.538)
    assert out["back_intake"].value == pytest.approx(4.5)
    assert out["delta"].value == 1.85
    assert out["waist_balance"].value == -0.5
    assert out["rise_adjust"].value == 3.75
    assert out["front_crotch_adjust"].value == -0.4
    assert out["crotch_drop_adjust"].value == 0.0
    assert out["knee_adjust"].value == 1.0
    assert out["hem_adjust"].value == 1.0
    assert "front_intake_adjust" not in out          # 微调位留人工
    # K4：溢余 → 无省
    assert merged.switches["back_dart"].value is False
    assert out["front_pocket_dart_width"].value == 1.0
    # 育克高腰带 + takeup 注记
    assert out["back_yoke_cb_dist"].value == 6.5
    assert out["back_yoke_side_dist"].value == 4.0
    assert "takeup≈0.00" in out["back_yoke_cb_dist"].evidence
    assert "低于常规带" in out["back_yoke_cb_dist"].evidence
    # 部件族抽查
    assert out["back_patch_width"].value == 13.5     # 女档
    assert out["back_patch_height"].value == 14.0
    assert out["front_pocket_mouth_bulge"].value == 1.25  # standard 档（真弧高 2.5÷2）
    assert out["watch_pocket_offset_from_side"].value == 2.0
    assert out["fly_width"].value == 4.0
    assert out["belt_loop_count"].value == 5
    assert out["waistband_width"].value == 4.0
    assert out["size_label"].value == "27"
    assert "thigh_limit" not in out
    assert "shrinkage_warp" not in out
    # 枚举透传
    assert out["fit"].value == "slim"
    assert out["front_pocket_mouth_mode"].value == "bulge"


def test_derive_all_no_yoke_double_dart():
    """W69 H95 fr19 size27 → low/curvy + 照片关机头关贴袋 → 双省 1.57。"""
    measurements = {"waist": 69.0, "hip": 95.0, "front_rise": 19.0,
                    "hem": 50.0}
    obs = Observation(entries={"back_yoke": _entry(False),
                               "back_patch": _entry(False)})
    merged, out = _derive(measurements, 27, obs=obs)
    assert merged.axes["waist_position"].value == "low"
    assert merged.switches["back_dart"].value is True
    assert merged.switches["back_dart"].source == "派生"
    assert out["back_dart_count"].value == 2
    assert out["back_dart_width"].value == pytest.approx(1.57)
    assert out["back_dart_length"].value == 10.5
    assert "back_yoke_cb_dist" not in out
    assert "back_patch_width" not in out
    assert out["rise_adjust"].value == -2.75
    assert out["delta"].value == 1.85


def test_derive_all_condition_keys():
    measurements = {"waist": 66.0, "hip": 92.0, "front_rise": 31.0,
                    "hem": 50.0, "thigh": 21.0}
    _, out = _derive(measurements, 27)
    assert out["thigh_limit"].value is True


def test_keymeta_shape():
    km = KeyMeta("delta", 1.0, "查表", 0.6, "依据")
    assert (km.key, km.value, km.source, km.confidence, km.evidence) == \
        ("delta", 1.0, "查表", 0.6, "依据")
