"""推码档差提取（层 3；.doc/工厂DXF逆向解析.md §6）。

逐码独立测量再相邻差分——**绕开跨码顶点漂移**（ET 放码每码重采样，
顶点索引跨码不可对应，见记忆 grading-pointcloud-cutter-counts）。

band 语义（params/sizerun.py）：码 i -> i+1 的步进取 **i+1 所属 band**，
自基码双向累加 v[i+1]=v[i]+step / v[i-1]=v[i]-step——即"进入某码的
过渡"一律取该码所在段的步进。故差分组 [d_p..d_q] 对应 band 码集
order[p+1..q+1]（首组再并入 order[0]，其无入过渡）。

差分基准 = 原始测量值（步进取中位数后圆整 0.01）：比在 0.1 圆整值上
差分多码累积漂移小一个量级（5028 实测 3XL 腰围 0.02 vs 0.1cm）；步长
均匀（段内逐键与中位数偏差 ≤ 容差）单 band，否则贪心分段，并在展开
复检漂移超线时告警（比对目标 = 报告显示的 0.1 圆整值）。
"""

from __future__ import annotations

from statistics import median
from typing import TYPE_CHECKING

from .model import size_sort_key

if TYPE_CHECKING:                          # 运行期零循环依赖（仅类型）
    from .measure import MeasuredSize

_KEYS = ("waist", "hip", "knee", "hem", "front_rise", "back_rise",
         "outseam", "thigh")
_TOL = 0.15          # cm：段内步进均匀性容差（5028 实测线性偏差 ≤0.03）
_DRIFT_WARN = 0.1    # cm：展开复检漂移告警线（信息性，不阻塞）


def grade_from_measurements(per_size: dict[str, "MeasuredSize"], base: str,
                            style: str, *, order: list[str] | None = None,
                            tol: float = _TOL) -> tuple[dict | None, list[str]]:
    """逐码测量 -> [size_run] 段 dict + 警告行。

    单码（无可差分相邻码）或基码不在码序 -> (None, [])，调用方跳过
    [size_run] 发射（退化单码模式）。步进取段内中位数（比均值抗单码
    离群），圆整 0.01。
    """
    if order is None:
        order = sorted(per_size, key=size_sort_key)
    if len(order) < 2 or base not in order:
        return None, []
    # 差分基准 = 原始测量值（漂移比 0.1 圆整值差分小一个量级）
    vals = {s: {k: float(per_size[s].values[k]) for k in _KEYS}
            for s in order}
    diffs = [{k: vals[order[i + 1]][k] - vals[order[i]][k] for k in _KEYS}
             for i in range(len(order) - 1)]
    groups = _segment(diffs, tol)
    bands: list[dict] = []
    for gi, (p, q) in enumerate(groups):
        sizes = list(order[p + 1:q + 2])
        if gi == 0:                        # 首段并入 order[0]（无入过渡）
            sizes.insert(0, order[0])
        band = {"sizes": sizes}
        for k in _KEYS:
            band[k] = round(median([diffs[i][k] for i in range(p, q + 1)]), 2)
        bands.append(band)
    size_run = {"base": base, "style": style, "order": list(order),
                "band": bands}
    warns: list[str] = []
    if len(bands) > 1:
        warns.append(f"档差跨码不均匀（容差 {tol}cm），分 {len(bands)} 段发射")
    warns.extend(_drift_warns(vals, order, size_run))
    return size_run, warns


def _segment(diffs: list[dict], tol: float) -> list[tuple[int, int]]:
    """贪心分段：切成段内（逐键相对中位数）均匀的连续段 [(p, q)] 闭区间。"""
    groups: list[tuple[int, int]] = []
    p = 0
    while p < len(diffs):
        q = p
        while q + 1 < len(diffs) and _uniform(diffs, p, q + 1, tol):
            q += 1
        groups.append((p, q))
        p = q + 1
    return groups


def _uniform(diffs: list[dict], p: int, q: int, tol: float) -> bool:
    """段 [p, q] 内每键步进与中位数偏差 ≤ tol。"""
    for k in _KEYS:
        ds = [diffs[i][k] for i in range(p, q + 1)]
        m = median(ds)
        if max(abs(d - m) for d in ds) > tol:
            return False
    return True


def _drift_warns(vals: dict[str, dict[str, float]], order: list[str],
                 size_run: dict) -> list[str]:
    """展开复检：按 sizerun._expand 同规则自基码双向累加，与逐码圆整值
    比对（只告警不阻塞——本期拟合测量不拟合形状）。"""
    band_of: dict[str, dict] = {}
    for b in size_run["band"]:
        for s in b["sizes"]:
            band_of[s] = b
    disp = {s: {k: round(v, 1) for k, v in vals[s].items()} for s in order}
    worst = 0.0
    bi = order.index(size_run["base"])
    cur = dict(vals[order[bi]])
    for k in range(bi, len(order) - 1):            # 大码方向
        step = band_of.get(order[k + 1], {})
        cur = {key: cur[key] + step.get(key, 0.0) for key in _KEYS}
        worst = max(worst, max(abs(cur[key] - disp[order[k + 1]][key])
                               for key in _KEYS))
    cur = dict(vals[order[bi]])
    for k in range(bi, 0, -1):                     # 小码方向
        step = band_of.get(order[k], {})
        cur = {key: cur[key] - step.get(key, 0.0) for key in _KEYS}
        worst = max(worst, max(abs(cur[key] - disp[order[k - 1]][key])
                               for key in _KEYS))
    if worst > _DRIFT_WARN:
        return [f"档差回读展开与逐码测量最大偏差 {worst:.2f}cm"
                f"（告警线 {_DRIFT_WARN}cm），建议检查分段/逐码几何"]
    return []
