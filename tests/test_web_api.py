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
    keys = {p["key"] for s in schema["sections"]
            for g in s["groups"] for p in g["params"]}
    from ylpattern.params import PatternOptions, Measurements
    engine = set(PatternOptions().__dict__) | set(
        Measurements(waist=68, hip=91, knee=44, hem=34, front_rise=25,
                     back_rise=33, outseam=102).__dict__)
    assert engine <= keys          # 引擎参数全部被 schema 覆盖（含 misc 兜底）


def test_schema_sections_structure():
    """两段式结构金标：整版绘制/裁片分家（.claude/plans/webapp-phase2）。

    段序固定；组 key 全局唯一；工艺参数迁裁片段、绘制参数留整版段；
    前后片自有工艺参数（缝份/刀口/缩水率）同组不拆分（用户口径 2026-08-25）。
    """
    schema = build_schema()
    sections = schema["sections"]
    assert [s["key"] for s in sections] == ["draft", "pieces"]
    group_keys = [g["key"] for s in sections for g in s["groups"]]
    assert len(group_keys) == len(set(group_keys))    # 组 key 全局唯一

    where: dict[str, tuple[str, str]] = {}           # param -> (段, 组)
    for s in sections:
        for g in s["groups"]:
            for p in g["params"]:
                where.setdefault(p["key"], (s["key"], g["key"]))
    assert where["waist"][1] == "measurements"       # 值来源路由组（前端契约）
    assert "misc" in group_keys                      # 白名单外参数兜底组在位
    for k in ("waistband_seam_allowances", "fly_sep_extra",
              "belt_loop_width", "front_piece_notch_type",
              "back_patch_notch_type"):
        assert where[k][0] == "pieces", k            # 工艺参数迁裁片段
    for k in ("waistband_width", "fly_width", "back_patch_shape",
              "side_rise"):
        assert where[k][0] == "draft", k             # 绘制参数留整版段
    for piece in ("front_piece", "back_piece"):
        groups_of = {where[f"{piece}_shrinkage_warp"][1],
                     where[f"{piece}_seam_allowances"][1],
                     where[f"{piece}_notch_type"][1]}
        assert len(groups_of) == 1, piece            # 裁片自有参数同组不拆分


def test_draft_sheet_ok():
    r = client.post("/api/draft/sheet", json={"measurements": BASE_M,
                                              "options": FULL_OPTS})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and "<svg" in body["sheet_svg"]
    assert body["report"]                # 报表非空
    # 金标：整版端点不带回裁片负载（两步生成拆分口径）
    assert "pieces" not in body and "skips" not in body


def test_draft_sheet_show_labels_switch():
    # show_labels=False：整版 SVG 文字标注全隐藏（端到端，options 透传出口层）
    r = client.post("/api/draft/sheet", json={"measurements": BASE_M,
                                              "options": {"show_labels": False}})
    assert r.status_code == 200
    assert r.json()["sheet_svg"].count("<text") == 0


def test_draft_pieces_dynamic():
    r = client.post("/api/draft/pieces", json={"measurements": BASE_M,
                                               "options": FULL_OPTS})
    assert r.status_code == 200
    body = r.json()
    names = {p["key"] for p in body["pieces"]}
    # 腰头永有；其余随开关
    assert "waistband" in names and "back_yoke" in names
    assert "front_pouch" in names and "belt_loop" in names
    assert all("<svg" in p["svg"] for p in body["pieces"])
    # 金标：裁片端点不带回整版负载
    assert "sheet_svg" not in body and "report" not in body


def test_draft_minimal_only_waistband_pieces():
    r = client.post("/api/draft/pieces", json={"measurements": BASE_M,
                                               "options": {}})
    body = r.json()
    # 全开关关闭：腰头 + 前后片必有，口袋类裁片不在清单
    names = {p["key"] for p in body["pieces"]}
    assert "waistband" in names and "front_piece" in names
    assert "front_pouch" not in names and "back_patch" not in names


def test_draft_validation_422():
    # 两端点共用 _build：同 payload 各自 422 且结构一致
    for ep in ("/api/draft/sheet", "/api/draft/pieces"):
        r = client.post(ep, json={"measurements": BASE_M,
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
    r3 = client.post("/api/dxf?kind=bogus",
                     json={"measurements": BASE_M, "options": {}})
    assert r3.status_code == 400
    assert "size_run" in r3.json()["detail"]


SIZE_RUN = {"base": "30", "style": "TEST-RUN",
            "order": ["29", "30", "31"],
            "band": [{"sizes": ["29", "30", "31"],
                      "waist": 2.5, "hip": 2.5}]}


def test_dxf_size_run_ok():
    """金标（手工演算）：3 码档差腰/臀 2.5 -> 多码单文件 DXF；Sample Size=
    基码 30、订单号进 Style Name / Grading Rule Table 两行头。"""
    ezdxf = pytest.importorskip("ezdxf")
    r = client.post("/api/dxf?kind=size_run",
                    json={"measurements": BASE_M, "options": {},
                          "size_run": SIZE_RUN})
    assert r.status_code == 200
    assert b"SECTION" in r.content
    assert b"Sample Size: 30" in r.content
    assert b"Style Name: TEST-RUN" in r.content
    assert r.headers["content-disposition"].endswith('size_run.dxf"')
    import io
    doc = ezdxf.read(io.StringIO(r.content.decode("latin-1")))
    blocks = [b.name for b in doc.blocks if not b.name.startswith(("*", "_"))]
    assert "WAISTBAND-31" in blocks and "FRONT_PIECE-29" in blocks


def test_dxf_size_run_missing_422():
    r = client.post("/api/dxf?kind=size_run",
                    json={"measurements": BASE_M, "options": {}})
    assert r.status_code == 422
    assert "size_run" in r.json()["detail"]


def test_dxf_size_run_invalid_422():
    # 码序重复：引擎 from_spec ValueError（消息带码标签）-> 422 字符串
    bad = dict(SIZE_RUN, order=["29", "29", "30"],
               band=[{"sizes": ["29", "30"], "waist": 2.5}])
    r = client.post("/api/dxf?kind=size_run",
                    json={"measurements": BASE_M, "options": {},
                          "size_run": bad})
    assert r.status_code == 422
    assert "重复" in r.json()["detail"]


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
    assert "size_run" not in r.text        # 未配置推板不带段（单码口径不变）


def test_toml_size_run_roundtrip(tmp_path):
    """金标：带 [size_run] 段导出 -> load_size_run 全等（Web 配置直喂 CLI 闭环），
    band 8 键全量显式、enabled 恒 true。"""
    r = client.post("/api/toml", json={"measurements": BASE_M,
                                       "options": {"size_label": "30"},
                                       "size_run": SIZE_RUN})
    assert r.status_code == 200
    assert "[size_run]" in r.text and "[[size_run.band]]" in r.text
    f = tmp_path / "size_run.toml"
    f.write_text(r.text, encoding="utf-8")
    from ylpattern.params import load_size_run
    run = load_size_run(str(f), fallback_base="30")
    assert run is not None
    assert run.labels == ("29", "30", "31")
    assert run.base == "30" and run.style_name == "TEST-RUN"
    # 基码 30 腰 68、档差 2.5：31 码 70.5、29 码 65.5
    assert run.measurements("31").waist == pytest.approx(70.5)
    assert run.measurements("29").waist == pytest.approx(65.5)


def test_templates_list_and_detail():
    r = client.get("/api/templates")
    assert r.status_code == 200 and len(r.json()) >= 2
    name = r.json()[0]["file"]
    d = client.get(f"/api/templates/{name}")
    assert "measurements" in d.json()
