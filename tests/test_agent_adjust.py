"""调版映射金标（2026-09-27，§10.9.2）：映射面生成 + 解析纯函数 + 会话重放
+ run_turn 集成。

手工演算口径写死在用例里；FakeVLM 单队列同轮出队顺序铁律：
**映射 -> S1 补漏 -> S2**（run_turn 在 user 事件 append 之前跑映射）。
交卷后的纯文字轮恒耗一条映射响应——空调整 canned _EMPTY_ADJ。
"""

from __future__ import annotations

import json

import pytest

from agent.converse import _build_delivery, run_turn
from agent.extract.adjust import (ADJUST_TABLE, AdjustResult,
                                  adjust_view_from_payload, build_adjust_prompt,
                                  gate_pass, map_adjustment, resolve_adjust)
from agent.extract.params_meta import (EXCLUDED, GROUP_ORDER, META,
                                       _default_value, adjust_surface,
                                       scalar_field_names)
from agent.extract.provider import FakeVLM
from agent.session import Event, Ledger, Session, replay

_DESC = ("女款高腰小脚牛仔裤，腰围74 臀围91 膝围44 脚口34 前浪25 后浪33 "
         "裤长102 大腿围58，微弹面料，五袋款带小表袋裤耳")

_EMPTY_ADJ = '{"adjustments": [], "note": ""}'
_ADJ_DEEP = json.dumps({
    "adjustments": [{"key": "front_pocket_mouth_depth", "level": "deep",
                     "evidence": "口袋弧深一点"}],
    "note": "袋口弧线加深"}, ensure_ascii=False)


def _view(**over) -> dict:
    """默认打底的映射面视图 + 指定覆写（gate 基线用）。"""
    return adjust_view_from_payload(over)


# -- 映射面生成（漂移金标 = 与引擎标量参数同步的结构保证） ------------------------

def test_surface_drift_golden():
    """set(META) == {PatternOptions 标量字段} − EXCLUDED：引擎加参数未登记
    即红（登记 = 补一行 label/group）；locked ⊆ META；group 全部在册。"""
    assert set(META) == scalar_field_names() - set(EXCLUDED)
    locked = {k for k, m in META.items() if m.locked}
    assert locked <= set(META)
    assert {m.group for m in META.values()} <= set(GROUP_ORDER)


def test_surface_spot_checks():
    """表面抽查：虚键落点/档位值、hint 通道 ⊆ merge 消费面、
    override 数值键咨询带两端不越引擎硬校验。"""
    s = adjust_surface()
    v = s["front_pocket_mouth_depth"]
    assert v.target == "front_pocket_mouth_bulge"
    assert v.level_values == (0.75, 1.25, 1.75)
    assert s["front_pocket"].channel == "hint"
    assert s["waistband_type"].levels == ("straight", "curved")
    assert s["back_dart_count"].levels == ("1", "2")
    assert s["fit"].ordinal is True
    assert s["front_pocket_mouth_bulge"].locked is True
    # 默认值自省：表面默认 == 引擎字段默认
    for k, spec in s.items():
        if not spec.target:
            assert spec.default == _default_value(k)
    # hint 通道键必须在 merge 的 hint 消费面内（否则种子进不去）
    from agent.extract.prejudge import prior_switches
    from agent.extract.schema import ENUM_DEFAULTS
    consume = ({k for k in ENUM_DEFAULTS if k != "front_pocket_mouth_depth"}
               | set(prior_switches()))
    for k, spec in s.items():
        if spec.channel == "hint":
            assert k in consume, k
    # override 数值键 lo/hi 两端单键构造不抛（咨询带不越硬校验）
    from ylpattern.params.options import PatternOptions
    for k, spec in s.items():
        if spec.target or spec.levels or spec.locked or not spec.step:
            continue
        PatternOptions.from_dict({k: spec.lo})
        PatternOptions.from_dict({k: spec.hi})


