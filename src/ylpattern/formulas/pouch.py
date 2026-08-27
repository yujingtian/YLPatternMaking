"""袋布自由边界常用袋型预设（袋布绘制.md §三.3，2026-08-27 登记）。

袋布自由边界 = P_w0 → K1..Kn → P_s0 开放链；K 节点相对 O（有效腰口侧缝
腰点）的 (dx, dy 向下正)，边形态三模式见 draft/curves.edge_geom。本模块以
两安全量（ΔW_safe 腰弧内延 / ΔH_safe 侧缝垂深）为基准给出常用袋型：
web「从形态导入」seed 消费本纯函数——单一事实来源，前端不复写公式。
standard 在默认安全量 (4, 8) 下与 PatternOptions 原默认链
(((5.0, 16.0), (1.5, 13.5)) + (("line",), ("arc", 2.5, 0.6), ("line",)))
逐位一致（金标钉死）。约束同公式层：只依赖标准库，纯 float/tuple 进出。
"""

_PRESET_SHAPE_ERR = ("未知袋型 shape={shape!r}"
                     "（取 standard/round_bottom/deep_rect）")


def pouch_chain_preset(shape: str, waist_safe: float, side_safe: float
                       ) -> tuple[tuple[tuple[float, float], ...], tuple]:
    """常用袋型 -> (K 节点, 边形态)。

    K 节点相对 O 的 (dx, dy 向下正)，第二节点沿腰向内收 2.5（下限 0.5
    防小安全量时越出侧缝）；边数 = 节点数 + 1（首段接腰缝锚点 P_w0、末段
    接侧缝锚点 P_s0——锚点由整版腰弧/外缝几何定位，不在本函数范围）。
    三袋型：
      standard    标准斜底：K1=(w+1, 2h) / K2=(w−2.5, 1.6875h)，中段
                  弧高式 arc(2.5, 0.6)（= 原默认链规律化）；
      round_bottom 圆弧底：同 standard 节点，中段 arc(4.0, 0.5) 大弧；
      deep_rect   加深方袋：K1=(w+1.5, 2.6h) / K2=(w−3, 2.3h)，全直线。
    非法 shape 抛 ValueError。金标：tests/test_pouch_formula.py。
    """
    k2_dx = max(waist_safe - 2.5, 0.5)
    if shape == "standard":
        nodes = ((waist_safe + 1.0, 2.0 * side_safe),
                 (k2_dx, 1.6875 * side_safe))
        edges = (("line",), ("arc", 2.5, 0.6), ("line",))
    elif shape == "round_bottom":
        nodes = ((waist_safe + 1.0, 2.0 * side_safe),
                 (k2_dx, 1.6875 * side_safe))
        edges = (("line",), ("arc", 4.0, 0.5), ("line",))
    elif shape == "deep_rect":
        nodes = ((waist_safe + 1.5, 2.6 * side_safe),
                 (max(waist_safe - 3.0, 0.5), 2.3 * side_safe))
        edges = (("line",), ("line",), ("line",))
    else:
        raise ValueError(_PRESET_SHAPE_ERR.format(shape=shape))
    return nodes, edges
