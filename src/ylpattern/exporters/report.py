"""尺寸报表：中间计算尺寸 + 追踪记录，供打版师核对。"""

from __future__ import annotations

from ..draft import DraftSheet
from ..draft.elements import NamedPoint, NamedLine
from ..params import Measurements, PatternOptions


def render_report(sheet: DraftSheet, m: Measurements,
                  o: PatternOptions, trace: str = "") -> str:
    lines = [
        "=" * 56,
        "打版绘制报表",
        "=" * 56,
        f"尺寸单： waist={m.waist} hip={m.hip} knee={m.knee} hem={m.hem}",
        f"         front_rise={m.front_rise} back_rise={m.back_rise} "
        f"outseam={m.outseam} thigh={m.thigh}",
        f"选项：   delta={o.delta} fit={o.fit.value} "
        f"waistband={o.waistband_type.value}",
        "-" * 56,
        f"版上元素：点 {len(sheet.points)}，线 {len(sheet.lines)}，"
        f"曲线 {len(sheet.curves)}",
        "-" * 56,
    ]
    for el in sheet:
        if isinstance(el, NamedLine):
            a, b = el.geom.a, el.geom.b
            pos = (f"y={a.y:.2f}" if abs(a.y - b.y) < 1e-9
                   else f"x={a.x:.2f}" if abs(a.x - b.x) < 1e-9
                   else f"({a.x:.1f},{a.y:.1f})~({b.x:.1f},{b.y:.1f})")
            lines.append(f"线  {el.name:<28} {pos:<14} {el.basis}")
        elif isinstance(el, NamedPoint):
            lines.append(f"点  {el.name:<28} ({el.geom.x:>6.2f}, "
                         f"{el.geom.y:>6.2f})  {el.basis}")
    if trace:
        lines += ["-" * 56, "绘制追踪：", trace]
    return "\n".join(lines)
