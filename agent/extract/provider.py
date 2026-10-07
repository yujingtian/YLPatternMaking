"""VLM 服务商接入（extract 唯一触网文件，urllib stdlib，零第三方依赖）。

接口（管线依赖的鸭子协议，FakeVLM 同构）：
    complete(prompt, images=(), thinking=None) -> str

- VLMConfig.load(path=None)：配置解析，优先级 显式 path > ./vlm.toml >
  环境变量 YLP_VLM_*（YLP_VLM_API_KEY / _BASE_URL / _MODEL / _THINKING），
  均缺 raise RuntimeError（提示配置方法，测试环境无配置不受影响）。
- OpenAICompatibleVLM.complete：OpenAI 兼容 chat/completions，恒流式 SSE 按行读。
- FakeVLM(responses)：队列重放假响应 + calls 记录，测试全程不触网。

踩坑清单（2026-08~09 实测，勿回退）：
- 端点默认 https://open.bigmodel.cn/api/coding/paas/v4（智谱 Coding Plan 套餐 key，
  普通 /api/paas/v4 端点不共享套餐额度）、模型默认 glm-5.3-flash；
  glm-4v-flash 结构识别失明（照片键全部 value=false conf=1.0 自相矛盾），禁用。
- 恒流式 SSE：空闲超时按「两次有数据行间隔」计（默认 300s，socket timeout 落在
  每次 recv 上即自然达成），**不设整包短超时**——推理模型思维链数百秒，
  整包 300s 超时会废掉生成重发全价重跑。
- max_tokens 默认 32768：思维链计入 completion，8192 会把 30+ 键 JSON 掐到
  0 字符；16384 也曾被 S2 带图思维链整轮耗尽（2026-10-01（二）实炸，
  finish_reason=length 时显式报错而非静默截断）。
- thinking 参数默认**不发送**（走服务端默认）；"on"/"off" 才发送
  （数值调用建议 off，实测 4.7s vs 思维链全开数百秒）。HTTP 400 自动摘参重发
  一次并 sticky（后续调用不再带）——部分端点不认该参数。
- usage 落账（商用加固 B，2026-10-07）：SSE **任意** data chunk 出现 usage 键
  即记录（不预设位置——各供应商有的放末块、有的要 stream_options 才回，
  解析不到就空 dict 不报错）——实例属性 last_usage + "ylagent.usage" logger
  每次调用一行 JSON（ts/model/purpose/duration_s/n_images/prompt_tokens/
  completion_tokens）；purpose 由调用点传（s1 补漏/s2 视觉/adjust 映射/
  recheck 复查），区分哪段贵。YLP_USAGE_LOG=1 模块自挂 stderr handler；
  CLI 侧调 enable_usage_log()。
- 瞬时错误重试（商用加固 C，2026-10-07）：HTTP 429/5xx/连接超时按
  config.retries 自动重试（默认 1 次；429 尊重 Retry-After 上限 10s、
  否则固定 2s）；SSE 中途空闲超时 / finish_reason=length **不**重试——
  已烧部分 token 整单重付不划算，交上层 503 + usage 日志人工判断。
  口径 .doc/agent商用加固一期设计.md B/C 项。
- 照片读文件 + base64 data URI 只存在于本层。
"""

from __future__ import annotations

import base64
import json
import logging
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - 3.10 环境
    import tomli as tomllib

# 图片扩展名 -> data URI MIME（读不到的扩展名按 jpeg 兜底，最常见）
_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
         ".webp": "image/webp", ".bmp": "image/bmp", ".gif": "image/gif"}

_DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
_DEFAULT_MODEL = "glm-5.3-flash"

# -- usage 日志（商用加固 B）：默认静默（root WARNING 吞 INFO），两处开法 ------
#   YLP_USAGE_LOG=1 环境变量（uvicorn 部署）/ CLI 调 enable_usage_log()。
_USAGE = logging.getLogger("ylagent.usage")
if os.environ.get("YLP_USAGE_LOG"):
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("%(message)s"))
    _USAGE.addHandler(_h)
    _USAGE.setLevel(logging.INFO)
    _USAGE.propagate = False


def enable_usage_log() -> None:
    """CLI 侧启用 usage 日志（stderr、INFO、每行一个 JSON）。幂等。"""
    if _USAGE.level != logging.INFO:
        _h = logging.StreamHandler(sys.stderr)
        _h.setFormatter(logging.Formatter("%(message)s"))
        _USAGE.addHandler(_h)
        _USAGE.setLevel(logging.INFO)
        _USAGE.propagate = False


class VLMError(RuntimeError):
    """VLM 调用失败（配置缺失/HTTP 错误/超时/输出被掐断）。"""


class _TransientVLMError(VLMError):
    """瞬时失败（HTTP 429/5xx/连接超时）——可安全重试（调用无状态）。

    retry_after：来自 Retry-After 头的秒数（无/非法为 None -> 固定退避）。
    继承 VLMError：重试耗尽后原样上抛即满足 503 契约，上层零感知。
    """

    def __init__(self, message: str, retry_after: float | None):
        super().__init__(message)
        self.retry_after = retry_after


