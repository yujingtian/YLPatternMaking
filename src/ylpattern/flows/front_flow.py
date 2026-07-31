"""前片流程：声明式步骤列表。

阶段 1（M1）：建立基础参考线与"大矩形"框架 —— 打版流程.md 前片步骤 1。
后续阶段随打版文档补全逐步扩充：裆部结构 → 腰/侧缝/内缝/脚口。
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
]
