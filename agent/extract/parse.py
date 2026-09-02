"""S1 描述解析（纯代码确定性解析，不走模型）——管线第一级。

- parse_describe(text) -> ParsedDescribe：数字正则 + 同义词典 + 尺码换算；
  只认显式数字（「腰围74」「29寸」「29码」），缺失即缺、绝不编数值
  （绝对 cm 照片永不贡献，A 表原则）。
- S2 响应解析（parse_model_json / sanitize）随实施顺序 ④ schema 白名单落地。

口径（A 表 + K8 初版）：
- 尺寸 8 键单位：显式单位优先（寸/英寸/inch → ×2.54 圆整 0.1）；无单位按各键
  英寸合理带判（腰围 29 → 29×2.54≈73.7），带外按 cm。
- 尺码换算：「29码 / W29 / 尺码29」→ size_label=29；描述无显式腰围时
  waist = round(label×2.54)（evidence 注换算式）。
- 同义词典命中 → hints（轴/开关倾向）；同轴多词命中取最早出现（长词优先），
  merge 阶段词典优先于照片（A 表：词典命中优先于照片）。

S2 响应解析（实施顺序 ④）：
- parse_model_json(text)：模型输出的 JSON 提取——围栏 / 散文包裹 / 花括号
  配平扫描三级容错，失败 raise ValueError（带原文尾部预览）。
- sanitize(raw) -> Observation：白名单（schema.MODEL_KEYS）过滤 + 枚举大小写
  归一 + 布尔多形态归一 + confidence 夹取 [0,1]；丢弃键进 dropped 供报告披露。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# -- 尺寸别名（键 -> 中英别名；扫描时长词优先防子串误配） ---------------------

_MEAS_ALIASES: dict[str, list[str]] = {
    "waist": ["腰围", "腰头", "腰身", "waist"],
    "hip": ["臀围", "坐围", "hip"],
    "knee": ["膝围", "膝盖围", "中裆围", "中档围", "knee"],
    "hem": ["脚口", "裤脚口", "裤脚", "下摆", "leg opening", "hem"],
    "front_rise": ["前浪", "前裆", "前档", "front rise", "front_rise", "frontrise"],
    "back_rise": ["后浪", "后裆", "后档", "back rise", "back_rise"],
    "outseam": ["外侧缝长", "外缝长", "裤全长", "裤长", "外长", "全长", "outseam"],
    "thigh": ["大腿围", "腿围", "thigh"],
}

# 键 -> 无单位时的英寸合理带（带内按英寸换算，带外按 cm）
_INCH_BANDS: dict[str, tuple[float, float]] = {
    "waist": (22, 44), "hip": (28, 48), "front_rise": (9, 16),
    "back_rise": (12, 19), "outseam": (28, 48), "knee": (11, 19),
    "hem": (11, 22), "thigh": (7, 12),
}

_INCH_UNITS = {"英寸", "寸", "inch", "in"}
_UNIT = r"(cm|厘米|公分|英寸|inch|in|寸)?"
_SEP = r"[\s:：=，,、约大概是为有]{0,8}"   # 别名与数字间的连接词（有界防跨句）

_MEAS_PAT: dict[str, re.Pattern] = {
    key: re.compile(
        rf"(?:{'|'.join(re.escape(a) for a in sorted(als, key=len, reverse=True))})"
        rf"{_SEP}(\d+(?:\.\d+)?)\s*{_UNIT}", re.I)
    for key, als in _MEAS_ALIASES.items()
}

# W29 / H91 拉丁尺寸式（值小=码号/英寸，值大=cm）
_LATIN_PAT = {
    "waist": re.compile(r"(?<![A-Za-z0-9])W\s*(\d{1,2})(?![0-9A-Za-z])", re.I),
    "hip": re.compile(r"(?<![A-Za-z0-9])H\s*(\d{1,2})(?![0-9A-Za-z])", re.I),
}
_LABEL_MAX = 45   # ≤45 视为码号/英寸量级；≥46 视为 cm

# 尺码标签（首个命中为准；码号合理带 20~48）
_SIZE_PATTERNS = [
    re.compile(r"尺码\s*(\d{1,2})"),
    re.compile(r"(\d{1,2})\s*码"),
    re.compile(r"size\s*[:：]?\s*(\d{1,2})", re.I),
]

# -- 同义词典 -> 轴/开关倾向（A 表；命中取最早出现、同位长词优先） -------------

_HINT_WORDS: dict[str, list[tuple[str, list[str]]]] = {
    "fit_level": [
        ("skinny", ["小脚", "铅笔", "紧身", "贴身", "skinny"]),
        ("slim", ["修身", "锥形", "微锥", "slim"]),
        ("regular", ["直筒", "直腿", "regular", "straight"]),
        ("loose", ["宽松", "妈妈裤", "妈妈款", "老爹裤", "老爹款", "mom", "dad",
                   "loose", "baggy"]),
        ("wide", ["阔腿", "大喇叭", "喇叭", "flare", "wide"]),
    ],
    "stretch": [
        ("high", ["弹力", "弹性", "高弹", "四面弹", "氨纶", "莱卡", "stretch",
                  "elastane", "spandex"]),
        ("none", ["无弹", "非弹", "不弹", "原浆", "硬挺", "raw denim", "rigid"]),
        ("low", ["微弹", "低弹", "常规"]),
    ],
    "waist_position": [
        ("high", ["超高腰", "高腰", "妈妈裤", "mom jeans", "high rise", "highrise",
                  "highwaist"]),
        ("mid_high", ["中高腰"]),
        ("mid", ["中腰", "正腰", "老爹裤", "dad jeans", "mid rise", "midrise"]),
        ("mid_low", ["中低腰"]),
        ("low", ["低腰", "露胯", "low rise", "lowrise"]),
    ],
    "gender": [
        ("male", ["男款", "男装", "男裤", "男士", "男生", "men", "male"]),
        ("female", ["女款", "女装", "女裤", "女士", "女生", "women", "female"]),
    ],
    "waistband_type": [
        ("curved", ["弯腰头", "弯曲腰头", "curved waistband", "curved"]),
        ("straight", ["直腰头", "直身腰头", "straight waistband"]),
    ],
    # 开关（on 值支持否定前缀；fly_separate 语义反向：连裁=off）
    "watch_pocket": [("on", ["小表袋", "表袋", "零钱袋", "硬币袋", "五袋",
                             "coin pocket", "watch pocket"])],
    "belt_loop": [("on", ["裤耳", "皮带袢", "belt loop", "beltloop"])],
    "back_dart": [("on", ["后省", "腰省", "省道", "收省"])],
    "front_patch": [("on", ["前贴袋", "前面贴袋"])],
    "fly_separate": [("off", ["连裁", "连门襟", "一体门襟"])],
}
# 「on」组支持否定前缀（无/没/非/不带 + 词 -> off）；「off」组不取反
_NEGATABLE = {"watch_pocket", "belt_loop", "back_dart", "front_patch"}
_NEG_TAIL = re.compile(r"(?:无|没有?|不带|非)$")

# 缩水率显式摘录（「缩水率3%」「缩水 3 个点」→ 0.03；≤1 的裸值视为已是小数）
_SHRINK_PAT = re.compile(
    r"缩水[率]?\s*[:：约大概是=]*\s*(\d+(?:\.\d+)?)\s*(%|％|个?点)?")

_FW_TRANS = str.maketrans("０１２３４５６７８９．：，＝", "0123456789.:,=")


@dataclass
class ParsedDescribe:
    """S1 解析产物：尺寸 + 逐键证据摘录 + 轴/开关倾向 + 码号。"""

    measurements: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)     # 尺寸键 -> 摘录/换算式
    hints: dict[str, str] = field(default_factory=dict)        # 轴/开关 -> 档位/on/off
    hint_words: dict[str, str] = field(default_factory=dict)   # 轴/开关 -> 命中词
    size_label: int | None = None
    shrinkage: float | None = None   # 显式缩水率（小数；无提及则 None 不发射）


def _to_cm(key: str, value: float, unit: str | None) -> tuple[float, str]:
    """按单位/英寸带换算成 cm，返回 (数值, evidence 附注)。"""
    if unit and unit.lower() in _INCH_UNITS:
        return round(value * 2.54, 1), f"（{value}{unit}×2.54）"
    if unit:
        return value, ""
    lo, hi = _INCH_BANDS.get(key, (0, 0))
    if lo <= value <= hi:
        return round(value * 2.54, 1), f"（无单位 {value} 落英寸带，×2.54）"
    return value, ""


def _scan_hints(lower: str) -> tuple[dict[str, str], dict[str, str]]:
    """同轴多组词命中取最早出现（同位长词优先）；on 组支持否定前缀。"""
    hints: dict[str, str] = {}
    words: dict[str, str] = {}
    for axis, groups in _HINT_WORDS.items():
        best: tuple[int, int, str, str] | None = None
        negatable = axis in _NEGATABLE
        for value, ws in groups:
            for w in ws:
                wl = w.lower()
                start = 0
                while True:
                    p = lower.find(wl, start)
                    if p < 0:
                        break
                    val = value
                    if negatable and value == "on" and \
                            _NEG_TAIL.search(lower[max(0, p - 2):p]):
                        val = "off"
                    cand = (p, -len(w), val, w)
                    if best is None or cand < best:
                        best = cand
                    start = p + 1
        if best is not None:
            hints[axis], words[axis] = best[2], best[3]
    return hints, words


def _scan_size_label(text: str) -> int | None:
    for pat in _SIZE_PATTERNS:
        m = pat.search(text)
        if m and 20 <= int(m.group(1)) <= 48:
            return int(m.group(1))
    return None


def parse_describe(text: str) -> ParsedDescribe:
    """解析一段文字描述：尺寸正则 + 同义词典 + 尺码换算（纯代码）。"""
    norm = text.translate(_FW_TRANS)
    lower = norm.lower()
    result = ParsedDescribe()

    for key, pat in _MEAS_PAT.items():
        m = pat.search(norm)
        if not m:
            continue
        value, unit = float(m.group(1)), m.group(2)
        cm, note = _to_cm(key, value, unit)
        result.measurements[key] = cm
        result.evidence[key] = f"描述摘录「{m.group(0).strip()}」{note}".rstrip()

    # W74 / H91 拉丁式补漏（别名未命中才查）
    for key, pat in _LATIN_PAT.items():
        if key in result.measurements:
            continue
        m = pat.search(norm)
        if not m:
            continue
        value = float(m.group(1))
        if value > _LABEL_MAX:               # 大数值直接是 cm
            result.measurements[key] = value
            result.evidence[key] = f"描述摘录「{m.group(0).strip()}」"
        elif key == "waist":                 # 小数值是码号，交给尺码换算
            result.size_label = result.size_label or int(value)

    result.size_label = result.size_label or _scan_size_label(norm)
    if result.size_label and "waist" not in result.measurements:
        label = result.size_label
        waist = float(round(label * 2.54))
        result.measurements["waist"] = waist
        result.evidence["waist"] = (
            f"尺码换算：{label}码×2.54≈{label * 2.54:.2f}→圆整{waist:.0f}")

    result.hints, result.hint_words = _scan_hints(lower)

    m = _SHRINK_PAT.search(norm)
    if m:
        raw = float(m.group(1))
        result.shrinkage = raw if (raw <= 1.0 and not m.group(2)) else raw / 100.0
    return result


# -- S2 响应解析（白名单/枚举值域来自 schema，勿在此重复维护） -----------------

_BOOL = "bool"


@dataclass
class ObservationEntry:
    """模型对单个键的观察：值 + 置信度 + 证据（推翻预判必须写视觉特征）。"""

    value: object
    confidence: float
    evidence: str


@dataclass
class Observation:
    """sanitize 后的模型观察（白名单内、值域归一）。"""

    entries: dict[str, ObservationEntry] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)   # 未知键/值域外值，报告披露


def parse_model_json(text: str) -> dict:
    """从模型输出提取 JSON：围栏 > 首个花括号配平扫描（容忍前后散文）。"""
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if fence:
        return json.loads(fence.group(1).strip())
    start = t.find("{")
    if start < 0:
        raise ValueError(f"模型输出无 JSON（尾部：…{t[-120:]!r}）")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(t)):
        ch = t[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(t[start:i + 1])
    raise ValueError(f"模型输出 JSON 未闭合（尾部：…{t[-120:]!r}）")


def _to_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        table = {"true": True, "false": False, "是": True, "否": False,
                 "有": True, "无": False, "on": True, "off": False,
                 "yes": True, "no": False}
        return table.get(value.strip().lower())
    return None


def sanitize(raw) -> Observation:
    """白名单过滤 + 值域/布尔归一 + confidence 夹取；未知键/值收集进 dropped。"""
    from .schema import MODEL_KEYS   # 局部 import 避免模块级环（schema 不依赖 parse）

    obs = Observation()
    if not isinstance(raw, dict):
        raise ValueError(f"模型输出不是 JSON 对象：{type(raw).__name__}")
    for key, val in raw.items():
        if key not in MODEL_KEYS:
            obs.dropped.append(str(key))
            continue
        domain = MODEL_KEYS[key]
        if isinstance(val, dict):
            value, conf, ev = val.get("value"), val.get("confidence", 0.5), \
                str(val.get("evidence") or "")
        else:
            value, conf, ev = val, 0.5, ""
        try:
            conf = min(1.0, max(0.0, float(conf)))
        except (TypeError, ValueError):
            conf = 0.5
        if domain == _BOOL:
            normalized = _to_bool(value)
            if normalized is None:
                obs.dropped.append(f"{key}={value!r}")
                continue
        else:
            normalized = str(value).strip().lower()
            if normalized not in domain:
                obs.dropped.append(f"{key}={value!r}")
                continue
        obs.entries[key] = ObservationEntry(normalized, conf, ev)
    return obs
