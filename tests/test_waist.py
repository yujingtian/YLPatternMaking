"""腰部公式金标测试：前中内收量（前中内收量推导.md §三.2）。

金标：内收量 = (成品臀围 H − 成品腰围 W)/16。
  H=96, W=70 → 26/16 = 1.625（中腰区间 1.0~1.5 的参考算式值）。
"""

from ylpattern.formulas import waist


def test_front_center_intake():
    assert abs(waist.front_center_intake(96, 70) - 1.625) < 1e-9


def test_front_center_intake_with_adjust():
    # 低腰款减小 0.5：1.625 − 0.5 = 1.125
    assert abs(waist.front_center_intake(96, 70, adjust=-0.5) - 1.125) < 1e-9
