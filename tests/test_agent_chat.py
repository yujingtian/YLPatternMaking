"""智能体多轮会话金标（2026-09-21 一期，§10.9）：零打扰 + 求援循环 + 账本/缓存。

对话脚本格式 = session JSON 子集（load_script）；FakeVLM 空队列即哨兵
（多调一次就 AssertionError）。金标断言（手工演算口径写死在用例里）：

- 零打扰主路径：全料一次喂入 → 0 次反问、0 次模型调用、直接交卷；
- 求援循环：缺 back_rise → 卡片点名「后浪」；补答 → 交卷 back_rise=33，
  两轮合计恰 1 次模型调用（S1 补漏答 null 那次）；
- 改口：后答覆盖先答（腰围 74 → 75，账本 turn=2）；
- VLM 批缓存：带照轮恰 1 次 S2；纯文字精修轮 0 新调用，且描述词
  「直腰头」覆盖照片认出的 curved（词典优先于照片，A 表）；
- 回滚 = 截断事件流重放（腰围回到 74）；
- 会话 JSON 往返无损；eval 脚本 {"turns":[…]} 落位；
- CLI chat 两轮交卷 exit 0 出双产物；HTTP /api/chat/turn 会话往返两轮。

调版映射（2026-09-27，§10.9.2）：交卷后的纯文字轮**先出队一条映射响应**
（map_adjustment 在 S1 补漏/S2 之前），相关用例队列头部补 _EMPTY_ADJ。
"""

from __future__ import annotations

import io
import json
import sys

import pytest

from agent.converse import run_turn
from agent.extract.provider import FakeVLM
from agent.session import Session, load_script, replay

_DESC = ("女款高腰小脚牛仔裤，腰围74 臀围91 膝围44 脚口34 前浪25 后浪33 "
         "裤长102 大腿围58，微弹面料，五袋款带小表袋裤耳")
_DESC_MISSING = "女款小脚牛仔裤，腰围74 臀围91 膝围44 脚口34 前浪25 裤长102"

_S2_REPLY = json.dumps({
    "waistband_type": {"value": "curved", "confidence": 0.85,
                       "evidence": "腰头上口在侧缝处下凹弧线，与裤身一体顺接"},
}, ensure_ascii=False)

# 交卷后纯文字轮的调版映射响应（空调整 = 模型判断与调版无关）
_EMPTY_ADJ = '{"adjustments": [], "note": ""}'


def test_zero_disturbance_full_input():
    """全料一次喂入：零反问零模型调用直接交卷（零打扰主路径金标）。"""
    vlm = FakeVLM([])                                  # 空队列哨兵
    outcome = run_turn(Session(), _DESC, (), provider=vlm)
    assert outcome.card is None and outcome.delivery is not None
    assert vlm.calls == []                             # 一次模型都没调
    assert outcome.delivery["measurements"]["waist"] == 74.0
    assert outcome.session.events[-1].kind == "deliver"
    # probe 段照旧进 payload（shape 与 /api/extract 契约一致）
    assert outcome.delivery["probe"]["ok"] is True


def test_missing_card_then_answer_delivers():
    """缺 back_rise：S1 补漏答 null → 求援卡点名后浪；补答后交卷。"""
    vlm = FakeVLM(['{"back_rise": null}'])
    out1 = run_turn(Session(), _DESC_MISSING, (), provider=vlm)
    assert out1.delivery is None
    card = out1.card.to_dict()
    assert [a["key"] for a in card["asks"]] == ["back_rise"]
    assert "后浪" in out1.card.message
    assert out1.session.events[-1].kind == "card"
    out2 = run_turn(out1.session, "后浪33", (), provider=vlm)
    assert out2.card is None
    assert out2.delivery["measurements"]["back_rise"] == 33.0
    assert len(vlm.calls) == 1                         # 第 2 轮零新增调用


