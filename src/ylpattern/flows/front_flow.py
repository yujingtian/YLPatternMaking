"""前片流程：声明式步骤列表。

阶段 1（M1）：建立基础参考线与"大矩形"框架 —— 打版流程.md 前片步骤 1。
阶段 2：裆部结构 —— 打版流程.md 前片步骤 2（前小裆宽、前中内收点）。
阶段 3：前浪弧线 —— 打版流程.md 前片步骤 2（前浪绘制.md）。
阶段 4：真实腰围线 —— 打版流程.md 前片步骤 3（腰头绘制推导.md）。
阶段 5：裤中线 —— 打版流程.md 前片步骤 4（前后片裤中线推导.md）。
阶段 6：膝围、脚口宽度 —— 打版流程.md 前片步骤 5（脚口膝围外缝点推导.md）。
阶段 7：外缝、内缝线 —— 打版流程.md 前片步骤 6（前片弧线推导.md）。
阶段 8：前口袋（可选步骤）—— 打版流程.md「前口袋打版过程」（前口袋绘制.md §二、§三）。
阶段 9：袋布（可选步骤，依赖前口袋）—— 打版流程.md「袋布打版过程」（袋布绘制.md §二、§三、§五）。
阶段 10：门襟（可选步骤，连裁门襟上版于前片）—— 门襟绘制.md §2.1~§4。
"""

from ..steps import front_steps as fs
from ..steps import front_pocket_steps as fps
from ..steps import front_pouch_steps as fph
from ..steps import front_fly_steps as ff

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
    fs.draw_front_lower_waistband,   # 弯腰头下腰缝线（可选：直腰头跳过）
    # —— 阶段 5：裤中线 ——
    fs.draw_front_crease_line,
    # —— 阶段 6：膝围、脚口宽度 ——
    fs.draw_front_knee_hem_widths,
    # —— 阶段 7：外缝、内缝线 ——
    fs.draw_front_outseam_curves,
    fs.draw_front_inseam_curves,
    # —— 阶段 8：前口袋（可选步骤，开关开启才绘制；先画后裁，不动其他元素） ——
    fps.draw_front_pocket,
    fps.draw_front_patch_pocket,
    # —— 阶段 9：袋布（可选步骤，依赖前口袋主切口） ——
    fph.draw_front_pouch,
    # —— 阶段 10：门襟（可选步骤，连裁门襟上版于前片） ——
    ff.draw_front_fly,
]
