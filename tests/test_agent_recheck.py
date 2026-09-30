"""定向复查金标（D，2026-09-29，设计 .doc/智能体闭环一期设计.md §3）。

覆盖：意图层 schema（D1 action/target + 解析失败回退）/ 路由表（D2）/
聚焦 prompt 基线+判据裁剪 / diff / 两段握手状态机（D3：directive ->
fulfill 直执行、空照片降级求援卡且承诺不销账）/ 同轮直执行（CLI 照片
在手）/ 补片续执行（catch-up）/ VLM 失败零打扰降级。

FakeVLM 单队列出队顺序铁律（同一轮内）：映射 -> S1 补漏 -> S2；复查轮
= 映射 -> 聚焦复查（S2 不跑——照片全喂聚焦调用，指纹去重绕过）。
"""

from __future__ import annotations

import json

from agent.converse import run_turn
from agent.extract.adjust import AdjustResult, map_adjustment
from agent.extract.parse import Observation, ObservationEntry
from agent.extract.params_meta import default_view
from agent.extract.provider import FakeVLM
from agent.extract.recheck import (ROUTING, build_focus_prompt, diff_obs,
                                   focus_cats, focus_keys, route_target)
from agent.extract.schema import MODEL_KEYS
from agent.extract.parse import parse_model_json
from agent.session import Session

_DESC = ("女款高腰小脚牛仔裤，腰围74 臀围91 膝围44 脚口34 前浪25 后浪33 "
         "裤长102 大腿围58，微弹面料，五袋款带小表袋裤耳")

# 第 1 轮带照 S2：认出方底贴袋（=复查基线）
_S2_REPLY = json.dumps({
    "back_patch_shape": {"value": "rectangle", "confidence": 0.8,
                         "evidence": "背面照袋底两角小圆角、底边平直"},
}, ensure_ascii=False)

# 复查意图映射响应（D1 新 schema）
_RECHECK_MAP = json.dumps({
    "action": "recheck", "target": "后贴袋", "adjustments": [],
    "note": "我来重新细看后贴袋的形状与大小",
}, ensure_ascii=False)

_EMPTY_ADJ = '{"adjustments": [], "note": ""}'

# 聚焦复查响应：贴袋有 + 形状改盾形（带视觉证据）
_FOCUS_REPLY = json.dumps({
    "back_patch": {"value": True, "confidence": 0.9,
                   "evidence": "背面照两枚贴袋清晰"},
    "back_patch_shape": {"value": "baker_shield", "confidence": 0.85,
                         "evidence": "底部两斜线交于底中一点成尖角"},
}, ensure_ascii=False)


# -- D1 意图层 -------------------------------------------------------------------


def test_intent_recheck_empties_adjustments_with_disclosure():
    """action=recheck 时 adjustments 必空：多余项进 dropped 披露；
    action/target 原样保留（旧响应缺 action 键 -> adjust 现状回退）。"""
    view = {**default_view(), "back_patch": True}   # 开门（引擎默认裸版关）
    vlm = FakeVLM([json.dumps({
        "action": "recheck", "target": "后贴袋",
        "adjustments": [{"key": "back_patch_shape", "level": "angular"}],
        "note": "重新细看后贴袋",
    }, ensure_ascii=False)])
    res = map_adjustment([], view, "后贴袋你再仔细看看", vlm)
    assert res.action == "recheck" and res.target == "后贴袋"
    assert res.entries == ()
    assert any("忽略调整项" in d for d in res.dropped)

    # 旧格式（无 action/target）-> adjust（现状行为，天然回退）
    vlm2 = FakeVLM([_EMPTY_ADJ])
    res2 = map_adjustment([], default_view(), "口袋再浅一点", vlm2)
    assert res2.action == "adjust" and res2.target == ""

    # 非法 action 值 -> adjust
    vlm3 = FakeVLM(['{"action": "reboot", "adjustments": [], "note": ""}'])
    res3 = map_adjustment([], default_view(), "x", vlm3)
    assert res3.action == "adjust"

    # to_dict/from_dict 往返 + 旧事件缺键回退
    d = res.to_dict()
    assert d["action"] == "recheck" and d["target"] == "后贴袋"
    assert AdjustResult.from_dict(d).action == "recheck"
    legacy = {"entries": [], "note": "n", "dropped": []}
    assert AdjustResult.from_dict(legacy).action == "adjust"