def test_adjust_view_from_payload():
    """默认打底 + payload 覆写 + 表外键忽略。"""
    view = _view(front_pocket=True, front_pocket_mouth_bulge=1.75,
                 not_a_table_key=99)
    assert view["front_pocket"] is True
    assert view["front_pocket_mouth_bulge"] == 1.75
    assert "not_a_table_key" not in view
    assert view["waistband_type"] == "straight"        # 未给 -> 引擎默认


def test_gate_pass_three_forms():
    assert gate_pass(None, {}) is True
    assert gate_pass("front_pocket", {"front_pocket": True}) is True
    assert gate_pass("front_pocket", {"front_pocket": False}) is False
    g = {"param": "front_pocket_mouth_mode", "values": ["bulge"],
         "requires": ["front_pocket"], "not": ["front_patch"]}
    assert gate_pass(g, {"front_pocket": True, "front_patch": False,
                         "front_pocket_mouth_mode": "bulge"}) is True
    assert gate_pass(g, {"front_pocket": False, "front_patch": False,
                         "front_pocket_mouth_mode": "bulge"}) is False
    assert gate_pass(g, {"front_pocket": True, "front_patch": True,
                         "front_pocket_mouth_mode": "bulge"}) is False
    assert gate_pass(g, {"front_pocket": True, "front_patch": False,
                         "front_pocket_mouth_mode": "tangent"}) is False


# -- resolve_adjust（纯函数，手工演算写死） ---------------------------------------

def _pocket_view() -> dict:
    return _view(front_pocket=True, front_pocket_mouth_mode="bulge",
                 front_pocket_mouth_bulge=1.25, fit="regular",
                 back_dart=True, back_dart_count=1,
                 front_pocket_p2_drop=11.0, waistband_type="curved")


def test_resolve_levels_and_types():
    v = _pocket_view()
    # 虚键：档位 -> bulge 绝对值（单通道落点）
    r = resolve_adjust({"key": "front_pocket_mouth_depth", "level": "deep"}, v)
    assert (r.key, r.value) == ("front_pocket_mouth_bulge", 1.75)
    # 虚键有序步进：standard -1 -> shallow
    r = resolve_adjust({"key": "front_pocket_mouth_depth", "step": -1}, v)
    assert r.value == 0.75
    # bool 档 on/off -> True/False
    r = resolve_adjust({"key": "back_dart", "level": "off"}, v)
    assert r.value is False
    # int 档位键（省数）："2" -> 2
    r = resolve_adjust({"key": "back_dart_count", "level": "2"}, v)
    assert r.value == 2 and isinstance(r.value, int)
    # 有序枚举步进：regular +1 -> loose
    r = resolve_adjust({"key": "fit", "step": 1}, v)
    assert r.value == "loose"
    # 数值 override：定标步长 × 步数
    r = resolve_adjust({"key": "front_pocket_p2_drop", "step": -2}, v)
    assert r.value == 9.0


def test_resolve_drop_cases():
    v = _pocket_view()
    assert "表外键" in resolve_adjust({"key": "no_such", "level": "x"}, v)
    assert "键已锁定" in resolve_adjust(
        {"key": "front_pocket_mouth_bulge", "step": 1}, v)
    assert "部件未开" in resolve_adjust(
        {"key": "back_patch_width", "step": 1}, v)     # back_patch 关
    assert "档位名非法" in resolve_adjust(
        {"key": "front_pocket_mouth_depth", "level": "huge"}, v)
    # 无序档位键不接受步进（nominal）
    assert "不接受步进" in resolve_adjust(
        {"key": "waistband_type", "step": 1}, v)
    # 步数域：0 / ±3 / 非整数
    for bad in (0, 3, -3, 1.5, "1", True):
        assert "步数" in resolve_adjust(
            {"key": "front_pocket_p2_drop", "step": bad}, v)
    # 有序档位步进钳端点：fit=loose 再 +1 -> 已在最档
    assert "已在最档" in resolve_adjust(
        {"key": "fit", "step": 1}, {**v, "fit": "loose"})
    # 数值钳位端点：值不变 -> 丢弃
    assert "值不变" in resolve_adjust(
        {"key": "front_pocket_p2_drop", "step": 1}, {**v, "front_pocket_p2_drop": 15.0})
    # 当前值缺失（视图没这键）：步进无处起算（gate 过但值缺）
    assert "当前值缺失" in resolve_adjust(
        {"key": "front_pocket_p2_drop", "step": 1}, {"front_pocket": True})
    # 缺 level/value/step
    assert "缺 level/value/step" in resolve_adjust({"key": "fit"}, v)


