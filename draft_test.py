# -*- coding: utf-8 -*-
"""打版测试脚本：改下面的参数，直接运行本文件即可生成 SVG。

    python draft_test.py
"""

from ylpattern import run

run(
    # ---- 核心尺寸（cm）----
    waist=74,        # 腰围（成品）
    hip=100,          # 臀围 = 净臀围 + 放松量
    knee=54,         # 膝围
    hem=47,          # 裤口
    front_rise=30,   # 前浪
    back_rise=40,    # 后浪
    outseam=102,     # 裤长
    thigh=63.5,        # 大腿围

    # ---- 版型选项 ----
    delta=1.5,       # 前后片臀围调节量（女装标准 1.0 / 男装 0.5~0.75）
    front_crotch_adjust=-0.4,  # 前小裆修正量（紧身牛仔裤取 -0.5 ~ -1.0）
    back_crotch_adjust=0.0,   # 后大裆修正量（坐姿伸展加深取正，常规 0）
    front_intake_adjust=0.0,  # 前中内收修正量（高腰取正、低腰取负）
    back_intake=2.5,          # 后中内收比例模数 X（实际内收 = 实际臀腰高 × X/15；
                              #   宽松 1.5~2.0 / 标准 2.5~3.0 / 紧身提臀 3.5~4.5）
    back_rise_alpha=0.40,     # 后浪大裆弯上控制柄系数（0.38~0.42）
    back_rise_beta=0.50,      # 后浪大裆弯下控制柄系数（0.48~0.55；紧身提臀取 0.55）
    rise_ratio=0.25, # 直裆深系数（直裆深 = 臀围 × 系数 + 调整量）
    rise_adjust=4.0, # 直裆深调整量（cm，加深取正、改浅取负）
    crotch_drop_adjust=0.0,   # 后片落裆调节量 Δc（落裆量 = H/100 + Δc；
                              #   高弹 -0.4~-0.3 / 标准直筒 0 / 宽松重磅 +0.2~+0.3）
    waistband_type="curved",  # 腰头类型："straight" 直腰头 / "curved" 弯腰头
    waistband_width=4.0,        # 腰头宽（直腰头从裤长中扣除；弯腰头忽略）
    side_rise=1.0,              # 侧缝腰头抬高量（0 = 腰围外缝顶点压基础线，常取 0~1.5）
    front_waist_curve_sag=0.4,  # 前片腰围线弧额外下凹量（贴合腰腹取 0.3~0.5）
    back_waist_curve_sag=0.4,   # 后片腰头线弧额外下凹量（贴合腰背背弓取 0.3~0.5）
                                #   （0 = 无额外下凹，但 90° 正交平顺段的弯曲仍在，非直线）
    waist_balance=1.5,          # 前后片腰围调节量（前片减、后片加；平分取 0）
    front_waist_dart=3.0,       # 前片省量/褶量（标准牛仔裤 0；西裤 1.5~3.0）
    back_waist_dart=3.0,        # 后片省量/约克转移量（后腰长 = W/4 + balance + 本值；
                                #   约克步骤前 0；Yoke 转移 2.5~4.0；后腰长容位，
                                #   与绘制的腰省相互独立）
    back_dart=True,             # 后片腰省开关（可选步骤，打版流程.md 后片步骤 9；
                                #   只画省，不动腰头）
    back_dart_count=1,          # 后片省数（1 = 腰头两等分取中点；2 = 三等分取两个中点）
    back_dart_width=[2.0],      # 每个省的省量列表（个数 = 省数，顺序同省中点：后中 → 侧缝；
                                #   写单个值则各省共用；省量为 0 的省不绘制）
    back_dart_length=10.0,      # 省中线长（默认 11cm）

    # ---- 后机头/育克（可选步骤，打版流程.md「后机头/育克绘制」）----
    #   弯腰头自下腰头顶点、直腰头自腰头线顶点沿后浪线/外缝线向下量取两端点；
    #   机头吸收后省（back_waist_dart 已含约克转移量），可视需要关 back_dart 看净机头。
    back_yoke=True,              # 机头绘制开关（只上版分割下口线，先画后裁）
    back_yoke_cb_dist=6.0,       # P0 后浪端点：自腰头内缝顶点沿后浪线向下弧长 D_cb（cm）
    back_yoke_side_dist=3.5,     # PN 侧缝端点：自腰头外缝顶点沿外缝线向下弧长 D_side（cm；
                                  #   D_cb − D_side = 倾斜落差，后中更深）
    back_yoke_mid_anchors=[],
                                  # 下口中间锚点 (u, depth)：u=弦上比例 0~1（递增）、
                                  #   depth=下凸深度（cm，正值向下凸、0=压弦、负值上凸）；
                                  #   空 [] = 直线下口（打版流程.md：无控制点即直线）
                                  #   例：[(0.5, 1.5)] 中间下凸成微笑线
    back_yoke_edges=[],
                                  # 下口逐段形态（个数 = 锚点数+1）：
                                  #   ("line",) / ("arc", 弧高, 弧顶分位) / ("bezier", α°, κ1, β°, κ2)
                                  #   空 [] = 全段直线（自动；加锚点时可不填 edges 即全直线）

    front_crease_e=0.0,         # 前片裤中线调节量（常规 0；修身 -0.5~-0.8）
    back_crease_e=0.0,          # 后片裤中线调节量（常规与前片一致；特体独立设定）
    knee_adjust=2.5,            # 膝围前后片调整量（前片膝围宽 = 膝围/2 − 本值；高弹 0.5~0.75）
    hem_adjust=2.5,             # 脚口前后片调整量（前片脚口宽 = 裤口/2 − 本值）

    # ---- 弧线参数（前片弧线推导.md）----
    calf_arc_alpha=0.0,   # 小腿段弧弓高系数（0.08~0.12；0 = 直筒直线）
    inseam_arc_k1=0.50,    # 内缝大腿段：小裆弯度（0.15~0.25，越大越早往膝口收）
    inseam_arc_ky=0.18,    # 内缝大腿段：弯曲纵向位置（越大弯曲点越靠下）
    inseam_arc_k2=0.35,    # 内缝大腿段：膝口切线柄长系数（越大膝口衔接越顺直）
    outseam_arc_dx=0.4,   # 外缝大腿段：大转子外凸量（0.1~0.2；顺直 0）
    outseam_arc_m2=0.35,   # 外缝大腿段：膝口切线柄长系数

    # ---- 后片弧线参数（后片弧线推导.md）----
    back_calf_arc_alpha=0.10,  # 后小腿段：弧弓高系数（0.08~0.12；0 = 直筒直线）
    back_inseam_arc_k1=0.30,   # 后内缝大腿段：大裆弯度（0.25~0.35，大于前片留运动空间）
    back_inseam_arc_ky=0.10,   # 后内缝大腿段：弯曲纵向位置
    back_inseam_arc_k2=0.35,   # 后内缝大腿段：膝口切线柄长系数
    back_outseam_arc_dx=0.15,  # 后外缝大腿段：臀侧饱满度（0.1~0.25；顺直 0）
    back_outseam_arc_m2=0.40,  # 后外缝大腿段：膝口切线柄长系数
    # 髋腰段（臀围外缝点 → 腰头外缝点）四个参数，两两一对：
    #   靠臀围这头用 dx1 + k1 调；靠腰头这头用 dx2 + k2 调。
    #   dx 管"横向凸出多少"（都是 0 = 不凸，越大越往外鼓）；
    #   k 管"纵向走势"：k1 越大凸感延续得越高、越晚拐弯；k2 越大越早往腰头收。
    back_hipwaist_arc_dx1=0.3,  # 臀侧凸出多少：0 = 顺直不凸，越大越往外鼓（0~0.3）
    back_hipwaist_arc_k1=0.3,   # 臀侧凸感延续多高：越大凸得越高、越晚往腰头弯（推荐 0.35~0.45）
    back_hipwaist_arc_dx2=0.3,   # 腰头角点凸出多少：0 = 竖直顺直进角，越大角点越往外鼓（0~0.3）
    back_hipwaist_arc_k2=0,   # 多早往腰头收：越大上段越早内缩、末端笔直进角（推荐 0.2~0.3；0 = 自由弯进角点）
    front_hem_arc_sag=0.0, # 前片脚口弧高（0 = 直线；正值向下凸，常取 0.3~0.8）
    back_hem_arc_sag=0.0,  # 后片脚口弧高（口径同前片，前后片独立录入）

    # ---- 前口袋（挖削嵌入式主切口，可选步骤，前口袋绘制.md §二、§三）----
    front_pocket=True,              # 主切口绘制开关（先画后裁，不做布尔裁除）
    front_pocket_p1_dist=10,       # P1：腰弧上自腰外缝顶点朝前浪顶点的弧长距离（cm）
    front_pocket_p2_drop=8,       # P2：外缝弧上自腰外缝顶点向下的弧长深度（cm）
    front_pocket_dart_width=1.5,    # 腰头吃省总宽（cm，常规 1.5~2.5；共线渐变撇削，
                                    #   腰头端最大、向侧缝端衰减至 0；0 = 不吃省）
    front_pocket_paring_n=1.5,      # 撇削衰减幂指数（常规 1.5~2.0）
    front_pocket_mouth_bulge=0,   # 袋口母线弧高（bulge 模式；正值向裤片内侧凹入加深勺口；0 = 直口）
    front_pocket_mouth_bulge_at=0.5,  # 袋口弧顶位置（bulge 模式；弦长比例 0~1；中点 0.5，
                                      #   最低点偏侧缝端取 0.6~0.7）
    front_pocket_mouth_mode="tangent",  # 袋口净线模式："bulge" 弧高式 / "tangent" 两端垂直式
                                      #   / "polyline" 折角式（带倒角折线）
    front_pocket_mouth_h1=8.0,    # 腰头端切线柄长（tangent 模式，P1 端切线 ⟂ 腰弧切线）
    front_pocket_mouth_h2=3.0,    # 侧缝端切线柄长（tangent 模式，P2 端切线 ⟂ 外缝弧切线）
    front_pocket_mouth_corners=[(0.3, 2), (0.6, 3)],
                                  # 折角列表（polyline 模式；每角 = (弦上位置, 内推深度cm)，
                                  #   按位置严格递增，可多个；空列表 = 直袋口）

    # ---- 袋布（嵌入式口袋储物袋布大片/小片，可选步骤，袋布绘制.md §二、§三、§五）----
    front_pouch=True,               # 袋布绘制开关（依赖 front_pocket 主切口）
    front_pouch_waist_safe=4.0,     # 腰缝锚点安全内延（沿腰弧自 P1 朝门襟，cm，3.5~5.0）
    front_pouch_side_safe=10,      # 侧缝锚点安全垂深（自 P2 沿侧缝下探，cm，6.0~10.0）
    front_pouch_nodes=[(12, 24.0), (6, 24.0)],
                                  # 自定义内部节点（≥2；相对腰外缝顶点，x 朝门襟、y 向下）
    front_pouch_edges=[("line",), ("line",), ("arc", 0.5, 0.6)],
                                  # 边形态（个数 = 节点数+1）：("line",) /
                                  #   ("arc", 弧高, 弧顶分位) / ("bezier", α°, κ1, β°, κ2)

    # ---- 小表袋（嵌于挖削嵌入式前口袋内的小贴袋，可选步骤，小表袋绘制.md §2~§4）----
    watch_pocket=True,                  # 小表袋开关（依赖 front_pocket 挖削嵌入式；
                                        #   打版流程.md：当前口袋是挖削嵌入式时才绘制）
    watch_pocket_offset_from_top=3.0,   # 离口袋顶部距离：自前口袋侧缝腰点垂直向下（cm，§2.3）
    watch_pocket_offset_from_side=2.5,  # 离口袋侧边距离：自侧缝水平向内（cm，§2.3）
    watch_pocket_rotate_deg=8.0,        # 整体绕参考点旋转角（度，顺时针为正，§2.3/§3.2）
    watch_pocket_points=[(0, 0), (5, 0), (5, 8), (0, 8)],
                                        # 净形锚点（相对参考点 dx/dy，≥3，顺时针；
                                        #   默认梯形：袋口宽 8、底宽 7.2、高 7.5）
    watch_pocket_edges=[("line",), ("line",), ("line",), ("line",)],
                                        # 边形态（个数 = 锚点数，闭合边）：("line",) /
                                        #   ("arc", 弧高, 弧顶分位) / ("bezier", α°, κ1, β°, κ2)

    # ---- 前贴袋（表面外贴式 PATCH，可选步骤，前口袋绘制.md §四）----
    front_patch=False,              # 贴袋绘制开关（前片不裁切，独立样板）
    front_patch_top_drop=1,      # 袋口外上角自腰外缝顶点垂直向下（cm）
    front_patch_top_inset=1.0,      # 袋口外上角自侧缝水平向内（cm）
    front_patch_width=10.0,         # 袋口宽（cm）
    front_patch_height=12.0,        # 袋身高（cm）
    front_patch_shape="custom",  # 净形：rectangle 方底 / baker_shield 盾形尖底
                                    #   / angular 底角斜切 / custom 全自定义
    front_patch_bottom_width=0.0,   # 袋底宽（baker_shield/angular；0 = 与袋口同宽，
                                    #   底边两侧对称内收）
    front_patch_rotate_deg=8.0,     # 贴袋整体绕袋口外上角旋转角（度，顺时针为正）
    front_patch_tip_depth=2,      # 盾形底尖额外深度（baker_shield，cm）
    front_patch_chamfer=1,        # 底角斜切量（angular，cm）
    front_patch_custom_points=[(0, 0), (10, 0), (10, -10), (0, -10)],
                                  # custom 净形角点（相对袋口外上角的 dx/dy，≥3，顺时针）
    front_patch_custom_edges=[(0, 0.5), (0, 0.5), (0, 0.5), (0, 0.5)],
                                  # custom 每边形态：(弧高, 弧顶位置)；弧高 0 = 直线，
                                  #   个数 = 角点数；示例为右边一段弧

    # ---- 后贴袋（表面外贴式 PATCH，可选步骤，后贴袋绘制.md §一~§三）----
    #   依赖后机头育克底线定位（须先开 back_yoke）；净样上版即表面定位标记，先画后裁。
    back_patch=True,                  # 后贴袋绘制开关（独立样板，后大片不裁切）
    back_patch_inset_x=4,           # 距后浪线的距离：沿约克底线朝侧缝（cm，§一.2；常规 4~5.5）
    back_patch_drop_y=2.5,            # 距约克底线的距离：向下（cm，§一.2；常规 3~4.5）
    back_patch_width=14.0,            # 袋口宽（cm）
    back_patch_height=12.0,           # 袋身高（cm）
    back_patch_shape="custom",        # 净形：rectangle 方底 / baker_shield 盾形尖底
                                      #   / angular 底角斜切 / custom 全自定义
    back_patch_bottom_width=12,      # 袋底宽（baker_shield/angular；0 = 与袋口同宽）
    back_patch_rotate_deg=3.5,        # 整体绕袋口近后浪侧顶点旋转角（度，顺时针为正；
                                      #   默认 0 = 平行约克底线≈后腰线）
    back_patch_tip_depth=2.5,         # 盾形底尖额外深度（baker_shield，cm）
    back_patch_chamfer=2.0,           # 底角斜切量（angular，cm）
    back_patch_custom_points=[(0, 0), (14, 0), (13.5, 15), (7, 17), (0.5, 15)],
                                      # custom 净形角点（局部 u-v：u 朝侧缝 +、v 向下 +，
                                      #   相对袋口近后浪侧顶点，顺时针）；默认盾形：
                                      #   袋口宽 14、底宽 12、高 15、底尖加深 2
    back_patch_custom_edges=[(0, 0.5), (0, 0.5), (-0.2, 0.5), (-0.2, 0.5), (0, 0.5)],
                                      # custom 每边形态：(弧高, 弧顶位置)；弧高 0 = 直线，
                                      #   个数 = 角点数；示例底两段微弧

    # ---- 门襟（可选步骤，门襟绘制.md §2.2~§5）----
    #   两种互斥形态：连裁门襟（fly=True，凸向前片外侧、与前片相连）/
    #   独立门襟（fly_separate=True，叠在前片上、之后分离成单独裁片；优先于 fly）
    # —— 公用参数（连裁 + 独立都生效）——
    fly_width=4,             # [公用] 门襟宽 W（连裁外线宽 / 独立裁片净宽；YKK 5# 3.5~4.2）
    fly_length_ratio=0.35,     # [公用] 开深系数（开深 L = 系数 × 前浪 + 基值，§2.2）
    fly_length_base=2.0,       # [公用] 开深基值（cm，§2.2）
    # —— 连裁门襟专用（仅 fly=True 时生效；独立门襟不读这些）——
    fly=True,                  # [连裁开关] 弯腰头原点取下前中腰点 A'，直腰头取前浪顶点 A
    fly_turnback=0,         # [连裁] 牛仔布折转退层补偿 Δw（腰口顶端内收，§3.1）
    fly_corner_inset=0.5,   # [公用] 底角圆角内收（连裁+独立共用；R = W−本值 = 4−0.1 = 3.9，须 0<本值<W，§3.2/§5）
    fly_corner_turn=0.5,     # [连裁] 拐点弧位（90° 角弧比例；1.0=J 底（默认）；越小拐点越靠上、角弧越短，§3.2）
    fly_blend_drop=5,     # [连裁] 融合点 P2 较 L 下移量（cm；None=自动取 W−R 且不小于防波浪最小值；
                             #   手动录入须≥拐点所需最小值，否则抛错，§3.2.3）
    fly_stitch_inset=0.6,      # [连裁] J 字明线内收（明线 = 顺外边向内等距偏置本值的虚线，§4.2）
                               #   （拉链止口刀口、打枣点等工艺细节暂不绘制，留待工艺/裁切模块）
    # —— 独立门襟专用（仅 fly_separate=True 时生效；连裁门襟不读这些）——
    fly_separate=True,        # [独立开关] 叠在前片上、之后分离成单独裁片；裁片取净宽 W
                              #   （缝边/缩水留待之后的裁切模块，先画后裁）
    fly_sep_extra=0.0,         # [独立] 底部延展量（裁片高 = L + 本值，§5）

    # ---- 排版 ----
    piece_gap=10.0,        # 前后片排版间距（后片整体置于前片右侧，分开不重叠）

    # ---- 毗围限制（可选步骤，打版流程.md 后片步骤 8）----
    thigh_limit=True,        # 毗围闭环修正开关（按 前后片毗围推导.md §三 整版重跑至收敛）
    thigh_measure_offset=0.0,  # 实测下移量 d（0 = 立裆深线直量；常规实测 2.54）
    # —— 闭环控制参数（推导.md §三，默认值即文档规范值，可按需覆盖）——
    thigh_piece_split_max=0.2,    # 片间分配分界：|ΔW| ≤ 本值平分，否则大差量比
    thigh_front_share=0.2,       # 大差量前片分配比（红线：严禁 50:50）
    thigh_dual_track_min=0.3,     # 双轨分流阈值：|ΔW| ≤ 本值单动侧缝，否则内外联动
    thigh_front_crotch_coef=0.09, # 前小裆尖调拨系数（ΔX前 = 系数×ΔW）
    thigh_back_crotch_coef=0.21,  # 后大裆尖调拨系数（ΔX后 = 系数×ΔW）
    thigh_front_crotch_max=0.4,   # 前小裆累计调整上限（防卡耻骨，极值红线）
    thigh_back_crotch_max=1.0,    # 后大裆累计调整上限（防下蹲崩破，极值红线）
    thigh_max_iter=6,             # 闭环最大迭代轮数（侧缝被钳后仅靠裆宽收敛慢，可加大）
    thigh_tol=0.2,               # 闭环收敛容差（|ΔW| ≤ 本值即收敛）

    # ---- 输出 ----
    svg="out/sheet.svg",
    # until="draw_hip_line",      # 取消注释可只画到臀围线
    # trace="out/trace.txt",      # 取消注释输出逐步绘制记录
)
