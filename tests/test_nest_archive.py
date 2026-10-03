"""POST /api/nest/tasks/{task_id}/archive 回传存档测试（四期 US-004，
tasks/prd-machine-direct-channel.md）。

口径：multipart file_plt（PLT 文本）+ file_msn（.msn gzip）+ meta（JSON 串：
task_id/通道标记/density/width_mm/码套/seed/run_mode/时间）→
out/nest_archive/<task_id>/ 三件落盘（result.plt/state.msn/meta.json）+
仓级 index.jsonl 索引行（每 task_id 恰一行，重传整行覆盖不重复）；幂等 =
同 task_id 重传覆盖同路径不报错；task_id 路径安全闸 400 / meta 非法
JSON·非对象·task_id 不一致 400 / 空文件 422 / 超 10MB 上限 413（与
agent MAX_PHOTO_BYTES 上传约定一致）；校验前置——拒绝即零落盘。
依赖 fastapi + python-multipart（[web] 可选依赖组），缺失时整文件跳过。
"""

import gzip
import json

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("multipart")   # python-multipart：UploadFile 硬依赖
from fastapi.testclient import TestClient  # noqa: E402

import webapp.backend.app as backend          # noqa: E402

_PLT = b"IN;PS125800;SP1;PW0.08;PU0,0;PD1000,0;PD1000,500;\n"
_MSN = gzip.compress(b'{"doc": {"pieces": []}, "form": {"gate": "175"}}',
                     mtime=0)


def _meta(task_id="m170001_ab12cd", **over):
    m = {"task_id": task_id,
         "channel": {"kind": "direct", "base": "http://127.0.0.1:8012"},
         "density": 0.8524, "width_mm": 1750, "sizes": ["29", "30", "31"],
         "seed": 7, "run_mode": "normal", "time": "2026-10-02T10:00:00+08:00"}
    m.update(over)
    return m


@pytest.fixture()
def archive_dir(tmp_path, monkeypatch):
    d = tmp_path / "nest_archive"
    monkeypatch.setattr(backend, "_NEST_ARCHIVE_DIR", d)   # 同 _MS_BASE 先例
    return d


client = TestClient(backend.app)


def _post(task_id="m170001_ab12cd", meta=None, plt=_PLT, msn=_MSN):
    meta_str = meta if isinstance(meta, str) else json.dumps(
        meta if meta is not None else _meta(task_id))
    return client.post(
        f"/api/nest/tasks/{task_id}/archive",
        files={"file_plt": ("nest.plt", plt, "application/octet-stream"),
               "file_msn": ("state.msn", msn, "application/gzip")},
        data={"meta": meta_str})


def _index_entries(archive_dir):
    return [json.loads(x) for x in
            (archive_dir / "index.jsonl").read_text(encoding="utf-8")
            .splitlines()]


def test_archive_normal_three_files_and_index(archive_dir):
    r = _post()
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["task_id"] == "m170001_ab12cd"
    assert body["files"] == {"plt": "result.plt", "msn": "state.msn",
                             "meta": "meta.json"}
    assert body["sizes"] == {"plt": len(_PLT), "msn": len(_MSN)}
    task = archive_dir / "m170001_ab12cd"
    assert (task / "result.plt").read_bytes() == _PLT      # 字节原样落盘
    assert (task / "state.msn").read_bytes() == _MSN       # gzip 不解析透传
    on_disk = json.loads((task / "meta.json").read_text(encoding="utf-8"))
    assert on_disk == _meta()                              # meta 字段完整
    entries = _index_entries(archive_dir)
    assert len(entries) == 1
    e = entries[0]
    assert e["task_id"] == "m170001_ab12cd"
    assert e["channel"] == {"kind": "direct",
                            "base": "http://127.0.0.1:8012"}
    assert e["density"] == 0.8524 and e["width_mm"] == 1750
    assert e["sizes"] == ["29", "30", "31"]
    assert e["seed"] == 7 and e["run_mode"] == "normal"
    assert e["archive_dir"] == str(task)
    assert e["files"]["msn"] == "state.msn"
    assert e["archived_at"]


def test_archive_idempotent_overwrite(archive_dir):
    assert _post().status_code == 200
    plt2 = b"IN;PS999900;\n"
    msn2 = gzip.compress(b'{"doc": {"v": 2}}', mtime=0)
    assert _post(plt=plt2, msn=msn2, meta=_meta(density=0.9)).status_code == 200
    task = archive_dir / "m170001_ab12cd"
    assert (task / "result.plt").read_bytes() == plt2     # 覆盖同路径不报错
    assert (task / "state.msn").read_bytes() == msn2
    assert json.loads((task / "meta.json").read_text(
        encoding="utf-8"))["density"] == 0.9
    entries = _index_entries(archive_dir)
    assert len(entries) == 1                              # 无重复条目
    assert entries[0]["density"] == 0.9                   # 索引行同步更新


def test_archive_two_tasks_two_index_lines(archive_dir):
    assert _post().status_code == 200
    assert _post(task_id="m170002_ff99ee",
                 meta=_meta("m170002_ff99ee")).status_code == 200
    assert {e["task_id"] for e in _index_entries(archive_dir)} == \
        {"m170001_ab12cd", "m170002_ff99ee"}


def test_archive_meta_invalid(archive_dir):
    assert _post(meta="{not json").status_code == 400          # 非法 JSON
    assert _post(meta='["a"]').status_code == 400              # 非对象
    assert _post(meta=json.dumps(
        _meta("m170002_ff99ee"))).status_code == 400           # task_id 不一致
    assert not archive_dir.exists()               # 校验前置：拒绝即零落盘


def test_archive_bad_task_id(archive_dir):
    for bad in ("bad id", "%E4%BB%BB%E5%8A%A1", "%2e%2e", "-dash"):
        assert _post(task_id=bad).status_code == 400
    assert not archive_dir.exists()


def test_archive_empty_file(archive_dir):
    assert _post(msn=b"").status_code == 422
    assert not archive_dir.exists()


def test_archive_oversize(archive_dir, monkeypatch):
    monkeypatch.setattr(backend, "_NEST_ARCHIVE_MAX_FILE_BYTES", len(_PLT) - 1)
    assert _post().status_code == 413
    assert not archive_dir.exists()


def test_archive_limit_matches_upload_convention():
    # 与既有上传约定一致：agent MAX_PHOTO_BYTES 单文件 10MB
    assert backend._NEST_ARCHIVE_MAX_FILE_BYTES == 10 * 1024 * 1024


def test_archive_missing_meta_field(archive_dir):
    r = client.post("/api/nest/tasks/m170001_ab12cd/archive",
                    files={"file_plt": ("nest.plt", _PLT),
                           "file_msn": ("state.msn", _MSN)})
    assert r.status_code == 422                        # FastAPI 缺必填默认
    assert not archive_dir.exists()
