"""worker 胶水金标：engine_glue.handle 与 FastAPI 端点逐字段全等。

浏览器本地引擎（Pyodide worker，webapp/engine_glue.py）与后端 HTTP 通道
（webapp/backend/app.py）并行存在，两份实现的语义一致性由本文件钉死：
同输入下成功响应**全等**（含 SVG 字符串与全部浮点——两边调的是同一
引擎纯函数，输出确定）；错误口径同构（validation <-> 422）。
漂移即红：改任何一端必须同步另一端再跑本文件。
依赖 fastapi + httpx，缺失时整文件跳过（同 test_web_adjust.py）。
"""

import json

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from webapp import engine_glue  # noqa: E402
from webapp.backend.app import app  # noqa: E402

ADJ_M = dict(waist=70, hip=96, knee=46, hem=36,
             front_rise=25, back_rise=33, outseam=102, thigh=58)
POCKET_ON = {"front_pocket": True}
REQ = {"measurements": ADJ_M, "options": POCKET_ON}

client = TestClient(app)


def _glue(cmd: str, payload: dict) -> dict:
    return json.loads(engine_glue.handle(cmd, json.dumps(payload)))


def _handle(body: dict, element: str) -> dict:
    return next(h for h in body["handles"] if h["element"] == element)


# ---------- 成功响应全等（含 SVG 字符串） ----------

def test_sheet_glue_equals_http():
    http = client.post("/api/draft/sheet", json=REQ).json()
    glue = _glue("sheet", REQ)
    assert glue == http
    assert glue["sheet_svg"] == http["sheet_svg"]      # SVG 逐字符
    assert len(glue["handles"]) == len(http["handles"]) == 16


def test_pieces_glue_equals_http():
    http = client.post("/api/draft/pieces", json=REQ).json()
    assert _glue("pieces", REQ) == http


def test_seed_glue_equals_http():
    """seed 全等：三预设形态 × 前后侧（纯函数，输出确定）。
    入参只带贴袋尺寸子集——seed 不走 _build，其余参数缺失/非法不影响。"""
    for kind in ("back_patch", "front_patch"):
        opts = {f"{kind}_width": 14, f"{kind}_height": 16,
                f"{kind}_bottom_width": 12, f"{kind}_tip_depth": 2.5,
                f"{kind}_chamfer": 2}
        for shape in ("rectangle", "baker_shield", "angular"):
            req = {"kind": kind, "shape": shape, "options": opts}
            http = client.post("/api/seed", json=req).json()
            assert _glue("seed", req) == http
            assert http["ok"] is True and len(http["points"]) >= 4


def test_seed_pouch_glue_equals_http():
    """seed 袋布链全等：三袋型（边为完整 spec 格式，含 arc 模式）；
    options 缺安全量时走 4/8 缺省（中间态可用）。"""
    for shape in ("standard", "round_bottom", "deep_rect"):
        for opts in ({"front_pouch_waist_safe": 5,
                      "front_pouch_side_safe": 10}, {}):
            req = {"kind": "front_pouch", "shape": shape, "options": opts}
            http = client.post("/api/seed", json=req).json()
            assert _glue("seed", req) == http
            assert http["ok"] is True
            assert len(http["edges"]) == len(http["points"]) + 1
            assert all(isinstance(e[0], str) for e in http["edges"])


def test_seed_invalid_matches_http():
    req = {"kind": "back_patch", "shape": "custom", "options": {}}
    r = client.post("/api/seed", json=req)
    assert r.status_code == 422
    out = _glue("seed", req)
    assert out["ok"] is False
    assert out["error"]["kind"] == "validation"
    assert out["error"]["message"] == r.json()["detail"]


def test_adjust_glue_equals_http_cold():
    """冷缓存（guess=None）路径与 HTTP 全等，含 evaluations 逐位一致。"""
    sheet = client.post("/api/draft/sheet", json=REQ).json()
    h = _handle(sheet, "front.pocket_p2")
    req = {**REQ, "element": "front.pocket_p2",
           "param": "front_pocket_p2_drop", "axis": "y",
           "target": h["y"] - 1.5}
    http = client.post("/api/adjust", json=req).json()
    assert _glue("adjust", req) == http


def test_adjust_glue_warm_cache_still_correct():
    """热缓存只加速不改结果：冷/单点热/两点外推热三档，value/achieved/
    converged 均与 HTTP 一致；两点外推后（拖拽第 3 次求解）求值数大降。"""
    engine_glue._SOLVE_CACHE.clear()
    sheet = client.post("/api/draft/sheet", json=REQ).json()
    h = _handle(sheet, "front.pocket_p2")

    def req(dy: float) -> dict:
        return {**REQ, "element": "front.pocket_p2",
                "param": "front_pocket_p2_drop", "axis": "y",
                "target": h["y"] + dy}

    http = client.post("/api/adjust", json=req(-1.5)).json()
    first = _glue("adjust", req(-1.5))        # 冷：与 HTTP 全等并写缓存
    assert first == http
    second = _glue("adjust", req(-1.8))       # 单点 guess
    assert second["converged"] and second["evaluations"] <= http["evaluations"] + 1
    third = _glue("adjust", req(-2.1))        # 两点弦截外推
    assert third["converged"] and third["reason"] == "tol"
    assert abs(third["achieved"] - (h["y"] - 2.1)) <= 0.01
    assert third["evaluations"] <= 2


# ---------- 错误口径同构 ----------

def test_validation_error_detail_matches_http():
    bad = {"measurements": ADJ_M, "options": {"front_pouch": True}}
    r = client.post("/api/draft/sheet", json=bad)
    assert r.status_code == 422
    out = _glue("sheet", bad)
    assert out["ok"] is False
    assert out["error"]["kind"] == "validation"
    assert out["error"]["detail"] == r.json()["detail"]


def test_unregistered_binding_matches_http():
    req = {**REQ, "element": "front.pocket_p2", "param": "delta",
           "axis": "y", "target": 90.0}
    r = client.post("/api/adjust", json=req)
    assert r.status_code == 422
    out = _glue("adjust", req)
    assert out["error"]["kind"] == "validation"
    assert out["error"]["message"] == r.json()["detail"]


def test_handle_never_raises():
    assert json.loads(engine_glue.handle("sheet", "not-json"))["ok"] is False
    assert json.loads(engine_glue.handle("bogus", "{}"))["ok"] is False
    assert json.loads(engine_glue.handle("adjust", "{}"))["ok"] is False
    assert json.loads(engine_glue.handle("seed", "{}"))["ok"] is False
