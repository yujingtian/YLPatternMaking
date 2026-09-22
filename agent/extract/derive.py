"""合并（merge）与查表派生（derive_all）——extract 的数值产出核心。

条目对应（.doc/参数预测/，无条目号的表值禁止进代码）：
- K2 前中内收预测.md：基准带（低 0~0.5 / 中低 0.5~1.0 / 中 1.0~1.5 / 中高
  1.5~2.5 / 高 2.5~3.5）取带中值 + 四维修正（体态/面料/性别/廓形，修正量取
  保守端，体态有臀腰差连续锚点才上插）+ clamp 硬上限 3.5；发射 ratio 记账、
  adjust 保持 0（2026-09-02 用户裁定：预测口径取代 k=0.2 系数口径）。
- K3 后中内收预测.md：X = 臀腰差连续插值（锚点 5→2.0 / 15→3.0 / 20→3.5 /
  25→4.5），d>25 先按 §3 封顶 4.0（余量移交育克），再叠加偏移（低/中低腰
  −0.5、高腰 +0.5、有弹 −0.5「降半档」），clamp [1.5, 5.0]（极限 5）。
  实际内收绝对值 = 臀腰高 H_v×X/15（引擎口径 options.py:138）。
- K4 前口袋和育克转移省预测.md：全局余量排除法 R=(H−W)/2（弹力款 ×0.75）＝
  ①前中 + ②后中 + ③袋口转省（0.8 中值/大差 1.0，极限 1.5）+ ④侧缝目标
  （3.5 中值/大差 4.75）+ ⑤育克兜底（连续算出 clamp [0,5]，常规带 2.0~5.0）；
  有育克默认无后腰省；缺额 <0.5 不开省、≤2.5 单省、>2.5 双省（宽=缺额/2）。
- 直裆深推导.md §三 Δ 矩阵（C 表）：rise_adjust 低 −2.75 / 中 +0.75 / 高
  +3.75 带中值，中低/中高取相邻带线性中点（−1.0 / +2.25）。
- 前后片臀围推导.md §四：DELTA_PRESETS 五档路由（options.py:42）。
- 落裆推导.md §2.2：crotch_drop / knee / hem_adjust 弹力档。
- H_v 估算：直裆深 = H×0.25 + rise_adjust（引擎 rise_ratio 0.25），臀围线 =
  立裆线上移直裆深/3（front_steps.draw_hip_line）→ H_v = 直裆深×2/3。

merge 三源裁决（A 表）：描述词典 > 数字锚点(预判) > 照片 override > 惯例先验；
照片推翻必须 confidence>0.5 且 evidence 非空；数字锚点轴（waist_position 等
由尺寸算出的）词典也不可推翻（B 表：数字优先）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .parse import Observation

# -- 来源枚举（报告口径：推测依据汇总表） ---------------------------------------

DESC, PHOTO, PREJ, TABLE, DERIVED, DEFAULT = "描述", "照片", "预判", "查表", "派生", "默认"


@dataclass
class KeyMeta:
    """单键溯源三元组 + 键名（extracted.toml 行尾注释与报告逐键表的来源）。"""

    key: str
    value: object
    source: str
    confidence: float
    evidence: str


@dataclass
class MergedView:
    """merge 产物：三组键各自的终值与溯源。"""

    axes: dict[str, KeyMeta]
    switches: dict[str, KeyMeta]
    enums: dict[str, KeyMeta]


# -- 数字锚点轴判定（词典/照片均不可推翻，B 表） -------------------------------

_ANCHOR_DEPS = {"waist_position": ("front_rise",),
                "body_shape": ("waist", "hip"),
                "fit_level": ("hem", "hip"),
                "gender": ("__label__",)}


def _anchored_axes(measurements: dict[str, float], size_label: int | None,
                   axis: str) -> bool:
    deps = _ANCHOR_DEPS.get(axis)
    if deps is None:
        return False
    if "__label__" in deps:
        return size_label is not None and size_label >= 30   # gender 码号惯例锚
    return all(k in measurements for k in deps)


def _accept_override(obs: Observation, key: str, baseline) -> bool:
    """照片推翻判定：白名单内 + 值不同 + confidence>0.5 + evidence 非空。"""
    e = obs.entries.get(key)
    return (e is not None and e.value != baseline and e.confidence > 0.5
            and e.evidence.strip() != "")


def merge(observation: Observation, measurements: dict[str, float],
          prejudged: dict[str, tuple[str, str]], priors: dict[str, bool],
          hints: dict[str, str], size_label: int | None = None) -> MergedView:
    """三源合并出轴/开关/枚举终值。优先级：描述词典 > 数字锚点 > 照片 > 惯例。"""
    from .schema import AXIS_KEYS, ENUM_DEFAULTS

    from .schema import _AXIS_FALLBACK

    axes: dict[str, KeyMeta] = {}
    for axis in AXIS_KEYS:
        base_val, base_ev = prejudged.get(axis, (None, None))
        src, conf = PREJ, 0.6
        if base_val is None:      # 无锚点轴走模板同款惯例回退（schema 同源）
            base_val, note = _AXIS_FALLBACK.get(axis, ("low", "缺省"))
            base_ev, conf = f"无锚点惯例（{note}）", 0.3
        ev = base_ev
        if _accept_override(observation, axis, base_val):
            src, conf, ev = PHOTO, observation.entries[axis].confidence, \
                observation.entries[axis].evidence
            base_val = observation.entries[axis].value
        hint = hints.get(axis)
        if hint and hint != base_val and not _anchored_axes(measurements,
                                                            size_label, axis):
            base_val, src, conf, ev = hint, DESC, 0.9, f"描述词「{hint}」"
        axes[axis] = KeyMeta(axis, base_val, src, conf, ev)

    switches: dict[str, KeyMeta] = {}
    for key, prior in priors.items():
        value, src, conf, ev = prior, PREJ, 0.5, "惯例先验（未见照片/描述反例）"
        if _accept_override(observation, key, prior):
            value = observation.entries[key].value
            src, conf, ev = PHOTO, observation.entries[key].confidence, \
                observation.entries[key].evidence
        hint = hints.get(key)
        if hint and (hint == "on") != bool(value):
            value = hint == "on"
            src, conf, ev = DESC, 0.9, f"描述词（{key} {hint}）"
        switches[key] = KeyMeta(key, value, src, conf, ev)

    enums: dict[str, KeyMeta] = {}
    for key, default in ENUM_DEFAULTS.items():
        value, src, conf, ev = default, DEFAULT, 0.4, "引擎默认"
        if key == "fit":
            fl = axes["fit_level"].value
            value = "loose" if fl == "wide" else fl
            src, conf, ev = DERIVED, 0.6, f"fit_level {fl} 轴映射（wide→loose）"
        if _accept_override(observation, key, value):
            value = observation.entries[key].value
            src, conf, ev = PHOTO, observation.entries[key].confidence, \
                observation.entries[key].evidence
        hint = hints.get(key)   # 词典优先于照片（A 表；与轴/开关同款，
        if hint and hint != value:   # 2026-09-21 会话改口轮依赖此路生效）
            value, src, conf, ev = hint, DESC, 0.9, f"描述词「{hint}」"
        enums[key] = KeyMeta(key, value, src, conf, ev)
    return MergedView(axes, switches, enums)


def enforce_dependencies(merged: MergedView) -> list[str]:
    """开关依赖链收口（引擎硬依赖 + K4 配套），就地改写；返回披露清单。"""
    notes: list[str] = []

    def force(key: str, value: bool, why: str) -> None:
        if key not in merged.switches:
            if not value:
                return   # 缺席即引擎默认 False（如 front_pouch 不进先验表）
            merged.switches[key] = KeyMeta(key, True, DERIVED, 0.8,
                                           f"{why}（依赖链强制）")
            notes.append(f"{key}=开：{why}")
            return
        meta = merged.switches[key]
        if meta.value != value:
            merged.switches[key] = KeyMeta(key, value, DERIVED, 0.8,
                                           f"{why}（依赖链强制）")
            notes.append(f"{key}={'开' if value else '关'}：{why}")

    if not merged.switches["front_pocket"].value:
        for k in ("front_pocket_facing", "front_pouch", "watch_pocket"):
            force(k, False, "front_pocket 主切口关闭")
    if merged.switches["watch_pocket"].value:
        force("front_pocket_facing", True, "小表袋配套包（引擎缺口实测绕行）")
    if merged.switches["back_patch"].value:
        force("back_yoke", True, "后贴袋依赖后机头育克底线定位")
    if merged.switches["fly_separate"].value:
        force("fly", True, "独立门襟与连裁门襟互斥，fly_separate 优先")
    return notes


# -- K2 前中内收 ----------------------------------------------------------------

_K2_BASE = {"low": 0.25, "mid_low": 0.75, "mid": 1.25, "mid_high": 2.0,
            "high": 3.0}   # 基准带中值（K2 第一步表）


def front_intake_abs(measurements: dict[str, float],
                     axes: dict[str, str]) -> tuple[float, str]:
    """K2：基准带中值 + 四维修正（保守端；体态有臀腰差连续锚点）→ clamp 3.5。"""
    band = axes.get("waist_position", "mid")
    base = _K2_BASE.get(band, 1.25)
    w, h = measurements.get("waist"), measurements.get("hip")
    d = h - w if (w is not None and h is not None) else None
    parts = [f"基准 {band} 带中值 {base}"]
    shape = axes.get("body_shape", "standard")
    if shape == "curvy":       # 沙漏 +0.5~1.0，按臀腰差超 25 的幅度上插
        t = 0.0 if d is None else min(1.0, max(0.0, (d - 25) / 5))
        mod = 0.5 + 0.5 * t
        parts.append(f"体态沙漏 +{mod}（d={d if d is not None else '未知'}）")
        total = base + mod
    elif shape == "straight":  # 平腹 +0.5
        parts.append("体态平腹 +0.5")
        total = base + 0.5
    else:
        total = base
    stretch = axes.get("stretch", "low")
    if stretch == "high":
        total -= 0.5
        parts.append("高弹 −0.5")
    elif stretch == "none":
        total += 0.2
        parts.append("无弹 +0.2")
    if axes.get("gender") == "male":
        total -= 0.5
        parts.append("男款 −0.5")
    fitl = axes.get("fit_level", "regular")
    if fitl == "skinny":
        total += 0.2
        parts.append("紧身 +0.2")
    elif fitl == "wide":
        total -= 0.2
        parts.append("阔腿 −0.2")
    total = min(3.5, max(0.0, total))
    return total, "K2 前中内收预测.md：" + "、".join(parts) + f"，clamp 3.5 → {total:.2f}"


def front_intake_ratio(measurements: dict[str, float],
                       axes: dict[str, str]) -> tuple[float | None, float, str]:
    """返回 (ratio|None, 绝对值, 依据)。ratio = 绝对值÷((H−W)/4)（记账层）。"""
    absev: float
    absev, ev = front_intake_abs(measurements, axes)
    w, h = measurements.get("waist"), measurements.get("hip")
    if w is None or h is None or h - w <= 2.0:
        return None, absev, ev + "；臀腰差过小/缺尺寸，ratio 回退引擎默认 0.2"
    ratio = absev / ((h - w) / 4)
    return ratio, absev, ev + f"；ratio = {absev:.2f}÷((H−W)/4) = {ratio:.3f}"


# -- rise_adjust / H_v 估算（C 表 Δ 矩阵 + 引擎几何） ---------------------------

_RISE_ADJUST = {"low": -2.75, "mid_low": -1.0, "mid": 0.75, "mid_high": 2.25,
                "high": 3.75}   # 低/中/高取 Δ 矩阵带中值，中低/中高取相邻带中点


def rise_adjust_for(axes: dict[str, str]) -> float:
    return _RISE_ADJUST.get(axes.get("waist_position", "mid"), 0.75)


def hip_waist_height_est(measurements: dict[str, float],
                         axes: dict[str, str]) -> float:
    """H_v 估算 = 直裆深×2/3（直裆深 = H×0.25 + rise_adjust；臀围线上移其 1/3）。"""
    hip = measurements.get("hip")
    if hip is None:
        return 15.0   # 名义臀腰距兜底（15:X 的 15）
    return (hip * 0.25 + rise_adjust_for(axes)) * 2.0 / 3.0


# -- K3 后中内收 ----------------------------------------------------------------

_K3_ANCHORS = ((5.0, 2.0), (15.0, 3.0), (20.0, 3.5), (25.0, 4.5))


def back_intake_x(measurements: dict[str, float],
                  axes: dict[str, str]) -> tuple[float, str]:
    """K3：X 连续插值 + 大差封顶移交育克 + 腰位/弹力偏移，clamp [1.5, 5.0]。"""
    w, h = measurements.get("waist"), measurements.get("hip")
    d = h - w if (w is not None and h is not None) else 17.5   # 缺尺寸按标准带
    dc = min(25.0, max(5.0, d))
    x = _K3_ANCHORS[0][1]
    for (x0, y0), (x1, y1) in zip(_K3_ANCHORS, _K3_ANCHORS[1:]):
        if dc <= x1:
            x = y0 + (dc - x0) * (y1 - y0) / (x1 - x0)
            break
    else:
        x = _K3_ANCHORS[-1][1]
    parts = [f"臀腰差 {d:.0f} 插值 X={x:.2f}"]
    if d > 25:
        x = min(x, 4.0)
        parts.append("大差 §3 封顶 4.0（余量移交育克）")
    band = axes.get("waist_position", "mid")
    if band in ("low", "mid_low"):
        x -= 0.5
        parts.append(f"{band}腰 −0.5")
    elif band == "high":
        x += 0.5
        parts.append("高腰提臀 +0.5")
    if axes.get("stretch") == "high":
        x -= 0.5
        parts.append("有弹降半档 −0.5")
    x = min(5.0, max(1.5, x))
    return x, "K3 后中内收预测.md：" + "、".join(parts) + f" → 15:{x:.2f}"


def back_intake_abs(measurements: dict[str, float],
                    axes: dict[str, str]) -> tuple[float, float, str]:
    """② 后中绝对内收 = H_v×X/15（引擎 back_center_intake 同口径）。"""
    x, ev = back_intake_x(measurements, axes)
    hv = hip_waist_height_est(measurements, axes)
    return hv * x / 15.0, x, ev + f"；绝对值 = H_v≈{hv:.2f}×{x:.2f}/15"


# -- K4 余量排除法 --------------------------------------------------------------

def pocket_dart_width(measurements: dict[str, float]) -> tuple[float, str]:
    """③ 袋口转省：常规 0.8 中值、大差（d≥20）靠上带 1.0（极限 1.5，K4 §1）。"""
    w, h = measurements.get("waist"), measurements.get("hip")
    if w is not None and h is not None and h - w >= 20:
        return 1.0, "K4 §1 袋口转省：臀腰差大靠上带 1.0（极限 1.5）"
    return 0.8, "K4 §1 袋口转省：常规中值 0.8"


def side_seam_target(measurements: dict[str, float]) -> tuple[float, str]:
    """④ 侧缝目标带：3~4 取 3.5；大差款（d>25）4.5~5 取 4.75（K4，结果量仅校核）。"""
    w, h = measurements.get("waist"), measurements.get("hip")
    if w is not None and h is not None and h - w > 25:
        return 4.75, "K4 ④ 侧缝目标：大差款 4.5~5 取 4.75（结果量，仅前向校核）"
    return 3.5, "K4 ④ 侧缝目标带 3~4 取 3.5（结果量，仅前向校核）"


def yoke_residual(r_total: float, c1: float, c2: float, c3: float,
                   c4: float) -> float:
    """⑤ 育克兜底缺额 = R − ①前中 − ②后中 − ③袋口 − ④侧缝（K4 终极公式）。"""
    return r_total - c1 - c2 - c3 - c4


@dataclass
class DartPlan:
    """K4 省道组决策：约克省载体（有育克 → 省口宽=⑤，提取时闭口转省）
    + 无育克缺额强制真缝纫省。"""

    r_total: float
    channels: dict[str, float]        # ①②③④ 各渠道绝对值
    yoke_takeup: float                # ⑤（clamp [0,5]，常规带 2~5 出带警示）
    yoke_note: str
    dart_on: bool
    dart_count: int
    dart_width: float
    evidence: str


def dart_balance(measurements: dict[str, float], axes: dict[str, str],
                 yoke_on: bool) -> DartPlan:
    """K4 全局余量排除法 → 育克/后腰省决策（发射 front_pocket_dart_width 与
    back_dart* 的唯一依据）。"""
    w, h = measurements.get("waist"), measurements.get("hip")
    r = (h - w) / 2 if (w is not None and h is not None) else 8.75
    if axes.get("stretch") == "high":
        r *= 0.75   # 弹力吸收（K4）
    c1, _ = front_intake_abs(measurements, axes)
    c2, _, _ = back_intake_abs(measurements, axes)
    c3, ev3 = pocket_dart_width(measurements)
    c4, ev4 = side_seam_target(measurements)
    residual = yoke_residual(r, c1, c2, c3, c4)
    channels = {"①前中": c1, "②后中": c2, "③袋口": c3, "④侧缝目标": c4}
    ev = (f"K4 余量排除法：R={r:.2f}"
          f"{'×0.75 弹力' if axes.get('stretch') == 'high' else ''}"
          f" − ①{c1:.2f} − ②{c2:.2f} − ③{c3:.2f} − ④{c4:.2f}"
          f" = ⑤ {residual:.2f}（{ev3}；{ev4}）")

    if yoke_on:
        takeup = min(5.0, max(0.0, residual))
        note = ""
        if residual > 5.0:
            note = (f"超育克带上限 5.0 溢出 {residual - 5.0:.2f}"
                    "（披露，评分步观测）")
        elif residual < 2.0:
            note = "低于常规带 2.0（浅育克，评分步观测侧缝）"
        # 约克省载体 = 整版后腰省三键（用户口径 2026-09-02）：省口宽 = ⑤ 全额，
        # 育克裁片提取时绕省尖旋转闭口完成转省（back_yoke_steps §3 /
        # yoke_flow §2.2）——成品无可见省道，K4「有育克默认无后腰省」指成品形态
        shortfall = takeup
        ev += (f"；有育克：⑤ 全额作约克省口 width={takeup:.2f}"
               f"（育克绕省尖旋转闭口转省）{('，' + note) if note else ''}")
    else:
        takeup = 0.0
        shortfall = max(0.0, residual)
        ev += "；无育克，缺额全部强制腰省"

    dart_on = shortfall >= 0.5
    if not dart_on:
        count, width = 0, 0.0
        ev += "；缺额 <0.5 不开省"
    elif yoke_on:
        # 引擎育克闭口仅支持 1 省（yoke_flow 多省回退无省提取），count 恒 1
        count, width = 1, shortfall
        ev += f"；单省 width={width:.2f}（约克省载体）"
    elif shortfall <= 2.5:
        count, width = 1, min(2.5, max(1.0, shortfall))
        ev += f"；单省 width={width:.2f}（缺额 clamp[1.0,2.5]）"
    else:
        count, width = 2, min(2.5, shortfall / 2)
        ev += f"；双省 width={width:.2f}（缺额/2）"
    return DartPlan(r, channels, takeup, note if yoke_on else "", dart_on,
                    count, width, ev)


# -- 其余框架键（C 表） ----------------------------------------------------------

def resolve_delta(axes: dict[str, str], measurements: dict[str, float]
                   ) -> tuple[float, str]:
    """DELTA_PRESETS 五档路由（options.py:42）+ K4 大差侧缝前移（clamp 2.0）。"""
    from ylpattern.params.options import DELTA_PRESETS

    if axes.get("gender") == "male":
        key = "men_straight"
    elif axes.get("body_shape") == "curvy":
        key = "women_curvy"
    elif axes.get("stretch") == "high":
        key = "high_stretch"
    elif axes.get("fit_level") in ("loose", "wide"):
        key = "loose_wide"
    else:
        key = "women_standard"
    value, label = DELTA_PRESETS[key]
    ev = f"DELTA_PRESETS[{key}]={value}（{label}；前后片臀围推导.md §四）"
    w, h = measurements.get("waist"), measurements.get("hip")
    if w is not None and h is not None and h - w > 25:
        value = min(2.0, value + 0.5)
        ev += f"；大差侧缝前移技巧 +0.5（clamp 2.0 引擎守卫）→ {value}"
    return value, ev


def curvy_waist_balance(axes: dict[str, str]) -> tuple[float, str]:
    """curvy 联动防倒挂（C 表）：waist_balance=0，skinny/slim 再 −0.5。"""
    if axes.get("body_shape") == "curvy" and axes.get("fit_level") in ("skinny",
                                                                      "slim"):
        return -0.5, "curvy 联动：waist_balance=−0.5（skinny/slim 防前后侧缝收量倒挂）"
    return 0.0, "curvy 联动：waist_balance=0（C 表）"


def stretch_adjusts(axes: dict[str, str]) -> tuple[float, float, float, str]:
    """(crotch_drop, knee, hem, 依据)：高弹 −0.35/0.75/0.75，宽松无弹 +0.25。"""
    if axes.get("stretch") == "high":
        return -0.35, 0.75, 0.75, "落裆推导.md §2.2：高弹 crotch −0.35、knee/hem 0.75"
    if axes.get("fit_level") in ("loose", "wide") and axes.get("stretch") == "none":
        return 0.25, 1.0, 1.0, "落裆推导.md §2.2：宽松重磅 crotch +0.25"
    return 0.0, 1.0, 1.0, "标准弹力档：crotch 0、knee/hem 1.0（引擎默认）"


def front_crotch_adjust_for(axes: dict[str, str]) -> tuple[float, str]:
    """前小裆修正：紧身 −0.5~−1.0、常规 −0.4~0（C 表，常规取 0 引擎默认）。"""
    fitl = axes.get("fit_level", "regular")
    table = {"skinny": -0.75, "slim": -0.4, "regular": 0.0, "loose": 0.0,
             "wide": 0.0}
    v = table.get(fitl, 0.0)
    return v, f"前小裆修正 fit={fitl} → {v}（紧身 −0.5~−1.0、常规 −0.4~0）"


# -- derive_all：发射键总装 ------------------------------------------------------
# 依赖链收口在内部执行（幂等；要拿披露清单的调用方先自行调 enforce_dependencies）。

_PART_MATRIX = (   # (部件, 对应开关)
    ("front_pocket", "front_pocket"), ("facing", "front_pocket_facing"),
    ("pouch", "front_pouch"), ("watch_pocket", "watch_pocket"),
    ("back_patch", "back_patch"), ("yoke", "back_yoke"),
    ("dart", "back_dart"), ("fly", "fly"), ("belt_loop", "belt_loop"),
    ("waistband", None),   # 无开关，恒发射
)


def derive_all(measurements: dict[str, float], merged: MergedView,
               size_label: int | None = None,
               shrinkage: float | None = None) -> dict[str, KeyMeta]:
    """轴+尺寸 → 查表派生全部发射键（87 键覆盖面内除尺寸/开关外的数值键）。

    返回 {引擎键: KeyMeta}；开关终值仍留在 merged.switches（emit 步发射），
    唯一例外：K4 缺额强制腰省会就地翻转 merged.switches["back_dart"]。
    """
    from .families import part_family

    enforce_dependencies(merged)
    axes = {k: m.value for k, m in merged.axes.items()}
    enums = {k: m.value for k, m in merged.enums.items()}
    switches = {k: m.value for k, m in merged.switches.items()}
    out: dict[str, KeyMeta] = {}

    def put(key: str, value, ev: str, conf: float = 0.6,
            source: str = TABLE) -> None:
        out[key] = KeyMeta(key, value, source, conf, ev)

    # ③ 形态枚举 7（merge 已含 fit 轴映射，原样透传；
    # front_pocket_mouth_depth 是 S2 伪轴，仅供 families 映射 mouth_bulge
    # 0.3/0.4/0.5，本身不是引擎键、不发射）
    for k, m in merged.enums.items():
        if k != "front_pocket_mouth_depth":
            out[k] = m

    # ④ 弯曲框架 9（front_intake_adjust 保持 0 不发射，微调位留人工）
    ratio, _absev, fev = front_intake_ratio(measurements, axes)
    if ratio is not None:
        put("front_intake_ratio", round(ratio, 3), fev)
    x, xev = back_intake_x(measurements, axes)
    put("back_intake", round(x, 2), xev)
    dv, dev = resolve_delta(axes, measurements)
    put("delta", dv, dev)
    wb, wev = curvy_waist_balance(axes)
    put("waist_balance", wb, wev)
    put("rise_adjust", rise_adjust_for(axes),
        f"直裆深推导.md §三 Δ 矩阵：{axes['waist_position']} 腰档（低/中/高取带中值，"
        "中低/中高取相邻带中点）")
    fca, fcaev = front_crotch_adjust_for(axes)
    put("front_crotch_adjust", fca, fcaev)
    cd, ka, ha, aev = stretch_adjusts(axes)
    put("crotch_drop_adjust", cd, aev)
    put("knee_adjust", ka, aev)
    put("hem_adjust", ha, aev)

    # K4 省道组：③ 袋口转省 → 前口袋族；缺额 → 翻转 back_dart 开关 + 省 族
    plan = dart_balance(measurements, axes, switches["back_yoke"])
    if switches["front_pocket"]:
        _, ev3 = pocket_dart_width(measurements)
        put("front_pocket_dart_width", plan.channels["③袋口"], ev3)
    if plan.dart_on:
        merged.switches["back_dart"] = KeyMeta(
            "back_dart", True, DERIVED, 0.7, plan.evidence)
        switches["back_dart"] = True   # 同步本地快照，dart 族随之下发
        put("back_dart_count", plan.dart_count,
            f"K4 余量排除法缺省决策：{plan.evidence}", source=DERIVED)
        put("back_dart_width", round(plan.dart_width, 2),
            f"K4 余量排除法：缺额 {plan.channels} 合计外的省口宽", source=DERIVED)

    # ⑤ 部件族调用矩阵（K4 省组键在上面，族内只补模板键）
    for part, switch in _PART_MATRIX:
        if switch is not None and not switches.get(switch):
            continue
        if part == "yoke":   # 育克深度证据附加 K4 ⑤ 兜底注记
            for k, (v, ev) in part_family(part, axes, enums,
                                          measurements).items():
                note = f"；K4 ⑤ 育克兜底 takeup≈{plan.yoke_takeup:.2f}"
                if plan.yoke_note:
                    note += f"（{plan.yoke_note}）"
                put(k, v, ev + (note if k == "back_yoke_cb_dist" else ""))
            continue
        for k, (v, ev) in part_family(part, axes, enums, measurements).items():
            put(k, v, ev)

    # ⑬ 条件键 4
    if size_label is not None:
        put("size_label", str(size_label), "描述尺码标签摘录", conf=0.9,
            source=DESC)
    if measurements.get("thigh"):
        put("thigh_limit", True, "thigh>0 → 开毗围闭环（规则）")
    if shrinkage:
        put("shrinkage_warp", shrinkage,
            "描述显式缩水率摘录（经=纬同率）", conf=0.9, source=DESC)
        put("shrinkage_weft", shrinkage,
            "描述显式缩水率摘录（经=纬同率）", conf=0.9, source=DESC)
    return out
