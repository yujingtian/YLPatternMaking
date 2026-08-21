"""裁片收集测试（推码方案步 2；flows/collect.py）。

金标：固定顺序 waistband / back_yoke / front_facing|front_patch /
front_pouch / front_fly_single(+double) / watch_pocket / belt_loop /
back_patch / front_piece / back_piece；关闭项进 skips 不构建；双排关闭
只回单片。
"""

import pytest

from ylpattern.flows.back_flow import FULL_FLOW
from ylpattern.flows.collect import collect_pieces
from ylpattern.flows.runner import FlowRunner
from ylpattern.params import Measurements, PatternOptions

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)


def _ctx(**opt) -> "object":
    return FlowRunner(M, PatternOptions(**opt)).run(FULL_FLOW)


@pytest.fixture(scope="module")
def ctx_all():
    # watch_pocket 默认 facing_intersect 模式要求袋贴内边取 tangent 模式
    # （同 tests/test_watch_pocket_piece.py 可行组合）
    return _ctx(back_yoke=True, back_patch=True, front_pocket=True,
                front_pocket_facing=True, front_pocket_facing_mode="tangent",
                front_pouch=True, fly_separate=True, fly_sep_double=True,
                watch_pocket=True, belt_loop=True)


def test_all_on_order_and_no_skips(ctx_all):
    """全开关矩阵：片名有序金标，无跳过。"""
    pieces, skips = collect_pieces(ctx_all)
    assert [p.name for p in pieces] == [
        "waistband", "back_yoke", "front_facing", "front_pouch",
        "front_fly_single", "front_fly_double", "watch_pocket", "belt_loop",
        "back_patch", "front_piece", "back_piece"]
    assert skips == []


def test_all_off_minimal_set():
    """全关：仅整版必有的腰头/前片/后片，7 项进 skips 不构建。"""
    pieces, skips = collect_pieces(_ctx())
    assert [p.name for p in pieces] == ["waistband", "front_piece",
                                        "back_piece"]
    assert len(skips) == 7
    assert any("back_yoke" in s for s in skips)
    assert any("front_pocket_facing" in s for s in skips)
    assert any("front_pouch" in s for s in skips)
    assert any("fly_separate" in s for s in skips)
    assert any("watch_pocket" in s for s in skips)
    assert any("belt_loop" in s for s in skips)
    assert any("back_patch" in s for s in skips)


def test_front_patch_dispatch():
    """前口袋按 facing/patch 派发：开 front_patch 时片名为 front_patch。"""
    pieces, _ = collect_pieces(_ctx(front_pocket=True, front_patch=True))
    assert "front_patch" in [p.name for p in pieces]
    assert "front_facing" not in [p.name for p in pieces]


def test_fly_double_off_single_only():
    """门襟双排关闭（fly_sep_double=False）只回单片。"""
    pieces, skips = collect_pieces(_ctx(fly_separate=True,
                                        fly_sep_double=False))
    names = [p.name for p in pieces]
    assert "front_fly_single" in names
    assert "front_fly_double" not in names
    assert not any("门襟" in s for s in skips)   # fly_separate 开，不算跳过
