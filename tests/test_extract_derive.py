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
- 有育克 ⑤>0：约克省载体 = back_dart 三键，省数档位与无育克同口径
  （≤2.5 单省 / >2.5 双省摊薄局部折角，2026-09-27 引擎多省级联闭口后对齐；
  「有育克默认无后腰省」指成品形态）；省长 5.25×省宽 clamp[10.5,13] 省角恒定
- 无育克单省：W70 H92 R=11 − ①1.25 − ②4.1167 − ③1.0 − ④3.5 = 1.1333
- 无育克双省：W69 H95 R=13 − ①0.85 − ②3.2667 − ③1.0 − ④4.75 = 3.1333
  → count=2 width=1.5667
- delta 大差：standard 1.0+0.5=1.5；curvy 1.35+0.5=1.85（clamp 2.0 内）

K5 p1 四则（知识库 §五，2026-09-30 袋贴×门襟腰弧重合事故起）：
chord 前腰弦 = W/4 − balance + ③袋口（waist_front_target，弦 ≤ 腰弧安全侧）
- W74 金标（mid_high/straight/高弹/skinny，delta=wb=0.4，③=0.8）：
  chord 18.9；K5-a 插值 8.8+(74−64.3)×1.2/9.7=10.0 封顶上锚；
  bound 18.9−4−3.5−1=10.4 不 clamp → p1=10.0 零漂移
- W66 小码（high/curvy d=26，delta=wb=1.85，③=1.0）：chord 15.65；
  K5-a 插值 9.0 → K5-b bound 15.65−8.5=7.15 floor 0.1 → p1=7.1
- K5-d 照片比例主通道：ratio × chord（物理窗 p1 [0.40,0.65] 钳制、
  conf>0.6 才采纳）；conf≤0.6/无照片回退 K5-a；
  back_patch_width = ratio × 后腰弦（W/4+balance+Σ省口，金标 W74=18.9）
- K5-d 扩展（2026-10-01）p2_drop：ratio × 前浪有效高（front_rise−腰头宽 4；
  物理窗 [0.20,0.40]），金标 W74：0.35×26.0=9.1，兜底腰位分档 mid_high 7.5；
  watch_pocket_width：ratio × 前腰弦（窗 [0.22,0.40]），金标 W74：
  0.30×18.9=5.7（带内不钳），兜底 G 表 5.5
- K5-c 小表袋下界（2026-10-01 袋口宽动态）：ceil0.1(2+w·cos8°+0.5−3.5)，
  w=5.5 兜底 = 4.5 旧常数零漂移、w=6.3 → 5.3；与 K5-b 冲突下界胜出
- watch 宽 G 表带钳制（2026-10-01 实照分母歧义事故起）：换算值 clamp
  [5.0,6.5]，K5-c 下界同取钳后值——raw 4.5→5.0（下界 4.0 非 3.2）、
  raw 7.6→6.5；分母口径 = 单侧腰宽（全宽读数腰斩一半是事故根因）
"""

from __future__ import annotations

import pytest

from agent.extract.derive import (
    KeyMeta,
    back_intake_abs,
    back_intake_x,
    dart_balance,
    dart_length_linked,
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
    waist_balance_for,
    yoke_residual,
)
from agent.extract.families import part_family
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
    ——省数档位与无育克同口径（2026-09-27 引擎 yoke_flow 级联闭口多省化）：
    ⑤ ≤2.5 单省、>2.5 拆双省摊薄局部折角（总转省量不变）；成品无可见省道。"""
    plan = dart_balance(_m(69, 94), _axes(waist_position="low",
                                          body_shape="curvy"), yoke_on=True)
    assert plan.yoke_takeup > 0.5
    assert plan.dart_on
    assert plan.dart_count == 2                      # ⑤=3.5611 > 2.5 → 拆双省
    assert plan.dart_width == pytest.approx(1.78056, abs=1e-4)
    assert plan.dart_width * 2 == pytest.approx(plan.yoke_takeup, abs=1e-4)
    assert "约克省" in plan.evidence
    # ⑤ 超带上限：省口钳 5.0（双省各 2.5）并披露溢出
    big = dart_balance(_m(60, 100), _axes(waist_position="mid",
                                          body_shape="curvy"), yoke_on=True)
    assert big.dart_width == 2.5 and big.dart_count == 2
    assert "溢出" in big.yoke_note


