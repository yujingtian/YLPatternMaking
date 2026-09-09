"""FastAPI 入口：参数 schema 下发 / 两步生成（整版/裁片）/ DXF 下载 / 模板。

薄壳层：全部计算走 ylpattern 引擎（flows + exporters 内存渲染），
不落盘、不复制任何公式。启动：
    pip install -e ".[web]"
    uvicorn webapp.backend.app:app --reload
"""

from __future__ import annotations

import io
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ylpattern.exporters import dxf as dxf_exp
from ylpattern.exporters import fitting as fitting_exp
from ylpattern.exporters import piece_dxf as piece_dxf_exp
from ylpattern.exporters import piece_svg as piece_exp
from ylpattern.exporters import report as report_exp
from ylpattern.exporters import svg as svg_exp
from ylpattern.flows.adjust import solve_param
from ylpattern.flows.collect import collect_pieces
from ylpattern.flows.closure import run_with_thigh_closure
from ylpattern.api import run_size_run_groups, size_run_from_dict
from ylpattern.params import (Measurements, PatternOptions, build_issues)

from .schema import binding_for, build_schema, handles, seed_shape

app = FastAPI(title="YLPattern Web", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173"],  # Vite dev
    allow_methods=["*"], allow_headers=["*"])

# 生产：前端构建产物由本进程托管（单进程部署）。本地引擎资产同源下发：
#   /engine/<zip 内容 hash 文件名>、/pyodide/<版本>/ —— 均 immutable 长缓存；
#   /engine/manifest.json 是唯一每次冷启动都要拿最新的（zip 名变了即换新包），
#   专用 no-store 路由先注册、目录挂载后注册（Starlette 按注册顺序匹配）
_DIST = Path(__file__).resolve().parents[2] / "webapp" / "frontend" / "dist"


class _ImmutableStatic(StaticFiles):
    """内容寻址静态资产（hash/版本文件名）：immutable 一年缓存。"""

    def file_response(self, *args, **kwargs) -> Response:
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


if (_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"),
              name="assets")
if (_DIST / "engine").is_dir():

    @app.get("/engine/manifest.json")
    def engine_manifest() -> FileResponse:
        path = _DIST / "engine" / "manifest.json"
        if not path.is_file():
            raise HTTPException(
                404, "engine manifest 未生成：npm run build:engine")
        return FileResponse(path, headers={"Cache-Control": "no-store"})

    app.mount("/engine", _ImmutableStatic(directory=_DIST / "engine"),
              name="engine")
if (_DIST / "pyodide").is_dir():
    app.mount("/pyodide", _ImmutableStatic(directory=_DIST / "pyodide"),
              name="pyodide")

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


class DraftRequest(BaseModel):
    measurements: dict
    options: dict = {}
    size_run: dict | None = None   # 推板码表（仅 kind=size_run / toml 消费，
                                   # sheet/pieces/adjust/seed 忽略）


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


@app.post("/api/draft/sheet")
def draft_sheet(req: DraftRequest) -> dict:
    """整版 SVG + 报表文本（两步生成第一步；不收集裁片）。

    二期拖拽扩展：transform（px↔cm 仿射常量，与 SVG 根 data-* 同源）与
    handles（当前版面上的可调把手坐标 cm）。
    """
    m, o, ctx, warnings = _draft_ctx(req)
    _w, _h, top, ox = svg_exp.compute_view(ctx.sheet)
    return {
        "ok": True,
        "sheet_svg": svg_exp.render_sheet(ctx.sheet,
                                          show_labels=o.show_labels),
        "report": report_exp.render_report(ctx.sheet, m, o),
        "transform": {"scale": svg_exp.SCALE, "ox": ox, "top": top},
        "handles": handles(ctx, o),
        "warnings": warnings,
    }


class AdjustRequest(BaseModel):
    """拖拽反解请求：把手沿绑定轴拖到 target（版坐标 cm，Y 向上）。"""

    measurements: dict
    options: dict = {}
    element: str
    param: str
    axis: str
    target: float


@app.post("/api/adjust")
def adjust(req: AdjustRequest) -> dict:
    """拖拽反解（二期双向绑定）：目标坐标 -> 参数值，stateless。

    流程：当前参数过 _build（422 = 参数本身有错）→ 查 ADJUSTABLES
    （未注册绑定 422）→ solve_param 在 [lo, hi] 数值求根（定位参数 t
    由绑定表下发，不取请求值）。求解器护栏内不抛出——钳制/no_effect
    也 200（拖拽中不弹错，前端按 reason 显示钳制态）；仅基线不可生成
    （配置/测量矛盾）转 422。同步 def 走线程池，引擎纯函数线程安全。
    """
    m, o, _warnings = _build(DraftRequest(measurements=req.measurements,
                                          options=req.options))
    adj = binding_for(req.element, req.param, req.axis)
    if adj is None:
        raise HTTPException(
            422, f"未注册的可调绑定：{req.element} {req.param} "
                 f"{req.axis}（见 /api/schema adjustable_points）")
    try:
        r = solve_param(m, o, element=adj.element, param=adj.param,
                        axis=adj.axis, target=req.target,
                        lo=adj.lo, hi=adj.hi, t=adj.t)
    except ValueError as e:        # 基线不可生成：配置/测量矛盾
        raise HTTPException(422, str(e))
    return {"ok": True, "converged": r.converged, "value": r.value,
            "params": {adj.param: r.value},
            "achieved": r.achieved, "residual": r.residual,
            "reason": r.reason, "evaluations": r.evaluations}


