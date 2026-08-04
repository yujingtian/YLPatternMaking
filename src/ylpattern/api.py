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
        back_crotch_adjust: float = 0.0,
        front_intake_adjust: float = 0.0,
        rise_ratio: float = 0.25, rise_adjust: float = 0.0,
        waistband_type: WaistbandType | str = WaistbandType.STRAIGHT,
        waistband_width: float = 4.0,
        side_rise: float = 0.0,
        waist_balance: float = 0.0, front_waist_dart: float = 0.0,
        front_crease_e: float = 0.0,
        knee_adjust: float = 1.0, hem_adjust: float = 1.0,
        calf_arc_alpha: float = 0.10,
        inseam_arc_k1: float = 0.20, inseam_arc_ky: float = 0.28,
        inseam_arc_k2: float = 0.35,
        outseam_arc_dx: float = 0.15, outseam_arc_m2: float = 0.40,
        hem_arc_sag: float = 0.0,
        seam_allowance: float = 1.0,
        svg: str = "out/sheet.svg",
        until: str | None = None,
        trace: str | None = None,
        report: str | None = None) -> DraftContext:
    """录入尺寸参数，执行前片绘制流程并生成 SVG。

    参数：
        waist ~ thigh    八项核心尺寸（cm），含义见 examples/size_female_165.toml
        delta            前后片臀围单侧调节量 Δ（推导文档 §四）
        front_crotch_adjust 前小裆修正量（紧身款 -0.5~-1.0）
        back_crotch_adjust  后大裆修正量（坐姿伸展加深取正，常规 0）
        front_intake_adjust  前中内收修正量（内收量 = (H−W)/4 × 系数 + 本值；高腰取正、低腰取负）
        rise_ratio       直裆深系数（直裆深 = H × ratio + adjust，默认 H/4）
        rise_adjust      直裆深修正量（cm）
        waistband_type   腰头类型："straight" 直腰头 / "curved" 弯腰头（打版流程.md 注意点 1）
        waistband_width  腰头宽（cm）；直腰头打版时从裤长中扣除，弯腰头忽略
        side_rise        侧缝腰头抬高量 h（0 = 腰围外缝顶点压基础线，常取 0~1.5）
        waist_balance    前后片腰围调节量（前减后加；平分 0，常取 1.0~1.5）
        front_waist_dart 前片省量/褶量 V前省（标准牛仔裤 0；西裤 1.5~3.0）
        front_crease_e   前片裤中线调节量 e（常规 0；修身 -0.5~-0.8，裤中线推导.md §五）
        knee_adjust      膝围前后片调整量 δ（前减后加，前片膝围宽 = K/2 − δ；高弹 0.5~0.75）
        hem_adjust       脚口前后片调整量 δ（前减后加，前片脚口宽 = B/2 − δ）
        calf_arc_alpha   小腿段弧弓高系数 α（0.08~0.12；0 = 直筒直线，前片弧线推导.md §三）
        inseam_arc_k1    内缝大腿段小裆弯度 k1（0.15~0.25，越大越早往膝口收，§四）
        inseam_arc_ky    内缝大腿段纵向系数 ky（越大弯曲点越靠下，§四）
        inseam_arc_k2    内缝大腿段膝口切线柄长系数（k2 = 本值×ΔY，§四）
        outseam_arc_dx   外缝大腿段大转子外凸 δx（0.1~0.2；顺直 0，§五）
        outseam_arc_m2   外缝大腿段膝口切线柄长系数（m2 = 本值×ΔY，§五）
        hem_arc_sag      脚口弧高（0 = 直线；正值向上凹入裤片，常取 0.3~0.8）
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
                       back_crotch_adjust=back_crotch_adjust,
                       front_intake_adjust=front_intake_adjust,
                       rise_ratio=rise_ratio,
                       rise_adjust=rise_adjust,
                       waistband_type=WaistbandType(waistband_type),
                       waistband_width=waistband_width,
                       side_rise=side_rise,
                       waist_balance=waist_balance,
                       front_waist_dart=front_waist_dart,
                       front_crease_e=front_crease_e,
                       knee_adjust=knee_adjust,
                       hem_adjust=hem_adjust,
                       calf_arc_alpha=calf_arc_alpha,
                       inseam_arc_k1=inseam_arc_k1,
                       inseam_arc_ky=inseam_arc_ky,
                       inseam_arc_k2=inseam_arc_k2,
                       outseam_arc_dx=outseam_arc_dx,
                       outseam_arc_m2=outseam_arc_m2,
                       hem_arc_sag=hem_arc_sag,
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
