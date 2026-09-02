"""照片提取金标集评测：cases/*/describe.txt + truth.toml -> markdown 报告。

用法：
  python scripts/eval_extract.py --cases tests/_extract_golden [--config vlm.toml]
      [--out out/eval_extract.md] [--tol 0.5] [--baseline out/eval_prev.md]

口径（设计文档 §8 / plan §6）：
- 8 键召回率 / 编造率（结果里有、真值没有的尺寸键）；
- 数值键 MAE / 超差比例（|--tol|，默认 0.5cm）、开关与枚举命中率；
- 探针通过率 / stage 分布（L0=零回喂）/ 评分警告率；
- --baseline 上一轮报告 -> 总指标两列对比（判据/词典改动前后必须跑）。

真值 truth.toml 与产物同构（[measurements]/[options]）；case 带 photos/ 且
无 VLM 配置时该用例记错误（照片用例需 --config）。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - 3.10 环境
    import tomli as tomllib

try:
    from agent.extract import ExtractError, extract_from_input
except ImportError:                          # 未在仓库根运行时兜底
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from agent.extract import ExtractError, extract_from_input


def _load_truth(path: Path) -> dict:
    with open(path, "rb") as fp:
        data = tomllib.load(fp)
    return {"measurements": data.get("measurements", {}),
            "options": data.get("options", {})}


def _fmt_val(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def run_case(case: Path, *, config_path: str | None, tol: float) -> dict:
    """单用例评测：返回指标行 + 不命中明细（异常用例记 error 不中断全局）。"""
    truth = _load_truth(case / "truth.toml")
    describe = (case / "describe.txt").read_text(encoding="utf-8")
    photos = sorted(str(p) for p in (case / "photos").glob("*")) \
        if (case / "photos").is_dir() else []
    row: dict = {"case": case.name, "photos": len(photos), "misses": [],
                 "error": None, "probe_ok": False, "stage": "—", "warns": 0}
    try:
        result = extract_from_input(describe=describe, photos=photos,
                                    config_path=config_path)
    except (ExtractError, RuntimeError) as e:
        row["error"] = str(e)[:120]
        return row

    row["probe_ok"] = bool(result.probe.ok)
    row["stage"] = result.probe.stage
    row["warns"] = sum(1 for s in result.score_items if s.verdict == "warn")

    tm, to = truth["measurements"], truth["options"]
    got_m = {k: round(float(v), 1) for k, v in result.measurements.items()}
    hit = sum(1 for k, v in tm.items()
              if k in got_m and abs(got_m[k] - float(v)) < 0.05)
    row["meas_hit"], row["meas_total"] = hit, len(tm)
    row["fabricated"] = sorted(set(got_m) - set(tm))

    opts = result.options_dict()
    num_hit = num_all = bool_hit = bool_all = 0
    abs_err = 0.0
    over = 0
    for k, tv in to.items():
        gv = opts.get(k)
        if gv is None:
            row["misses"].append(f"`{k}`：真值 {_fmt_val(tv)}，未发射")
            continue
        if isinstance(tv, bool) or isinstance(gv, bool):
            bool_all += 1
            if bool(tv) is bool(gv):
                bool_hit += 1
            else:
                row["misses"].append(
                    f"`{k}`：真值 {_fmt_val(tv)}，实测 {_fmt_val(gv)}")
        elif isinstance(tv, (int, float)):
            num_all += 1
            diff = float(gv) - float(tv)
            abs_err += abs(diff)
            if abs(diff) > tol:
                over += 1
                row["misses"].append(
                    f"`{k}`：真值 {tv:g}，实测 {_fmt_val(gv)}（差 {diff:+.2f}）")
        else:
            bool_all += 1                      # 枚举/串按同口径计命中率
            if str(tv) == str(gv):
                bool_hit += 1
            else:
                row["misses"].append(
                    f"`{k}`：真值 {_fmt_val(tv)}，实测 {_fmt_val(gv)}")
    row["num_all"], row["num_over"] = num_all, over
    row["num_abs_err"] = abs_err
    row["cat_hit"], row["cat_all"] = bool_hit, bool_all
    return row


def _summary(rows: list[dict]) -> list[tuple[str, str]]:
    n = len(rows)
    ok = [r for r in rows if not r["error"]]
    meas_t = sum(r.get("meas_total", 0) for r in ok)
    meas_h = sum(r.get("meas_hit", 0) for r in ok)
    num_a = sum(r.get("num_all", 0) for r in ok)
    cat_a = sum(r.get("cat_all", 0) for r in ok)
    cat_h = sum(r.get("cat_hit", 0) for r in ok)
    fab = sum(len(r.get("fabricated", ())) for r in ok)
    return [
        ("用例", f"{n}（照片用例 {sum(r['photos'] for r in rows)}，"
               f"错误 {n - len(ok)}）"),
        ("8 键召回", f"{meas_h}/{meas_t}"
         + (f" = {meas_h / meas_t:.0%}" if meas_t else "")),
        ("编造尺寸键", f"{fab}（结果有真值无，应为 0）"),
        ("数值键 MAE", f"{sum(r.get('num_abs_err', 0.0) for r in ok) / num_a:.3f}cm"
         f"（{num_a} 键）" if num_a else "—"),
        ("数值键超差", f"{sum(r.get('num_over', 0) for r in ok)}/{num_a}"
         + (f" = {sum(r.get('num_over', 0) for r in ok) / num_a:.0%}"
            if num_a else "")),
        ("开关/枚举命中", f"{cat_h}/{cat_a}"
         + (f" = {cat_h / cat_a:.0%}" if cat_a else "")),
        ("探针通过", f"{sum(1 for r in ok if r['probe_ok'])}/{n}"),
        ("stage 分布", ", ".join(f"{s}:{sum(1 for r in ok if r['stage'] == s)}"
                               for s in sorted({r['stage'] for r in ok}))),
        ("评分警告", f"{sum(1 for r in ok if r['warns'])}/{len(ok)}"
         f"（共 {sum(r['warns'] for r in ok)} 条）"),
    ]


def render(rows: list[dict], *, model: str, tol: float,
           baseline: str | None) -> str:
    out = ["# 照片提取评测报告", "",
           f"- 时间：{datetime.now():%Y-%m-%d %H:%M}；模型：{model}；"
           f"数值容差 {tol}cm", ""]
    out += ["## 总指标", "", "| 指标 | 值 |", "|---|---|"]
    summ = _summary(rows)
    for k, v in summ:
        out.append(f"| {k} | {v} |")
    if baseline:
        out += ["", f"## 基线对比（{baseline}）", "", "见上一轮报告总指标；"
                "判据/词典改动前后各跑一次人工对照。"]
    out += ["", "## 每用例明细", ""]
    for r in rows:
        out.append(f"### {r['case']}（照片 {r['photos']} 张，探针 {r['stage']}"
                   f" {'通过' if r['probe_ok'] else '未通过'}）")
        if r["error"]:
            out.append(f"- **错误**：{r['error']}")
        for m in r["misses"]:
            out.append(f"- {m}")
        if not r["error"] and not r["misses"]:
            out.append("- 全部命中")
        out.append("")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="照片提取金标集评测")
    ap.add_argument("--cases", default="tests/_extract_golden/cases")
    ap.add_argument("--config", help="VLM 配置路径（照片用例必需）")
    ap.add_argument("--out", default="out/eval_extract.md")
    ap.add_argument("--tol", type=float, default=0.5, help="数值键容差 cm")
    ap.add_argument("--baseline", help="上一轮报告路径（总指标对比）")
    args = ap.parse_args(argv)

    root = Path(args.cases)
    cases = sorted(p for p in root.iterdir() if (p / "describe.txt").is_file()) \
        if root.is_dir() else []
    if not cases:
        print(f"错误：{root} 下无用例（需 describe.txt + truth.toml）",
              file=sys.stderr)
        return 2

    from agent.extract.provider import VLMConfig
    try:
        model = VLMConfig.load(args.config).model
    except RuntimeError as e:
        if any((c / "photos").is_dir() and
               list((c / "photos").iterdir()) for c in cases):
            print(f"错误：照片用例需 VLM 配置（{e}）", file=sys.stderr)
            return 2
        model = "（纯描述路径，未调用模型）"

    rows = [run_case(c, config_path=args.config, tol=args.tol) for c in cases]
    text = render(rows, model=model, tol=args.tol,
                  baseline=args.baseline)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"评测报告已输出：{out}")
    for k, v in _summary(rows):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