def test_k4_dart_length_linked():
    """省长随省宽联动（省角恒定 ≈5.4°）：5.25×省宽 clamp[10.5,13]——
    常规窄省触下限 10.5、宽省加长、双省顶格 2.5 钳 13。"""
    assert dart_length_linked(1.0)[0] == 10.5
    assert dart_length_linked(2.0)[0] == 10.5
    assert dart_length_linked(2.2)[0] == 11.55
    assert dart_length_linked(2.5)[0] == 13.0     # 5.25×2.5=13.125 钳 13


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


def test_waist_balance_follows_delta():
    """臀腰同调（2026-09-29 用户口径）：waist_balance 恒 = delta 终值——
    五档路由 + 大差加成全档同值；旧 curvy 联动 −0.5 桩退役（症状侧由
    balance.py 塌零守卫接管，score 只警不改）。"""
    for axes in (_axes(gender="male"), _axes(body_shape="curvy"),
                 _axes(stretch="high"), _axes(fit_level="loose"),
                 _axes(), _axes(body_shape="curvy", fit_level="skinny")):
        dv, dev = resolve_delta(axes, {})
        assert waist_balance_for(dv, dev)[0] == dv
    # 大差侧缝前移 +0.5 同步跟随（standard 1.5 / curvy 1.85）
    dv, _ = resolve_delta(_axes(), _m(69, 95))
    assert waist_balance_for(dv, "")[0] == 1.5
    dv, _ = resolve_delta(_axes(body_shape="curvy"), _m(69, 95))
    assert waist_balance_for(dv, "")[0] == 1.85
    # evidence 链带同调口径 + delta 溯源
    _, ev = waist_balance_for(1.85, "curvy 大差 1.85")
    assert "臀腰同调" in ev and "1.85" in ev


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
                    "hem": 42.0}   # 42/92=0.4565 → slim
    merged, out = _derive(measurements, 27)
    assert merged.axes["waist_position"].value == "high"
    assert merged.axes["body_shape"].value == "curvy"
    assert merged.axes["fit_level"].value == "slim"
    # 弯曲框架 9
    assert out["front_intake_ratio"].value == pytest.approx(0.538)
    assert out["back_intake"].value == pytest.approx(4.5)
    assert out["delta"].value == 1.85
    assert out["waist_balance"].value == 1.85   # 臀腰同调 = delta（2026-09-29）
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


# -- K5 p1 四则（知识库 §五，2026-09-30） ------------------------------------------


def _m74():
    # 金标 case female_high_sk_29 尺寸：mid_high/straight/高弹/skinny
    return {"waist": 74.0, "hip": 91.0, "knee": 44.0, "hem": 34.0,
            "front_rise": 30.0, "back_rise": 38.0, "outseam": 102.0,
            "thigh": 58.0}


def _m66():
    # curvy 高腰小码（d=26 → ③=1.0、delta=wb=1.85）
    return {"waist": 66.0, "hip": 92.0, "front_rise": 31.0, "hem": 42.0}


def test_k5_p1_golden_anchors():
    """W74 金标零漂移（K5-a 封顶上锚 10.0、bound 10.4 不 clamp）；
    W66 小码 K5-a 插值 9.0 被 K5-b 腰弧预算 clamp 压至 7.1（弦 15.65−8.5
    = 7.15 floor 0.1——2026-09-30 袋贴×门襟腰弧重合事故的 extract 侧修复）。"""
    _, out = _derive(_m74(), 29, hints={"stretch": "high"})
    p1 = out["front_pocket_p1_dist"]
    assert p1.value == 10.0                       # 金标 example 值零漂移
    assert "K5-a 腰围锚点插值" in p1.evidence
    assert "clamp" not in p1.evidence             # bound 10.4 > 10.0
    _, out = _derive(_m66(), 27)
    p1 = out["front_pocket_p1_dist"]
    assert p1.value == 7.1
    assert "K5-a" in p1.evidence and "K5-b 腰弧预算 clamp" in p1.evidence
    assert "15.65" in p1.evidence                 # 弦值入证
    assert "K5-c" not in p1.evidence              # 7.1 ≥ 4.5 不踩小表袋下界


