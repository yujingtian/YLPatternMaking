"""web 层参数校验：构造期异常 -> 结构化 Issue + 跨选项前置条件。

与 PatternOptions.__post_init__ 的分工：后者是**逐字段硬校验**（非法即抛
异常，CLI/引擎口径）；本模块面向 web 入口，把构造异常转成可定位到参数的
结构化清单（前端逐参数高亮），并补上 FlowRunner 会静默跳过的**跨选项前置
条件**（CLAUDE.md「可选步骤」节：web 上显式报错比静默跳过更负责）。

错误归因采用逐键累加构造：按用户覆盖键顺序逐个套入默认值构造，失败的
键即错误来源（post_init 轻量，180 键全量构造在 ms 量级）。

一键修复（2026-09-29）：Issue.fixes 携带 0~2 条 Fix（param/value/label/
scope），前端 IssueStrip 渲染成按钮、点击改参并自动重生成。三档口径：
尺寸关系错误给「满足关系的最小替代值」（动态按当前输入算，不恢复默认
——用户基码可能离 FALLBACK 很远，恢复默认会跳款）；选项逐字段错误给
「恢复引擎默认」；跨选项依赖给「开依赖 / 关自身」双方向。运行期几何
失败的归因与修复见 flows/diagnose.py。
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum

from .measurements import Measurements
from .options import PatternOptions, option_default


@dataclass(frozen=True)
class Fix:
    """一条一键修复：把 param 改成 value。value 为 JSON 兼容值（引擎默认
    值经 norm_json 归一：Enum->str、sa dataclass->dict、tuple->list）；
    scope 告知前端走 setMeasurement 还是 setOption；label 为按钮中文。"""

    param: str
    value: object
    label: str
    scope: str = "options"   # "options" | "measurements"


@dataclass(frozen=True)
class Issue:
    """一条校验问题。param 为参数名（跨选项规则的触发方），group 为
    前端分组键（与 webapp schema 分组对齐，未知则 None）。"""

    param: str | None
    message: str
    group: str | None = None
    level: str = "error"   # error = 阻断生成；warning = 生成但提示
    fixes: tuple[Fix, ...] = ()   # 一键修复候选（0~2 条）


def norm_json(v):
    """值归一化：引擎侧值（Enum 实例 / sa dataclass / tuple）与 web JSON
    载荷值（str / dict / list）的比较口径。递归处理容器；标量原样
    （68 == 68.0、True == 1 由 Python 相等语义天然放行）。"""
    if isinstance(v, Enum):
        return norm_json(v.value)
    if is_dataclass(v) and not isinstance(v, type):
        return {f.name: norm_json(getattr(v, f.name)) for f in fields(v)}
    if isinstance(v, (tuple, list)):
        return [norm_json(x) for x in v]
    if isinstance(v, dict):
        return {k: norm_json(x) for k, x in v.items()}
    return v


# 归因用回退尺寸（常规女裤 165/68A，与 examples/size_female_165 一致）：
# 仅在用户尺寸自相矛盾时用来逐键试探归因，不影响用户数据。公开导出：
# flows/diagnose.py 的 touched 判定与本模块「必填键 <=0」修复共用。
FALLBACK_MEASUREMENTS = dict(waist=68, hip=91, knee=44, hem=34,
                             front_rise=25, back_rise=33, outseam=102,
                             thigh=58)

_FALLBACK_M = FALLBACK_MEASUREMENTS   # 旧名（模块内引用简写）


def _num(data: dict, key: str) -> float | None:
    """data[key] 数值化（非数返回 None，修复规则表据此跳过该方向）。"""
    v = data.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _measurement_fixes(key: str, data: dict) -> tuple[Fix, ...]:
    """构造期尺寸问题的一键修复：在原始 data 上重算触发关系（不解析消息
    文本，确定性强），按规则表产「满足关系的最小替代值」。margin 依据：
    臀腰差 3cm（女裤下限）、前后浪差 1cm（最小满足）、内长 75cm（牛仔
    常规 75~80 下限）；方向键带正数/下限守卫，越界则该方向不提供。"""
    v = _num(data, key)
    if v is None:
        return ()
    # 必填键非正 / thigh 为负：给常规值（thigh=0 即未录入）
    if key in _FALLBACK_M and (v <= 0 or (key == "thigh" and v < 0)):
        fb = 0 if key == "thigh" else _FALLBACK_M[key]
        label = ("清除为 0（未录入）" if key == "thigh"
                 else f"改为常规值 {fb:g}cm")
        return (Fix(key, fb, label, "measurements"),)
    # 关系型：按归因键给本方向替代值（另一头不动）
    if key == "hip":
        w = _num(data, "waist")
        if w is not None and v <= w:
            return (Fix(key, round(w + 3, 1), "臀围改为 腰围+3cm",
                        "measurements"),)
    if key == "waist":
        h = _num(data, "hip")
        if h is not None and h <= v and h - 3 > 0:
            return (Fix(key, round(h - 3, 1), "腰围改为 臀围−3cm",
                        "measurements"),)
    if key == "back_rise":
        fr = _num(data, "front_rise")
        if fr is not None and v <= fr:
            return (Fix(key, round(fr + 1, 1), "后浪改为 前浪+1cm",
                        "measurements"),)
    if key == "front_rise":
        br = _num(data, "back_rise")
        if br is not None and br <= v and br - 1 > 0:
            return (Fix(key, round(br - 1, 1), "前浪改为 后浪−1cm",
                        "measurements"),)
    if key == "outseam":
        fr = _num(data, "front_rise")
        if fr is not None and v <= fr:
            return (Fix(key, round(fr + 75, 1), "裤长改为 前浪+75cm（常规内长）",
                        "measurements"),)
    if key == "front_rise":
        # front_rise 归因到「浪长 > 裤长」时（上面 back_rise 分支未命中）：
        # 裤长 − 常规内长 75，下限 15 防荒谬小值
        os_ = _num(data, "outseam")
        if os_ is not None and os_ <= v and os_ - 75 >= 15:
            return (Fix(key, round(os_ - 75, 1), "前浪改为 裤长−75cm",
                        "measurements"),)
    return ()


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
                issues.append(Issue(key, str(e),
                                    fixes=_measurement_fixes(key, data)))
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

    # -- PatternOptions：整体先试，失败再逐键累加归因（键序无关）--
    # 关系型参数对（如 front/back_patch_shape=custom + custom_points/edges）
    # 只在合在一起时才可判定：整体构造成功即无键级问题（2026-08 修复）；
    # 整体失败走归因时第一遍失败键**延迟重试**——shape 在前的前缀里角点
    # 仍是默认空元组会假败，等全部键入列后带完整伙伴键重试一次，仍败才
    # 归因（2026-09-29 二遍式：fly_width 越界触发归因路径时不再连带误报
    # 两个 custom「得到 0 个」）。
    o_data = {k: v for k, v in options.items() if not k.startswith("_")}
    try:
        o = PatternOptions.from_dict(o_data)
    except (TypeError, ValueError):
        o = None
    if o is not None:
        issues.extend(cross_issues(m, o))
        return issues

    def report(key: str, e: Exception) -> None:
        """归因到 key 并回退默认（del 由调用方做）。"""
        if isinstance(e, TypeError):
            msg = str(e)
            if "unexpected keyword" in msg:
                issues.append(Issue(key, f"未知选项：{key}"))
                return
            issues.append(Issue(
                key, f"类型错误：{msg}",
                fixes=(Fix(key, norm_json(option_default(key)),
                           "恢复引擎默认"),)))
        else:
            issues.append(Issue(
                key, str(e),
                fixes=(Fix(key, norm_json(option_default(key)),
                           "恢复引擎默认"),)))

    acc: dict = {}
    deferred: list[tuple[str, object]] = []
    for key, val in o_data.items():
        acc[key] = val
        try:
            PatternOptions.from_dict(acc)
        except (TypeError, ValueError):
            del acc[key]                # 先不报：可能是伙伴键尚未入列
            deferred.append((key, val))

    for key, val in deferred:           # 二遍：完整上下文下重试，仍败才归因
        acc[key] = val
        try:
            PatternOptions.from_dict(acc)
        except (TypeError, ValueError) as e:
            report(key, e)
            del acc[key]                # 回退该键默认值，继续归因后续键

    try:
        o = PatternOptions.from_dict(acc)
    except (ValueError, TypeError):
        return issues                   # 键级回退后仍失败：错误已逐键记录

    issues.extend(cross_issues(m, o))
    return issues


def cross_issues(m: Measurements, o: PatternOptions) -> list[Issue]:
    """跨选项前置条件（FlowRunner 静默跳过的依赖关系，web 上显式报出）。
    依据：CLAUDE.md「可选步骤（开关驱动）」节 + 各选项 docstring。
    每条规则带双方向一键修复：开依赖（保特征）/ 关自身（弃特征）。"""
    issues: list[Issue] = []

    def need(param: str, message: str, group: str | None = None,
             level: str = "error",
             fixes: tuple[Fix, ...] = ()) -> None:
        issues.append(Issue(param, message, group, level, fixes))

    if (o.front_pocket_facing or o.front_pouch or o.watch_pocket) \
            and not o.front_pocket:
        # 三者都依赖主切口；逐个精确报
        if o.front_pocket_facing:
            need("front_pocket_facing",
                 "袋贴依赖前口袋主切口，请先开启 front_pocket",
                 fixes=(Fix("front_pocket", True, "开启前口袋主切口"),
                        Fix("front_pocket_facing", False, "关闭袋贴")))
        if o.front_pouch:
            need("front_pouch", "袋布依赖前口袋主切口，请先开启 front_pocket",
                 fixes=(Fix("front_pocket", True, "开启前口袋主切口"),
                        Fix("front_pouch", False, "关闭袋布")))
        if o.watch_pocket:
            need("watch_pocket", "小表袋依赖前口袋主切口，请先开启 front_pocket",
                 fixes=(Fix("front_pocket", True, "开启前口袋主切口"),
                        Fix("watch_pocket", False, "关闭小表袋")))
    if (o.watch_pocket and o.watch_pocket_mode == "facing_intersect"
            and not o.front_pocket_facing):
        # 修复不能回默认（默认即 facing_intersect 等于没改）、不能改
        # custom（需点/边数据会引新构造错误）——第二方向只能是关小表袋
        need("watch_pocket_mode",
             "小表袋相交模式额外依赖袋贴，请先开启 front_pocket_facing",
             fixes=(Fix("front_pocket_facing", True, "开启袋贴"),
                    Fix("watch_pocket", False, "关闭小表袋")))
    if o.back_patch and not o.back_yoke:
        need("back_patch", "后贴袋依赖后机头下口线定位，请先开启 back_yoke",
             fixes=(Fix("back_yoke", True, "开启后机头"),
                    Fix("back_patch", False, "关闭后贴袋")))
    if o.thigh_limit and m.thigh <= 0:
        need("thigh_limit", "毗围闭环依赖大腿围录入，请在基础测量填 thigh > 0",
             fixes=(Fix("thigh_limit", False, "关闭毗围闭环"),
                    Fix("thigh", 58, "录入常规大腿围 58cm", "measurements")))
    # fly/fly_separate 双真不再报 warning：引擎口径 fly_separate 优先生效，
    # web 端 fly_type 虚拟下拉已强制互斥（双真仅模板 toml 载入出现，下拉
    # 按 fly_separate 优先如实显示，2026-08 移除冗余提示）
    return issues
