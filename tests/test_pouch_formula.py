"""formulas.pouch 金标（袋布绘制.md §三.3）：三袋型手工演算。

默认安全量 (waist_safe=4, side_safe=8) 下 standard 与 PatternOptions 原
默认链逐位一致：节点 ((5,16),(1.5,13.5))、边 (line, arc(2.5,0.6), line)。
"""

import pytest

from ylpattern.formulas import pouch


def test_standard_matches_options_default():
    """4/8 -> K1=(5,16) K2=(1.5,13.5)，中段弧高式（= 原默认链）。"""
    nodes, edges = pouch.pouch_chain_preset("standard", 4.0, 8.0)
    assert nodes == ((5.0, 16.0), (1.5, 13.5))
    assert edges == (("line",), ("arc", 2.5, 0.6), ("line",))


def test_round_bottom_same_nodes_bigger_arc():
    """圆弧底同节点、中段大弧 arc(4.0, 0.5)。"""
    nodes, edges = pouch.pouch_chain_preset("round_bottom", 4.0, 8.0)
    assert nodes == ((5.0, 16.0), (1.5, 13.5))
    assert edges == (("line",), ("arc", 4.0, 0.5), ("line",))


def test_deep_rect_scales_with_safe():
    """5/10 -> K1=(6.5,26) K2=(2,23)，全直线。"""
    nodes, edges = pouch.pouch_chain_preset("deep_rect", 5.0, 10.0)
    assert nodes == ((6.5, 26.0), (2.0, 23.0))
    assert edges == (("line",), ("line",), ("line",))


def test_standard_scales_with_safe():
    """6/10 -> K1=(7,20) K2=(3.5,16.875)（1.6875=13.5/8 规律系数）。"""
    nodes, _ = pouch.pouch_chain_preset("standard", 6.0, 10.0)
    assert nodes == ((7.0, 20.0), (3.5, 16.875))


def test_small_waist_safe_clamps_k2_dx():
    """w=1 时 K2 dx 下限 0.5（防越出侧缝），deep_rect w−3 同理。"""
    nodes, _ = pouch.pouch_chain_preset("standard", 1.0, 8.0)
    assert nodes[1][0] == 0.5
    nodes, _ = pouch.pouch_chain_preset("deep_rect", 1.0, 8.0)
    assert nodes[1][0] == 0.5


@pytest.mark.parametrize("bad", ["custom", "", "round", "STANDARD"])
def test_unknown_shape_raises(bad):
    with pytest.raises(ValueError):
        pouch.pouch_chain_preset(bad, 4.0, 8.0)
