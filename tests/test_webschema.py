"""webschema 下沉后的结构金标（2026-08 自 webapp/backend/schema.py 搬移）。

从新位置 ylpattern.webschema 直接断言 schema 结构与把手派生，钉死搬移
无损；HTTP 口径的全等比对（worker 胶水 vs FastAPI 端点）见
tests/test_engine_glue.py，本文件不重复。

金标：
- schema 覆盖：Measurements + PatternOptions 全部字段在面板里出现且仅一次
  （misc 兜底保证不丢参数）；两段式 sections 键固定；
- 把手自门控（引擎直调，不经 HTTP）：口袋开+bulge = 16 / 关 = 13 /
  tangent = 15，与 test_web_adjust.py 的 HTTP 金标同口径；
- 薄再导出：webapp.backend.schema 的符号就是 ylpattern.webschema 的符号
  （identity，防有人往旧文件回写实现）。
"""

import pytest

from ylpattern.flows.closure import run_with_thigh_closure
from ylpattern.params import Measurements, PatternOptions
from ylpattern.webschema import (ADJUSTABLES, build_schema, handles,
                                 seed_patch_shape)

ADJ_M = dict(waist=70, hip=96, knee=46, hem=36,
             front_rise=25, back_rise=33, outseam=102, thigh=58)
POCKET_ON = {"front_pocket": True}

# 两段式段键固定（前端 PreviewPane/ParamPanel 按段渲染）
_SECTION_KEYS = ["draft", "pieces"]


def _ctx_handles(options: dict) -> list[dict]:
    m = Measurements(**ADJ_M)
    o = PatternOptions.from_dict(options)
    ctx, _ = run_with_thigh_closure(m, o)
    return handles(ctx, o)


# ---------- schema 覆盖 ----------

def test_schema_sections_and_full_coverage():
    schema = build_schema()
    assert [s["key"] for s in schema["sections"]] == _SECTION_KEYS
    seen: list[str] = []
    for s in schema["sections"]:
        for g in s["groups"]:
            for p in g["params"]:
                # pocket_type / fly_type / *_custom 是前端虚拟参数，不对应
                # 引擎字段（custom_shape 编辑器读写隐藏真实键）
                if p["type"] not in ("pocket_type", "fly_type",
                                     "custom_shape"):
                    seen.append(p["key"])
    assert len(seen) == len(set(seen)), "面板参数出现重复"
    m_keys = vars(Measurements(waist=68, hip=91, knee=44, hem=34,
                               front_rise=25, back_rise=33,
                               outseam=102, thigh=58))
    o_keys = vars(PatternOptions())
    assert set(seen) == set(m_keys) | set(o_keys), \
        "引擎参数未全覆盖（misc 兜底失效？）"


def test_custom_shape_virtual_specs():
    """custom 形态编辑器虚拟参数：kind / 两真实键 / v_positive 元数据齐备
    （后贴袋存储 v 向下正、前贴袋 dy 向上正，编辑器内部归一显示）；
    原始 *_custom_points/edges 仍进 schema 全集但标记 hidden
    （422 校验错误归因到这些键、由编辑器合并承接）。"""
    schema = build_schema()
    specs = {p["key"]: p for s in schema["sections"]
             for g in s["groups"] for p in g["params"]}
    back = specs["back_patch_custom"]
    front = specs["front_patch_custom"]
    assert back["type"] == front["type"] == "custom_shape"
    assert back["kind"] == "back_patch"
    assert back["points_key"] == "back_patch_custom_points"
    assert back["edges_key"] == "back_patch_custom_edges"
    assert back["v_positive"] == "down"
    assert front["kind"] == "front_patch"
    assert front["v_positive"] == "up"
    assert back["choices"] == ["rectangle", "baker_shield", "angular"]
    # gate 必须挂到虚拟 spec（build_schema 特判 continue 早于通用挂接点，
    # 曾静默丢失致编辑器在非 custom 形态下也常显）
    assert back["visible_if"] == {"param": "back_patch_shape",
                                  "values": ["custom"]}
    assert front["visible_if"] == {"param": "front_patch_shape",
                                   "values": ["custom"],
                                   "requires": ["front_patch"]}
    for k in ("back_patch_custom_points", "back_patch_custom_edges",
              "front_patch_custom_points", "front_patch_custom_edges"):
        assert specs[k]["hidden"] is True


def test_seed_patch_shape():
    """seed 金标（数值同 tests/test_patch.py）：baker 后侧 bi=1 五边形、
    angular 前侧消费底宽（后侧不消费形成对照）；边恒直线；
    非法 kind / 预设外 shape 抛 ValueError。"""
    r = seed_patch_shape(
        "back_patch", "baker_shield",
        {"back_patch_width": 14, "back_patch_height": 16,
         "back_patch_bottom_width": 12, "back_patch_tip_depth": 2.5})
    assert r["points"] == [[0.0, 0.0], [14.0, 0.0], [13.0, 16.0],
                           [7.0, 18.5], [1.0, 16.0]]
    assert r["edges"] == [[0.0, 0.5]] * 5
    f = seed_patch_shape(
        "front_patch", "angular",
        {"front_patch_width": 14, "front_patch_height": 16,
         "front_patch_bottom_width": 12, "front_patch_chamfer": 2})
    assert f["points"] == [[0.0, 0.0], [14.0, 0.0], [13.0, 14.0],
                           [11.0, 16.0], [3.0, 16.0], [1.0, 14.0]]
    with pytest.raises(ValueError):
        seed_patch_shape("side_patch", "rectangle", {})
    with pytest.raises(ValueError):
        seed_patch_shape("back_patch", "custom", {})


def test_adjustable_points_kind_t_pairing():
    pts = build_schema()["adjustable_points"]
    assert len(pts) == len(ADJUSTABLES)
    for p in pts:
        if p["kind"] == "curve":
            assert p["t"] is not None
        else:
            assert p["kind"] == "point" and p["t"] is None


# ---------- 把手自门控（引擎直调口径同 test_web_adjust.py） ----------

def test_handles_gating_counts():
    assert len(_ctx_handles(POCKET_ON)) == 16
    off = _ctx_handles({})
    assert len(off) == 13
    assert not any(h["element"].startswith("front.pocket") for h in off)
    assert len(_ctx_handles({**POCKET_ON,
                             "front_pocket_mouth_mode": "tangent"})) == 15


# ---------- 薄再导出（后端旧 import 路径稳定） ----------

def test_backend_reexport_identity():
    webapp_schema = pytest.importorskip("webapp.backend.schema")
    import ylpattern.webschema as impl
    for name in ("ADJUSTABLES", "build_schema", "binding_for",
                 "gate_on", "handles"):
        assert getattr(webapp_schema, name) is getattr(impl, name), \
            f"webapp.backend.schema.{name} 不是 ylpattern.webschema 的再导出"
