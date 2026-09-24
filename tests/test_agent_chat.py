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
    vlm = FakeVLM([])
    out1 = run_turn(Session(), _DESC, (), provider=vlm)
    out2 = run_turn(out1.session, "腰围75", (), provider=vlm)
    assert out2.delivery["measurements"]["waist"] == 75.0
    led = replay(out2.session)
    assert led.measurements["waist"].turn == 2


def test_photo_batch_cache_and_hint_priority(tmp_path):
    """带照轮恰 1 次 S2；纯文字轮缓存命中 0 新调用 + 词典覆盖照片。"""
    photo = tmp_path / "front.png"
    photo.write_bytes(b"png-bytes")
    vlm = FakeVLM([_S2_REPLY])
    out1 = run_turn(Session(), _DESC, (str(photo),), provider=vlm)
    assert len(vlm.calls) == 1
    assert out1.delivery["keys"]["waistband_type"]["value"] == "curved"
    # 同一张照片全量重发 + 文字改口：缓存命中（无新指纹）不二次调模型
    out2 = run_turn(out1.session, "直腰头", (str(photo),), provider=vlm)
    assert len(vlm.calls) == 1
    wb = out2.delivery["keys"]["waistband_type"]
    assert wb["value"] == "straight" and wb["source"] == "描述"
    assert out2.session.vlm_cache["photos"]            # 指纹已落账


def test_new_photo_second_batch(tmp_path):
    """中途补的照片是新指纹：第二轮 S2 带新照片再调一次，证据覆盖。"""
    p1 = tmp_path / "a.png"
    p1.write_bytes(b"aaa")
    p2 = tmp_path / "b.png"
    p2.write_bytes(b"bbb")
    vlm = FakeVLM([_S2_REPLY,
                   json.dumps({"back_patch": {"value": False,
                                              "confidence": 0.8,
                                              "evidence": "背面照无贴袋"}},
                              ensure_ascii=False)])
    out1 = run_turn(Session(), _DESC, (str(p1),), provider=vlm)
    out2 = run_turn(out1.session, "换个角度看", (str(p1), str(p2)),
                    provider=vlm)
    assert len(vlm.calls) == 2
    assert len(vlm.calls[1]["images"]) == 1            # 只送新照片 b
    bp = out2.delivery["keys"]["back_patch"]
    assert bp["value"] is False and "背面照" in bp["evidence"]


def test_rollback_truncate_replays():
    """回滚：截断到 turn 1 重放，腰围回到 74。"""
    vlm = FakeVLM([])
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
