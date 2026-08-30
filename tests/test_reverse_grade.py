"""reverse.grade 合成金标测试（分段/漂移告警/单码退化；不依赖真件）。

头注手工演算（MeasuredSize 手工构造，8 键齐全；差分基准 = 原始值）：

- 单码（无可差分相邻码）-> (None, [])，调用方跳过 [size_run]；
- 三码均匀步进 2.0/2.0：单 band 全码，步进 = 中位数 2.0；
- 步进跳变（S->M 2.0、M->L 2.0、L->XL 6.0，容差 0.15）贪心分段两段：
  段1 = 差分 d0/d1 -> band {S,M,L} step 2.0；段2 = d2 -> band {XL}
  step 6.0。band 语义（params/sizerun.py）：进入某码的过渡取该码所在
  段步进——XL = L + 6.0（band_of[XL]）、S = M − 2.0（band_of[S]），
  与实测差分逐对吻合；
- 段内缓变漂移告警：步进 2.0/2.12/2.24（对中位数 2.12 偏差 0.12 <
  容差 0.15，单 band），自基码展开逐码漂移 0.12/0.12/0 -> 告警线 0.1
  触发一行；
- 展开一致性（sizerun._expand 同规则）：均匀三码从中间码双向累加复现
  逐码值（中位数步进 2.0 时整除零漂移）。
"""

from __future__ import annotations

import pytest

from ylpattern.reverse.grade import grade_from_measurements
from ylpattern.reverse.measure import MeasuredSize

_KEYS = ("waist", "hip", "knee", "hem", "front_rise", "back_rise",
         "outseam", "thigh")


def _ms(size: str, waist: float) -> MeasuredSize:
    return MeasuredSize(size=size,
                        values={k: waist for k in _KEYS}, trace=[], extras={})


def test_single_size_degenerates():
    sr, warns = grade_from_measurements({"S": _ms("S", 64.0)}, "S", "T1")
    assert sr is None and warns == []


def test_uniform_single_band():
    per = {"S": _ms("S", 64.0), "M": _ms("M", 66.0), "L": _ms("L", 68.0)}
    sr, warns = grade_from_measurements(per, "M", "T1")
    assert sr is not None and not warns
    assert sr["base"] == "M" and sr["order"] == ["S", "M", "L"]
    assert len(sr["band"]) == 1
    band = sr["band"][0]
    assert band["sizes"] == ["S", "M", "L"]
    assert all(band[k] == 2.0 for k in _KEYS)


def test_step_jump_two_bands():
    """步进跳变分段：进入 XL 的过渡取 XL 所在段（band 语义核心断言）。"""
    per = {"S": _ms("S", 64.0), "M": _ms("M", 66.0), "L": _ms("L", 68.0),
           "XL": _ms("XL", 74.0)}                    # L->XL 跳 +6.0
    sr, warns = grade_from_measurements(per, "M", "T1")
    assert sr is not None
    assert any("不均匀" in w for w in warns)          # 分段告警
    b1, b2 = sr["band"]
    assert b1["sizes"] == ["S", "M", "L"] and b1["waist"] == 2.0
    assert b2["sizes"] == ["XL"] and b2["waist"] == 6.0
    # 展开一致性：自基码 M 双向累加逐码复现（步进 = 目标码所在段）
    band_of = {s: b for b in sr["band"] for s in b["sizes"]}
    assert 66.0 - band_of["S"]["waist"] == 64.0       # S = M − band[S]
    assert 66.0 + band_of["L"]["waist"] == 68.0       # L = M + band[L]
    assert 68.0 + band_of["XL"]["waist"] == 74.0      # XL = L + band[XL]


def test_drift_warn_when_steps_creep():
    """段内缓变（≤容差单 band）但累计漂移超告警线 -> 一行告警。"""
    per = {"S": _ms("S", 64.0), "M": _ms("M", 66.0), "L": _ms("L", 68.12),
           "XL": _ms("XL", 70.36)}                    # 步进 2.0/2.12/2.24
    sr, warns = grade_from_measurements(per, "S", "T1")
    assert sr is not None and len(sr["band"]) == 1     # 偏差 0.12 < 0.15 不分段
    assert sr["band"][0]["waist"] == pytest.approx(2.12, abs=1e-6)
    assert len([w for w in warns if "偏差" in w]) == 1  # 累计漂移 0.12 > 0.1
