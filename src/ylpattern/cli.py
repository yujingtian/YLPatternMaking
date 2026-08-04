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
from .flows.runner import FlowRunner
from .params import Measurements, PatternOptions


def _cmd_draft(args: argparse.Namespace) -> int:
    m = Measurements.from_file(args.size)
    o = PatternOptions.from_file(args.size)

    runner = FlowRunner(m, o)
    want_trace = bool(args.trace)
    ctx = runner.run(FULL_FLOW, until=args.until, trace=want_trace)

    if args.until and not any(t.startswith(f"[{args.until}]")
                              for t in runner.trace_log) \
            and args.until not in [f.__name__ for f in FULL_FLOW]:
        print(f"警告：流程中不存在步骤 '{args.until}'，已执行全部步骤",
              file=sys.stderr)

    if args.svg:
        svg_exp.write_sheet_svg(ctx.sheet, args.svg)
        print(f"SVG 已输出：{args.svg}")
    if want_trace:
        with open(args.trace, "w", encoding="utf-8") as fp:
            fp.write(runner.trace_text())
        print(f"追踪记录已输出：{args.trace}")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fp:
            fp.write(report_exp.render_report(
                ctx.sheet, m, o, runner.trace_text()))
        print(f"报表已输出：{args.report}")
    if not (args.svg or args.trace or args.report):
        print(report_exp.render_report(ctx.sheet, m, o, runner.trace_text()))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ylpattern",
                                     description="牛仔裤数字化打版系统")
    sub = parser.add_subparsers(dest="command", required=True)

    p_draft = sub.add_parser("draft", help="绘制整版（前片/后片流程）")
    p_draft.add_argument("--size", required=True,
                         help="尺寸单路径（.toml 或 .json）")
    p_draft.add_argument("--svg", help="输出整版 SVG 路径")
    p_draft.add_argument("--until", help="执行到指定步骤（含）后停止")
    p_draft.add_argument("--trace", help="输出逐步绘制追踪记录路径")
    p_draft.add_argument("--report", help="输出尺寸报表路径")
    p_draft.set_defaults(func=_cmd_draft)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