def test_missing_card_no_photo_nudge_with_cached_evidence():
    """清池口径（2026-09-24）：会话 vlm_cache 已有照片观测时，缺项卡
    不再建议补拍——照片已提交过，本轮不重发也 counts as has_photos。"""
    vlm = FakeVLM(['{"back_rise": null}'])
    session = Session()
    session.vlm_cache = {
        "entries": {"waistband_type": {"value": "curved",
                                       "confidence": 0.85,
                                       "evidence": "腰头上口下凹弧线"}},
        "dropped": [],
        "photos": ["abc123"],
    }
    out = run_turn(session, _DESC_MISSING, (), provider=vlm)
    assert out.card is not None
    assert out.card.want_photos == []                  # 有证据：不劝补拍
    assert "也可以补一张平铺照片" not in out.card.message


def test_correction_later_turn_wins():
    """改口：第 2 轮「腰围75」覆盖第 1 轮 74，账本记 turn=2。"""
    vlm = FakeVLM([_EMPTY_ADJ])
    out1 = run_turn(Session(), _DESC, (), provider=vlm)
    out2 = run_turn(out1.session, "腰围75", (), provider=vlm)
    assert out2.delivery["measurements"]["waist"] == 75.0
    led = replay(out2.session)
    assert led.measurements["waist"].turn == 2


def test_photo_batch_cache_and_hint_priority(tmp_path):
    """带照轮恰 1 次 S2；纯文字轮缓存命中 0 新调用 + 词典覆盖照片。"""
    photo = tmp_path / "front.png"
    photo.write_bytes(b"png-bytes")
    vlm = FakeVLM([_S2_REPLY, _EMPTY_ADJ])
    out1 = run_turn(Session(), _DESC, (str(photo),), provider=vlm)
    assert len(vlm.calls) == 1
    assert out1.delivery["keys"]["waistband_type"]["value"] == "curved"
    # 同一张照片全量重发 + 文字改口：缓存命中（无新指纹）不二次调 S2，
    # 但调版映射出队一次（calls[1]，纯文本）——直腰头是词典词，canned
    # 空映射不碰它，同轮碰撞规则由 test_agent_adjust.py 金标钉死
    out2 = run_turn(out1.session, "直腰头", (str(photo),), provider=vlm)
    assert len(vlm.calls) == 2
    wb = out2.delivery["keys"]["waistband_type"]
    assert wb["value"] == "straight" and wb["source"] == "描述"
    assert out2.session.vlm_cache["photos"]            # 指纹已落账


# -- 思考段透传（2026-10-08 前端折叠展示） ------------------------------------


def test_s2_reasoning_threaded_to_delivery(tmp_path):
    """S2 思考段经 provider.last_reasoning -> delivery.reasoning 透传；
    纯文字轮（S2 未跑）恒空串——映射节点虽也 complete 了，草稿不外漏。"""
    photo = tmp_path / "front.png"
    photo.write_bytes(b"png-bytes")

    class _ReasoningVLM(FakeVLM):
        def complete(self, prompt, images=(), thinking=None, purpose=""):
            r = super().complete(prompt, images, thinking, purpose)
            self.last_reasoning = "先看腰头：上缘水平，侧缝处明显下沉——弯腰头"
            return r

    vlm = _ReasoningVLM([_S2_REPLY, _EMPTY_ADJ])
    out1 = run_turn(Session(), _DESC, (str(photo),), provider=vlm)
    assert out1.delivery["reasoning"] == (
        "先看腰头：上缘水平，侧缝处明显下沉——弯腰头")
    # 第 2 轮纯文字（映射出队 _EMPTY_ADJ，无 S2）：思考段空
    out2 = run_turn(out1.session, "腰围75", (), provider=vlm)
    assert out2.delivery["reasoning"] == ""


def test_clip_reasoning_head_tail():
    """clip_reasoning 响应瘦身：≤6000 原样；超限保头 4000 + 中略标记 + 尾 1500。"""
    from agent.extract import clip_reasoning

    assert clip_reasoning("短草稿") == "短草稿"
    out = clip_reasoning("x" * 7001)
    assert out.startswith("x" * 4000)
    assert out.endswith("x" * 1500)
    assert "中略" in out and len(out) < 7001


