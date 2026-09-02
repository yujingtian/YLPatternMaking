"""打版后特征合理性评分（F 表）——探针判「炸不炸」，评分判「合不合理」。

一期只警示不改参（出界进报告「合理性警告」，回喂改参留二期）。全部特征从
DraftContext 实测（先画后评，不重复推导）：

| 特征 | 区间 | 实证出处 |
|---|---|---|
| 袋口弦长/前片宽 | 45%~55% | 评审实证 13.35/59% 失调配例 |
| 袋口弧深/弦长（bulge 弧线式） | 10%~32% | 工厂 5015 实测 27%、照片深月牙 25%~30% |
| 前/后侧缝上段斜度（腰→臀连线偏角） | ≤~30° | W69+H94 极限臀腰差元凶 |
| 前后侧缝收量倒挂（前 > 后） | 前 ≤ 后 | curvy 联动防的正是这个 |
| 直裆深自洽（前浪−腰头 vs H/4+rise_adjust） | [est−0.3, est+8] | B 表自洽校验同源 |
| 前中内收落档（绝对值 vs K2 基准带） | 带内 | K2 前中内收预测.md |
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .prejudge import waist_position_band

# K2 基准带上下界（前中内收预测.md 第一步表，score 只做复核不再修正）
_K2_BOUNDS = {"low": (0.0, 0.5), "mid_low": (0.5, 1.0), "mid": (1.0, 1.5),
              "mid_high": (1.5, 2.5), "high": (2.5, 3.5)}


@dataclass(frozen=True)
class ScoreItem:
    """单条评分：实测值 + 期望区间 + 判定（ok/warn）。"""

    feature: str
    value: str
    band: str
    verdict: str


def warnings(items: list[ScoreItem]) -> list[ScoreItem]:
    return [i for i in items if i.verdict == "warn"]


def _dist(p, q) -> float:
    return math.hypot(p.x - q.x, p.y - q.y)


def score_features(ctx, measurements: dict, options: dict) -> list[ScoreItem]:
    """从打版成功的 DraftContext 量派生特征并按业务区间评分。"""
    sheet = ctx.sheet
    has = lambda n: n in sheet   # noqa: E731（局部谓词，非导出 API）
    items: list[ScoreItem] = []

    # S1 袋口弦长 / 前片宽
    if has("front.pocket_p1") and has("front.pocket_p2") and \
            has("front.hip_line"):
        chord = _dist(ctx.point("front.pocket_p1"), ctx.point("front.pocket_p2"))
        width = _dist(ctx.line("front.hip_line").a, ctx.line("front.hip_line").b)
        if width > 1e-9:
            r = chord / width
            items.append(ScoreItem(
                "袋口弦长/前片宽", f"{r:.0%}", "45%~55%",
                "ok" if 0.45 <= r <= 0.55 else "warn"))

    # S1b 袋口弧深/弦长（bulge 弧线式）：真弧高÷弦长。经典五袋带 10%~32%
    # （工厂 5015 实测 3.36/弦长≈27%、2026-09-02 照片深月牙 25%~30%；
    # 旧未校准三档渲染仅 0.6~1.0cm ≈5%~8% 出下界——正是「弧度和照片
    # 差距很大」那类配例的输出侧兜底哨兵）。tangent 直切式近直线、
    # polyline 无 baseline（front_pocket_steps 仅 mode != polyline 上版
    # baseline），均不参与本带判定。
    if has("front.pocket_mouth_baseline") and \
            str(options.get("front_pocket_mouth_mode", "bulge")) == "bulge":
        c = ctx.curve("front.pocket_mouth_baseline")
        pa, pb = c.p0, c.p3
        chord = _dist(pa, pb)
        if chord > 1e-9:
            ux, uy = (pb.x - pa.x) / chord, (pb.y - pa.y) / chord
            sag = max(abs((c.point_at(i / 32).x - pa.x) * uy
                          - (c.point_at(i / 32).y - pa.y) * ux)
                      for i in range(1, 32))
            r = sag / chord
            items.append(ScoreItem(
                "袋口弧深/弦长（bulge）", f"{r:.0%}",
                "10%~32%（经典五袋带，工厂实测≈27%）",
                "ok" if 0.10 <= r <= 0.32 else "warn"))

    # S2 侧缝上段斜度（腰侧点→臀侧点连线与竖直方向夹角，前/后各一）
    for piece, label in (("front", "前片"), ("back", "后片")):
        if has(f"{piece}.waist_side_point") and \
                has(f"{piece}.hip_outseam_point"):
            w = ctx.point(f"{piece}.waist_side_point")
            h = ctx.point(f"{piece}.hip_outseam_point")
            dy = abs(w.y - h.y)
            ang = math.degrees(math.atan2(abs(h.x - w.x), dy if dy > 1e-9 else 1e-9))
            items.append(ScoreItem(
                f"{label}侧缝上段斜度", f"{ang:.1f}°", "≤~30°",
                "ok" if ang <= 30.0 else "warn"))

    # S3 前后侧缝收量倒挂（收量 = 臀宽弦长 − 腰净宽弦长）
    try:
        fw = _dist(ctx.point("front.waist_side_point"),
                   ctx.point("front.rise_top_point"))
        fh = _dist(ctx.point("front.hip_outseam_point"),
                   ctx.point("front.hip_inner_point"))
        bw = _dist(ctx.point("back.waist_side_point"),
                   ctx.point("back.rise_top_point"))
        bh = _dist(ctx.point("back.hip_outseam_point"),
                   ctx.point("back.hip_inner_final"))
        fi, bi = fh - fw, bh - bw
        items.append(ScoreItem(
            "前后侧缝收量（前−后）", f"{fi - bi:+.2f}cm（前{fi:.2f}/后{bi:.2f}）",
            "前 ≤ 后（倒挂即警告）", "ok" if fi <= bi + 1e-9 else "warn"))
    except (KeyError, TypeError):
        pass   # 元素缺失（如 until 中断的版）跳过本项

    # S4 直裆深自洽：excess = 前浪 − H/4 − rise_adjust（腰头扣除两边相消；
    # 引擎直裆深在扣腰头后的版上取 H/4+Δ，前浪弧长应比它长出裆弯弧深）
    hip, fr = measurements.get("hip"), measurements.get("front_rise")
    if hip and fr:
        excess = fr - hip * 0.25 - float(options.get("rise_adjust", 0.0) or 0.0)
        items.append(ScoreItem(
            "直裆深自洽（前浪−H/4−Δ 裆弯弧深）", f"{excess:.2f}cm",
            "[1.5, 4.5]（经验带）", "ok" if 1.5 <= excess <= 4.5 else "warn"))

    # S5 前中内收落档：绝对值应落在腰位档的 K2 基准带内
    w, h = measurements.get("waist"), measurements.get("hip")
    ratio = options.get("front_intake_ratio")
    if w and h and fr and ratio is not None:
        intake = float(ratio) * (h - w) / 4 + \
            float(options.get("front_intake_adjust", 0.0) or 0.0)
        label = options.get("size_label", "-")
        try:
            sl = int(str(label)) if str(label).isdigit() else None
        except ValueError:
            sl = None
        band, _ = waist_position_band(fr, None, sl)
        lo, hi = _K2_BOUNDS.get(band, (0.0, 3.5))
        items.append(ScoreItem(
            f"前中内收落档（{band} 腰档）", f"{intake:.2f}cm",
            f"[{lo}, {hi}]（K2 基准带）", "ok" if lo <= intake <= hi else "warn"))
    return items
