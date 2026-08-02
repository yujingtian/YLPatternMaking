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
    back_rise=44,    # 后浪
    outseam=102,     # 裤长
    thigh=62,        # 大腿围

    # ---- 版型选项 ----
    delta=1.5,       # 前后片臀围调节量（女装标准 1.0 / 男装 0.5~0.75）
    rise_ratio=0.25, # 直裆深系数（直裆深 = 臀围 × 系数 + 调整量）
    rise_adjust=4.0, # 直裆深调整量（cm，加深取正、改浅取负）
    waistband_type="straight",  # 腰头类型："straight" 直腰头 / "curved" 弯腰头
    waistband_width=4.0,        # 腰头宽（直腰头从裤长中扣除；弯腰头忽略）
    side_rise=1.0,              # 侧缝腰头抬高量（0 = 腰围外缝顶点压基础线，常取 0~1.5）
    waist_balance=1.5,          # 前后片腰围调节量（前片减、后片加；平分取 0）
    front_waist_dart=3.0,       # 前片省量/褶量（标准牛仔裤 0；西裤 1.5~3.0）
    front_crease_e=0.0,         # 前片裤中线调节量（常规 0；修身 -0.5~-0.8）
    knee_adjust=2.5,            # 膝围前后片调整量（前片膝围宽 = 膝围/2 − 本值；高弹 0.5~0.75）
    hem_adjust=2.5,             # 脚口前后片调整量（前片脚口宽 = 裤口/2 − 本值）

    # ---- 弧线参数（前片弧线推导.md）----
    calf_arc_alpha=0.0,   # 小腿段弧弓高系数（0.08~0.12；0 = 直筒直线）
    inseam_arc_k1=0.50,    # 内缝大腿段：小裆弯度（0.15~0.25，越大越早往膝口收）
    inseam_arc_ky=0.18,    # 内缝大腿段：弯曲纵向位置（越大弯曲点越靠下）
    inseam_arc_k2=0.35,    # 内缝大腿段：膝口切线柄长系数（越大膝口衔接越顺直）
    outseam_arc_dx=0.15,   # 外缝大腿段：大转子外凸量（0.1~0.2；顺直 0）
    outseam_arc_m2=0.40,   # 外缝大腿段：膝口切线柄长系数
    hem_arc_sag=0.0,       # 脚口弧高（0 = 直线；正值向上凹，常取 0.3~0.8）

    # ---- 输出 ----
    svg="out/sheet.svg",
    # until="draw_hip_line",      # 取消注释可只画到臀围线
    # trace="out/trace.txt",      # 取消注释输出逐步绘制记录
)
