"""后片流程：声明式步骤列表。

阶段 1：建立基础参考线与"大矩形"框架 —— 打版流程.md 后片步骤 1。

后片与前片在同一全局坐标系的一张 DraftSheet 上分开排版绘制：
后片整体置于前片右侧（间距 piece_gap），脚口/立裆/臀围/膝围/腰围
五条水平线与前片等高（直接读 front.xxx 元素），落裆线单独绘制
（后立裆线下移 Dc，落裆推导.md §2.1），框架宽为 H后 = H/4 + Δ
（前后片臀围推导.md §三.1）。
因此后片流程必须在前片流程之后执行（FULL_FLOW）。
"""

from ..steps import back_steps as bs
from ..steps import back_yoke_steps as yoke
from .front_flow import FRONT_FLOW

BACK_FLOW = [
    # —— 阶段 1：五条水平参考线 + 大矩形框架 ——
    bs.draw_back_hem_line,
    bs.draw_back_crotch_line,
    bs.draw_back_crotch_drop_line,
    bs.draw_back_hip_line,
    bs.draw_back_knee_line,
    bs.draw_back_waist_line,
    bs.draw_back_outseam_refline,
    bs.draw_back_hip_width,
    bs.draw_back_inner_seam_refline,
    # —— 阶段 2：绘制后浪 ——
    bs.draw_back_crotch_width,
    bs.draw_back_center_intake,
    bs.draw_back_rise,
    # —— 阶段 3：绘制后片腰头 ——
    bs.draw_back_waistline,
    bs.draw_back_waistband_arc,
    # —— 阶段 4：绘制后臀围线 ——
    bs.draw_back_hip_final,
    # —— 阶段 5：裤中线 ——
    bs.draw_back_crease_line,
    # —— 阶段 6：膝围、脚口宽度 ——
    bs.draw_back_knee_hem_widths,
    # —— 阶段 7：外缝、内缝线 ——
    bs.draw_back_outseam_curves,
    bs.draw_back_inseam_curves,
    bs.draw_back_lower_waistband,   # 弯腰头下腰缝线（可选：直腰头跳过；侧缝绘制完后）
    # —— 阶段 8：毗围限制（测量上版；闭环修正见 flows/closure.py） ——
    bs.draw_back_thigh_limit,
    # —— 阶段 9：后片绘制省（可选步骤，开关开启且 V后省 > 0 才绘制） ——
    bs.draw_back_darts,
    # -- 阶段 10：后机头/育克（可选步骤，开关开启才绘制；先画后裁，只上版分割下口线） --
    yoke.draw_back_yoke,
]

# 整版流程：先前片、后后片（后片步骤读取前片共享基准线）
FULL_FLOW = [*FRONT_FLOW, *BACK_FLOW]
