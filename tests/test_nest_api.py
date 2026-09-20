"""POST /api/nest 金标测试（排料对接产物：带 g 码 DXF + numMap，JSON）。

对接文档《母版DXF编号植入对接文档_2026-09.md》口径：
- 单码：码号 = 腰围英寸档（waist=68 -> 27）、numMap 扁平 {g码: 数量}、
  belt_loop 不进产物（文件无 BELT_LOOP 块、numMap 无 g10）、file 解码后
  为 R12 ASCII DXF 且块名带 -G{NN}-{码} 尾缀与 TEXT 层编号；
- 多码（size_run）：码号 = 推板码表、跨码同 g 码、numMap 仍扁平；
- 422：推板码号非纯数字（块名码号尾缀正则要求）、非法 measurements。
依赖 fastapi + httpx + ezdxf（[web]/[dxf] 可选依赖组），缺失时整文件跳过。
"""

import base64

import pytest

fastapi = pytest.importorskip("fastapi")
ezdxf = pytest.importorskip("ezdxf")
from fastapi.testclient import TestClient  # noqa: E402

from webapp.backend.app import app  # noqa: E402

BASE_M = dict(waist=68, hip=91, knee=44, hem=34,
              front_rise=25, back_rise=33, outseam=102, thigh=0)
# 不开 watch_pocket：小表袋相交模式在纯默认口袋参数下几何越界（已知
# 默认几何缺口，引擎侧自适应定位待修），Web 产品层默认也靠口袋参数
# 预填绕行；g09 数量口径由 test_piece_codes 覆盖。
FULL_OPTS = dict(front_pocket=True, front_pocket_facing=True,
                 front_pouch=True, fly=True, fly_separate=True,
                 back_yoke=True, back_patch=True, belt_loop=True)
SIZE_RUN = {"base": "28", "style": "NEST-TEST",
            "band": [{"sizes": ["28", "30", "32"],
                      "waist": 2.5, "hip": 2.5}]}

client = TestClient(app)


def _decode(body: dict):
    """file 字段 base64 -> ASCII DXF 文本。"""
    return base64.b64decode(body["file"]).decode("ascii")


def test_nest_single_size(client=client):
    r = client.post("/api/nest", json={"measurements": BASE_M,
                                       "options": FULL_OPTS})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["filename"] == "nest.dxf"
    # 单码码号 = 腰围英寸档：68cm / 2.54 = 26.77 -> 27
    text = _decode(body)
    assert "AC1009" in text
    assert "FRONT_PIECE-G01-27" in text
    assert "BELT_LOOP" not in text                     # 裤耳不进排料产物
    # numMap 扁平、无 g10（裤耳）；门襟 g08=1、双排门襟 g11=1、其余默认 2
    assert "g10" not in body["numMap"]
    assert body["numMap"]["g01"] == 2
    assert body["numMap"]["g08"] == 1
    assert body["numMap"]["g11"] == 1
    # labels 中文裁片名（仅供展示，不进 DXF）
    assert body["labels"]["g01"] == "前片裁片"
    assert "门襟" in body["labels"]["g08"]
    assert "前片" not in text                          # DXF 纯 ASCII 红线


def test_nest_single_size_dxf_structure():
    """ezdxf 回读：TEXT 层注册、每块恰 1 个 TEXT 层编号且锚点在层 1
    折线内、块名方式 A 复算与赋码表一致（对接验收清单 §7.1）。"""
    from ylpattern.exporters import piece_codes
    r = client.post("/api/nest", json={"measurements": BASE_M,
                                       "options": FULL_OPTS})
    assert r.status_code == 200
    import io
    doc = ezdxf.read(io.StringIO(_decode(r.json())))
    assert "TEXT" in doc.layers
    blocks = [b for b in doc.blocks if not b.name.startswith(("*", "$", "_"))]
    assert len(blocks) > 0
    for blk in blocks:
        size, g = piece_codes.parse_block_code(blk.name)
        assert size == "27" and g is not None
        cut = next(e for e in blk if e.dxftype() == "POLYLINE"
                   and e.dxf.layer == "1")
        codes = [e for e in blk if e.dxftype() == "TEXT"
                 and e.dxf.layer == "TEXT"]
        assert len(codes) == 1
        assert codes[0].dxf.text == piece_codes.code_text(g, "27")
        poly = [(v.dxf.location.x, v.dxf.location.y) for v in cut.vertices]
        assert piece_codes.point_in_polygon(
            (codes[0].dxf.insert.x, codes[0].dxf.insert.y), poly)


def test_nest_size_run():
    r = client.post("/api/nest", json={"measurements": BASE_M,
                                       "options": FULL_OPTS,
                                       "size_run": SIZE_RUN})
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "nest_size_run.dxf"
    text = _decode(body)
    # 跨码同 g 码：腰头三码块同名段只差码号尾缀
    for s in ("28", "30", "32"):
        assert f"WAISTBAND-G05-{s}" in text
    # Sample Size = 基码（Sample Size 行是 ET08 尺码栏数据源）
    assert "Sample Size: 28" in text
    # numMap 扁平（不含码维度）
    assert body["numMap"] == {"g01": 2, "g02": 2, "g03": 2, "g04": 2,
                              "g05": 2, "g06": 2, "g07": 2, "g08": 1,
                              "g11": 1}


def test_nest_size_run_non_numeric_label_422():
    bad = {"base": "M", "style": "X",
           "band": [{"sizes": ["S", "M", "L"], "waist": 2.5}]}
    r = client.post("/api/nest", json={"measurements": BASE_M,
                                       "options": {},
                                       "size_run": bad})
    assert r.status_code == 422
    assert "纯数字" in r.json()["detail"]
    assert "S" in r.json()["detail"] and "L" in r.json()["detail"]


def test_nest_validation_422():
    # 非法参数组合（front_pouch 依赖 front_pocket）-> 结构化 422
    r = client.post("/api/nest", json={"measurements": BASE_M,
                                       "options": {"front_pouch": True}})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail[0]["param"] == "front_pouch"


def test_nest_minimal_options():
    """全开关关闭：仅腰头+前后片，numMap 收缩为三键（缺片留洞不影响
    all-or-nothing——在场片全部带编号）。"""
    r = client.post("/api/nest", json={"measurements": BASE_M,
                                       "options": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["numMap"] == {"g01": 2, "g02": 2, "g05": 2}
