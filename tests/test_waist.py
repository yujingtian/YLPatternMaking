"""腰部公式金标测试：前中内收量（前中内收量推导.md §三.2）、
后中内收量（后中内收点推导.md §一）。

金标：前中内收量 = (成品臀围 H − 成品腰围 W)/4 × 系数（默认 0.2）。
  H=96, W=70 → 26/4 × 0.2 = 1.3（中腰区间 1.0~1.5 的参考算式值）。
后中内收量 D_h = H_v × X/15（斜率比例折算，文档示例直接转金标）。
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


def test_waistline_horizontal_span():
    # 腰头绘制推导.md §7 伪代码示例：L=20, h=1.0, d=1.3 → sqrt(400 − 5.29) ≈ 19.867
    span = waist.waistline_horizontal_span(20.0, 1.0, 1.3)
    assert abs(span - 19.8666) < 1e-3
    # h=0、d=0 时退化为水平线：跨度 = 腰长
    assert abs(waist.waistline_horizontal_span(18.5, 0.0, 0.0) - 18.5) < 1e-9


def test_waistline_horizontal_span_raises():
    # 边界（§6.2）：L ≤ h + d 无法构成腰线
    import pytest
    with pytest.raises(ValueError, match="无法构成腰线"):
        waist.waistline_horizontal_span(2.0, 1.0, 1.3)


def test_back_center_intake_doc_examples():
    # 后中内收点推导.md §一 计算示例（斜率比 15:2.5，D_h = H_v × 2.5/15）
    assert abs(waist.back_center_intake(15.0) - 2.5) < 1e-9   # H_v=15 → 2.5
    assert abs(waist.back_center_intake(12.0) - 2.0) < 1e-9   # H_v=12（中低腰）→ 2.0
    assert abs(waist.back_center_intake(18.0) - 3.0) < 1e-9   # H_v=18（超高腰）→ 3.0


def test_back_center_intake_ratio():
    # 紧身/提臀档 X=4.0（§二 系数表）：H_v=15 → 15 × 4/15 = 4.0
    assert abs(waist.back_center_intake(15.0, intake=4.0) - 4.0) < 1e-9


def test_waist_back_target():
    # 前减后加：平分（balance=0）70/4 = 17.5；balance=0.5 → 18.0（后片加）
    assert abs(waist.waist_back_target(70) - 17.5) < 1e-9
    assert abs(waist.waist_back_target(70, balance=0.5) - 18.0) < 1e-9
    # 约克转移量 V后省 3.0：17.5 + 3.0 = 20.5（腰围推导.md §三.2、§五）
    assert abs(waist.waist_back_target(70, dart=3.0) - 20.5) < 1e-9
