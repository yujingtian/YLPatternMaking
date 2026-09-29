"""数值选项「很大的值」审计（2026-09-29，用户报障 watch_pocket_width=50
表单项不红 -> 统一检查同类）。

对构造期无上界守卫的全部数值选项，注入荒谬大值（默认×10 / 零默认 +20 /
负默认 ×10 更负），过 build_issues + 引擎 + diagnose_runtime 三关，分类：
  A 构造期拦住            —— 建议值守卫已覆盖（红 + 修复按钮即时）
  B 运行期失败+归因本键    —— 生成后红落在用户改的字段上（合格）
  C 运行期失败+归因他键    —— 红落在别的字段（假归因，需上界守卫救）
  D 引擎不失败            —— 静默出怪版型或无效果（需上界守卫裁决）

用法：python scripts/audit_option_bounds.py [--out out/audit_bounds.md]
"""

from __future__ import annotations

import argparse
import io
import sys
from dataclasses import fields, replace
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from ylpattern.flows.closure import run_with_thigh_closure  # noqa: E402
from ylpattern.flows.diagnose import diagnose_runtime  # noqa: E402
from ylpattern.params import Measurements, PatternOptions  # noqa: E402
from ylpattern.params.validate import build_issues  # noqa: E402

M_BASE = dict(waist=68, hip=91, knee=44, hem=34,
              front_rise=25, back_rise=33, outseam=102, thigh=58)
# 全特征绿色基线（watch_pocket 用 custom 模式：facing_intersect 默认几何
# 与 hip=91 组合是已知引擎缺口——见内存 watch-pocket-default-geometry-gap，
# 不属本审计对象；缺它不妨碍其它特征字段的大值扫描）
O_BASE = dict(front_pocket=True, front_pocket_facing=True, front_pouch=True,
              watch_pocket=True, watch_pocket_mode="custom",
              back_yoke=True, back_patch=True, belt_loop=True, fly=True,
              back_dart=True)


def absurd(default: float) -> float:
    if default > 0:
        return default * 10
    if default < 0:
        return default * 10
    return 20.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="out/audit_bounds.md")
    args = parser.parse_args()

    base = PatternOptions.from_dict(O_BASE)
    no_upper: list[tuple[str, float]] = []
    for f in fields(PatternOptions):
        d = f.default
        if not isinstance(d, (int, float)) or isinstance(d, bool):
            continue
        try:
            replace(base, **{f.name: d * 10})
        except Exception:
            continue                       # 已有守卫（含上界/关系对）
        no_upper.append((f.name, d))

    rows: list[tuple[str, str, str]] = []   # (field, cls, detail)
    for name, d in no_upper:
        val = absurd(d)
        o = dict(O_BASE, **{name: val})
        issues = build_issues(M_BASE, o)
        hit = [i for i in issues if i.param == name]
        if hit:
            rows.append((name, "A 构造期", hit[0].message))
            continue
        try:
            run_with_thigh_closure(Measurements.from_dict(M_BASE),
                                   PatternOptions.from_dict(o))
            rows.append((name, "D 引擎不失败", f"{name}={val} 引擎静默接受"))
            continue
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
        result = diagnose_runtime(M_BASE, o, msg,
                                  max_probes=16, budget_s=60.0)
        params = [i.param for i in result]
        if params == [name]:
            rows.append((name, "B 运行期+归因本键", msg))
        else:
            rows.append((name, f"C 归因{'无' if not params else str(params)}",
                         msg))

    order = {"A 构造期": 0, "B 运行期+归因本键": 1}
    rows.sort(key=lambda r: (order.get(r[1], 2), r[0]))

    lines = [f"# 数值选项大值审计（{len(no_upper)} 个无上界字段）", "",
             "| 字段 | 分类 | 详情 |", "|---|---|---|"]
    for name, cls, detail in rows:
        lines.append(f"| `{name}` | {cls} | {detail} |")
    text = "\n".join(lines) + "\n"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    counts: dict[str, int] = {}
    for _, cls, _ in rows:
        counts[cls] = counts.get(cls, 0) + 1
    print("## 汇总")
    for cls, n in sorted(counts.items()):
        print(f"  {cls}: {n}")


if __name__ == "__main__":
    main()
