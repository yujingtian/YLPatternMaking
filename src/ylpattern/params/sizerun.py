"""尺码表（推码 SizeRun）：多尺码订单的参数层展开。

推码方案（.claude/plans/lucky-dreaming-wilkinson.md 步 1）：一份订单录
多个尺码，逐码参数化重打版（每码用该码 Measurements 完整重跑整版）。
本模块只做参数表展开——档差累加是算术不是打版公式，**不 import
formulas**（「params 禁 import formulas」红线）。

两种形态（已拍板都支持，可混用）：
- **基码分段档差展开**：[[size_run.band]] 声明段内码序与 8 参数相邻码
  步进，自基码双向累加（v[i+1]=v[i]+step / v[i-1]=v[i]-step）；
- **逐码显式**：[size_run.sizes.X] 直接给定；子集键 = 单码特调覆盖
  展开值（显式优先），全 8 键且无 band = 纯显式形态。

展开约定：
- **码序 order**：显式 size_run.order > 自动（band.sizes 声明序串联 +
  显式键序追加，去重保首现）。字母码/"36L" 无需数值解析，**永不做
  数值猜测**；
- **步进归属**：码 i -> i+1 的步进取 **i+1 所属 band**（"32->33 跨段取
  33 所在大码段" = 工厂 "33 码起放大档" 习惯）；无 band 覆盖的码须显式
  补全，否则报缺参清单；
- **thigh 特例**：基码 thigh=0（未录入）时忽略一切 thigh 步进（全码 0，
  毗围不启用）；显式 thigh>0 可单码启用；
- 每码构造 Measurements **复用其全部交叉校验**，失败消息带码标签。

总开关：`[size_run] enabled = false` 整段失效（load_size_run 返回
None = 单码模式，免删段；缺省 true）。单双码共用一份尺寸单时只翻
这一个布尔值。

TOML 段示例见 examples/size_female_zhitong.toml 文末。
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from .measurements import Measurements
from .options import PatternOptions
from .sizefile import load_size_file

MEASURE_KEYS: tuple[str, ...] = ("waist", "hip", "knee", "hem", "front_rise",
                                 "back_rise", "outseam", "thigh")

_SPEC_KEYS = ("base", "style", "order", "band", "sizes", "enabled")


def _clean(d: dict) -> dict:
    """过滤 `_` 前缀备注键（与 Measurements.from_file 同口径）。"""
    return {k: v for k, v in d.items() if not k.startswith("_")}


def _enabled_of(spec: dict) -> bool:
    """[size_run].enabled 总开关：缺省 true；须为布尔（防 "false" 字符串恒真）。"""
    v = spec.get("enabled", True)
    if not isinstance(v, bool):
        raise ValueError(f"[size_run].enabled 须为布尔开关（true/false），"
                         f"得到 {v!r}")
    return v


def _as_float(value, where: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{where} 须为数值，得到 {value!r}") from None


@dataclass(frozen=True)
class SizeBand:
    """档差段：sizes = 段内码序（TOML 声明序），8 字段 = 相邻码步进 cm。"""
    sizes: tuple[str, ...]
    waist: float = 0.0
    hip: float = 0.0
    knee: float = 0.0
    hem: float = 0.0
    front_rise: float = 0.0
    back_rise: float = 0.0
    outseam: float = 0.0
    thigh: float = 0.0


@dataclass(frozen=True)
class SizeEntry:
    """单个尺码条目：码标签 + 该码完整尺寸单。"""
    label: str
    measurements: Measurements


@dataclass(frozen=True)
class SizeRun:
    """尺码表：按码序的条目序列 + 基码标签 + 订单号。

    base        基码（Sample Size，ET08 尺码栏默认选中码）；
    style_name  订单号（须 ASCII，进 DXF 头 Style Name / Grading Rule
                Table 两行，默认 "noname" = ET08 自身缺省口径）；
    entries     按码序（order）排列的 SizeEntry。
    """

    base: str
    style_name: str = "noname"
    entries: tuple[SizeEntry, ...] = ()

    def __post_init__(self) -> None:
        if not self.entries:
            raise ValueError("尺码表至少需要一个尺码条目")
        labels = self.labels
        if len(set(labels)) != len(labels):
            raise ValueError(f"码标签重复：{list(labels)}")
        if self.base not in labels:
            raise ValueError(f"基码 '{self.base}' 不在码序 {list(labels)} 中")
        if not self.style_name.isascii():
            raise ValueError(f"订单号 style_name 须为 ASCII（进 R12 DXF TEXT），"
                             f"得到 '{self.style_name}'")

    @property
    def labels(self) -> tuple[str, ...]:
        """码序标签（= entries 声明序）。"""
        return tuple(e.label for e in self.entries)

    def measurements(self, label: str) -> Measurements:
        """取指定码的完整尺寸单。"""
        for e in self.entries:
            if e.label == label:
                return e.measurements
        raise ValueError(f"尺码表中不存在码 '{label}'（现有：{list(self.labels)}）")

    def base_measurements(self) -> Measurements:
        return self.measurements(self.base)

    def options_for(self, label: str, o: PatternOptions) -> PatternOptions:
        """逐码选项：只改 size_label，其余约 150 选项全码共享——跨码唯一
        变量是 Measurements（"尺码表进、逐码重打版"路线的构造化保证）。"""
        if label not in self.labels:
            raise ValueError(f"尺码表中不存在码 '{label}'（现有：{list(self.labels)}）")
        return dataclasses.replace(o, size_label=label)

    @classmethod
    def from_spec(cls, base_m: Measurements, raw: dict, *,
                  fallback_base: str = "-") -> "SizeRun":
        """从尺寸单原始 dict（load_size_file 产物）的 [size_run] 段展开。

        base_m 为基码尺寸（[measurements] 段，调用方已加载）；
        fallback_base 为基码回退（options.size_label != "-" 时用，其次
        order[0]）。
        """
        section = raw.get("size_run")
        if not isinstance(section, dict):
            raise ValueError("尺寸单缺 [size_run] 段（单码模式请直接用 run）")
        spec = _clean(section)
        unknown = [k for k in spec if k not in _SPEC_KEYS]
        if unknown:
            raise ValueError(f"[size_run] 含未知键 {unknown}"
                             f"（可用：{list(_SPEC_KEYS)}）")
        _enabled_of(spec)      # 类型校验（开关值只影响 load_size_run 探测）
        bands = _bands_from(spec)
        explicit = _explicit_from(spec)
        order = _order_from(spec, bands, explicit)
        base = _base_from(spec, order, fallback_base)
        entries = _expand(base_m, order, base, bands, explicit)
        style = spec.get("style", "noname")
        if not isinstance(style, str) or not style:
            raise ValueError("[size_run].style 须为非空字符串订单号")
        return cls(base=base, style_name=style, entries=tuple(entries))

    @classmethod
    def from_file(cls, path: str, *,
                  fallback_base: str = "-") -> "SizeRun":
        run = load_size_run(path, fallback_base=fallback_base)
        if run is None:
            raise ValueError(f"尺寸单 '{path}' 缺 [size_run] 段")
        return run


def _bands_from(spec: dict) -> list[SizeBand]:
    """解析 [[size_run.band]] 档差段列表（含跨段/段内重复码检查）。"""
    raw_bands = spec.get("band", [])
    if not isinstance(raw_bands, list):
        raise ValueError("[size_run].band 须为数组（[[size_run.band]]）")
    bands: list[SizeBand] = []
    seen: dict[str, int] = {}
    for i, d in enumerate(raw_bands):
        d = _clean(d)
        sizes = d.pop("sizes")
        if (not isinstance(sizes, list) or not sizes
                or not all(isinstance(s, str) and s for s in sizes)):
            raise ValueError(f"第 {i + 1} 个档差段 sizes 须为非空字符串数组")
        if len(set(sizes)) != len(sizes):
            raise ValueError(f"第 {i + 1} 个档差段 sizes 内部存在重复码：{sizes}")
        for s in sizes:
            if s in seen:
                raise ValueError(f"码 '{s}' 在第 {seen[s]} 与第 {i + 1} 个"
                                 "档差段中重复（一码只能属于一个段）")
            seen[s] = i + 1
        unknown = [k for k in d if k not in MEASURE_KEYS]
        if unknown:
            raise ValueError(f"第 {i + 1} 个档差段含未知参数 {unknown}"
                             f"（可用：{list(MEASURE_KEYS)}）")
        bands.append(SizeBand(
            sizes=tuple(sizes),
            **{k: _as_float(v, f"第 {i + 1} 个档差段 {k}") for k, v in d.items()}))
    return bands


def _explicit_from(spec: dict) -> dict[str, dict[str, float]]:
    """解析 [size_run.sizes.X] 逐码显式参数（子集键 = 覆盖展开值）。"""
    raw_sizes = spec.get("sizes", {})
    if not isinstance(raw_sizes, dict):
        raise ValueError("[size_run].sizes 须为表（[size_run.sizes.X]）")
    out: dict[str, dict[str, float]] = {}
    for label, d in raw_sizes.items():
        d = _clean(d)
        unknown = [k for k in d if k not in MEASURE_KEYS]
        if unknown:
            raise ValueError(f"码 '{label}' 显式参数含未知键 {unknown}"
                             f"（可用：{list(MEASURE_KEYS)}）")
        out[label] = {k: _as_float(v, f"码 '{label}' 显式参数 {k}")
                      for k, v in d.items()}
    return out


def _order_from(spec: dict, bands: list[SizeBand],
                explicit: dict[str, dict[str, float]]) -> list[str]:
    """码序：显式 order > 自动（band.sizes 声明序串联 + 显式键序追加，
    去重保首现）。显式 order 须覆盖 band ∪ 显式键全集（缺失列出）。"""
    if "order" in spec:
        order = spec["order"]
        if (not isinstance(order, list) or not order
                or not all(isinstance(s, str) and s for s in order)):
            raise ValueError("[size_run].order 须为非空字符串数组")
        dup = sorted({s for s in order if order.count(s) > 1})
        if dup:
            raise ValueError(f"码序 order 存在重复码：{dup}")
        known: set[str] = set()
        for b in bands:
            known.update(b.sizes)
        known.update(explicit)
        missing = [s for s in known if s not in order]
        if missing:
            raise ValueError(f"码序 order 缺少以下尺码：{missing}"
                             "（档差段与显式条目中的码都必须列入）")
        return list(order)
    order: list[str] = []
    for b in bands:
        for s in b.sizes:
            if s not in order:
                order.append(s)
    for label in explicit:
        if label not in order:
            order.append(label)
    if not order:
        raise ValueError("尺码表码序为空：需要 order、档差段或显式尺码三者之一")
    return order


def _base_from(spec: dict, order: list[str], fallback_base: str) -> str:
    """基码：size_run.base > fallback_base（options.size_label 已录入）>
    order[0]；不在码序抛错。"""
    base = spec.get("base")
    if base is not None and not isinstance(base, str):
        raise ValueError("[size_run].base 须为字符串码标签")
    if base in (None, "", "-"):
        base = fallback_base if fallback_base not in ("", "-") else None
    if base is None:
        base = order[0]
    if base not in order:
        raise ValueError(f"基码 '{base}' 不在码序 {order} 中")
    return base


def _expand(base_m: Measurements, order: list[str], base: str,
            bands: list[SizeBand],
            explicit: dict[str, dict[str, float]]) -> list[SizeEntry]:
    """双向累加展开 + thigh 特例 + 显式覆盖，逐码构造 Measurements。

    步进归属：相邻码 i -> i+1 的步进取 i+1 所属 band（无 band 覆盖 = 0，
    该码须显式补全，否则报缺参清单）。
    """
    band_of: dict[str, SizeBand] = {}
    for b in bands:
        for s in b.sizes:
            band_of[s] = b
    vals: dict[str, dict[str, float]] = {
        base: {k: float(getattr(base_m, k)) for k in MEASURE_KEYS}}
    bi = order.index(base)
    for k in range(bi, len(order) - 1):            # 自基码向前（大码方向）
        cur, nxt = order[k], order[k + 1]
        b = band_of.get(nxt)
        vals[nxt] = {key: vals[cur][key] + (getattr(b, key, 0.0) if b else 0.0)
                     for key in MEASURE_KEYS}
    for k in range(bi, 0, -1):                     # 自基码向后（小码方向）
        prv, cur = order[k - 1], order[k]
        b = band_of.get(cur)
        vals[prv] = {key: vals[cur][key] - (getattr(b, key, 0.0) if b else 0.0)
                     for key in MEASURE_KEYS}
    if base_m.thigh == 0:
        # thigh 特例：基码未录入时忽略一切 thigh 步进（全码 0，毗围不启用）
        for v in vals.values():
            v["thigh"] = 0.0
    orphans = [s for s in order
               if s != base and s not in band_of and not explicit.get(s)]
    if orphans:
        raise ValueError(f"以下尺码既不在任何档差段也无显式参数（无法确定"
                         f"尺寸，请补 band 覆盖或 [size_run.sizes.X]）：{orphans}")
    for label, kv in explicit.items():             # 显式覆盖（优先于展开值）
        vals[label].update(kv)
    entries = []
    for label in order:
        try:
            m = Measurements(**vals[label])
        except (TypeError, ValueError) as e:
            raise ValueError(f"码 '{label}'：{e}") from e
        entries.append(SizeEntry(label=label, measurements=m))
    return entries


def load_size_run(path: str, *,
                  fallback_base: str = "-") -> SizeRun | None:
    """读取尺寸单文件构建尺码表；无 [size_run] 段或 enabled = false 时
    返回 None（cli/api 单码/多码模式探测口）。fallback_base 传
    options.size_label 以启用基码回退。"""
    raw = load_size_file(path)
    section = raw.get("size_run")
    if not isinstance(section, dict) or not _enabled_of(section):
        return None
    m_sec = raw.get("measurements")
    if not isinstance(m_sec, dict):
        raise ValueError(f"尺寸单 '{path}' 缺 [measurements] 段（基码尺寸）")
    fields = {k: v for k, v in m_sec.items() if not k.startswith("_")}
    base_m = Measurements(**fields)
    return SizeRun.from_spec(base_m, raw, fallback_base=fallback_base)
