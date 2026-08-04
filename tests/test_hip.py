"""公式金标测试：与 scripts/calc_hip_width.py 的手工演算结果对照。

金标（H=96, Δ=1.0）：H前=23.0, H后=25.0, W小裆=4.8, W大裆=9.6,
前片总宽=27.8, 后片总宽=34.6（前后片臀围推导.md §三）。
"""

from ylpattern.formulas import hip


def test_hip_front_back():
    assert hip.hip_front(100, 1.5) == 23.5
    assert hip.hip_back(96, 1.0) == 25.0


def test_crotch_widths():
    assert abs(hip.crotch_front_width(96) - 4.8) < 1e-9
    assert abs(hip.crotch_back_width(96) - 9.6) < 1e-9


def test_crotch_front_adjust():
    # 紧身款修正 -0.5：4.8 - 0.5 = 4.3
    assert abs(hip.crotch_front_width(96, adjust=-0.5) - 4.3) < 1e-9


def test_crotch_back_adjust():
    # 后大裆加深修正 +0.5：9.6 + 0.5 = 10.1
    assert abs(hip.crotch_back_width(96, adjust=0.5) - 10.1) < 1e-9
    # 修正量透传后片总宽：25.0 + 10.1 = 35.1
    assert abs(hip.back_total_width(96, 1.0, adjust=0.5) - 35.1) < 1e-9


def test_total_widths():
    assert abs(hip.front_total_width(96, 1.0) - 27.8) < 1e-9
    assert abs(hip.back_total_width(96, 1.0) - 34.6) < 1e-9


def test_hip_closure():
    # 校验：2×(H前+H后) = H
    assert abs(2 * (hip.hip_front(96, 1.0) + hip.hip_back(96, 1.0)) - 96) < 1e-9

if __name__ == "__main__":
    test_hip_front_back()