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
- max_tokens 默认 16384：思维链计入 completion，8192 会把 30+ 键 JSON 掐到
  0 字符（finish_reason=length 时显式报错而非静默截断）。
- thinking 参数默认**不发送**（走服务端默认）；"on"/"off" 才发送
  （数值调用建议 off，实测 4.7s vs 思维链全开数百秒）。HTTP 400 自动摘参重发
  一次并 sticky（后续调用不再带）——部分端点不认该参数。
- 照片读文件 + base64 data URI 只存在于本层。
"""

from __future__ import annotations

import base64
import json
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
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


class VLMError(RuntimeError):
    """VLM 调用失败（配置缺失/HTTP 错误/超时/输出被掐断）。"""


class _ThinkingRejected(Exception):
    """HTTP 400 且请求带了 thinking 参数——摘参重发一次（内部信号）。"""


@dataclass(frozen=True)
class VLMConfig:
    """VLM 接入配置（vlm.toml / 环境变量解析结果）。"""

    api_key: str
    base_url: str = _DEFAULT_BASE_URL
    model: str = _DEFAULT_MODEL
    max_tokens: int = 16384          # 思维链计入 completion，勿低于此值
    timeout_idle: float = 300.0      # SSE 相邻数据行间隔上限（秒）
    thinking: str | None = None      # None=不发送该参数；"on"/"off" 强制

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
            max_tokens=int(data.get("max_tokens") or 16384),
            timeout_idle=float(data.get("timeout_idle") or 300.0),
            thinking=thinking,
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

    def complete(self, prompt: str, images: tuple[str, ...] | list[str] = (),
                 thinking: str | None = None) -> str:
        """一次补全。thinking：None=回落 config.thinking（仍 None 则不发送）；
        "on"/"off" 强制。返回拼接后的正文文本。"""
        effective = thinking if thinking is not None else self.config.thinking
        if effective is not None and self._thinking_dropped:
            effective = None
        try:
            return self._request(prompt, images, effective)
        except _ThinkingRejected:
            self._thinking_dropped = True
            return self._request(prompt, images, None)

    # -- 内部 ----------------------------------------------------------

    def _request(self, prompt: str, images, thinking: str | None) -> str:
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
            raise VLMError(f"VLM HTTP {e.code}：{detail}") from None
        except (socket.timeout, TimeoutError) as e:
            raise VLMError(f"VLM 连接超时（>{cfg.timeout_idle:.0f}s）") from e
        with resp:
            return _read_sse(resp, cfg.timeout_idle)


def _read_sse(resp, timeout_idle: float) -> str:
    """逐行读 SSE data: 块，聚合 delta.content；空闲超时按行间隔计。"""
    parts: list[str] = []
    finish: str | None = None
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
                       "思维链计入 completion，请保持 max_tokens >= 16384")
    if not parts:
        raise VLMError("VLM 返回空内容（无 delta.content）")
    return "".join(parts)


class FakeVLM:
    """测试替身：按序重放假响应，记录每次调用（prompt/images/thinking）。"""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, prompt: str, images: tuple[str, ...] | list[str] = (),
                 thinking: str | None = None) -> str:
        self.calls.append({"prompt": prompt, "images": list(images),
                           "thinking": thinking})
        if not self._responses:
            raise AssertionError("FakeVLM 响应队列已耗尽")
        return self._responses.pop(0)
