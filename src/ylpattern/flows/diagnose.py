"""运行期引擎异常的参数归因（2026-09-29，web 校验报红二期）。

背景：build_issues 只覆盖构造期校验（post_init 逐字段 + 跨选项前置条件）；
flow 执行期的几何守卫（formulas/steps 里几十处 raise ValueError）此前在
后端裸抛 500、中文守卫消息全部丢失。本模块在失败发生后做**二分探测
归因**：把用户改过的键（touched = 值 ≠ 引擎默认）逐个回默认重跑
run_with_thigh_closure（只跑 closure 不跑导出），找出「回默认即可生成」
的罪魁键——复用 params/validate.py 逐键试探的既有哲学，通用覆盖全部
运行期守卫、无需逐点维护「守卫 -> 参数」映射表。

算法（纯 CPU、确定性、无随机——HTTP 与 Pyodide 双通道同输入必同输出，
tests/test_engine_glue.py 金标钉死的前提）：
1. solo 轮：单键回默认即成功 = 独罪魁，立即返回（最常见路径）；
2. 联合故障轮：无 solo 罪魁（多键单独无害、组合致死）时全量回退验证
   （默认配置是工作配置）+ 后向最小化（逐键试剔除，防把旁观键算成
   罪魁）；
3. 兜底：预算/探测上限耗尽或全默认仍失败（= 引擎 bug）->
   Issue(param=None)，保住引擎原始消息。

预算双闸：max_probes（探测次数）+ budget_s（墙钟，time.monotonic 每次
探测前查）。thigh_limit 开启时每探测最多 6 次 FULL_FLOW（thigh_max_iter），
Pyodide 慢于 CPython 数倍，故墙钟闸不可省；耗尽退化为兜底（消息仍在）。

修复口径：options 罪魁给「恢复默认」单按钮（值经 norm_json 过 JSON
兼容）；**measurements 罪魁不给修复按钮**——用户基码可能离
FALLBACK_MEASUREMENTS 很远，恢复默认会跳款，定位 + 引擎守卫消息
（如 hip.py:48「请减小后浪/内收量或加大臀围」）已含人话指引。
"""

from __future__ import annotations

import time

from ..params.measurements import Measurements
from ..params.options import PatternOptions, option_default
from ..params.validate import FALLBACK_MEASUREMENTS, Fix, Issue, norm_json
from .closure import run_with_thigh_closure


class _Abort(Exception):
    """探测预算（次数/墙钟）耗尽：中止探测，走兜底。"""


def _touched(measurements: dict, options: dict) -> list[tuple[str, str]]:
    """用户改过的键（(key, scope) 序）：值经 norm_json 归一后 ≠ 引擎默认
    （measurements 对 FALLBACK_MEASUREMENTS、options 对 dataclass 字段
    默认，未知选项键跳过——回默认无从谈起）。

    注意：web 载荷因产品层注入口袋族默认（PRODUCT_POCKET_KEYS，与引擎
    默认不同），touched 几乎恒非空——属预期，solo 语义不受影响（单键回
    引擎默认修不好别人引起的失败，不会被误判为罪魁）。"""
    m_data = {k: v for k, v in measurements.items()
              if not str(k).startswith("_")}
    o_data = {k: v for k, v in options.items() if not str(k).startswith("_")}
    touched_m = [k for k, v in m_data.items()
                 if k in FALLBACK_MEASUREMENTS
                 and norm_json(v) != norm_json(FALLBACK_MEASUREMENTS[k])]
    touched_o = [k for k, v in o_data.items()
                 if option_default(k) is not None
                 and norm_json(v) != norm_json(option_default(k))]
    return [(k, "measurements") for k in touched_m] \
        + [(k, "options") for k in touched_o]


