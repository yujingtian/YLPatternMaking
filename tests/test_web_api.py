"""API 金标测试：webapp 后端全链路（TestClient，不落盘）。

合法参数 -> 200 且裁片清单动态反映开关；非法参数 -> 422 结构化；
DXF 非空 R12；toml 导出可被 PatternOptions.from_file 往返。
依赖 fastapi + httpx（[web] 可选依赖组），缺失时整文件跳过。
"""

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from webapp.backend.app import app  # noqa: E402
from webapp.backend.schema import build_schema  # noqa: E402

BASE_M = dict(waist=68, hip=91, knee=44, hem=34,
              front_rise=25, back_rise=33, outseam=102, thigh=0)
FULL_OPTS = dict(front_pocket=True, front_pocket_facing=True,
                 front_pouch=True, fly=True, fly_separate=True,
                 back_yoke=True, back_patch=True, belt_loop=True)

client = TestClient(app)


def test_schema_groups_cover_all_options():
    schema = build_schema()
    keys = {p["key"] for g in schema["groups"] for p in g["params"]}
    from ylpattern.params import PatternOptions, Measurements
    engine = set(PatternOptions().__dict__) | set(
        Measurements(waist=68, hip=91, knee=44, hem=34, front_rise=25,
                     back_rise=33, outseam=102).__dict__)
    assert engine <= keys          # 引擎参数全部被 schema 覆盖（含 misc 兜底）


def test_draft_ok_dynamic_pieces():
    r = client.post("/api/draft", json={"measurements": BASE_M,
                                        "options": FULL_OPTS})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and "<svg" in body["sheet_svg"]
    names = {p["key"] for p in body["pieces"]}
    # 腰头永有；其余随开关
    assert "waistband" in names and "back_yoke" in names
    assert "front_pouch" in names and "belt_loop" in names
    assert all("<svg" in p["svg"] for p in body["pieces"])


def test_draft_minimal_only_waistband_pieces():
    r = client.post("/api/draft", json={"measurements": BASE_M, "options": {}})
    body = r.json()
    # 全开关关闭：腰头 + 前后片必有，口袋类裁片不在清单
    names = {p["key"] for p in body["pieces"]}
    assert "waistband" in names and "front_piece" in names
    assert "front_pouch" not in names and "back_patch" not in names


def test_draft_validation_422():
    r = client.post("/api/draft",
                    json={"measurements": BASE_M,
                          "options": {"front_pouch": True}})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail[0]["param"] == "front_pouch"
    assert "front_pocket" in detail[0]["message"]


def test_dxf_download_nonempty():
    r = client.post("/api/dxf?kind=pieces",
                    json={"measurements": BASE_M, "options": FULL_OPTS})
    assert r.status_code == 200
    assert b"SECTION" in r.content and len(r.content) > 1000
    r2 = client.post("/api/dxf?kind=sheet",
                     json={"measurements": BASE_M, "options": {}})
    assert r2.status_code == 200 and b"SECTION" in r2.content


def test_toml_roundtrip(tmp_path):
    r = client.post("/api/toml", json={"measurements": BASE_M,
                                       "options": {"delta": 1.35,
                                                   "front_pocket": True}})
    assert r.status_code == 200
    f = tmp_path / "roundtrip.toml"
    f.write_text(r.text, encoding="utf-8")
    from ylpattern.params import PatternOptions
    o = PatternOptions.from_file(str(f))
    assert o.delta == 1.35 and o.front_pocket is True


def test_templates_list_and_detail():
    r = client.get("/api/templates")
    assert r.status_code == 200 and len(r.json()) >= 2
    name = r.json()[0]["file"]
    d = client.get(f"/api/templates/{name}")
    assert "measurements" in d.json()