def test_new_photo_second_batch(tmp_path):
    """中途补的照片是新指纹：第二轮 S2 带新照片再调一次，证据覆盖。"""
    p1 = tmp_path / "a.png"
    p1.write_bytes(b"aaa")
    p2 = tmp_path / "b.png"
    p2.write_bytes(b"bbb")
    vlm = FakeVLM([_S2_REPLY, _EMPTY_ADJ,
                   json.dumps({"back_patch": {"value": False,
                                              "confidence": 0.8,
                                              "evidence": "背面照无贴袋"}},
                              ensure_ascii=False)])
    out1 = run_turn(Session(), _DESC, (str(p1),), provider=vlm)
    out2 = run_turn(out1.session, "换个角度看", (str(p1), str(p2)),
                    provider=vlm)
    assert len(vlm.calls) == 3                          # S2 + 映射 + 新批 S2
    assert len(vlm.calls[2]["images"]) == 1            # 只送新照片 b
    bp = out2.delivery["keys"]["back_patch"]
    assert bp["value"] is False and "背面照" in bp["evidence"]


def test_rollback_truncate_replays():
    """回滚：截断到 turn 1 重放，腰围回到 74。"""
    vlm = FakeVLM([_EMPTY_ADJ])
    out1 = run_turn(Session(), _DESC, (), provider=vlm)
    out2 = run_turn(out1.session, "腰围75", (), provider=vlm)
    assert out2.delivery["measurements"]["waist"] == 75.0
    rolled = out2.session
    rolled.events = [e for e in rolled.events if e.turn <= 1]
    assert replay(rolled).measurements["waist"].value == 74.0


def test_session_json_roundtrip_and_script_format():
    """会话 JSON 往返无损；eval 脚本 {"turns":[…]} 逐轮落位。"""
    vlm = FakeVLM(['{"back_rise": null}'])
    out = run_turn(Session(), _DESC_MISSING, (), provider=vlm)
    restored = Session.from_json(out.session.to_json())
    assert [e.kind for e in restored.events] == \
        [e.kind for e in out.session.events]
    assert replay(restored).measurements["waist"].value == 74.0
    script = load_script({"turns": [{"text": _DESC}, {"text": "腰围75"}]})
    assert [e.turn for e in script.events] == [1, 2]
    assert script.events[0].role == "user"


# -- B 拆分（2026-09-29）：S2 只看本轮叙事 + 账本摘要/基线注入 ------------------

def test_ledger_brief_renders():
    """_ledger_brief 四行渲染：尺寸终值 / 尺码+缩水 / 描述倾向 / 已应用调版
    （最近 3 条带轮次原话）；空账本 None（调用方据此回落全史=旧行为）。"""
    from agent.converse import _ledger_brief
    from agent.session import Ledger, LedgerRow
    led = Ledger()
    led.measurements = {"waist": LedgerRow(74.0, 1, "描述摘录「腰围74」"),
                        "hip": LedgerRow(91.0, 1, "描述摘录「臀围91」")}
    led.size_label = LedgerRow(29, 1, "29码")
    led.shrinkage = LedgerRow(0.03, 1, "缩水3%")
    led.hints = {"stretch": LedgerRow("high", 2, "弹力面料")}
    led.adjustments = {"front_pocket_p2_drop": LedgerRow(9.0, 2, "口袋往下一点")}
    brief = _ledger_brief(led)
    assert "尺寸：腰围74、臀围91" in brief
    assert "尺码29码" in brief and "缩水3%" in brief
    assert "描述倾向：stretch=high" in brief
    assert "已应用调版：第2轮「口袋往下一点」→ front_pocket_p2_drop=9" in brief
    assert _ledger_brief(Ledger()) is None   # 空账本 -> 摘要不注（回退开关）


