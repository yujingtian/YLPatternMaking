"""solve_param 热启动 guess 金标（2026-08 本地引擎拖拽加速）。

固定测量（同 test_adjust / test_web_adjust）：waist=70 hip=96 knee=46
hem=36 前浪25 后浪33 裤长102 thigh=58；front_pocket=True。

金标：
- 正确性：任意合法 guess 不改 value/achieved/converged/reason（guess
  只收紧初始括号，不动护栏语义）；
- 加速分两档：单点 guess（上次解）至多 +1 次求值不回退；两点弦截外推
  （胶水 _warm_guess）邻近目标 1~2 次求值收敛（拖拽流畅度核心收益）；
- 越界静默：guess 出 (lo, hi) 与 None 路径逐位一致（含 evaluations）。
"""

import pytest

from ylpattern.flows.adjust import element_coordinate, solve_param
from ylpattern.flows.closure import run_with_thigh_closure
from ylpattern.params import Measurements, PatternOptions

ADJ_M = dict(waist=70, hip=96, knee=46, hem=36,
             front_rise=25, back_rise=33, outseam=102, thigh=58)
POCKET_ON = {"front_pocket": True}


def _solve(m, o, *, target, guess=None, param="front_pocket_p2_drop",
           element="front.pocket_p2", axis="y", lo=2.0, hi=15.0):
    return solve_param(m, o, element=element, param=param, axis=axis,
                       target=target, lo=lo, hi=hi, t=None, guess=guess)


@pytest.fixture(scope="module")
def setup():
    m = Measurements(**ADJ_M)
    o = PatternOptions.from_dict(POCKET_ON)
    ctx, _ = run_with_thigh_closure(m, o)
    y0 = element_coordinate(ctx, "front.pocket_p2", "y")
    return m, o, y0


def test_guess_none_and_far_guess_agree(setup):
    """guess=None 与远离解的 guess 结果一致（正确性不依赖猜测质量）。
    求解器契约是坐标容差（|残差|<=tol_coord=0.01cm 即停）：不同迭代
    路径的参数解允许 ~1e-4 量级差异，断言按契约口径（value 宽松、
    achieved 同达目标容差内）。"""
    m, o, y0 = setup
    target = y0 - 1.5
    base = _solve(m, o, target=target)
    assert base.converged and base.reason == "tol"
    for guess in (2.5, 14.0, 6.0):
        r = _solve(m, o, target=target, guess=guess)
        assert r.converged and r.reason == "tol"
        assert r.value == pytest.approx(base.value, abs=0.01)
        assert abs(r.achieved - target) <= 0.01
        assert abs(r.achieved - base.achieved) <= 0.01


def test_guess_single_point_no_regression(setup):
    """单点 guess（上次解）：至多多 1 次求值（guess 求值本身），
    结果正确——中距离跳变的兜底表现。"""
    m, o, y0 = setup
    first = _solve(m, o, target=y0 - 1.5)
    cold = _solve(m, o, target=y0 - 2.5)
    warm = _solve(m, o, target=y0 - 2.5, guess=first.value)
    assert warm.converged and warm.reason == "tol"
    assert warm.value == pytest.approx(cold.value, abs=0.01)
    assert abs(warm.achieved - (y0 - 2.5)) <= 0.01
    assert warm.evaluations <= cold.evaluations + 1


def test_guess_two_point_extrapolation_one_eval(setup):
    """两点弦截外推（胶水 _warm_guess 同逻辑）：两个历史解定斜率，
    邻近目标的第三次解 1~2 次求值即收敛（实测 1 次）——拖拽流畅度
    的核心收益来源。"""
    m, o, y0 = setup
    t1, t2, t3 = y0 - 1.5, y0 - 1.8, y0 - 2.1
    r1 = _solve(m, o, target=t1)
    r2 = _solve(m, o, target=t2)
    slope = (r2.achieved - r1.achieved) / (r2.value - r1.value)
    guess = r2.value + (t3 - r2.achieved) / slope
    r3 = _solve(m, o, target=t3, guess=guess)
    assert r3.converged and r3.reason == "tol"
    assert abs(r3.achieved - t3) <= 0.01
    assert r3.evaluations <= 2


def test_guess_hits_tolerance_single_eval(setup):
    """guess 恰为上次收敛解：|f(guess)|<=tol_coord，1 次求值直接返回。"""
    m, o, y0 = setup
    first = _solve(m, o, target=y0 - 1.5)
    assert first.evaluations > 1
    again = _solve(m, o, target=y0 - 1.5, guess=first.value)
    assert again.evaluations == 1
    assert again.converged and again.reason == "tol"
    assert again.value == pytest.approx(first.value, abs=1e-9)


def test_guess_out_of_range_is_silent_noop(setup):
    """guess 越界（=lo/hi/区间外）静默弃用：与 None 路径逐位一致。"""
    m, o, y0 = setup
    base = _solve(m, o, target=y0 - 1.5, guess=None)
    for guess in (2.0, 15.0, -3.0, 99.0):
        r = _solve(m, o, target=y0 - 1.5, guess=guess)
        assert (r.value, r.achieved, r.converged, r.reason,
                r.evaluations) == (base.value, base.achieved,
                                   base.converged, base.reason,
                                   base.evaluations)


def test_guess_preserves_clamped_semantics(setup):
    """目标超参数能力（range_clamped）时 guess 不改判：仍报钳制态，
    前端学边界机制依赖该 reason 稳定。"""
    m, o, y0 = setup
    base = _solve(m, o, target=y0 - 30.0)          # 远超 p2_drop 能力
    assert base.reason == "range_clamped"
    r = _solve(m, o, target=y0 - 30.0, guess=8.0)
    assert r.reason == "range_clamped"
    assert r.value == pytest.approx(base.value, abs=1e-9)
