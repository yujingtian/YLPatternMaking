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
