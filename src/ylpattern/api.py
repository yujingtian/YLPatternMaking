"""顶层便捷 API：录入参数，直接生成 SVG。

用法：

    from ylpattern import run

    run(waist=70, hip=96, knee=46, hem=36,
        front_rise=25, back_rise=33, outseam=102, thigh=58,
        svg="out/sheet.svg")
"""

from __future__ import annotations

from .draft import DraftContext
from .exporters import svg as svg_exp
from .flows.front_flow import FRONT_FLOW
from .flows.runner import FlowRunner
from .params import Measurements, PatternOptions, WaistbandType


def run(*, waist: float, hip: float, knee: float, hem: float,
        front_rise: float, back_rise: float, outseam: float, thigh: float,
        delta: float = 1.0, front_crotch_adjust: float = 0.0,
        rise_ratio: float = 0.25, rise_adjust: float = 0.0,
        waistband_type: WaistbandType | str = WaistbandType.STRAIGHT,
        waistband_width: float = 4.0,
        seam_allowance: float = 1.0,
        svg: str = "out/sheet.svg",
        until: str | None = None,
        trace: str | None = None,
        report: str | None = None) -> DraftContext:
    """录入尺寸参数，执行前片绘制流程并生成 SVG。

    参数：
        waist ~ thigh    八项核心尺寸（cm），含义见 examples/size_female_165.toml
        delta            前后片臀围单侧调节量 Δ（推导文档 §四）
        rise_ratio       直裆深系数（直裆深 = H × ratio + adjust，默认 H/4）
        rise_adjust      直裆深修正量（cm）
        waistband_type   腰头类型："straight" 直腰头 / "curved" 弯腰头（打版流程.md 注意点 1）
        waistband_width  腰头宽（cm）；直腰头打版时从裤长中扣除，弯腰头忽略
        svg              SVG 输出路径
        until            执行到指定步骤（含）停止，用于看中间状态
        trace / report   可选：同时输出追踪记录 / 尺寸报表到指定路径

    返回：
        DraftContext —— 可继续从 ctx.sheet 取元素做自定义处理。
    """
    m = Measurements(waist=waist, hip=hip, knee=knee, hem=hem,
                     front_rise=front_rise, back_rise=back_rise,
                     outseam=outseam, thigh=thigh)
    o = PatternOptions(delta=delta,
                       front_crotch_adjust=front_crotch_adjust,
                       rise_ratio=rise_ratio,
                       rise_adjust=rise_adjust,
                       waistband_type=WaistbandType(waistband_type),
                       waistband_width=waistband_width,
                       seam_allowance=seam_allowance)

    runner = FlowRunner(m, o)
    ctx = runner.run(FRONT_FLOW, until=until, trace=bool(trace))

    svg_exp.write_sheet_svg(ctx.sheet, svg)
    print(f"SVG 已输出:{svg}")

    if trace:
        with open(trace, "w", encoding="utf-8") as fp:
            fp.write(runner.trace_text())
        print(f"追踪记录已输出:{trace}")
    if report:
        from .exporters import report as report_exp
        with open(report, "w", encoding="utf-8") as fp:
            fp.write(report_exp.render_report(ctx.sheet, m, o,
                                              runner.trace_text()))
        print(f"报表已输出:{report}")
    return ctx