def test_resolve_evidence_default():
    r = resolve_adjust({"key": "fit", "level": "slim"}, _pocket_view())
    assert r.evidence == "口语调版映射"
    r = resolve_adjust({"key": "fit", "level": "slim", "evidence": "太紧"},
                       _pocket_view())
    assert r.evidence == "太紧"


# -- 绝对设定 value 通道（2026-10-08：原话数字逐字转述，§10.9.2） ------------------


def _patch_view() -> dict:
    return _view(back_patch=True, back_patch_width=12.0,
                 back_patch_height=13.0)


def test_resolve_absolute_value_channel():
    """绝对设定：原话在册逐字转述 -> 咨询带内直设；模型自算数/档位虚键/
    非数字一律丢弃——LLM 只做转述者，红线收窄为「绝不自行产出 cm」。"""
    v = _patch_view()
    # 原话在册：直设 13
    r = resolve_adjust({"key": "back_patch_width", "value": 13},
                       v, "后贴袋宽度调整到13")
    assert (r.key, r.value) == ("back_patch_width", 13.0)
    # 小数逐字转述
    r = resolve_adjust({"key": "back_patch_width", "value": 13.5},
                       v, "宽度改成 13.5")
    assert r.value == 13.5
    # 咨询带外钳位（hi=20）：带内夹界，真守卫仍是引擎 validate/probe
    r = resolve_adjust({"key": "back_patch_width", "value": 25},
                       v, "宽度调到25")
    assert r.value == 20.0
    # 模型自算/折中（原话只有 13）-> 丢
    assert "未见于本轮原话" in resolve_adjust(
        {"key": "back_patch_width", "value": 12.5}, v, "宽度调整到13")
    # 缺省空文本 = 无从校验 -> 丢（安全缺省）
    assert "未见于本轮原话" in resolve_adjust(
        {"key": "back_patch_width", "value": 13}, v)
    # 档位/虚键不吃 value（数字在册也不行——走 level/step）
    assert "不接受绝对值" in resolve_adjust(
        {"key": "fit", "value": 2}, _pocket_view(), "宽松调到2")
    assert "不接受绝对值" in resolve_adjust(
        {"key": "front_pocket_mouth_depth", "value": 2.0},
        _pocket_view(), "弧深调到2")
    # 非数字 / bool（int 子类须显式拒）
    assert "绝对值须为数字" in resolve_adjust(
        {"key": "back_patch_width", "value": "13"}, v, "宽度调到13")
    assert "绝对值须为数字" in resolve_adjust(
        {"key": "back_patch_width", "value": True}, v, "宽度调到1")
    # 已等于当前值
    assert "值不变" in resolve_adjust(
        {"key": "back_patch_width", "value": 12}, v, "宽度调到12")


def test_map_adjustment_absolute_and_step_mixed():
    """绝对设定与模糊步进同轮混发：value 走原话校验、step 照旧起算。"""
    view = _patch_view()
    reply = json.dumps({"adjustments": [
        {"key": "back_patch_width", "value": 13,
         "evidence": "宽度调整到13"},
        {"key": "back_patch_height", "step": 1, "evidence": "高度再高一点"}],
        "note": "袋宽直设 13，袋高微升"}, ensure_ascii=False)
    res = map_adjustment([], view, "后贴袋宽度调整到13，高度再高一点",
                         FakeVLM([reply]))
    got = {e.key: e.value for e in res.entries}
    assert got == {"back_patch_width": 13.0, "back_patch_height": 13.5}
    assert res.dropped == ()


