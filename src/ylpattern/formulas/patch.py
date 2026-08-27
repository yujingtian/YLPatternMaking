"""贴袋净形公式：纯 float 计算（后贴袋绘制.md §二.1、前口袋绘制.md §五）。

步骤层（back_patch_steps / front_pocket_steps）与 web 端「从形态导入」
（webschema.seed_shape）共用本模块——预设形态角点是同一份打版
事实，单一来源，禁止在前端 TS 复写。
"""

from __future__ import annotations


def patch_net_vertices(shape: str, w: float, h: float,
                       bottom_width: float = 0.0,
                       tip_depth: float = 0.0,
                       chamfer: float = 0.0,
                       chamfer_bottom_taper: bool = False
                       ) -> tuple[tuple[float, float], ...]:
    """贴袋净形预设形态的局部角点序列（后贴袋绘制.md §二.1 / 前口袋绘制.md §五）。

    规范局部系（前后侧统一）：u 沿袋口自定位角点量取为正、v 向下为正，
    V0=(0,0) 为定位角点（后贴袋=袋口近后浪侧顶点 P0、前贴袋=袋口外上角），
    顺时针绕行。前贴袋存储的 custom 角点 dy 向上为正，与规范系相反，
    由步骤层映射（Point(a.x+u, a.y−v)），预设角点两侧行为一致。

    形态路由（与步骤层原内联实现逐位等价）：
      - "rectangle" 方底四边形：底两角 (w,h)/(0,h)；
      - "baker_shield" 盾形尖底：底边换为底中尖点（额外加深 tip_depth）
        的五边形，袋底宽可独立于袋口宽（0 = 同宽，底边两侧对称内收
        bi = (w − bottom_width)/2，负值 = 外扩）；
      - "angular" 底角斜切：两底角各斜切 chamfer 的六边形。chamfer_bottom_taper
        登记两侧行为差异的唯一出处：前贴袋消费底宽（六边形底边用 w−bi、
        斜切起点同随 bi 内收），后贴袋不消费（顶点全用 w/c，后贴袋绘制.md
        §二.1 六边形）。

    金标（tests/test_formulas_patch.py 头注）：w=14, h=16, bottom_width=12,
    tip_depth=2.5, chamfer=2 时 rectangle/baker/back angular/front angular
    的角点序列。

    shape 为 "custom" 或未知值时抛 ValueError：custom 角点由
    PatternOptions.back_patch_custom_points / front_patch_custom_points
    直接给定，不经本函数。
    """
    bw = bottom_width or w
    bi = (w - bw) / 2
    if shape == "rectangle":
        return ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h))
    if shape == "baker_shield":
        return ((0.0, 0.0), (w, 0.0),
                (w - bi, h), (w / 2, h + tip_depth), (bi, h))
    if shape == "angular":
        c = chamfer
        if chamfer_bottom_taper:
            return ((0.0, 0.0), (w, 0.0),
                    (w - bi, h - c), (w - bi - c, h), (bi + c, h), (bi, h - c))
        return ((0.0, 0.0), (w, 0.0),
                (w, h - c), (w - c, h), (c, h), (0.0, h - c))
    raise ValueError(f"未知贴袋形态 shape={shape!r}"
                     "（custom 角点由 *_custom_points 直接给定，"
                     "预设形态取 rectangle/baker_shield/angular）")
