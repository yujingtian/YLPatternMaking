"""轴预判（B 表锚点：代码从核心尺寸算好档位，S2 视觉确认只做编辑）。

条目对应（.doc/参数预测/参数推测知识库.md）：
- waist_position：K1 直裆深预测.md 女表（≤20 低 / 20~23 中低 / 23~26 中 /
  26~29 中高 / ≥29 高）、男表（<23 / 23~25 / 26~28 / 28~30 / ≥31，男比女长 2~3）；
  先放码归一化 norm = front_rise − (码−基准)×0.75（女基准 27、男 31），
  码号未知不归一化、按女款处理（K1 边界约定）。带边界归上带（23→中、26→中高、
  29→高），女表 20 显式归低（≤20），男表 23 归中低（<23 为低）。
- gender / body_shape / fit_level / stretch：K8 轴锚点初版（金标校准中）。
  body_shape：臀腰差 ≥25 或 W/H≤0.75 → curvy；<18 → straight；其余 standard。
  fit_level：脚口/臀围比 skinny<0.45 / slim<0.50 / regular<0.56 / loose<0.65 /
  wide≥0.65（边界归上带，越界向内 clamp），脚口≥膝围直接 wide（喇叭特例）；
  无尺寸回落描述词。
  stretch：只认描述词（面料词无法从尺寸反推），缺省 low。

prior_switches：D 表部件惯例（模型只报偏离）。back_dart=False 依据 K4——
有育克时育克即巨型转移省，经典牛仔裤默认无后腰省。
"""

from __future__ import annotations

_CUTS_F = (20, 23, 26, 29)
_LABELS = ("low", "mid_low", "mid", "mid_high", "high")
_CUTS_M = (23, 26, 28, 31)
_CUTS_FIT = (0.45, 0.50, 0.56, 0.65)
_LABELS_FIT = ("skinny", "slim", "regular", "loose", "wide")


def _band(x: float, cuts: tuple, labels: tuple, first_inclusive: bool) -> str:
    """分带：低于首切点归最低带（首切点可含）；其余切点值归上带（K1 约定）。"""
    if x < cuts[0] or (first_inclusive and x <= cuts[0]):
        return labels[0]
    for cut, lab in zip(cuts[1:], labels[1:-1]):
        if x < cut:
            return lab
    return labels[-1]


def waist_position_band(front_rise: float, gender: str | None,
                        size_label: int | None) -> tuple[str, str]:
    """K1：前裆弧长 -> 腰位五带（先按码号放码归一化）。返回 (档位, 依据)。"""
    g = gender if gender in ("male", "female") else "female"  # 码号未知按女款
    base = 31 if g == "male" else 27
    if size_label is not None and 20 <= size_label <= 48:
        norm = front_rise - (size_label - base) * 0.75
        note = (f"（{size_label}码放码归一化 {front_rise}−({size_label}−{base})"
                f"×0.75={norm:.2f}）")
    else:
        norm = front_rise
        note = ""
    cuts = _CUTS_M if g == "male" else _CUTS_F
    band = _band(norm, cuts, _LABELS, first_inclusive=(g == "female"))
    return band, f"front_rise {front_rise}{note} → {band}（K1 直裆深预测.md {'男' if g == 'male' else '女'}表）"


def prejudge_axes(measurements: dict[str, float], hints: dict[str, str],
                  size_label: int | None = None) -> dict[str, tuple[str, str]]:
    """按 B 表锚点从核心尺寸预判各轴；返回 轴 -> (档位, 依据)。"""
    axes: dict[str, tuple[str, str]] = {}

    # -- gender：描述词 > 码号惯例（W30+ 倾向男）> 默认女款（K8 初版） --------
    hint_g = hints.get("gender")
    if hint_g:
        axes["gender"] = (hint_g, f"描述词「{hint_g}」（K8）")
    elif size_label is not None and size_label >= 30:
        axes["gender"] = ("male", f"尺码{size_label}≥30 惯例倾向男款（K8）")
    else:
        axes["gender"] = ("female", "未识别性别信号，默认女款（K8）")

    # -- waist_position：front_rise 锚点 > 描述词（K1）------------------------
    fr = measurements.get("front_rise")
    hint_wp = hints.get("waist_position")
    if fr is not None:
        band, ev = waist_position_band(fr, axes["gender"][0], size_label)
        if hint_wp and hint_wp != band:
            ev += f"；描述词倾向 {hint_wp} 不一致，数字锚点优先（B 表）"
        axes["waist_position"] = (band, ev)
    elif hint_wp:
        axes["waist_position"] = (hint_wp, f"描述词「{hint_wp}」（无 front_rise 锚点）")

    # -- body_shape：臀腰差 + W/H 双判据（K8 初版）----------------------------
    w, h = measurements.get("waist"), measurements.get("hip")
    if w is not None and h is not None:
        diff = h - w
        if diff >= 25 or w / h <= 0.75:
            shape = "curvy"
        elif diff < 18:
            shape = "straight"
        else:
            shape = "standard"
        axes["body_shape"] = (shape, f"臀腰差 {h}−{w}={diff:.0f}、W/H={w / h:.3f}"
                                     f" → {shape}（K8 初版）")

    # -- fit_level：脚口/臀围比 + 脚口≥膝围特例 > 描述词（K8 初版）-------------
    hem, hip = measurements.get("hem"), measurements.get("hip")
    knee = measurements.get("knee")
    if hem is not None and hip:
        ratio = hem / hip
        if knee is not None and hem >= knee:
            axes["fit_level"] = ("wide", f"脚口{hem}≥膝围{knee}（喇叭特例）"
                                         f" → wide（K8 初版）")
        else:
            band = _band(ratio, _CUTS_FIT, _LABELS_FIT, first_inclusive=False)
            axes["fit_level"] = (band, f"脚口{hem}÷臀围{hip}={ratio:.2f}"
                                       f" → {band}（K8 初版）")
    elif hints.get("fit_level"):
        axes["fit_level"] = (hints["fit_level"],
                             f"描述词「{hints['fit_level']}」（无脚口/臀围锚点）")

    # -- stretch：只认描述词，缺省 low（K8 初版）-------------------------------
    axes["stretch"] = (hints.get("stretch", "low"),
                       f"描述词「{hints.get('stretch', '')}」"
                       if hints.get("stretch") else "缺省 low（常规微弹默认）")
    return axes


def prior_switches() -> dict[str, bool]:
    """D 表部件惯例先验（牛仔裤工业惯例，模型只报偏离、推翻需 evidence）。

    front_pouch（袋布）不在先验表：内部件照片看不到、描述侧也无判据词，
    「没分析到就不发射」（用户口径 2026-09-02）——走引擎默认 False，待
    判据手册/描述词典有袋布条目后再入表。
    """
    return {
        "front_pocket": True,
        "front_pocket_facing": True,
        "watch_pocket": True,
        "back_patch": True,
        "back_yoke": True,
        "belt_loop": True,
        "fly": True,
        "fly_separate": True,     # 现代主流独立门襟；连裁需照片证据
        "front_patch": False,     # 前贴袋罕见，开启才出族
        "back_dart": False,       # K4 先验关；dart_balance 按 ⑤/缺额翻开（有育克
                                  # = 约克省载体，无育克 = 真缝纫省，derive.py）
    }
