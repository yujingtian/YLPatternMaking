"""命令行入口（纯引擎命令；大模型相关命令在 agent/cli.py，
`python -m agent extract ...`，2026-09-03 边界：ylpattern 零 LLM 代码）。

用法：
  ylpattern draft --size size.toml --svg out/sheet.svg [--until 步骤名]
                  [--trace out/trace.txt] [--report out/report.txt]
  ylpattern reverse --dxf 工厂.dxf --size out/reverse.toml [--report …]
                    [--style auto|5015|5028] [--probe]
"""

from __future__ import annotations

import argparse
import sys

from .exporters import report as report_exp
from .exporters import svg as svg_exp
from .flows.back_flow import FULL_FLOW
from .flows.closure import run_with_thigh_closure
from .params import Measurements, PatternOptions


def _cmd_draft_size_run(args: argparse.Namespace) -> int:
    """多码推码模式（--size 含 [size_run] 段时自动进入，推码方案步 4）：
    逐码参数化重打版 -> 多码单文件裁片 DXF；整版 SVG/追踪/报表只出基码。"""
    if args.until:
        print("错误：--until 调版与多码推码互斥（临时调版请复制尺寸单删 "
              "[size_run] 段走单码模式）", file=sys.stderr)
        return 2
    if not args.pieces_dxf:
        print("错误：多码推码模式需 --pieces-dxf 指定输出 DXF 路径",
              file=sys.stderr)
        return 2
    ignored = [flag for flag, path in (
        ("--waistband-svg", args.waistband_svg),
        ("--yoke-svg", args.yoke_svg),
        ("--front-pocket-svg", args.front_pocket_svg),
        ("--front-pouch-svg", args.front_pouch_svg),
        ("--front-fly-single-svg", args.front_fly_single_svg),
        ("--front-fly-double-svg", args.front_fly_double_svg),
        ("--watch-pocket-svg", args.watch_pocket_svg),
        ("--belt-loop-svg", args.belt_loop_svg),
        ("--back-patch-svg", args.back_patch_svg),
        ("--front-piece-svg", args.front_piece_svg),
        ("--back-piece-svg", args.back_piece_svg)) if path]
    if ignored:
        print(f"提示：多码模式忽略逐片 SVG 参数 {' '.join(ignored)}"
              "（整版输出只出基码）", file=sys.stderr)
    from .api import run_size_run
    run_size_run(args.size, pieces_dxf=args.pieces_dxf,
                 svg=args.svg, trace=args.trace, report=args.report)
    return 0


