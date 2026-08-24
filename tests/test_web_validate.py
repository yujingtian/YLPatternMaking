"""金标测试：params/validate.py 构造期归因 + 跨选项前置条件（web 校验层）。

手工演算（size_female_165 基础尺寸 waist=68 hip=91 knee=44 hem=34
front_rise=25 back_rise=33 outseam=102）：
- 袋布开口袋关 -> Issue(param="front_pouch", error)
- 小表袋相交模式袋贴关 -> Issue(param="watch_pocket_mode", error)
- 后贴袋无机头 -> Issue(param="back_patch", error)
- 毗围开但 thigh=0 -> Issue(param="thigh_limit", error)
- 连裁+独立门襟同开 -> warning 级
- delta=9.9 越界（post_init [0,2.0]）-> Issue(param="delta") 且归因到键
- 未知选项键 -> Issue(param=该键, "未知选项")
"""

from ylpattern.params import build_issues, cross_issues
from ylpattern.params import Measurements, PatternOptions

BASE_M = dict(waist=68, hip=91, knee=44, hem=34,
              front_rise=25, back_rise=33, outseam=102)


def test_valid_no_issues():
    assert build_issues(BASE_M, {"delta": 1.0, "front_pocket": True}) == []


def test_pouch_requires_pocket():
    issues = build_issues(BASE_M, {"front_pouch": True})
    assert [i.param for i in issues] == ["front_pouch"]
    assert issues[0].level == "error"


def test_watch_pocket_facing_intersect_requires_facing():
    issues = build_issues(BASE_M, {"front_pocket": True,
                                   "watch_pocket": True})
    # mode 默认 facing_intersect，袋贴未开 -> 报 mode 依赖
    assert [i.param for i in issues] == ["watch_pocket_mode"]


def test_back_patch_requires_yoke():
    issues = build_issues(BASE_M, {"back_patch": True})
    assert [i.param for i in issues] == ["back_patch"]


def test_thigh_limit_requires_thigh_measurement():
    issues = build_issues(BASE_M, {"thigh_limit": True})
    assert [i.param for i in issues] == ["thigh_limit"]


def test_fly_both_true_no_warning():
    # fly/fly_separate 双真：引擎 fly_separate 优先生效，web 下拉已强制
    # 互斥（双真仅模板载入出现），不再报冗余 warning（2026-08 移除）
    issues = build_issues(BASE_M, {"fly": True, "fly_separate": True})
    assert issues == []


def test_field_error_attributed_to_key():
    issues = build_issues(BASE_M, {"delta": 9.9})
    assert [i.param for i in issues] == ["delta"]
    assert "0~2.0" in issues[0].message


def test_unknown_option_key():
    issues = build_issues(BASE_M, {"no_such_param": 1})
    assert [i.param for i in issues] == ["no_such_param"]
    assert "未知选项" in issues[0].message


def test_measurement_relation_error_reported():
    # 臀围 <= 腰围：Measurements.__post_init__ 抛 ValueError，逐键归因到 hip
    issues = build_issues({**BASE_M, "hip": 60}, {})
    assert any(i.param == "hip" for i in issues)


def test_cross_issues_direct():
    m = Measurements(**BASE_M)
    o = PatternOptions(front_pocket_facing=True, back_patch=True)
    issues = cross_issues(m, o)
    # back_yoke=False -> 袋贴报前口袋依赖、后贴袋报机头依赖
    assert {(i.param, i.level) for i in issues} == {
        ("front_pocket_facing", "error"), ("back_patch", "error")}
