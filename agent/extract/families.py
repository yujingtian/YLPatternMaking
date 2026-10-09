"""部件参数族模板（G 表）——部件开关开启即全族发射，族内自洽。

数值权威：计划 G 表初版（v1 = examples 金标值 / 工业惯例 / 档位中值；K5
部件尺寸初版子规则 a/b/c/d 已上线（知识库 §五，2026-09-30），其余键待
收集→ 与引擎默认一致的键标注「引擎默认在带内」）。返回
{引擎键: (值, 依据)}，由 derive.derive_all 包成 KeyMeta(source=查表)。

例外（不经本表，由 K4 余量排除法直接产出）：
- front_pocket_dart_width（③ 袋口转省三档：d<20→0 / 20~25→0.8 / >25→1.0）
- back_dart_count / back_dart_width（缺额→省数/省宽）
- back_dart_length 的 10.5 模板值仅作 dart_on=False（S2 强制开开关而缺额
  不足）兜底；dart_on 时由 derive.dart_length_linked 随省宽联动（省角恒定）
- front_pocket_p1_dist 走 K5 四则（K5-d 照片比例主通道 → K5-b 腰弧预算
  clamp〔照片比例在库时伴生宽先收带下限让位再钳，K5-b' 2026-10-02〕
  → K5-c 小表袋下界〔袋口宽随 K5-d 动态、过 G 表带 5.0~6.5 钳制〕
  → K5-a 腰围锚点插值兜底）；
  front_pocket_p2_drop / watch_pocket_width / watch_pocket_offset_from_top /
  watch_pocket_rotate_deg 亦有 K5-d 比例主通道（2026-10-01，兜底 = 腰位
  分档 / G 表 5.5 / G 表 1.0 / G 表 8°；分母一律单侧腰宽或前浪有效高），
  extra 由 derive 注入。
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
# 小表袋顶 drop×倾角联合可行域（金标 W74 标定，2026-10-01 实照事故补防线）：
# top ≤ _TOP_CAP0 − _TOP_CAP_SLOPE×rot（cm/度）。几何本质 = 内上角
# pt_b 必须在袋贴内边弧线上方（倾角×袋口宽把 pt_b 压沉：19.3°×5.7 压 1.9cm，
# pt_b 沉过内边即射线起点在弧线下方永不相交）。实测边界 8°→3.0+/19.3°→
# 2.0~2.5/24.2°→1.0+，31° 连 1.0 都炸（rot 物理窗因此收窄 0.45）。保守
# 必要条件（尺寸泛化未标定），充分性由探针 L0 兜底——与 K5-c 同构。
_TOP_CAP0 = 3.4
_TOP_CAP_SLOPE = 0.088
_WAISTBAND_W = 4.0      # 腰头宽（waistband 族同值；p2 锚 = 前浪 − 本值）
_P1_ANCHORS = ((64.3, 8.8), (74.0, 10.0))   # K5-a 插值锚（W→p1）
_P1_FLY_MARGIN = 0.3    # K5-b 门襟侧安全间隙（2026-10-01 收紧：弦≤腰弧
                        # 实测的保守量已天然含余量，1.0 把阔腿小腰款 p1
                        # 压到弦的 ~45%（实照袋口上端在 ~55%）；引擎守卫
                        # 零间隙 raise，本预算 max(袋贴,吃省)+fly+margin
                        # 恒 < 弦 ≤ 弧，余量 ≥0.3 不会触发）
_FACING_W_MIN = 3.0     # 袋贴腰头端宽带下限（引擎 options 注释常规 3.0~4.0）
_FLY_W_MIN = 3.5        # fly_width 带下限（YKK 5# 3.5~4.2）
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
    | ratio_p1 / ratio_bp / ratio_p2 / ratio_wpw / ratio_wpt / ratio_wps
    K5-d 已采纳照片比例（conf≥0.5 + 钳物理窗后，None = 未观测/低置信走
    兜底）| front_rise 前浪（p2 / 小表袋顶 drop 锚）| watch_w 小表袋宽
    K5-d 换算值（derive 单点算出，K5-c 动态下界与 watch 族宽度共用）。
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
        # 预算扣减与引擎守卫同口径（front_pocket_steps 主守卫 = p1 +
        # max(袋贴腰头端宽, 袋口吃省) + fly_width ≥ 腰弧 raise；袋贴关闭
        # 伴随守卫只扣吃省）——取 max(袋贴, dw)，margin 0.3 时预算端恒
        # p1+扣减+fly = 弦−margin < 弦 ≤ 弧，不触引擎 raise（2026-10-01）
        facing_w = _FACING_WAIST_W if ex.get("facing_on") else 0.0
        fly_w = _FLY_W
        dw = ex.get("pocket_dw") or 0.0

        def _budget(fw: float, fy: float) -> float:
            return math.floor(
                (chord - fy - max(fw, dw) - _P1_FLY_MARGIN) * 10 + 1e-9) / 10

        bound = None
        if ex.get("fly_sep") and chord is not None:
            # K5-b：弦 = waist_front_target（弦 ≤ 腰弧实测，保守安全侧）；
            # floor 0.1（+1e-9 护浮点尘），下界冲突时 K5-c 胜出并披露
            bound = _budget(facing_w, fly_w)
            if p1 > bound and ratio is not None:
                # K5-b' 伴生宽让位（2026-10-02 实照口径，用户裁定）：照片
                # 袋宽优先——伴生宽收引擎带下限（袋贴 常规 3.0~4.0 取 3.0、
                # fly 3.5~4.2 取 3.5）让预算闭合，仍不足才按收窄后的界钳
                # p1；无照片比例（K5-a 兜底）不收缩维持旧钳口径——默认
                # 伴生宽是工业常态，不为兜底值让位。收缩值经 extra（同一
                # dict 引用）传入 facing/fly 族发射：族矩阵里前口袋族最先
                # 执行、facing/fly 在后，put 后写覆盖故此处先记账后生效
                f_new = _FACING_W_MIN if ex.get("facing_on") else 0.0
                y_new = _FLY_W_MIN
                bound2 = _budget(f_new, y_new)
                if bound2 > bound:
                    parts = []
                    if f_new != facing_w:
                        parts.append(f"袋贴 {facing_w:g}→{f_new:g}")
                        facing_w = f_new
                        if extra is not None:
                            extra["facing_w_eff"] = f_new
                    if y_new != fly_w:
                        parts.append(f"fly_width {fly_w:g}→{y_new:g}")
                        fly_w = y_new
                        if extra is not None:
                            extra["fly_w_eff"] = y_new
                    if p1 <= bound2:
                        evs.append(
                            f"K5-b 伴生宽让位：标准伴生界 {bound:.2f} < "
                            f"照片袋宽 {p1:.1f}，{'、'.join(parts)}重算界 "
                            f"{bound2:.2f} ≥ {p1:.1f} 保照片袋宽（防袋贴×"
                            "门襟腰弧重合）")
                    else:
                        p1 = bound2
                        evs.append(
                            f"K5-b 腰弧预算 clamp：照片袋宽超伴生收窄后界"
                            f"——{'、'.join(parts)}后界 {bound2:.2f} 仍不足 "
                            f"→ p1={p1:.1f}（防袋贴×门襟腰弧重合）")
                    bound = bound2
                else:
                    # 伴生宽已在带下限、无让位空间：按现行界钳（不静默放行
                    # p1 超界）
                    p1 = bound
                    evs.append(f"K5-b 腰弧预算 clamp：前腰弦 {chord:.2f} − "
                               f"fly_width {fly_w:g} − 袋贴/吃省 "
                               f"{max(facing_w, dw):g} − 间隙 "
                               f"{_P1_FLY_MARGIN:g} → p1={p1:.1f}（防袋贴×"
                               "门襟重合，伴生宽已收无可让）")
            elif p1 > bound:
                p1 = bound
                evs.append(f"K5-b 腰弧预算 clamp：前腰弦 {chord:.2f} − "
                           f"fly_width {fly_w:g} − 袋贴/吃省 "
                           f"{max(facing_w, dw):g} − 间隙 "
                           f"{_P1_FLY_MARGIN:g} → p1={p1:.1f}（防袋贴×"
                           "门襟重合，独立门襟才占腰弧）")
        # K5-c 小表袋下界（watch 开；2026-10-01 袋口宽动态化——K5-d 比例可
        # 改 watch_w，取 G 表带 5.0~6.5 钳后值，兜底 5.5 时 = 旧常数 4.5
        # 零漂移）；ceil0.1（−1e-9 护浮点尘）。cos8° 取兜底平角 = x 向投影
        # 上界（倾角照片通道可到 ~30°，cos 更小 → 下界更松，保守安全侧）。
        # 必要非充分：充分性由探针 L0 兜底
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
        # 腰头端宽：K5-b' 伴生宽让位时收窄（前口袋族经 extra 记账，此处
        # 消费；无记账走 G 表 3.5）
        ex_f = extra or {}
        fw = _FACING_WAIST_W
        few = f"{g}：引擎默认在带内"
        if ex_f.get("facing_w_eff") is not None:
            fw = ex_f["facing_w_eff"]
            few = (f"K5-b 伴生宽让位：袋贴腰头端宽收带下限 {fw:g}"
                   "（常规 3.0~4.0；照片袋宽优先，防袋贴×门襟腰弧重合）")
        fam["front_pocket_facing_width"] = (fw, few)
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
        # 定位口径（2026-10-01 实照再校准，取代 09-02 单照片「顶部对齐」
        # 单一定标）：小表袋定位三件套（顶边离腰 drop / 顶边斜率 / 袋口宽）
        # 均照片可见，K5-d 比例主通道优先，G 表兜底（无照片金标零漂移）；
        # 深度仍不管控（facing_intersect 自动延伸入袋）。
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
        # 顶边离腰 drop：比例 × 前浪有效高（与 p2 同分母锚），覆盖 G 表 1.0
        top = 1.0
        topev = f"{g}：贴腰头下缘 ~1.0（09-02 单照片定标，兜底值）"
        r_top, fr = ex.get("ratio_wpt"), ex.get("front_rise")
        if r_top is not None and fr is not None:
            top = round(r_top * (fr - _WAISTBAND_W), 1)
            topev = (f"K5-d 照片比例主通道：比例 {r_top:.2f} × 前浪有效高 "
                     f"{fr - _WAISTBAND_W:.1f} = {top:.1f}（覆盖 G 表 1.0；"
                     "宽腰照实测 0.13×26≈3.4 挂腰头下缘偏高失真）")
        # 顶边斜率：模型报「相对腰头线，内端比外端低多少 ÷ 袋口宽」
        # （= tan 倾角；参照系 = 腰头下缘线而非画面水平，2026-10-02
        # 用户口径——整车旋转不进倾角），代码 atan 换算度数，覆盖 G 表 8°
        rot = 8.0
        rotev = f"{g}：顺时针倾 8°（兜底值）"
        r_sl = ex.get("ratio_wps")
        if r_sl is not None:
            rot = round(math.degrees(math.atan(r_sl)), 1)
            rotev = (f"K5-d 照片比例主通道：顶边相对腰线落差 ÷ 袋口宽 "
                     f"{r_sl:.2f} → atan ≈ {rot:.1f}°（覆盖 G 表 8°）")
        # 联合可行域钳（金标 W74 标定必要条件）：内上角须在袋贴内边上方，
        # 照片构造常为顶部外露式（顶边深+大倾角）超 facing_intersect 藏头式
        # 可行域——钳至可行域内保守近似，照片读数披露不静默
        top_cap = round(_TOP_CAP0 - _TOP_CAP_SLOPE * rot, 1)
        if top > top_cap:
            top = max(1.0, top_cap)
            topev += (f" → 联合可行域钳 {top:.1f}（top ≤ {_TOP_CAP0:g} − "
                      f"{_TOP_CAP_SLOPE:g}×{rot:.1f}° = {top_cap:.1f}，内上角"
                      "须在袋贴内边上方的保守必要条件；照片构造疑为顶部外露式"
                      "超藏头式可行域，充分性由探针 L0 兜底）")
        fam["watch_pocket_offset_from_top"] = (top, topev)
        fam["watch_pocket_offset_from_side"] = (
            _WATCH_SIDE, "小表袋配套包（引擎缺口实测 66–84 码全过）")
        fam["watch_pocket_rotate_deg"] = (rot, rotev)

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
        # 门襟宽：K5-b' 伴生宽让位时收窄（前口袋族经 extra 记账，此处
        # 消费；无记账走 G 表 4.0）
        ex_f = extra or {}
        fyw = _FLY_W
        fywev = f"{g}：YKK 5# 门襟宽 3.5~4.2"
        if ex_f.get("fly_w_eff") is not None:
            fyw = ex_f["fly_w_eff"]
            fywev = (f"K5-b 伴生宽让位：fly_width 收带下限 {fyw:g}"
                     "（3.5~4.2；照片袋宽优先，防袋贴×门襟腰弧重合）")
        fam["fly_width"] = (fyw, fywev)
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