def test_k5_p1_no_clamp_without_separate_fly():
    """连裁门襟不占腰弧（fly_separate=False 照片关）：W66 不 clamp 取插值
    9.0；W=60 低于下锚 64.3 取 8.8（无实测锚披露）。"""
    obs = Observation(entries={"fly_separate": _entry(False)})
    _, out = _derive(_m66(), 27, obs=obs)
    p1 = out["front_pocket_p1_dist"]
    assert p1.value == 9.0
    assert "K5-a" in p1.evidence and "K5-b" not in p1.evidence
    _, out = _derive({"waist": 60.0, "hip": 86.0}, 24, obs=obs)
    p1 = out["front_pocket_p1_dist"]
    assert p1.value == 8.8
    assert "下锚" in p1.evidence and "无实测锚" in p1.evidence


def test_k5_part_family_unit():
    """part_family 直调（extra 注入）：K5-b 预算 clamp / K5-c 下界 / 冲突
    下界胜出 / K5-a 端点下锚与封顶，逐分支金标（W74 插值 10.0 起步）。"""
    axes = {"waist_position": "mid", "gender": "female",
            "body_shape": "standard", "fit_level": "regular", "stretch": "low"}

    def _p1(meas, extra=None):
        return part_family("front_pocket", axes, {}, meas,
                           extra=extra)["front_pocket_p1_dist"]

    v, ev = _p1({"waist": 74.0}, {"chord": 13.5, "fly_sep": True,
                                  "facing_on": True, "watch_on": True})
    assert v == 5.0 and "K5-b" in ev               # 13.5−8.5=5.0 整档无尘
    v, ev = _p1({"waist": 74.0}, {"chord": 13.0, "fly_sep": True,
                                  "facing_on": True, "watch_on": True})
    assert v == 4.5 and "K5-c" not in ev           # 4.5 不低于下界
    v, ev = _p1({"waist": 74.0}, {"chord": 12.0, "fly_sep": True,
                                  "facing_on": True, "watch_on": True})
    assert v == 4.5 and "K5-c" in ev and "冲突" in ev   # bound 3.5 < 4.5 下界胜出
    v, ev = _p1({"waist": 74.0}, {"chord": 12.0, "fly_sep": True,
                                  "facing_on": True, "watch_on": False})
    assert v == 3.5 and "K5-c" not in ev           # 无小表袋不设下界
    v, ev = _p1({"waist": 64.3})
    assert v == 8.8 and "下锚" in ev               # 端点=下锚
    v, ev = _p1({"waist": 80.0})
    assert v == 10.0 and "封顶" in ev              # 超上锚封顶（无实测锚）


def test_k5_ratio_primary_channel():
    """K5-d 照片比例主通道：ratio × 前腰弦直接作带值（K5-a 不参与）；
    W66 换算 8.6 仍被 K5-b 压制至 7.1——两通道统一防重合。"""
    obs = Observation(entries={
        "ratio_front_pocket_p1": _entry(0.55, 0.9, "约 55% 目测")})
    _, out = _derive(_m74(), 29, hints={"stretch": "high"}, obs=obs)
    p1 = out["front_pocket_p1_dist"]
    assert p1.value == 10.4                        # 0.55×18.9=10.395 → 10.4
    assert "K5-d" in p1.evidence and "0.55" in p1.evidence
    assert "18.9" in p1.evidence                   # 弦值入证
    assert "K5-b" not in p1.evidence               # 10.4 ≤ bound 10.4
    _, out = _derive(_m66(), 27, obs=obs)
    p1 = out["front_pocket_p1_dist"]
    assert p1.value == 7.1                         # 8.6 被 K5-b clamp 压制
    assert "K5-d" in p1.evidence and "K5-b" in p1.evidence


