"""毗围闭环修正公式金标（前后片毗围推导.md §三）。

手工演算（ΔW = 目标 − 实测，正 = 需加宽；默认阈值：平分界 0.2、
双轨界 0.3、大差量前片分配比 0.2）：
  片间分配：ΔW=0.2（边界）→ 平分 0.5；ΔW=0.8 / ±2.0（>0.2）→ 前 0.2
    （红线：大差量严禁 50:50，前 20% : 后 80%）。
  裆尖调拨（|ΔW| ≤ 0.3 单动侧缝 → 0）：
    ΔW=0.5 → 前小裆 0.09×0.5 = 0.045；
    ΔW=2.0 → 前 0.18、后大裆 0.21×2 = 0.42；
    ΔW=10 → 前钳 +0.4（防卡耻骨）、后钳 +1.0（防下蹲崩破）；
    ΔW=−10 → 前 −0.4、后 −1.0（对称钳制）。
  累计钳制：已调 0.3 再调 0.18 → 累计钳 0.4（极值红线针对全程累计）。
  侧缝承担：ΔW=2.0 → 前 0.2×2 − 0.18 = 0.22、后 0.8×2 − 0.42 = 1.18；
    ΔW=−0.2（边界平分、单轨）→ 前 −0.1、后 −0.1；
    裆尖实际增量小于请求时残余回流侧缝：ΔW=2.0、fc=0.1、bc=0.2
    → 前 0.4 − 0.1 = 0.3、后 1.6 − 0.2 = 1.4。
  防内凹钳制（外缝朝 −X）：加宽 0.5 → 0.28 − 0.5 = −0.22 不钳；
    收窄 0.7 → 33.05 + 0.7 = 33.75 跨越弦 33.31 → 钳在 33.31。
"""

import pytest

from ylpattern.formulas import thigh as thigh_f


def test_front_share_ratio():
    assert thigh_f.front_share_ratio(0.2) == 0.5       # 边界仍平分
    assert thigh_f.front_share_ratio(0.8) == 0.2       # 大差量 20:80 红线
    assert thigh_f.front_share_ratio(2.0) == 0.2
    assert thigh_f.front_share_ratio(-2.0) == 0.2      # 负向同理


def test_front_crotch_shift():
    assert thigh_f.front_crotch_shift(0.3) == 0.0      # 边界仍单轨，锁死裆尖
    assert thigh_f.front_crotch_shift(0.5) == pytest.approx(0.045)
    assert thigh_f.front_crotch_shift(2.0) == pytest.approx(0.18)
    assert thigh_f.front_crotch_shift(-2.0) == pytest.approx(-0.18)
    assert thigh_f.front_crotch_shift(10.0) == 0.4     # 钳制：防卡耻骨
    assert thigh_f.front_crotch_shift(-10.0) == -0.4


def test_back_crotch_shift():
    assert thigh_f.back_crotch_shift(0.3) == 0.0
    assert thigh_f.back_crotch_shift(2.0) == pytest.approx(0.42)
    assert thigh_f.back_crotch_shift(10.0) == 1.0      # 钳制：防下蹲崩破
    assert thigh_f.back_crotch_shift(-10.0) == -1.0


def test_cap_crotch_total():
    # 累计钳制：0.3 + 0.18 → 0.4；−0.3 − 0.18 → −0.4
    assert thigh_f.cap_crotch_total(0.3, 0.18, 0.4) == pytest.approx(0.4)
    assert thigh_f.cap_crotch_total(-0.3, -0.18, 0.4) == pytest.approx(-0.4)
    # 未触限时原样累计
    assert thigh_f.cap_crotch_total(0.1, 0.18, 0.4) == pytest.approx(0.28)


def test_outseam_shifts():
    f, b = thigh_f.outseam_shifts(2.0)
    assert f == pytest.approx(0.22)    # 0.2×2 − 0.18
    assert b == pytest.approx(1.18)    # 0.8×2 − 0.42
    f, b = thigh_f.outseam_shifts(-0.2)
    assert f == pytest.approx(-0.1)    # 边界平分，单轨全量
    assert b == pytest.approx(-0.1)
    # 裆尖钳制残余回流侧缝（闭环迭代传实际增量）
    f, b = thigh_f.outseam_shifts(2.0, 0.1, 0.2)
    assert f == pytest.approx(0.3)
    assert b == pytest.approx(1.4)


def test_clamp_outseam_target():
    # 加宽（dw_out > 0，目标向 −X）：0.28 − 0.5 = −0.22，不钳
    assert thigh_f.clamp_outseam_target(0.28, 0.5, 1.98) == pytest.approx(-0.22)
    # 收窄（目标向 +X）：33.05 + 0.7 = 33.75 跨越弦 33.31 → 钳在弦上
    assert thigh_f.clamp_outseam_target(33.05, -0.7, 33.31) == pytest.approx(33.31)


def test_formula_params_overridable():
    # 文档常数均可由调用方覆盖（PatternOptions.thigh_* 传入）：
    # 分配分界 1.0→0.5：ΔW=0.8 从平分变为大差量比 0.4
    assert thigh_f.front_share_ratio(0.8, split_max=0.5, share_large=0.4) == 0.4
    # 双轨阈值 1.5→1.0：ΔW=1.2 从单动侧缝变为内外联动，系数/上限同步生效
    assert thigh_f.front_crotch_shift(1.2, dual_track_min=1.0,
                                      coef=0.10, max_abs=0.5) == pytest.approx(0.12)
    assert thigh_f.back_crotch_shift(9.0, dual_track_min=1.0,
                                     coef=0.25, max_abs=0.8) == pytest.approx(0.8)
    # 侧缝分配比覆盖：ΔW=2.0、share_large=0.4 → 前 0.4×2、后 0.6×2
    f, b = thigh_f.outseam_shifts(2.0, 0.0, 0.0, share_large=0.4)
    assert (f, b) == (pytest.approx(0.8), pytest.approx(1.2))
