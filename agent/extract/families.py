"""部件参数族模板（G 表）——部件开关开启即全族发射，族内自洽。

数值权威：计划 G 表初版（v1 = examples 金标值 / 工业惯例 / 档位中值；K5
部件尺寸初版子规则 a/b/c/d 已上线（知识库 §五，2026-09-30），其余键待
收集→ 与引擎默认一致的键标注「引擎默认在带内」）。返回
{引擎键: (值, 依据)}，由 derive.derive_all 包成 KeyMeta(source=查表)。

例外（不经本表，由 K4 余量排除法直接产出）：
- front_pocket_dart_width（③ 袋口转省 0.8/1.0）
- back_dart_count / back_dart_width（缺额→省数/省宽）
- back_dart_length 的 10.5 模板值仅作 dart_on=False（S2 强制开开关而缺额
  不足）兜底；dart_on 时由 derive.dart_length_linked 随省宽联动（省角恒定）
- front_pocket_p1_dist 走 K5 四则（K5-d 照片比例主通道 → K5-b 腰弧预算
  clamp → K5-c 小表袋下界〔袋口宽随 K5-d 动态、过 G 表带 5.0~6.5 钳制〕
  → K5-a 腰围锚点插值兜底）；
  front_pocket_p2_drop / watch_pocket_width 亦有 K5-d 比例主通道
  （2026-10-01，兜底 = 腰位分档 / G 表 5.5；分母一律单侧腰宽），extra 由
  derive 注入。
"""

from __future__ import annotations

import math

# -- K5 部件尺寸初版子规则常量（知识库 §五，单一事实源；各族值改引用） -------

_FLY_W = 4.0            # 门襟顶边占腰弧宽（fly_width G 表同值）
_FACING_WAIST_W = 3.5   # 袋贴腰头端宽（facing 族同值）
_WATCH_SIDE = 2.0       # 小表袋配套包：离口袋侧边距离
_WATCH_WIDTH = 5.5      # 小表袋袋口宽（K5-d 无比例时的 G 表兜底值）
_WATCH_W_MIN = 5.0      # G 表带下限（浅小兜 5~6.5；K5-d 换算值钳制，2026-10-01）
_WATCH_W_MAX = 6.5      # G 表带上限
_WAISTBAND_W = 4.0      # 腰头宽（waistband 族同值；p2 锚 = 前浪 − 本值）
_P1_ANCHORS = ((64.3, 8.8), (74.0, 10.0))   # K5-a 插值锚（W→p1）
_P1_FLY_MARGIN = 1.0    # K5-b 门襟侧安全间隙
# K5-c 小表袋下界 2026-10-01 动态化（袋口宽随 K5-d 可变）：ceil0.1(
# _WATCH_SIDE + 袋口宽·cos8° + 0.5 − _FACING_WAIST_W)；袋口宽 5.5 时 = 4.5
# （即旧常数 _P1_WATCH_FLOOR，零漂移）

# 袋口弧深三档（款式判据手册 §二）。值 = 引擎 bulge，渲染真弧高 = 2×bulge
# （curves.arc_through 实测口径，2026-08-30 钉死）。档位按真弧高 cm 定标：
# 浅 1.5 / 标准 2.5 / 深 3.5，即 bulge 0.75/1.25/1.75。定标出处：工厂 DXF 实测
# 5015/5028 真弧高 3.36（深档带内，工厂DXF逆向解析.md 袋口形态行、
# test_reverse_gold_5015 断言 bulge=1.68）+ 2026-09-02 照片读数深月牙 3~4cm
# 同带；旧 0.3/0.4/0.5 渲染仅 0.6/0.8/1.0cm，比工厂/照片浅 3~4 倍（用户复核
# 发现）。标准档 2.5 为插值初版，待打版师金标校准。
_MOUTH_BULGE = {"shallow": 0.75, "standard": 1.25, "deep": 1.75}


