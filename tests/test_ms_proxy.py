"""MS 代理通道测试：/ms/{path} httpx 转发（二期机器排料对接 §10.3.2）。

夹具 = 线程内真 uvicorn echo 服务（随机端口，镜像 MS 机器端点行为面）：
GET / 首页探针（Cache-Control: no-cache）、multipart 字节透传（echo 回显
原始 body）、DELETE 方法、文件流（Content-Disposition）；MS 未启动分支用
刚释放的随机端口探 502 中文提示。依赖 fastapi + httpx + uvicorn（[web]
可选依赖组），缺失时整文件跳过。
"""

from __future__ import annotations

import base64
import socket
import threading
import time

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI, Request            # noqa: E402
from fastapi.responses import JSONResponse, Response  # noqa: E402
from fastapi.testclient import TestClient       # noqa: E402

import webapp.backend.app as backend            # noqa: E402

_PLT = (b"IN;PU0,0;PD1000,0;PD1000,500;PD0,500;PD0,0;PU;\n"
        b"SI0.12,0.16;LB29-30 85.00%;\n")
_CD = ('attachment; filename="nest_29-30_85.00pct_seed1_clean.plt"; '
       "filename*=UTF-8''%E6%8E%92%E6%96%99.plt")


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

    return app


@pytest.fixture()
def ms_echo(monkeypatch):
    """真 uvicorn 起在随机端口（线程内），YL 侧 _MS_BASE 指向它。"""
    uvicorn = pytest.importorskip("uvicorn")
    server = uvicorn.Server(uvicorn.Config(
        _echo_app(), host="127.0.0.1", port=0, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started, "echo uvicorn 未在限期内启动"
    port = server.servers[0].sockets[0].getsockname()[1]
    monkeypatch.setattr(backend, "_MS_BASE", f"http://127.0.0.1:{port}")
    yield f"http://127.0.0.1:{port}"
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
