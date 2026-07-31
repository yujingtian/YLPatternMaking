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

    # ---- 输出 ----
    svg="out/sheet.svg",
    # until="draw_hip_line",      # 取消注释可只画到臀围线
    # trace="out/trace.txt",      # 取消注释输出逐步绘制记录
)
