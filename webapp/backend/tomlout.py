"""尺寸单 toml 导出（web -> CLI 双向兼容：导出的文件可直接作 --size 输入）。"""

from __future__ import annotations


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return f'"{v}"'
    if v is None:
        return '""'   # toml 无 null；空串由加载端按缺省处理（值键留空仅示意见）
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {_fmt(x)}" for k, x in v.items()) + " }"
    return repr(v)


def render_size_toml(measurements: dict, options: dict) -> str:
    lines = ["# YLPattern 尺寸单（web 端导出）",
             "# 可直接用于：python -m ylpattern.cli draft --size 本文件", ""]
    lines.append("[measurements]")
    lines += [f"{k} = {_fmt(v)}" for k, v in measurements.items()
              if not k.startswith("_")]
    lines += ["", "[options]"]
    for k, v in options.items():
        if k.startswith("_") or isinstance(v, dict):
            continue
        lines.append(f"{k} = {_fmt(v)}")
    for k, v in options.items():          # 缝份 dict 走子表，可读性更好
        if isinstance(v, dict):
            lines += ["", f"[options.{k}]"]
            lines += [f"{ek} = {_fmt(ev)}" for ek, ev in v.items()]
    return "\n".join(lines) + "\n"
