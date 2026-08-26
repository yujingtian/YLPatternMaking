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
from ylpattern.webschema import ADJUSTABLES, build_schema, handles

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
                # pocket_type / fly_type 是前端虚拟下拉，不对应引擎字段
                if p["type"] not in ("pocket_type", "fly_type"):
                    seen.append(p["key"])
    assert len(seen) == len(set(seen)), "面板参数出现重复"
    m_keys = vars(Measurements(waist=68, hip=91, knee=44, hem=34,
                               front_rise=25, back_rise=33,
                               outseam=102, thigh=58))
    o_keys = vars(PatternOptions())
    assert set(seen) == set(m_keys) | set(o_keys), \
        "引擎参数未全覆盖（misc 兜底失效？）"


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
