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
from ylpattern.webschema import (ADJUSTABLES, build_schema, gate_on, handles,
                                 seed_shape)

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
    assert back["mode"] == front["mode"] == "closed"
    assert back["edge_format"] == front["edge_format"] == "bulge"
    # gate 必须挂到虚拟 spec（build_schema 特判 continue 早于通用挂接点，
    # 曾静默丢失致编辑器在非 custom 形态下也常显）
    assert back["visible_if"] == {"param": "back_patch_shape",
                                  "values": ["custom"]}
    assert front["visible_if"] == {"param": "front_patch_shape",
                                   "values": ["custom"],
                                   "requires": ["front_patch"]}
    # 袋布自由边界：open 链 + spec 边格式 + 近似锚点四参数；链恒自定义无 gate
    pouch = specs["front_pouch_chain"]
    assert pouch["type"] == "custom_shape"
    assert pouch["kind"] == "front_pouch"
    assert pouch["points_key"] == "front_pouch_nodes"
    assert pouch["edges_key"] == "front_pouch_edges"
    assert pouch["v_positive"] == "down"
    assert pouch["mode"] == "open"
    assert pouch["edge_format"] == "spec"
    assert pouch["anchor_keys"] == [
        "front_pocket_p1_dist", "front_pouch_waist_safe",
        "front_pocket_p2_drop", "front_pouch_side_safe"]
    assert pouch["choices"] == ["standard", "round_bottom", "deep_rect"]
    assert "visible_if" not in pouch
    # 小表袋 custom：closed + spec，gate=watch_pocket_mode 值 custom
    watch = specs["watch_pocket_custom"]
    assert watch["kind"] == "watch_pocket"
    assert watch["points_key"] == "watch_pocket_points"
    assert watch["edges_key"] == "watch_pocket_edges"
    assert watch["v_positive"] == "down"
    assert watch["mode"] == "closed"
    assert watch["edge_format"] == "spec"
    assert watch["choices"] == []
    assert watch["visible_if"] == {"param": "watch_pocket_mode",
                                   "values": ["custom"]}
    for k in ("back_patch_custom_points", "back_patch_custom_edges",
              "front_patch_custom_points", "front_patch_custom_edges",
              "front_pouch_nodes", "front_pouch_edges",
              "watch_pocket_points", "watch_pocket_edges"):
        assert specs[k]["hidden"] is True


def test_seed_shape():
    """seed 金标（数值同 tests/test_patch.py）：baker 后侧 bi=1 五边形、
    angular 前侧消费底宽（后侧不消费形成对照）；边恒直线；
    front_pouch 袋型预设（数值同 tests/test_pouch_formula.py，边为完整
    spec 格式）；非法 kind / 预设外 shape 抛 ValueError。"""
    r = seed_shape(
        "back_patch", "baker_shield",
        {"back_patch_width": 14, "back_patch_height": 16,
         "back_patch_bottom_width": 12, "back_patch_tip_depth": 2.5})
    assert r["points"] == [[0.0, 0.0], [14.0, 0.0], [13.0, 16.0],
                           [7.0, 18.5], [1.0, 16.0]]
    assert r["edges"] == [[0.0, 0.5]] * 5
    f = seed_shape(
        "front_patch", "angular",
        {"front_patch_width": 14, "front_patch_height": 16,
         "front_patch_bottom_width": 12, "front_patch_chamfer": 2})
    assert f["points"] == [[0.0, 0.0], [14.0, 0.0], [13.0, 14.0],
                           [11.0, 16.0], [3.0, 16.0], [1.0, 14.0]]
    p = seed_shape("front_pouch", "standard",
                   {"front_pouch_waist_safe": 4, "front_pouch_side_safe": 8})
    assert p["points"] == [[5.0, 16.0], [1.5, 13.5]]
    assert p["edges"] == [["line"], ["arc", 2.5, 0.6], ["line"]]
    # 安全量缺省回退 4/8（中间态可用）
    p2 = seed_shape("front_pouch", "deep_rect", {})
    assert p2["points"] == [[5.5, 20.8], [1.0, 18.4]]
    with pytest.raises(ValueError):
        seed_shape("side_patch", "rectangle", {})
    with pytest.raises(ValueError):
        seed_shape("back_patch", "custom", {})
    with pytest.raises(ValueError):
        seed_shape("front_pouch", "custom", {})


def test_adjustable_points_kind_t_pairing():
    pts = build_schema()["adjustable_points"]
    assert len(pts) == len(ADJUSTABLES)
    for p in pts:
        if p["kind"] == "curve":
            assert p["t"] is not None
        else:
            assert p["kind"] == "point" and p["t"] is None


# ---------- 模式互斥参数显隐（2026-09-24：下拉选到对应模式才显示） ----------