def test_k5_ratio_adoption_gates():
    """采纳门槛：conf≤0.6 不采纳回退 K5-a；出物理窗 [0.40,0.65] 钳窗再算。"""
    obs = Observation(entries={
        "ratio_front_pocket_p1": _entry(0.55, conf=0.5, ev="拿不准")})
    _, out = _derive(_m74(), 29, hints={"stretch": "high"}, obs=obs)
    p1 = out["front_pocket_p1_dist"]
    assert p1.value == 10.0 and "K5-d" not in p1.evidence
    obs = Observation(entries={
        "ratio_front_pocket_p1": _entry(0.30, 0.9, "目测偏小")})
    _, out = _derive(_m74(), 29, hints={"stretch": "high"}, obs=obs)
    p1 = out["front_pocket_p1_dist"]
    assert p1.value == 7.6                         # 0.40×18.9=7.56 → 7.6
    assert "0.40" in p1.evidence                   # 钳后比例入证


def test_k5_ratio_back_patch_width():
    """K5-d 后贴袋宽：ratio × 后腰弦（W/4+balance+Σ省口；金标 W74 无省
    =18.9）覆盖 G 表性别档；高度不随比例。"""
    obs = Observation(entries={
        "ratio_back_patch_width": _entry(0.62, 0.9, "约 62% 目测")})
    _, out = _derive(_m74(), 29, hints={"stretch": "high"}, obs=obs)
    w = out["back_patch_width"]
    assert w.value == 11.7                         # 0.62×18.9=11.718 → 11.7
    assert "K5-d" in w.evidence and "后腰弦" in w.evidence
    assert out["back_patch_height"].value == 14.0  # 高度走 G 表不动
    _, out = _derive(_m74(), 29, hints={"stretch": "high"})
    assert out["back_patch_width"].value == 13.5   # 无比例 → G 表女档兜底


def test_k5_ratio_p2_drop_channel():
    """K5-d p2_drop（2026-10-01 扩展）：比例 × 前浪有效高（前浪 30 − 腰头宽
    4 = 26.0）覆盖腰位分档兜底；conf≤0.6 回退分档、出物理窗 [0.20,0.40]
    钳窗再算。金标：0.35×26.0=9.1；0.50 钳 0.40×26.0=10.4。"""
    obs = Observation(entries={
        "ratio_front_pocket_p2": _entry(0.35, 0.9, "约 35% 目测")})
    _, out = _derive(_m74(), 29, hints={"stretch": "high"}, obs=obs)
    p2 = out["front_pocket_p2_drop"]
    assert p2.value == 9.1
    assert "K5-d" in p2.evidence and "0.35" in p2.evidence
    assert "26.0" in p2.evidence                    # 前浪有效高入证
    obs = Observation(entries={
        "ratio_front_pocket_p2": _entry(0.35, conf=0.5, ev="拿不准")})
    _, out = _derive(_m74(), 29, hints={"stretch": "high"}, obs=obs)
    p2 = out["front_pocket_p2_drop"]
    assert p2.value == 7.5 and "K5-d" not in p2.evidence   # mid_high 分档兜底
    obs = Observation(entries={
        "ratio_front_pocket_p2": _entry(0.50, 0.9, "目测偏深")})
    _, out = _derive(_m74(), 29, hints={"stretch": "high"}, obs=obs)
    p2 = out["front_pocket_p2_drop"]
    assert p2.value == 10.4 and "0.40" in p2.evidence      # 钳后比例入证


