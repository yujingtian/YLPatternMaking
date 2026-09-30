"""调版映射节点：交卷后的口语调版反馈 -> 参数调整（2026-09-27）。

分工红线（用户口径 2026-09-26/27，.doc/python工程设计.md §10.9.2）：
- LLM = 意图理解 + 参数定位 + 方向/步幅（档位名 / ±1/±2 整数步），
  **永不输出绝对 cm**；代码 = 数值步进与钳位（resolve_adjust 纯函数）、
  白名单校验、状态累积（Session 账本重放）、幂等重跑（seed 通道注入）；
- 触发 = 交卷后每轮都调（ADJUST_TRIGGER，"off" 一键停用）；
- thinking 恒 off（数值类短调用，provider 踩坑口径：不吃轮次参数）；
- 零打扰：歧义最佳猜测 + note 披露，绝不反问；provider 未配置 /
  调用失败 / 解析失败一律空结果静默跳过（映射永不 503）。

键面/档位/步长/通道全部来自 params_meta.adjust_surface()（全参数自动
生成 + 精定标 + 虚键，漂移金标钉死与引擎同步）。本模块**不 import
agent.session**（session -> extract.parse 会成环）：history 由 converse
传入纯 dict 列表（[{turn,text,adjust}]）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .params_meta import (GROUP_ORDER, adjust_surface, default_view)
from .parse import parse_model_json

# -- 旋钮（口径见模块 docstring） ------------------------------------------------

ADJUST_TRIGGER = "always_after_deliver"   # "off" = 停用映射
ADJUST_THINKING = "off"                   # 数值类短调用关思维链
STEP_RANGE = (-2, 2)                      # 整数步幅带（放宽只动这里）

ADJUST_TABLE = adjust_surface()


# -- 产物结构 --------------------------------------------------------------------

@dataclass(frozen=True)
class AdjustEntry:
    """一条已解析调整：目标键（虚键已落到 target）+ 绝对值 + 溯源。"""

    key: str
    value: object
    evidence: str = ""


@dataclass(frozen=True)
class AdjustResult:
    """一轮映射产物：意图（action/target，2026-09-29 D1）+ 生效 entries +
    note 披露 + 丢弃原因清单。

    action：adjust（现状默认）/ recheck（定向复查——entries 必空、target
    = 部位组名）/ none（与版型无关）。解析失败默认 adjust（= 现状行为，
    天然回退）；旧事件缺键 from_dict 同样回 adjust。
    """

    entries: tuple[AdjustEntry, ...] = ()
    note: str = ""
    dropped: tuple[str, ...] = ()
    action: str = "adjust"
    target: str = ""

    def to_dict(self) -> dict:
        return {"entries": [{"key": e.key, "value": e.value,
                             "evidence": e.evidence}
                            for e in self.entries],
                "note": self.note,
                "dropped": list(self.dropped),
                "action": self.action,
                "target": self.target}

    @classmethod
    def from_dict(cls, d: dict) -> "AdjustResult":
        if not isinstance(d, dict):
            return cls()
        entries = tuple(
            AdjustEntry(str(e.get("key")), e.get("value"),
                        str(e.get("evidence") or ""))
            for e in (d.get("entries") or []) if isinstance(e, dict))
        action = str(d.get("action") or "adjust")
        if action not in ("adjust", "recheck", "none"):
            action = "adjust"
        return cls(entries, str(d.get("note") or ""),
                   tuple(str(x) for x in (d.get("dropped") or [])),
                   action, str(d.get("target") or ""))


# -- 视图与门控 ------------------------------------------------------------------

def adjust_view_from_payload(options: dict) -> dict:
    """delivery["options"] -> 映射面视图：默认值打底，payload 键覆写。

    probe 回退后的真实值快照（converse 存 deliver 事件 data["adjust_view"]，
    下轮映射的当前值/门控基线）。payload 缺的键 = 该轮未发射（部件关），
    用引擎默认兜底——门控键由 payload 开关行决定真假。
    """
    view = dict(default_view())
    view.update({k: v for k, v in (options or {}).items() if k in view})
    return view


def gate_pass(gate, view: dict) -> bool:
    """参数级 gate 判定（与 webschema.gate_on 同语义的 dict 版）：
    None = 恒过；str = 布尔开关键；dict = {param, values, requires, not}。"""
    if gate is None:
        return True
    if isinstance(gate, str):
        return bool(view.get(gate))
    if not all(view.get(k) for k in gate.get("requires", ())):
        return False
    if any(view.get(k) for k in gate.get("not", ())):
        return False
    if "param" not in gate:
        return True
    v = view.get(gate["param"])
    return v is not None and str(v) in gate["values"]


# -- 解析（纯函数） ---------------------------------------------------------------

def _current_level(spec, view: dict):
    """档位键当前档名：值匹配 levels；虚键按最近 level_values 反查。"""
    cur = view.get(spec.target or spec.key)
    if cur is None:
        cur = spec.default
    if spec.target:
        vals = spec.level_values
        return spec.levels[min(range(len(vals)),
                               key=lambda i: abs(float(vals[i]) - float(cur)))]
    if isinstance(cur, bool):
        return "on" if cur else "off"
    return str(cur)


def _apply_level(spec, level: str, target_key: str, ev: str):
    """档名 -> AdjustEntry（bool/int/枚举/虚键四型归一）。"""
    if level not in spec.levels:
        return f"档位名非法（{spec.key}）：{level!r}"
    if spec.target:                      # 虚键：档位 -> 绝对值（单通道落点）
        return AdjustEntry(target_key,
                           spec.level_values[spec.levels.index(level)], ev)
    if isinstance(spec.default, bool):
        return AdjustEntry(target_key, level == "on", ev)
    if isinstance(spec.default, int) and not isinstance(spec.default, bool):
        try:
            return AdjustEntry(target_key, int(level), ev)
        except ValueError:
            return f"档位名非法（{spec.key}）：{level!r}"
    return AdjustEntry(target_key, level, ev)


def resolve_adjust(raw: object, view: dict):
    """单条模型输出 -> AdjustEntry 或丢弃原因（str）。纯函数、永不抛。

    规则：表外/locked/gate 不过即丢；level 须 ∈ levels；step 须非零整数
    ∈ STEP_RANGE——ordinal 档位键沿 levels 移档（到头 = 已在最档丢弃）、
    数值键 clamp(current + step×step, lo, hi)（current 缺 / 值不变丢弃）、
    无序档位键（nominal）+ step 丢弃；虚键经 _apply_level 落绝对值。
    """
    if not isinstance(raw, dict):
        return "输出项非对象"
    key = raw.get("key")
    if not isinstance(key, str) or not key:
        return "缺 key"
    spec = ADJUST_TABLE.get(key)
    if spec is None:
        return f"表外键：{key}"
    if spec.locked:
        return f"键已锁定（映射停用）：{key}"
    if not gate_pass(spec.gate, view):
        return f"部件未开/形态不符：{key}"
    ev = str(raw.get("evidence") or "").strip() or "口语调版映射"
    target_key = spec.target or spec.key

    level = raw.get("level")
    if level is not None:
        return _apply_level(spec, str(level), target_key, ev)
    step = raw.get("step")
    if step is None:
        return f"缺 level/step：{key}"
    if isinstance(step, bool) or not isinstance(step, int):
        return f"步数须为整数：{step!r}"
    if step == 0 or not (STEP_RANGE[0] <= step <= STEP_RANGE[1]):
        return f"步数须 ±1 或 ±2：{step!r}"

    if spec.levels:                       # 档位键步进：仅 ordinal 接受
        if not spec.ordinal:
            return f"无序档位键不接受步进：{key}"
        cur = _current_level(spec, view)
        if cur is None or cur not in spec.levels:
            return f"当前档位缺失：{key}"
        idx = spec.levels.index(cur) + step
        if idx < 0 or idx >= len(spec.levels):
            return f"已在最档，不再步进：{key}"
        return _apply_level(spec, spec.levels[idx], target_key, ev)

    # 数值 override 键：定标步长 × 步数，钳位带内
    if not spec.step:
        return f"该键无步长定标：{key}"
    cur = view.get(spec.key)
    if isinstance(cur, bool) or not isinstance(cur, (int, float)):
        return f"当前值缺失或非数值：{key}"
    raw_v = min(max(cur + step * spec.step, spec.lo), spec.hi)
    if isinstance(spec.default, int) and not isinstance(spec.default, bool):
        val: object = int(round(raw_v))
    else:
        val = round(float(raw_v), 2)
    if val == cur:
        return f"已在钳位端点，值不变：{key}"
    return AdjustEntry(target_key, val, ev)


# -- prompt ----------------------------------------------------------------------

_PROMPT_HEAD = """你是牛仔裤打版参数映射器：把用户的口语调版反馈映射为参数调整。
规则：
0. 先判意图定 "action"：用户要求再看/复查/仔细看某部位（「再看看X」「X不对吧」「X再确认下」），但没说要怎么改 → "recheck"（此时 "adjustments" 必须为空数组，"target" 填复查部位组名：前口袋/后贴袋/腰头/育克后片/门襟/版型腰位，指不清部位或整版观感 → "兜底"）；方向性修改意图（太大/太小/太凸/太浅…要改）→ "adjust"；纯确认/寒暄/与版型无关 → "none"（adjustments 空）。action=recheck/none 时 note 禁止「暂不改动」式不作为表述——recheck 说明你要重点复查什么（例「我来重新细看后贴袋的形状与大小」），none 说明你理解到了什么。
1. 只允许使用【当前版参数】里列出的键，绝不发明键名。键已按部位分组；用户指部位不指参数时，在该部位组内选 1~3 个最相关键联动调整，并在 note 里说明动了哪些。
2. 档位键给 "level"（必须用列出的档名）；有序档位键和数值键可给 "step"（整数 ±1 或 ±2，沿当前值同向再进 N 步；用户重复强调 = 同向再加一步）；无序档位键不给 step。绝不输出厘米等绝对数值。
3. 相对词（"再浅一点""还是太凸"）对照【对话历史】消解——历史里列了每轮已应用的调整，只动与本次反馈相关的键。
4. 版面方位（方向词消解的唯一权威）：前片/后片均侧缝在左、前中/后中在右，Y 向上朝腰头——用户口中的"左/右/上/下"按此换算（如"向右凸"＝朝前中方向）。
5. 用户要求整体前后互换/侧缝前移（如"侧缝往前挪""前后片调换"）时，「前后片臀围调节量」与「腰围前后分配」两键同向同幅联动（两键同发，打版惯例臀腰同调），并在 note 里说明联动。
6. 整体松紧找「版型松紧」；弧线形状找各弧线键；腰围/浪长/裤长等尺寸数字不归你管（用户会自己报数）。
7. 部件未开启的键不在参数表里，不要建议开启部件。
8. 歧义时按最佳猜测执行并在 note 说明，绝不提问；与调版无关的反馈输出空 adjustments。
严格只输出一个 JSON 对象：
{"action": "adjust", "target": "", "adjustments": [{"key": "键名", "level": "档名"} 或 {"key": "键名", "step": -1}, "evidence": "用户原话依据"}], "note": "一句中文说明"}
（action=adjust 时 target 留空串；action=recheck/none 时 adjustments 为空数组）"""


def _label_of(key: str) -> str:
    spec = ADJUST_TABLE.get(key)
    if spec is not None:
        return spec.label
    for s in ADJUST_TABLE.values():      # 虚键落点（bulge）回指人话标签
        if s.target == key:
            return s.label
    return key


def _fmt_val(v) -> str:
    if isinstance(v, bool):
        return "开" if v else "关"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _render_history(history: list[dict]) -> str:
    lines: list[str] = []
    for h in history:
        if not isinstance(h, dict):
            continue
        t = f"第{h.get('turn', '?')}轮 用户：{str(h.get('text', ''))[:120]}"
        adj = h.get("adjust") or {}
        entries = adj.get("entries") or []
        if entries:
            t += "\n  已应用调整：" + "；".join(
                f"{_label_of(e.get('key'))}={_fmt_val(e.get('value'))}"
                for e in entries if isinstance(e, dict))
            if adj.get("note"):
                t += f"（note：{adj['note']}）"
        lines.append(t)
    return "\n".join(lines) if lines else "（无）"


def _render_surface(view: dict) -> str:
    """gate 通过且未 locked 的键按部位分组渲染（一行一键：当前值 + 调法）。"""
    out: list[str] = []
    for group in GROUP_ORDER:
        specs = [s for s in ADJUST_TABLE.values()
                 if s.group == group and not s.locked
                 and gate_pass(s.gate, view)]
        if not specs:
            continue
        out.append(f"〔{group}〕")
        for s in specs:
            cur = view.get(s.target or s.key, s.default)
            # 语义句（≠label 才附）：档位含义/方向语义是 LLM 选键选档的
            # 唯一依据——缺席时只能按英文词形瞎猜（tangent/polyline 事故根因）
            sem = f"；{s.semantics}" if s.semantics != s.label else ""
            if s.target:
                out.append(f"- {s.label}（{s.key}）：当前档 {_current_level(s, view)}；"
                           f"档位 {'/'.join(s.levels)}（有序，可 step）{sem}")
            elif s.levels:
                tail = (f"档位 {'/'.join(s.levels)}"
                        + ("（有序，可 step）" if s.ordinal else ""))
                out.append(f"- {s.label}（{s.key}）：当前 {_fmt_val(cur)}；{tail}{sem}")
            else:
                out.append(f"- {s.label}（{s.key}）：当前 {_fmt_val(cur)}；"
                           f"step 每步 {_fmt_val(s.step)}，"
                           f"范围 [{_fmt_val(s.lo)}, {_fmt_val(s.hi)}]{sem}")
    return "\n".join(out)


def build_adjust_prompt(history: list[dict], view: dict, text: str) -> str:
    """映射 prompt：规则 + 全史 + 当前版参数（gate 内键）+ 本轮反馈。"""
    return (_PROMPT_HEAD
            + "\n\n【对话历史】\n" + _render_history(history)
            + "\n\n【当前版参数】（只允许这些键）\n" + _render_surface(view)
            + f"\n\n【本轮反馈】\n{text.strip()}\n")


# -- 映射调用（永不抛） -----------------------------------------------------------

def map_adjustment(history: list[dict], view: dict, text: str, provider,
                   thinking: str | None = ADJUST_THINKING) -> AdjustResult:
    """一次映射调用；provider 缺 / 空文本 / 调用失败 / 解析失败 -> 空结果。

    同响应重复键后者胜（先者进 dropped 记因）；解析层丢弃逐条披露。
    """
    if provider is None or not (text or "").strip():
        return AdjustResult()
    prompt = build_adjust_prompt(history, view, text)
    try:
        raw = parse_model_json(provider.complete(prompt, (), thinking))
    except (ValueError, RuntimeError):
        # 映射失败不阻断（VLMError 也是 RuntimeError）：零打扰口径
        return AdjustResult()
    if not isinstance(raw, dict):
        return AdjustResult()
    # 意图层（2026-09-29 D1）：非法值一律回 adjust = 现状行为（天然回退）
    action = str(raw.get("action") or "adjust").strip() or "adjust"
    if action not in ("adjust", "recheck", "none"):
        action = "adjust"
    target = str(raw.get("target") or "").strip()
    items = raw.get("adjustments")
    if not isinstance(items, list):
        items = []
    note = str(raw.get("note") or "").strip()
    entries: list[AdjustEntry] = []
    dropped: list[str] = []
    seen: dict[str, int] = {}
    for item in items:
        r = resolve_adjust(item, view)
        if isinstance(r, str):
            dropped.append(r)
            continue
        if r.key in seen:                 # 同响应重复键：后者胜
            entries[seen[r.key]] = r
            dropped.append(f"重复键取后者：{r.key}")
            continue
        seen[r.key] = len(entries)
        entries.append(r)
    if action != "adjust" and entries:
        # recheck/none 时 adjustments 必空：多余项记 dropped 披露（口径 §3.1）
        dropped.extend(f"action={action} 忽略调整项：{e.key}" for e in entries)
        entries = []
    return AdjustResult(tuple(entries), note, tuple(dropped),
                        action=action, target=target)
