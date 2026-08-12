"""顶层便捷 API：录入参数，直接生成 SVG。

用法：

    from ylpattern import run

    run(waist=70, hip=96, knee=46, hem=36,
        front_rise=25, back_rise=33, outseam=102, thigh=58,
        svg="out/sheet.svg")
"""

from __future__ import annotations

from .draft import DraftContext
from .exporters import svg as svg_exp
from .flows.closure import run_with_thigh_closure
from .params import (Measurements, PatternOptions, WaistbandGrain, WaistbandType,
                     WaistbandSeamAllowances)


def _coerce_sa(v) -> WaistbandSeamAllowances:
    """dict -> WaistbandSeamAllowances（已是其类型则原样返回）。"""
    if isinstance(v, WaistbandSeamAllowances):
        return v
    if isinstance(v, dict):
        return WaistbandSeamAllowances.from_dict(v)
    raise TypeError("waistband_seam_allowances 须为 dict 或 WaistbandSeamAllowances")


def run(*, waist: float, hip: float, knee: float, hem: float,
        front_rise: float, back_rise: float, outseam: float, thigh: float = 0.0,
        delta: float = 1.0, front_crotch_adjust: float = 0.0,
        back_crotch_adjust: float = 0.0,
        front_intake_adjust: float = 0.0,
        back_intake: float = 2.5,
        back_rise_alpha: float = 0.40, back_rise_beta: float = 0.50,
        front_rise_handle_ratio: float = 1 / 3,
        rise_ratio: float = 0.25, rise_adjust: float = 0.0,
        crotch_drop_adjust: float = 0.0,
        waistband_type: WaistbandType | str = WaistbandType.STRAIGHT,
        waistband_width: float = 4.0,
        waistband_front_drop: float = 1.5,
        waistband_fly_extension: float = 3.5,
        waistband_full_piece: bool = True,
        waistband_grain: WaistbandGrain | str = WaistbandGrain.WIDTH,
        shrinkage_warp: float = 0.0,
        shrinkage_weft: float = 0.0,
        waistband_seam_allowances: dict | object | None = None,
        side_rise: float = 0.0,
        front_waist_curve_sag: float = 0.3, back_waist_curve_sag: float = 0.3,
        waist_balance: float = 0.0, front_waist_dart: float = 0.0,
        back_waist_dart: float = 0.0,
        back_dart: bool = False, back_dart_count: int = 1,
        back_dart_width: float | list[float] | tuple[float, ...] = 2.0,
        back_dart_length: float = 11.0,
        back_yoke: bool = False,
        back_yoke_cb_dist: float = 4.0,
        back_yoke_side_dist: float = 3.0,
        back_yoke_mid_anchors: list | tuple = (),
        back_yoke_edges: list | tuple = (),
        front_crease_e: float = 0.0, back_crease_e: float = 0.0,
        knee_adjust: float = 1.0, hem_adjust: float = 1.0,
        calf_arc_alpha: float = 0.10,
        inseam_arc_k1: float = 0.20, inseam_arc_ky: float = 0.28,
        inseam_arc_k2: float = 0.35,
        outseam_arc_dx: float = 0.15, outseam_arc_m2: float = 0.40,
        back_calf_arc_alpha: float = 0.10,
        back_inseam_arc_k1: float = 0.30, back_inseam_arc_ky: float = 0.30,
        back_inseam_arc_k2: float = 0.35,
        back_outseam_arc_dx: float = 0.15, back_outseam_arc_m2: float = 0.40,
        back_hipwaist_arc_dx1: float = 0.15, back_hipwaist_arc_k1: float = 0.40,
        back_hipwaist_arc_dx2: float = 0.0, back_hipwaist_arc_k2: float = 0.25,
        front_hem_arc_sag: float = 0.0, back_hem_arc_sag: float = 0.0,
        front_pocket: bool = False,
        front_pocket_p1_dist: float = 8.5,
        front_pocket_p2_drop: float = 7.5,
        front_pocket_dart_width: float = 2.0,
        front_pocket_paring_n: float = 2.0,
        front_pocket_mouth_bulge: float = 0.5,
        front_pocket_mouth_bulge_at: float = 0.5,
        front_pocket_mouth_mode: str = "bulge",
        front_pocket_mouth_h1: float = 3.0,
        front_pocket_mouth_h2: float = 3.0,
        front_pocket_mouth_corners: list | tuple = ((0.55, 1.5),),
        front_pocket_facing: bool = False,
        front_pocket_facing_width: float = 3.5,
        front_patch: bool = False,
        front_patch_top_drop: float = 10.0,
        front_patch_top_inset: float = 2.0,
        front_patch_width: float = 14.0,
        front_patch_height: float = 15.0,
        front_patch_shape: str = "rectangle",
        front_patch_bottom_width: float = 0.0,
        front_patch_rotate_deg: float = 0.0,
        front_patch_tip_depth: float = 2.5,
        front_patch_chamfer: float = 2.0,
        front_patch_custom_points: list | tuple = (),
        front_patch_custom_edges: list | tuple = (),
        back_patch: bool = False,
        back_patch_inset_x: float = 4.5,
        back_patch_drop_y: float = 3.5,
        back_patch_width: float = 14.0,
        back_patch_height: float = 16.0,
        back_patch_shape: str = "rectangle",
        back_patch_bottom_width: float = 0.0,
        back_patch_rotate_deg: float = 0.0,
        back_patch_tip_depth: float = 2.5,
        back_patch_chamfer: float = 2.0,
        back_patch_custom_points: list | tuple = (),
        back_patch_custom_edges: list | tuple = (),
        front_pouch: bool = False,
        front_pouch_waist_safe: float = 4.0,
        front_pouch_side_safe: float = 8.0,
        front_pouch_nodes: list | tuple = ((5.0, 16.0), (1.5, 13.5)),
        front_pouch_edges: list | tuple = (("line",), ("arc", 2.5, 0.6), ("line",)),
        watch_pocket: bool = False,
        watch_pocket_offset_from_top: float = 4.0,
        watch_pocket_offset_from_side: float = 3.5,
        watch_pocket_rotate_deg: float = 0.0,
        watch_pocket_points: list | tuple = ((0.0, 0.0), (8.0, 0.0), (7.6, 7.5), (0.4, 7.5)),
        watch_pocket_edges: list | tuple = (("line",), ("line",), ("line",), ("line",)),
        fly: bool = False,
        fly_width: float = 3.8,
        fly_length_ratio: float = 0.35,
        fly_length_base: float = 2.0,
        fly_turnback: float = 0.25,
        fly_corner_inset: float = 0.8,
        fly_corner_turn: float = 1.0,
        fly_blend_drop: float | None = None,
        fly_stitch_inset: float = 0.6,
        fly_separate: bool = False,
        fly_sep_extra: float = 2.0,
        thigh_limit: bool = False, thigh_measure_offset: float = 0.0,
        thigh_piece_split_max: float = 0.2, thigh_front_share: float = 0.2,
        thigh_dual_track_min: float = 0.3,
        thigh_front_crotch_coef: float = 0.09,
        thigh_back_crotch_coef: float = 0.21,
        thigh_front_crotch_max: float = 0.4,
        thigh_back_crotch_max: float = 1.0,
        thigh_max_iter: int = 6, thigh_tol: float = 0.3,
        piece_gap: float = 10.0,
        seam_allowance: float = 1.0,
        svg: str = "out/sheet.svg",
        waistband_svg: str | None = None,
        until: str | None = None,
        trace: str | None = None,
        report: str | None = None) -> DraftContext:
    """录入尺寸参数，执行整版绘制流程（前片 + 后片）并生成 SVG。

    参数：
        waist ~ outseam  七项核心尺寸（cm），含义见 examples/size_female_165.toml
        thigh            大腿围（可选；0 = 未录入，毗围限制自动跳过，
                         打版流程.md 后片步骤 8）
        delta            前后片臀围单侧调节量 Δ（推导文档 §四）
        front_crotch_adjust 前小裆修正量（紧身款 -0.5~-1.0）
        back_crotch_adjust  后大裆修正量（坐姿伸展加深取正，常规 0）
        front_intake_adjust  前中内收修正量（内收量 = (H−W)/4 × 系数 + 本值；高腰取正、低腰取负）
        back_intake      后中内收比例模数 X（实际内收 = 臀腰高×X/15；宽松 1.5~2、标准 2.5~3、紧身 3.5~4.5）
        back_rise_alpha 后浪大裆弯上控制柄系数 α（0.38~0.42，后浪绘制.md §3.1）
        back_rise_beta  后浪大裆弯下控制柄系数 β（0.48~0.55，紧身提臀 0.55，§3.1）
        front_rise_handle_ratio 前浪裆弯控制柄比例（k1=k2=|BC|×本值；默认 1/3，前浪绘制.md §4）
        rise_ratio       直裆深系数（直裆深 = H × ratio + adjust，默认 H/4）
        rise_adjust      直裆深修正量（cm）
        crotch_drop_adjust 后片落裆调节量 Δc（落裆量 = H/100 + Δc；高弹取负、宽松取正）
        waistband_type   腰头类型："straight" 直腰头 / "curved" 弯腰头（打版流程.md 注意点 1）
        waistband_width  腰头宽（cm）；直腰头打版时从裤长中扣除，弯腰头忽略
        waistband_front_drop  弯腰头弧深量（cm，正数=下口线向下凹 ∪；控制下口线弯曲度，腰头裁片.md §四）
        waistband_fly_extension  门襟搭门量（cm，左片前中端外延，§三.3）
        waistband_full_piece  True=整条腰头（后中折线对称）；False=沿后中分两片（本期实现 True）
        waistband_grain  腰头经向方向（§五.2）："width" 宽向=经（默认，横裁，=裤长方向）/ "length" 长向=经（直裁）
        shrinkage_warp / shrinkage_weft  面料经/纬向缩水率（0.03=3%）；映射到腰头 X/Y 轴
                          由 waistband_grain 决定；裁片先缩水再加缝边，缝份不叠加缩水，§五
        waistband_seam_allowances  四边独立缝份 dict {top,bottom,left_end,right_end}
                          （cm；后中折线不外扩；§二.3/§五.3）
        side_rise        侧缝腰头抬高量 h（0 = 腰围外缝顶点压基础线，常取 0~1.5）
        front_waist_curve_sag  前片腰围线弧额外下凹量（贴合腰腹取 0.3~0.5；
                               0 = 无额外下凹，90° 正交平顺段的弯曲仍在）
        back_waist_curve_sag   后片腰头线弧额外下凹量（贴合腰背背弓取 0.3~0.5，同上）
        waist_balance    前后片腰围调节量（前减后加；平分 0，常取 1.0~1.5）
        front_waist_dart 前片省量/褶量 V前省（标准牛仔裤 0；西裤 1.5~3.0）
        back_waist_dart 后片省量/约克转移量 V后省（约克步骤前 0；Yoke 2.5~4.0；
                        后腰长容位，与绘制的腰省相互独立）
        back_dart        后片腰省绘制开关（可选步骤，打版流程.md 后片步骤 9；
                         只画省，不动腰头）
        back_dart_count  后片省数（1 = 腰头两等分取中点；2 = 三等分取两个中点）
        back_dart_width  每个省的省量（默认 2cm；列表逐省控制，顺序同省中点：
                         后中 → 侧缝，个数须等于省数；写单个值则各省共用；
                         省量为 0 的省不绘制）
        back_dart_length 省中线长（默认 11cm）
        back_yoke        后机头/育克绘制开关（可选步骤，打版流程.md「后机头/育克绘制」；
                         只上版分割下口线，先画后裁，不做布尔裁除）
        back_yoke_cb_dist / back_yoke_side_dist
                         机头下口两端点：自腰头内缝/外缝顶点沿后浪线/外缝线向下量取的
                         弧长 D_cb / D_side（cm，后机头绘制.md §1；弯腰头改自下腰头顶点
                         量取、链上再下移腰头宽 W）
        back_yoke_mid_anchors
                         下口线中间控制锚点列表，每个 = (u, depth)：u = P0->PN 弦上
                         位置比例 0~1（严格递增）、depth = 偏离弦深度（cm，正值向下凸
                         入裤身、0 = 压弦、负值上凸）；空 = 直线下口
                         （打版流程.md：无锚点即直线）
        back_yoke_edges  下口线逐段形态（个数 = 锚点数 + 1）：("line",) 直线 /
                         ("arc", 弧高, 弧顶分位) 弧高式 /
                         ("bezier", α°, κ1, β°, κ2) 双手柄贝塞尔（与袋布/小表袋同口径）；
                         空 = 全段直线（自动，打版流程.md：无控制点即直线）
        front_crease_e   前片裤中线调节量 e（常规 0；修身 -0.5~-0.8，裤中线推导.md §五）
        back_crease_e    后片裤中线调节量 e（常规与 front_crease_e 一致；
                         偏平臀/特大臀峰/提臀造型时独立设定，§五）
        knee_adjust      膝围前后片调整量 δ（前减后加，前片膝围宽 = K/2 − δ；高弹 0.5~0.75）
        hem_adjust       脚口前后片调整量 δ（前减后加，前片脚口宽 = B/2 − δ）
        calf_arc_alpha   小腿段弧弓高系数 α（0.08~0.12；0 = 直筒直线，前片弧线推导.md §三）
        inseam_arc_k1    内缝大腿段小裆弯度 k1（0.15~0.25，越大越早往膝口收，§四）
        inseam_arc_ky    内缝大腿段纵向系数 ky（越大弯曲点越靠下，§四）
        inseam_arc_k2    内缝大腿段膝口切线柄长系数（k2 = 本值×ΔY，§四）
        outseam_arc_dx   外缝大腿段大转子外凸 δx（0.1~0.2；顺直 0，§五）
        outseam_arc_m2   外缝大腿段膝口切线柄长系数（m2 = 本值×ΔY，§五）
        back_calf_arc_alpha  后片小腿段弧弓高系数 α（0.08~0.12，后片弧线推导.md §二）
        back_inseam_arc_k1   后内缝大腿段大裆弯度 k1（0.25~0.35，大于前片留运动空间，§三）
        back_inseam_arc_ky   后内缝大腿段纵向系数 ky（§三）
        back_inseam_arc_k2   后内缝大腿段膝口切线柄长系数（k2 = 本值×ΔY，§三）
        back_outseam_arc_dx  后外缝大腿段臀侧饱满度 δx（0.1~0.25；顺直 0，§四）
        back_outseam_arc_m2  后外缝大腿段膝口切线柄长系数（m2 = 本值×ΔY，§四）
        back_hipwaist_arc_dx1  臀侧凸出多少（0~0.3；0 = 顺直不凸，越大越往外鼓，§五）
        back_hipwaist_arc_k1   臀侧凸感延续多高（0.35~0.45；越大越晚往腰头弯，§五）
        back_hipwaist_arc_dx2  腰头角点凸出多少（0~0.3；0 = 竖直顺直进角，越大角点越鼓，§五）
        back_hipwaist_arc_k2   多早往腰头收（0.20~0.30；越大上段越早内缩、末端笔直进角，§五）
        front_hem_arc_sag  前片脚口弧高（0 = 直线；正值向下凸出裤片，常取 0.3~0.8）
        back_hem_arc_sag   后片脚口弧高（口径同前片，前后片独立录入）
        front_pocket       前口袋（挖削嵌入式主切口）绘制开关（可选步骤，
                           打版流程.md「前口袋打版过程」；先画后裁，不做布尔裁除）
        front_pocket_p1_dist   P1 锚点：腰弧上自腰外缝顶点朝前浪顶点的弧长距离（cm）
        front_pocket_p2_drop   P2 锚点：外缝弧上自腰外缝顶点向下的弧长深度（cm）
        front_pocket_dart_width  腰头吃省总宽 ΔW（cm，前口袋绘制.md §三.1，常规 1.5~2.5；
                           共线渐变撇削：省顶点 P1′ = P1 沿腰弧朝前浪顶点量取 ΔW（落在腰头线上），
                           切削线 = 设计净线 + (P1′−P1)·(1−t)ⁿ，侧缝端衰减至 0；0 = 不吃省）
        front_pocket_paring_n  撇削衰减幂指数 n（常规 1.5~2.0；越大吃量越集中在腰头端）
        front_pocket_mouth_bulge  袋口母线弧高（bulge 模式；正值向裤片内侧凹入加深勺口；0 = 直口）
        front_pocket_mouth_bulge_at  袋口弧顶位置（bulge 模式；弦长比例 0~1，默认中点 0.5；
                           袋口最低点偏侧缝端取 0.6~0.7）
        front_pocket_mouth_mode  袋口净线模式："bulge" 弧高式 / "tangent" 两端垂直式 /
                           "polyline" 折角式（带倒角折线：P1 → 折角 K → P2）
        front_pocket_mouth_h1 / front_pocket_mouth_h2
                           腰头端 / 侧缝端切线柄长（tangent 模式，cm，默认 3.0）
        front_pocket_mouth_corners  折角列表（polyline 模式；每个折角 = (弦上位置 0~1,
                           内推深度 cm)，按位置严格递增，可多个；空列表 = 直袋口）
        front_pocket_facing  前口袋袋贴（facing）绘制开关（可选步骤，前口袋绘制.md §三.3.(1)；
                           依赖 front_pocket 主切口；袋贴宽 = 腰头端量取距离 = 侧缝端下落
                           距离 = 内边法向偏置间距，三者等距；先画后裁，不做布尔裁除）
        front_pocket_facing_width  袋贴宽 w_facing（cm，即距离 A；常规 3.0~4.0，默认 3.5）
        front_patch        前贴袋（表面外贴式 PATCH）绘制开关（前口袋绘制.md §四；
                           前片不裁切，独立样板，净样即表面定位标记）
        front_patch_top_drop / front_patch_top_inset
                           袋口外上角定位：自腰外缝顶点垂直向下 / 水平向内（cm）
        front_patch_width / front_patch_height  袋口宽 / 袋身高（cm）
        front_patch_shape  净形："rectangle" 方底 / "baker_shield" 盾形尖底 /
                           "angular" 底角斜切 / "custom" 全自定义
        front_patch_bottom_width  袋底宽（baker_shield/angular，cm；0 = 与袋口同宽，
                           底边两侧对称内收）
        front_patch_rotate_deg  贴袋整体绕袋口外上角旋转角（度，顺时针为正）
        front_patch_tip_depth  盾形底尖额外深度（baker_shield，cm）
        front_patch_chamfer  底角斜切量（angular，cm）
        front_patch_custom_points  custom 净形角点列表（相对袋口外上角的
                           dx/dy，≥3 个，顺时针绕行）
        front_patch_custom_edges  custom 每边形态：(弧高, 弧顶位置 0~1)，
                           弧高 0 = 直线；个数 = 角点数
        back_patch        后贴袋（表面外贴式 PATCH）绘制开关（后贴袋绘制.md §一~§三；
                          依赖后机头育克底线定位，须先开 back_yoke；净样即表面定位标记）
        back_patch_inset_x / back_patch_drop_y
                          袋口近后浪侧顶点定位：距后浪线（沿约克底线朝侧缝）/ 距约克底线
                          （向下）量取（cm，§一.2；常规 4.0~5.5 / 3.0~4.5）
        back_patch_width / back_patch_height  袋口宽 / 袋身高（cm，§二.1）
        back_patch_shape  净形："rectangle" 方底 / "baker_shield" 盾形尖底 /
                          "angular" 底角斜切 / "custom" 全自定义（§二.1 形态路由）
        back_patch_bottom_width  袋底宽（baker_shield/angular，cm；0 = 与袋口同宽，
                          底边两侧对称内收）
        back_patch_rotate_deg  贴袋整体绕袋口近后浪侧顶点旋转角（度，顺时针为正，§二.2；
                          默认 0 = 平行约克底线≈后腰线）
        back_patch_tip_depth  盾形底尖额外深度（baker_shield，cm，§二.1）
        back_patch_chamfer  底角斜切量（angular，cm，§二.1）
        back_patch_custom_points  custom 净形角点列表（局部 u-v：u 朝侧缝 +、v 向下 +，
                          相对袋口近后浪侧顶点，≥3 个，顺时针）
        back_patch_custom_edges  custom 每边形态：(弧高, 弧顶位置 0~1)，
                          弧高 0 = 直线；个数 = 角点数
        front_pouch        袋布绘制开关（袋布绘制.md §一~§五；依赖 front_pocket 主切口）
        front_pouch_waist_safe  腰缝锚点安全内延（沿腰弧自 P1 朝门襟，cm，推荐 3.5~5.0）
        front_pouch_side_safe  侧缝锚点安全垂深（自 P2 沿侧缝下探，cm，推荐 6.0~10.0）
        front_pouch_nodes  自定义内部节点列表（≥2 个；相对腰外缝顶点，x 朝门襟、
                           y 向下为正）
        front_pouch_edges  边形态列表（个数 = 节点数 + 1）：("line",) 直线 /
                           ("arc", 弧高, 弧顶分位 0.1~0.9) /
                           ("bezier", α°, κ1, β°, κ2) 双手柄贝塞尔
        watch_pocket      小表袋绘制开关（打版流程.md「小表袋绘制」；依赖 front_pocket
                          挖削嵌入式；以前口袋侧缝腰点为基准定位，净样锚点 + 逐边形态）
        watch_pocket_offset_from_top / watch_pocket_offset_from_side
                          离口袋顶部（垂直向下）/ 离口袋侧边（水平向内）距离（cm，
                          小表袋绘制.md §2.3）
        watch_pocket_rotate_deg  整体绕参考点旋转角（度，顺时针为正，§2.3/§3.2）
        watch_pocket_points  净形锚点（相对参考点 dx/dy，≥3 个，顺时针；默认梯形）
        watch_pocket_edges  边形态列表（个数 = 锚点数，闭合边）：("line",) /
                          ("arc", 弧高, 弧顶分位) / ("bezier", α°, κ1, β°, κ2)
        fly              门襟（连裁门襟）绘制开关（可选步骤，门襟绘制.md §3、§4；
                           上版于前片，弯腰头时原点取下前中腰点 A'）
        fly_width        门襟宽 W（常规 YKK 5# 拉链 3.8，3.5~4.2）
        fly_length_ratio / fly_length_base
                           开深 L = ratio × 前浪 + base（§2.2，默认 0.35/2.0）
        fly_turnback     牛仔布折转退层补偿 Δw（腰口顶端内收，§3.1，默认 0.25）
        fly_corner_inset 底角圆角内收量（连裁 + 独立共用；角弧半径 R = W − 本值，
                           默认 0.8 -> R=3.0；越大角越紧，须 0<本值<W，§3.2/§5）
        fly_corner_turn  拐点 P_turn 在 J 型角弧上的弧位（90° 角弧比例；1.0 = J 底
                         （默认，角弧终点）；越小拐点越靠上、角弧越短、融合弧越长，§3.2）
        fly_blend_drop  融合点 P2 较开深 L 的下移量（cm，§3.2.3；None = 自动取 W−R
                        且不小于拐点所需防波浪最小值；手动过浅则抛错）
        fly_stitch_inset J 字明线内收（明线 = 顺外边向内等距偏置本值，§4.2 简化，
                           默认 0.6；剪口刀口、打枣点等工艺细节暂不绘制）
        fly_separate     独立门襟开关（§5；开启后左前片不连裁，单独生成矩形
                           门襟裁片。fly / fly_separate 任一开启即绘制，
                           fly_separate 优先，互斥形态）
        fly_sep_extra    底部延展量（裁片高 = L + 本值，§5，默认 2.0）
        thigh_limit        毗围闭环修正开关（可选步骤，打版流程.md 后片步骤 8；
                           开启后按 前后片毗围推导.md §三 双轨分流整版重跑至收敛）
        thigh_measure_offset  毗围实测下移量 d（0 = 立裆深线直量；常规实测 2.54）
        thigh_piece_split_max  片间分配分界（|ΔW| ≤ 本值平分，否则大差量比，§三.1）
        thigh_front_share  大差量前片分配比（后片 = 1 − 本值；红线严禁 50:50，§三.1）
        thigh_dual_track_min  双轨分流阈值（|ΔW| ≤ 本值单动侧缝，否则内外联动，§三.2）
        thigh_front_crotch_coef / thigh_back_crotch_coef
                           前/后裆尖调拨系数（ΔX = 系数×ΔW，默认 0.09 / 0.21，§三.2）
        thigh_front_crotch_max / thigh_back_crotch_max
                           前/后裆尖累计调整上限（防卡耻骨 0.4 / 防下蹲崩破 1.0，§三.2）
        thigh_max_iter / thigh_tol  闭环最大迭代轮数（默认 6）/ 收敛容差（默认 0.3）
        piece_gap        前后片排版间距（后片整体置于前片右侧，分开不重叠）
        svg              SVG 输出路径
        waistband_svg    腰头裁片独立 SVG 输出路径（None=不输出；需完整整版，
                         中断调版 until 时不生成；腰头裁片.md §五 独立裁片）
        until            执行到指定步骤（含）停止，用于看中间状态
        trace / report   可选：同时输出追踪记录 / 尺寸报表到指定路径

    返回：
        DraftContext —— 可继续从 ctx.sheet 取元素做自定义处理。
    """
    m = Measurements(waist=waist, hip=hip, knee=knee, hem=hem,
                     front_rise=front_rise, back_rise=back_rise,
                     outseam=outseam, thigh=thigh)
    o = PatternOptions(delta=delta,
                       front_crotch_adjust=front_crotch_adjust,
                       back_crotch_adjust=back_crotch_adjust,
                       front_intake_adjust=front_intake_adjust,
                       back_intake=back_intake,
                       back_rise_alpha=back_rise_alpha,
                       back_rise_beta=back_rise_beta,
                       front_rise_handle_ratio=front_rise_handle_ratio,
                       rise_ratio=rise_ratio,
                       rise_adjust=rise_adjust,
                       crotch_drop_adjust=crotch_drop_adjust,
                       waistband_type=WaistbandType(waistband_type),
                       waistband_width=waistband_width,
                       waistband_front_drop=waistband_front_drop,
                       waistband_fly_extension=waistband_fly_extension,
                       waistband_full_piece=waistband_full_piece,
                       waistband_grain=WaistbandGrain(waistband_grain),
                       shrinkage_warp=shrinkage_warp,
                       shrinkage_weft=shrinkage_weft,
                       **({"waistband_seam_allowances":
                           _coerce_sa(waistband_seam_allowances)}
                          if waistband_seam_allowances is not None else {}),
                       side_rise=side_rise,
                       front_waist_curve_sag=front_waist_curve_sag,
                       back_waist_curve_sag=back_waist_curve_sag,
                       waist_balance=waist_balance,
                       front_waist_dart=front_waist_dart,
                       back_waist_dart=back_waist_dart,
                       back_dart=back_dart,
                       back_dart_count=back_dart_count,
                       back_dart_width=back_dart_width,
                       back_dart_length=back_dart_length,
                       back_yoke=back_yoke,
                       back_yoke_cb_dist=back_yoke_cb_dist,
                       back_yoke_side_dist=back_yoke_side_dist,
                       back_yoke_mid_anchors=back_yoke_mid_anchors,
                       back_yoke_edges=back_yoke_edges,
                       front_crease_e=front_crease_e,
                       back_crease_e=back_crease_e,
                       knee_adjust=knee_adjust,
                       hem_adjust=hem_adjust,
                       calf_arc_alpha=calf_arc_alpha,
                       inseam_arc_k1=inseam_arc_k1,
                       inseam_arc_ky=inseam_arc_ky,
                       inseam_arc_k2=inseam_arc_k2,
                       outseam_arc_dx=outseam_arc_dx,
                       outseam_arc_m2=outseam_arc_m2,
                       back_calf_arc_alpha=back_calf_arc_alpha,
                       back_inseam_arc_k1=back_inseam_arc_k1,
                       back_inseam_arc_ky=back_inseam_arc_ky,
                       back_inseam_arc_k2=back_inseam_arc_k2,
                       back_outseam_arc_dx=back_outseam_arc_dx,
                       back_outseam_arc_m2=back_outseam_arc_m2,
                       back_hipwaist_arc_dx1=back_hipwaist_arc_dx1,
                       back_hipwaist_arc_k1=back_hipwaist_arc_k1,
                       back_hipwaist_arc_dx2=back_hipwaist_arc_dx2,
                       back_hipwaist_arc_k2=back_hipwaist_arc_k2,
                       front_hem_arc_sag=front_hem_arc_sag,
                       back_hem_arc_sag=back_hem_arc_sag,
                       front_pocket=front_pocket,
                       front_pocket_p1_dist=front_pocket_p1_dist,
                       front_pocket_p2_drop=front_pocket_p2_drop,
                       front_pocket_dart_width=front_pocket_dart_width,
                       front_pocket_paring_n=front_pocket_paring_n,
                       front_pocket_mouth_bulge=front_pocket_mouth_bulge,
                       front_pocket_mouth_bulge_at=front_pocket_mouth_bulge_at,
                       front_pocket_mouth_mode=front_pocket_mouth_mode,
                       front_pocket_mouth_h1=front_pocket_mouth_h1,
                       front_pocket_mouth_h2=front_pocket_mouth_h2,
                       front_pocket_mouth_corners=front_pocket_mouth_corners,
                       front_pocket_facing=front_pocket_facing,
                       front_pocket_facing_width=front_pocket_facing_width,
                       front_patch=front_patch,
                       front_patch_top_drop=front_patch_top_drop,
                       front_patch_top_inset=front_patch_top_inset,
                       front_patch_width=front_patch_width,
                       front_patch_height=front_patch_height,
                       front_patch_shape=front_patch_shape,
                       front_patch_bottom_width=front_patch_bottom_width,
                       front_patch_rotate_deg=front_patch_rotate_deg,
                       front_patch_tip_depth=front_patch_tip_depth,
                       front_patch_chamfer=front_patch_chamfer,
                       front_patch_custom_points=front_patch_custom_points,
                       front_patch_custom_edges=front_patch_custom_edges,
                       back_patch=back_patch,
                       back_patch_inset_x=back_patch_inset_x,
                       back_patch_drop_y=back_patch_drop_y,
                       back_patch_width=back_patch_width,
                       back_patch_height=back_patch_height,
                       back_patch_shape=back_patch_shape,
                       back_patch_bottom_width=back_patch_bottom_width,
                       back_patch_rotate_deg=back_patch_rotate_deg,
                       back_patch_tip_depth=back_patch_tip_depth,
                       back_patch_chamfer=back_patch_chamfer,
                       back_patch_custom_points=back_patch_custom_points,
                       back_patch_custom_edges=back_patch_custom_edges,
                       front_pouch=front_pouch,
                       front_pouch_waist_safe=front_pouch_waist_safe,
                       front_pouch_side_safe=front_pouch_side_safe,
                       front_pouch_nodes=front_pouch_nodes,
                       front_pouch_edges=front_pouch_edges,
                       watch_pocket=watch_pocket,
                       watch_pocket_offset_from_top=watch_pocket_offset_from_top,
                       watch_pocket_offset_from_side=watch_pocket_offset_from_side,
                       watch_pocket_rotate_deg=watch_pocket_rotate_deg,
                       watch_pocket_points=watch_pocket_points,
                       watch_pocket_edges=watch_pocket_edges,
                       fly=fly,
                       fly_width=fly_width,
                       fly_length_ratio=fly_length_ratio,
                       fly_length_base=fly_length_base,
                       fly_turnback=fly_turnback,
                       fly_corner_inset=fly_corner_inset,
                       fly_corner_turn=fly_corner_turn,
                       fly_blend_drop=fly_blend_drop,
                       fly_stitch_inset=fly_stitch_inset,
                       fly_separate=fly_separate,
                       fly_sep_extra=fly_sep_extra,
                       thigh_limit=thigh_limit,
                       thigh_measure_offset=thigh_measure_offset,
                       thigh_piece_split_max=thigh_piece_split_max,
                       thigh_front_share=thigh_front_share,
                       thigh_dual_track_min=thigh_dual_track_min,
                       thigh_front_crotch_coef=thigh_front_crotch_coef,
                       thigh_back_crotch_coef=thigh_back_crotch_coef,
                       thigh_front_crotch_max=thigh_front_crotch_max,
                       thigh_back_crotch_max=thigh_back_crotch_max,
                       thigh_max_iter=thigh_max_iter, thigh_tol=thigh_tol,
                       piece_gap=piece_gap,
                       seam_allowance=seam_allowance)

    ctx, trace_text = run_with_thigh_closure(m, o, until=until,
                                             trace=bool(trace))

    if until:
        # 中断调版时不出腰头裁片（需完整整版提取腰弧净长）
        pass
    elif waistband_svg:
        from .flows.waistband_flow import build_waistband
        from .exporters import piece_svg as piece_exp
        piece, _wb_ctx = build_waistband(ctx)
        piece_exp.write_piece_svg(piece, waistband_svg)
        print(f"腰头裁片 SVG 已输出:{waistband_svg}")

    svg_exp.write_sheet_svg(ctx.sheet, svg)
    print(f"SVG 已输出:{svg}")

    if trace:
        with open(trace, "w", encoding="utf-8") as fp:
            fp.write(trace_text)
        print(f"追踪记录已输出:{trace}")
    if report:
        from .exporters import report as report_exp
        with open(report, "w", encoding="utf-8") as fp:
            fp.write(report_exp.render_report(ctx.sheet, m, ctx.options,
                                              trace_text))
        print(f"报表已输出:{report}")
    return ctx
