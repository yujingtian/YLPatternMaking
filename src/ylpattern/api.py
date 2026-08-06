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
from .flows.closure import run_with_thigh_closure
from .params import Measurements, PatternOptions, WaistbandType


def run(*, waist: float, hip: float, knee: float, hem: float,
        front_rise: float, back_rise: float, outseam: float, thigh: float = 0.0,
        delta: float = 1.0, front_crotch_adjust: float = 0.0,
        back_crotch_adjust: float = 0.0,
        front_intake_adjust: float = 0.0,
        back_intake: float = 2.5,
        back_rise_alpha: float = 0.40, back_rise_beta: float = 0.50,
        rise_ratio: float = 0.25, rise_adjust: float = 0.0,
        crotch_drop_adjust: float = 0.0,
        waistband_type: WaistbandType | str = WaistbandType.STRAIGHT,
        waistband_width: float = 4.0,
        side_rise: float = 0.0,
        front_waist_curve_sag: float = 0.3, back_waist_curve_sag: float = 0.3,
        waist_balance: float = 0.0, front_waist_dart: float = 0.0,
        back_waist_dart: float = 0.0,
        back_dart: bool = False, back_dart_count: int = 1,
        back_dart_width: float | list[float] | tuple[float, ...] = 2.0,
        back_dart_length: float = 11.0,
        front_crease_e: float = 0.0, back_crease_e: float = 0.0,
        knee_adjust: float = 1.0, hem_adjust: float = 1.0,
        calf_arc_alpha: float = 0.10,
        inseam_arc_k1: float = 0.20, inseam_arc_ky: float = 0.28,
        inseam_arc_k2: float = 0.35,
        outseam_arc_dx: float = 0.15, outseam_arc_m2: float = 0.40,
        back_calf_arc_alpha: float = 0.10,
        back_inseam_arc_k1: float = 0.30, back_inseam_arc_ky: float = 0.30,
        back_inseam_arc_k2: float = 0.35,
        back_outseam_arc_dx: float = 0.15, back_outseam_arc_m2: float = 0.40,
        back_hipwaist_arc_dx1: float = 0.15, back_hipwaist_arc_k1: float = 0.40,
        back_hipwaist_arc_dx2: float = 0.0, back_hipwaist_arc_k2: float = 0.25,
        front_hem_arc_sag: float = 0.0, back_hem_arc_sag: float = 0.0,
        thigh_limit: bool = False, thigh_measure_offset: float = 0.0,
        thigh_piece_split_max: float = 0.2, thigh_front_share: float = 0.2,
        thigh_dual_track_min: float = 0.3,
        thigh_front_crotch_coef: float = 0.09,
        thigh_back_crotch_coef: float = 0.21,
        thigh_front_crotch_max: float = 0.4,
        thigh_back_crotch_max: float = 1.0,
        thigh_max_iter: int = 6, thigh_tol: float = 0.3,
        piece_gap: float = 10.0,
        seam_allowance: float = 1.0,
        svg: str = "out/sheet.svg",
        until: str | None = None,
        trace: str | None = None,
        report: str | None = None) -> DraftContext:
    """录入尺寸参数，执行整版绘制流程（前片 + 后片）并生成 SVG。

    参数：
        waist ~ outseam  七项核心尺寸（cm），含义见 examples/size_female_165.toml
        thigh            大腿围（可选；0 = 未录入，毗围限制自动跳过，
                         打版流程.md 后片步骤 8）
        delta            前后片臀围单侧调节量 Δ（推导文档 §四）
        front_crotch_adjust 前小裆修正量（紧身款 -0.5~-1.0）
        back_crotch_adjust  后大裆修正量（坐姿伸展加深取正，常规 0）
        front_intake_adjust  前中内收修正量（内收量 = (H−W)/4 × 系数 + 本值；高腰取正、低腰取负）
        back_intake      后中内收比例模数 X（实际内收 = 臀腰高×X/15；宽松 1.5~2、标准 2.5~3、紧身 3.5~4.5）
        back_rise_alpha 后浪大裆弯上控制柄系数 α（0.38~0.42，后浪绘制.md §3.1）
        back_rise_beta  后浪大裆弯下控制柄系数 β（0.48~0.55，紧身提臀 0.55，§3.1）
        rise_ratio       直裆深系数（直裆深 = H × ratio + adjust，默认 H/4）
        rise_adjust      直裆深修正量（cm）
        crotch_drop_adjust 后片落裆调节量 Δc（落裆量 = H/100 + Δc；高弹取负、宽松取正）
        waistband_type   腰头类型："straight" 直腰头 / "curved" 弯腰头（打版流程.md 注意点 1）
        waistband_width  腰头宽（cm）；直腰头打版时从裤长中扣除，弯腰头忽略
        side_rise        侧缝腰头抬高量 h（0 = 腰围外缝顶点压基础线，常取 0~1.5）
        front_waist_curve_sag  前片腰围线弧额外下凹量（贴合腰腹取 0.3~0.5；
                               0 = 无额外下凹，90° 正交平顺段的弯曲仍在）
        back_waist_curve_sag   后片腰头线弧额外下凹量（贴合腰背背弓取 0.3~0.5，同上）
        waist_balance    前后片腰围调节量（前减后加；平分 0，常取 1.0~1.5）
        front_waist_dart 前片省量/褶量 V前省（标准牛仔裤 0；西裤 1.5~3.0）
        back_waist_dart 后片省量/约克转移量 V后省（约克步骤前 0；Yoke 2.5~4.0；
                        后腰长容位，与绘制的腰省相互独立）
        back_dart        后片腰省绘制开关（可选步骤，打版流程.md 后片步骤 9；
                         只画省，不动腰头）
        back_dart_count  后片省数（1 = 腰头两等分取中点；2 = 三等分取两个中点）
        back_dart_width  每个省的省量（默认 2cm；列表逐省控制，顺序同省中点：
                         后中 → 侧缝，个数须等于省数；写单个值则各省共用；
                         省量为 0 的省不绘制）
        back_dart_length 省中线长（默认 11cm）
        front_crease_e   前片裤中线调节量 e（常规 0；修身 -0.5~-0.8，裤中线推导.md §五）
        back_crease_e    后片裤中线调节量 e（常规与 front_crease_e 一致；
                         偏平臀/特大臀峰/提臀造型时独立设定，§五）
        knee_adjust      膝围前后片调整量 δ（前减后加，前片膝围宽 = K/2 − δ；高弹 0.5~0.75）
        hem_adjust       脚口前后片调整量 δ（前减后加，前片脚口宽 = B/2 − δ）
        calf_arc_alpha   小腿段弧弓高系数 α（0.08~0.12；0 = 直筒直线，前片弧线推导.md §三）
        inseam_arc_k1    内缝大腿段小裆弯度 k1（0.15~0.25，越大越早往膝口收，§四）
        inseam_arc_ky    内缝大腿段纵向系数 ky（越大弯曲点越靠下，§四）
        inseam_arc_k2    内缝大腿段膝口切线柄长系数（k2 = 本值×ΔY，§四）
        outseam_arc_dx   外缝大腿段大转子外凸 δx（0.1~0.2；顺直 0，§五）
        outseam_arc_m2   外缝大腿段膝口切线柄长系数（m2 = 本值×ΔY，§五）
        back_calf_arc_alpha  后片小腿段弧弓高系数 α（0.08~0.12，后片弧线推导.md §二）
        back_inseam_arc_k1   后内缝大腿段大裆弯度 k1（0.25~0.35，大于前片留运动空间，§三）
        back_inseam_arc_ky   后内缝大腿段纵向系数 ky（§三）
        back_inseam_arc_k2   后内缝大腿段膝口切线柄长系数（k2 = 本值×ΔY，§三）
        back_outseam_arc_dx  后外缝大腿段臀侧饱满度 δx（0.1~0.25；顺直 0，§四）
        back_outseam_arc_m2  后外缝大腿段膝口切线柄长系数（m2 = 本值×ΔY，§四）
        back_hipwaist_arc_dx1  臀侧凸出多少（0~0.3；0 = 顺直不凸，越大越往外鼓，§五）
        back_hipwaist_arc_k1   臀侧凸感延续多高（0.35~0.45；越大越晚往腰头弯，§五）
        back_hipwaist_arc_dx2  腰头角点凸出多少（0~0.3；0 = 竖直顺直进角，越大角点越鼓，§五）
        back_hipwaist_arc_k2   多早往腰头收（0.20~0.30；越大上段越早内缩、末端笔直进角，§五）
        front_hem_arc_sag  前片脚口弧高（0 = 直线；正值向下凸出裤片，常取 0.3~0.8）
        back_hem_arc_sag   后片脚口弧高（口径同前片，前后片独立录入）
        thigh_limit        毗围闭环修正开关（可选步骤，打版流程.md 后片步骤 8；
                           开启后按 前后片毗围推导.md §三 双轨分流整版重跑至收敛）
        thigh_measure_offset  毗围实测下移量 d（0 = 立裆深线直量；常规实测 2.54）
        thigh_piece_split_max  片间分配分界（|ΔW| ≤ 本值平分，否则大差量比，§三.1）
        thigh_front_share  大差量前片分配比（后片 = 1 − 本值；红线严禁 50:50，§三.1）
        thigh_dual_track_min  双轨分流阈值（|ΔW| ≤ 本值单动侧缝，否则内外联动，§三.2）
        thigh_front_crotch_coef / thigh_back_crotch_coef
                           前/后裆尖调拨系数（ΔX = 系数×ΔW，默认 0.09 / 0.21，§三.2）
        thigh_front_crotch_max / thigh_back_crotch_max
                           前/后裆尖累计调整上限（防卡耻骨 0.4 / 防下蹲崩破 1.0，§三.2）
        thigh_max_iter / thigh_tol  闭环最大迭代轮数（默认 3）/ 收敛容差（默认 0.05）
        piece_gap        前后片排版间距（后片整体置于前片右侧，分开不重叠）
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
                       back_intake=back_intake,
                       back_rise_alpha=back_rise_alpha,
                       back_rise_beta=back_rise_beta,
                       rise_ratio=rise_ratio,
                       rise_adjust=rise_adjust,
                       crotch_drop_adjust=crotch_drop_adjust,
                       waistband_type=WaistbandType(waistband_type),
                       waistband_width=waistband_width,
                       side_rise=side_rise,
                       front_waist_curve_sag=front_waist_curve_sag,
                       back_waist_curve_sag=back_waist_curve_sag,
                       waist_balance=waist_balance,
                       front_waist_dart=front_waist_dart,
                       back_waist_dart=back_waist_dart,
                       back_dart=back_dart,
                       back_dart_count=back_dart_count,
                       back_dart_width=back_dart_width,
                       back_dart_length=back_dart_length,
                       front_crease_e=front_crease_e,
                       back_crease_e=back_crease_e,
                       knee_adjust=knee_adjust,
                       hem_adjust=hem_adjust,
                       calf_arc_alpha=calf_arc_alpha,
                       inseam_arc_k1=inseam_arc_k1,
                       inseam_arc_ky=inseam_arc_ky,
                       inseam_arc_k2=inseam_arc_k2,
                       outseam_arc_dx=outseam_arc_dx,
                       outseam_arc_m2=outseam_arc_m2,
                       back_calf_arc_alpha=back_calf_arc_alpha,
                       back_inseam_arc_k1=back_inseam_arc_k1,
                       back_inseam_arc_ky=back_inseam_arc_ky,
                       back_inseam_arc_k2=back_inseam_arc_k2,
                       back_outseam_arc_dx=back_outseam_arc_dx,
                       back_outseam_arc_m2=back_outseam_arc_m2,
                       back_hipwaist_arc_dx1=back_hipwaist_arc_dx1,
                       back_hipwaist_arc_k1=back_hipwaist_arc_k1,
                       back_hipwaist_arc_dx2=back_hipwaist_arc_dx2,
                       back_hipwaist_arc_k2=back_hipwaist_arc_k2,
                       front_hem_arc_sag=front_hem_arc_sag,
                       back_hem_arc_sag=back_hem_arc_sag,
                       thigh_limit=thigh_limit,
                       thigh_measure_offset=thigh_measure_offset,
                       thigh_piece_split_max=thigh_piece_split_max,
                       thigh_front_share=thigh_front_share,
                       thigh_dual_track_min=thigh_dual_track_min,
                       thigh_front_crotch_coef=thigh_front_crotch_coef,
                       thigh_back_crotch_coef=thigh_back_crotch_coef,
                       thigh_front_crotch_max=thigh_front_crotch_max,
                       thigh_back_crotch_max=thigh_back_crotch_max,
                       thigh_max_iter=thigh_max_iter, thigh_tol=thigh_tol,
                       piece_gap=piece_gap,
                       seam_allowance=seam_allowance)

    ctx, trace_text = run_with_thigh_closure(m, o, until=until,
                                             trace=bool(trace))

    svg_exp.write_sheet_svg(ctx.sheet, svg)
    print(f"SVG 已输出:{svg}")

    if trace:
        with open(trace, "w", encoding="utf-8") as fp:
            fp.write(trace_text)
        print(f"追踪记录已输出:{trace}")
    if report:
        from .exporters import report as report_exp
        with open(report, "w", encoding="utf-8") as fp:
            fp.write(report_exp.render_report(ctx.sheet, m, ctx.options,
                                              trace_text))
        print(f"报表已输出:{report}")
    return ctx
