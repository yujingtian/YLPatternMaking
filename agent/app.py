"""LLM agent 后端服务入口：POST /api/extract + GET /healthz。

启动（项目根）：
    pip install -e ".[agent]"
    python -m uvicorn agent.app:app --port 8001

与 webapp/backend 同为薄壳（引擎/提取库零改动）；独立进程独立端口——
VLM 长请求（空闲超时默认 300s）与交互式打版服务互不干扰。端点用 sync
def：FastAPI 自动走 Starlette threadpool，不阻塞事件循环。一期同步等待
返回（前端未接线、量小）；二期会话/记忆/job 在本包内扩展（§10.9）。
"""

from __future__ import annotations

import time

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from agent.extract import ExtractError
from agent.extract.provider import VLMError

from .config import resolve_config_path
from .runner import run_extract

app = FastAPI(title="YLPattern Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173"],  # Vite dev
    allow_methods=["*"], allow_headers=["*"])


@app.get("/healthz")
def healthz() -> dict:
    """存活 + VLM 是否已配置（只回 bool，配置内容不回显）。"""
    try:
        from agent.extract.provider import VLMConfig
        VLMConfig.load(resolve_config_path())
        configured = True
    except Exception:
        configured = False
    return {"status": "ok", "vlm_configured": configured}


def _progress_sink(t0: float, lines: list[str]):
    """管线 progress 回调 -> 「[相对秒] 消息」行收集器（随响应体回传前端）。

    CLI 走 stderr 直打不受影响；HTTP 侧此前 progress=None 静默（同步等待
    无处展示），带图轮次动辄分钟级，分阶段耗时对用户是关键反馈
    （S2 行自带「耗时 xx s」，2026-10-01）。
    """
    def sink(msg: str) -> None:
        lines.append(f"[{time.monotonic() - t0:6.1f}s] {msg}")
    return sink


@app.post("/api/chat/turn")
def api_chat_turn(session: str = Form(...), text: str = Form(default=""),
                  photos: list[UploadFile] = File(default=[]),
                  photo_meta: str | None = Form(default=None),
                  fulfill: str | None = Form(default=None),
                  thinking: str | None = Form(default=None),
                  run_probe: bool = Form(default=True),
                  run_score: bool = Form(default=True),
                  max_refeed: int = Form(default=2)) -> dict:
    """多轮对话一轮（智能体一期，§10.9）：会话 JSON 随请求往返，后端无状态。

    请求：session（上轮返回的会话 JSON 串，首轮 "{}" 或空对象序列化）+
    text（可空——D5 续发轮次 B 无文本；注意 python-multipart 会把零长度
    表单字段整个丢弃，客户端发了也到不了这里，故必须 default 而非必填）+
    photos（前端持的全部照片全量重发，后端按指纹去重只送新照片进
    S2）+ photo_meta（可选 JSON 串：[{name, category, note}] 按 photos
    顺序对齐，C 照片三类 2026-09-29）+ fulfill（可选，当前仅 "recheck"：
    定向复查两段握手轮次 B，D 2026-09-29——响应 directive 后前端自动附
    类别照片续发）。响应：{ok, session, card, delivery, directive,
    progress}——card/delivery/directive 三选一；缺必填不 422，转求援卡
    （零打扰口径）；progress = 分阶段耗时行（2026-10-01：管线 progress
    回调带「[相对秒] 前缀」随响应回传，前端气泡展示——此前 HTTP 侧同步
    等待无处展示，只有 CLI 打 stderr）。

    错误口径同 /api/extract：照片非法 422、会话 JSON 非法 400、
    photo_meta 非法 422、fulfill 非法 422、VLM 未配置/上游失败 503
    （原消息，不含 key）。
    """
    import json as _json

    from .converse import run_turn
    from .runner import _build_provider, _save_photos
    from .session import Session as ChatSession

    config_path = resolve_config_path()
    try:
        sess = ChatSession.from_json(session)
    except (ValueError, TypeError, KeyError) as e:
        raise HTTPException(400, detail=f"会话 JSON 非法：{e}") from None
    meta: list[dict] | None = None
    if photo_meta:
        try:
            parsed = _json.loads(photo_meta)
        except ValueError as e:
            raise HTTPException(422, detail=f"photo_meta 非法：{e}") from None
        if not isinstance(parsed, list):
            raise HTTPException(422, detail="photo_meta 非法：应为 JSON 数组")
        meta = parsed
    if fulfill is not None and fulfill != "recheck":
        raise HTTPException(422,
                            detail=f"fulfill 非法：{fulfill!r}（当前仅支持 recheck）")
    tmp = None
    t0 = time.monotonic()
    progress_lines: list[str] = []
    try:
        # _save_photos 的 ValueError（照片后缀/空文件/超限/超张数）同走照片
        # 非法 422 契约——此前在 try 外，实炸为 500（2026-09-30 修）
        paths, tmp = _save_photos(photos)
        outcome = run_turn(sess, text, paths, photo_meta=meta,
                           fulfill=fulfill,
                           provider=_build_provider(config_path),
                           thinking=thinking, run_probe=run_probe,
                           run_score=run_score, max_refeed=max_refeed,
                           config_path=config_path,
                           progress=_progress_sink(t0, progress_lines))
    except ValueError as e:
        raise HTTPException(422, detail=str(e)) from None
    except ExtractError as e:
        raise HTTPException(503, detail=str(e)) from None
    except VLMError as e:
        raise HTTPException(503, detail=str(e)) from None
    finally:
        if tmp is not None:
            tmp.cleanup()
    body = outcome.to_dict()
    body["ok"] = True
    body["progress"] = progress_lines
    return body


@app.post("/api/extract")
def api_extract(
    describe: str = Form(...),
    photos: list[UploadFile] = File(default=[]),
    thinking: str | None = Form(default=None),
    run_probe: bool = Form(default=True),
    run_score: bool = Form(default=True),
    max_refeed: int = Form(default=2),
) -> dict:
    """照片 + 描述 -> 参数提取（to_web_payload 契约 + 信封）。

    错误口径：缺必填尺寸/照片非法 -> 422（detail 带 param 清单或消息）；
    VLM 未配置/上游失败 -> 503（原消息，不含 key）。
    """
    config_path = resolve_config_path()
    try:
        return run_extract(describe, photos, thinking=thinking,
                           run_probe=run_probe, run_score=run_score,
                           max_refeed=max_refeed, config_path=config_path)
    except ValueError as e:          # 照片非法
        raise HTTPException(422, detail=str(e)) from None
    except ExtractError as e:
        if e.missing:                # CLI exit 2 同语义：缺必填清单
            raise HTTPException(422, detail=[
                {"param": k,
                 "message": "描述与模型补漏后仍缺必填尺寸（不编数值）",
                 "level": "error"} for k in e.missing]) from None
        raise HTTPException(503, detail=str(e)) from None
    except VLMError as e:            # 配置缺失/上游错误/超时/截断
        raise HTTPException(503, detail=str(e)) from None


if __name__ == "__main__":
    print("启动：python -m uvicorn agent.app:app --port 8001 "
          "（项目根；需 pip install -e \".[agent]\"）")