_RETRY_BACKOFF = 2.0        # 固定退避（秒）
_RETRY_BACKOFF_MAX = 10.0   # Retry-After 上限


def _retry_after(err: urllib.error.HTTPError) -> float | None:
    """Retry-After 头 -> 秒数；缺失/HTTP 日期格式/非法 -> None。"""
    try:
        v = err.headers.get("Retry-After") if err.headers else None
    except AttributeError:
        return None
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None                       # HTTP-date 等格式不认，走固定退避


class _ThinkingRejected(Exception):
    """HTTP 400 且请求带了 thinking 参数——摘参重发一次（内部信号）。"""


@dataclass(frozen=True)
class VLMConfig:
    """VLM 接入配置（vlm.toml / 环境变量解析结果）。"""

    api_key: str
    base_url: str = _DEFAULT_BASE_URL
    model: str = _DEFAULT_MODEL
    max_tokens: int = 32768          # 思维链计入 completion；16384 被 S2 带图
                                     # 思维链耗尽过（2026-10-01），勿降回
    timeout_idle: float = 300.0      # SSE 相邻数据行间隔上限（秒）
    thinking: str | None = None      # None=不发送该参数；"on"/"off" 强制
    retries: int = 1                 # 瞬时错误（429/5xx/连接超时）重试次数，
                                     # 0=关（商用加固 C）

    @classmethod
    def load(cls, path: str | None = None) -> "VLMConfig":
        """按优先级解析配置：显式 path > ./vlm.toml > 环境变量；均缺 raise。"""
        data = cls._load_raw(path)
        if data is None:
            raise VLMError(
                "缺少 VLM 配置：复制 vlm.toml.example 为 vlm.toml 并填入 api_key，"
                "或设置环境变量 YLP_VLM_API_KEY（可选 YLP_VLM_BASE_URL / "
                "YLP_VLM_MODEL / YLP_VLM_THINKING）")
        api_key = str(data.get("api_key") or "").strip()
        if not api_key:
            raise VLMError("VLM 配置缺 api_key（vlm.toml 或 YLP_VLM_API_KEY）")
        thinking = data.get("thinking")
        if thinking is not None and thinking not in ("on", "off"):
            raise VLMError(f"thinking 只支持 \"on\"/\"off\" 或不配置，得到 {thinking!r}")
        return cls(
            api_key=api_key,
            base_url=str(data.get("base_url") or _DEFAULT_BASE_URL),
            model=str(data.get("model") or _DEFAULT_MODEL),
            max_tokens=int(data.get("max_tokens") or 32768),
            timeout_idle=float(data.get("timeout_idle") or 300.0),
            thinking=thinking,
            retries=max(0, int(data["retries"])) if data.get("retries") is not None
            else 1,
        )

    @staticmethod
    def _load_raw(path: str | None) -> dict | None:
        if path:                       # 显式路径：文件必须存在
            with open(path, "rb") as fp:
                return tomllib.load(fp)
        if Path("vlm.toml").is_file():  # 工作目录约定位置
            with open("vlm.toml", "rb") as fp:
                return tomllib.load(fp)
        import os
        if os.environ.get("YLP_VLM_API_KEY"):   # 环境变量兜底
            return {k.removeprefix("YLP_VLM_").lower(): v
                    for k, v in os.environ.items() if k.startswith("YLP_VLM_")}
        return None


def _data_uri(image_path: str) -> str:
    """本地图片 -> base64 data URI（仅本函数接触图片文件）。"""
    suffix = Path(image_path).suffix.lower()
    mime = _MIME.get(suffix, "image/jpeg")
    payload = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