def test_intent_prompt_rule_and_schema_line():
    """prompt 规则 0（意图判据：recheck 判据 + note 禁不作为）+ 输出 JSON
    行含 action/target；规则 1~8 编号不动（外部文档引用规则号）。"""
    from agent.extract.adjust import build_adjust_prompt
    p = build_adjust_prompt([], default_view(), "后贴袋你再仔细看看")
    assert "0. 先判意图定" in p
    assert '"recheck"' in p and "必须为空数组" in p
    assert "禁止「暂不改动」" in p
    assert '{"action": "adjust", "target": ""' in p
    assert "1. 只允许使用【当前版参数】" in p     # 原规则编号保持
    assert "5. 用户要求整体前后互换" in p


# -- D2 路由 / 聚焦 prompt / diff --------------------------------------------------


def test_route_target_and_focus_sets():
    """target 归一：规范组名直取 / surface 分组名别名 / 含组名子串 /
    未知或空 -> 兜底（全键全类别，不替用户缩小范围）。"""
    assert route_target("后贴袋") == "后贴袋"
    assert route_target("袋贴") == "前口袋"        # adjust surface 分组名别名
    assert route_target("后育克") == "育克后片"
    assert route_target("就后贴袋那块再看看") == "后贴袋"
    assert route_target("") == "兜底"
    assert route_target("不知道哪不对") == "兜底"
    assert focus_keys("后贴袋") == ("back_patch", "back_patch_shape")
    assert focus_cats("腰头") == ("front", "back")
    assert focus_keys("兜底") == tuple(MODEL_KEYS)
    assert set(ROUTING["门襟"]["keys"]) <= set(MODEL_KEYS)


def test_build_focus_prompt_baseline_criteria_template():
    """聚焦 prompt：基线段逐键带证据 + 仅该组判据（他组哨兵不混入）+
    本轮原话 + 预填模板可被解析器吃回（先验补缺键）。"""
    prior = {"back_patch_shape": ObservationEntry("rectangle", 0.8,
                                                  "袋底两角小圆角")}
    keys = focus_keys("后贴袋")
    p = build_focus_prompt("后贴袋", keys, prior, "后贴袋你再仔细看看")
    assert "【上次判断（基线）】" in p
    assert "back_patch_shape: rectangle（袋底两角小圆角）" in p
    assert "后贴袋你再仔细看看" in p
    assert "盾形" in p and "数底部" in p       # 本组判据在场
    assert "直腰头" not in p                   # 他组判据不混入
    tpl = parse_model_json(p)                   # 模板回环可解析
    assert set(tpl) == set(keys)
    assert tpl["back_patch_shape"]["value"] == "rectangle"   # 基线预填
    assert tpl["back_patch"]["value"] is True                 # 先验补缺键


def test_diff_obs_changed_new_unchanged():
    """diff 只记变化：值同不记 / 基线缺=新判断（old=None）/ 键序随 focus。"""
    prior = Observation(entries={
        "back_patch": ObservationEntry(True, 0.8, "两枚贴袋"),
        "back_patch_shape": ObservationEntry("rectangle", 0.8, "小圆角")})
    obs = Observation(entries={
        "back_patch": ObservationEntry(True, 0.9, "维持"),
        "back_patch_shape": ObservationEntry("baker_shield", 0.85, "底中尖角")})
    diff = diff_obs(prior, obs, ("back_patch", "back_patch_shape"))
    assert diff == [{"key": "back_patch_shape", "old": "rectangle",
                     "new": "baker_shield", "evidence": "底中尖角"}]
    # 基线缺键 -> 新判断
    diff2 = diff_obs(None, obs, ("back_patch", "back_patch_shape"))
    assert [d["key"] for d in diff2] == ["back_patch", "back_patch_shape"]
    assert diff2[0]["old"] is None


# -- D3 两段握手 / 同轮直执行 / 降级 ------------------------------------------------


