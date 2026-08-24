"""web 层参数校验：构造期异常 -> 结构化 Issue + 跨选项前置条件。

与 PatternOptions.__post_init__ 的分工：后者是**逐字段硬校验**（非法即抛
异常，CLI/引擎口径）；本模块面向 web 入口，把构造异常转成可定位到参数的
结构化清单（前端逐参数高亮），并补上 FlowRunner 会静默跳过的**跨选项前置
条件**（CLAUDE.md「可选步骤」节：web 上显式报错比静默跳过更负责）。

错误归因采用逐键累加构造：按用户覆盖键顺序逐个套入默认值构造，失败的
键即错误来源（post_init 轻量，180 键全量构造在 ms 量级）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .measurements import Measurements
from .options import PatternOptions


@dataclass(frozen=True)
class Issue:
    """一条校验问题。param 为参数名（跨选项规则的触发方），group 为
    前端分组键（与 webapp schema 分组对齐，未知则 None）。"""

    param: str | None
    message: str
    group: str | None = None
    level: str = "error"   # error = 阻断生成；warning = 生成但提示


# 归因用回退尺寸（常规女裤 165/68A，与 examples/size_female_165 一致）：
# 仅在用户尺寸自相矛盾时用来逐键试探归因，不影响用户数据。
_FALLBACK_M = dict(waist=68, hip=91, knee=44, hem=34,
                   front_rise=25, back_rise=33, outseam=102, thigh=58)


def _build_measurements(measurements: dict) -> tuple[Measurements | None,
                                                     list[Issue]]:
    """整体构造 Measurements；失败时逐键回退 _FALLBACK_M 试探归因
    （跨字段关系如臀围<=腰围会命中触发键，按传入顺序取首个）。"""
    data = {k: v for k, v in measurements.items() if not k.startswith("_")}
    issues: list[Issue] = []
    while True:
        try:
            return Measurements.from_dict(data), issues
        except TypeError as e:
            issues.append(Issue(None, f"尺寸单字段问题：{e}"))
            return None, issues
        except ValueError as e:
            for key in data:
                if data.get(key, _FALLBACK_M.get(key)) == _FALLBACK_M.get(key):
                    continue
                probe = dict(data)
                if key in _FALLBACK_M:
                    probe[key] = _FALLBACK_M[key]
                    try:
                        Measurements.from_dict(probe)
                    except (ValueError, TypeError):
                        continue
                issues.append(Issue(key, str(e)))
                if key in _FALLBACK_M:
                    data[key] = _FALLBACK_M[key]
                break
            else:                                   # 无键可归因，整体报出
                issues.append(Issue(None, str(e)))
                return None, issues


def build_issues(measurements: dict, options: dict) -> list[Issue]:
    """dict 形式尺寸 + 选项 -> 结构化问题清单（空列表 = 可构造）。"""
    issues: list[Issue] = []

    m, m_issues = _build_measurements(measurements)
    issues.extend(m_issues)
    if m is None:                       # 尺寸单缺字段/自相矛盾：先修尺寸
        return issues

    # -- PatternOptions：同口径逐键累加 --
    o_data: dict = {}
    for key, val in options.items():
        if key.startswith("_"):
            continue
        o_data[key] = val
        try:
            PatternOptions.from_dict(o_data)
        except TypeError as e:
            msg = str(e)
            if "unexpected keyword" in msg:
                issues.append(Issue(key, f"未知选项：{key}"))
            else:
                issues.append(Issue(key, f"类型错误：{msg}"))
            del o_data[key]
        except ValueError as e:
            issues.append(Issue(key, str(e)))
            del o_data[key]             # 回退该键默认值，继续归因后续键

    try:
        o = PatternOptions.from_dict(o_data)
    except (ValueError, TypeError):
        return issues                   # 键级回退后仍失败：错误已逐键记录

    issues.extend(cross_issues(m, o))
    return issues


def cross_issues(m: Measurements, o: PatternOptions) -> list[Issue]:
    """跨选项前置条件（FlowRunner 静默跳过的依赖关系，web 上显式报出）。
    依据：CLAUDE.md「可选步骤（开关驱动）」节 + 各选项 docstring。"""
    issues: list[Issue] = []

    def need(param: str, message: str, group: str | None = None,
             level: str = "error") -> None:
        issues.append(Issue(param, message, group, level))

    if (o.front_pocket_facing or o.front_pouch or o.watch_pocket) \
            and not o.front_pocket:
        # 三者都依赖主切口；逐个精确报
        if o.front_pocket_facing:
            need("front_pocket_facing", "袋贴依赖前口袋主切口，请先开启 front_pocket")
        if o.front_pouch:
            need("front_pouch", "袋布依赖前口袋主切口，请先开启 front_pocket")
        if o.watch_pocket:
            need("watch_pocket", "小表袋依赖前口袋主切口，请先开启 front_pocket")
    if (o.watch_pocket and o.watch_pocket_mode == "facing_intersect"
            and not o.front_pocket_facing):
        need("watch_pocket_mode",
             "小表袋相交模式额外依赖袋贴，请先开启 front_pocket_facing")
    if o.back_patch and not o.back_yoke:
        need("back_patch", "后贴袋依赖后机头下口线定位，请先开启 back_yoke")
    if o.thigh_limit and m.thigh <= 0:
        need("thigh_limit", "毗围闭环依赖大腿围录入，请在基础测量填 thigh > 0")
    if o.fly and o.fly_separate:
        need("fly_separate", "连裁/独立门襟互斥形态，fly_separate 优先生效（fly 忽略）",
             level="warning")
    return issues
