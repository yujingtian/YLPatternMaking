"""参数面元数据登记处：全参数调版映射面的生成底座（2026-09-27）。

口径（.doc/python工程设计.md §10.9.2「调版映射」条）：
- 映射面 = PatternOptions 全部标量参数**自动生成**（用户口径 2026-09-27：
  手工挑键局限且会漂移）+ META 精定标 override + 1 个虚键
  （front_pocket_mouth_depth —— bulge 单通道，映射为弧高绝对值）；
- **漂移金标**：set(META) == {PatternOptions 标量字段} − EXCLUDED——引擎
  增删参数未同步登记，tests/test_agent_adjust.py 即红；登记 = 补一行
  label/group；
- 默认值自省（__dataclass_fields__）；数值边界带 = default±nice(|d|/2)
  咨询带经 validator 探测向内二分夹界（from_dict 单值试构造 try/except，
  表面构建时跑一次缓存）——**带只是步进钳位/prompt 展示的咨询值，真守卫
  仍是引擎 validate/probe**（撞上跨字段约束把带探窄无害）；枚举值域与
  webschema._ENUMS / schema.MODEL_KEYS 同源；bool → ("on","off") 档；
- 步长缺省 nice((hi−lo)/5)（2~5 步走满带），META 精定标优先；
- **通道分配**：键 ∈ schema.ENUM_DEFAULTS ∪ prejudge.prior_switches（merge
  的 hint 消费面）→ channel="hint"（走现有 seed_hints，管线零改动）；
  其余（全部数值键 + 外围开关/枚举）→ "override"（extract_from_input 的
  seed_overrides 注入缝）；
- LOCKED：标量但映射停用（防双通道漂移/无稳定感知语义的几何柄），
  不进 prompt、不出现在映射输出，理由逐键注释。

依赖方向：agent → ylpattern（params.options/webschema 同源只读），
本模块不 import provider（无配置环境零影响）。
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from enum import Enum

from ylpattern.params.options import PatternOptions

# -- 部位分组（prompt 分区渲染序；「用户指部位不指参数」的导航结构） ----------

GROUP_ORDER = ("全局", "腰头", "省道", "前裆", "后裆", "侧缝", "内缝",
               "裤中线", "小腿", "脚口", "袋口", "袋贴", "袋布", "小表袋",
               "前贴袋", "后贴袋", "后育克", "门襟", "裤耳", "前片裁片",
               "后片裁片", "缩水")


@dataclass(frozen=True)
class MetaEntry:
    """单键手写登记：人话标签 + 部位分组 + 可选精定标。

    label/semantics 翻译自 options.py 行内注释（感知语义照抄原话）；
    精定标（step/lo/hi/levels/ordinal）是质量锚点，缺省走自动派生。
    """

    label: str
    group: str
    semantics: str = ""
    step: float | None = None
    lo: float | None = None
    hi: float | None = None
    levels: tuple = ()          # 非空 = 档位键（int 档配 level_values 规则见下）
    ordinal: bool = False       # 档位有序才接受步进
    gate: object = None         # None | 布尔开关键 | {param, values, requires, not}
    locked: bool = False        # 映射停用（不进 prompt）


@dataclass(frozen=True)
class AdjustKeySpec:
    """映射面终态规格（adjust_surface 产物；adjust.py/WP3/WP4 消费）。"""

    key: str
    label: str
    semantics: str
    group: str
    channel: str          # "hint"（现有 seed_hints）| "override"（seed_overrides）
    levels: tuple         # 档位名（bool→on/off；数值键为空）
    ordinal: bool
    step: float           # 数值步长（档位键 = 0）
    lo: float             # 数值钳位带（档位键 = 0）
    hi: float
    default: object       # 引擎默认（自省；枚举已转 str 值）
    gate: object
    locked: bool
    target: str = ""          # 虚键落点（非空 = 本键非引擎键，值写 target）
    level_values: tuple = ()  # 虚键档位 → 绝对值（与 levels 对齐）


# -- 停用面（EXCLUDED：非语义/复杂结构键，逐键原因） ----------------------------

EXCLUDED: dict[str, str] = {
    # 出口显示 / 元数据 / 排版（非服装几何）
    "show_labels": "整版标注显示开关（出口层显示控制，非几何）",
    "show_seam_allowance": "缝边显示开关（出口层显示控制，非几何）",
    "size_label": "尺码标签（订单元数据，不参与几何）",
    "piece_gap": "前后片排版间距（版面布局，非服装参数）",
    # tuple / 联合类型复杂结构
    "back_dart_width": "tuple|float 联合（省量由 K4 缺额派生发射）",
    "back_yoke_mid_anchors": "tuple 锚点表（复杂结构）",
    "back_yoke_edges": "tuple 边形态表（复杂结构）",
    "front_pocket_mouth_corners": "tuple 折角表（复杂结构）",
    "front_patch_custom_points": "custom 角点 tuple（复杂结构）",
    "front_patch_custom_edges": "custom 边形态 tuple（复杂结构）",
    "back_patch_custom_points": "custom 角点 tuple（复杂结构）",
    "back_patch_custom_edges": "custom 边形态 tuple（复杂结构）",
    "front_pouch_nodes": "袋布节点 tuple（复杂结构）",
    "front_pouch_edges": "袋布边形态 tuple（复杂结构）",
    "watch_pocket_points": "小表袋锚点 tuple（复杂结构）",
    "watch_pocket_edges": "小表袋边形态 tuple（复杂结构）",
    # 嵌套缝份对象（内部键，感知面是默认缝份/专用率整体）
    "back_yoke_seam_allowances": "嵌套缝份对象",
    "back_patch_seam_allowances": "嵌套缝份对象",
    "front_piece_seam_allowances": "嵌套缝份对象",
    "back_piece_seam_allowances": "嵌套缝份对象",
    "front_pouch_seam_allowances": "嵌套缝份对象",
    "watch_pocket_seam_allowances": "嵌套缝份对象",
    "fly_seam_allowances": "嵌套缝份对象",
    "waistband_seam_allowances": "嵌套缝份对象",
    "front_pocket_facing_seam_allowances": "嵌套缝份对象",
    "front_patch_seam_allowances": "嵌套缝份对象",
    # None 三态 / 自适应语义（默认值不是标量）
    "back_yoke_join_fillet": "None=按邻边自适应倒圆（手动值覆盖自适应口径）",
    "fly_blend_drop": "None=自适应融合弧（默认非标量）",
    "back_yoke_shrinkage_warp": "None=回退全局缩水（三态）",
    "back_yoke_shrinkage_weft": "None=回退全局缩水（三态）",
    "back_patch_shrinkage_warp": "None=回退全局缩水（三态）",
    "back_patch_shrinkage_weft": "None=回退全局缩水（三态）",
    "front_piece_shrinkage_warp": "None=回退全局缩水（三态）",
    "front_piece_shrinkage_weft": "None=回退全局缩水（三态）",
    "back_piece_shrinkage_warp": "None=回退全局缩水（三态）",
    "back_piece_shrinkage_weft": "None=回退全局缩水（三态）",
    "fly_shrinkage_warp": "None=回退全局缩水（三态）",
    "fly_shrinkage_weft": "None=回退全局缩水（三态）",
    "waistband_shrinkage_warp": "None=回退全局缩水（三态）",
    "waistband_shrinkage_weft": "None=回退全局缩水（三态）",
    "front_pocket_shrinkage_warp": "None=回退全局缩水（三态）",
    "front_pocket_shrinkage_weft": "None=回退全局缩水（三态）",
    # 毗围闭环求解器内部参数（感知面 = 大腿围尺寸本身，S1 领地）
    "thigh_limit": "毗围闭环总开关（thigh 尺寸录入即开，求解器内部）",
    "thigh_measure_offset": "毗围实测下移量（量体口径，求解器内部）",
    "thigh_piece_split_max": "毗围闭环双轨分流参数（求解器内部）",
    "thigh_front_share": "毗围闭环前片分配比（求解器内部）",
    "thigh_dual_track_min": "毗围闭环双轨阈值（求解器内部）",
    "thigh_front_crotch_coef": "毗围闭环裆弯系数（求解器内部）",
    "thigh_back_crotch_coef": "毗围闭环裆弯系数（求解器内部）",
    "thigh_front_crotch_max": "毗围闭环累计上限（求解器内部）",
    "thigh_back_crotch_max": "毗围闭环累计上限（求解器内部）",
    "thigh_max_iter": "闭环最大迭代轮数（求解器内部）",
    "thigh_tol": "闭环收敛容差（求解器内部）",
}


# -- META 登记（每标量键一行；label/semantics 译自 options.py 行内注释） -------

META: dict[str, MetaEntry] = {
    # 全局框架
    "delta": MetaEntry("前后片臀围调节量", "全局", "大=前后片侧缝整体外移",
                       step=0.25, lo=0.0, hi=2.0),
    "waist_balance": MetaEntry(
        "腰围前后分配", "全局",
        "默认=臀围调节量同值（臀腰同调）；正=后腰加前腰减；负=反向",
        step=0.25, lo=-2.0, hi=2.0),   # 对齐 delta 上限（防默认 1.35 顶穿
        # 钳位端点致步进方向反转，2026-09-29）
    "front_waist_dart": MetaEntry("前腰长调节量", "全局",
                                  "前片纯腰长微调（不吃省宽）"),
    "back_waist_dart": MetaEntry("后腰长调节量", "全局",
                                 "后片纯腰长微调（不吃省宽）"),
    "fit": MetaEntry("版型松紧", "全局",
                     "整体松紧找本键；弧线形状找各弧线键",
                     levels=("skinny", "slim", "regular", "loose"), ordinal=True),
    "seam_allowance": MetaEntry("默认缝份", "全局", "裁片缝边宽度",
                                step=0.25, lo=0.5, hi=3.0),
    "rise_adjust": MetaEntry("直裆深修正量", "全局",
                             "大=裆位下落（腰位变低），小=上提",
                             step=0.5, lo=-3.5, hi=4.5),
    # 腰头
    "waistband_type": MetaEntry("腰头类型", "腰头",
                                "straight 等宽直条 / curved 前中下凹弯腰头",
                                levels=("straight", "curved")),
    "waistband_width": MetaEntry("腰头宽", "腰头", "腰头高度",
                                 step=0.5, lo=2.0, hi=6.0),
    "waistband_fly_extension": MetaEntry("门襟搭门量", "腰头",
                                         "腰头左端门襟外延长（宝剑头）"),
    "waistband_full_piece": MetaEntry("腰头整条/分两片", "腰头",
                                      "开=整条后中折线对称"),
    "waistband_grain": MetaEntry("腰头裁片经向", "腰头",
                                 "width 横裁（默认）/ length 直裁",
                                 levels=("width", "length")),
    # 省道
    "back_dart": MetaEntry("后腰省开关", "省道", "后片竖向省道"),
    "back_dart_count": MetaEntry("后腰省省数", "省道",
                                 "1=腰头两等分单省；2=三等分双省",
                                 levels=("1", "2"), gate="back_dart"),
    "back_dart_length": MetaEntry("后腰省长度", "省道", "省尖到腰口深",
                                  step=1.0, lo=6.0, hi=16.0, gate="back_dart"),
    # 前裆
    "front_crotch_adjust": MetaEntry("前小裆修正量", "前裆",
                                     "正=前小裆外放、负=内收",
                                     step=0.25, lo=-1.5, hi=1.0),
    "front_intake_ratio": MetaEntry("前中内收比例", "前裆",
                                    "大=前中腰口内收多",
                                    step=0.05, lo=0.05, hi=0.9),
    "front_intake_adjust": MetaEntry("前中内收微调", "前裆",
                                     "正=在预测之上再内收",
                                     step=0.5, lo=-2.0, hi=3.0),
    "front_rise_alpha": MetaEntry("前裆弯位置系数", "前裆",
                                  "大=近臀段平直、弯度下移",
                                  step=0.04, lo=0.25, hi=0.45),
    "front_rise_beta": MetaEntry("前裆底饱满度", "前裆",
                                 "大=裆底越饱满",
                                 step=0.04, lo=0.25, hi=0.45),
    "front_rise_exit_angle": MetaEntry("前裆底圆角", "前裆",
                                       "0=留裆尖；大=裆底圆角化（紧身/弹力 10~25）",
                                       step=10.0, lo=0.0, hi=30.0),
    # 后裆
    "back_crotch_adjust": MetaEntry("后大裆修正量", "后裆",
                                    "正=后大裆外放",
                                    step=0.25, lo=-1.0, hi=2.0),
    "back_intake": MetaEntry("后中内收量", "后裆",
                             "大=后腰后中收进多（15:X 模数的 X）",
                             step=0.25, lo=1.5, hi=4.5),
    "crotch_drop_adjust": MetaEntry("落裆修正量", "后裆",
                                    "正=后片落裆加深",
                                    step=0.25, lo=-1.0, hi=1.0),
    "back_rise_alpha": MetaEntry("后裆弯位置系数", "后裆",
                                 "后浪上段弯度位置",
                                 step=0.015, lo=0.38, hi=0.42),
    "back_rise_beta": MetaEntry("后浪提臀", "后裆",
                                "大=提臀（紧身 0.55）",
                                step=0.025, lo=0.48, hi=0.55),
    # 侧缝 / 腰口弧
    "side_rise": MetaEntry("侧缝腰口抬高量", "侧缝",
                           "大=侧缝腰口上抬", step=0.25, lo=0.0, hi=2.0),
    "outseam_bulge": MetaEntry("前侧缝腰臀外凸", "侧缝",
                               "外侧缝上段弧外凸量",
                               step=0.05, lo=0.1, hi=0.6),
    "front_waist_curve_sag": MetaEntry("前腰口弧凹度", "侧缝",
                                       "大=腰弧下凹多",
                                       step=0.1, lo=0.0, hi=1.0),
    "back_waist_curve_sag": MetaEntry("后腰口弧凹度", "侧缝",
                                      "同上（后片独立）",
                                      step=0.1, lo=0.0, hi=1.0),
    "outseam_arc_dx": MetaEntry("前外缝大转子外凸", "侧缝",
                                "大腿段大转子外凸量",
                                step=0.05, lo=0.0, hi=0.6),
    "outseam_arc_m2": MetaEntry("前外缝下段弯度", "侧缝",
                                "外缝大腿段切线柄长系数（大=弧线越弯）"),
    "back_outseam_arc_dx": MetaEntry("后外缝臀侧饱满", "侧缝",
                                     "大腿段臀侧饱满度",
                                     step=0.05, lo=0.0, hi=0.6),
    "back_outseam_arc_m2": MetaEntry("后外缝下段弯度", "侧缝",
                                     "后外缝大腿段切线柄长系数（大=弧线越弯）"),
    "back_hipwaist_arc_dx1": MetaEntry("后臀腰段外鼓量", "侧缝",
                                       "0=顺直，大=往外鼓",
                                       step=0.05, lo=0.0, hi=0.5),
    "back_hipwaist_arc_k1": MetaEntry("后臀腰弧上段弯度", "侧缝",
                                      "臀侧凸感延续多高（越大越晚往腰头弯）"),
    "back_hipwaist_arc_k2": MetaEntry("后臀腰弧下段弯度", "侧缝",
                                      "多早往腰头收（越大上段越早内缩、"
                                      "末端笔直进角）"),
    "back_hipwaist_arc_dx2": MetaEntry("后臀腰段下段鼓量", "侧缝", "",
                                       locked=True),   # 与 dx1 感知重叠
    # 内缝
    "inseam_arc_k1": MetaEntry("前内缝上段弧度", "内缝",
                               "内缝大腿段小裆弯度（0.15~0.25）"),
    "inseam_arc_ky": MetaEntry("前内缝膝段弯曲权重", "内缝",
                               "内缝大腿段纵向位置系数"),
    "inseam_arc_k2": MetaEntry("前内缝下段弧度", "内缝",
                               "内缝大腿段切线柄长系数（大=弧线越弯）"),
    "back_inseam_arc_k1": MetaEntry("后内缝上段弧度", "内缝",
                                    "后内缝大腿段大裆弯度（0.25~0.35，"
                                    "大于前片留运动空间）"),
    "back_inseam_arc_ky": MetaEntry("后内缝膝段弯曲权重", "内缝",
                                    "后内缝大腿段纵向位置系数"),
    "back_inseam_arc_k2": MetaEntry("后内缝下段弧度", "内缝",
                                    "后内缝大腿段切线柄长系数（大=弧线越弯）"),
    # 裤中线
    "front_crease_e": MetaEntry("前裤中线偏置", "裤中线",
                                "大=前烫迹线向内侧缝偏",
                                step=0.1, lo=-0.5, hi=0.5),
    "back_crease_e": MetaEntry("后裤中线偏置", "裤中线",
                               "大=后烫迹线向内侧缝偏",
                               step=0.1, lo=-0.5, hi=0.5),
    # 小腿 / 膝 / 脚口
    "knee_adjust": MetaEntry("膝围调节量", "小腿", "大=膝围外放",
                             step=0.25, lo=0.0, hi=2.0),
    "calf_arc_alpha": MetaEntry("前小腿弧弓高", "小腿", "小腿段弧弓高系数",
                                step=0.01, lo=0.08, hi=0.12),
    "back_calf_arc_alpha": MetaEntry("后小腿弧弓高", "小腿",
                                     "同上（后片独立）",
                                     step=0.01, lo=0.08, hi=0.12),
    "hem_adjust": MetaEntry("脚口调节量", "脚口", "大=脚口外放",
                            step=0.25, lo=0.0, hi=2.0),
    "front_hem_arc_sag": MetaEntry("前脚口弧", "脚口",
                                   "0=直线，大=向下凸",
                                   step=0.2, lo=0.0, hi=1.5),
    "back_hem_arc_sag": MetaEntry("后脚口弧", "脚口",
                                  "同上（前后独立）",
                                  step=0.2, lo=0.0, hi=1.5),
    # 前口袋 / 袋口
    "front_pocket": MetaEntry("前口袋开关", "袋口", "斜插袋主切口"),
    "front_pocket_p1_dist": MetaEntry("袋口腰头端位置", "袋口",
                                      "P1 自侧缝腰点沿腰口朝前中量取的弧长"
                                      "（大=袋口上角靠前中）",
                                      step=1.0, lo=4.0, hi=15.0,
                                      gate="front_pocket"),
    "front_pocket_p2_drop": MetaEntry("袋口深浅", "袋口",
                                      "P2 沿侧缝下落深度（大=袋口深）",
                                      step=1.0, lo=2.0, hi=15.0,
                                      gate="front_pocket"),
    "front_pocket_dart_width": MetaEntry("袋口吃省宽", "袋口",
                                         "袋口腰头端吃省量",
                                         step=0.25, lo=0.0, hi=1.5,
                                         gate="front_pocket"),
    "front_pocket_paring_n": MetaEntry("袋口撇削强度", "袋口",
                                       "袋口边撇削衰减（大=撇得急）",
                                       step=0.25, lo=1.0, hi=3.0,
                                       gate="front_pocket"),
    "front_pocket_mouth_mode": MetaEntry("袋口形态", "袋口",
                                         "bulge 弯月弧 / tangent 两端垂直式（P1 端切线⊥腰弧、"
                                         "P2 端切线⊥外缝弧）/ polyline 折角式（P1→折角K→P2）",
                                         levels=("bulge", "tangent", "polyline"),
                                         gate="front_pocket"),
    "front_pocket_mouth_bulge": MetaEntry("袋口弧线弧高", "袋口",
                                          "经「袋口弧深」档位单通道调整",
                                          locked=True),   # 弧深单通道，防双通道漂移
    "front_pocket_mouth_bulge_at": MetaEntry("袋口弧顶位置", "袋口", "",
                                             locked=True),   # 几何细节
    "front_pocket_mouth_h1": MetaEntry("袋口切线柄长 1", "袋口", "",
                                       locked=True),   # 几何柄无感知语义
    "front_pocket_mouth_h2": MetaEntry("袋口切线柄长 2", "袋口", "",
                                       locked=True),
    "waist_rect_len": MetaEntry("直角修正段长", "腰头", "",
                                locked=True),   # 构造性直角修正段
    "rise_ratio": MetaEntry("直裆深比例", "全局", "",
                            locked=True),   # 腰位轴→rise_adjust 已覆盖，防双通道
    # 袋贴
    "front_pocket_facing": MetaEntry("袋贴开关", "袋贴", "袋口挖削贴布"),
    "front_pocket_facing_width": MetaEntry("袋贴宽", "袋贴",
                                           "袋贴腰头方向宽度",
                                           step=0.5, lo=1.0, hi=10.0,
                                           gate="front_pocket_facing"),
    "front_pocket_facing_side_w": MetaEntry("袋贴侧缝深度", "袋贴",
                                            "0=与腰头同宽；大=沿侧缝下探",
                                            step=0.5, lo=0.0, hi=15.0,
                                            gate="front_pocket_facing"),
    "front_pocket_facing_mode": MetaEntry(
        "袋贴内边形态", "袋贴",
        "tangent 两端垂直式（P_fw ⟂ 腰弧、P_fs ⟂ 外缝弧）"
        " / offset 传统等距偏置 / bulge 弧高式浅弧",
        levels=("tangent", "offset", "bulge"),
        gate="front_pocket_facing"),
    "front_pocket_facing_bulge": MetaEntry("袋贴内边弧凸量", "袋贴",
                                           "bulge 形态内边弧高"
                                           "（正值向裤身内侧凹入，"
                                           "从袋口看即弧线朝前中方向凸出）",
                                           gate={"param": "front_pocket_facing_mode",
                                                 "values": ["bulge"],
                                                 "requires": ["front_pocket_facing"]}),
    "front_pocket_facing_bulge_at": MetaEntry("袋贴内边弧顶位置", "袋贴",
                                              "大=弧顶靠侧缝端（版面左）、"
                                              "小=靠腰头端（版面右）",
                                              step=0.1, lo=0.3, hi=0.7,
                                              gate={"param": "front_pocket_facing_mode",
                                                    "values": ["bulge"],
                                                    "requires": ["front_pocket_facing"]}),
    "front_pocket_facing_h1": MetaEntry("袋贴切线柄长 1", "袋贴", "",
                                        locked=True),   # 几何柄
    "front_pocket_facing_h2": MetaEntry("袋贴切线柄长 2", "袋贴", "",
                                        locked=True),
    # 袋布
    "front_pouch": MetaEntry("袋布开关", "袋布", "前口袋袋布裁片"),
    "front_pouch_waist_safe": MetaEntry("袋布腰头安全量", "袋布",
                                        "腰缝锚点安全内延（沿腰弧自 P1 朝门襟）",
                                        gate="front_pouch"),
    "front_pouch_side_safe": MetaEntry("袋布侧缝垂深", "袋布",
                                       "侧缝锚点安全垂深（自 P2 沿侧缝下探）",
                                       gate="front_pouch"),
    # 小表袋
    "watch_pocket": MetaEntry("小表袋开关", "小表袋", "第五袋"),
    "watch_pocket_mode": MetaEntry("小表袋做法", "小表袋",
                                   "facing_intersect 袋贴相交 / custom 全自定义",
                                   levels=("custom", "facing_intersect"),
                                   gate="watch_pocket"),
    "watch_pocket_width": MetaEntry("小表袋宽", "小表袋", "袋口宽",
                                    step=0.5, lo=3.0, hi=10.0,
                                    gate="watch_pocket"),
    "watch_pocket_taper": MetaEntry("小表袋收窄", "小表袋",
                                    "两侧内收倾斜（0=垂直下落，大=袋底越窄）",
                                    gate="watch_pocket"),
    "watch_pocket_offset_from_top": MetaEntry("小表袋离顶部距离", "小表袋",
                                              "离口袋顶部的下移量",
                                              step=0.5, lo=1.0, hi=5.0,
                                              gate="watch_pocket"),
    "watch_pocket_offset_from_side": MetaEntry("小表袋离侧边距离", "小表袋",
                                               "离袋口侧边的内移量",
                                               step=0.5, lo=1.5, hi=6.0,
                                               gate="watch_pocket"),
    "watch_pocket_rotate_deg": MetaEntry("小表袋旋转角", "小表袋",
                                         "整体旋转（顺时针为正，绕参考点）",
                                         step=5.0, lo=-30.0, hi=30.0,
                                         gate="watch_pocket"),
    # 前贴袋
    "front_patch": MetaEntry("前贴袋开关", "前贴袋", "前片贴袋（罕见款）"),
    "front_patch_top_drop": MetaEntry("前贴袋下移量", "前贴袋",
                                      "袋口外上角自腰外缝顶点垂直向下"
                                      "（大=贴袋下移）",
                                      gate="front_patch"),
    "front_patch_top_inset": MetaEntry("前贴袋内移量", "前贴袋",
                                       "袋口外上角自侧缝水平向内"
                                       "（大=贴袋内移）",
                                       gate="front_patch"),
    "front_patch_width": MetaEntry("前贴袋宽", "前贴袋", "袋口宽",
                                   step=0.5, lo=8.0, hi=20.0,
                                   gate="front_patch"),
    "front_patch_height": MetaEntry("前贴袋高", "前贴袋", "袋身高",
                                    step=0.5, lo=8.0, hi=22.0,
                                    gate="front_patch"),
    "front_patch_shape": MetaEntry("前贴袋形状", "前贴袋",
                                   "rectangle 方底 / baker_shield 盾形尖底"
                                   " / angular 底角斜切 / custom 全自定义",
                                   levels=("rectangle", "baker_shield",
                                           "angular", "custom"),
                                   gate="front_patch"),
    "front_patch_bottom_width": MetaEntry("前贴袋袋底宽", "前贴袋",
                                          "0=与袋口同宽",
                                          gate="front_patch"),
    "front_patch_rotate_deg": MetaEntry("前贴袋旋转角", "前贴袋",
                                        "绕袋口外上角旋转（顺时针为正）",
                                        step=5.0, lo=-30.0, hi=30.0,
                                        gate="front_patch"),
    "front_patch_tip_depth": MetaEntry("前贴袋底尖深度", "前贴袋",
                                       "盾形底尖", gate="front_patch"),
    "front_patch_chamfer": MetaEntry("前贴袋底角斜切", "前贴袋",
                                     "底角斜切量（angular 形态）",
                                     gate="front_patch"),
    # 后贴袋
    "back_patch": MetaEntry("后贴袋开关", "后贴袋", "后片贴袋"),
    "back_patch_inset_x": MetaEntry("后贴袋距后浪距离", "后贴袋",
                                    "自后浪线沿约克底线朝侧缝量取"
                                    "（大=袋位靠侧缝）",
                                    step=0.5, lo=2.0, hi=8.0,
                                    gate="back_patch"),
    "back_patch_drop_y": MetaEntry("后贴袋距育克距离", "后贴袋",
                                   "离育克底线下移量",
                                   step=0.5, lo=1.0, hi=8.0,
                                   gate="back_patch"),
    "back_patch_width": MetaEntry("后袋宽", "后贴袋", "袋口宽",
                                  step=0.5, lo=8.0, hi=20.0,
                                  gate="back_patch"),
    "back_patch_height": MetaEntry("后袋高", "后贴袋", "袋身高",
                                   step=0.5, lo=8.0, hi=22.0,
                                   gate="back_patch"),
    "back_patch_shape": MetaEntry("后袋形状", "后贴袋",
                                  "rectangle 方底 / baker_shield 盾形尖底"
                                  " / angular 底角斜切 / custom 全自定义",
                                  levels=("rectangle", "baker_shield",
                                          "angular", "custom"),
                                  gate="back_patch"),
    "back_patch_bottom_width": MetaEntry("后袋袋底宽", "后贴袋",
                                         "0=与袋口同宽", gate="back_patch"),
    "back_patch_rotate_deg": MetaEntry("后贴袋旋转角", "后贴袋",
                                       "绕袋口近后浪侧顶点旋转（顺时针为正；"
                                       "0=平行约克底线）",
                                       step=5.0, lo=-30.0, hi=30.0,
                                       gate="back_patch"),
    "back_patch_tip_depth": MetaEntry("后袋底尖深度", "后贴袋", "盾形底尖",
                                      gate="back_patch"),
    "back_patch_chamfer": MetaEntry("后袋底角斜切", "后贴袋",
                                    "底角斜切量（angular 形态）",
                                    gate="back_patch"),
    "back_patch_top_hem_taper": MetaEntry("后袋袋口撇势", "后贴袋",
                                          "负值=袋口向内收",
                                          step=0.05, lo=-0.4, hi=0.0,
                                          gate="back_patch"),
    "back_patch_notch_type": MetaEntry("后袋刀口类型", "后贴袋", "V / I",
                                       levels=("V", "I"), gate="back_patch"),
    "back_patch_notch_depth": MetaEntry("后袋刀口深度", "后贴袋",
                                        "对位刀口深度",
                                        gate="back_patch"),
    # 后育克（机头）
    "back_yoke": MetaEntry("后机头开关", "后育克", "后片腰下分割线"),
    "back_yoke_cb_dist": MetaEntry("机头后浪深度", "后育克",
                                   "后中向下深度", step=0.5, lo=2.0, hi=7.0,
                                   gate="back_yoke"),
    "back_yoke_side_dist": MetaEntry("机头侧缝深度", "后育克",
                                     "侧缝端向下深度",
                                     step=0.5, lo=2.0, hi=6.0,
                                     gate="back_yoke"),
    "back_yoke_side_corner_mirror": MetaEntry("机头侧缝角镜像折角", "后育克",
                                              "裁片拼合角处理开关",
                                              gate="back_yoke"),
    "back_yoke_cb_corner_mirror": MetaEntry("机头后浪角镜像折角", "后育克",
                                            "裁片拼合角处理开关",
                                            gate="back_yoke"),
    # 门襟
    "fly": MetaEntry("门襟开关", "门襟", "门襟绘制（连裁门襟上版于前片）"),
    "fly_width": MetaEntry("门襟宽", "门襟", "门襟条宽度",
                           step=0.25, lo=3.0, hi=4.5, gate="fly"),
    "fly_length_ratio": MetaEntry("门襟开深系数", "门襟",
                                  "大=门襟开得深",
                                  step=0.05, lo=0.2, hi=0.5, gate="fly"),
    "fly_length_base": MetaEntry("门襟开深基值", "门襟",
                                 "开深基值（开深 = 系数×前浪 + 本值）",
                                 gate="fly"),
    "fly_turnback": MetaEntry("门襟退层补偿", "门襟",
                              "腰口顶端内收的牛仔布折转退层补偿",
                              gate="fly"),
    "fly_corner_inset": MetaEntry("门襟底角圆角内收", "门襟",
                                  "大=底角越尖", gate="fly"),
    "fly_corner_turn": MetaEntry("门襟拐点弧位", "门襟",
                                 "1.0=J 底；小=拐点上移", gate="fly"),
    "fly_stitch_inset": MetaEntry("门襟明线内距", "门襟",
                                  "J 字明线内收（顺外边向内等距偏置）",
                                  gate="fly"),
    "fly_separate": MetaEntry("独立门襟开关", "门襟",
                              "开=门襟独立裁片；关=与前片连裁"),
    "fly_sep_extra": MetaEntry("独立门襟外放", "门襟",
                               "独立裁片底部延展量（裁片高 = 开深 + 本值）",
                               gate="fly_separate"),
    "fly_sep_double": MetaEntry("门襟形态二选一", "门襟",
                                "开=只出双排（对折）片；关=只出单排（单层）片",
                                gate="fly_separate"),
    # 裤耳
    "belt_loop": MetaEntry("裤耳开关", "裤耳", "腰头袢带"),
    "belt_loop_width": MetaEntry("裤耳宽", "裤耳", "成品净宽（净裁无缝份）",
                                 step=0.1, lo=0.8, hi=1.8, gate="belt_loop"),
    "belt_loop_unit_length": MetaEntry("裤耳单根长", "裤耳", "单根成品长",
                                       step=0.5, lo=4.0, hi=8.0,
                                       gate="belt_loop"),
    "belt_loop_count": MetaEntry("裤耳根数", "裤耳", "总根数（通常 5 根）",
                                 step=1.0, lo=3, hi=8, gate="belt_loop"),
    "belt_loop_waste": MetaEntry("裤耳连裁损耗", "裤耳",
                                 "裁剪与车缝损耗（加在连裁总长末尾）",
                                 gate="belt_loop"),
    # 前后片裁片
    "front_piece_crotch_corner": MetaEntry("前片裆尖角镜像折角", "前片裁片",
                                           "开=镜像折角；关=切线 miter 尖角"),
    "front_piece_notch_type": MetaEntry("前片刀口类型", "前片裁片", "V / I",
                                        levels=("V", "I")),
    "back_piece_crotch_corner": MetaEntry("后片裆尖角镜像折角", "后片裁片",
                                          "开=镜像折角；关=纯尖角"),
    "back_piece_notch_type": MetaEntry("后片刀口类型", "后片裁片", "V / I",
                                       levels=("V", "I")),
    # 缩水（工艺量；整版净样不随动、裁片毛样随动）
    "shrinkage_enabled": MetaEntry("缩水总开关", "缩水",
                                   "关=全部裁片不缩水"),
    "shrinkage_warp": MetaEntry("经向缩水率", "缩水", "0.03=3%",
                                step=0.01, lo=0.0, hi=0.15),
    "shrinkage_weft": MetaEntry("纬向缩水率", "缩水", "0.03=3%",
                                step=0.01, lo=0.0, hi=0.15),
    "front_pouch_shrinkage_warp": MetaEntry("袋布里料经向缩水率", "缩水",
                                            "默认 0（里料隔离大身）"),
    "front_pouch_shrinkage_weft": MetaEntry("袋布里料纬向缩水率", "缩水",
                                            "默认 0（里料隔离大身）"),
    "watch_pocket_shrinkage_warp": MetaEntry("小表袋里料经向缩水率", "缩水",
                                             "默认 0（里料隔离大身）"),
    "watch_pocket_shrinkage_weft": MetaEntry("小表袋里料纬向缩水率", "缩水",
                                             "默认 0（里料隔离大身）"),
}


# -- 表面机械（自省 + validator 探测 + 枚举值域；模块级一次算好缓存） ----------

def scalar_field_names() -> set[str]:
    """PatternOptions 标量字段名（漂移金标的比对基准：默认值可直接构造的
    bool/int/float/str/枚举字段；factory 默认 = 嵌套缝份对象恒在 EXCLUDED 侧）。"""
    out: set[str] = set()
    for f in dataclasses.fields(PatternOptions):
        if f.default is dataclasses.MISSING:
            continue
        if isinstance(f.default, (bool, int, float, str, Enum)):
            out.add(f.name)
    return out


def _default_value(key: str):
    for f in dataclasses.fields(PatternOptions):
        if f.name == key:
            v = f.default
            return v.value if isinstance(v, Enum) else v
    return None


def _valid_value(key: str, value: float) -> bool:
    """validator 探测：单键覆写默认构造（真守卫仍是管线 validate/probe）。"""
    try:
        PatternOptions.from_dict({key: value})
        return True
    except (TypeError, ValueError):
        return False


def _walk_to_valid(key: str, cand: float, good: float) -> float:
    """cand 非法时向 good 二分夹出合法边界（8 轮，咨询精度足够）。"""
    if _valid_value(key, cand):
        return cand
    bad = cand
    for _ in range(8):
        mid = (bad + good) / 2.0
        if _valid_value(key, mid):
            good = mid
        else:
            bad = mid
    return good


def _nice(x: float) -> float:
    """1 位有效数字的「好看」数（步长定标用；下限 0.01）。"""
    x = abs(float(x)) or 0.01
    m = 10.0 ** math.floor(math.log10(x))
    return max(0.01, round(x / m) * m)


def _numeric_bounds(key: str, default: float, m: MetaEntry
                    ) -> tuple[float, float, float]:
    """数值键 (lo, hi, step)：精定标优先；缺省 default±nice(|d|/2) 咨询带
    经 validator 探测夹界，步长 nice((hi−lo)/5)。"""
    if m.lo is not None and m.hi is not None:
        lo, hi = m.lo, m.hi
    else:
        span = _nice(abs(default) / 2.0) if default else 0.5
        lo = m.lo if m.lo is not None else _walk_to_valid(
            key, default - span, default)
        hi = m.hi if m.hi is not None else _walk_to_valid(
            key, default + span, default)
    step = m.step if m.step is not None else _nice((hi - lo) / 5.0)
    return lo, hi, step


def _enum_domains() -> dict[str, tuple]:
    """枚举值域合集：webschema._ENUMS ∪ schema.MODEL_KEYS（同源只读）。"""
    out: dict[str, tuple] = {}
    from ylpattern.webschema import _ENUMS
    for k, vals in _ENUMS.items():
        out[k] = tuple(vals)
    from .schema import MODEL_KEYS
    for k, dom in MODEL_KEYS.items():
        if isinstance(dom, tuple) and k not in out:
            out[k] = tuple(dom)
    return out


def _hint_channel_keys() -> set[str]:
    """merge 的 hint 消费面（枚举默认键 + 部件惯例开关）——走 seed_hints
    的键集合；mouth_depth 是 S2 伪轴不算引擎键。"""
    from .prejudge import prior_switches
    from .schema import ENUM_DEFAULTS
    return ({k for k in ENUM_DEFAULTS if k != "front_pocket_mouth_depth"}
            | set(prior_switches()))


def _virtual_specs() -> tuple[AdjustKeySpec, ...]:
    """虚键：非引擎键、映射为绝对值落在 target（bulge 弧深单通道）。"""
    from .families import _MOUTH_BULGE
    levels = ("shallow", "standard", "deep")
    return (AdjustKeySpec(
        key="front_pocket_mouth_depth", label="袋口弧深",
        semantics="袋口弯月弧线的深浅（浅/标准/深，映射为弧高绝对值）",
        group="袋口", channel="override", levels=levels, ordinal=True,
        step=0.0, lo=0.0, hi=0.0, default="standard",
        gate={"param": "front_pocket_mouth_mode", "values": ["bulge"],
              "requires": ["front_pocket"]},
        locked=False, target="front_pocket_mouth_bulge",
        level_values=tuple(_MOUTH_BULGE[k] for k in levels)),)


_SURFACE: dict[str, AdjustKeySpec] | None = None
_DEFAULT_VIEW: dict | None = None


def adjust_surface() -> dict[str, AdjustKeySpec]:
    """映射面终态：META 生成 + 虚键（模块级缓存一次算好）。"""
    global _SURFACE
    if _SURFACE is not None:
        return _SURFACE
    hints = _hint_channel_keys()
    domains = _enum_domains()
    out: dict[str, AdjustKeySpec] = {}
    for key, m in META.items():
        default = _default_value(key)
        if isinstance(default, bool):
            levels = m.levels or ("on", "off")
            lo = hi = step = 0.0
        elif isinstance(default, str):
            levels = m.levels or domains.get(key, ())
            lo = hi = step = 0.0
        else:
            levels = m.levels
            lo, hi, step = _numeric_bounds(key, float(default), m)
            if m.levels:                       # int 档位键（省数）
                lo = hi = step = 0.0
        out[key] = AdjustKeySpec(
            key=key, label=m.label, semantics=m.semantics or m.label,
            group=m.group, channel="hint" if key in hints else "override",
            levels=tuple(levels), ordinal=m.ordinal, step=step, lo=lo, hi=hi,
            default=default, gate=m.gate, locked=m.locked)
    for spec in _virtual_specs():
        out[spec.key] = spec
    _SURFACE = out
    return out


def default_view() -> dict:
    """映射面默认值视图（回退后/覆盖面外键的 gate 与当前值兜底源）。"""
    global _DEFAULT_VIEW
    if _DEFAULT_VIEW is None:
        _DEFAULT_VIEW = {k: s.default for k, s in adjust_surface().items()
                         if not s.target}
    return _DEFAULT_VIEW
