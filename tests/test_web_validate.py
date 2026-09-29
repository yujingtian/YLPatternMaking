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


# ---------- 一键修复内容金标（2026-09-29 二期） ----------

def _fx(issue):
    return [(f.param, f.value, f.label, f.scope) for f in issue.fixes]


def test_cross_fixes_content():
    """cross 五类规则双按钮逐字段：开依赖（保特征）/ 关自身（弃特征）；
    毗围第二条改录常规 thigh（scope=measurements）。mode 规则与袋贴规则
    互斥触发（mode 需 facing=False、袋贴需 facing=True），分两次构造。"""
    m = Measurements(**BASE_M)
    a = PatternOptions(front_pouch=True, watch_pocket=True,
                       back_patch=True, thigh_limit=True)
    by = {i.param: i for i in cross_issues(m, a)}
    assert set(by) == {"front_pouch", "watch_pocket", "watch_pocket_mode",
                       "back_patch", "thigh_limit"}
    assert _fx(by["front_pouch"]) == [
        ("front_pocket", True, "开启前口袋主切口", "options"),
        ("front_pouch", False, "关闭袋布", "options")]
    assert _fx(by["watch_pocket"]) == [
        ("front_pocket", True, "开启前口袋主切口", "options"),
        ("watch_pocket", False, "关闭小表袋", "options")]
    # mode 第二方向不能回默认（默认即 facing_intersect）/不能改 custom
    assert _fx(by["watch_pocket_mode"]) == [
        ("front_pocket_facing", True, "开启袋贴", "options"),
        ("watch_pocket", False, "关闭小表袋", "options")]
    assert _fx(by["back_patch"]) == [
        ("back_yoke", True, "开启后机头", "options"),
        ("back_patch", False, "关闭后贴袋", "options")]
    assert _fx(by["thigh_limit"]) == [
        ("thigh_limit", False, "关闭毗围闭环", "options"),
        ("thigh", 58, "录入常规大腿围 58cm", "measurements")]
    b = PatternOptions(front_pocket_facing=True)
    facing = {i.param: i for i in cross_issues(m, b)}
    assert _fx(facing["front_pocket_facing"]) == [
        ("front_pocket", True, "开启前口袋主切口", "options"),
        ("front_pocket_facing", False, "关闭袋贴", "options")]


def test_measurement_relation_fix_value():
    # 臀围 <= 腰围：归因 hip -> 替代值 = 腰围+3（68+3=71，最小满足）
    issues = build_issues({**BASE_M, "hip": 60}, {})
    hip = next(i for i in issues if i.param == "hip")
    assert _fx(hip) == [("hip", 71, "臀围改为 腰围+3cm", "measurements")]


def test_measurement_nonpositive_fix_fallback():
    # 必填键 <=0：给 FALLBACK 常规值（waist -> 68）
    issues = build_issues({**BASE_M, "waist": 0}, {})
    w = next(i for i in issues if i.param == "waist")
    assert _fx(w) == [("waist", 68, "改为常规值 68cm", "measurements")]


def test_option_range_fix_reverts_default():
    # 越界选项：单按钮恢复引擎默认（delta 默认 1.0）
    issues = build_issues(BASE_M, {"delta": 9.9})
    assert _fx(issues[0]) == [("delta", 1.0, "恢复引擎默认", "options")]


def test_value_range_table_catches_absurd_and_fixes():
    """量级守卫表（2026-09-29「很大的值不标红」统一审计）：watch_pocket_width=50
    此前只有 <=0 守卫——大值静默进引擎，facing_intersect 缺口组合下归因漂到
    watch_pocket 开关、字段本身永不红。表驱动上界后构造期直接归因本键
    + 恢复默认按钮（7.5）。"""
    issues = build_issues(BASE_M, {"watch_pocket_width": 50})
    assert issues[0].param == "watch_pocket_width"
    assert "小表袋口宽" in issues[0].message
    assert _fx(issues[0]) == [
        ("watch_pocket_width", 7.5, "恢复引擎默认", "options")]


def test_value_range_closure_negative_arc_dx_allowed():
    """毗围闭环解算会把 outseam_arc_dx 解成负值（实测 -0.44，closure.py
    replace 写回）——闭合对称区间是解算产物通道，不能按「常规 0.1~0.2」
    单侧拦负；90° 旋转同属几何合法（金标 rotation 用例）。"""
    PatternOptions(outseam_arc_dx=-0.44, back_outseam_arc_dx=-0.42,
                   front_patch_rotate_deg=90.0, watch_pocket_rotate_deg=-90.0)


def test_unknown_option_key_no_fixes():
    # 未知键无从回默认 -> 不给修复按钮
    issues = build_issues(BASE_M, {"no_such_param": 1})
    assert issues[0].fixes == ()


def test_attribution_no_false_positive_on_relation_pairs():
    """归因路径键序无关（2026-09-29 二遍式延迟重试）：fly_width 越界触发
    逐键归因时，shape=custom 先于 custom_points 入列的前缀构造会因角点
    还是默认空元组假败——第一遍不报、二遍带完整伙伴键重试，只归因真凶
    fly_width，不连带误报两个 custom「得到 0 个」。"""
    pts = [[0, 0], [14, 0], [14, 16], [0, 16]]
    edges = [[0, 0], [0, 0], [0, 0], [0, 0]]
    issues = build_issues(BASE_M, {
        "front_patch": True, "back_patch": True, "back_yoke": True,
        "front_patch_shape": "custom", "front_patch_custom_points": pts,
        "front_patch_custom_edges": edges,
        "back_patch_shape": "custom", "back_patch_custom_points": pts,
        "back_patch_custom_edges": edges,
        "fly_width": 30,
    })
    assert [i.param for i in issues] == ["fly_width"]
    assert "3.5~4.2" in issues[0].message


def test_attribution_reports_genuinely_broken_custom():
    # 真坏的 custom（角点真的少于 3 个）：二遍重试后仍败 -> 照常归因 shape
    issues = build_issues(BASE_M, {
        "front_patch": True,
        "front_patch_shape": "custom",
        "front_patch_custom_points": [[0, 0], [1, 0]],
    })
    assert [i.param for i in issues] == ["front_patch_shape"]
    assert "至少 3 个" in issues[0].message
