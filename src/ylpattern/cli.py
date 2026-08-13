"""命令行入口。

用法：
  ylpattern draft --size size.toml --svg out/sheet.svg [--until 步骤名]
                  [--trace out/trace.txt] [--report out/report.txt]
"""

from __future__ import annotations

import argparse
import sys

from .exporters import report as report_exp
from .exporters import svg as svg_exp
from .flows.back_flow import FULL_FLOW
from .flows.closure import run_with_thigh_closure
from .params import Measurements, PatternOptions


def _cmd_draft(args: argparse.Namespace) -> int:
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
        svg_exp.write_sheet_svg(ctx.sheet, args.svg)
        print(f"SVG 已输出：{args.svg}")
    if args.waistband_svg and not args.until:
        from .flows.waistband_flow import build_waistband
        from .exporters import piece_svg as piece_exp
        piece, _wb = build_waistband(ctx)
        piece_exp.write_piece_svg(piece, args.waistband_svg)
        print(f"腰头裁片 SVG 已输出：{args.waistband_svg}")
    elif args.waistband_svg and args.until:
        print("警告：--until 中断调版时不生成腰头裁片（需完整整版提取腰弧净长）",
              file=sys.stderr)
    if args.yoke_svg and not args.until:
        from .flows.yoke_flow import build_yoke
        from .exporters import piece_svg as piece_exp
        piece, _yk = build_yoke(ctx)
        piece_exp.write_piece_svg(piece, args.yoke_svg)
        print(f"机头裁片 SVG 已输出：{args.yoke_svg}")
    elif args.yoke_svg and args.until:
        print("警告：--until 中断调版时不生成机头裁片（需完整整版提取机头边界）",
              file=sys.stderr)
    if args.front_pocket_svg and not args.until:
        from .flows.front_pocket_flow import build_front_pocket
        from .exporters import piece_svg as piece_exp
        if not (ctx.options.front_pocket_facing or ctx.options.front_patch):
            print("警告：未开启 front_pocket_facing/front_patch，跳过前口袋裁片",
                  file=sys.stderr)
        else:
            piece, _fp = build_front_pocket(ctx)
            piece_exp.write_piece_svg(piece, args.front_pocket_svg)
            print(f"前口袋裁片 SVG 已输出：{args.front_pocket_svg}")
    elif args.front_pocket_svg and args.until:
        print("警告：--until 中断调版时不生成前口袋裁片（需完整整版提取口袋净样边界）",
              file=sys.stderr)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ylpattern",
                                     description="牛仔裤数字化打版系统")
    sub = parser.add_subparsers(dest="command", required=True)

    p_draft = sub.add_parser("draft", help="绘制整版（前片/后片流程）")
    p_draft.add_argument("--size", required=True,
                         help="尺寸单路径（.toml 或 .json）")
    p_draft.add_argument("--svg", help="输出整版 SVG 路径")
    p_draft.add_argument("--waistband-svg",
                         help="输出腰头裁片独立 SVG 路径（需完整整版，勿与 --until 同用）")
    p_draft.add_argument("--yoke-svg",
                         help="输出后机头/育克裁片独立 SVG 路径（需完整整版，勿与 --until 同用）")
    p_draft.add_argument("--front-pocket-svg",
                         help="输出前口袋裁片独立 SVG 路径（袋贴 front_pocket_facing / 贴袋 front_patch；需完整整版，勿与 --until 同用）")
    p_draft.add_argument("--until", help="执行到指定步骤（含）后停止")
    p_draft.add_argument("--trace", help="输出逐步绘制追踪记录路径")
    p_draft.add_argument("--report", help="输出尺寸报表路径")
    p_draft.set_defaults(func=_cmd_draft)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