def test_k5_ratio_watch_width_channel():
    """K5-d 小表袋宽：比例 × 前腰弦覆盖 G 表 5.5；无比例回退 G 表同值
    （evidence 分通道）。金标 W74：0.30×18.9=5.67→5.7（G 表带 5~6.5 内
    不钳，带外钳制见 test_k5_watch_band_clamp）；K5-c 动态下界
    ceil(2+5.7·cos8°+0.5−3.5)=4.7 < p1 10.0 不触发。"""
    obs = Observation(entries={
        "ratio_watch_pocket_width": _entry(0.30, 0.9, "约 30% 目测")})
    _, out = _derive(_m74(), 29, hints={"stretch": "high"}, obs=obs)
    wv = out["watch_pocket_width"]
    assert wv.value == 5.7
    assert "K5-d" in wv.evidence and "18.9" in wv.evidence
    assert "钳" not in wv.evidence
    p1 = out["front_pocket_p1_dist"]
    assert p1.value == 10.0 and "K5-c" not in p1.evidence  # 动态下界 4.7 不动
    _, out = _derive(_m74(), 29, hints={"stretch": "high"})
    wv = out["watch_pocket_width"]
    assert wv.value == 5.5 and "K5-d" not in wv.evidence   # G 表兜底同值


def test_k5_watch_dynamic_floor_unit():
    """K5-c 动态下界（袋口宽随 K5-d 可变）：part_family 直调 watch_w=6.3 →
    下界 ceil0.1(2+6.3·cos8°+0.5−3.5)=5.3；K5-b bound 3.5 < 5.3 冲突
    下界胜出（w=5.5 兜底时 = 4.5 旧常数，见 test_k5_part_family_unit）。"""
    axes = {"waist_position": "mid", "gender": "female",
            "body_shape": "standard", "fit_level": "regular", "stretch": "low"}
    v, ev = part_family("front_pocket", axes, {}, {"waist": 74.0},
                        extra={"chord": 12.0, "fly_sep": True,
                               "facing_on": True, "watch_on": True,
                               "watch_w": 6.3})["front_pocket_p1_dist"]
    assert v == 5.3
    assert "K5-c" in ev and "5.3" in ev and "冲突" in ev


def test_k5_watch_band_clamp():
    """K5-d 小表袋宽换算值过 G 表带 5.0~6.5 钳制（2026-10-01 实照事故：分母
    被读成整条腰头全宽→比例腰斩→3.8cm 漏网）。金标 W74：0.24×18.9=4.536→
    4.5 → 钳 5.0（披露原值）；0.50 钳物理窗 0.40×18.9=7.6 → 钳 6.5。"""
    obs = Observation(entries={
        "ratio_watch_pocket_width": _entry(0.24, 0.9, "约 24% 目测")})
    _, out = _derive(_m74(), 29, hints={"stretch": "high"}, obs=obs)
    wv = out["watch_pocket_width"]
    assert wv.value == 5.0
    assert "= 4.5" in wv.evidence and "钳 5.0" in wv.evidence
    p1 = out["front_pocket_p1_dist"]
    assert p1.value == 10.0 and "K5-c" not in p1.evidence
    # 下界按钳后 5.0 算 = ceil0.1(2+5.0·cos8°+0.5−3.5)=4.0 < 10.0 不触发
    obs = Observation(entries={
        "ratio_watch_pocket_width": _entry(0.50, 0.9, "目测偏大")})
    _, out = _derive(_m74(), 29, hints={"stretch": "high"}, obs=obs)
    wv = out["watch_pocket_width"]
    assert wv.value == 6.5
    assert "0.40" in wv.evidence and "钳 6.5" in wv.evidence


def test_k5_watch_band_floor_consistency():
    """K5-c 动态下界取 G 表带钳后值（与 watch 族宽度同源防漂）：raw 4.2 →
    按 5.0 算下界 ceil0.1(2+4.9513+0.5−3.5)=4.0（raw 直算仅 3.2）；K5-a
    W=64.3 → 8.8 → K5-b chord 11 bound 2.5 → 下界 4.0 胜出。"""
    axes = {"waist_position": "mid", "gender": "female",
            "body_shape": "standard", "fit_level": "regular", "stretch": "low"}
    v, ev = part_family("front_pocket", axes, {}, {"waist": 64.3},
                        extra={"chord": 11.0, "fly_sep": True,
                               "facing_on": True, "watch_on": True,
                               "watch_w": 4.2})["front_pocket_p1_dist"]
    assert v == 4.0
    assert "K5-c" in ev and "4.0" in ev