def _cmd_draft(args: argparse.Namespace) -> int:
    from .params import load_size_run
    if load_size_run(args.size) is not None:      # 尺码表探测：多码推码模式
        return _cmd_draft_size_run(args)
    m = Measurements.from_file(args.size)
    o = PatternOptions.from_file(args.size)

    want_trace = bool(args.trace)
    ctx, trace_text = run_with_thigh_closure(m, o, until=args.until,
                                             trace=want_trace)

    if args.until and not any(t.startswith(f"[{args.until}]")
                              for t in trace_text.splitlines()) \
            and args.until not in [f.__name__ for f in FULL_FLOW]:
        print(f"警告：流程中不存在步骤 '{args.until}'，已执行全部步骤",
              file=sys.stderr)

    if args.svg:
        svg_exp.write_sheet_svg(ctx.sheet, args.svg, show_labels=o.show_labels)
        print(f"SVG 已输出：{args.svg}")
    if args.dxf:
        from .exporters import dxf as dxf_exp
        dxf_exp.write_sheet_dxf(ctx.sheet, args.dxf)
        print(f"DXF 已输出：{args.dxf}")
    # 裁片独立 SVG/DXF 需完整整版，--until 中断调版时不生成；传 --pieces-dxf
    # 或任一裁片 SVG 时经 collect_pieces 固定顺序全收集（推码方案步 2：
    # 收敛 api/cli 平行分支），按片名映射写 SVG、末尾一并出 DXF
    svg_map = {
        "waistband": args.waistband_svg, "back_yoke": args.yoke_svg,
        "front_facing": args.front_pocket_svg,
        "front_patch": args.front_pocket_svg,
        "front_pouch": args.front_pouch_svg,
        "front_fly_single": args.front_fly_single_svg,
        "front_fly_double": args.front_fly_double_svg,
        "watch_pocket": args.watch_pocket_svg, "belt_loop": args.belt_loop_svg,
        "back_patch": args.back_patch_svg, "front_piece": args.front_piece_svg,
        "back_piece": args.back_piece_svg,
    }
    want_any_piece = any(v for v in svg_map.values()) or bool(args.pieces_dxf)
    if want_any_piece and args.until:
        print("警告：--until 中断调版时不生成裁片（裁片需完整整版提取净样边界）",
              file=sys.stderr)
    if want_any_piece and not args.until:
        from .flows.collect import collect_pieces
        from .exporters import piece_svg as piece_exp
        pieces, skips = collect_pieces(ctx)
        if args.pieces_dxf:
            for msg in skips:
                print(f"警告：{msg}", file=sys.stderr)
        else:
            names = {p.name for p in pieces}
            for piece_name, out in svg_map.items():
                if out and piece_name not in names:
                    print(f"警告：裁片 {piece_name} 未开启或依赖不满足，"
                          "跳过其 SVG 输出", file=sys.stderr)
        for piece in pieces:
            out = svg_map.get(piece.name)
            if out:
                piece_exp.write_piece_svg(piece, out,
                                          show_seam=o.show_seam_allowance)
                print(f"{piece.label} SVG 已输出：{out}")
        if args.pieces_dxf:
            from .exporters import piece_dxf
            piece_dxf.write_pieces_dxf(pieces, args.pieces_dxf,
                                       size=ctx.options.size_label,
                                       show_seam=o.show_seam_allowance)
            print(f"裁片合集 DXF 已输出：{args.pieces_dxf}")
    if want_trace:
        with open(args.trace, "w", encoding="utf-8") as fp:
            fp.write(trace_text)
        print(f"追踪记录已输出：{args.trace}")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fp:
            fp.write(report_exp.render_report(
                ctx.sheet, m, ctx.options, trace_text))
        print(f"报表已输出：{args.report}")
    if not (args.svg or args.trace or args.report):
        print(report_exp.render_report(ctx.sheet, m, ctx.options, trace_text))
    return 0