def test_b1_prompt_split_brief_and_baseline(tmp_path):
    """B1/B3：第 2 轮新照片 S2 prompt 只含本轮叙事 +【已确认状态】摘要
    （账本尺寸终值）+【上次视觉判断】基线段——早轮叙事不再整段复述。"""
    p1 = tmp_path / "front.png"
    p1.write_bytes(b"aaa")
    p2 = tmp_path / "back.png"
    p2.write_bytes(b"bbb")
    vlm = FakeVLM([_S2_REPLY, _EMPTY_ADJ, _S2_REPLY])
    out1 = run_turn(Session(), _DESC, (str(p1),), provider=vlm)
    out2 = run_turn(out1.session, "麻烦看下背面贴袋", (str(p2),),
                    provider=vlm)
    assert len(vlm.calls) == 3               # 第 1 轮 S2 + 映射 + 新批 S2
    prompt = vlm.calls[2]["prompt"]
    assert "麻烦看下背面贴袋" in prompt       # 本轮叙事在场
    assert "五袋款带小表袋裤耳" not in prompt  # 第 1 轮叙事整段不复述
    assert "【已确认状态" in prompt
    assert "尺寸：腰围74" in prompt           # 摘要=账本终值（无空格拼接）
    assert "【上次视觉判断" in prompt          # 第 1 轮认出的 curved 可见
    assert "waistband_type: curved" in prompt


def test_b1_first_turn_prompt_unchanged(tmp_path):
    """首轮（turn==1）不注摘要段/基线段——与拆分前 prompt 逐位同形（回退）。"""
    p1 = tmp_path / "front.png"
    p1.write_bytes(b"aaa")
    vlm = FakeVLM([_S2_REPLY])
    run_turn(Session(), _DESC, (str(p1),), provider=vlm)
    prompt = vlm.calls[0]["prompt"]
    assert "【已确认状态" not in prompt
    assert "【上次视觉判断" not in prompt
    assert "五袋款带小表袋裤耳" in prompt      # 首轮叙事=describe 原样在场


def test_b1_s1_fill_uses_full_history():
    """S1 补漏保持全史输入（拆分只切 S2）：第 2 轮 S1 prompt 仍含第 1 轮
    叙事原文——早轮报过的数字仍能从历史里捞。"""
    vlm = FakeVLM(['{"back_rise": null}', '{"back_rise": null}'])
    out1 = run_turn(Session(), _DESC_MISSING, (), provider=vlm)
    out2 = run_turn(out1.session, "还是没说后浪", (), provider=vlm)
    assert out2.card is not None             # 仍缺 -> 再卡（S1 拿历史问不到）
    assert len(vlm.calls) == 2
    s1_prompt = vlm.calls[1]["prompt"]
    assert "从下面这段服装描述文字中提取" in s1_prompt
    assert _DESC_MISSING in s1_prompt        # 全史输入：第 1 轮原文在场
    assert "还是没说后浪" in s1_prompt        # 本轮文本也在


# -- C 照片三类（2026-09-29）：meta 注入 + vlm_cache 迁移 + 补照精准化 ----------

def test_c_photo_meta_prompt_and_cache(tmp_path):
    """photo_meta 随轮发出：S2 prompt 注【照片清单】（类别重点清单）、
    vlm_cache.photos 落 {d, c, n} 行（C5 新格式）。"""
    p1 = tmp_path / "f.png"
    p1.write_bytes(b"fff")
    vlm = FakeVLM([_S2_REPLY])
    meta = [{"category": "front", "note": ""}]
    out = run_turn(Session(), _DESC, (str(p1),), photo_meta=meta,
                   provider=vlm)
    assert out.delivery is not None
    prompt = vlm.calls[0]["prompt"]
    assert "【照片清单（类别为用户标注" in prompt
    assert "第1张 正面平铺：重点看前口袋形态与弧深、门襟、小表袋" in prompt
    rows = out.session.vlm_cache["photos"]
    assert len(rows) == 1 and rows[0]["c"] == "front" and rows[0]["n"] == ""


def test_c_vlm_cache_legacy_string_migrates(tmp_path):
    """硬约束 4 前向兼容：旧会话 vlm_cache.photos 字符串读入迁移 any
    （类别不可知不猜）；本轮补新照片后落账统一 {d, c, n} 新格式（旧行
    保留）。"""
    session = Session()
    session.vlm_cache = {
        "entries": {"waistband_type": {"value": "curved",
                                       "confidence": 0.85,
                                       "evidence": "腰头上口下凹弧线"}},
        "dropped": [], "photos": ["abc123"]}
    p2 = tmp_path / "b.png"
    p2.write_bytes(b"bbb")
    vlm = FakeVLM([_S2_REPLY])
    out = run_turn(session, _DESC, (str(p2),),
                   photo_meta=[{"category": "back", "note": "背面平铺"}],
                   provider=vlm)
    assert out.delivery is not None
    rows = out.session.vlm_cache["photos"]
    by_c = {r["c"]: r for r in rows}
    assert by_c["any"]["d"] == "abc123"          # 旧行迁移保留
    assert by_c["back"]["n"] == "背面平铺"        # 新照片带类别+说明


