"""人读报告：反解析全链溯源文本（.doc/工厂DXF逆向解析.md §5.3）。

仿 exporters/report.py 风格：件清单表 -> 缩水标定 -> 识别指派与告警 ->
逐键口径推导（measure trace 原文）-> 选项与警告 -> 档差 -> 未恢复清单。
render 返回 str，写文件或打印由调用方决定。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:                          # 运行期零循环依赖（仅类型）
    from .identify import RoleReport
    from .measure import Calibration, MeasuredSize
    from .model import FactoryDoc

# 层 5：几何上不存在、无法从 DXF 恢复的参数族（保持引擎默认，报告明示）
_NOT_RECOVERED = (
    "形状系数族（弧线 α/β/κ、sag、bulge 等）——层 4 逆拟合不在本期",
    "显示/工艺标注（show_labels、notch 类型 V/I、back_dart 布局与省量）",
    "毗围闭环控制参数（thigh_piece_split_max 等，开关已按观测发射）"
    "与 fit 版型标签",
    "其余口袋族逐锚点形状（front_pouch_nodes、front_patch_custom_* "
    "等——袋布走里料不在工厂打版 DXF）",
)


def render_reverse_report(doc: "FactoryDoc", profile, roles: "RoleReport",
                          calib: "Calibration | None",
                          base: str,
                          measured: dict[str, "MeasuredSize"],
                          options: dict | None,
                          warns: list[str],
                          size_run: dict | None) -> str:
    """组装完整报告文本（probe 模式传 calib=None / measured={} /
    options=None / size_run=None）。"""
    from .identify import piece_inventory_lines

    L: list[str] = []
    L.append(f"工厂 DXF 反解析报告：{doc.path}")
    L.append("=" * 64)
    L.append(f"款型档案：{profile.key}（{profile.description}）")
    if doc.header.style_name:
        L.append(f"头标 STYLE NAME：{doc.header.style_name}")
    if doc.header.sample_size:
        L.append(f"头标 SAMPLE SIZE：{doc.header.sample_size}")
    if doc.header.grade_rule_table:
        L.append(f"头标 GRADE RULE TABLE：{doc.header.grade_rule_table}")
    L.append("")

    L.append("-- 件清单 --")
    L.extend(piece_inventory_lines(doc))
    L.append("")

    if calib is not None:
        L.append("-- 缩水标定 --")
        L.append(f"来源：{calib.source}；横(纬/weft)={calib.weft:.0%}、"
                 f"直(经/warp)={calib.warp:.0%}")
        L.append("还原口径：成品cm = 净样mm ×(1−率)÷10（乘法；与 cutter 除法"
                 "口径互逆）")
        L.append("")

    L.append("-- 角色指派 --")
    if roles.notes:
        L.extend(roles.notes)
    else:
        L.append("无告警")
    if roles.unassigned:
        L.append("未指派子片：")
        for key, reason in roles.unassigned:
            L.append(f"  {key}：{reason}")
    L.append("")

    for label in measured:
        ms = measured[label]
        tag = "（基码）" if label == base else ""
        L.append(f"-- 尺寸单 8 键 [{label}]{tag} --")
        for k in ("waist", "hip", "thigh", "knee", "hem", "front_rise",
                  "back_rise", "outseam"):
            L.append(f"  {k:<12} {ms.values[k]:8.2f} cm")
        L.append("  口径推导：")
        L.extend(f"    {t}" for t in ms.trace)
        for k in sorted(ms.extras):
            v = ms.extras[k]
            text = f"{v:.2f}" if isinstance(v, float) else str(v)
            L.append(f"    [旁证] {k} = {text}")
        L.append("")

    if options is not None:
        L.append(f"-- 选项（层 2，基码 {base}）--")
        for k, v in options.items():
            if isinstance(v, dict):
                inner = ", ".join(f"{kk}={vv}" for kk, vv in v.items())
                L.append(f"  {k}: {inner}")
            else:
                L.append(f"  {k:<28} {v}")
        if warns:
            L.append("  警告：")
            L.extend(f"    {w}" for w in warns)
        L.append("")

    if size_run is not None:
        L.append("-- 推码档差（层 3）--")
        for band in size_run.get("band", ()):
            sizes = "/".join(band["sizes"])
            steps = ", ".join(f"{k}={band[k]:+.2f}" for k in
                              ("waist", "hip", "knee", "hem", "front_rise",
                               "back_rise", "outseam", "thigh") if k in band)
            L.append(f"  段 {sizes}：{steps}")
        L.append("")

    L.append("-- 未恢复清单（层 5，保持引擎默认）--")
    L.extend(f"  - {item}" for item in _NOT_RECOVERED)
    if doc.warnings:
        L.append("")
        L.append("-- 读取警告 --")
        L.extend(f"  {w}" for w in doc.warnings)
    return "\n".join(L) + "\n"