def _cmd_reverse(args: argparse.Namespace) -> int:
    """工厂 DXF 反解析（.doc/工厂DXF逆向解析.md）：层 1+2+3 -> 尺寸单 TOML。"""
    try:
        from .reverse import ReverseError, reverse_dxf
        res = reverse_dxf(args.dxf, style=args.style, probe_only=args.probe)
    except (ReverseError, RuntimeError, OSError) as e:
        # ReverseError=口径失配 / RuntimeError=ezdxf 缺失 / OSError=文件不存在
        print(f"错误：{e}", file=sys.stderr)
        return 2

    from .reverse.emit import build_size_file, write_size_file
    from .reverse.report import render_reverse_report

    if args.probe:
        text = render_reverse_report(res.doc, res.profile, res.roles,
                                     None, "", {}, None, [], None)
        if args.report:
            with open(args.report, "w", encoding="utf-8") as fp:
                fp.write(text)
            print(f"探查报告已输出：{args.report}")
        else:
            print(text)
        return 0

    size_run = res.size_run or None
    data = build_size_file(res.measured[res.base], res.options, size_run)
    header = [f"工厂 DXF 反解析尺寸单（款型档案 {res.profile.key}）",
              f"源文件：{args.dxf}",
              f"基码：{res.base}；缩水 横{res.calib.weft:.0%}/直{res.calib.warp:.0%}"
              f"（{res.calib.source}）",
              "回环：ylpattern draft --size 本文件 --svg out/sheet.svg"]
    if args.size:
        write_size_file(args.size, data, header)
        print(f"尺寸单已输出：{args.size}")
    text = render_reverse_report(res.doc, res.profile, res.roles, res.calib,
                                 res.base, res.measured, res.options,
                                 res.warns, size_run)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fp:
            fp.write(text)
        print(f"反解析报告已输出：{args.report}")
    else:
        print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ylpattern",
                                     description="牛仔裤数字化打版系统")
    sub = parser.add_subparsers(dest="command", required=True)

    p_rev = sub.add_parser(
        "reverse", help="工厂 DXF 反解析 -> 尺寸单 TOML（层1 8键+层2 选项+层3 档差）")
    p_rev.add_argument("--dxf", required=True,
                       help="工厂 DXF 路径（布衣科技 R12/mm 口径；款型档案"
                            "外的款先用 --probe 看件清单）")
    p_rev.add_argument("--size", help="输出尺寸单 TOML 路径（--probe 时不写）")
    p_rev.add_argument("--report", help="输出人读报告路径（缺省打印到终端）")
    p_rev.add_argument("--style", default="auto",
                       help="款型档案：auto 自动识别（头标 STYLE NAME -> 块名"
                            "款号多数表决）/ 显式款号（5015、5028）")
    p_rev.add_argument("--probe", action="store_true",
                       help="只读取+识别出件清单报告，不标定不测量不写 TOML")
    p_rev.set_defaults(func=_cmd_reverse)

    p_draft = sub.add_parser("draft", help="绘制整版（前片/后片流程）")
    p_draft.add_argument("--size", required=True,
                         help="尺寸单路径（.toml 或 .json）；文件含 [size_run] 段且"
                              " enabled = true 时进入多码推码模式（需 --pieces-dxf，"
                              "整版 SVG/追踪/报表只出基码；enabled = false 或删段走单码）")
    p_draft.add_argument("--svg", help="输出整版 SVG 路径")
    p_draft.add_argument("--waistband-svg",
                         help="输出腰头裁片独立 SVG 路径（需完整整版，勿与 --until 同用）")
    p_draft.add_argument("--yoke-svg",
                         help="输出后机头/育克裁片独立 SVG 路径（需完整整版，勿与 --until 同用）")
    p_draft.add_argument("--front-pocket-svg",
                         help="输出前口袋裁片独立 SVG 路径（袋贴 front_pocket_facing / 贴袋 front_patch；需完整整版，勿与 --until 同用）")
    p_draft.add_argument("--front-pouch-svg",
                         help="输出袋布裁片独立 SVG 路径（front_pouch 开启；一片式对折，需完整整版，勿与 --until 同用）")
    p_draft.add_argument("--front-fly-single-svg",
                         help="输出单排（单层）门襟裁片独立 SVG 路径（fly_separate 开启；需完整整版，勿与 --until 同用）")
    p_draft.add_argument("--front-fly-double-svg",
                         help="输出双排（对折）门襟裁片独立 SVG 路径（fly_separate + fly_sep_double 开启；需完整整版，勿与 --until 同用）")
    p_draft.add_argument("--watch-pocket-svg",
                         help="输出小表袋裁片独立 SVG 路径（watch_pocket 开启；按 watch_pocket_mode 派发，需完整整版，勿与 --until 同用）")
    p_draft.add_argument("--belt-loop-svg",
                         help="输出裤耳裁片独立 SVG 路径（belt_loop 开启；净宽×总长长方形整根连裁，净裁无缝份，勿与 --until 同用）")
    p_draft.add_argument("--back-patch-svg",
                         help="输出后贴袋裁片独立 SVG 路径（back_patch 开启（依赖 back_yoke）；四形态净样+袋口折边，需完整整版，勿与 --until 同用）")
    p_draft.add_argument("--front-piece-svg",
                         help="输出前片裁片独立 SVG 路径（弯腰头剥离/口袋挖削/连裁门襟三形态净边装配；需完整整版，勿与 --until 同用）")
    p_draft.add_argument("--back-piece-svg",
                         help="输出后片裁片独立 SVG 路径（剥离腰头/机头三形态净边装配+浪尖折角+刀口投影；需完整整版，勿与 --until 同用）")
    p_draft.add_argument("--dxf",
                         help="输出整版 DXF 路径（R12/mm 裁床兼容，曲线按 0.1mm 弦高公差离散；需可选依赖：pip install 'ylpattern[dxf]'）")
    p_draft.add_argument("--pieces-dxf",
                         help="输出全部裁片合集 DXF 路径（开启开关的裁片平铺合一张，功能图层 CUT/NET/SHRUNK/MARK/GRAIN/DRILL/NOTCH/TEXT；R12/mm，需完整整版且 ezdxf）")
    p_draft.add_argument("--until", help="执行到指定步骤（含）后停止")
    p_draft.add_argument("--trace", help="输出逐步绘制追踪记录路径")
    p_draft.add_argument("--report", help="输出尺寸报表路径")
    p_draft.set_defaults(func=_cmd_draft)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