def test_c_missing_card_want_photos_precision(tmp_path):
    """C6 补照精准化：按已见类别只提缺的那面——只正面 → 只提背面；
    正反齐全 → 不劝补拍；other-only → 两面都提；旧会话 any → 不猜。"""
    def want_for(bodies_and_meta):
        paths = []
        for i, (body, _m) in enumerate(bodies_and_meta):
            p = tmp_path / f"p{i}.png"
            p.write_bytes(body)
            paths.append(str(p))
        vlm = FakeVLM(['{"back_rise": null}'])
        out = run_turn(Session(), "女款牛仔裤", paths,
                       photo_meta=[m for _b, m in bodies_and_meta],
                       provider=vlm)
        assert out.card is not None
        return out.card.want_photos

    assert want_for([(b"f", {"category": "front", "note": ""})]) == \
        ["背面平铺照"]
    assert want_for([(b"b", {"category": "back", "note": ""})]) == \
        ["正面平铺照"]
    assert want_for([(b"f", {"category": "front", "note": ""}),
                     (b"b", {"category": "back", "note": ""})]) == []
    assert want_for([(b"o", {"category": "other", "note": "侧面"})]) == \
        ["正面平铺照", "背面平铺照"]

    # 旧会话照片行（any）+ 本轮无照片：类别不可知 -> 旧行为不劝补拍
    session = Session()
    session.vlm_cache = {
        "entries": {"waistband_type": {"value": "curved", "confidence": 0.85,
                                       "evidence": "侧缝处下凹"}},
        "dropped": [], "photos": ["abc123"]}
    vlm = FakeVLM(['{"back_rise": null}'])
    out = run_turn(session, "女款牛仔裤", (), provider=vlm)
    assert out.card is not None
    assert out.card.want_photos == []


def test_http_chat_photo_meta_invalid():
    """photo_meta 非法 422：非 JSON / 非数组（app.py Form 解析口径）。"""
    client = _client()
    for bad, frag in [("{not json", "photo_meta"),
                      ('"abc"', "JSON 数组")]:
        r = client.post("/api/chat/turn",
                        data={"session": Session().to_json(),
                              "text": "x", "photo_meta": bad})
        assert r.status_code == 422, (bad, r.text)
        assert frag in r.json()["detail"]


# -- CLI ----------------------------------------------------------------------

def test_cli_chat_two_turns_deliver(tmp_path, monkeypatch):
    """stdin 两轮：缺后浪问一次 → 补答交卷，exit 0 出双产物。"""
    monkeypatch.chdir(tmp_path)                        # 隔离 cwd vlm.toml
    monkeypatch.setattr(sys, "stdin",
                        io.StringIO(_DESC_MISSING + "\n后浪33\n"))
    from agent.cli import main
    rc = main(["chat", "--out-dir", "out"])
    assert rc == 0
    assert (tmp_path / "out" / "extracted.toml").is_file()
    assert (tmp_path / "out" / "extract_report.md").is_file()


def test_cli_chat_quit_no_delivery(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO("缺尺寸的描述\n:quit\n"))
    from agent.cli import main
    rc = main(["chat", "--out-dir", "out"])
    assert rc == 1
    assert not (tmp_path / "out" / "extracted.toml").exists()


# -- HTTP（会话随请求往返，后端无状态） ------------------------------------------

def _client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from agent.app import app
    return TestClient(app)


