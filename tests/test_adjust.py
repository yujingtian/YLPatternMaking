"""可调点反解求解器 flows/adjust 测试（web 二期拖拽；金标）。

参数：waist=70 hip=96 knee=46 hem=36 前浪25 后浪33 裤长102 thigh=58
（thigh_limit 默认关，run_with_thigh_closure 退化为单次整版执行）。

金标依据（各步骤 basis 已注明）：
- front.hem 脚口弧 = sag_curve：t=0.5 处 y 恰为弦中点 y − sag（对 sag
  严格线性、斜率 −1、端点与 sag 无关）→ 弦截一轮精确命中，
  evaluations ≤ 4，value 恢复到 1e-6；
- front.pocket_p2 弧长参数化（非线性、单调）与 front.outseam_upper
  δx（t=0.5 处对 δx 线性）：可恢复性——先用 v* 前向跑出目标坐标，
  再反解应恢复 v*（1e-3）；
- 越界目标 → range_clamped 钳最近端；tangent 模式下 bulge 为死参数
  → no_effect（仅 2 次求值）；
- 本测量下 P2 外缝弧长仅 12.85：绑定 hi=15/200 超能力时，求解器向内
  二分**自愈到能力边界**（hi=200 时钳在 ≈12.85 报 range_clamped，
  不误判 engine_error）；仅当区间与当前参数值全部不可生成（基线损坏，
  配置/测量矛盾）→ 抛 ValueError。
"""

from dataclasses import replace

import pytest

from ylpattern.flows.adjust import element_coordinate, solve_param
from ylpattern.flows.closure import run_with_thigh_closure
from ylpattern.params import Measurements, PatternOptions

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)
O = PatternOptions(delta=1.0, front_pocket=True)


def _coord(param: str, value: float, element: str, axis: str,
           t: float | None = None, o: PatternOptions = O) -> float:
    """前向：给定参数值跑整版，取定位器坐标。"""
    ctx, _ = run_with_thigh_closure(M, replace(o, **{param: value}))
    return element_coordinate(ctx, element, axis, t=t)


# ---------- 定位器 ----------

def test_element_coordinate_locators():
    ctx, _ = run_with_thigh_closure(M, O)
    assert element_coordinate(ctx, "front.pocket_p2", "y") == pytest.approx(
        ctx.point("front.pocket_p2").y)
    assert element_coordinate(ctx, "front.outseam_upper", "x", t=0.5) == \
        pytest.approx(ctx.curve("front.outseam_upper").point_at(0.5).x)
    with pytest.raises(KeyError):                       # 元素不存在
        element_coordinate(ctx, "front.no_such", "x")
    with pytest.raises(TypeError):                      # 线元素不可作定位器
        element_coordinate(ctx, "front.crotch_line", "x")
    with pytest.raises(ValueError):                     # 曲线缺 t
        element_coordinate(ctx, "front.hem", "x")
    with pytest.raises(ValueError):                     # axis 非法
        element_coordinate(ctx, "front.pocket_p2", "z")


def test_solve_param_argument_guards():
    with pytest.raises(KeyError):
        solve_param(M, O, element="front.hem", param="no_such_field",
                    axis="y", target=0.0, lo=0.0, hi=1.0, t=0.5)
    with pytest.raises(ValueError):
        solve_param(M, O, element="front.hem", param="front_hem_arc_sag",
                    axis="y", target=0.0, lo=1.0, hi=0.0, t=0.5)


# ---------- 线性金标 ----------

def test_hem_sag_linear_golden():
    # sag=0 时 t=0.5 处 y = 弦中点 y；目标 = 弦中点 − 0.4 → 反解 sag=0.4
    y0 = _coord("front_hem_arc_sag", 0.0, "front.hem", "y", t=0.5)
    r = solve_param(M, O, element="front.hem", param="front_hem_arc_sag",
                    axis="y", target=y0 - 0.4, lo=0.0, hi=1.5, t=0.5)
    assert r.converged and r.reason == "tol"
    assert r.value == pytest.approx(0.4, abs=1e-6)
    assert r.evaluations <= 4
    assert r.achieved == pytest.approx(y0 - 0.4, abs=1e-6)


# ---------- 可恢复性（前向出目标，反向恢复参数） ----------

@pytest.mark.parametrize("v_star", [5.0, 7.5, 12.0])
def test_pocket_p2_recoverable(v_star):
    target = _coord("front_pocket_p2_drop", v_star, "front.pocket_p2", "y")
    # tol_coord 收紧到 1e-3：参数恢复精度 = 坐标容差 / 斜率
    r = solve_param(M, O, element="front.pocket_p2",
                    param="front_pocket_p2_drop", axis="y",
                    target=target, lo=2.0, hi=15.0, tol_coord=1e-3)
    assert r.converged
    assert r.value == pytest.approx(v_star, abs=1e-3)


@pytest.mark.parametrize("v_star", [0.0, 0.3, 0.8])
def test_outseam_dx_recoverable(v_star):
    target = _coord("outseam_arc_dx", v_star,
                    "front.outseam_upper", "x", t=0.5)
    r = solve_param(M, O, element="front.outseam_upper",
                    param="outseam_arc_dx", axis="x",
                    target=target, lo=0.0, hi=1.5, t=0.5, tol_coord=1e-3)
    assert r.converged
    assert r.value == pytest.approx(v_star, abs=1e-3)


# ---------- 护栏 ----------

def test_target_beyond_range_clamps():
    y0 = _coord("front_hem_arc_sag", 0.0, "front.hem", "y", t=0.5)
    # 需 sag=5 超出 [0, 1.5]：钳最近端 hi（残差更小侧）
    r = solve_param(M, O, element="front.hem", param="front_hem_arc_sag",
                    axis="y", target=y0 - 5.0, lo=0.0, hi=1.5, t=0.5)
    assert not r.converged and r.reason == "range_clamped"
    assert r.value == pytest.approx(1.5)


def test_dead_param_reports_no_effect():
    o_tangent = replace(O, front_pocket_mouth_mode="tangent")
    # 偏离当前 0.5cm 的目标：tangent 模式下 bulge 全程无位移
    cur = _coord("front_pocket_mouth_bulge", 0.0,
                 "front.pocket_mouth", "x", t=0.5, o=o_tangent)
    r = solve_param(M, o_tangent, element="front.pocket_mouth",
                    param="front_pocket_mouth_bulge", axis="x",
                    target=cur + 0.5, lo=0.0, hi=2.5, t=0.5)
    assert not r.converged and r.reason == "no_effect"
    assert r.evaluations == 2          # 仅两端点即判定


def test_beyond_capability_self_heals_to_boundary():
    # hi=200 远超外缝弧长（本测量 12.85）：自愈到能力边界后正常判定。
    # 目标 y=60 在可达范围（y≈86~96）之外 → 钳最近端（能力边界 ≈12.85）
    r = solve_param(M, O, element="front.pocket_p2",
                    param="front_pocket_p2_drop", axis="y",
                    target=60.0, lo=2.0, hi=200.0)
    assert not r.converged and r.reason == "range_clamped"
    assert r.value == pytest.approx(12.85, abs=0.3)


def test_broken_baseline_raises():
    # 基线损坏（当前值 200 不可生成，区间 [180,220] 全不可生成）→ 抛出
    o_bad = replace(O, front_pocket_p2_drop=200.0)
    with pytest.raises(ValueError):
        solve_param(M, o_bad, element="front.pocket_p2",
                    param="front_pocket_p2_drop", axis="y",
                    target=60.0, lo=180.0, hi=220.0)