# -- prompt ----------------------------------------------------------------------

def test_build_adjust_prompt_gating_and_content():
    view = _view(front_pocket=True, front_pocket_mouth_mode="bulge",
                 front_pocket_mouth_bulge=1.25)
    prompt = build_adjust_prompt(
        [{"turn": 1, "text": "第一条裤子", "adjust": None}], view, "口袋弧深一点")
    assert "口袋弧深一点" in prompt
    assert "第一条裤子" in prompt                       # 全史进 prompt
    assert "〔袋口〕" in prompt                        # 部位分组标题
    assert "袋口腰头端位置" in prompt                   # gate 过的键出场
    assert "袋口弧深" in prompt                         # 虚键人话出场
    assert "两端垂直式" in prompt                      # 语义句进 prompt（选档唯一依据）
    assert "袋口弧线弧高" not in prompt                 # locked 键缺席
    # gate 挡：front_pocket 关 -> 口袋组键全部缺席
    off = _view(front_pocket=False)
    p2 = build_adjust_prompt([], off, "无")
    assert "袋口腰头端位置" not in p2
    assert "袋口弧深" not in p2


# -- map_adjustment（FakeVLM；永不抛） ---------------------------------------------

def test_map_adjustment_multi_key_dup_and_dropped():
    view = _view(front_pocket=True, front_pocket_mouth_mode="bulge")
    reply = json.dumps({"adjustments": [
        {"key": "front_pocket_mouth_depth", "level": "deep"},
        {"key": "front_pocket_p2_drop", "step": 1},
        {"key": "front_pocket_p2_drop", "step": -1},   # 重复键后者胜
        {"key": "no_such_key", "level": "x"}],         # 表外
        "note": "袋口加深微下移"}, ensure_ascii=False)
    vlm = FakeVLM([reply])
    res = map_adjustment([{"turn": 1, "text": "hi", "adjust": None}],
                         view, "口袋深一点弧度大一点", vlm)
    assert [e.key for e in res.entries] == [
        "front_pocket_mouth_bulge", "front_pocket_p2_drop"]
    cur = view["front_pocket_p2_drop"]
    dup = res.entries[1]
    assert dup.value == round(cur - 1.0, 2)            # 后者（-1）胜
    assert any("表外键" in d for d in res.dropped)
    assert any("重复键取后者" in d for d in res.dropped)
    assert res.note == "袋口加深微下移"
    assert len(vlm.calls) == 1
    assert vlm.calls[0]["thinking"] == "off"           # 恒关思维链


def test_map_adjustment_never_raises():
    view = _view()

    class _Boom:
        def complete(self, *a, **k):
            raise RuntimeError("VLM down")

    assert map_adjustment([], view, "垃圾", FakeVLM(["不是json"])).entries == ()
    assert map_adjustment([], view, "炸", _Boom()).entries == ()
    assert map_adjustment([], view, "无provider", None).entries == ()
    assert map_adjustment([], view, "", FakeVLM([])).entries == ()  # 空文本
    assert AdjustResult.from_dict(res_d := map_adjustment(
        [], view, "x", None).to_dict()) == AdjustResult()


# -- 会话重放投影 ------------------------------------------------------------------

