"""FastAPI 入口：参数 schema 下发 / 打版生成 / DXF 下载 / 模板。

薄壳层：全部计算走 ylpattern 引擎（flows + exporters 内存渲染），
不落盘、不复制任何公式。启动：
    pip install -e ".[web]"
    uvicorn webapp.backend.app:app --reload
"""

from __future__ import annotations

import io
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from ylpattern.exporters import dxf as dxf_exp
from ylpattern.exporters import piece_dxf as piece_dxf_exp
from ylpattern.exporters import piece_svg as piece_exp
from ylpattern.exporters import report as report_exp
from ylpattern.exporters import svg as svg_exp
from ylpattern.flows.collect import collect_pieces
from ylpattern.flows.closure import run_with_thigh_closure
from ylpattern.params import (Measurements, PatternOptions, build_issues)

from .schema import build_schema

app = FastAPI(title="YLPattern Web", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173"],  # Vite dev
    allow_methods=["*"], allow_headers=["*"])

# 生产：前端构建产物由本进程托管（单进程部署）
_DIST = Path(__file__).resolve().parents[2] / "webapp" / "frontend" / "dist"
if (_DIST / "assets").is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"),
              name="assets")

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


class DraftRequest(BaseModel):
    measurements: dict
    options: dict = {}


def _build(req: DraftRequest):
    """校验 + 构造 (Measurements, PatternOptions)；有 error 级问题 -> 422。"""
    issues = build_issues(req.measurements, req.options)
    errors = [i for i in issues if i.level == "error"]
    if errors:
        raise HTTPException(422, detail=[
            {"param": i.param, "group": i.group, "message": i.message,
             "level": i.level} for i in errors])
    m = Measurements.from_dict(req.measurements)
    o = PatternOptions.from_dict(req.options)
    warnings = [{"param": i.param, "group": i.group, "message": i.message,
                 "level": i.level} for i in issues if i.level == "warning"]
    return m, o, warnings


def _draft_ctx(req: DraftRequest):
    m, o, warnings = _build(req)
    ctx, _trace = run_with_thigh_closure(m, o)
    return m, o, ctx, warnings


@app.get("/api/schema")
def get_schema() -> dict:
    return build_schema()


@app.post("/api/draft")
def draft(req: DraftRequest) -> dict:
    """整版 SVG + 动态裁片清单（各裁片 SVG）+ 报表文本。"""
    m, o, ctx, warnings = _draft_ctx(req)
    pieces, skips = collect_pieces(ctx)
    return {
        "ok": True,
        "sheet_svg": svg_exp.render_sheet(ctx.sheet),
        "report": report_exp.render_report(ctx.sheet, m, o),
        "pieces": [{"key": p.name, "name": p.label, "count": 1,
                    "svg": piece_exp.render_piece_svg(
                        p, show_seam=o.show_seam_allowance)}
                   for p in pieces],
        "skips": skips,
        "warnings": warnings,
    }


@app.post("/api/dxf")
def dxf(req: DraftRequest, kind: str = "pieces") -> Response:
    """DXF 下载：pieces = 裁片合集平铺（默认）；sheet = 整版。"""
    if kind not in ("pieces", "sheet"):
        raise HTTPException(400, "kind 须为 pieces / sheet")
    _, o, ctx, _ = _draft_ctx(req)
    if kind == "sheet":
        doc = dxf_exp.render_sheet_dxf(ctx.sheet)
        name = "sheet.dxf"
    else:
        pieces, _ = collect_pieces(ctx)
        doc = piece_dxf_exp.render_pieces_dxf(
            pieces, size=o.size_label, show_seam=o.show_seam_allowance)
        name = "pieces.dxf"
    buf = io.StringIO()
    doc.write(buf)
    return Response(buf.getvalue(), media_type="application/dxf",
                    headers={"Content-Disposition":
                             f'attachment; filename="{name}"'})


@app.post("/api/toml")
def export_toml(req: DraftRequest) -> Response:
    """当前参数导出为尺寸单 toml（可作 CLI --size 输入，双向兼容）。"""
    from .tomlout import render_size_toml
    return Response(render_size_toml(req.measurements, req.options),
                    media_type="application/toml",
                    headers={"Content-Disposition":
                             'attachment; filename="size_draft.toml"'})


@app.get("/api/templates")
def templates() -> list[dict]:
    return [{"name": p.stem, "file": p.name}
            for p in sorted(_EXAMPLES.glob("size_*.toml"))]


@app.get("/api/templates/{name}")
def template_detail(name: str) -> dict:
    """模板内容（measurements + options，前端表单一键填充）。"""
    import tomllib
    path = _EXAMPLES / name
    if not path.is_file():
        raise HTTPException(404, f"模板不存在:{name}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    # 展平缝份子表到 options（与 POST /api/draft 的 options 口径一致）
    options = {k: v for k, v in data.get("options", {}).items()}
    for key, val in list(options.items()):
        if isinstance(val, dict):
            options[key] = val
    return {"measurements": data.get("measurements", {}),
            "options": options,
            "size_run": data.get("size_run")}


@app.get("/")
def index() -> Response:
    dist = _DIST / "index.html"
    if dist.is_file():
        return FileResponse(dist)
    return Response(
        "前端未构建：cd webapp/frontend && npm install && npm run build\n"
        "开发模式：npm run dev 后访问 http://localhost:5173",
        media_type="text/plain; charset=utf-8")


if __name__ == "__main__":
    # 本文件含包内相对导入，不能 cd 进本目录用 python app.py 直跑；
    # 正确启动：项目根目录执行 python -m uvicorn webapp.backend.app:app
    raise SystemExit(
        "请在项目根目录启动：python -m uvicorn webapp.backend.app:app --reload")
