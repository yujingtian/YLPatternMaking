"""前片流程：声明式步骤列表。

阶段 1（M1）：建立基础参考线与"大矩形"框架 —— 打版流程.md 前片步骤 1。
阶段 2：裆部结构 —— 打版流程.md 前片步骤 2（前小裆宽、前中内收点）。
阶段 3：前浪弧线 —— 打版流程.md 前片步骤 2（前浪绘制.md）。
阶段 4：真实腰围线 —— 打版流程.md 前片步骤 3（腰头绘制推导.md）。
阶段 5：裤中线 —— 打版流程.md 前片步骤 4（前后片裤中线推导.md）。
阶段 6：膝围、脚口宽度 —— 打版流程.md 前片步骤 5（脚口膝围外缝点推导.md）。
后续阶段随打版文档补全逐步扩充：侧缝/内缝。
"""

from ..steps import front_steps as fs

FRONT_FLOW = [
    # —— 阶段 1：五条水平参考线 + 大矩形框架 ——
    fs.draw_hem_line,
    fs.draw_crotch_line,
    fs.draw_hip_line,
    fs.draw_knee_line,
    fs.draw_waist_line,
    fs.draw_outseam_refline,
    fs.draw_front_hip_width,
    fs.draw_inner_seam_refline,
    # —— 阶段 2：裆部结构 ——
    fs.draw_front_crotch_width,
    fs.draw_front_center_intake,
    # —— 阶段 3：前浪弧线 ——
    fs.draw_front_rise,
    # —— 阶段 4：真实腰围线 ——
    fs.draw_front_waistline,
    fs.draw_front_waist_outseam_curves,
    # —— 阶段 5：裤中线 ——
    fs.draw_front_crease_line,
    # —— 阶段 6：膝围、脚口宽度 ——
    fs.draw_front_knee_hem_widths,
]
