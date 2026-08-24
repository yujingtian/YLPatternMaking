"""参数分组 schema：web 前端参数面板的唯一数据源。

默认值从 PatternOptions/Measurements 实例**反射**（不在两处维护）；
中文标签从 params 源码行内注释解析（打版师口径注释即现成文案）；
分组为手工白名单（不在白名单的键归入 misc，前端默认收起）。

分组结构对齐 .claude/plans/webapp-phase1.md（16 组）。
"""

from __future__ import annotations

import re
from pathlib import Path

from ylpattern.params import Measurements, PatternOptions
from ylpattern.params import measurements as _m_mod
from ylpattern.params import options as _o_mod

_SRC_OPTIONS = Path(_o_mod.__file__)
_SRC_MEASURES = Path(_m_mod.__file__)

# 前端参数显示名开关：False = 显示英文参数名（key），True = 解析源码注释中文标签
USE_CN_LABELS = False


def _parse_labels(path: Path) -> dict[str, str]:
    """从源码行内注释提取标签：`    name: ... # 标签（说明）...` ->
    "标签"（截到首个全角括号/逗号/分号前）。

    USE_CN_LABELS = False 时前端一律显示英文参数名（用户口径 2026-08）；
    注释解析逻辑保留，置 True 即恢复中文标签。
    """
    if not USE_CN_LABELS:
        return {}
    labels: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s{4}(\w+):[^#]*#\s*(.+?)\s*$", line)
        if m:
            label = re.split(r"[（，；(,;]", m.group(2))[0].strip()
            if label:
                labels[m.group(1)] = label
    return labels


# ---- 16 组参数白名单（键序即展示序） ----

GROUPS: list[dict] = [
    {"key": "measurements", "label": "基础测量", "params": [
        "waist", "hip", "knee", "hem", "front_rise", "back_rise",
        "outseam", "thigh"]},
    {"key": "switches", "label": "款式开关", "params": [
        "front_pouch", "watch_pocket", "back_dart", "back_yoke", "back_patch",
        "belt_loop"]},
    {"key": "waistband", "label": "腰头", "params": [
        "waistband_type", "waistband_width", "waistband_front_drop",
        "waistband_fly_extension", "waistband_full_piece", "waistband_grain",
        "side_rise", "front_waist_curve_sag", "back_waist_curve_sag",
        "waistband_seam_allowances", "waistband_shrinkage_warp",
        "waistband_shrinkage_weft"], "visible_if": None},
    {"key": "front_pocket", "label": "前口袋", "params": [
        "pocket_type", "front_pocket", "front_patch",
        "front_pocket_p1_dist", "front_pocket_p2_drop",
        "front_pocket_dart_width", "front_pocket_paring_n",
        "front_pocket_mouth_mode", "front_pocket_mouth_bulge",
        "front_pocket_mouth_bulge_at", "front_pocket_mouth_h1",
        "front_pocket_mouth_h2", "front_pocket_mouth_corners",
        # 贴袋参数同组互斥显示（参数级 gate=front_patch；元组见 build_schema）
        ("front_patch_top_drop", "front_patch"),
        ("front_patch_top_inset", "front_patch"),
        ("front_patch_width", "front_patch"),
        ("front_patch_height", "front_patch"),
        ("front_patch_shape", "front_patch"),
        ("front_patch_bottom_width", "front_patch"),
        ("front_patch_rotate_deg", "front_patch"),
        ("front_patch_tip_depth", "front_patch"),
        ("front_patch_chamfer", "front_patch"),
        ("front_patch_custom_points", "front_patch"),
        ("front_patch_custom_edges", "front_patch"),
        ("front_patch_seam_allowances", "front_patch"),
        # 口袋裁片缩水率：袋贴/贴袋两形态共用（多键任一真）
        ("front_pocket_shrinkage_warp", ["front_pocket", "front_patch"]),
        ("front_pocket_shrinkage_weft", ["front_pocket", "front_patch"]),
        ],
     # 组常显（承载类型下拉），组内挖削参数仅口袋类型=挖削时逐参数显示
     "param_visible_if": "front_pocket",
     "param_visible_except": ["pocket_type", "front_pocket", "front_patch"]},
    {"key": "facing", "label": "袋贴", "params": [
        "front_pocket_facing", "front_pocket_facing_width",
        "front_pocket_facing_side_w", "front_pocket_facing_mode",
        "front_pocket_facing_h1", "front_pocket_facing_h2",
        "front_pocket_facing_bulge", "front_pocket_facing_bulge_at",
        "front_pocket_facing_seam_allowances"],
     "visible_if": "front_pocket"},
    {"key": "pouch", "label": "袋布", "params": [
        "front_pouch_waist_safe", "front_pouch_side_safe",
        "front_pouch_nodes", "front_pouch_edges",
        "front_pouch_seam_allowances", "front_pouch_shrinkage_warp",
        "front_pouch_shrinkage_weft"],
     "visible_if": ["front_pouch", "front_pocket"]},
    {"key": "watch", "label": "小表袋", "params": [
        "watch_pocket_mode", "watch_pocket_width", "watch_pocket_taper",
        "watch_pocket_offset_from_top", "watch_pocket_offset_from_side",
        "watch_pocket_rotate_deg", "watch_pocket_points",
        "watch_pocket_edges", "watch_pocket_seam_allowances",
        "watch_pocket_shrinkage_warp", "watch_pocket_shrinkage_weft"],
     "visible_if": ["watch_pocket", "front_pocket"]},
    {"key": "fly", "label": "门襟", "params": [
        # 虚拟下拉 fly_type 驱动 fly / fly_separate 互斥开关（前端映射）
        "fly_type", "fly", "fly_separate",
        # 两形态共用（宽/开深/底角，门襟绘制.md §2.2/§3.2 连裁+独立共用）
        ("fly_width", ["fly", "fly_separate"]),
        ("fly_length_ratio", ["fly", "fly_separate"]),
        ("fly_length_base", ["fly", "fly_separate"]),
        ("fly_corner_inset", ["fly", "fly_separate"]),
        ("fly_corner_turn", ["fly", "fly_separate"]),
        ("fly_blend_drop", ["fly", "fly_separate"]),
        # 连裁门襟专属（§3.1 折转退层 / §4.2 J 字明线，上版于前片）
        ("fly_turnback", "fly"),
        ("fly_stitch_inset", "fly"),
        # 独立门襟专属（§5 分裁延展 / 门襟裁片.md 缝份与缩水）
        ("fly_sep_extra", "fly_separate"),
        ("fly_sep_double", "fly_separate"),
        ("fly_seam_allowances", "fly_separate"),
        ("fly_shrinkage_warp", "fly_separate"),
        ("fly_shrinkage_weft", "fly_separate")]},
    {"key": "back_dart", "label": "后省", "params": [
        "back_dart_count", "back_dart_width", "back_dart_length"],
     "visible_if": "back_dart"},
    {"key": "back_yoke", "label": "后机头", "params": [
        "back_yoke_cb_dist", "back_yoke_side_dist", "back_yoke_mid_anchors",
        "back_yoke_edges", "back_yoke_join_fillet",
        "back_yoke_side_corner_mirror", "back_yoke_cb_corner_mirror",
        "back_yoke_seam_allowances", "back_yoke_shrinkage_warp",
        "back_yoke_shrinkage_weft"], "visible_if": "back_yoke"},
    {"key": "back_patch", "label": "后贴袋", "params": [
        "back_patch_inset_x", "back_patch_drop_y", "back_patch_width",
        "back_patch_height", "back_patch_shape",
        # 形态专属参数按 back_patch_shape 联动（baker_shield=底宽+底尖 /
        # angular=底宽+斜切 / custom=角点+边形态，后贴袋绘制.md §二.1）
        ("back_patch_bottom_width", {"param": "back_patch_shape",
                                     "values": ["baker_shield", "angular"]}),
        "back_patch_rotate_deg",
        ("back_patch_tip_depth", {"param": "back_patch_shape",
                                  "values": ["baker_shield"]}),
        ("back_patch_chamfer", {"param": "back_patch_shape",
                                "values": ["angular"]}),
        ("back_patch_custom_points", {"param": "back_patch_shape",
                                      "values": ["custom"]}),
        ("back_patch_custom_edges", {"param": "back_patch_shape",
                                     "values": ["custom"]}),
        "back_patch_seam_allowances", "back_patch_top_hem_taper",
        "back_patch_notch_type", "back_patch_notch_depth",
        "back_patch_shrinkage_warp", "back_patch_shrinkage_weft"],
     "visible_if": "back_patch"},
    {"key": "belt", "label": "裤耳", "params": [
        "belt_loop_width", "belt_loop_unit_length", "belt_loop_count",
        "belt_loop_waste"], "visible_if": "belt_loop"},
    {"key": "thigh", "label": "毗围限制", "params": [
        "thigh_limit", "thigh_measure_offset", "thigh_piece_split_max",
        "thigh_front_share", "thigh_dual_track_min", "thigh_front_crotch_coef",
        "thigh_back_crotch_coef", "thigh_front_crotch_max",
        "thigh_back_crotch_max", "thigh_max_iter", "thigh_tol"],
     "visible_if": "thigh_limit"},
    {"key": "frame", "label": "臀腰裆框架", "params": [
        "delta", "front_crotch_adjust", "back_crotch_adjust",
        "front_intake_ratio", "front_intake_adjust", "back_intake",
        "waist_balance", "front_waist_dart", "back_waist_dart",
        "side_intake_k_waist", "outseam_bulge",
        "waist_rect_len",
        "rise_ratio", "rise_adjust", "crotch_drop_adjust", "back_rise_alpha",
        "back_rise_beta", "front_rise_handle_ratio"]},
    {"key": "legs", "label": "腿部与弧线微调", "params": [
        "front_crease_e", "back_crease_e", "knee_adjust", "hem_adjust",
        "calf_arc_alpha", "inseam_arc_k1", "inseam_arc_ky", "inseam_arc_k2",
        "outseam_arc_dx", "outseam_arc_m2", "back_calf_arc_alpha",
        "back_inseam_arc_k1", "back_inseam_arc_ky", "back_inseam_arc_k2",
        "back_outseam_arc_dx", "back_outseam_arc_m2", "back_hipwaist_arc_dx1",
        "back_hipwaist_arc_k1", "back_hipwaist_arc_dx2",
        "back_hipwaist_arc_k2", "front_hem_arc_sag", "back_hem_arc_sag"]},
    {"key": "shrink", "label": "缩水与缝边", "params": [
        "shrinkage_enabled", "shrinkage_warp", "shrinkage_weft",
        "front_piece_shrinkage_warp", "front_piece_shrinkage_weft",
        "back_piece_shrinkage_warp", "back_piece_shrinkage_weft",
        # 全局缝边参数归此组（默认缝份 + 缝边显示总开关；前后片专属缝份在裁片工艺）
        "seam_allowance", "show_seam_allowance"]},
    {"key": "piece_craft", "label": "裁片工艺", "params": [
        "front_piece_seam_allowances", "front_piece_crotch_corner",
        "front_piece_notch_type", "back_piece_seam_allowances",
        "back_piece_crotch_corner", "back_piece_notch_type"]},
    {"key": "misc", "label": "版面杂项", "params": ["piece_gap", "fit",
                                                    "size_label"],
     "collapsed": True},
]

# 字符串枚举（post_init 白名单校验的 str 字段）：前端渲染下拉
_ENUMS: dict[str, list[str]] = {
    "front_pocket_mouth_mode": ["bulge", "tangent", "polyline"],
    "front_pocket_facing_mode": ["tangent", "offset", "bulge"],
    "front_patch_shape": ["rectangle", "baker_shield", "angular", "custom"],
    "back_patch_shape": ["rectangle", "baker_shield", "angular", "custom"],
    "watch_pocket_mode": ["custom", "facing_intersect"],
    "front_piece_notch_type": ["V", "I"],
    "back_piece_notch_type": ["V", "I"],
    "back_patch_notch_type": ["V", "I"],
    "waistband_type": ["straight", "curved"],
    "waistband_grain": ["width", "length"],
    "fit": ["skinny", "slim", "regular", "loose"],
}


def _sa_fields(sa) -> dict | None:
    """缝份对象 -> {边名: 默认值}（非缝份字段返回 None）。"""
    if sa is None or not hasattr(sa, "__dataclass_fields__"):
        return None
    return {name: getattr(sa, name)
            for name in type(sa).__dataclass_fields__}


# 前端隐藏的原始开关（由 pocket_type / fly_type 虚拟下拉驱动，避免互斥开关双见）
_HIDDEN = {"front_pocket", "front_patch", "fly", "fly_separate"}


def _param_spec(name: str, value, labels: dict[str, str]) -> dict:
    """单参数 schema：类型/默认/枚举/标签。tuple 复杂结构渲染为 JSON 文本。"""
    spec: dict = {"key": name, "label": labels.get(name, name)}
    if name in _HIDDEN:
        spec["hidden"] = True
    if name in _ENUMS:
        enum_val = value.value if hasattr(value, "value") else value
        spec.update(type="enum", choices=_ENUMS[name], default=enum_val)
        return spec
    sa = _sa_fields(value)
    if sa is not None:
        spec.update(type="sa", default=sa)
        return spec
    if isinstance(value, bool):
        spec.update(type="bool", default=value)
    elif isinstance(value, int) and not isinstance(value, bool):
        spec.update(type="int", default=value)
    elif isinstance(value, float):
        spec.update(type="number", default=value,
                    nullable=name.endswith("_drop"))
    elif isinstance(value, str):
        spec.update(type="string", default=value)
    elif value is None:
        spec.update(type="number", default=None, nullable=True)
    else:                       # tuple/list：JSON 文本编辑
        spec.update(type="json", default=list(value))
    return spec


def build_schema() -> dict:
    """组装完整 schema（默认值反射 + 标签解析 + 白名单分组）。"""
    o = PatternOptions()        # post_init 已归一化 tuple 默认值
    m = Measurements(waist=68, hip=91, knee=44, hem=34, front_rise=25,
                     back_rise=33, outseam=102, thigh=58)
    labels = {**_parse_labels(_SRC_OPTIONS), **_parse_labels(_SRC_MEASURES)}
    values = {**vars(m), **vars(o)}

    grouped: set[str] = set()
    groups_out = []
    for g in GROUPS:
        specs = []
        for entry in g["params"]:
            # 条目为 (name, gate) 元组时显式指定参数级联动：gate 为字符串=
            # 布尔开关键（可多键，任一真即显示）；为 {"param","values"} 字典=
            # 枚举参数值匹配（如贴袋形态专属参数随 back_patch_shape 切换）
            name, param_gate = (entry if isinstance(entry, tuple)
                                 else (entry, None))
            if name == "pocket_type":
                # 虚拟参数：口袋类型下拉（挖削/贴袋互斥），前端读写
                # front_pocket / front_patch 两开关（见 ParamPanel）
                specs.append({"key": "pocket_type", "label": "口袋类型",
                              "type": "pocket_type", "default": None,
                              "choices": ["无", "挖削前口袋", "前贴袋"]})
                continue
            if name == "fly_type":
                # 虚拟参数：门襟形态下拉（连裁/独立互斥），前端读写
                # fly / fly_separate 两开关（见 ParamPanel）
                specs.append({"key": "fly_type", "label": "门襟形态",
                              "type": "fly_type", "default": None,
                              "choices": ["无", "连裁门襟", "独立门襟"]})
                continue
            if name not in values:
                raise KeyError(f"schema 白名单引用了不存在的参数:{name}")
            specs.append(_param_spec(name, values[name], labels))
            grouped.add(name)
            if param_gate is not None:
                specs[-1]["visible_if"] = param_gate
            elif (g.get("param_visible_if")
                    and name not in g.get("param_visible_except", ())):
                specs[-1]["visible_if"] = g["param_visible_if"]
        groups_out.append({
            "key": g["key"], "label": g["label"], "params": specs,
            "visible_if": g.get("visible_if"),
            "collapsed": g.get("collapsed", False)})
    # 白名单外的引擎参数归 misc 尾部（不丢功能，防引擎加参数面板缺项）
    for name, value in values.items():
        if name not in grouped:
            groups_out[-1]["params"].append(_param_spec(name, value, labels))

    # 可调点配置表占位（一期只定格式不做交互；二期拖拽微调复用）
    adjustable_points: list[dict] = [
        {"element": "front.pocket_p2", "label": "袋口侧缝端点 P2",
         "bindings": [{"param": "front_pocket_p2_drop", "axis": "y",
                       "range": [2.0, 15.0]}]},
        {"element": "front.pocket_p1", "label": "袋口腰头端点 P1",
         "bindings": [{"param": "front_pocket_p1_dist", "axis": "x",
                       "range": [4.0, 15.0]}]},
    ]
    return {"groups": groups_out, "adjustable_points": adjustable_points}
