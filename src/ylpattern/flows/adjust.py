"""可调点反解驱动（web 二期拖拽调版；.doc/python工程设计.md §10.7）。

策略与 flows/closure.py 同层同哲学的"整版重跑"：
  拖拽目标坐标 target → 对绑定参数 p 在 [lo, hi] 上数值求根
  f(v) = element_coordinate(整版重跑(m, replace(o, **{p: v})), element, axis, t)
         − target
每轮求值穿过 run_with_thigh_closure（与整版展示同口径：thigh_limit 关闭时
退化为单次整版执行；浪长闭合等结构不变量自动保持）。

不逐点手写反演公式：本库参数 → 定位器坐标大多严格单调（内收/裆宽对
修正量斜率 ±1、sag_curve 中点偏差精确 = −sag、贝塞尔对控制点线性），
bracketed secant–bisection（Illinois 防单侧滞留）2~4 轮收敛，线性依赖
一轮弦截精确命中。

护栏（照抄 closure 精神）：
- 解值钳定在 [lo, hi]；目标超能力 → range_clamped 返回最近端；
- 参数对定位器无效果（模式不匹配 / 毗围闭环对抗）→ no_effect；
- 引擎异常（如 front_pocket_p2_drop 大于外缝弧长、绑定 range 端点超出
  生成能力）→ 以区间中部可用点为锚向失败端**二分找能力边界**，把括号
  收紧到真实边界而非直接判死；迭代内点失败回退中点，仍败 →
  engine_error 返回当前最优，不抛出；仅当基线（当前参数值）也无法
  生成时抛 ValueError（配置/测量矛盾，由 web 层转结构化错误）。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..draft import DraftContext
from ..draft.elements import NamedCurve, NamedPoint
from ..params import Measurements, PatternOptions
from .closure import run_with_thigh_closure


@dataclass(frozen=True)
class SolveResult:
    """单次反解结果。

    value/achieved/residual：解出的参数值、该值下定位器实测坐标（cm）、
    achieved − target（负 = 目标在可达范围外近侧端）。
    converged：|residual| ≤ tol_coord。
    reason：tol（收敛）/ range_clamped（钳端）/ no_effect / engine_error /
    max_iter（迭代耗尽未达坐标容差）。
    """

    value: float
    achieved: float
    residual: float
    converged: bool
    evaluations: int
    reason: str = ""


def element_coordinate(ctx: DraftContext, element: str, axis: str,
                       *, t: float | None = None) -> float:
    """定位器：元素在 axis 向的当前坐标（cm）。

    点：NamedPoint 的轴向坐标；曲线：t 必填，取 CubicBezier.point_at(t)
    的轴向坐标——SVG 里曲线是采样 polyline，反解必须回到贝塞尔本体。
    元素不存在 → KeyError；线元素/axis 不符 → TypeError/ValueError
    （web 端 handles 下发用它做元素级自门控）。
    """
    if axis not in ("x", "y"):
        raise ValueError(f"axis 只支持 x/y，得到 {axis!r}")
    el = ctx.sheet.get(element)
    if isinstance(el, NamedPoint):
        p = el.geom
    elif isinstance(el, NamedCurve):
        if t is None:
            raise ValueError(f"曲线元素 {element} 必须给定位参数 t")
        p = el.geom.point_at(t)
    else:
        raise TypeError(f"元素 {element} 不是点/曲线，不能作为可调定位器")
    return p.x if axis == "x" else p.y


def solve_param(m: Measurements, o: PatternOptions, *,
                element: str, param: str, axis: str, target: float,
                lo: float, hi: float, t: float | None = None,
                tol_coord: float = 0.01, tol_param: float = 1e-3,
                max_iter: int = 16) -> SolveResult:
    """对单个参数反解：求 v 使定位器坐标在整版重跑后达到 target。

    f(v) = element_coordinate(run_with_thigh_closure(
        m, replace(o, **{param: v}))[0], element, axis, t=t) − target，
    在 [lo, hi] 上求根（bracketed secant–bisection，Illinois 阻尼）。
    tol_coord 坐标容差 cm（缺省 0.01 = 0.1px @10px/cm，低于目测分辨）；
    tol_param 参数区间收敛宽；max_iter 弦截/二分轮数上限（总求值 =
    2 端点 + 失败端能力边界二分 ≤6×2 + max_iter + 内点回退 ≤2）。
    """
    if not hasattr(o, param):
        raise KeyError(f"PatternOptions 无字段 {param}")
    if axis not in ("x", "y"):
        raise ValueError(f"axis 只支持 x/y，得到 {axis!r}")
    if not hi > lo:
        raise ValueError(f"求根区间须 lo < hi，得到 [{lo}, {hi}]")
    evals = 0

    def f(v: float) -> tuple[float | None, bool]:
        """单次求值：整版重跑取定位器坐标残差；引擎任何异常 → (None, False)。"""
        nonlocal evals
        evals += 1
        try:
            ctx, _ = run_with_thigh_closure(m, replace(o, **{param: v}))
            return element_coordinate(ctx, element, axis, t=t) - target, True
        except Exception:
            return None, False

    def result(v: float, fv: float, converged: bool,
               reason: str) -> SolveResult:
        return SolveResult(v, target + fv, fv, converged, evals, reason)

    def boundary(good: tuple[float, float],
                 bad_v: float) -> tuple[float, float]:
        """从可用点向失败端二分 ≤10 轮，返回最靠失败端的可用点（能力边界）。"""
        g_v, g_f = good
        b_v = bad_v
        for _ in range(10):
            if abs(b_v - g_v) <= tol_param:
                break
            c = (g_v + b_v) / 2
            fc, ok = f(c)
            if ok:
                g_v, g_f = c, fc
            else:
                b_v = c
        return g_v, g_f

    lo_f = f(lo)
    hi_f = f(hi)
    if lo_f[1] and hi_f[1]:
        a, fa = lo, lo_f[0]
        b, fb = hi, hi_f[0]
    else:
        # 至少一端不可生成（绑定 range 超能力）：锚点优先取可用端（零额
        # 外求值），两端皆败再试区间中部，仍败退当前参数值（展示基线，
        # 正常必然可生成）→ engine_error；连基线都不可生成 → 配置/测量
        # 矛盾，抛 ValueError（web 层转结构化错误）
        anchor: tuple[float, float] | None = None
        if lo_f[1]:
            anchor = (lo, lo_f[0])
        elif hi_f[1]:
            anchor = (hi, hi_f[0])
        else:
            mid_v = (lo + hi) / 2
            fv, ok = f(mid_v)
            if ok:
                anchor = (mid_v, fv)
        if anchor is None:
            v_cur = float(getattr(o, param))
            fv, ok = f(v_cur)
            if ok:
                return result(v_cur, fv, False, "engine_error")
            raise ValueError(
                f"参数 {param} 在 [{lo}, {hi}] 与当前值 {v_cur} 均无法"
                "生成整版，请检查绑定 range 与测量组合")
        a, fa = (lo, lo_f[0]) if lo_f[1] else boundary(anchor, lo)
        b, fb = (hi, hi_f[0]) if hi_f[1] else boundary(anchor, hi)
    if abs(fa) <= tol_coord:                       # 目标恰达能力边界
        return result(a, fa, True, "tol")
    if abs(fb) <= tol_coord:
        return result(b, fb, True, "tol")
    if abs(fb - fa) <= tol_coord:                  # 全程位移 < 容差 = 无效果
        v, fv = (a, fa) if abs(fa) <= abs(fb) else (b, fb)
        return result(v, fv, False, "no_effect")
    if fa * fb > 0:                                # 无变号：目标超参数能力
        v, fv = (a, fa) if abs(fa) <= abs(fb) else (b, fb)
        return result(v, fv, False, "range_clamped")

    best_v, best_f = (a, fa) if abs(fa) <= abs(fb) else (b, fb)
    last = ""
    for _ in range(max_iter):
        if abs(b - a) <= tol_param:
            break
        denom = fb - fa
        c = ((a * fb - b * fa) / denom             # 弦截候选
             if abs(denom) > 1e-15 else (a + b) / 2)
        if not min(a, b) < c < max(a, b):          # 越括号 → 二分兜底
            c = (a + b) / 2
        fc, ok = f(c)
        if not ok:                                 # 内点失败 → 回退中点
            c = (a + b) / 2
            fc, ok = f(c)
            if not ok:
                return result(best_v, best_f, False, "engine_error")
        if abs(fc) <= tol_coord:
            return result(c, fc, True, "tol")
        if abs(fc) < abs(best_f):
            best_v, best_f = c, fc
        if fa * fc < 0:
            b, fb = c, fc
            if last == "b":                        # 连续同侧更新 → 阻尼对侧
                fa /= 2
            last = "b"
        else:
            a, fa = c, fc
            if last == "a":
                fb /= 2
            last = "a"

    converged = abs(best_f) <= tol_coord
    return result(best_v, best_f, converged,
                  "tol" if converged else "max_iter")