class OpenAICompatibleVLM:
    """OpenAI 兼容端点的流式调用封装。"""

    def __init__(self, config: VLMConfig):
        self.config = config
        self._thinking_dropped = False   # 400 摘参后 sticky：后续不再发送
        self.last_usage: dict = {}       # 最近一次调用的 usage（空=上游没回）

    def complete(self, prompt: str, images: tuple[str, ...] | list[str] = (),
                 thinking: str | None = None, purpose: str = "") -> str:
        """一次补全。thinking：None=回落 config.thinking（仍 None 则不发送）；
        "on"/"off" 强制。purpose：调用点标签（s1/s2/adjust/recheck，进 usage
        日志行区分哪段贵，不影响请求体）。返回拼接后的正文文本。"""
        effective = thinking if thinking is not None else self.config.thinking
        if effective is not None and self._thinking_dropped:
            effective = None
        t0 = time.monotonic()
        try:
            text, usage = self._complete_retry(prompt, images, effective)
        except _ThinkingRejected:
            self._thinking_dropped = True
            text, usage = self._complete_retry(prompt, images, None)
        self.last_usage = usage
        self._log_usage(purpose, usage, t0, len(images))
        return text

    # -- 内部 ----------------------------------------------------------

    def _complete_retry(self, prompt, images, thinking):
        """瞬时错误重试层（商用加固 C）：429/5xx/连接超时重试 config.retries
        次；其余（含 _ThinkingRejected、SSE 中途超时、length 掐断）原样抛。"""
        attempts = max(1, self.config.retries + 1)
        err: _TransientVLMError | None = None
        for attempt in range(attempts):
            try:
                return self._request(prompt, images, thinking)
            except _TransientVLMError as e:
                err = e
                if attempt + 1 < attempts:
                    delay = (e.retry_after if e.retry_after is not None
                             else _RETRY_BACKOFF)
                    time.sleep(min(delay, _RETRY_BACKOFF_MAX))
        raise err                        # 重试耗尽：VLMError 子类，503 契约不变

    def _log_usage(self, purpose: str, usage: dict, t0: float,
                   n_images: int) -> None:
        """usage 日志行（商用加固 B）：INFO 级 JSON，未启用直接返回。"""
        if not _USAGE.isEnabledFor(logging.INFO):
            return
        row = {"ts": datetime.now().isoformat(timespec="seconds"),
               "model": self.config.model, "purpose": purpose,
               "duration_s": round(time.monotonic() - t0, 2),
               "n_images": n_images}
        if "prompt_tokens" in usage:
            row["prompt_tokens"] = usage["prompt_tokens"]
        if "completion_tokens" in usage:
            row["completion_tokens"] = usage["completion_tokens"]
        _USAGE.info(json.dumps(row, ensure_ascii=False))

    def _request(self, prompt: str, images,
                 thinking: str | None) -> tuple[str, dict]:
        cfg = self.config
        content: list[dict] = [{"type": "text", "text": prompt}]
        for p in images:
            content.append({"type": "image_url",
                            "image_url": {"url": _data_uri(p)}})
        body: dict = {
            "model": cfg.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": cfg.max_tokens,
            "stream": True,
        }
        if thinking in ("on", "off"):
            body["thinking"] = {"type": "enabled" if thinking == "on"
                                          else "disabled"}
        req = urllib.request.Request(
            cfg.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {cfg.api_key}"},
            method="POST")
        try:
            # socket timeout 落在每次 recv：流式按行读时即「相邻数据行间隔」上限
            resp = urllib.request.urlopen(req, timeout=cfg.timeout_idle)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            if e.code == 400 and "thinking" in body:
                raise _ThinkingRejected(detail) from None
            if e.code == 429 or e.code >= 500:
                raise _TransientVLMError(f"VLM HTTP {e.code}：{detail}",
                                         _retry_after(e)) from None
            raise VLMError(f"VLM HTTP {e.code}：{detail}") from None
        except (socket.timeout, TimeoutError) as e:
            raise _TransientVLMError(
                f"VLM 连接超时（>{cfg.timeout_idle:.0f}s）", None) from e
        with resp:
            return _read_sse(resp, cfg.timeout_idle)


def _read_sse(resp, timeout_idle: float) -> tuple[str, dict]:
    """逐行读 SSE data: 块，聚合 delta.content + usage；空闲超时按行间隔计。

    usage：任意 data chunk 出现 usage 键即并入（后块覆盖前块的部分值），
    上游不回则空 dict——不预设位置，各供应商行为不一（见模块 docstring）。
    """
    parts: list[str] = []
    finish: str | None = None
    usage: dict = {}
    try:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue            # 注释行/事件行等非数据行
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue            # 尾部 usage 等非 JSON 行
            u = chunk.get("usage")
            if isinstance(u, dict):
                usage.update(u)
            for choice in chunk.get("choices", ()):
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    parts.append(delta["content"])
                if choice.get("finish_reason"):
                    finish = choice["finish_reason"]
    except (socket.timeout, TimeoutError) as e:
        raise VLMError(f"VLM 流式读取空闲超时（>{timeout_idle:.0f}s 无数据，"
                      "推理模型思维链可能仍在生成，勿设整包短超时）") from e
    if finish == "length":
        raise VLMError("VLM 输出被 max_tokens 掐断（finish_reason=length）："
                       "思维链计入 completion，请保持 max_tokens >= 32768"
                       "（vlm.toml 可配）；急用可临时关 thinking 绕行")
    if not parts:
        raise VLMError("VLM 返回空内容（无 delta.content）")
    return "".join(parts), usage


class FakeVLM:
    """测试替身：按序重放假响应，记录每次调用（prompt/images/thinking/purpose）。"""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, prompt: str, images: tuple[str, ...] | list[str] = (),
                 thinking: str | None = None, purpose: str = "") -> str:
        self.calls.append({"prompt": prompt, "images": list(images),
                           "thinking": thinking, "purpose": purpose})
        if not self._responses:
            raise AssertionError("FakeVLM 响应队列已耗尽")
        return self._responses.pop(0)
