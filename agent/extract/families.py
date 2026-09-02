"""部件参数族模板（G 表）——部件开关开启即全族发射，族内自洽。

数值权威：计划 G 表初版（v1 = examples 金标值 / 工业惯例 / 档位中值；K5
部件尺寸档位【待收集】→ 与引擎默认一致的键标注「引擎默认在带内」）。返回
{引擎键: (值, 依据)}，由 derive.derive_all 包成 KeyMeta(source=查表)。

例外（不经本表，由 K4 余量排除法直接产出）：
- front_pocket_dart_width（③ 袋口转省 0.8/1.0）
- back_dart_count / back_dart_width（缺额→省数/省宽）
- watch_pocket_offset_from_side=2.0 属小表袋配套包（引擎缺口实测），随本族发射。
"""

from __future__ import annotations

# 袋口弧深三档（款式判据手册 §二）。值 = 引擎 bulge，渲染真弧高 = 2×bulge
# （curves.arc_through 实测口径，2026-08-30 钉死）。档位按真弧高 cm 定标：
# 浅 1.5 / 标准 2.5 / 深 3.5，即 bulge 0.75/1.25/1.75。定标出处：工厂 DXF 实测
# 5015/5028 真弧高 3.36（深档带内，工厂DXF逆向解析.md 袋口形态行、
# test_reverse_gold_5015 断言 bulge=1.68）+ 2026-09-02 照片读数深月牙 3~4cm
# 同带；旧 0.3/0.4/0.5 渲染仅 0.6/0.8/1.0cm，比工厂/照片浅 3~4 倍（用户复核
# 发现）。标准档 2.5 为插值初版，待打版师金标校准。
_MOUTH_BULGE = {"shallow": 0.75, "standard": 1.25, "deep": 1.75}


def _back_patch_size(axes: dict[str, str]) -> tuple[float, float, str]:
    """贴袋 width/height：女档中值 13.5/14.0，男款放大 1.5（G 表）。"""
    if axes.get("gender") == "male":
        return 15.0, 15.5, "G 表男档（女档 13.5/14.0 放大 1.5）"
    return 13.5, 14.0, "G 表女档中值（width 13~14 / height 12~15）"


def part_family(part: str, axes: dict[str, str], enums: dict[str, str],
                measurements: dict[str, float]) -> dict[str, tuple[object, str]]:
    """按部件名发射整族模板键（值, 依据）。part 见 derive_all 的调用矩阵。"""
    fam: dict[str, tuple[object, str]] = {}
    g = "G 表（部件参数族模板 v1，K5 待收集）"

    if part == "front_pocket":
        # p1 10.0 对齐金标 example（引擎默认 8.5 在高腰款与小表袋射线相交
        # 失配——实测 p1 10 后袋贴内边弧让射线命中，66–84 码口径延续）
        fam["front_pocket_p1_dist"] = (10.0, f"{g}：金标 example 值")
        # p2 按腰位分档：竖向空间 = 外缝弧臀围端→腰侧，低腰档弧短（低腰喇叭
        # 实测仅 ~10.3），须满足 p2_drop + facing_side_w < 弧长（袋贴守卫）；
        # 低腰 5.5（实测 5.0~6.5 全过取中偏浅）/ 中低 6.5 / 中+ 7.5（金标
        # example 8.0 属高腰带）
        band = axes.get("waist_position", "mid")
        p2 = {"low": 5.5, "mid_low": 6.5}.get(band, 7.5)
        fam["front_pocket_p2_drop"] = (
            p2, f"{g}：腰位联动 {band} 档（低腰竖向空间小，袋口相应变浅）")
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
        fam["front_pocket_facing_width"] = (3.5, f"{g}：引擎默认在带内")
        # 侧缝深度：注释带 5~7 是大码余量，小码 p2_drop+side_w 越外缝弧臀围端
        # （front_pocket_steps.py 守卫）；金标 examples/size_female_165 同量级用 3.5
        fam["front_pocket_facing_side_w"] = (
            3.5, f"{g}：金标 example 值（注释带 5~7 大码适用，需 p2+side<外缝弧长）")
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
        fam["watch_pocket_width"] = (
            5.5, f"{g}：浅小兜 5~6.5 取 5.5（实照核对，旧 7.0 偏大）")
        fam["watch_pocket_taper"] = (0.2, f"{g}：两侧收 0.2")
        fam["watch_pocket_offset_from_top"] = (
            1.0, f"{g}：贴腰头下缘 ~1.0（实照核对，旧 3.0 顶部下沉过多）")
        fam["watch_pocket_offset_from_side"] = (
            2.0, "小表袋配套包（引擎缺口实测 66–84 码全过）")
        fam["watch_pocket_rotate_deg"] = (8.0, f"{g}：顺时针倾 8°")

    elif part == "back_patch":
        w, hgt, sizev = _back_patch_size(axes)
        fam["back_patch_inset_x"] = (4.5, f"{g}：距后浪 4~5.5 中值")
        fam["back_patch_drop_y"] = (3.5, f"{g}：距约克底线 3~4.5 中值")
        fam["back_patch_rotate_deg"] = (3.5, f"{g}：平行约克线倾角")
        fam["back_patch_width"] = (w, f"{g}：{sizev}")
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
        fam["fly_width"] = (4.0, f"{g}：YKK 5# 门襟宽 3.5~4.2")
        fam["fly_length_ratio"] = (0.35, f"{g}：开深系数（引擎默认在带内）")
        fam["fly_length_base"] = (2.0, f"{g}：开深基值（引擎默认在带内）")
        fam["fly_corner_inset"] = (0.5, f"{g}：底角内收 0.5（R = W−本值）")

    elif part == "belt_loop":
        fam["belt_loop_width"] = (1.2, f"{g}：引擎默认（净宽 1.2）")
        fam["belt_loop_unit_length"] = (6.0, f"{g}：单根 6.0")
        fam["belt_loop_count"] = (5, f"{g}：5 根")
        fam["belt_loop_waste"] = (3.0, f"{g}：损耗 3.0")

    elif part == "waistband":
        fam["waistband_width"] = (4.0, f"{g}：腰头宽默认 4.0（宽窄档 3.5/4.5 待照片判据）")

    return fam
