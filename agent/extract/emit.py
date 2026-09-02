"""发射层：merge/derive 终值 -> 尺寸单 TOML（口径镜像 reverse/emit.py）。

- 手写 TOML 序列化（_fmt/_quote 与 reverse/emit.py 同款实现——平行包
  不共享 import，口径变更两边同步）；
- **发射前回验**：Measurements.from_dict + PatternOptions.from_dict，
  未知键/非法值写文件前拦截；
- 每键行尾 `# 来源：…`（KeyMeta 三元组落注释，人工核对的锚点）；
- 圆整：测量 0.1 / 选项浮点 4 位（int 值浮点写整数，reverse 同款）；
- 段序 [measurements] → [options]（标量在前、dict 子表在后，TOML 硬约束）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ylpattern.params.measurements import Measurements
from ylpattern.params.options import PatternOptions
from .derive import KeyMeta

_MEAS_LABELS = {"waist": "腰围", "hip": "臀围", "knee": "膝围", "hem": "脚口",
                "front_rise": "前浪（含腰头）", "back_rise": "后浪（含腰头）",
                "outseam": "裤长", "thigh": "大腿围"}


def _fmt(v: Any) -> str:
    """TOML 字面量（与 reverse/emit.py 同款；布尔/整数/浮点/串/嵌套数组）。"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return repr(round(v, 4))
    if isinstance(v, str):
        return _quote(v)
    if isinstance(v, (tuple, list)):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    return str(v)


def _quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _meta_comment(m: KeyMeta) -> str:
    ev = m.evidence.replace("\n", " ")
    return f"# 来源：{m.source} conf {m.confidence:.2f} | {ev}"


def build_size_text(measurements: dict[str, float],
                    evidence: dict[str, str],
                    options_meta: dict[str, KeyMeta],
                    header: list[str]) -> str:
    """终值 -> extracted.toml 文本（发射前回验，构造失败上抛不写盘）。"""
    measures = {k: round(float(v), 1) for k, v in measurements.items()}
    opts = {k: m.value for k, m in options_meta.items()}
    Measurements.from_dict(dict(measures))          # 回验：缺键/矛盾即抛
    PatternOptions.from_dict(dict(opts))            # 回验：未知键/越界即抛

    out = ["# " + line for line in header]
    out.append("")
    out.append("[measurements]")
    for k, v in measures.items():
        ev = evidence.get(k, "")
        note = f"    # 来源：描述 | {_MEAS_LABELS.get(k, k)}；{ev}" if ev else ""
        out.append(f"{k} = {_fmt(v)}{note.rstrip('；')}")
    if opts:
        out.append("")
        out.append("[options]")
        for k, m in options_meta.items():
            if isinstance(m.value, dict):
                continue                             # 子表延后
            out.append(f"{k} = {_fmt(m.value)}    {_meta_comment(m)}")
        for k, m in options_meta.items():
            if not isinstance(m.value, dict):
                continue
            out.append("")
            out.append(f"[options.{k}]")
            for kk, vv in m.value.items():
                out.append(f"{kk} = {_fmt(vv)}")
    return "\n".join(out) + "\n"


def write_outputs(out_dir: str, size_text: str,
                  report_text: str | None = None) -> tuple[Path, Path | None]:
    """写 extracted.toml + extract_report.md，返回路径。"""
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    size_path = base / "extracted.toml"
    size_path.write_text(size_text, encoding="utf-8")
    report_path = None
    if report_text is not None:
        report_path = base / "extract_report.md"
        report_path.write_text(report_text, encoding="utf-8")
    return size_path, report_path
