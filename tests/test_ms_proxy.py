"""MS 代理通道测试：/ms/{path} httpx 转发（二期机器排料对接 §10.3.2）+
.msn 状态文件专用透传端点 GET /api/nest/tasks/{id}/state-file（三期 US-001，
tasks/prd-machine-state-file-yl.md）。

夹具 = 线程内真 uvicorn echo 服务（随机端口，镜像 MS 机器端点行为面）：
GET / 首页探针（Cache-Control: no-cache）、multipart 字节透传（echo 回显
原始 body）、DELETE 方法、文件流（Content-Disposition）、state-file 族
（gzip 附件 / 慢流 / 大载荷 / 401·404·409·500 错误支路，请求头留痕供
token 注入断言）；MS 未启动分支用刚释放的随机端口探 502 中文提示。
依赖 fastapi + httpx + uvicorn（[web] 可选依赖组），缺失时整文件跳过。
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import socket
import threading
import time
from urllib.parse import quote

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI, Request            # noqa: E402
from fastapi.responses import (JSONResponse, Response,  # noqa: E402
                               StreamingResponse)
from fastapi.testclient import TestClient       # noqa: E402

import webapp.backend.app as backend            # noqa: E402

_PLT = (b"IN;PU0,0;PD1000,0;PD1000,500;PD0,500;PD0,0;PU;\n"
        b"SI0.12,0.16;LB29-30 85.00%;\n")
_CD = ('attachment; filename="nest_29-30_85.00pct_seed1_clean.plt"; '
       "filename*=UTF-8''%E6%8E%92%E6%96%99.plt")

# .msn 状态文件（三期）：镜像 MS state-file 端点的文件名双写形态
# （<stem>_state_<ts>.msn ASCII + <stem>_状态_<ts>.msn RFC5987）与 gzip 附件体
_MSN_CN = "nest_size_run_状态_20260922-101010.msn"
_MSN_ASCII = "nest_size_run_state_20260922-101010.msn"
_MSN_CD = (f'attachment; filename="{_MSN_ASCII}"; '
           f"filename*=UTF-8''{quote(_MSN_CN)}")
_MSN = gzip.compress(b'{"doc": {"pieces": []}, "form": {"gate": "175"}}',
                     mtime=0)
_MSN_BIG = b"\x1f\x8b.msn-stream-payload-" * 400_000   # 6.4MB 大载荷


def _echo_app() -> FastAPI:
    app = FastAPI()

    @app.get("/")
    def index() -> Response:
        # 镜像 MS routes_views 口径：index 每次重验证（no-cache）
        return Response("ms-echo", media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-cache"})

    async def echo(request: Request) -> JSONResponse:
        body = await request.body()
        return JSONResponse({
            "method": request.method,
            "path": request.url.path,
            "query": request.url.query,
            "content_type": request.headers.get("content-type", ""),
            "body_len": len(body),
            "body_b64": base64.b64encode(body).decode(),
        })

    app.add_api_route("/api/echo", echo, methods=["GET", "POST", "DELETE"])
    # 镜像 MS 机器端点路径面（solve 提交 / DELETE 会话回收走 echo）
    app.add_api_route("/api/machine/solve", echo, methods=["POST"])
    app.add_api_route("/api/machine/solve/{task_id}", echo,
                      methods=["DELETE"])

    @app.post("/api/machine/export")
    def file() -> Response:
        return Response(_PLT, media_type="application/octet-stream",
                        headers={"Content-Disposition": _CD})

    # 镜像 MS 三期 state-file 端点：请求头留痕（token 注入断言）+ task_id 编码
    # 错误支路 + gzip 附件 / 慢流 / 大载荷 / 迟响应四种 200 前形态
    app.state.ms_state_seen = []
    app.state.slow_done = False

    @app.get("/api/machine/solve/{task_id}/state-file")
    async def state_file(task_id: str, request: Request) -> Response:
        app.state.ms_state_seen.append(dict(request.headers))
        err = {"st401": 401, "st404": 404, "st409": 409,
               "st500": 500}.get(task_id)
        if err is not None:
            return JSONResponse({"error": f"ms-structured-error-{err}"},
                                status_code=err)
        if task_id == "big":        # 6.4MB：大载荷逐字节对拍
            return Response(_MSN_BIG, media_type="application/gzip",
                            headers={"Content-Disposition": _MSN_CD})
        if task_id == "sleepy":     # 迟响应：超时支路（测试把超时拧小）
            await asyncio.sleep(1.0)
            return Response(_MSN, media_type="application/gzip")
        if task_id == "slow":       # 分块慢流：证明代理逐块转发不缓冲整包

            async def chunks():
                for i in range(3):
                    yield b"chunk%d;" % i
                    await asyncio.sleep(0.4)
                app.state.slow_done = True

            return StreamingResponse(chunks(), media_type="application/gzip",
                                     headers={"Content-Disposition": _MSN_CD})
        return Response(_MSN, media_type="application/gzip",
                        headers={"Content-Disposition": _MSN_CD})

    return app


@pytest.fixture()
def ms_echo(monkeypatch):
    """真 uvicorn 起在随机端口（线程内），YL 侧 _MS_BASE 指向它；
    yield echo app（state 上留有 state-file 请求头观察面）。"""
    uvicorn = pytest.importorskip("uvicorn")
    app = _echo_app()
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=0, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started, "echo uvicorn 未在限期内启动"
    port = server.servers[0].sockets[0].getsockname()[1]
    monkeypatch.setattr(backend, "_MS_BASE", f"http://127.0.0.1:{port}")
    yield app
    server.should_exit = True
    thread.join(timeout=5)


client = TestClient(backend.app)


def test_ms_default_base():
    # 缺省基址（环境变量未设时）：127.0.0.1:8010
    import os
    if "YLP_MS_BASE" in os.environ:
        pytest.skip("本机设置了 YLP_MS_BASE，缺省值不可验")
    assert backend._MS_BASE == "http://127.0.0.1:8010"


def test_ms_timeout_tiers():
    # 超时分档：solve 提交 / export / result 重端点 120s；
    # status 轮询 / stop / DELETE / 首页探针等轻端点 30s
    slow = ("api/machine/solve", "api/machine/export",
            "api/machine/solve/m170001_ab12cd/result")
    fast = ("api/machine/solve/m170001_ab12cd/status",
            "api/machine/solve/m170001_ab12cd/stop",
            "api/machine/solve/m170001_ab12cd", "")
    for p in slow:
        assert backend._ms_timeout_sec(p) == 120.0, p
    for p in fast:
        assert backend._ms_timeout_sec(p) == 30.0, p


def test_ms_homepage_probe(ms_echo):
    """GET /ms/（MS 首页探针）：200 + Cache-Control 头原样透传。"""
    r = client.get("/ms/")
    assert r.status_code == 200
    assert r.text == "ms-echo"
    assert r.headers["cache-control"] == "no-cache"


def test_ms_multipart_bytes_passthrough(ms_echo):
    """multipart POST 字节透传：echo 夹具回显原始 body——长度一致且逐字节
    全等、content-type（含 boundary）原样（MS 侧才能正确解 multipart）。"""
    boundary = "----ylpnest7d83a1c"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="config"\r\n\r\n'
        '{"gate_mm":1750,"run_mode":"normal","sizes":[29,30]}\r\n'
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; '
        'filename="nest_size_run.dxf"\r\n'
        "Content-Type: application/dxf\r\n\r\n"
    ).encode() + b"0\r\nSECTION\r\n2\r\nHEADER\r\n0\r\nENDSEC\r\n" + \
        f"\r\n--{boundary}--\r\n".encode()
    ctype = f"multipart/form-data; boundary={boundary}"
    r = client.post("/ms/api/machine/solve", content=body,
                    headers={"content-type": ctype})
    assert r.status_code == 200, r.text
    echo = r.json()
    assert echo["method"] == "POST"
    assert echo["path"] == "/api/machine/solve"
    assert echo["body_len"] == len(body)                  # 长度一致
    assert base64.b64decode(echo["body_b64"]) == body     # 逐字节透传
    assert echo["content_type"] == ctype                  # boundary 原样


def test_ms_delete_forward(ms_echo):
    # DELETE 方法可转发（结果期显式关闭 -> MS 侧会话回收的消费端）
    r = client.delete("/ms/api/machine/solve/m170001_ab12cd")
    assert r.status_code == 200, r.text
    echo = r.json()
    assert echo["method"] == "DELETE"
    assert echo["path"] == "/api/machine/solve/m170001_ab12cd"


def test_ms_query_string_forward(ms_echo):
    r = client.get("/ms/api/echo?task_id=abc&verbose=1")
    assert r.status_code == 200
    assert r.json()["query"] == "task_id=abc&verbose=1"


def test_ms_file_stream_content_disposition(ms_echo):
    """文件流：Content-Disposition 响应头原样透传（ASCII filename + UTF-8
    扩展段双写形态不拆解），body 逐字节一致。"""
    r = client.post("/ms/api/machine/export", json={"task_id": "m170001"})
    assert r.status_code == 200
    assert r.content == _PLT
    assert r.headers["content-disposition"] == _CD


def test_ms_unreachable_502(monkeypatch):
    # MS 未启动（刚释放的随机端口，保证无监听）-> 502 中文提示含 YLP_MS_BASE
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    monkeypatch.setattr(backend, "_MS_BASE", f"http://127.0.0.1:{port}")
    r = client.get("/ms/")
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert "MS" in detail and "YLP_MS_BASE" in detail


# ---------------- 三期 US-001：.msn 状态文件专用透传端点 ----------------


def test_state_file_defaults():
    # YLP_MS_TOKEN 缺省空（未配置不发头）；专用超时 60s（PRD：>=30s 建议 60s，
    # 不落 _ms_timeout_sec 的 30s 轻端点档）
    import os
    if "YLP_MS_TOKEN" in os.environ:
        pytest.skip("本机设置了 YLP_MS_TOKEN，缺省值不可验")
    assert backend._MS_TOKEN == ""
    assert backend._MS_STATE_TIMEOUT_SEC == 60.0


def test_state_file_passthrough(ms_echo):
    """200 透传：gzip 字节、Content-Type、Content-Disposition（.msn ASCII/
    UTF-8 双写文件名）与 MS 原始响应逐字节一致——浏览器落盘名与 MS 侧相同。"""
    r = client.get("/api/nest/tasks/m170001_ab12cd/state-file")
    assert r.status_code == 200
    assert r.content == _MSN                       # 逐字节对拍
    assert r.headers["content-type"] == "application/gzip"
    assert r.headers["content-disposition"] == _MSN_CD


def test_state_file_big_payload(ms_echo):
    # 大载荷（6.4MB）逐字节一致 + 附件头原样——流式转发不整体读入内存的对拍面
    r = client.get("/api/nest/tasks/big/state-file")
    assert r.status_code == 200
    assert len(r.content) == len(_MSN_BIG) > 6_000_000
    assert r.content == _MSN_BIG
    assert r.headers["content-disposition"] == _MSN_CD


def test_state_file_streaming_no_buffer(ms_echo):
    """流式不缓冲（全栈 TCP 证法：starlette TestClient 会先把 ASGI app 跑完
    才出响应，看不出渐进性——故 YL app 另起真 uvicorn、真 httpx stream）：
    上游慢流分块下发，客户端收到首块时上游尚未发完——若代理整体缓冲再转发，
    首块只能在上游 slow_done 之后到达。"""
    uvicorn = pytest.importorskip("uvicorn")
    import httpx
    server = uvicorn.Server(uvicorn.Config(
        backend.app, host="127.0.0.1", port=0, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started, "YL 侧 uvicorn 未在限期内启动"
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}",
                          timeout=30) as hc:
            with hc.stream("GET", "/api/nest/tasks/slow/state-file") as r:
                assert r.status_code == 200
                it = r.iter_bytes()
                assert next(it) == b"chunk0;"
                assert not ms_echo.state.slow_done   # 首块已到、上游未发完
                assert b"".join(it) == b"chunk1;chunk2;"
        assert ms_echo.state.slow_done
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_state_file_error_mapping(ms_echo):
    # 401/404/409 原码 + 固定中文文案；其它（500）归一 502 通用文案
    for tid, code, msg in (
            ("st401", 401, "排料服务认证失败，请联系管理员"),
            ("st404", 404, "任务不存在或已清理"),
            ("st409", 409, "任务数据已不可得，请重新提交排料"),
            ("st500", 502, "排料服务暂不可用，请稍后重试")):
        r = client.get(f"/api/nest/tasks/{tid}/state-file")
        assert r.status_code == code, tid
        assert r.json()["detail"] == msg, tid


def test_state_file_timeout_502(ms_echo, monkeypatch):
    # 超时支路：超时拧小 0.2s，上游 1s 才回 -> 502 通用文案
    monkeypatch.setattr(backend, "_MS_STATE_TIMEOUT_SEC", 0.2)
    r = client.get("/api/nest/tasks/sleepy/state-file")
    assert r.status_code == 502
    assert r.json()["detail"] == "排料服务暂不可用，请稍后重试"


def test_state_file_unreachable_502(monkeypatch):
    # 连接失败支路：死端口（刚释放的随机端口，保证无监听）-> 502 通用文案
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    monkeypatch.setattr(backend, "_MS_BASE", f"http://127.0.0.1:{port}")
    r = client.get("/api/nest/tasks/m1/state-file")
    assert r.status_code == 502
    assert r.json()["detail"] == "排料服务暂不可用，请稍后重试"


def test_state_file_token_injection(ms_echo, monkeypatch):
    """YLP_MS_TOKEN 已配置 -> 服务端注入 X-Machine-Token；未配置不发；
    token 不出现在响应头/体（前端可达面零泄露）。"""
    monkeypatch.setattr(backend, "_MS_TOKEN", "")
    client.get("/api/nest/tasks/m170001_ab12cd/state-file")
    assert "x-machine-token" not in ms_echo.state.ms_state_seen[-1]

    monkeypatch.setattr(backend, "_MS_TOKEN", "yl-secret-token-7f3a")
    r = client.get("/api/nest/tasks/m170001_ab12cd/state-file")
    assert ms_echo.state.ms_state_seen[-1]["x-machine-token"] == \
        "yl-secret-token-7f3a"
    assert "yl-secret-token-7f3a" not in r.text       # 响应体零出现
    assert all("yl-secret-token-7f3a" not in f"{k}: {v}"             # noqa: E501
               for k, v in r.headers.items())          # 响应头零出现
