"""agent 命令行入口：`python -m agent extract ...`。

大模型相关命令都挂在这里（ylpattern.cli 只留纯引擎命令 draft/reverse，
2026-09-03 边界）；argparse 保留 subparsers 为二期 serve/会话子命令留位。
退出码语义与迁出前逐位一致：缺 7 必填尺寸 / VLM 配置网络错误 / 探针
未通过拒 --draft 直出 → 2，正常（含 --draft 成功出 SVG）→ 0。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ylpattern.exporters import svg as svg_exp
from ylpattern.flows.closure import run_with_thigh_closure
from ylpattern.params import Measurements, PatternOptions


def _cmd_extract(args: argparse.Namespace) -> int:
    from agent.extract import ExtractError, extract_from_input
    from agent.extract.emit import write_outputs

    # 进度走 stderr（stdout 留给产物路径等结论行）：累计秒数 + 一句阶段话
    t0 = time.monotonic()

    def progress(message: str) -> None:
        print(f"[agent] {time.monotonic() - t0:6.1f}s {message}",
              file=sys.stderr, flush=True)

    try:
        result = extract_from_input(
            describe=args.describe, photos=args.photo, thinking=args.thinking,
            run_probe=not args.no_geometry, run_score=not args.no_score,
            max_refeed=args.max_refeed, config_path=args.config,
            progress=progress)
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
        progress("--draft：重跑整版并写 SVG…")
        m = Measurements.from_file(str(size_path))
        o = PatternOptions.from_file(str(size_path))
        ctx, _ = run_with_thigh_closure(m, o)
        svg = str(Path(args.out_dir) / "sheet.svg")
        svg_exp.write_sheet_svg(ctx.sheet, svg, show_labels=o.show_labels)
        print(f"整版 SVG 已输出：{svg}")
    return 0


def _cmd_chat(args: argparse.Namespace) -> int:
    """交互式多轮（智能体一期）：一行一轮；:photo 补照片、:quit 退出。

    零打扰口径：全料喂齐直接交卷；缺尺寸批量问一次（卡片），答完重画。
    """
    from agent.converse import render_milestones, run_turn
    from agent.extract.emit import write_outputs
    from agent.session import Session

    t0 = time.monotonic()

    def progress(message: str) -> None:
        print(f"[agent] {time.monotonic() - t0:6.1f}s {message}",
              file=sys.stderr, flush=True)

    session = Session()
    photos: list[str] = list(args.photo)
    # Windows 管道 stdin 按 locale（cp936）解码会把 UTF-8 喂入读成代理对
    # 乱码（交互式控制台走 WinAPI 宽字符不受影响）——统一按 UTF-8 读、
    # 坏字节替换不炸：解析不到就多问一轮，符合零打扰兜底。
    enc = getattr(sys.stdin, "encoding", None)
    if enc and enc.lower().replace("-", "") != "utf8":
        try:
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass
    print("〔chat〕用一句描述开始（建议含 7 必填尺寸）；一行一轮。",
          "补照片：:photo 路径；退出：:quit", flush=True)
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        if line == ":quit":
            print("未交卷退出（无产物）", file=sys.stderr)
            return 1
        if line.startswith(":photo"):
            path = line.partition(" ")[2].strip()
            if not path:
                print("用法：:photo 路径", file=sys.stderr)
                continue
            photos.append(path)
            print(f"已登记照片（累计 {len(photos)} 张）", flush=True)
            continue
        try:
            outcome = run_turn(session, line, photos, config_path=args.config,
                               thinking=args.thinking,
                               run_probe=not args.no_geometry,
                               run_score=not args.no_score,
                               max_refeed=args.max_refeed,
                               progress=progress)
        except RuntimeError as e:   # VLMError 等配置/网络（provider 唯一触网层）
            print(f"配置错误：{e}", file=sys.stderr)
            return 2
        session = outcome.session
        if outcome.card is not None:
            print(f"〔问〕{outcome.card.message}", flush=True)
            continue

        result = outcome.result
        size_path, report_path = write_outputs(args.out_dir, result.size_text,
                                               result.report_text)
        print(f"尺寸单已输出：{size_path}")
        print(f"核对报告已输出：{report_path}")
        print(f"探针：{result.probe.stage} "
              + ("通过" if result.probe.ok else "未通过（--draft 拒直出）"))
        review = outcome.delivery["review"]
        if review["reverted"]:
            print(f"待确认（探针自愈回退，引擎默认接管）："
                  f"{'、'.join(review['reverted'])}", flush=True)
        if review["low_confidence"]:
            print(f"待确认（低置信惯例预填）："
                  f"{'、'.join(review['low_confidence'])}", flush=True)
        if review["score_warnings"]:
            print(f"合理性警告：{'、'.join(review['score_warnings'])}"
                  "（详见报告§六）", file=sys.stderr)
        if args.draft:
            if not result.probe.ok:
                print("错误：探针未通过，拒绝 --draft 直出（退出码 2）",
                      file=sys.stderr)
                return 2
            progress("--draft：重跑整版并写 SVG…")
            m = Measurements.from_file(str(size_path))
            o = PatternOptions.from_file(str(size_path))
            ctx, _ = run_with_thigh_closure(m, o)
            svg = str(Path(args.out_dir) / "sheet.svg")
            svg_exp.write_sheet_svg(ctx.sheet, svg, show_labels=o.show_labels)
            print(f"整版 SVG 已输出：{svg}")
            if args.staged:
                for p in render_milestones(m, o, args.out_dir):
                    print(f"中间版已输出：{p}")
        return 0
    print("输入结束未交卷（无产物）", file=sys.stderr)
    return 1


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

    p_chat = sub.add_parser(
        "chat", help="多轮对话打版（智能体一期：缺啥问啥、能画就画、零打扰）")
    p_chat.add_argument("--photo", action="append", default=[],
                        metavar="PATH",
                        help="初始照片路径，可多次；会话中「:photo 路径」随时补")
    p_chat.add_argument("--out-dir", default="out",
                        help="输出目录（交卷时写 extracted.toml + 报告）")
    p_chat.add_argument("--draft", action="store_true",
                        help="探针通过后直接出整版 SVG")
    p_chat.add_argument("--staged", action="store_true",
                        help="--draft 时另出三里程碑中间版 SVG（版生长过程）")
    p_chat.add_argument("--thinking", choices=("on", "off"),
                        help="推理开关：CLI > vlm.toml > 服务端默认（不发送）")
    p_chat.add_argument("--no-geometry", action="store_true",
                        help="跳过引擎探针（快路径，--draft 不可用）")
    p_chat.add_argument("--no-score", action="store_true",
                        help="跳过打版后合理性评分（快路径）")
    p_chat.add_argument("--config", metavar="PATH",
                        help="VLM 配置路径（缺省找 ./vlm.toml 或环境变量）")
    p_chat.add_argument("--max-refeed", type=int, default=2, metavar="N",
                        help="探针 L1 归因回喂最大轮数（默认 2）")
    p_chat.set_defaults(func=_cmd_chat)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