def test_replay_adjustments_later_wins_and_truncate():
    adj1 = {"entries": [{"key": "front_pocket_mouth_bulge", "value": 1.75,
                         "evidence": "弧深"}], "note": "", "dropped": []}
    adj2 = {"entries": [{"key": "front_pocket_mouth_bulge", "value": 0.75,
                         "evidence": "再浅"}], "note": "", "dropped": []}
    s = Session(events=[
        Event(1, "user", "input", text=_DESC),
        Event(1, "agent", "deliver"),
        Event(2, "user", "input", text="弧深一点", data={"adjust": adj1}),
        Event(2, "agent", "deliver"),
        Event(3, "user", "input", text="再浅一点", data={"adjust": adj2})])
    led = replay(s)
    row = led.adjustments["front_pocket_mouth_bulge"]
    assert row.value == 0.75 and row.turn == 3 and row.evidence == "再浅"
    rolled = Session(events=[e for e in s.events if e.turn <= 2])
    assert replay(rolled).adjustments[
        "front_pocket_mouth_bulge"].value == 1.75      # 截断回滚随丢


# -- run_turn 集成（金标核心） ------------------------------------------------------

def test_run_turn_adjust_applies_persists_discloses():
    """①交卷后口语调版 -> 映射注入 -> 新交卷带披露；②后续轮重放持久。"""
    vlm = FakeVLM([])
    out1 = run_turn(Session(), _DESC, (), provider=vlm)
    assert vlm.calls == [] and out1.delivery is not None
    assert out1.delivery["options"]["front_pocket_mouth_bulge"] == 1.25

    vlm2 = FakeVLM([_ADJ_DEEP, _EMPTY_ADJ])
    out2 = run_turn(out1.session, "口袋弧深一点", (), provider=vlm2)
    d2 = out2.delivery
    assert d2["options"]["front_pocket_mouth_bulge"] == 1.75
    assert d2["keys"]["front_pocket_mouth_bulge"]["source"] == "描述"
    assert d2["keys"]["front_pocket_mouth_bulge"]["evidence"].startswith("调版")
    assert len(vlm2.calls) == 1                        # 本轮仅映射一次调用
    assert "口袋弧深一点" in vlm2.calls[0]["prompt"]
    assert "第1轮" in vlm2.calls[0]["prompt"]           # 全史进映射 prompt
    assert d2["adjust"]["applied"] == [
        {"key": "front_pocket_mouth_bulge", "value": 1.75}]
    assert d2["adjust"]["note"] == "袋口弧线加深"
    # ②持久性：无调版语句的后续轮，账本种子照旧生效（结构保证不靠记性）
    out3 = run_turn(out2.session, "挺好，长度没问题", (), provider=vlm2)
    assert out3.delivery["options"]["front_pocket_mouth_bulge"] == 1.75
    assert out3.delivery["keys"]["front_pocket_mouth_bulge"]["source"] == "描述"
    assert len(vlm2.calls) == 2                        # 每轮一条映射（空调整）


def test_run_turn_absolute_set_applies_persists():
    """⑪绝对设定端到端：「后贴袋宽度调整到13」原话数字经 value 通道直设
    参数、交卷披露，账本持久与步进同构（2026-10-08）。"""
    out1 = run_turn(Session(), _DESC, (), provider=FakeVLM([]))
    assert out1.delivery["options"]["back_patch"] is True   # 五袋款带后贴袋
    w13 = json.dumps({
        "adjustments": [{"key": "back_patch_width", "value": 13,
                         "evidence": "后贴袋宽度调整到13"}],
        "note": "后袋宽直接设为 13"}, ensure_ascii=False)
    vlm2 = FakeVLM([w13, _EMPTY_ADJ])
    out2 = run_turn(out1.session, "后贴袋宽度调整到13", (), provider=vlm2)
    d = out2.delivery
    assert d["options"]["back_patch_width"] == 13.0
    assert d["adjust"]["applied"] == [
        {"key": "back_patch_width", "value": 13.0}]
    assert "后袋宽直接设为 13" in d["adjust"]["note"]
    # 持久：后续无关轮账本种子照旧（与步进调整同构）
    out3 = run_turn(out2.session, "挺好就这样", (), provider=vlm2)
    assert out3.delivery["options"]["back_patch_width"] == 13.0
    assert len(vlm2.calls) == 2                        # 每轮一条映射