def test_recheck_two_phase_handshake(tmp_path):
    """握手金标：轮次 A 文字复查请求（无照片）→ directive（组 + 类别 +
    message）；轮次 B fulfill + 背面照 → 聚焦复查直执行：diff 披露
    rectangle→baker_shield、payload keys 更新、缓存入账、不新增 user
    事件、directive 标记 done。"""
    p1 = tmp_path / "front.png"
    p1.write_bytes(b"fff")
    p2 = tmp_path / "back.png"
    p2.write_bytes(b"bbb")
    vlm = FakeVLM([_S2_REPLY, _RECHECK_MAP, _FOCUS_REPLY])
    out1 = run_turn(Session(), _DESC, (str(p1),),
                    photo_meta=[{"category": "front", "note": ""}],
                    provider=vlm)
    assert out1.delivery is not None
    assert out1.delivery["keys"]["back_patch_shape"]["value"] == "rectangle"

    # 轮次 A：文字请求，无照片 → directive（不交卷不出卡）
    out2 = run_turn(out1.session, "后贴袋你再仔细看看", (), provider=vlm)
    assert out2.card is None and out2.delivery is None
    assert out2.directive == {"group": "后贴袋",
                              "photo_categories": ["back"],
                              "message": out2.directive["message"]}
    assert "背面照片" in out2.directive["message"]
    kinds = [(e.role, e.kind) for e in out2.session.events[-2:]]
    assert kinds == [("user", "input"), ("agent", "directive")]

    # 轮次 B：fulfill + 背面照 → 直执行（无 user 事件、无 S2、无映射）
    n_user = sum(1 for e in out2.session.events if e.role == "user")
    out3 = run_turn(out2.session, "", (str(p2),),
                    photo_meta=[{"category": "back", "note": ""}],
                    fulfill="recheck", provider=vlm)
    assert out3.directive is None and out3.card is None
    assert sum(1 for e in out3.session.events if e.role == "user") == n_user
    assert len(vlm.calls) == 3                       # S2 + 映射 + 聚焦
    assert vlm.calls[2]["images"] == [str(p2)]       # 只喂背面照
    fp = vlm.calls[2]["prompt"]
    assert "【上次判断（基线）】" in fp and "rectangle" in fp
    assert "后贴袋你再仔细看看" in fp                # 轮次 A 原话进复查
    # directive 已销账（done 标记在事件 data 内）
    dv = [e for e in out3.session.events if e.kind == "directive"][-1]
    assert dv.data["done"] is True
    # diff 披露：back_patch 基线缺=新判断，shape rectangle->盾形
    rc = out3.delivery["recheck"]
    assert rc["group"] == "后贴袋"
    assert [(d["key"], d["old"], d["new"]) for d in rc["diff"]] == \
        [("back_patch", None, True),
         ("back_patch_shape", "rectangle", "baker_shield")]
    assert all("底中" in d["evidence"] or d["key"] == "back_patch"
               for d in rc["diff"])
    # note = 映射注语 + 复查结论一句话（diff 摘要；evidence 在 diff 条目）
    assert rc["note"] == ("我来重新细看后贴袋的形状与大小；复查后贴袋："
                          "2 处更新（back_patch （未判断）→开、"
                          "back_patch_shape rectangle→baker_shield）")
    # payload 更新 + 证据进 keys
    k = out3.delivery["keys"]["back_patch_shape"]
    assert k["value"] == "baker_shield" and "底中" in k["evidence"]
    # 缓存入账：shape 已改 + 背面照行落账（聚焦看过即入账）
    assert out3.session.vlm_cache["entries"]["back_patch_shape"]["value"] \
        == "baker_shield"
    rows = {r["c"]: r for r in out3.session.vlm_cache["photos"]}
    assert set(rows) == {"front", "back"}


