"""web 二期拖拽后端契约测试（/api/adjust + sheet 扩展；TestClient 金标）。

固定测量（同 test_adjust）：waist=70 hip=96 knee=46 hem=36 前浪25 后浪33
裤长102 thigh=58；选项 front_pocket=True（bulge 模式默认）。

金标：
- 往返：sheet 拿把手现值 → target = 现值 − 1.5 → /api/adjust → 200
  converged → params 回代重新生成 → 该把手坐标 == target（±0.01cm，
  引擎 tol_coord 默认值口径）；
- handles 自门控计数：口袋开+bulge = 16 条全量；口袋关 = 13 条；
  tangent 模式 = 15 条（袋口弧把手随形态消失）；
- transform 与引擎 compute_view 逐字段一致，且与 SVG 根 data-ox/top
  同源（两处不得漂移）；
- 绑定 range ⊆ PatternOptions 硬校验：每条 range 两端点值代入
  build_issues 无 error 级 Issue（防拖出值后续生成 422）；
- 未注册绑定 / 基线参数矛盾 → 422。
依赖 fastapi + httpx（[web] 可选依赖组），缺失时整文件跳过。
"""

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from webapp.backend.app import app  # noqa: E402
from webapp.backend.schema import ADJUSTABLES, build_schema  # noqa: E402

ADJ_M = dict(waist=70, hip=96, knee=46, hem=36,
             front_rise=25, back_rise=33, outseam=102, thigh=58)
POCKET_ON = {"front_pocket": True}

client = TestClient(app)


def _sheet(options: dict = POCKET_ON) -> dict:
    r = client.post("/api/draft/sheet",
                    json={"measurements": ADJ_M, "options": options})
    assert r.status_code == 200
    return r.json()


def _handle(body: dict, element: str) -> dict:
    return next(h for h in body["handles"] if h["element"] == element)


# ---------- /api/adjust 往返 ----------

def test_adjust_roundtrip_pocket_p2():
    body = _sheet()
    h = _handle(body, "front.pocket_p2")
    target = h["y"] - 1.5                       # 下拖 1.5cm
    r = client.post("/api/adjust", json={
        "measurements": ADJ_M, "options": POCKET_ON,
        "element": "front.pocket_p2", "param": "front_pocket_p2_drop",
        "axis": "y", "target": target})
    assert r.status_code == 200
    res = r.json()
    assert res["ok"] and res["converged"] and res["reason"] == "tol"
    assert 2.0 <= res["value"] <= 15.0
    # p2_drop 是外缝弧上弧长深度：竖直下拖 1.5cm → 弧长略大于 1.5
    #（默认 7.5 → ≈9.07），往返断言才是精确金标
    assert 9.0 < res["value"] < 9.2
    # params 回代重新生成：把手落到目标位（tol_coord=0.01 口径）
    body2 = _sheet({**POCKET_ON,
                    "front_pocket_p2_drop": res["params"]["front_pocket_p2_drop"]})
    assert _handle(body2, "front.pocket_p2")["y"] == pytest.approx(target, abs=0.01)


def test_adjust_curve_handle_hem_sag():
    body = _sheet()
    h = _handle(body, "front.hem")
    r = client.post("/api/adjust", json={
        "measurements": ADJ_M, "options": POCKET_ON,
        "element": "front.hem", "param": "front_hem_arc_sag",
        "axis": "y", "target": h["y"] - 0.6})
    assert r.status_code == 200
    res = r.json()
    assert res["converged"]
    assert res["value"] == pytest.approx(0.6, abs=1e-3)   # sag 中点线性金标
    body2 = _sheet({**POCKET_ON, "front_hem_arc_sag": res["value"]})
    assert _handle(body2, "front.hem")["y"] == pytest.approx(h["y"] - 0.6, abs=0.01)


def test_adjust_clamps_beyond_range():
    # 目标远超 [0, 1.5] 能力：200 + range_clamped 钳 hi（拖拽中不弹错）
    body = _sheet()
    h = _handle(body, "front.hem")
    r = client.post("/api/adjust", json={
        "measurements": ADJ_M, "options": POCKET_ON,
        "element": "front.hem", "param": "front_hem_arc_sag",
        "axis": "y", "target": h["y"] - 5.0})
    assert r.status_code == 200
    res = r.json()
    assert not res["converged"] and res["reason"] == "range_clamped"
    assert res["value"] == pytest.approx(1.5)