def diagnose_runtime(measurements: dict, options: dict, message: str, *,
                     max_probes: int = 16, budget_s: float = 3.0
                     ) -> list[Issue]:
    """失败配置 -> 归因 Issue 清单（带一键修复）。message 为引擎原始异常
    文本（含 type 名），透传给用户并用于探测排序（消息点名的键优先——
    子串匹配、长键优先，仿 agent/extract/probe.py _attribute 语义；布尔
    开关最后探，防开关遮蔽叶子参数失败）。"""
    m_data = {k: v for k, v in measurements.items()
              if not str(k).startswith("_")}
    o_data = {k: v for k, v in options.items() if not str(k).startswith("_")}
    touched = _touched(measurements, options)
    named = sorted([k for k, _ in touched if k in message],
                   key=len, reverse=True)
    rest = [k for k, _ in touched if k not in named]

    def _is_switch(k: str) -> bool:
        """布尔开关（选项默认值为 bool；测量键恒数值不在此列）。"""
        return k not in m_data and isinstance(option_default(k), bool)

    # 开关遮蔽（2026-09-29）：回布尔开关 = 跳过整个特征执行，任何子参数
    # 的运行期失败都会被「关掉特征」修好（cb_dist=30 归因到 back_yoke
    # 而非 cb_dist 的假归因）——叶子参数（测量 + 非布尔选项）先探，
    # 开关最后探；真凶确是开关时叶子探测全败、仍能命中。
    order = (named
             + [k for k in rest if not _is_switch(k)]
             + [k for k in rest if _is_switch(k)])

    if not order:                     # 全默认仍失败 = 引擎 bug，不探测
        return [Issue(None, f"引擎生成失败：{message}")]

    probes = 0
    deadline = time.monotonic() + budget_s

    def try_with(reverted: frozenset[str]) -> bool:
        """reverted 键集回默认后能否生成（计数/预算共享一个闸）。

        测量键回退 = 换成 FALLBACK 值；选项键回退 = 删键（from_dict 缺键
        即取默认）。探测组合自身构造失败（fallback 与其余用户值关系冲突）
        按「没修好」计，不崩。"""
        nonlocal probes
        if probes >= max_probes or time.monotonic() >= deadline:
            raise _Abort
        probes += 1
        m2 = {k: FALLBACK_MEASUREMENTS[k] if k in reverted else v
              for k, v in m_data.items()}
        o2 = {k: v for k, v in o_data.items() if k not in reverted}
        try:
            run_with_thigh_closure(Measurements.from_dict(m2),
                                   PatternOptions.from_dict(o2))
            return True
        except Exception:
            return False

    def culprit_issue(k: str, solo: bool) -> Issue:
        scope = "measurements" if k in m_data else "options"
        suffix = "已定位：单独恢复默认后可生成" if solo \
            else "已定位：与其余参数组合导致（可逐个恢复默认排查）"
        fixes: tuple[Fix, ...] = ()
        if scope == "options":
            fixes = (Fix(k, norm_json(option_default(k)), "恢复默认"),)
        return Issue(k, f"{message}（{suffix}）", None, "error", fixes)

    # -- 1. solo：单键回默认即成功 = 独罪魁 --
    solo_cache: dict[str, bool] = {}
    for k in order:
        try:
            solo_cache[k] = try_with(frozenset({k}))
        except _Abort:
            return [Issue(None, f"引擎生成失败：{message}")]
        if solo_cache[k]:
            return [culprit_issue(k, solo=True)]

    # -- 2. 联合故障（无 solo 罪魁）：全量回退 + 后向最小化 --
    # 前向贪心在此场景失效（单键候选全走 solo 缓存 False、acc 永远空），
    # 改自顶向下：先验证「全部 touched 回默认」可生成（默认配置是工作
    # 配置——项目不变量），再逐键试剔除，剔除后仍成功则去过归因（防把
    # 旁观键算成罪魁）。全量回退仍失败 = 引擎 bug，走兜底。
    try:
        if not try_with(frozenset(order)):
            return [Issue(None, f"引擎生成失败：{message}")]
        acc = set(order)
        for j in order:
            if len(acc) == 1:
                break
            if try_with(frozenset(acc - {j})):
                acc.discard(j)
        return [culprit_issue(k, solo=False)
                for k in order if k in acc]
    except _Abort:
        return [Issue(None, f"引擎生成失败：{message}")]