def test_recheck_fulfill_no_photos_degrades_then_catchup(tmp_path):
    """空照片降级（§3.4）：轮次 B 无背面照 → 按类别求援卡、零模型调用、
    directive **不销账**；用户按卡补片（普通轮带片）→ catch-up 续执行
    承诺的复查。"""
    p1 = tmp_path / "front.png"
    p1.write_bytes(b"fff")
    p2 = tmp_path / "back.png"
    p2.write_bytes(b"bbb")
    vlm = FakeVLM([_S2_REPLY, _RECHECK_MAP])
    out1 = run_turn(Session(), _DESC, (str(p1),),
                    photo_meta=[{"category": "front", "note": ""}],
                    provider=vlm)
    out2 = run_turn(out1.session, "后贴袋你再仔细看看", (), provider=vlm)
    assert out2.directive is not None

    out3 = run_turn(out2.session, "", (), fulfill="recheck",
                    provider=FakeVLM([]))            # 空队列哨兵：零调用
    assert out3.card is not None and out3.delivery is None
    assert out3.card.want_photos == ["背面平铺照"]
    assert "后贴袋" in out3.card.message
    dv = [e for e in out3.session.events if e.kind == "directive"][-1]
    assert "done" not in dv.data                     # 未销账：承诺仍有效

    # 补片轮（普通轮带背面照）：catch-up 续执行
    vlm2 = FakeVLM([_FOCUS_REPLY])                  # text 空 -> 无映射调用
    out4 = run_turn(out3.session, "", (str(p2),),
                    photo_meta=[{"category": "back", "note": ""}],
                    provider=vlm2)
    assert out4.delivery is not None
    assert out4.delivery["recheck"]["group"] == "后贴袋"
    assert out4.delivery["keys"]["back_patch_shape"]["value"] == "baker_shield"


def test_recheck_same_turn_direct_with_photos(tmp_path):
    """同轮直执行（CLI 照片在手 / 前端顺手带片）：复查请求轮带背面照 →
    无握手直接复查；轮次序列 = 轮1 S2 建基线 -> 轮2 映射 + 聚焦（S2 不
    跑）；新照片聚焦看过即入缓存行。"""
    p1 = tmp_path / "front.png"
    p1.write_bytes(b"fff")
    p2 = tmp_path / "back.png"
    p2.write_bytes(b"bbb")
    vlm = FakeVLM([_S2_REPLY, _RECHECK_MAP, _FOCUS_REPLY])
    out1 = run_turn(Session(), _DESC, (str(p1),),
                    photo_meta=[{"category": "front", "note": ""}],
                    provider=vlm)                          # 轮1：S2 建基线
    assert len(vlm.calls) == 1
    out2 = run_turn(out1.session, "后贴袋你再仔细看看", (str(p2),),
                    photo_meta=[{"category": "back", "note": ""}],
                    provider=vlm)
    assert out2.directive is None and out2.card is None
    assert out2.delivery is not None
    rc = out2.delivery["recheck"]
    assert rc["group"] == "后贴袋"
    assert rc["diff"][1] == {"key": "back_patch_shape", "old": "rectangle",
                             "new": "baker_shield",
                             "evidence": "底部两斜线交于底中一点成尖角"}
    assert len(vlm.calls) == 3                       # S2 + 映射 + 聚焦
    assert vlm.calls[2]["images"] == [str(p2)]       # 聚焦只喂背面照
    assert "后贴袋你再仔细看看" in vlm.calls[2]["prompt"]   # 原话进复查
    rows = out2.session.vlm_cache["photos"]
    assert {r["c"] for r in rows} == {"front", "back"}


def test_recheck_directive_when_photos_wrong_category(tmp_path):
    """类别不合（只有正面照，复查要背面）→ 仍走 directive；正面照照常
    进 S2（新指纹），不被复查吞掉。"""
    p1 = tmp_path / "front.png"
    p1.write_bytes(b"fff")
    vlm = FakeVLM([_S2_REPLY, _RECHECK_MAP])
    out1 = run_turn(Session(), _DESC, (str(p1),),
                    photo_meta=[{"category": "front", "note": ""}],
                    provider=vlm)
    out2 = run_turn(out1.session, "后贴袋你再仔细看看", (str(p1),),
                    photo_meta=[{"category": "front", "note": ""}],
                    provider=vlm)
    assert out2.directive is not None                # 正面照喂不了后贴袋复查
    assert out2.directive["photo_categories"] == ["back"]
    assert len(vlm.calls) == 2                       # S2 + 映射；旧指纹不重调 S2