def test_http_chat_roundtrip(monkeypatch):
    """两轮 HTTP：卡片 → 补答交卷；会话 JSON 在请求间往返。"""
    client = _client()
    import agent.runner
    vlm = FakeVLM(['{"back_rise": null}'])
    monkeypatch.setattr(agent.runner, "_build_provider", lambda p: vlm)
    r1 = client.post("/api/chat/turn",
                     data={"session": Session().to_json(),
                           "text": _DESC_MISSING})
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["ok"] is True and b1["card"] and b1["delivery"] is None
    r2 = client.post("/api/chat/turn",
                     data={"session": json.dumps(b1["session"]),
                           "text": "后浪33"})
    b2 = r2.json()
    assert r2.status_code == 200, r2.text
    assert b2["card"] is None
    assert b2["delivery"]["measurements"]["back_rise"] == 33.0
    assert len(vlm.calls) == 1


def test_http_chat_bad_session_400(monkeypatch):
    client = _client()
    r = client.post("/api/chat/turn",
                    data={"session": "{not json", "text": _DESC})
    assert r.status_code == 400
    assert "会话" in r.json()["detail"]


def test_http_chat_progress_lines(monkeypatch):
    """分阶段耗时行随响应回传（2026-10-01）：「[相对秒] 消息」格式；
    带照轮必含「S2 视觉确认」行——前端灰字气泡的数据源（此前 HTTP 侧
    progress=None 静默，只有 CLI 打 stderr）。"""
    client = _client()
    import agent.runner
    vlm = FakeVLM([_S2_REPLY])
    monkeypatch.setattr(agent.runner, "_build_provider", lambda p: vlm)
    r = client.post("/api/chat/turn",
                    data={"session": Session().to_json(), "text": _DESC},
                    files=[("photos", ("front.png", b"png-bytes",
                                       "image/png"))])
    assert r.status_code == 200, r.text
    lines = r.json()["progress"]
    assert len(lines) > 0
    assert all(ln.startswith("[") and "s] " in ln for ln in lines)
    assert any("S2 视觉确认" in ln for ln in lines)


# -- HTTP 复盘金标（2026-09-30 用户「对话失败 422」实炸链） -----------------------

def _browser_multipart(fields, photo=None):
    """浏览器字节形态 multipart：空串字段如实成 part。

    httpx data= 会把零长度表单字段整个丢掉（客户端侧），用 TestClient
    常规姿势测不出服务端真实行为——python-multipart 解析层同样丢弃零长度
    part，必填 text 收不到即 RequestValidationError。此处手工拼字节。
    """
    b = "----yltestboundary"
    out = bytearray()
    for name, value in fields.items():
        out += (f"--{b}\r\nContent-Disposition: form-data; "
                f"name=\"{name}\"\r\n\r\n{value}\r\n").encode()
    if photo is not None:
        fname, content = photo
        out += (f"--{b}\r\nContent-Disposition: form-data; name=\"photos\"; "
                f"filename=\"{fname}\"\r\nContent-Type: image/jpeg\r\n\r\n"
                ).encode() + content + b"\r\n"
    out += f"--{b}--\r\n".encode()
    return bytes(out), b


def test_http_chat_empty_text_part_browser_bytes(monkeypatch):
    """D5 续发轮 text='' 422 复盘金标（2026-09-30）：directive 后前端自动
    附片续发带空 text，python-multipart 丢零长度 part -> 必填 text 缺失
    RequestValidationError。修法 text Form(default='')；空 text + 新照片
    走正常 intake 通路。"""
    client = _client()
    import agent.runner
    vlm = FakeVLM(['{"back_rise": null}'])
    monkeypatch.setattr(agent.runner, "_build_provider", lambda p: vlm)
    body, boundary = _browser_multipart(
        {"session": Session().to_json(), "text": ""},
        photo=("1.jpg", b"\xff\xd8\xff\xe0fake"))
    r = client.post("/api/chat/turn", content=body,
                    headers={"Content-Type":
                             f"multipart/form-data; boundary={boundary}"})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_http_chat_bad_photo_suffix_422(monkeypatch):
    """照片后缀非法 422（契约「照片非法 422」）：_save_photos 曾在 try 外
    实炸 500，2026-09-30 移入 try 同走照片非法 422。"""
    client = _client()
    r = client.post("/api/chat/turn",
                    data={"session": Session().to_json(), "text": "x"},
                    files={"photos": ("a.tiff", b"II*\x00fake", "image/tiff")})
    assert r.status_code == 422, r.text
    assert "后缀" in r.json()["detail"]
