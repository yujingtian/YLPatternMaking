"""腰部公式金标测试：前中内收量（前中内收量推导.md §三.2）。

金标：内收量 = (成品臀围 H − 成品腰围 W)/4 × 系数（默认 0.2）。
  H=96, W=70 → 26/4 × 0.2 = 1.3（中腰区间 1.0~1.5 的参考算式值）。
"""

from ylpattern.formulas import waist


def test_front_center_intake():
    assert abs(waist.front_center_intake(96, 70) - 1.3) < 1e-9


def test_front_center_intake_with_ratio():
    # 低腰款系数 0.15：26/4 × 0.15 = 0.975
    assert abs(waist.front_center_intake(96, 70, ratio=0.15) - 0.975) < 1e-9


def test_front_center_intake_with_adjust():
    # 低腰款减小 0.5：1.3 − 0.5 = 0.8
    assert abs(waist.front_center_intake(96, 70, adjust=-0.5) - 0.8) < 1e-9


def test_waist_front_finished():
    # 前减后加：平分（balance=0）70/4 = 17.5；balance=0.5 → 17.0（前片减）
    assert abs(waist.waist_front_finished(70) - 17.5) < 1e-9
    assert abs(waist.waist_front_finished(70, balance=0.5) - 17.0) < 1e-9


def test_waist_front_target():
    # 牛仔裤无前省：17.5；西裤前省 2.0：19.5（推导.md §三.2、§五）
    assert abs(waist.waist_front_target(70) - 17.5) < 1e-9
    assert abs(waist.waist_front_target(70, dart=2.0) - 19.5) < 1e-9


def test_side_seam_intake_front_cases():
    # 前片侧缝内收推导.md §三 三个案例（H=96, W=72 基准）
    # 案例 1：501 无前省同调节量 → 4.8
    assert abs(waist.side_seam_intake_front(23.0, 17.0, 1.2) - 4.8) < 1e-9
    # 案例 2：双褶 2.5、收斜 1.0 → 2.5
    assert abs(waist.side_seam_intake_front(23.0, 17.0 + 2.5, 1.0) - 2.5) < 1e-9
    # 案例 3：k_hip=1.5 / k_waist=0.5 → 3.8
    assert abs(waist.side_seam_intake_front(22.5, 17.5, 1.2) - 3.8) < 1e-9