def test_recheck_vlm_fail_degrades_to_current_state(tmp_path):
    """聚焦调用失败（输出非 JSON）：零打扰降级——照常交卷、diff 空、note
    披露「保持原判断」、缓存不动（背面照保持未识别）。"""
    p1 = tmp_path / "front.png"
    p1.write_bytes(b"fff")
    p2 = tmp_path / "back.png"
    p2.write_bytes(b"bbb")
    vlm = FakeVLM([_S2_REPLY, _RECHECK_MAP, "模型打了个盹，没有 JSON"])
    out1 = run_turn(Session(), _DESC, (str(p1),),
                    photo_meta=[{"category": "front", "note": ""}],
                    provider=vlm)
    out2 = run_turn(out1.session, "后贴袋你再仔细看看", (str(p2),),
                    photo_meta=[{"category": "back", "note": ""}],
                    provider=vlm)
    assert out2.delivery is not None                 # 不阻断：照常交卷
    rc = out2.delivery["recheck"]
    assert rc["diff"] == []
    assert "保持原判断" in rc["note"]
    assert out2.delivery["keys"]["back_patch_shape"]["value"] == "rectangle"
    rows = out2.session.vlm_cache["photos"]
    assert [r["c"] for r in rows] == ["front"]       # 失败片不入账（可再喂）


def test_fulfill_without_directive_falls_back_to_normal():
    """fulfill 无待执行 directive → 降级普通轮：映射/user 事件照常、
    文本正常进管线（不丢话）。"""
    vlm = FakeVLM([_EMPTY_ADJ])
    out1 = run_turn(Session(), _DESC, (), provider=vlm)
    out2 = run_turn(out1.session, "腰围75", (), fulfill="recheck",
                    provider=vlm)
    assert out2.delivery is not None
    assert out2.delivery["measurements"]["waist"] == 75.0
    assert out2.session.events[-2].role == "user"    # user 事件照常 append


# -- 聚焦复查辅助图（2026-09-30 后贴袋裁块 + 临时目录时机回归） --------------------

def test_focus_recheck_back_pocket_crop_attached_and_alive(tmp_path):
    """后贴袋组聚焦复查附袋区放大辅助图，且临时图在 complete 调用瞬间
    仍在盘上（首版 with 块在调用前就清理、辅助图从未真正送达的回归钉；
    provider 读盘即 FileNotFoundError，还会漏出 except (ValueError,
    RuntimeError) 之外）。调用后临时文件清理、不落残留。"""
    import os

    from agent.extract.recheck import focus_recheck

    p_back = tmp_path / "back.png"
    try:
        from PIL import Image
        Image.new("RGB", (800, 1600), (240, 240, 240)).save(p_back, "PNG")
    except ImportError:                              # 无 Pillow 环境跳过
        p_back.write_bytes(b"\xff\xd8notreally")     # 降级：无辅助图也回归时机

    class _RecordingVLM(FakeVLM):
        """记录 complete 调用瞬间各图是否在盘上。"""

        def __init__(self, responses):
            super().__init__(responses)
            self.alive_at_call = None

        def complete(self, prompt, images=(), thinking=None):
            self.alive_at_call = [os.path.exists(ip) for ip in images]
            self.calls.append({"prompt": prompt, "images": list(images),
                               "thinking": thinking})
            return self._responses.pop(0)

    prior = Observation(entries={
        "back_patch_shape": ObservationEntry("rectangle", 0.8, "底边平直")})
    vlm = _RecordingVLM(["{"])                       # 非 JSON：走降级分支即可
    obs, diff, note = focus_recheck(
        "后贴袋", "后贴袋你再仔细看看", [str(p_back)], prior, vlm,
        photo_meta=[{"category": "back", "note": ""}])
    assert obs is None and note == "视觉模型调用失败，保持原判断"
    imgs = vlm.calls[0]["images"]
    if len(imgs) == 2:                               # Pillow 在场：附了袋区裁块
        aux = imgs[1]
        assert "bp_crop_back" in aux
        assert vlm.alive_at_call == [True, True]     # 调用瞬间都在盘上
        assert not os.path.exists(aux)               # 调用后清理、不残留
    else:                                            # 裁剪降级：至少原图在
        assert imgs == [str(p_back)] and vlm.alive_at_call == [True]
