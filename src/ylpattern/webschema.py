"""参数分组 schema 与拖拽把手：web 前端参数面板的唯一数据源。

本模块是 schema 的**唯一实现**（2026-08 从 webapp/backend/schema.py 下沉到
引擎包）：后端 FastAPI 与浏览器 Pyodide worker 胶水（webapp/engine_glue.py）
共用一份，防两处漂移；webapp/backend/schema.py 只做薄再导出保持 import
路径稳定。依赖方向：webschema -> params / flows.adjust / formulas.patch
（与 api 同层，红线内）；仅 stdlib（re/dataclasses/pathlib），Pyodide 可直接加载。

默认值从 PatternOptions/Measurements 实例**反射**（不在两处维护）；
中文标签从 params 源码行内注释解析（打版师口径注释即现成文案）；
分组为手工白名单（不在白名单的键归入 misc，前端默认收起）。

两段式分组（.claude/plans/webapp-phase2-param-sections.md）：
sections=整版绘制（画在整版 DraftSheet 上的参数）/裁片（各独立裁片的
缩水·缝边·刀口·裁片构造参数）。归属判定：影响整版几何归整版绘制，
只影响裁切链归裁片；裤耳例外（不依赖整版几何，整组归裁片）。
每个裁片的自有工艺参数与其裁片同组、不可分割（用户口径 2026-08-25）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ylpattern.flows.adjust import element_coordinate
from ylpattern.formulas import patch as patch_f
from ylpattern.formulas import pouch as pouch_f
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


# ---- 两段式参数白名单（段→组，键序即展示序；整版绘制 15 组 / 裁片 11 组） ----
# 归属判定见模块 docstring；整版段零缝份/缩水参数（全在裁片段各裁片组内）。

SECTIONS: list[dict] = [
    {"key": "draft", "label": "整版绘制", "collapsed": False, "groups": [
        {"key": "measurements", "label": "基础测量", "params": [
            "waist", "hip", "knee", "hem", "front_rise", "back_rise",
            "outseam", "thigh"]},
        {"key": "switches", "label": "款式开关", "collapsed": True,
         "params": [
            "front_pouch", "watch_pocket", "back_dart", "back_yoke",
            "back_patch", "belt_loop"]},
        {"key": "frame", "label": "臀腰裆框架", "collapsed": True,
         "params": [
            "delta", "front_crotch_adjust", "back_crotch_adjust",
            "front_intake_ratio", "front_intake_adjust", "back_intake",
            "waist_balance", "front_waist_dart", "back_waist_dart",
            "outseam_bulge",
            "waist_rect_len",
            "rise_ratio", "rise_adjust", "crotch_drop_adjust",
            "back_rise_alpha", "back_rise_beta", "front_rise_alpha",
            "front_rise_beta", "front_rise_exit_angle"]},
        # 只留影响整版几何的绘制参数（腰弧 sag 控制上腰口/下腰头线）；
        # front_drop/fly_extension/full_piece/grain/缝份/缩水只在
        # build_waistband 裁切链消费，归裁片段 craft_waistband
        {"key": "waistband", "label": "腰头绘制", "collapsed": True,
         "params": [
            "waistband_type", "waistband_width",
            "side_rise", "front_waist_curve_sag", "back_waist_curve_sag"]},
        {"key": "front_pocket", "label": "前口袋绘制", "collapsed": True,
         "params": [
            "pocket_type", "front_pocket", "front_patch",
            "front_pocket_p1_dist", "front_pocket_p2_drop",
            "front_pocket_dart_width", "front_pocket_paring_n",
            "front_pocket_mouth_mode", "front_pocket_mouth_bulge",
            "front_pocket_mouth_bulge_at", "front_pocket_mouth_h1",
            "front_pocket_mouth_h2", "front_pocket_mouth_corners",
            # 贴袋参数同组互斥显示（参数级 gate=front_patch）；形态专属参数
            # 复合 gate（requires 开关 + front_patch_shape 值匹配，前口袋绘制.md §五）
            ("front_patch_top_drop", "front_patch"),
            ("front_patch_top_inset", "front_patch"),
            ("front_patch_width", "front_patch"),
            ("front_patch_height", "front_patch"),
            ("front_patch_shape", "front_patch"),
            ("front_patch_bottom_width", {"param": "front_patch_shape",
                                          "values": ["baker_shield", "angular",
                                                     "custom"],
                                          "requires": ["front_patch"]}),
            ("front_patch_rotate_deg", "front_patch"),
            ("front_patch_tip_depth", {"param": "front_patch_shape",
                                       "values": ["baker_shield", "custom"],
                                       "requires": ["front_patch"]}),
            ("front_patch_chamfer", {"param": "front_patch_shape",
                                     "values": ["angular", "custom"],
                                     "requires": ["front_patch"]}),
            # custom 结构化编辑器（虚拟参数：读写下方两隐藏真实键，
            # 见 build_schema 特判与 ParamPanel custom_shape 分支）
            ("front_patch_custom", {"param": "front_patch_shape",
                                    "values": ["custom"],
                                    "requires": ["front_patch"]}),
            ("front_patch_custom_points", {"param": "front_patch_shape",
                                           "values": ["custom"],
                                           "requires": ["front_patch"]}),
            ("front_patch_custom_edges", {"param": "front_patch_shape",
                                          "values": ["custom"],
                                          "requires": ["front_patch"]}),
            ],
         # 组常显（承载类型下拉），组内挖削参数仅口袋类型=挖削时逐参数显示
         "param_visible_if": "front_pocket",
         "param_visible_except": ["pocket_type", "front_pocket",
                                  "front_patch"]},
        {"key": "facing", "label": "袋贴", "collapsed": True, "params": [
            "front_pocket_facing", "front_pocket_facing_width",
            "front_pocket_facing_side_w", "front_pocket_facing_mode",
            "front_pocket_facing_h1", "front_pocket_facing_h2",
            "front_pocket_facing_bulge", "front_pocket_facing_bulge_at"],
         "visible_if": "front_pocket"},
        {"key": "pouch", "label": "袋布绘制", "collapsed": True, "params": [
            "front_pouch_waist_safe", "front_pouch_side_safe",
            # 自由边界结构化编辑器（虚拟参数：open 链 + spec 边格式，
            # 读写下方两隐藏真实键；锚点近似定位读上方两安全量）
            ("front_pouch_chain", None),
            "front_pouch_nodes", "front_pouch_edges"],
         "visible_if": ["front_pouch", "front_pocket"]},
        {"key": "watch", "label": "小表袋绘制", "collapsed": True,
         "params": [
            "watch_pocket_mode", "watch_pocket_width", "watch_pocket_taper",
            "watch_pocket_offset_from_top", "watch_pocket_offset_from_side",
            "watch_pocket_rotate_deg",
            # custom 净形结构化编辑器（虚拟参数：closed 链 + spec 边格式，
            # 仅 custom 模式显示；读写下方两隐藏真实键）
            ("watch_pocket_custom", {"param": "watch_pocket_mode",
                                     "values": ["custom"]}),
            "watch_pocket_points", "watch_pocket_edges"],
         "visible_if": ["watch_pocket", "front_pocket"]},
        {"key": "fly", "label": "门襟绘制", "collapsed": True, "params": [
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
            ("fly_stitch_inset", "fly")]},
        {"key": "back_dart", "label": "后省", "collapsed": True, "params": [
            "back_dart_count", "back_dart_width", "back_dart_length"],
         "visible_if": "back_dart"},
        # 只留分割下口线形状（draft 只上版下口线）；倒圆/旋转闭合与
        # 缝份缩水在裁片段 craft_back_yoke
        {"key": "back_yoke", "label": "后机头绘制", "collapsed": True,
         "params": [
            "back_yoke_cb_dist", "back_yoke_side_dist",
            "back_yoke_mid_anchors", "back_yoke_edges"],
         "visible_if": "back_yoke"},
        {"key": "back_patch", "label": "后贴袋绘制", "collapsed": True,
         "params": [
            "back_patch_inset_x", "back_patch_drop_y", "back_patch_width",
            "back_patch_height", "back_patch_shape",
            # 形态专属参数按 back_patch_shape 联动（baker_shield=底宽+底尖 /
            # angular=斜切 / custom=角点+边形态；values 含 custom = 该参数
            # 在 custom 态作为「从形态导入」的基准尺寸可见可调，引擎 custom
            # 分支不消费；后贴袋 angular 不消费底宽，与前贴袋不同——
            # back_patch_steps 六边形顶点全用 w/c，§二.1）
            ("back_patch_bottom_width", {"param": "back_patch_shape",
                                         "values": ["baker_shield", "custom"]}),
            "back_patch_rotate_deg",
            ("back_patch_tip_depth", {"param": "back_patch_shape",
                                      "values": ["baker_shield", "custom"]}),
            ("back_patch_chamfer", {"param": "back_patch_shape",
                                    "values": ["angular", "custom"]}),
            # custom 结构化编辑器（虚拟参数：读写下方两隐藏真实键）
            ("back_patch_custom", {"param": "back_patch_shape",
                                   "values": ["custom"]}),
            ("back_patch_custom_points", {"param": "back_patch_shape",
                                          "values": ["custom"]}),
            ("back_patch_custom_edges", {"param": "back_patch_shape",
                                         "values": ["custom"]})],
         "visible_if": "back_patch"},
        {"key": "legs", "label": "腿部与弧线微调", "collapsed": True,
         "params": [
            "front_crease_e", "back_crease_e", "knee_adjust", "hem_adjust",
            "calf_arc_alpha", "inseam_arc_k1", "inseam_arc_ky",
            "inseam_arc_k2", "outseam_arc_dx", "outseam_arc_m2",
            "back_calf_arc_alpha", "back_inseam_arc_k1",
            "back_inseam_arc_ky", "back_inseam_arc_k2",
            "back_outseam_arc_dx", "back_outseam_arc_m2",
            "back_hipwaist_arc_dx1", "back_hipwaist_arc_k1",
            "back_hipwaist_arc_dx2", "back_hipwaist_arc_k2",
            "front_hem_arc_sag", "back_hem_arc_sag"]},
        {"key": "thigh", "label": "毗围限制", "collapsed": True, "params": [
            "thigh_limit", "thigh_measure_offset", "thigh_piece_split_max",
            "thigh_front_share", "thigh_dual_track_min",
            "thigh_front_crotch_coef", "thigh_back_crotch_coef",
            "thigh_front_crotch_max", "thigh_back_crotch_max",
            "thigh_max_iter", "thigh_tol"],
         "visible_if": "thigh_limit"},
        # 兜底组：白名单外的引擎参数追加至此（见 build_schema）
        {"key": "misc", "label": "版面杂项", "collapsed": True,
         "params": ["piece_gap", "fit", "size_label", "show_labels"]},
    ]},
    {"key": "pieces", "label": "裁片", "collapsed": True, "groups": [
        {"key": "craft_global", "label": "全局工艺", "collapsed": True,
         "params": [
            "shrinkage_enabled", "shrinkage_warp", "shrinkage_weft",
            "seam_allowance", "show_seam_allowance"]},
        {"key": "craft_waistband", "label": "腰头裁片", "collapsed": True,
         "params": [
            "waistband_fly_extension",
            "waistband_full_piece", "waistband_grain",
            "waistband_seam_allowances", "waistband_shrinkage_warp",
            "waistband_shrinkage_weft"]},
        # 组级 gate 无法表达"挖削 OR 贴袋 OR 袋贴"（前端组级是 AND 语义），
        # 故组常显、全参数带参数级 gate：相关开关全关时参数过滤为空，
        # 前端按 params 为空自动隐藏整组
        {"key": "craft_front_pocket", "label": "前口袋裁片",
         "collapsed": True, "params": [
            ("front_patch_seam_allowances", "front_patch"),
            ("front_pocket_facing_seam_allowances", "front_pocket_facing"),
            # 口袋裁片缩水率：袋贴/贴袋两形态共用（多键任一真）
            ("front_pocket_shrinkage_warp", ["front_pocket", "front_patch"]),
            ("front_pocket_shrinkage_weft", ["front_pocket", "front_patch"])]},
        {"key": "craft_pouch", "label": "袋布裁片", "collapsed": True,
         "params": [
            "front_pouch_seam_allowances", "front_pouch_shrinkage_warp",
            "front_pouch_shrinkage_weft"],
         "visible_if": ["front_pouch", "front_pocket"]},
        {"key": "craft_watch", "label": "小表袋裁片", "collapsed": True,
         "params": [
            "watch_pocket_seam_allowances", "watch_pocket_shrinkage_warp",
            "watch_pocket_shrinkage_weft"],
         "visible_if": ["watch_pocket", "front_pocket"]},
        # 独立门襟专属（§5 分裁延展 / 门襟裁片.md 缝份与缩水）；
        # 参数级 gate 与组级一致（自文档，双保险）
        {"key": "craft_fly", "label": "门襟裁片", "collapsed": True,
         "params": [
            ("fly_sep_extra", "fly_separate"),
            ("fly_sep_double", "fly_separate"),
            ("fly_seam_allowances", "fly_separate"),
            ("fly_shrinkage_warp", "fly_separate"),
            ("fly_shrinkage_weft", "fly_separate")],
         "visible_if": "fly_separate"},
        # 裁切链专属：拼合处 G1 倒圆 / 绕省尖旋转闭合（draft 只画分割下口线）
        {"key": "craft_back_yoke", "label": "后机头裁片", "collapsed": True,
         "params": [
            "back_yoke_join_fillet", "back_yoke_side_corner_mirror",
            "back_yoke_cb_corner_mirror", "back_yoke_seam_allowances",
            "back_yoke_shrinkage_warp", "back_yoke_shrinkage_weft"],
         "visible_if": "back_yoke"},
        {"key": "craft_back_patch", "label": "后贴袋裁片", "collapsed": True,
         "params": [
            "back_patch_top_hem_taper", "back_patch_notch_type",
            "back_patch_notch_depth", "back_patch_seam_allowances",
            "back_patch_shrinkage_warp", "back_patch_shrinkage_weft"],
         "visible_if": "back_patch"},
        # 净裁无缝份不折边、不走 cutter，无缩水缝边参数
        {"key": "craft_belt", "label": "裤耳裁片", "collapsed": True,
         "params": [
            "belt_loop_width", "belt_loop_unit_length", "belt_loop_count",
            "belt_loop_waste"],
         "visible_if": "belt_loop"},
        # 裁片自有工艺参数同组不拆分：缝份+裆尖角+刀口+缩水率（用户口径 2026-08-25）
        {"key": "craft_front_piece", "label": "前片", "collapsed": True,
         "params": [
            "front_piece_seam_allowances", "front_piece_crotch_corner",
            "front_piece_notch_type", "front_piece_shrinkage_warp",
            "front_piece_shrinkage_weft"]},
        {"key": "craft_back_piece", "label": "后片", "collapsed": True,
         "params": [
            "back_piece_seam_allowances", "back_piece_crotch_corner",
            "back_piece_notch_type", "back_piece_shrinkage_warp",
            "back_piece_shrinkage_weft"]},
    ]},
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


# ---- 可调把手绑定表（二期拖拽调版；.doc/python工程设计.md §10.7） ----
# 每条绑定 = 定位元素（点 / 曲线 t 处）沿单轴拖动 -> 反解单参数。
# 选参原则（后续加绑定沿用）：同一几何量有"系数/规律参数"与"_adjust 修正量"
# 两入口时一律绑修正量——cm 1:1 拖感、跨尺寸/推码稳健、语义=调版旋钮；
# 仅比例单入口时兜底绑比例（back_intake）。range 端点必须落在
# PatternOptions 硬校验内（tests/test_web_adjust.py 金标防漂移）；
# 被浪长闭合锁死的点（前浪顶点类）不纳入——几何事实而非实现限制。


@dataclass(frozen=True)
class Adjustable:
    """一条拖拽绑定：把手 element（kind=curve 时定位在参数 t 处）沿
    axis 拖动，经 /api/adjust 反解 param 至 [lo, hi] 内。"""

    element: str
    label: str
    kind: str                          # point / curve
    param: str
    axis: str                          # "x" / "y"
    lo: float
    hi: float
    t: float | None = None             # curve 定位参数（point 恒 None）
    visible_if: object | None = None   # gate：str=布尔开关 / dict=枚举匹配


ADJUSTABLES: list[Adjustable] = [
    Adjustable("front.pocket_p1", "袋口腰头端 P1", "point",
               "front_pocket_p1_dist", "x", 4.0, 15.0,
               visible_if="front_pocket"),
    Adjustable("front.pocket_p2", "袋口侧缝端 P2", "point",
               "front_pocket_p2_drop", "y", 2.0, 15.0,
               visible_if="front_pocket"),
    Adjustable("front.pocket_mouth", "袋口弧线", "curve",
               "front_pocket_mouth_bulge", "x", 0.0, 3.0, t=0.5,
               visible_if={"param": "front_pocket_mouth_mode",
                           "values": ["bulge"],
                           "requires": ["front_pocket"]}),
    Adjustable("front.crotch_vertex", "前小裆顶点", "point",
               "front_crotch_adjust", "x", -1.5, 1.0),
    Adjustable("back.crotch_vertex", "后大裆顶点", "point",
               "back_crotch_adjust", "x", -1.0, 2.0),
    Adjustable("front.knee_outseam_point", "膝围外缝点", "point",
               "knee_adjust", "x", 0.0, 2.0),
    Adjustable("front.hem_outseam_point", "脚口外缝点", "point",
               "hem_adjust", "x", 0.0, 2.0),
    Adjustable("front.hem", "前脚口弧", "curve",
               "front_hem_arc_sag", "y", 0.0, 1.5, t=0.5),
    Adjustable("back.hem", "后脚口弧", "curve",
               "back_hem_arc_sag", "y", 0.0, 1.5, t=0.5),
    Adjustable("front.outseam_upper", "前外缝上段", "curve",
               "outseam_arc_dx", "x", 0.0, 0.6, t=0.5),
    Adjustable("back.outseam_upper", "后外缝上段", "curve",
               "back_outseam_arc_dx", "x", 0.0, 0.6, t=0.5),
    Adjustable("back.outseam_hip_waist", "后臀腰弧", "curve",
               "back_hipwaist_arc_dx1", "x", 0.0, 0.5, t=0.5),
    Adjustable("front.waistline_arc", "前腰弧", "curve",
               "front_waist_curve_sag", "y", 0.0, 1.0, t=0.5),
    Adjustable("back.waistline_arc", "后腰弧", "curve",
               "back_waist_curve_sag", "y", 0.0, 1.0, t=0.5),
    Adjustable("front.center_intake_point", "前中内收点", "point",
               "front_intake_adjust", "x", -2.0, 3.0),
    Adjustable("back.center_intake_point", "后中内收点", "point",
               "back_intake", "x", 1.5, 4.5),
]


def gate_on(gate, o: PatternOptions) -> bool:
    """参数级 gate 判定（与前端 ParamPanel.gateOn 同语义）：
    字符串 = 布尔开关键；dict = {param, values, requires} 枚举值匹配
    （requires 布尔开关须同时全真）。"""
    if isinstance(gate, str):
        return bool(getattr(o, gate, False))
    if not all(bool(getattr(o, k, False)) for k in gate.get("requires", ())):
        return False
    v = getattr(o, gate["param"], None)
    return v is not None and str(v) in gate["values"]


def binding_for(element: str, param: str, axis: str) -> Adjustable | None:
    """按 (element, param, axis) 查绑定表；未注册返回 None（/api/adjust 422）。"""
    for adj in ADJUSTABLES:
        if (adj.element, adj.param, adj.axis) == (element, param, axis):
            return adj
    return None


def handles(ctx, o: PatternOptions) -> list[dict]:
    """可调把手清单（二期拖拽）：ADJUSTABLES 逐条元素级自门控——
    gate 满足且元素在版上才下发坐标，前端零重复判断开关/形态。

    （2026-08 自 webapp/backend/app.py._handles 下沉：后端 /api/draft/sheet
    与浏览器 worker 胶水共用本实现，金标 test_engine_glue.py 钉死一致。）
    """
    out: list[dict] = []
    for adj in ADJUSTABLES:
        if adj.visible_if is not None and not gate_on(adj.visible_if, o):
            continue
        try:
            x = element_coordinate(ctx, adj.element, "x", t=adj.t)
            y = element_coordinate(ctx, adj.element, "y", t=adj.t)
        except (KeyError, TypeError, ValueError):
            continue        # 元素不在版上（开关/形态未开）：跳过
        out.append({"element": adj.element, "label": adj.label,
                    "kind": adj.kind, "t": adj.t, "x": x, "y": y,
                    "bindings": [{"param": adj.param, "axis": adj.axis,
                                  "range": [adj.lo, adj.hi]}]})
    return out


def seed_shape(kind: str, shape: str, options: dict) -> dict:
    """预设形态 -> custom 初始点/边（web「从形态导入」seed，§10.8）。

    kind 取 front_patch / back_patch / front_pouch：
      贴袋两侧自 options 提取该侧 5 个尺寸参数（{kind}_width / _height /
      _bottom_width / _tip_depth / _chamfer）代入
      formulas.patch.patch_net_vertices，返回 **v 向下正**规范系角点
      （前后侧统一；前侧编辑器写回时 dy 自行取负）与全直线边（预设形态
      引擎本就逐边画直线，steps 走 (0.0, 0.5) 分支）；
      front_pouch 提取 waist_safe/side_safe 两安全量（缺省回退 4/8）代入
      formulas.pouch.pouch_chain_preset，返回 K 节点（v 向下正）与边形态
      完整 spec 格式（[\"line\"] / [\"arc\",b,at] / [\"bezier\",...]）。
    非法 kind/shape 抛 ValueError（HTTP 422 / 引擎胶水 _ValidationError，
    两通道同构）。

    不走 PatternOptions 构造：seed 只依赖这几个参数，且其余参数处于
    中间态（可能暂时非法）时也要可用，避免无谓 422 耦合。
    """

    def _num(key: str, default: float | None = None) -> float:
        v = options.get(key, default)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"seed 依赖参数 {key} 缺失或非数值：{v!r}")
        return float(v)

    if kind in ("front_patch", "back_patch"):
        pts = patch_f.patch_net_vertices(
            shape,
            _num(f"{kind}_width"), _num(f"{kind}_height"),
            bottom_width=_num(f"{kind}_bottom_width", 0.0),
            tip_depth=_num(f"{kind}_tip_depth", 0.0),
            chamfer=_num(f"{kind}_chamfer", 0.0),
            chamfer_bottom_taper=(kind == "front_patch"))
        return {"ok": True,
                "points": [[float(u), float(v)] for u, v in pts],
                "edges": [[0.0, 0.5] for _ in range(len(pts))]}
    if kind == "front_pouch":
        nodes, edges = pouch_f.pouch_chain_preset(
            shape,
            _num("front_pouch_waist_safe", 4.0),
            _num("front_pouch_side_safe", 8.0))
        return {"ok": True,
                "points": [[float(dx), float(dy)] for dx, dy in nodes],
                "edges": [list(e) for e in edges]}
    raise ValueError(
        f"未知 seed kind={kind!r}（取 front_patch/back_patch/front_pouch）")


def _sa_fields(sa) -> dict | None:
    """缝份对象 -> {边名: 默认值}（非缝份字段返回 None）。"""
    if sa is None or not hasattr(sa, "__dataclass_fields__"):
        return None
    return {name: getattr(sa, name)
            for name in type(sa).__dataclass_fields__}


# 前端隐藏的原始开关与原始 json 键（前者由 pocket_type / fly_type 虚拟下拉
# 驱动，避免互斥开关双见；后者由 *_custom / *_chain 虚拟参数的 custom_shape
# 结构化编辑器读写——两套 UI 并存编辑同一数据必然漂移。参数仍进 schema
# 全集：422 校验错误归因到这些键、由编辑器合并承接，toml 导出亦不受影响）
_HIDDEN = {"front_pocket", "front_patch", "fly", "fly_separate",
           "front_patch_custom_points", "front_patch_custom_edges",
           "back_patch_custom_points", "back_patch_custom_edges",
           "front_pouch_nodes", "front_pouch_edges",
           "watch_pocket_points", "watch_pocket_edges"}

# custom_shape 虚拟参数 spec 表（mode × edge_format 两维，§10.7）：
#   closed+bulge  前/后贴袋（闭合多边形、边=(弧高,位置) 二元组）；
#   closed+spec   小表袋 custom（闭合、边三模式 line/arc/bezier）；
#   open+spec     袋布自由边界（开放链 P_w0→K1..Kn→P_s0，两端锚点由
#                 anchor_keys 四参数前端近似定位、不可拖——真实锚点由
#                 整版腰弧/外缝几何决定）。choices 为 seed 可导入的预设
#   （空 = 无导入）；v_positive 标存储值第二轴方向（前贴袋 dy 向上正是
#   唯一异类，编辑器内部归一为 v 向下正显示）。
_SHAPE_EDITOR_SPECS = {
    "back_patch_custom": {
        "label": "自定义形态编辑", "kind": "back_patch",
        "points_key": "back_patch_custom_points",
        "edges_key": "back_patch_custom_edges",
        "v_positive": "down", "mode": "closed", "edge_format": "bulge",
        "choices": ["rectangle", "baker_shield", "angular"]},
    "front_patch_custom": {
        "label": "自定义形态编辑", "kind": "front_patch",
        "points_key": "front_patch_custom_points",
        "edges_key": "front_patch_custom_edges",
        "v_positive": "up", "mode": "closed", "edge_format": "bulge",
        "choices": ["rectangle", "baker_shield", "angular"]},
    "front_pouch_chain": {
        "label": "自由边界编辑", "kind": "front_pouch",
        "points_key": "front_pouch_nodes",
        "edges_key": "front_pouch_edges",
        "v_positive": "down", "mode": "open", "edge_format": "spec",
        "anchor_keys": ["front_pocket_p1_dist", "front_pouch_waist_safe",
                        "front_pocket_p2_drop", "front_pouch_side_safe"],
        "choices": ["standard", "round_bottom", "deep_rect"]},
    "watch_pocket_custom": {
        "label": "自定义形态编辑", "kind": "watch_pocket",
        "points_key": "watch_pocket_points",
        "edges_key": "watch_pocket_edges",
        "v_positive": "down", "mode": "closed", "edge_format": "spec",
        "choices": []},
}


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
    """组装完整 schema（默认值反射 + 标签解析 + 两段式白名单分组）。"""
    o = PatternOptions()        # post_init 已归一化 tuple 默认值
    m = Measurements(waist=68, hip=91, knee=44, hem=34, front_rise=25,
                     back_rise=33, outseam=102, thigh=58)
    labels = {**_parse_labels(_SRC_OPTIONS), **_parse_labels(_SRC_MEASURES)}
    values = {**vars(m), **vars(o)}

    grouped: set[str] = set()
    sections_out: list[dict] = []
    fallback: dict | None = None     # misc 组引用：白名单外参数兜底目标
    for s in SECTIONS:
        groups_out = []
        for g in s["groups"]:
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
                    if param_gate is not None:
                        specs[-1]["visible_if"] = param_gate
                    continue
                if name == "fly_type":
                    # 虚拟参数：门襟形态下拉（连裁/独立互斥），前端读写
                    # fly / fly_separate 两开关（见 ParamPanel）
                    specs.append({"key": "fly_type", "label": "门襟形态",
                                  "type": "fly_type", "default": None,
                                  "choices": ["无", "连裁门襟", "独立门襟"]})
                    if param_gate is not None:
                        specs[-1]["visible_if"] = param_gate
                    continue
                if name in _SHAPE_EDITOR_SPECS:
                    # 虚拟参数：custom 形态/链结构化编辑器（spec 元数据含义
                    # 见 _SHAPE_EDITOR_SPECS 注释），前端读写 points_key /
                    # edges_key 两隐藏真实键（ParamPanel custom_shape 分支）
                    spec = {"key": name, "type": "custom_shape",
                            "default": None}
                    spec.update(_SHAPE_EDITOR_SPECS[name])
                    specs.append(spec)
                    # 虚拟参数同样吃参数级 gate（custom 编辑器仅 shape=custom
                    # 时显示——continue 早于通用挂接点，须在此单独挂）
                    if param_gate is not None:
                        specs[-1]["visible_if"] = param_gate
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
            if g["key"] == "misc":
                fallback = groups_out[-1]
        sections_out.append({
            "key": s["key"], "label": s["label"],
            "collapsed": s.get("collapsed", False), "groups": groups_out})
    # 白名单外的引擎参数归 misc 尾部（不丢功能，防引擎加参数面板缺项）；
    # misc 被误删时兜底目标缺失，快失败优于静默丢参数
    if fallback is None:
        raise KeyError("SECTIONS 白名单缺少 misc 组：白名单外参数无兜底目标")
    for name, value in values.items():
        if name not in grouped:
            fallback["params"].append(_param_spec(name, value, labels))

    # 可调把手从 ADJUSTABLES 派生（一期 adjustable_points 字段名保留，
    # 前端兼容；新增 kind/t/visible_if 供二期拖拽消费）
    adjustable_points = [
        {"element": adj.element, "label": adj.label,
         "kind": adj.kind, "t": adj.t, "visible_if": adj.visible_if,
         "bindings": [{"param": adj.param, "axis": adj.axis,
                       "range": [adj.lo, adj.hi]}]}
        for adj in ADJUSTABLES]
    return {"sections": sections_out,
            "adjustable_points": adjustable_points}