def test_same_turn_dictionary_wins():
    """③同轮碰撞：词典亲说键胜，映射同键剔除进 dropped 披露。"""
    vlm = FakeVLM([])
    out1 = run_turn(Session(), _DESC, (), provider=vlm)
    canned = json.dumps({
        "adjustments": [{"key": "waistband_type", "level": "curved",
                         "evidence": "换弯腰头"}],
        "note": "换弯腰头"}, ensure_ascii=False)
    vlm2 = FakeVLM([canned])
    out2 = run_turn(out1.session, "直腰头", (), provider=vlm2)
    wb = out2.delivery["keys"]["waistband_type"]
    # 值 = 词典 straight（无照片路径 hint==默认值时 merge 保持「默认」归因，
    # 值语义不受影响——source 断言只对「词典改默认」场景成立）
    assert wb["value"] == "straight"
    assert out2.delivery["adjust"]["applied"] == []
    assert any("明确说法" in d for d in out2.delivery["adjust"]["dropped"])


def test_cross_turn_recency():
    """④跨轮新近性：t1 词典直 -> t2 映射弯胜 -> t3 词典直再胜。"""
    vlm = FakeVLM([])
    out1 = run_turn(Session(), _DESC + "，直腰头", (), provider=vlm)
    assert out1.delivery["keys"]["waistband_type"]["value"] == "straight"
    canned = json.dumps({
        "adjustments": [{"key": "waistband_type", "level": "curved",
                         "evidence": "弯一点"}],
        "note": "改弯腰头"}, ensure_ascii=False)
    vlm2 = FakeVLM([canned, _EMPTY_ADJ])
    out2 = run_turn(out1.session, "微调一下细节", (), provider=vlm2)
    assert out2.delivery["keys"]["waistband_type"]["value"] == "curved"
    out3 = run_turn(out2.session, "还是直腰头吧", (), provider=vlm2)
    assert out3.delivery["keys"]["waistband_type"]["value"] == "straight"


def test_gate_blocks_pocket_keys_when_off():
    """⑤gate：front_pocket 关 -> prompt 无口袋键、模型返口袋键被丢。"""
    off = _view(front_pocket=False)
    prompt = build_adjust_prompt([], off, "改")
    assert "袋口腰头端位置" not in prompt
    assert "部件未开" in resolve_adjust(
        {"key": "front_pocket_p1_dist", "step": 1}, off)


def test_semantics_cover_all_unlocked_keys():
    """语义审计金标（2026-09-27，逐条对 options.py 行内注释）：未 locked
    键全部带语义句——语义是 LLM 选键选档的唯一依据（tangent 误译事故后
    补齐 37 空键 + 修 2 处反向/含混译；locked 键不进 prompt 允许空）。"""
    empty = [k for k, m in META.items() if not m.locked and not m.semantics]
    assert empty == []
    # 方向语义抽查：p1_dist 量取方向（自侧缝朝前中，旧译「离开前中」反向）
    prompt = build_adjust_prompt([], _view(front_pocket=True), "查")
    assert "朝前中量取" in prompt
    assert "两端垂直式" in build_adjust_prompt(
        [], _view(front_pocket_facing=True), "查")   # 袋贴内边形态同口径


def test_direction_anchor_and_facing_bulge_gate():
    """⑩方位锚 + 袋贴 bulge 键口径（「向右凸」误改口袋宽度事故收口）：
    prompt 头部带版面方位消解规则；facing_bulge 双视角语义（凸/凹同弧
    不反义）；bulge/bulge_at gate 收紧到 facing_mode=bulge——tangent/
    offset 模式两键不进 prompt、调整被丢。"""
    prompt = build_adjust_prompt(
        [], _view(front_pocket_facing=True, front_pocket_facing_mode="bulge"), "查")
    assert "侧缝在左" in prompt                        # 头部方位锚
    assert "朝前中方向凸出" in prompt                  # 双视角语义
    assert "版面左" in prompt                          # bulge_at 方位句
    # gate：tangent 模式两键缺席、调整被丢
    off = build_adjust_prompt(
        [], _view(front_pocket_facing=True, front_pocket_facing_mode="tangent"), "查")
    assert "袋贴内边弧凸量" not in off
    assert "袋贴内边弧顶位置" not in off
    assert "形态不符" in resolve_adjust(
        {"key": "front_pocket_facing_bulge", "step": 1},
        _view(front_pocket_facing=True, front_pocket_facing_mode="tangent"))


