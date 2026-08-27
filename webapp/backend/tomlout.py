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


def render_size_toml(measurements: dict, options: dict,
                     size_run: dict | None = None) -> str:
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
    if size_run:
        lines += _size_run_lines(size_run)
    return "\n".join(lines) + "\n"


def _size_run_lines(size_run: dict) -> list[str]:
    """[size_run] 推板段回写（结构对齐 params/sizerun 规范段）。

    enabled 恒 true（导出即生效：置 false 或删段才退化单码）；band 每段
    8 键全量显式、缺省补 0（输出确定性）；[[size_run.band]] 数组表必须
    在 [size_run] 标量键之后（TOML 语法）。
    """
    from ylpattern.params import MEASURE_KEYS
    lines = ["", "# 推板段（多码推码）：enabled = false 或删段退化单码",
             "", "[size_run]", "enabled = true"]
    for key in ("base", "style", "order"):
        if size_run.get(key) is not None:
            lines.append(f"{key} = {_fmt(size_run[key])}")
    for band in size_run.get("band") or []:
        lines += ["", "[[size_run.band]]",
                  f"sizes = {_fmt(list(band.get('sizes', [])))}"]
        for k in MEASURE_KEYS:
            lines.append(f"{k} = {float(band.get(k, 0))!r}")
    return lines
