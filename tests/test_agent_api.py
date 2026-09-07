"""agent 服务 API 测试：TestClient + FakeVLM 全程离线（§10.9）。

注入缝 = monkeypatch agent.runner._build_provider（见 runner docstring）。
注意 _build_provider 返回 FakeVLM 后门面忽略 config_path，故不受本机
仓库根 vlm.toml 影响（纯描述用例也不会触发真调用）。
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient    # noqa: E402

import agent.runner                          # noqa: E402
from agent.app import app                    # noqa: E402
from agent.extract.provider import FakeVLM, VLMError  # noqa: E402

client = TestClient(app)

_DESC = ("女款高腰小脚牛仔裤，腰围74 臀围91 膝围44 脚口34 前浪25 后浪33 "
         "裤长102 大腿围58，微弹面料，五袋款带小表袋裤耳")
_DESC_MISSING = "女款小脚牛仔裤，腰围74 臀围91 膝围44 脚口34 前浪25 裤长102"

_S2_REPLY = json.dumps({
    "front_patch": {"value": True, "confidence": 0.9,
                    "evidence": "正面照腰下明贴袋，双针明线可见"},
}, ensure_ascii=False)

_PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89")


def _use_fake(monkeypatch, vlm):
    monkeypatch.setattr(agent.runner, "_build_provider", lambda p: vlm)


def _extract(vlm, monkeypatch, *, describe=_DESC, files=(), **form):
    _use_fake(monkeypatch, vlm)
    data = {"describe": describe, **form}
    return client.post("/api/extract", data=data, files=list(files))


def test_extract_full(monkeypatch):
    """照片+完整描述：200、信封 + payload 六键、逐键溯源形状。"""
    vlm = FakeVLM([_S2_REPLY])
    files = [("photos", ("front.png", _PNG, "image/png")),
             ("photos", ("back.png", _PNG, "image/png"))]
    r = _extract(vlm, monkeypatch, files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["photo_count"] == 2
    assert set(body) >= {"ok", "model", "photo_count", "measurements",
                         "options", "keys", "issues", "probe", "score"}
    assert body["measurements"]["waist"] == 74.0
    assert "delta" in body["options"]
    assert set(body["keys"]["delta"]) == {"value", "source", "confidence",
                                          "evidence"}
    # 尺寸键也进 keys（source=描述 + evidence 溯源；前端确认屏徽章数据源）
    assert body["keys"]["waist"]["source"] == "描述"
    assert body["keys"]["waist"]["confidence"] == 1.0
    assert body["keys"]["waist"]["value"] == 74.0
    assert len(vlm.calls) == 1                      # S2 恰一次（S1 全中）
    assert len(vlm.calls[0]["images"]) == 2


def test_extract_missing_required_422(monkeypatch):
    """缺必填尺寸（CLI exit 2 同语义）-> 422 + 缺键 param 清单。"""
    _use_fake(monkeypatch, FakeVLM(['{"back_rise": null}']))   # 补漏答 null
    r = client.post("/api/extract", data={"describe": _DESC_MISSING})
    assert r.status_code == 422
    params = [d["param"] for d in r.json()["detail"]]
    assert params == ["back_rise"]
    assert all(d["level"] == "error" for d in r.json()["detail"])


def test_extract_vlm_unconfigured_503(monkeypatch):
    """有照片 + VLM 配置缺失 -> 503，消息不含 key。"""
    def _raise(config_path):
        raise VLMError("缺少 VLM 配置（vlm.toml 或 YLP_VLM_API_KEY）")
    monkeypatch.setattr(agent.runner, "_build_provider", _raise)
    r = client.post("/api/extract", data={"describe": _DESC},
                    files=[("photos", ("front.png", _PNG, "image/png"))])
    assert r.status_code == 503
    assert "缺少 VLM 配置" in r.json()["detail"]
    assert "api_key" not in r.text or "sk-" not in r.text


def test_extract_bad_photo_suffix_422(monkeypatch):
    _use_fake(monkeypatch, FakeVLM([]))
    r = client.post("/api/extract", data={"describe": _DESC},
                    files=[("photos", ("evil.txt", b"x", "text/plain"))])
    assert r.status_code == 422
    assert "后缀" in r.json()["detail"]


def test_extract_empty_photo_422(monkeypatch):
    _use_fake(monkeypatch, FakeVLM([]))
    r = client.post("/api/extract", data={"describe": _DESC},
                    files=[("photos", ("front.png", b"", "image/png"))])
    assert r.status_code == 422
    assert "空文件" in r.json()["detail"]


def test_extract_thinking_passthrough(monkeypatch):
    """thinking=off 透传到 provider.complete。"""
    vlm = FakeVLM([_S2_REPLY])
    _extract(vlm, monkeypatch,
             files=[("photos", ("front.png", _PNG, "image/png"))],
             thinking="off")
    assert vlm.calls[0]["thinking"] == "off"


def test_extract_pure_describe_zero_calls(monkeypatch):
    """纯描述：FakeVLM([]) 空队列哨兵——一次都不该调。"""
    r = _extract(FakeVLM([]), monkeypatch)
    assert r.status_code == 200
    body = r.json()
    assert body["photo_count"] == 0 and body["model"]


def test_photo_tempdir_cleaned(monkeypatch, tmp_path):
    """照片临时目录用后即删（runner TemporaryDirectory 上下文口径）。"""
    import agent.runner as runner_mod
    vlm = FakeVLM([_S2_REPLY])
    seen = {}

    orig = runner_mod.extract_from_input

    def _spy(**kwargs):
        seen["paths"] = kwargs["photos"]
        return orig(**kwargs)

    monkeypatch.setattr(runner_mod, "_build_provider", lambda p: vlm)
    monkeypatch.setattr(runner_mod, "extract_from_input", _spy)
    r = _extract(vlm, monkeypatch,
                 files=[("photos", ("front.png", _PNG, "image/png"))])
    assert r.status_code == 200
    import os
    assert all(not os.path.exists(p) for p in seen["paths"])


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["vlm_configured"], bool)
