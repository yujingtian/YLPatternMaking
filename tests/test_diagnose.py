"""金标测试：flows/diagnose.py 运行期异常二分归因（web 校验报红二期，
2026-09-29）。

手工演算（真引擎，size_female_165 基础尺寸 waist=68 hip=91 knee=44
hem=34 front_rise=25 back_rise=33 outseam=102）：
- back_rise=50 其余默认 -> 引擎在 waistline_horizontal_span 守卫炸
  （腰长 <= 高差绝对值，原为 math domain error 盲区）；唯一 touched 键
  back_rise，solo 探测回 33 后可生成 -> 归因 back_rise、测量类无修复；
- waist/hip/outseam 同时偏离默认 + back_rise=50 -> solo 轮 3 次探测
  （waist、hip 先败）后命中 back_rise；
- 全默认 + 伪消息 -> touched 空 -> 0 探测直接兜底 Issue(param=None)；
- max_probes=1 + 多 touched -> 首探测后 _Abort -> 兜底（消息保留）；
- monkeypatch run_with_thigh_closure 按「键集含 A+B 才成功」 ->
  贪心累积 + 后向最小化返回 A、B 双罪魁（选项类各带恢复默认修复）；
- norm_json：Enum->str、tuple<->list、sa dataclass->dict、68==68.0。
"""

from ylpattern.flows.diagnose import _touched, diagnose_runtime
from ylpattern.params import norm_json
from ylpattern.params.options import WaistbandType
from ylpattern.params.validate import FALLBACK_MEASUREMENTS

BASE_M = dict(waist=68, hip=91, knee=44, hem=34,
              front_rise=25, back_rise=33, outseam=102)
BAD_RISE_M = dict(BASE_M, back_rise=50)


def test_solo_attribution_real_engine():
    issues = diagnose_runtime(BAD_RISE_M, {}, "ValueError: 腰长 17.00")
    assert len(issues) == 1
    i = issues[0]
    assert i.param == "back_rise"
    assert i.level == "error"
    assert "已定位：单独恢复默认后可生成" in i.message
    assert i.fixes == ()          # 测量类罪魁不给修复（保用户基码）


def test_solo_after_multiple_touched():
    md = dict(BASE_M, waist=70, hip=95, back_rise=50, outseam=104)
    issues = diagnose_runtime(md, {}, "ValueError: x")
    assert [i.param for i in issues] == ["back_rise"]


def test_empty_touched_falls_back():
    issues = diagnose_runtime(BASE_M, {}, "KeyError: bug")
    assert len(issues) == 1
    assert issues[0].param is None
    assert issues[0].message == "引擎生成失败：KeyError: bug"
    assert issues[0].fixes == ()


def test_probe_budget_abort_falls_back():
    md = dict(BASE_M, waist=70, hip=95, back_rise=50, outseam=104)
    issues = diagnose_runtime(md, {}, "ValueError: x", max_probes=1)
    assert issues[0].param is None
    assert "ValueError: x" in issues[0].message


def test_joint_culprits_full_revert_then_minimize(monkeypatch):
    """联合故障：仅当 waist、back_intake 同时回默认才可生成 -> 全量回退
    验证 + 后向最小化；旁观键 delta（改不改都行）被剔除、不误报。"""
    import ylpattern.flows.diagnose as dz

    def fake_run(m, o):
        if abs(m.waist - FALLBACK_MEASUREMENTS["waist"]) > 1e-9 \
                or abs(o.back_intake - 2.5) > 1e-9:
            raise ValueError("joint failure")
        return None, ""

    monkeypatch.setattr(dz, "run_with_thigh_closure", fake_run)
    # touched：waist=70（测量）、delta=1.5（选项旁观）、back_intake=3.5（选项）
    issues = diagnose_runtime(dict(BASE_M, waist=70),
                              {"delta": 1.5, "back_intake": 3.5},
                              "ValueError: joint failure")
    params = [i.param for i in issues]
    assert set(params) == {"waist", "back_intake"}
    # 选项罪魁带恢复默认修复；测量罪魁不带
    fixes = {i.param: i.fixes for i in issues}
    assert fixes["back_intake"][0].value == 2.5
    assert fixes["waist"] == ()
    assert all("与其余参数组合导致" in i.message for i in issues)


def test_option_culprit_carries_revert_fix(monkeypatch):
    """单选项罪魁：回默认即可生成 -> 带恢复默认按钮（值经 norm_json）。"""
    import ylpattern.flows.diagnose as dz

    def fake_run(m, o):
        if o.delta != 1.0:
            raise ValueError("delta bomb")
        return None, ""

    monkeypatch.setattr(dz, "run_with_thigh_closure", fake_run)
    issues = diagnose_runtime(BASE_M, {"delta": 1.9}, "ValueError: delta bomb")
    assert [i.param for i in issues] == ["delta"]
    f = issues[0].fixes[0]
    assert (f.param, f.value, f.scope) == ("delta", 1.0, "options")
    assert f.label == "恢复默认"


def test_switch_masking_leaf_param_real_engine():
    """开关遮蔽叶子参数（真引擎，2026-09-29）：cb_dist=30 越链长炸 ->
    回 back_yoke 开关也能「修好」（跳过特征执行），但真凶是叶子参数——
    开关最后探，solo 首中 cb_dist、带恢复默认 4.0，不误归因开关。"""
    issues = diagnose_runtime(
        BASE_M, {"back_yoke": True, "back_yoke_cb_dist": 30},
        "ValueError: 量取距离 30 超过几何体链总长")
    assert [i.param for i in issues] == ["back_yoke_cb_dist"]
    f = issues[0].fixes[0]
    assert (f.param, f.value, f.label) == ("back_yoke_cb_dist", 4.0, "恢复默认")


def test_switch_genuine_culprit_still_found(monkeypatch):
    """真凶确是开关：叶子全败后开关命中（不被「开关最后探」饿死）。"""
    import ylpattern.flows.diagnose as dz

    def fake_run(m, o):
        if o.front_pocket:
            raise ValueError("pocket bomb")
        return None, ""

    monkeypatch.setattr(dz, "run_with_thigh_closure", fake_run)
    issues = diagnose_runtime(
        BASE_M, {"delta": 1.5, "front_pocket": True}, "ValueError: pocket bomb")
    assert [i.param for i in issues] == ["front_pocket"]
    assert issues[0].fixes[0].value is False


def test_norm_json():
    assert norm_json(WaistbandType.CURVED) == "curved"
    assert norm_json((1.0, 2.0)) == [1.0, 2.0] == norm_json([1.0, 2.0])
    from ylpattern.params import PatternOptions
    sa = PatternOptions().waistband_seam_allowances
    assert norm_json(sa) == {"top": 1.0, "bottom": 1.0,
                             "left_end": 1.2, "right_end": 1.0}
    assert norm_json(68) == norm_json(68.0)   # == 语义天然放行
    assert norm_json(True) is True


def test_touched_ignores_unknown_option_keys():
    ts = _touched(BASE_M, {"nope": 1, "delta": 1.0})
    # delta 恰为默认值 -> 不 touched；未知键无从回默认 -> 跳过
    assert ts == []
    ts2 = _touched(BASE_M, {"delta": 1.5, "nope": 1})
    assert ts2 == [("delta", "options")]