def _watch_band(w: float) -> float:
    """K5-d 换算的袋口宽过 G 表带钳制（换算后照常过静态值域口径，
    2026-10-01）：实照读数偏小漏到 3.8cm 后补的防线。K5-c 动态下界与
    watch 族宽度都取钳后值，防两处消费漂移。"""
    return min(_WATCH_W_MAX, max(_WATCH_W_MIN, w))


def _back_patch_size(axes: dict[str, str]) -> tuple[float, float, str]:
    """贴袋 width/height：女档中值 13.5/14.0，男款放大 1.5（G 表）。"""
    if axes.get("gender") == "male":
        return 15.0, 15.5, "G 表男档（女档 13.5/14.0 放大 1.5）"
    return 13.5, 14.0, "G 表女档中值（width 13~14 / height 12~15）"


def part_family(part: str, axes: dict[str, str], enums: dict[str, str],
                measurements: dict[str, float], *,
                extra: dict | None = None) -> dict[str, tuple[object, str]]:
    """按部件名发射整族模板键（值, 依据）。part 见 derive_all 的调用矩阵。

    extra（derive 注入的 K5 上下文，缺省 None = 纯 G 表旧行为）：
    chord 前腰弦 | chord_back 后腰弦 | fly_sep/facing_on/watch_on 开关快照
    | ratio_p1 / ratio_bp / ratio_p2 / ratio_wpw K5-d 已采纳照片比例
    （conf>0.6 + 钳物理窗后，None = 未观测/低置信走兜底）| front_rise 前浪
    （p2 锚）| watch_w 小表袋宽 K5-d 换算值（derive 单点算出，K5-c 动态
    下界与 watch 族宽度共用）。
    """
    fam: dict[str, tuple[object, str]] = {}
    g = "G 表（部件参数族模板 v1，K5 待收集）"

    if part == "front_pocket":
        # p1 四则（知识库 §五）：K5-d 照片比例主通道（extra.ratio_p1 × 前腰
        # 弦）→ K5-b 腰弧预算 clamp（防袋贴×门襟重合，主/兜底两通道统一）
        # → K5-c 小表袋下界；无比例时 K5-a 腰围锚点插值兜底（2026-09-30
        # 固定 10.0 不随码自适应致 W=66 款重合，退役）
        ex = extra or {}
        chord, w = ex.get("chord"), measurements.get("waist")
        p1: float
        evs: list[str] = []
        ratio = ex.get("ratio_p1")
        if ratio is not None and chord is not None:
            p1 = round(ratio * chord, 1)
            evs.append(f"K5-d 照片比例主通道：比例 {ratio:.2f} × 前腰弦 "
                       f"{chord:.2f} = {p1:.1f}")
        elif w is not None:
            (wa0, p0), (wa1, p1h) = _P1_ANCHORS
            raw = p0 + (w - wa0) * (p1h - p0) / (wa1 - wa0)
            if w <= wa0:
                p1, note = p0, (f"W={w:g} 低于下锚 {wa0:g}，"
                                "取下锚（无实测锚，披露）")
            elif raw >= p1h:
                p1, note = p1h, (f"W={w:g} 超上锚 {wa1:g}，"
                                 "封顶上锚（无实测锚，披露）")
            else:
                p1 = round(raw, 1)
                note = (f"{p0:g} + (W{w:g}−{wa0:g})×{p1h - p0:g}÷{wa1 - wa0:g}"
                        f" = {p1:.1f}（锚点 {wa0:g}→{p0:g} / {wa1:g}→{p1h:g}）")
            evs.append(f"K5-a 腰围锚点插值：{note}")
        else:
            p1 = 10.0
            evs.append("K5-a：缺腰围锚，金标 example 值 10.0 兜底（披露）")
        facing_w = _FACING_WAIST_W if ex.get("facing_on") else 0.0
        bound = None
        if ex.get("fly_sep") and chord is not None:
            # K5-b：弦 = waist_front_target（弦 ≤ 腰弧实测，保守安全侧）；
            # floor 0.1（+1e-9 护浮点尘），下界冲突时 K5-c 胜出并披露
            bound = math.floor(
                (chord - _FLY_W - facing_w - _P1_FLY_MARGIN) * 10 + 1e-9) / 10
            if p1 > bound:
                p1 = bound
                evs.append(f"K5-b 腰弧预算 clamp：前腰弦 {chord:.2f} − "
                           f"fly_width {_FLY_W:g} − 袋贴 {facing_w:g} − 间隙 "
                           f"{_P1_FLY_MARGIN:g} → p1={p1:.1f}（防袋贴×门襟"
                           "重合，独立门襟才占腰弧）")
        # K5-c 小表袋下界（watch 开；2026-10-01 袋口宽动态化——K5-d 比例可
        # 改 watch_w，取 G 表带 5.0~6.5 钳后值，兜底 5.5 时 = 旧常数 4.5
        # 零漂移）；ceil0.1（−1e-9 护浮点尘）。必要非充分：充分性由探针
        # L0 兜底
        w_watch = ex.get("watch_w")
        if w_watch is None:
            w_watch = _WATCH_WIDTH
        else:
            w_watch = _watch_band(w_watch)
        p1_floor = math.ceil(
            (_WATCH_SIDE + w_watch * math.cos(math.radians(8.0)) + 0.5
             - facing_w) * 10 - 1e-9) / 10
        if ex.get("watch_on") and p1 < p1_floor:
            p1 = p1_floor
            evs.append(
                f"K5-c 小表袋下界：p1 抬至 {p1_floor:.1f}（s_fw ≥ 侧距 "
                f"{_WATCH_SIDE:g} + 袋口宽 {w_watch:g}·cos8° + 间隙 0.5 "
                "的必要条件；充分性由探针 L0 兜底）")
            if bound is not None and bound < p1_floor:
                evs.append(f"K5-b/K5-c 冲突：下界胜出（K5-b bound={bound:.1f}"
                           f" < {p1_floor:.1f}，可归因侧失败优于射线"
                           "空归因直掉 L2，披露）")
        fam["front_pocket_p1_dist"] = (p1, "；".join(evs))
        # p2：K5-d 照片比例主通道（2026-10-01，锚 = 前浪 − 腰头宽 = 照片可见
        # 的腰头下缘→裆底竖直空间）→ 腰位分档兜底：竖向空间 = 外缝弧臀围端
        # →腰侧，低腰档弧短（低腰喇叭实测仅 ~10.3），p2_drop 须小于弧长
        # （P2 主切口守卫，消息含键字面量；facing_side_w 越臀围线引擎已接
        # 大腿段外缝，2026-09-28 起无袋贴硬守卫）；分档带值：低腰 5.5（实测
        # 5.0~6.5 全过取中偏浅）/ 中低 6.5 / 中+ 7.5（金标 example 8.0 属
        # 高腰带）
        band = axes.get("waist_position", "mid")
        p2 = {"low": 5.5, "mid_low": 6.5}.get(band, 7.5)
        ratio_p2, fr = ex.get("ratio_p2"), measurements.get("front_rise")
        if ratio_p2 is not None and fr is not None:
            p2 = round(ratio_p2 * (fr - _WAISTBAND_W), 1)
            p2ev = (f"K5-d 照片比例主通道：比例 {ratio_p2:.2f} × 前浪有效高 "
                    f"{fr - _WAISTBAND_W:.1f}（前浪 {fr:g} − 腰头宽 "
                    f"{_WAISTBAND_W:g}）= {p2:.1f}（覆盖腰位分档兜底）")
        else:
            p2ev = f"{g}：腰位联动 {band} 档（低腰竖向空间小，袋口相应变浅）"
        fam["front_pocket_p2_drop"] = (p2, p2ev)
        fam["front_pocket_paring_n"] = (2.0, f"{g}：常规 1.5~2.0 上缘")
        mode = enums.get("front_pocket_mouth_mode", "bulge")
        if mode == "bulge":
            depth = enums.get("front_pocket_mouth_depth", "standard")
            fam["front_pocket_mouth_bulge"] = (
                _MOUTH_BULGE.get(depth, 1.25),
                f"{g}：弧深三档 {depth}（判据手册 §二 真弧高 浅1.5/标准2.5/"
                "深3.5cm，÷2 发射 bulge；工厂实测 3.36 见表头注释）")
            # arc_through 渲染弧顶弦位 = 0.375×bulge_at+0.3125（仅弦中段
            # [0.31,0.69]），0.6 渲染 ≈0.54 近中；5015 工厂实测最深点 0.39
            fam["front_pocket_mouth_bulge_at"] = (
                0.6, f"{g}：bulge_at 0.6（渲染弧顶弦位≈0.54 近中）")
        elif mode == "tangent":
            fam["front_pocket_mouth_h1"] = (8.0, f"{g}：tangent 柄长 8/3")
            fam["front_pocket_mouth_h2"] = (3.0, f"{g}：tangent 柄长 8/3")
        else:   # polyline
            fam["front_pocket_mouth_corners"] = (
                ((0.3, 2.0), (0.6, 3.0)), f"{g}：polyline 折点（按弦长缩放）")

    elif part == "facing":
        fam["front_pocket_facing_width"] = (_FACING_WAIST_W,
                                            f"{g}：引擎默认在带内")
        # 侧缝深度：注释带 5~7 是大码余量；小码 p2_drop+side_w 越外缝弧臀围端
        # 时引擎已接大腿段外缝继续量（2026-09-28 跨段量取，无硬边界），
        # 金标 examples/size_female_165 同量级用 3.5
        fam["front_pocket_facing_side_w"] = (
            3.5, f"{g}：金标 example 值（注释带 5~7 大码适用，越臀围线自动接大腿段外缝）")
        if enums.get("front_pocket_facing_mode") == "tangent":
            fam["front_pocket_facing_h1"] = (14.0, f"{g}：tangent 柄长 14/1")
            fam["front_pocket_facing_h2"] = (1.0, f"{g}：tangent 柄长 14/1")

    elif part == "pouch":
        fam["front_pouch_waist_safe"] = (6.0, f"{g}：腰缝安全内延 6")
        fam["front_pouch_side_safe"] = (10.0, f"{g}：侧缝安全垂深 10")
        # nodes/edges 走引擎默认底弧（与袋口形状同风格），报告标注，不发射

    elif part == "watch_pocket":
        # 顶部对齐口径（2026-09-02 实照核对，用户定标）：照片只能看到小表袋
        # 顶部（贴腰口位置 + 袋口宽），下半段由 facing_intersect 自动延伸
        # 入袋、藏住不可见——只需顶部一致，深度不管控。
        ex = extra or {}
        wv = _WATCH_WIDTH
        wev = f"{g}：浅小兜 5~6.5 取 5.5（实照核对，旧 7.0 偏大）"
        if (ex.get("watch_w") is not None and ex.get("ratio_wpw") is not None
                and ex.get("chord") is not None):
            # K5-d 照片比例主通道（2026-10-01）：小表袋袋口宽 ÷ 单侧前腰宽 ×
            # 前腰弦，覆盖 G 表 5.5；watch_w 由 derive 单点换算（K5-c 同值），
            # 换算值过 G 表带 5.0~6.5 钳制（K5-c 同取钳后值防漂）
            raw = ex["watch_w"]
            wv = _watch_band(raw)
            wev = (f"K5-d 照片比例主通道：比例 {ex['ratio_wpw']:.2f} × 前腰弦 "
                   f"{ex['chord']:.2f} = {raw:.1f}")
            if wv != raw:
                wev += (f" → G 表带 {_WATCH_W_MIN:g}~{_WATCH_W_MAX:g} 钳 "
                        f"{wv:.1f}（实照读数偏低防漏网）")
            wev += "（覆盖 G 表 5.5）"
        fam["watch_pocket_width"] = (wv, wev)
        fam["watch_pocket_taper"] = (0.2, f"{g}：两侧收 0.2")
        fam["watch_pocket_offset_from_top"] = (
            1.0, f"{g}：贴腰头下缘 ~1.0（实照核对，旧 3.0 顶部下沉过多）")
        fam["watch_pocket_offset_from_side"] = (
            _WATCH_SIDE, "小表袋配套包（引擎缺口实测 66–84 码全过）")
        fam["watch_pocket_rotate_deg"] = (8.0, f"{g}：顺时针倾 8°")

    elif part == "back_patch":
        w, hgt, sizev = _back_patch_size(axes)
        ex = extra or {}
        ratio_bp = ex.get("ratio_bp")
        chord_back = ex.get("chord_back")
        width_ev = f"{g}：{sizev}"
        if ratio_bp is not None and chord_back is not None:
            # K5-d 照片比例主通道（覆盖 G 表性别档）：袋口宽 ÷ 背面可见
            # 后腰宽 × 后腰弦（W/4 + balance + Σ后省口，derive 注入）
            w = round(ratio_bp * chord_back, 1)
            width_ev = (f"K5-d 照片比例主通道：比例 {ratio_bp:.2f} × 后腰弦 "
                        f"{chord_back:.2f} = {w:.1f}（覆盖 G 表性别档）")
        fam["back_patch_inset_x"] = (4.5, f"{g}：距后浪 4~5.5 中值")
        fam["back_patch_drop_y"] = (3.5, f"{g}：距约克底线 3~4.5 中值")
        fam["back_patch_rotate_deg"] = (3.5, f"{g}：平行约克线倾角")
        fam["back_patch_width"] = (w, width_ev)
        fam["back_patch_height"] = (hgt, f"{g}：{sizev}")
        shape = enums.get("back_patch_shape", "rectangle")
        if shape == "baker_shield":
            fam["back_patch_bottom_width"] = (
                round(0.85 * w, 1), f"{g}：盾形底宽 0.85×width")
            fam["back_patch_tip_depth"] = (2.25, f"{g}：盾形尖深 2~2.5 中值")
        elif shape == "angular":
            fam["back_patch_chamfer"] = (1.75, f"{g}：切角 1.5~2 中值")
        # rectangle/custom：底宽走引擎默认（0=底边同口宽）；custom 需人工点集

    elif part == "yoke":
        band = axes.get("waist_position", "mid")
        if band in ("low", "mid_low"):
            cb, side, ev = 4.5, 3.0, "低腰收窄 3~4 带（臀围线推导 §三约克建议）"
        elif band == "high":
            cb, side, ev = 6.5, 4.0, "高腰加宽 5~7 带（臀围线推导 §三约克建议）"
        else:
            cb, side, ev = 6.0, 3.5, f"{g}：基准 {band} 档"
        fam["back_yoke_cb_dist"] = (cb, ev)
        fam["back_yoke_side_dist"] = (side, ev)

    elif part == "dart":
        fam["back_dart_length"] = (10.5, f"{g}：省长 10.5")

    elif part == "fly":
        fam["fly_width"] = (_FLY_W, f"{g}：YKK 5# 门襟宽 3.5~4.2")
        fam["fly_length_ratio"] = (0.35, f"{g}：开深系数（引擎默认在带内）")
        fam["fly_length_base"] = (2.0, f"{g}：开深基值（引擎默认在带内）")
        fam["fly_corner_inset"] = (0.5, f"{g}：底角内收 0.5（R = W−本值）")

    elif part == "belt_loop":
        fam["belt_loop_width"] = (1.2, f"{g}：引擎默认（净宽 1.2）")
        fam["belt_loop_unit_length"] = (6.0, f"{g}：单根 6.0")
        fam["belt_loop_count"] = (5, f"{g}：5 根")
        fam["belt_loop_waste"] = (3.0, f"{g}：损耗 3.0")

    elif part == "waistband":
        fam["waistband_width"] = (_WAISTBAND_W,
                                  f"{g}：腰头宽默认 4.0（宽窄档 3.5/4.5 待照片判据）")

    return fam
