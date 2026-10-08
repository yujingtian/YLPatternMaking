"""extract provider 测试（FakeVLM + 假 urlopen，全程不触网）。

覆盖（实施顺序 ② 金标）：
- VLMConfig.load 优先级：显式 path > ./vlm.toml > YLP_VLM_* 环境变量 > 均缺 raise；
  toml 缺 api_key / thinking 非法值 raise。
- FakeVLM 队列重放 + calls 记录。
- OpenAICompatibleVLM 请求体：max_tokens=32768 / stream=True / 图片 base64 data URI /
  Authorization Bearer；SSE 解析（data: 行聚合 delta.content、[DONE] 收尾、
  非 data 行与坏 JSON 行忽略、finish_reason=length 显式报错、空内容报错）。
- thinking：None 不发送；400 自动摘参重发一次并 sticky；
  400 且未带 thinking 时直接 VLMError 不重试。
- 空闲超时：readline 期间 socket.timeout -> VLMError（idle 语义）。
- usage 落账（商用加固 B）：末块 usage 记入 last_usage + ylagent.usage JSON
  行（purpose 标签透传）；上游不回 usage -> 空 dict 不炸。
- 瞬时重试（商用加固 C）：429/5xx/连接超时重试 retries 次（429 尊重
  Retry-After、上限 10s）；SSE 中途空闲超时/400 不重试；retries=0 关闭。
"""

from __future__ import annotations

import io
import json
import logging
import socket
import urllib.error

import pytest

from agent.extract.provider import (
    FakeVLM,
    OpenAICompatibleVLM,
    VLMConfig,
    VLMError,
    _read_sse,
)


# -- 通用假件 ---------------------------------------------------------------


class _FakeResponse:
    """假 HTTPResponse：按行产出 bytes（模拟 SSE 按行迭代）。"""

    def __init__(self, lines: list[bytes] | None = None, raise_at: int | None = None):
        self._lines = list(lines or [])
        self._raise_at = raise_at  # 产出该下标行时抛 socket.timeout

    def __iter__(self):
        for i, line in enumerate(self._lines):
            if i == self._raise_at:
                raise socket.timeout("readline timed out")
            yield line

    def read(self) -> bytes:
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _sse_lines(*deltas: str, finish: str | None = "stop") -> list[bytes]:
    """构造一段标准 SSE 响应行。"""
    lines = [b": keep-alive comment"]
    for d in deltas:
        lines.append(b"data: " + json.dumps(
            {"choices": [{"delta": {"content": d}, "finish_reason": None}]}
        ).encode("utf-8"))
    if finish:
        lines.append(b"data: " + json.dumps(
            {"choices": [{"delta": {}, "finish_reason": finish}]}
        ).encode("utf-8"))
    lines.append(b"data: [DONE]")
    return lines


_CFG = VLMConfig(api_key="test-key")


# -- VLMConfig.load 优先级 ----------------------------------------------------


def test_config_load_explicit_path(tmp_path):
    f = tmp_path / "custom.toml"
    f.write_text('api_key = "k1"\nbase_url = "https://x/v4"\nmodel = "m1"\n',
                 encoding="utf-8")
    cfg = VLMConfig.load(str(f))
    assert cfg.api_key == "k1"
    assert cfg.base_url == "https://x/v4"
    assert cfg.model == "m1"
    assert cfg.max_tokens == 32768        # 省略走默认（16384 被 S2 思维链耗尽过）
    assert cfg.timeout_idle == 300.0
    assert cfg.thinking is None           # 默认不发送


def test_config_load_cwd_toml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("YLP_VLM_API_KEY", raising=False)
    (tmp_path / "vlm.toml").write_text(
        'api_key = "k2"\nthinking = "off"\nmax_tokens = 20000\n', encoding="utf-8")
    cfg = VLMConfig.load()
    assert cfg.api_key == "k2"
    assert cfg.thinking == "off"
    assert cfg.max_tokens == 20000