class SeedRequest(BaseModel):
    """从形态导入请求：kind 侧 + 预设 shape + 当前 options（仅取贴袋
    5 尺寸参数；不带 measurements、不走 _build——其余参数中间态非法时
    seed 也要可用，避免无谓 422 耦合）。"""

    kind: str
    shape: str
    options: dict = {}


@app.post("/api/seed")
def seed(req: SeedRequest) -> dict:
    """预设形态 -> custom 初始角点/边（贴袋编辑器「从形态导入」）。

    纯函数（webschema.seed_shape -> formulas.patch / formulas.pouch），同步
    def 走线程池；非法 kind/shape/尺寸 -> 422（与 Pyodide 胶水 validation
    同构，前端不触发通道回退）。
    """
    try:
        return seed_shape(req.kind, req.shape, req.options)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/draft/pieces")
def draft_pieces(req: DraftRequest) -> dict:
    """动态裁片清单（各裁片 SVG）+ 跳过说明（两步生成第二步）。

    先整版后裁片仅为前端 UI 门控口径（先画后裁）；后端无状态，
    本端点自跑整版引擎再提取裁片。
    """
    _, o, ctx, warnings = _draft_ctx(req)
    pieces, skips = collect_pieces(ctx)
    return {
        "ok": True,
        "pieces": [{"key": p.name, "name": p.label, "count": 1,
                    "svg": piece_exp.render_piece_svg(
                        p, show_seam=o.show_seam_allowance)}
                   for p in pieces],
        "skips": skips,
        "warnings": warnings,
    }


@app.post("/api/draft/fitting")
def draft_fitting(req: DraftRequest) -> dict:
    """3D 试穿 payload（§10.11）：前后片净样边链（整版全局坐标 cm、Y 向上）
    + 人台放样站点 + 腰头标量。与 Pyodide 胶水 _fitting 逐字段同构
    （tests/test_engine_glue.py 钉死全等）；size_run 忽略。
    """
    m, _o, ctx, warnings = _draft_ctx(req)
    return {"ok": True, **fitting_exp.build_fitting_payload(ctx, m),
            "warnings": warnings}


@app.post("/api/dxf")
def dxf(req: DraftRequest, kind: str = "pieces") -> Response:
    """DXF 下载：pieces = 裁片合集平铺（默认）；sheet = 整版；
    size_run = 多码推码合集（逐码重打版，码表来自 DraftRequest.size_run）。"""
    if kind not in ("pieces", "sheet", "size_run"):
        raise HTTPException(400, "kind 须为 pieces / sheet / size_run")
    if kind == "size_run":
        m, o, _ = _build(req)     # 基码构造+校验；逐码重打版在内存核心里
        if not req.size_run:
            raise HTTPException(422, "推板导出缺少 [size_run] 配置"
                                      "（请先在推板设置抽屉完成配置）")
        try:
            run = size_run_from_dict(m, o, req.size_run)
            _ctxs, groups, _rows, _tr = run_size_run_groups(run, o)
        except ValueError as e:   # 码表/档差/逐码展开非法（消息带码标签）
            raise HTTPException(422, str(e))
        doc = piece_dxf_exp.render_size_run_dxf(
            groups, sample_size=run.base, style_name=run.style_name,
            show_seam=o.show_seam_allowance)
        name = "size_run.dxf"     # 固定名：base 可能非 ASCII，不进 header
    else:
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
    """当前参数导出为尺寸单 toml（可作 CLI --size 输入，双向兼容；
    配置过推板时带 [size_run] 段 = CLI 多码推码模式）。"""
    from .tomlout import render_size_toml
    return Response(render_size_toml(req.measurements, req.options,
                                     req.size_run),
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
    # 展平缝份子表到 options（与生成端点的 options 口径一致）
    options = {k: v for k, v in data.get("options", {}).items()}
    for key, val in list(options.items()):
        if isinstance(val, dict):
            options[key] = val
    return {"measurements": data.get("measurements", {}),
            "options": options,
            "size_run": data.get("size_run")}


# agent 服务同源转发（一期前端接线 §10.9）：dev 由 Vite proxy /agent -> 8001，
# 生产（dist 由本进程托管）无 Vite，故此处 httpx 原样字节透传——前端 dev/prod
# 同构、零 CORS 依赖。multipart 直传（≤4×10MB，内存可承受）；超时 310s 对齐
# agent uvicorn 空闲 300s；agent 未启动 -> 502（中文消息，前端弹层直显）。
_AGENT_BASE = os.environ.get("YLP_AGENT_BASE", "http://localhost:8001")


@app.api_route("/agent/{path:path}", methods=["GET", "POST"])
async def agent_forward(path: str, request: Request) -> Response:
    import httpx   # 懒加载（同 ezdxf 先例）：未装 httpx 只影响本路由
    try:
        async with httpx.AsyncClient(base_url=_AGENT_BASE,
                                     timeout=httpx.Timeout(310)) as client:
            resp = await client.request(
                request.method, f"/{path}", content=await request.body(),
                headers={"content-type": request.headers.get("content-type", "")})
    except httpx.HTTPError:
        raise HTTPException(
            502, "agent 服务未启动或不可达（默认 http://localhost:8001，"
                 "可用环境变量 YLP_AGENT_BASE 覆盖）")
    return Response(resp.content, status_code=resp.status_code,
                    media_type=resp.headers.get("content-type", ""))


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
