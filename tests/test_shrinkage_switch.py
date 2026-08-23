"""缩水总开关 shrinkage_enabled 测试（计算级跳过，与 show_seam_allowance 的
出口层显示控制不同）。

金标（PatternOptions.shrinkage_rates 解析口 + 全裁片端到端）：
- 解析矩阵：总开关 False -> 专用率（含 None）一律归 (0, 0)；True 时专用
  None 回退全局 (0.1, 0.06)、专用非 None 覆盖 (0.05, 0.0)；
- 端到端（FULL_FLOW 全开关 + collect_pieces，M=W70/H96 组）：
  - 全局 0.1/0.06 开缩水时腰头有缩水 notes 且 shrunk != net（净样被放大）；
  - 总开关 False（专用/全局率保持非 0）时全部 11 片 shrunk == net 逐边相等、
    notes 无「缩水：」字样--计算级等价于率全 0，专用率一并失效；
  - 专用率单独生效：front_piece_shrinkage_warp=0.05 时前片 Y 向被放大
    （shrunk.y > net.y），关总开关后复原。
口径：False 不是把率改成 0 存储（字段原值保留），仅在解析口收缩。
"""

import pytest

from ylpattern.flows.back_flow import FULL_FLOW
from ylpattern.flows.collect import collect_pieces
from ylpattern.flows.runner import FlowRunner
from ylpattern.params import Measurements, PatternOptions

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)

_OPT = dict(back_yoke=True, back_patch=True, front_pocket=True,
            front_pocket_facing=True, front_pocket_facing_mode="tangent",
            front_pouch=True, fly_separate=True, fly_sep_double=True,
            watch_pocket=True, belt_loop=True)


def _pieces(**opt):
    ctx = FlowRunner(M, PatternOptions(**_OPT, **opt)).run(FULL_FLOW)
    return dict((p.name, p) for p in collect_pieces(ctx)[0])


# ---- 解析口金标（手算）----

def test_rates_off_returns_zero_even_with_overrides():
    o = PatternOptions(shrinkage_enabled=False,
                       shrinkage_warp=0.1, shrinkage_weft=0.06,
                       back_yoke_shrinkage_warp=0.05)
    assert o.shrinkage_rates(None, None) == (0.0, 0.0)
    assert o.shrinkage_rates(0.05, 0.04) == (0.0, 0.0)
    # 字段原值保留，仅在解析口收缩
    assert o.shrinkage_warp == 0.1 and o.back_yoke_shrinkage_warp == 0.05


def test_rates_on_fallback_and_override():
    o = PatternOptions(shrinkage_warp=0.1, shrinkage_weft=0.06)
    assert o.shrinkage_rates(None, None) == (0.1, 0.06)
    assert o.shrinkage_rates(0.05, 0.0) == (0.05, 0.0)
    assert PatternOptions().shrinkage_rates(None, None) == (0.0, 0.0)


# ---- 端到端金标 ----

def test_off_all_pieces_shrunk_equals_net():
    """总开关 False：11 片全部无缩水--shrunk == net 逐边相等，或率 0 守卫
    （袋布/小表袋等 `if warp or weft` 分支）干脆未构建 shrunk（() 空元组）；
    notes 不再出现「缩水：」。"""
    on = _pieces(shrinkage_warp=0.1, shrinkage_weft=0.06,
                 back_yoke_shrinkage_warp=0.05, watch_pocket_shrinkage_warp=0.1)
    assert any("缩水：" in n for n in on["waistband"].notes)   # 开时确有缩水
    off = _pieces(shrinkage_enabled=False,
                  shrinkage_warp=0.1, shrinkage_weft=0.06,
                  back_yoke_shrinkage_warp=0.05, watch_pocket_shrinkage_warp=0.1)
    assert len(off) == 11
    for name, p in off.items():
        assert p.shrunk_edges in ((), p.net_edges), name
        assert not any("缩水：" in n for n in p.notes), name


def test_on_shrunk_actually_scales():
    """开总开关时全局率真实生效（关则不动）：前片（经向=局部 Y 吃 warp）、
    腰头（WIDTH 映射 Y 吃 warp）shrunk 净样均 != net；再关总开关即复原逐边相等。"""
    on = _pieces(shrinkage_warp=0.1, shrinkage_weft=0.06)
    off = _pieces(shrinkage_enabled=False,
                  shrinkage_warp=0.1, shrinkage_weft=0.06)
    for name in ("front_piece", "waistband"):
        assert on[name].shrunk_edges not in ((), on[name].net_edges), name
        assert off[name].shrunk_edges == off[name].net_edges, name


def test_waistband_dedicated_rates_override_and_disabled():
    """腰头专用缩水率（2026-08 新增，此前唯一直读全局的主面料裁片）：
    - 专用 0.05/0.0 覆盖全局 0.1/0.06（WIDTH 映射 X 吃纬 0、Y 吃经 0.05，
      腰头局部系 Y 向下、shrunk 纵向边长精确 ×1/(1-0.05)）；
    - 总开关 False 时专用率一并失效，shrunk == net。"""
    on = _pieces(shrinkage_warp=0.1, shrinkage_weft=0.06,
                 waistband_shrinkage_warp=0.05, waistband_shrinkage_weft=0.0)
    wb = on["waistband"]
    assert wb.shrunk_edges not in ((), wb.net_edges)
    # 取一条纯竖直净边（腰头局部系 x 为常数的后中/端封边），shrunk 长度
    # = net 长度 / (1-0.05)（Y 吃经向 0.05；X 吃纬 0 不横向缩放）
    for en, es in zip(wb.net_edges, wb.shrunk_edges):
        gn, gs = en.geom, es.geom
        if isinstance(gn, type(gs)) and hasattr(gn, "a"):  # LineSegment
            if abs(gn.a.x - gn.b.x) < 1e-9 and abs(gn.a.y - gn.b.y) > 1e-6:
                ln = abs(gn.a.y - gn.b.y)
                ls = abs(gs.a.y - gs.b.y)
                assert ls == pytest.approx(ln / 0.95, abs=1e-9)
                assert gs.a.x == pytest.approx(gn.a.x, abs=1e-9)  # X 不缩
    off = _pieces(shrinkage_enabled=False,
                  shrinkage_warp=0.1, shrinkage_weft=0.06,
                  waistband_shrinkage_warp=0.05, waistband_shrinkage_weft=0.0)
    assert off["waistband"].shrunk_edges == off["waistband"].net_edges