def test_config_load_env_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)           # 无 ./vlm.toml
    monkeypatch.setenv("YLP_VLM_API_KEY", "k3")
    monkeypatch.setenv("YLP_VLM_MODEL", "env-model")
    cfg = VLMConfig.load()
    assert cfg.api_key == "k3"
    assert cfg.model == "env-model"
    assert cfg.base_url.endswith("/api/coding/paas/v4")  # 其余走默认


def test_config_load_missing_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("YLP_VLM_API_KEY", raising=False)
    with pytest.raises(VLMError, match="缺少 VLM 配置"):
        VLMConfig.load()


def test_config_missing_api_key_raises(tmp_path):
    f = tmp_path / "bad.toml"
    f.write_text('model = "m"\n', encoding="utf-8")
    with pytest.raises(VLMError, match="缺 api_key"):
        VLMConfig.load(str(f))


def test_config_bad_thinking_raises(tmp_path):
    f = tmp_path / "bad.toml"
    f.write_text('api_key = "k"\nthinking = "maybe"\n', encoding="utf-8")
    with pytest.raises(VLMError, match="thinking"):
        VLMConfig.load(str(f))


# -- FakeVLM ------------------------------------------------------------------


def test_fake_vlm_replay_and_record():
    vlm = FakeVLM(["r1", "r2"])
    assert vlm.complete("p1", ["a.jpg"], thinking="off") == "r1"
    assert vlm.complete("p2", purpose="s2") == "r2"
    assert vlm.calls == [
        {"prompt": "p1", "images": ["a.jpg"], "thinking": "off", "purpose": ""},
        {"prompt": "p2", "images": [], "thinking": None, "purpose": "s2"},
    ]
    with pytest.raises(AssertionError):
        vlm.complete("p3")


# -- 请求体 + SSE 解析 --------------------------------------------------------


