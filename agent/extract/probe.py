"""探针回喂（L0~L4）：引擎是最强判据——进程内试跑，失败逐级兜底。

阶梯（引擎默认开关全 False，故 L2 只回退数值键保留款式、L3 才关开关，
两级不坍缩）：
- L0 试跑（先 build_issues 静态构造，再 run_with_thigh_closure 真跑）；
- L1 错误归因（异常消息对候选键子串匹配，长键优先）→ 回退归因键重试
  ≤ max_refeed 轮；
- L2 数值键全量回退引擎默认（款式开关保留）；
- L3 可选开关全关（最朴素基线版：纯直筒无部件）；
- L4 仍失败 → 不阻断产出（报告披露 + header 注明「探针未通过」，
  CLI --draft 拒绝直出、退出码 2）。

依赖方向：agent → ylpattern（2026-09-03 边界：ylpattern 纯引擎、全部
LLM 代码在 agent）。本模块 import ylpattern.flows.closure（探针要纯内存
(m,o)→ctx，与 _cmd_draft 同一入口）；extract 包顶层不 import 本模块
（__init__ 惰性）。
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from ylpattern.flows.closure import run_with_thigh_closure
from ylpattern.params.measurements import Measurements
from ylpattern.params.options import PatternOptions
from .validate import build_issues, issue_keys

# 可选开关集合（L3 关闭对象；含 thigh_limit——毗围闭环也是可选步骤）
_SWITCH_KEYS = frozenset({
    "front_pocket", "front_pocket_facing", "front_pouch", "front_patch",
    "watch_pocket", "back_patch", "back_yoke", "back_dart", "belt_loop",
    "fly", "fly_separate", "thigh_limit",
})

# 归因时的测量键（异常消息可能点名尺寸）
_MEAS_KEYS = ("waist", "hip", "knee", "hem", "front_rise", "back_rise",
              "outseam", "thigh")


@dataclass
class ProbeOutcome:
    """探针结论：管线产物 header 与报告的探针段数据源。"""

    ok: bool
    stage: str                       # 达到的最深阶梯 L0~L4
    message: str                     # 最终一轮引擎消息 / 构造问题
    error_keys: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)   # 每轮一句（报告探针段）
    reverted: list[str] = field(default_factory=list)   # 被回退/降级的键
    ctx: object = None               # 成功时的 DraftContext（score 步输入）
    header: str = ""                 # 未通过时的产物 header 注记


def fallback_value(key: str):
    """选项键的引擎默认值（dataclasses 字段默认；factory 取调用值）。"""
    for f in dataclasses.fields(PatternOptions):
        if f.name == key:
            if f.default is not dataclasses.MISSING:
                return f.default
            return f.default_factory() if f.default_factory else None
    return None


def _clean(data: dict) -> dict:
    return {k: v for k, v in data.items() if not str(k).startswith("_")}


def _run_once(measurements: dict, options: dict):
    """静态构造 + 引擎真跑。返回 (ok, message, keys, ctx)。"""
    issues = build_issues(_clean(measurements), _clean(options))
    errors = [i for i in issues if i.level == "error"]
    if errors:
        msgs = "；".join(i.message for i in errors[:3])
        return False, f"构造失败：{msgs}", sorted(issue_keys(errors)), None
    try:
        m = Measurements.from_dict(_clean(measurements))
        o = PatternOptions.from_dict(_clean(options))
    except (TypeError, ValueError) as e:
        return False, f"构造失败：{e}", [], None
    try:
        ctx, msg = run_with_thigh_closure(m, o)
        return True, msg, [], ctx
    except Exception as e:   # 引擎期异常：归因交上层（消息可能点名参数键）
        return False, f"{type(e).__name__}: {e}", _attribute(str(e), options), \
            None


def _attribute(message: str, options: dict) -> list[str]:
    """异常消息对候选键子串匹配（长键优先，防 back_yoke 抢 yoke_cb_dist）。"""
    keys = [k for k in options if k in message]
    keys.sort(key=len, reverse=True)
    return [k for k in keys if not any(k != o and k in o for o in keys)]


def probe_loop(measurements: dict, options: dict,
               max_refeed: int = 2) -> ProbeOutcome:
    """L0~L4 状态机：返回最终结论（含成功 ctx 或未通过 header）。"""
    out = ProbeOutcome(False, "L4", "")
    opts = dict(options)
    reverted: list[str] = []

    def attempt(stage: str) -> bool:
        ok, msg, keys, ctx = _run_once(measurements, opts)
        out.message = msg
        out.error_keys = keys
        if ok:
            out.ok, out.ctx = True, ctx
            out.log.append(f"{stage} 通过：{msg}")
            return True
        out.log.append(f"{stage} 失败：{msg[:160]}")
        return False

    if attempt("L0"):
        out.stage = "L0"
        return out

    # L1：归因键回退重试（≤ max_refeed 轮，每轮重新归因累积）
    for i in range(1, max_refeed + 1):
        if not out.error_keys:
            break
        for k in out.error_keys:
            if k in opts and k not in reverted:
                opts.pop(k, None)   # 删键即回引擎默认（测量键不在 opts，天然跳过）
                reverted.append(k)
        if attempt(f"L1 第{i}轮"):
            out.stage, out.reverted = f"L1({i})", reverted
            return out

    # L2：数值键全量回退默认（款式开关保留）
    numeric = [k for k in opts if k not in _SWITCH_KEYS]
    for k in numeric:
        opts.pop(k, None)
    reverted.extend(numeric)
    if attempt("L2"):
        out.stage, out.reverted = "L2", reverted
        return out

    # L3：可选开关全关（基线直筒）
    switches = [k for k in opts if k in _SWITCH_KEYS]
    for k in switches:
        opts.pop(k, None)
    reverted.extend(switches)
    if attempt("L3"):
        out.stage, out.reverted = "L3", reverted
        return out

    out.stage, out.reverted = "L4", reverted
    out.header = (f"探针未通过（L4）：{out.message[:120]}；产物仅供人工核查，"
                  "--draft 拒绝直出")
    return out
