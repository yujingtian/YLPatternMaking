"""核对报告渲染：预判/override 轨迹 + 逐键溯源表 + 探针/评分/披露各节。

半自动流程的人工核对界面（plan §report.py）：conf<0.7 标 ⚠，低置信/回退/
丢弃/降级全部披露——报告是提取结果的「为什么」的单一入口。
"""

from __future__ import annotations

from .derive import KeyMeta, MergedView

_WARN_CONF = 0.7


def _cell(s: str) -> str:
    return str(s).replace("|", "∕").replace("\n", " ")


def _conf_mark(conf: float) -> str:
    return f"{conf:.2f}" + ("" if conf >= _WARN_CONF else " ⚠")


def _key_table(rows: list[tuple[str, KeyMeta]]) -> list[str]:
    out = ["| 键 | 值 | 来源 | 置信度 | 依据 |",
           "|---|---|---|---|---|"]
    for key, m in rows:
        out.append(f"| {_cell(key)} | {_cell(_value_str(m.value))} | "
                   f"{m.source} | {_conf_mark(m.confidence)} | "
                   f"{_cell(m.evidence)} |")
    return out


def _value_str(v) -> str:
    if isinstance(v, bool):
        return "有" if v else "无"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def render_extract_report(*, describe: str, photo_count: int, model: str,
                          measurements: dict, evidence: dict,
                          merged: MergedView,
                          derived: dict[str, KeyMeta],
                          issues: list, probe, score_items: list,
                          dropped: list[str], dep_notes: list[str],
                          reverted: list[str],
                          size_path: str = "extracted.toml") -> str:
    """渲染 extract_report.md（probe/score 为鸭子类型：stage/log/verdict）。"""
    out: list[str] = ["# 照片参数提取报告", ""]
    summary = describe.strip().replace("\n", " ")
    if len(summary) > 80:
        summary = summary[:80] + "…"
    out += ["## 一、款式摘要", "",
            f"- 文字描述：{summary}",
            f"- 照片：{photo_count} 张；视觉确认模型：{model}",
            f"- 探针：{probe.stage} "
            + ("通过" if probe.ok else f"**未通过**——{probe.header}"),
            f"- 产物：`{size_path}`（可直接喂 `ylpattern draft --size`）", ""]

    out += ["## 二、款式判定轨迹（预判 vs 照片/描述）", ""]
    out += _key_table([("轴 " + k, m) for k, m in merged.axes.items()]
                      + [("开关 " + k, m) for k, m in merged.switches.items()]
                      + [("枚举 " + k, m) for k, m in merged.enums.items()])

    out += ["", "## 三、尺寸（描述摘录，非模型产出）", ""]
    out += ["| 键 | 值 cm | 摘录 |", "|---|---|---|"]
    for k, v in measurements.items():
        out.append(f"| {k} | {v:g} | {_cell(evidence.get(k, ''))} |")

    out += ["", "## 四、派生参数（查表/派生，evidence 注知识库条目）", ""]
    out += _key_table([(k, m) for k, m in derived.items()])

    out += ["", "## 五、校验与探针", ""]
    if issues:
        out += [f"- {'⚠' if i.level != 'error' else '✕'} "
                f"`{i.param or '—'}`：{i.message}" for i in issues]
    else:
        out.append("- 静态校验无问题")
    out.append("")
    out += [f"- 探针轨迹：{' → '.join(probe.log) if probe.log else '未运行'}"]
    if reverted:
        out.append(f"- **回退/降级键**（{len(reverted)}）：{', '.join(reverted)}")

    out += ["", "## 六、打版后合理性评分", ""]
    if score_items:
        out += ["| 特征 | 实测 | 期望区间 | 判定 |", "|---|---|---|---|"]
        for s in score_items:
            mark = "✓" if s.verdict == "ok" else "⚠"
            out.append(f"| {_cell(s.feature)} | {_cell(s.value)} | "
                       f"{_cell(s.band)} | {mark} |")
    else:
        out.append("- 未运行（--no-score 或打版未成功）")

    disc: list[str] = []
    if dropped:
        disc.append(f"- 模型输出被白名单丢弃：{', '.join(_cell(d) for d in dropped)}")
    if dep_notes:
        disc.extend(f"- 依赖链收口：{n}" for n in dep_notes)
    if not probe.ok:
        disc.append("- 探针未通过：产物仅供人工核查，`--draft` 将拒绝直出")
    if disc:
        out += ["", "## 七、披露"] + disc
    return "\n".join(out) + "\n"