def test_mapping_provider_unconfigured(tmp_path, monkeypatch):
    """⑥provider 未配置（None+无 vlm.toml）：不抛、不落 adjust、正常交卷。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("YLP_VLM_API_KEY", raising=False)
    out1 = run_turn(Session(), _DESC, ())
    assert out1.delivery is not None
    out2 = run_turn(out1.session, "口袋弧深一点", ())
    assert out2.delivery is not None
    assert "adjust" not in out2.delivery


def test_build_delivery_reverted_disclosure():
    """⑦回退∩applied 披露：probe 回退键不在 keys -> 引擎默认值兜底显示。"""

    class _Stub:
        reverted = ["front_pocket_p2_drop"]
        measurements = {"waist": 74.0}
        model_name = "stub"
        photo_count = 0
        balance_notes: list[str] = []   # 2026-09-29 A5：delivery 契约新增键

        def to_web_payload(self):
            return {"measurements": self.measurements, "options": {},
                    "keys": {}, "issues": [],
                    "probe": {"stage": "L1", "ok": True, "log": []},
                    "score": []}

    adjust_data = {"entries": [{"key": "front_pocket_p2_drop", "value": 13.0,
                                "evidence": "袋口下移"}],
                   "note": "袋口下移", "dropped": []}
    d = _build_delivery(_Stub(), Ledger(), 2, adjust_data)
    adj = d["adjust"]
    assert adj["reverted"] == ["front_pocket_p2_drop"]
    assert adj["applied"] == [
        {"key": "front_pocket_p2_drop",
         "value": _default_value("front_pocket_p2_drop")}]
    assert "引擎校验回退" in adj["note"]
    assert "袋口深浅" in adj["note"]                    # 人话标签披露


# -- probe L0.5（调版回退：版面保持原样不截肢，2026-09-27） ------------------------

_MEAS_FULL = {"waist": 74.0, "hip": 96.0, "knee": 46.0, "hem": 36.0,
              "front_rise": 25.0, "back_rise": 33.0, "outseam": 102.0,
              "thigh": 58.0}
# watch_pocket=True + 纯默认口袋参数 + 相交模式 = 引擎已知默认几何缺口
# （内存 watch-pocket-default-geometry-gap）：L0 必炸（射线不交）
_BOMB = {"front_pocket": True, "front_pocket_facing": True, "watch_pocket": True}


def test_probe_l05_revert_keeps_draft():
    """L0 失败先撤回映射键上一版值重试：成功 L0.5、adjust_kept 记保留值
    （区别于 L1+ 弹键回默认）；等值撤回不触发；撤回治不了病则还原快照
    走原阶梯（L1~L3 照旧）。"""
    from agent.extract.probe import probe_loop
    r = probe_loop(_MEAS_FULL, dict(_BOMB),
                   adjust_revert={"watch_pocket": False})
    assert r.stage == "L0.5" and r.ok
    assert r.adjust_kept == {"watch_pocket": False}
    assert r.reverted == []                     # L0.5 不弹键、不回默认
    # 等值撤回（值没变）-> 不触发 L0.5
    r2 = probe_loop(_MEAS_FULL, dict(_BOMB),
                    adjust_revert={"watch_pocket": True})
    assert r2.stage != "L0.5" and not r2.adjust_kept
    # 撤回的键治不了炸弹（病根在另一键）-> 还原快照走原阶梯
    o3 = {**_BOMB, "front_patch": True}
    r3 = probe_loop(_MEAS_FULL, o3, adjust_revert={"front_patch": False})
    assert r3.stage != "L0.5" and not r3.adjust_kept


def test_run_turn_l05_adjust_not_applied_disclosed():
    """⑨L0.5 端到端：映射值单键带内合法但撞交叉约束 -> L0 失败撤回上一版
    重试 -> 交卷版面不变（部件全在、值保持上一版）、stage L0.5、note 披露
    「未生效/保持上一版」，replaced 旧口径的 L3 截肢交纯直筒。
    触发键 front_pocket_p2_drop 撞 P2 主切口守卫（p2_drop 须 < 外缝弧全长
    ≈11.77）：两轮 +2 自基线 7.5 顶到 11.5（弧内 L0 全过——11.5 + 侧深 3.5
    已越过臀围线，2026-09-28 起跨段接大腿段外缝照常过，正是被解开的旧守卫
    不再拦的路径）、第三轮 +1 = 12.5 越弧长 -> L0 失败撤回 11.5。"""
    out1 = run_turn(Session(), _DESC, (), provider=FakeVLM([]))
    assert out1.delivery["options"]["front_pocket_p2_drop"] == 7.5
    bump = json.dumps({
        "adjustments": [{"key": "front_pocket_p2_drop", "step": 2,
                         "evidence": "袋口深一点"}],
        "note": "袋口下移加深"}, ensure_ascii=False)
    out2 = run_turn(out1.session, "袋口深一点", (), provider=FakeVLM([bump]))
    assert out2.delivery["probe"]["stage"] == "L0"
    assert out2.delivery["options"]["front_pocket_p2_drop"] == 9.5
    out3 = run_turn(out2.session, "再深一点", (), provider=FakeVLM([bump]))
    prev = out3.delivery["options"]["front_pocket_p2_drop"]
    assert out3.delivery["probe"]["stage"] == "L0"
    assert prev == 11.5
    over = json.dumps({
        "adjustments": [{"key": "front_pocket_p2_drop", "step": 1,
                         "evidence": "袋口深一点"}],
        "note": "袋口下移加深"}, ensure_ascii=False)
    out4 = run_turn(out3.session, "还深一点", (), provider=FakeVLM([over]))
    d = out4.delivery
    assert d["probe"]["stage"] == "L0.5"
    assert d["options"]["front_pocket_p2_drop"] == prev     # 保持上一版
    assert d["options"]["front_pocket"] is True             # 版面未截肢
    assert d["options"]["watch_pocket"] is True
    adj = d["adjust"]
    assert adj["applied"] == [{"key": "front_pocket_p2_drop", "value": prev}]
    assert adj["reverted"] == []
    assert "未生效" in adj["note"] and "保持上一版" in adj["note"]
    assert "袋口下移加深" in adj["note"]                    # 映射 note 前缀保留


def test_http_adjust_roundtrip(monkeypatch):
    """⑧HTTP 缝：_build_provider 注入两轮 POST，会话 JSON 往返带映射数据。"""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from agent.app import app
    import agent.runner
    vlm = FakeVLM([_ADJ_DEEP, _EMPTY_ADJ])
    monkeypatch.setattr(agent.runner, "_build_provider", lambda p: vlm)
    client = TestClient(app)
    r1 = client.post("/api/chat/turn",
                     data={"session": Session().to_json(), "text": _DESC})
    b1 = r1.json()
    assert b1["ok"] and b1["delivery"]
    r2 = client.post("/api/chat/turn",
                     data={"session": json.dumps(b1["session"]),
                           "text": "口袋弧深一点"})
    b2 = r2.json()
    assert r2.status_code == 200, r2.text
    d = b2["delivery"]
    assert d["options"]["front_pocket_mouth_bulge"] == 1.75
    assert d["adjust"]["applied"][0]["value"] == 1.75
    restored = Session.from_json(json.dumps(b2["session"]))
    led = replay(restored)
    assert led.adjustments["front_pocket_mouth_bulge"].value == 1.75
