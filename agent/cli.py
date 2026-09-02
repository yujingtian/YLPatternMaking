"""agent 命令行入口：`python -m agent extract ...`。

大模型相关命令都挂在这里（ylpattern.cli 只留纯引擎命令 draft/reverse，
2026-09-03 边界）；argparse 保留 subparsers 为二期 serve/会话子命令留位。
退出码语义与迁出前逐位一致：缺 7 必填尺寸 / VLM 配置网络错误 / 探针
未通过拒 --draft 直出 → 2，正常（含 --draft 成功出 SVG）→ 0。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ylpattern.exporters import svg as svg_exp
from ylpattern.flows.closure import run_with_thigh_closure
from ylpattern.params import Measurements, PatternOptions


def _cmd_extract(args: argparse.Namespace) -> int:
    from agent.extract import ExtractError, extract_from_input
    from agent.extract.emit import write_outputs

    try:
        result = extract_from_input(
            describe=args.describe, photos=args.photo, thinking=args.thinking,
            run_probe=not args.no_geometry, run_score=not args.no_score,
            max_refeed=args.max_refeed, config_path=args.config)
    except ExtractError as e:
        if e.missing:
            print(f"错误：{e}\n缺失键清单：{'、'.join(e.missing)}", file=sys.stderr)
        else:
            print(f"错误：{e}", file=sys.stderr)
        return 2
    except RuntimeError as e:   # VLMError 等配置/网络问题（provider 唯一触网层）
        print(f"配置错误：{e}", file=sys.stderr)
        return 2

    size_path, report_path = write_outputs(args.out_dir, result.size_text,
                                           result.report_text)
    if args.report:
        alt = Path(args.report)
        alt.parent.mkdir(parents=True, exist_ok=True)
        alt.write_text(result.report_text, encoding="utf-8")
        report_path = alt
    print(f"尺寸单已输出：{size_path}")
    print(f"核对报告已输出：{report_path}")
    print(f"探针：{result.probe.stage} "
          + ("通过" if result.probe.ok else "未通过（--draft 将拒绝直出）"))
    warns = [s for s in result.score_items if s.verdict == "warn"]
    if warns:
        print(f"合理性警告 {len(warns)} 条（详见报告§六）：", file=sys.stderr)
        for s in warns:
            print(f"  - {s.feature} {s.value}（期望 {s.band}）", file=sys.stderr)

    if args.draft:
        if not result.probe.ok:
            print("错误：探针未通过，拒绝 --draft 直出（退出码 2）",
                  file=sys.stderr)
            return 2
        m = Measurements.from_file(str(size_path))
        o = PatternOptions.from_file(str(size_path))
        ctx, _ = run_with_thigh_closure(m, o)
        svg = str(Path(args.out_dir) / "sheet.svg")
        svg_exp.write_sheet_svg(ctx.sheet, svg, show_labels=o.show_labels)
        print(f"整版 SVG 已输出：{svg}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent",
                                     description="牛仔裤打版 LLM 服务与命令行")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ext = sub.add_parser(
        "extract", help="照片+描述 -> 尺寸单 TOML + 逐键核对报告（半自动）")
    p_ext.add_argument("--describe", required=True,
                       help="文字描述（建议含 7 必填尺寸：腰围/臀围/膝围/脚口/"
                            "前浪/后浪/裤长 + 面料弹力；缺失列清单退出不编数值）")
    p_ext.add_argument("--photo", action="append", default=[],
                       metavar="PATH",
                       help="牛仔裤照片路径，可多次（建议正/背面平铺照；"
                            "无照片走纯描述路径）")
    p_ext.add_argument("--out-dir", default="out",
                       help="输出目录（extracted.toml + extract_report.md）")
    p_ext.add_argument("--draft", action="store_true",
                       help="探针通过后直接出整版 SVG（未通过拒绝直出，退出码 2）")
    p_ext.add_argument("--thinking", choices=("on", "off"),
                       help="推理开关：CLI > vlm.toml > 服务端默认（不发送）")
    p_ext.add_argument("--no-geometry", action="store_true",
                       help="跳过引擎探针（快路径，报告注明，--draft 将不可用）")
    p_ext.add_argument("--no-score", action="store_true",
                       help="跳过打版后合理性评分（快路径）")
    p_ext.add_argument("--config", metavar="PATH",
                       help="VLM 配置路径（缺省找 ./vlm.toml 或环境变量 "
                            "YLP_VLM_*；参照 vlm.toml.example）")
    p_ext.add_argument("--max-refeed", type=int, default=2, metavar="N",
                       help="探针 L1 归因回喂最大轮数（默认 2）")
    p_ext.add_argument("--report", metavar="PATH",
                       help="报告另写路径（缺省 out-dir/extract_report.md）")
    p_ext.set_defaults(func=_cmd_extract)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