def test_mode_param_gates():
    """模式互斥参数 gate 金标：袋口线/袋贴内边三模式参数、小表袋
    facing_intersect 专属参数、sa 字段级 gate（前片 fly_* 三边随连裁
    门襟、后片上边互补）。steps 各分支单出口消费对应参数（前口袋
    绘制.md §二/§三.3、seam_allowances.py docstring），非当前模式的
    参数在面板不显示。"""
    schema = build_schema()
    specs = {p["key"]: p for s in schema["sections"]
             for g in s["groups"] for p in g["params"]}
    # 袋口线模式：bulge 双参 / tangent 双柄长 / polyline 折角列表；
    # 组无 visible_if（承载类型下拉）故 gate 复合 requires front_pocket
    bulge = {"param": "front_pocket_mouth_mode", "values": ["bulge"],
             "requires": ["front_pocket"]}
    assert specs["front_pocket_mouth_bulge"]["visible_if"] == bulge
    assert specs["front_pocket_mouth_bulge_at"]["visible_if"] == bulge
    tangent = {**bulge, "values": ["tangent"]}
    assert specs["front_pocket_mouth_h1"]["visible_if"] == tangent
    assert specs["front_pocket_mouth_h2"]["visible_if"] == tangent
    assert specs["front_pocket_mouth_corners"]["visible_if"] == {
        **bulge, "values": ["polyline"]}
    # 袋贴内边模式：tangent 双柄长 / bulge 双参（offset 沿袋口净线等距
    # 偏置无专属参数）；requires 复合袋贴开关
    ft = {"param": "front_pocket_facing_mode", "values": ["tangent"],
          "requires": ["front_pocket_facing"]}
    assert specs["front_pocket_facing_h1"]["visible_if"] == ft
    assert specs["front_pocket_facing_h2"]["visible_if"] == ft
    fb = {**ft, "values": ["bulge"]}
    assert specs["front_pocket_facing_bulge"]["visible_if"] == fb
    assert specs["front_pocket_facing_bulge_at"]["visible_if"] == fb
    # 袋贴组参数级 gate：宽/侧深/模式随袋贴开关，开关本身豁免
    assert specs["front_pocket_facing_width"]["visible_if"] \
        == "front_pocket_facing"
    assert specs["front_pocket_facing_mode"]["visible_if"] \
        == "front_pocket_facing"
    assert "visible_if" not in specs["front_pocket_facing"]
    # 小表袋：袋口宽/收拢仅 facing_intersect（custom 净形全由锚点偏移 +
    # points/edges 决定，不消费）；组级 gate 已覆盖两开关
    wi = {"param": "watch_pocket_mode", "values": ["facing_intersect"]}
    assert specs["watch_pocket_width"]["visible_if"] == wi
    assert specs["watch_pocket_taper"]["visible_if"] == wi
    # sa 字段级 gate：前片 fly_* 三边仅连裁消费（fly 且非 fly_separate，
    # 独立门襟 fly_separate 优先——基样模板两开关同 true 按独立判）；
    # mouth 随挖削口袋；后片上边互补（top=有育克、waist=无机头）；
    # 独立门襟 bottom 仅双排
    fly_gate = {"requires": ["fly"], "not": ["fly_separate"]}
    assert specs["front_piece_seam_allowances"]["sa_field_gates"] == {
        "mouth": "front_pocket",
        "fly_top": fly_gate, "fly_outer": fly_gate, "fly_bottom": fly_gate}
    assert specs["back_piece_seam_allowances"]["sa_field_gates"] == {
        "top": "back_yoke", "waist": {"not": ["back_yoke"]}}
    assert specs["fly_seam_allowances"]["sa_field_gates"] == {
        "bottom": "fly_sep_double"}


def test_gate_on_not_semantics():
    """gate_on not 语义（互补开关）：not 键须全假才真；requires/not/
    param 组合按序判定（前端 ParamInput.gateOn 同口径）。"""
    assert gate_on({"not": ["back_yoke"]}, PatternOptions()) is True
    assert gate_on({"not": ["back_yoke"]},
                   PatternOptions.from_dict({"back_yoke": True})) is False
    combo = {"requires": ["front_pocket"], "not": ["front_patch"],
             "param": "front_pocket_mouth_mode", "values": ["bulge"]}
    assert gate_on(combo, PatternOptions.from_dict(
        {"front_pocket": True})) is True
    # requires 假 / not 真 / 枚举不匹配 三路各拦截
    assert gate_on(combo, PatternOptions()) is False
    assert gate_on(combo, PatternOptions.from_dict(
        {"front_pocket": True, "front_patch": True})) is False
    assert gate_on(combo, PatternOptions.from_dict(
        {"front_pocket": True, "front_pocket_mouth_mode": "tangent"})) is False


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