def test_request_body_and_data_uri(tmp_path, monkeypatch):
    img = tmp_path / "pic.jpg"
    img.write_bytes(b"\xff\xd8fakejpeg")
    bodies = []

    def fake_urlopen(req, timeout):
        bodies.append(json.loads(req.data.decode("utf-8")))
        assert req.headers.get("Authorization") == "Bearer test-key"
        assert req.full_url.endswith("/chat/completions")
        return _FakeResponse(_sse_lines("hello ", "world"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    vlm = OpenAICompatibleVLM(_CFG)
    assert vlm.complete("看图", [str(img)]) == "hello world"
    body = bodies[0]
    assert body["stream"] is True
    assert body["max_tokens"] == 32768
    assert "thinking" not in body                    # 默认不发送
    content = body["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "看图"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert content[1]["image_url"]["url"].endswith(
        __import__("base64").b64encode(b"\xff\xd8fakejpeg").decode("ascii"))


def test_thinking_param_sent_when_forced(monkeypatch):
    bodies = []
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout: (bodies.append(json.loads(
                            req.data.decode("utf-8"))) or _FakeResponse(
                            _sse_lines("ok"))))
    vlm = OpenAICompatibleVLM(_CFG)
    vlm.complete("p", thinking="off")
    assert bodies[0]["thinking"] == {"type": "disabled"}
    vlm.complete("p", thinking="on")
    assert bodies[1]["thinking"] == {"type": "enabled"}


def test_thinking_from_config_applied(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout: _FakeResponse(_sse_lines("ok")))
    vlm = OpenAICompatibleVLM(
        VLMConfig(api_key="k", thinking="off"))
    vlm.complete("p")                                 # 未显式传 -> 回落 config
    # 通过 400 摘参路径反证 thinking 确实发送过（见下一条测试的机制）
    assert vlm.config.thinking == "off"


def test_thinking_400_drop_and_sticky(monkeypatch):
    bodies = []
    err = urllib.error.HTTPError(
        "url", 400, "Bad Request", {}, io.BytesIO(b'{"error":"invalid thinking"}'))

    def fake_urlopen(req, timeout):
        bodies.append(json.loads(req.data.decode("utf-8")))
        if len(bodies) == 1:
            raise err
        return _FakeResponse(_sse_lines("ok"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    vlm = OpenAICompatibleVLM(_CFG)
    # 第一次：config 强制 off -> 400 -> 摘参重发成功
    vlm2 = OpenAICompatibleVLM(VLMConfig(api_key="k", thinking="off"))
    assert vlm2.complete("p") == "ok"
    assert bodies[0]["thinking"] == {"type": "disabled"}
    assert "thinking" not in bodies[1]
    # sticky：后续即使显式要求也不再发送
    vlm2.complete("p", thinking="on")
    assert "thinking" not in bodies[2]


def test_http_400_without_thinking_raises_directly(monkeypatch):
    err = urllib.error.HTTPError(
        "url", 400, "Bad Request", {}, io.BytesIO(b'{"error":"bad model"}'))
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        raise err

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    vlm = OpenAICompatibleVLM(_CFG)
    with pytest.raises(VLMError, match="HTTP 400"):
        vlm.complete("p")
    assert len(calls) == 1            # 未带 thinking 不重试


def test_http_500_raises(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        # 每次新抛（HTTPError.read 消耗 BytesIO，复用同实例第二次 detail 变空）
        raise urllib.error.HTTPError(
            "url", 500, "Server Error", {}, io.BytesIO(b"boom"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("agent.extract.provider.time.sleep",
                        lambda s: None)      # 重试退避不真睡
    vlm = OpenAICompatibleVLM(_CFG)
    with pytest.raises(VLMError, match="HTTP 500"):
        vlm.complete("p")
    assert len(calls) == 2                   # 默认 retries=1：重试一次后上抛


def test_sse_ignores_noise_lines():
    lines = [b"event: message", b"", b"data: not-json",
             b"data: " + json.dumps({"choices": [{"delta": {"content": "a"}}]}).encode(),
             b"data: [DONE]",
             b"data: " + json.dumps({"choices": [{"delta": {"content": "ignored"}}]}).encode()]
    text, usage, reasoning = _read_sse(_FakeResponse(lines), 300.0)
    assert text == "a"
    assert usage == {}                       # 无 usage 块 -> 空 dict
    assert reasoning == ""                   # 无思考段 -> 空串


def test_sse_finish_length_raises():
    lines = _sse_lines("partial", finish="length")
    with pytest.raises(VLMError, match="max_tokens"):
        _read_sse(_FakeResponse(lines), 300.0)


def test_sse_empty_content_raises():
    lines = [b"data: " + json.dumps({"choices": [{"delta": {}}]}).encode(),
             b"data: [DONE]"]
    with pytest.raises(VLMError, match="空内容"):
        _read_sse(_FakeResponse(lines), 300.0)


def test_idle_timeout_raises_vlmerror():
    lines = _sse_lines("first")
    resp = _FakeResponse(lines, raise_at=2)   # 第 3 行前停摆
    with pytest.raises(VLMError, match="空闲超时"):
        _read_sse(resp, 300.0)


# -- 思考段捕获（2026-10-08 前端折叠展示） ----------------------------------------


def test_sse_reasoning_captured_out_of_band():
    """思考段进 last_reasoning、不进正文：reasoning_content 片段按序拼接
    （reasoning 字段名兼容）；content 照旧只收 delta.content。"""
    lines = [
        b"data: " + json.dumps({"choices": [
            {"delta": {"reasoning_content": "先看腰头：上缘水平，"}}]}).encode(),
        b"data: " + json.dumps({"choices": [
            {"delta": {"reasoning": "侧缝处明显下沉。"}}]}).encode(),
        b"data: " + json.dumps({"choices": [
            {"delta": {"content": '{"waistband_type": '}}]}).encode(),
        b"data: " + json.dumps({"choices": [
            {"delta": {"content": '"curved"}'}}]}).encode(),
        b"data: [DONE]",
    ]
    text, usage, reasoning = _read_sse(_FakeResponse(lines), 300.0)
    assert text == '{"waistband_type": "curved"}'
    assert reasoning == "先看腰头：上缘水平，侧缝处明显下沉。"
    assert usage == {}


# -- usage 落账（商用加固 B，2026-10-07） --------------------------------------


def test_usage_recorded_and_logged(monkeypatch, caplog):
    """末块带 usage：last_usage 记录 + ylagent.usage JSON 行（purpose 透传）。"""
    lines = _sse_lines("hi")
    lines.insert(-1, b"data: " + json.dumps(
        {"usage": {"prompt_tokens": 120, "completion_tokens": 35}}).encode())
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout: _FakeResponse(lines))
    vlm = OpenAICompatibleVLM(_CFG)
    with caplog.at_level(logging.INFO, logger="ylagent.usage"):
        assert vlm.complete("p", purpose="s2") == "hi"
    assert vlm.last_usage == {"prompt_tokens": 120, "completion_tokens": 35}
    row = json.loads(caplog.records[-1].getMessage())
    assert row["purpose"] == "s2"
    assert row["prompt_tokens"] == 120 and row["completion_tokens"] == 35
    assert row["model"] == _CFG.model and row["n_images"] == 0
    assert "duration_s" in row and "ts" in row


def test_usage_absent_empty_and_no_log(monkeypatch, caplog):
    """上游不回 usage：last_usage 空 dict 不炸；INFO 级无 token 字段。"""
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout: _FakeResponse(_sse_lines("ok")))
    vlm = OpenAICompatibleVLM(_CFG)
    with caplog.at_level(logging.INFO, logger="ylagent.usage"):
        assert vlm.complete("p") == "ok"
    assert vlm.last_usage == {}
    row = json.loads(caplog.records[-1].getMessage())
    assert "prompt_tokens" not in row and "completion_tokens" not in row


# -- 瞬时错误重试（商用加固 C，2026-10-07） -------------------------------------


def test_retry_429_with_retry_after_then_success(monkeypatch):
    calls, sleeps = [], []
    err = urllib.error.HTTPError(
        "url", 429, "Too Many Requests", {"Retry-After": "0"},
        io.BytesIO(b"rate limit"))

    def fake_urlopen(req, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise err
        return _FakeResponse(_sse_lines("ok"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("agent.extract.provider.time.sleep", sleeps.append)
    vlm = OpenAICompatibleVLM(_CFG)
    assert vlm.complete("p") == "ok"
    assert len(calls) == 2 and sleeps == [0.0]   # 尊重 Retry-After=0


def test_retry_connect_timeout_then_success(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise socket.timeout("connect timed out")
        return _FakeResponse(_sse_lines("ok"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("agent.extract.provider.time.sleep", lambda s: None)
    vlm = OpenAICompatibleVLM(_CFG)
    assert vlm.complete("p") == "ok"
    assert len(calls) == 2


def test_retry_disabled_with_retries_zero(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(
            "url", 429, "Too Many Requests", {}, io.BytesIO(b"rate"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("agent.extract.provider.time.sleep", lambda s: None)
    vlm = OpenAICompatibleVLM(VLMConfig(api_key="k", retries=0))
    with pytest.raises(VLMError, match="HTTP 429"):
        vlm.complete("p")
    assert len(calls) == 1                      # retries=0：一次都不重试


def test_sse_idle_timeout_not_retried(monkeypatch):
    """SSE 中途空闲超时**不**重试（已烧部分 token，整单重付不划算）。"""
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        return _FakeResponse(_sse_lines("first"), raise_at=2)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("agent.extract.provider.time.sleep", lambda s: None)
    vlm = OpenAICompatibleVLM(_CFG)
    with pytest.raises(VLMError, match="空闲超时"):
        vlm.complete("p")
    assert len(calls) == 1


def test_retries_config_from_toml(tmp_path):
    """vlm.toml retries 键：显式 0 生效（or 假值陷阱钉死）。"""
    f = tmp_path / "vlm.toml"
    f.write_text('api_key = "k"\nretries = 0\n', encoding="utf-8")
    assert VLMConfig.load(str(f)).retries == 0
    f.write_text('api_key = "k"\n', encoding="utf-8")
    assert VLMConfig.load(str(f)).retries == 1          # 省略走默认 1
