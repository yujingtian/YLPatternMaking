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
]

# 整版流程：先前片、后后片（后片步骤读取前片共享基准线）
FULL_FLOW = [*FRONT_FLOW, *BACK_FLOW]