# ---------- 422 护栏 ----------

def test_adjust_unknown_binding_422():
    for element, param, axis in [
            ("front.pocket_p2", "delta", "y"),          # 参数未绑定该元素
            ("front.no_such", "front_pocket_p2_drop", "y"),
            ("front.pocket_p2", "front_pocket_p2_drop", "x")]:  # 轴不符
        r = client.post("/api/adjust", json={
            "measurements": ADJ_M, "options": POCKET_ON,
            "element": element, "param": param, "axis": axis, "target": 90.0})
        assert r.status_code == 422, (element, param, axis)


def test_adjust_baseline_error_422():
    # 基线参数矛盾（袋布依赖前口袋）：_build 422 先于求解
    r = client.post("/api/adjust", json={
        "measurements": ADJ_M, "options": {"front_pouch": True},
        "element": "front.hem", "param": "front_hem_arc_sag",
        "axis": "y", "target": 0.0})
    assert r.status_code == 422


# ---------- sheet 扩展：transform + handles ----------

def test_sheet_transform_matches_engine():
    from ylpattern.exporters import svg as svg_exp
    from ylpattern.flows.closure import run_with_thigh_closure
    from ylpattern.params import Measurements, PatternOptions
    m = Measurements.from_dict(ADJ_M)
    o = PatternOptions.from_dict(POCKET_ON)
    ctx, _ = run_with_thigh_closure(m, o)
    _w, _h, top, ox = svg_exp.compute_view(ctx.sheet)
    body = _sheet()
    assert body["transform"] == {"scale": svg_exp.SCALE, "ox": ox, "top": top}
    # SVG 根 data-* 与 transform 同源（.10g 格式化后一致）
    assert f'data-ox="{ox:.10g}"' in body["sheet_svg"]
    assert f'data-top="{top:.10g}"' in body["sheet_svg"]


def test_handles_full_and_gated():
    # 口袋开 + bulge 默认：16 条全量
    body = _sheet()
    assert len(body["handles"]) == 16
    hem = _handle(body, "front.hem")
    assert hem["kind"] == "curve" and hem["t"] == 0.5
    assert hem["bindings"] == [{"param": "front_hem_arc_sag",
                                "axis": "y", "range": [0.0, 1.5]}]
    # 口袋关：3 条口袋把手消失 → 13 条
    body_off = _sheet({})
    elems = {h["element"] for h in body_off["handles"]}
    assert len(body_off["handles"]) == 13
    assert not any(e.startswith("front.pocket") for e in elems)
    # tangent 模式：袋口弧把手随形态消失 → 15 条
    body_tan = _sheet({**POCKET_ON, "front_pocket_mouth_mode": "tangent"})
    assert len(body_tan["handles"]) == 15


def test_schema_adjustable_points_derived():
    schema = build_schema()
    pts = schema["adjustable_points"]
    assert len(pts) == len(ADJUSTABLES)
    for p in pts:                              # kind/t 配对约束
        if p["kind"] == "curve":
            assert p["t"] is not None
        else:
            assert p["kind"] == "point" and p["t"] is None
    # 绑定字段完整可回查 binding_for
    from webapp.backend.schema import binding_for
    for p in pts:
        b = p["bindings"][0]
        assert binding_for(p["element"], b["param"], b["axis"]) is not None


# ---------- 绑定 range ⊆ 硬校验（金标，防拖出值后续生成 422） ----------

def test_binding_ranges_within_validation():
    from ylpattern.params import build_issues
    base = {"front_pocket": True}          # 口袋 gate 全开（bulge 默认）
    for adj in ADJUSTABLES:
        for v in (adj.lo, adj.hi):
            issues = build_issues(ADJ_M, {**base, adj.param: v})
            errs = [i for i in issues if i.level == "error"]
            assert not errs, f"{adj.param}={v} 触发硬校验：{[e.message for e in errs]}"
