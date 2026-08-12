#!/usr/bin/env python3
"""代码统计：按语言分类统计 文件数 / 空行 / 注释行 / 代码行。

零第三方依赖（仅标准库），跨平台。用法：

    python count.py [路径] [--by-file] [--sort code|files|lang] [--json]
    python count.py                 # 统计当前目录
    python count.py src             # 统计指定目录
    python count.py --by-file       # 附带逐文件明细
    python count.py --json          # 输出 JSON（便于进一步处理）

设计要点
- 按扩展名映射语言，每种语言声明「行注释符」与「块注释定界符」。
- 行分类规则（与 cloc 对齐）：
    * 空白行 → blank
    * 整行只有注释 → comment
    * 既有代码又有注释 → code（行首不是注释符即视为代码）
    * 其余 → code
- 块注释（Python 三引号、C 的 /* */、HTML 的 <!-- -->）用状态机跨行跟踪。
- 默认排除生成物目录与二进制后缀（呼应本项目 .gitignore：__pycache__/egg-info/out）。
- 读取用 UTF-8 + errors="replace"，对 GBK 等编码容错，不报错中断。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

# 排除的目录名（任意层级命中即跳过整棵子树）
EXCLUDE_DIRS = {
    ".git", ".hg", ".svn",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    "node_modules", "bower_components", "jspm_packages",
    ".venv", "venv", "env", ".env", "virtualenv",
    "dist", "build", "target", "out", ".eggs",
    ".idea", ".vscode", ".cache",
}
# 排除的扩展名（二进制 / 生成物）
EXCLUDE_EXT = {
    ".pyc", ".pyo", ".pyd", ".class", ".jar", ".war",
    ".so", ".o", ".a", ".dll", ".dylib", ".lib",
    ".exe", ".bin", ".obj", ".pdb", ".woff", ".woff2",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",
    ".zip", ".gz", ".tar", ".tgz", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".egg-info",  # 作为扩展名片段兜底
}
# 跳过超过此大小的单文件（避免误读巨型生成文件，5 MB）
MAX_FILE_BYTES = 5 * 1024 * 1024

# 扩展名 → (语言名, 行注释符|None, (块开头, 块结尾)|None)
LANGUAGES: dict[str, tuple[str, str | None, tuple[str, str] | None]] = {
    # Python 系
    ".py":  ("Python",     "#",  ('"""', '"""')),
    ".pyi": ("Python",     "#",  ('"""', '"""')),
    # C / C++ / Java / JS / TS / Go / Rust / C# / Swift / Kotlin / PHP 系（// 与 /* */）
    ".c":     ("C",         "//", ("/*", "*/")),
    ".h":     ("C/C++",     "//", ("/*", "*/")),
    ".cpp":   ("C++",       "//", ("/*", "*/")),
    ".cc":    ("C++",       "//", ("/*", "*/")),
    ".cxx":   ("C++",       "//", ("/*", "*/")),
    ".hpp":   ("C++",       "//", ("/*", "*/")),
    ".java":  ("Java",      "//", ("/*", "*/")),
    ".js":    ("JavaScript","//", ("/*", "*/")),
    ".mjs":   ("JavaScript","//", ("/*", "*/")),
    ".cjs":   ("JavaScript","//", ("/*", "*/")),
    ".jsx":   ("JavaScript","//", ("/*", "*/")),
    ".ts":    ("TypeScript","//", ("/*", "*/")),
    ".tsx":   ("TypeScript","//", ("/*", "*/")),
    ".go":    ("Go",        "//", ("/*", "*/")),
    ".rs":    ("Rust",      "//", ("/*", "*/")),
    ".cs":    ("C#",        "//", ("/*", "*/")),
    ".swift": ("Swift",     "//", ("/*", "*/")),
    ".kt":    ("Kotlin",    "//", ("/*", "*/")),
    ".kts":   ("Kotlin",    "//", ("/*", "*/")),
    ".scala": ("Scala",     "//", ("/*", "*/")),
    ".php":   ("PHP",       "//", ("/*", "*/")),
    ".dart":  ("Dart",      "//", ("/*", "*/")),
    # hash 行注释系
    ".rb":    ("Ruby",      "#", None),
    ".sh":    ("Shell",     "#", None),
    ".bash":  ("Shell",     "#", None),
    ".zsh":   ("Shell",     "#", None),
    ".ps1":   ("PowerShell","#", None),
    ".yaml":  ("YAML",      "#", None),
    ".yml":   ("YAML",      "#", None),
    ".toml":  ("TOML",      "#", None),
    ".ini":   ("INI",       "#", None),
    ".cfg":   ("INI",       ";", None),
    ".dockerfile": ("Dockerfile", "#", None),
    ".tf":    ("Terraform", "#", None),
    # dash 行注释
    ".sql":   ("SQL",       "--", ("/*", "*/")),
    # 仅块注释
    ".css":   ("CSS",       None, ("/*", "*/")),
    ".scss":  ("SCSS",      "//", ("/*", "*/")),
    ".less":  ("Less",      "//", ("/*", "*/")),
    ".html":  ("HTML",      None, ("<!--", "-->")),
    ".htm":   ("HTML",      None, ("<!--", "-->")),
    ".xml":   ("XML",       None, ("<!--", "-->")),
    ".vue":   ("Vue",       "//", ("<!--", "-->")),
    ".svelte":("Svelte",    "//", ("<!--", "-->")),
    # 不区分注释的文本类（全部计为内容行）
    ".md":    ("Markdown",  None, None),
    ".markdown": ("Markdown", None, None),
    ".json":  ("JSON",      None, None),
    ".json5": ("JSON5",     "//", None),
    ".jsonc": ("JSON",      "//", None),
    ".txt":   ("Text",      None, None),
    ".csv":   ("CSV",       None, None),
    ".tsv":   ("CSV",       None, None),
    # 其它脚本
    ".lua":   ("Lua",       "--", ("--[[", "]]")),
    ".pl":    ("Perl",      "#",  None),
    ".r":     ("R",         "#",  None),
    ".jl":    ("Julia",     "#",  None),
    ".ex":    ("Elixir",    "#",  None),
    ".exs":   ("Elixir",    "#",  None),
    ".erl":   ("Erlang",    "%",  None),
    ".vim":   ("Vim Script", '"', None),
    ".elm":   ("Elm",       "--", ("{-", "-}")),
    ".hs":    ("Haskell",   "--", ("{-", "-}")),
}


@dataclass
class LangStat:
    """单个语言的累计统计。"""
    files: int = 0
    blank: int = 0
    comment: int = 0
    code: int = 0
    # 逐文件明细（仅 --by-file 时填充）：[(相对路径, blank, comment, code), ...]
    rows: list[tuple[str, int, int, int]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.blank + self.comment + self.code


def should_skip_dir(name: str) -> bool:
    if name in EXCLUDE_DIRS:
        return True
    # 包生成目录：*.egg-info / *.dist-info / *.egg-link
    return name.endswith((".egg-info", ".dist-info", ".egg-link"))


def language_of(path: str) -> tuple[str, str | None, tuple[str, str] | None] | None:
    """返回 (语言名, 行注释符, 块定界) 或 None（未识别 / 应跳过）。"""
    # Dockerfile / Makefile 这类无扩展名的命名文件
    base = os.path.basename(path).lower()
    if base in {"dockerfile", "makefile", "gemfile", "rakefile"}:
        if base == "makefile":
            return "Makefile", "#", None
        return base.capitalize(), "#", None
    # 兜底：.egg-info 是目录名而非扩展名，这里按片段排除
    if ".egg-info" in base:
        return None
    ext = os.path.splitext(base)[1].lower()
    if not ext or ext in EXCLUDE_EXT:
        return None
    info = LANGUAGES.get(ext)
    if info is None:
        return None
    return info


def classify_file(path: str, line_comment: str | None,
                  block: tuple[str, str] | None) -> tuple[int, int, int]:
    """逐行分类，返回 (blank, comment, code)。读取异常返回 (0, 0, 0)。"""
    blank = comment = code = 0
    in_block = False
    b_open, b_close = block if block else (None, None)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    blank += 1
                    continue
                if in_block:
                    # 仍处于块注释中：本行算注释；若出现结束符则关闭
                    if b_close and b_close in line:
                        in_block = False
                    comment += 1
                    continue
                # 不在块中：先看是否进入块注释
                if b_open and line.startswith(b_open):
                    # 单行块（同一行出现结束符）
                    rest = line[len(b_open):]
                    if b_close and b_close in rest:
                        comment += 1
                    else:
                        in_block = True
                        comment += 1
                    continue
                if line_comment and line.startswith(line_comment):
                    comment += 1
                    continue
                code += 1
    except OSError:
        return (0, 0, 0)
    return (blank, comment, code)


def walk(root: str):
    """递归生成 (相对路径, 绝对路径)，跳过排除目录与二进制后缀。"""
    for dirpath, dirnames, filenames in os.walk(root):
        # 原地改 dirnames，阻止 os.walk 进入排除目录
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for fn in filenames:
            ap = os.path.join(dirpath, fn)
            try:
                if os.path.isfile(ap) and os.path.getsize(ap) <= MAX_FILE_BYTES:
                    rel = os.path.relpath(ap, root)
                    yield rel, ap
            except OSError:
                continue


def collect(root: str, by_file: bool) -> dict[str, LangStat]:
    stats: dict[str, LangStat] = {}
    for rel, ap in walk(root):
        info = language_of(ap)
        if info is None:
            continue
        lang, line_c, block = info
        b, c, k = classify_file(ap, line_c, block)
        st = stats.setdefault(lang, LangStat())
        st.files += 1
        st.blank += b
        st.comment += c
        st.code += k
        if by_file:
            st.rows.append((rel.replace("\\", "/"), b, c, k))
    return stats


def fmt_int(n: int) -> str:
    """千分位分组，便于阅读大数字。"""
    return f"{n:,}"


def render_table(stats: dict[str, LangStat], sort: str) -> str:
    order = sorted(
        stats.items(),
        key=lambda kv: (-kv[1].code, -kv[1].files, kv[0])
        if sort == "code"
        else (-kv[1].files, -kv[1].code, kv[0])
        if sort == "files"
        else (kv[0],),
    )
    # 列宽：按表头与数据取最大
    headers = ["语言", "文件", "空行", "注释", "代码", "合计"]
    rows = [
        [lang, fmt_int(s.files), fmt_int(s.blank), fmt_int(s.comment),
         fmt_int(s.code), fmt_int(s.total)]
        for lang, s in order
    ]
    tot = LangStat()
    for _, s in order:
        tot.files += s.files
        tot.blank += s.blank
        tot.comment += s.comment
        tot.code += s.code
    total_row = ["合计", fmt_int(tot.files), fmt_int(tot.blank),
                 fmt_int(tot.comment), fmt_int(tot.code), fmt_int(tot.total)]

    width = [max(len(str(h)), max((len(r[i]) for r in rows), default=0),
              len(total_row[i])) for i, h in enumerate(headers)]

    ncol = len(headers)

    def fmt_row(r):
        # 语言列左对齐，数值列右对齐
        return "  ".join(
            str(r[i]).ljust(width[i]) if i == 0 else str(r[i]).rjust(width[i])
            for i in range(ncol))
    sep = "  ".join("-" * width[i] for i in range(ncol))
    lines = ["  ".join(headers[i].ljust(width[i]) if i == 0 else headers[i].rjust(width[i])
                       for i in range(ncol)), sep]
    lines += [fmt_row(r) for r in rows]
    lines += [sep, fmt_row(total_row)]
    out = "\n".join(lines)
    if tot.files:
        # 代码占比便于快速判断主体语言
        pct = tot.code / tot.total * 100 if tot.total else 0
        out += f"\n\n代码行 / 总行 = {fmt_int(tot.code)} / {fmt_int(tot.total)} ({pct:.1f}%)"
    return out


def render_by_file(stats: dict[str, LangStat]) -> str:
    lines: list[str] = []
    for lang, s in sorted(stats.items()):
        if not s.rows:
            continue
        lines.append(f"\n## {lang}（{fmt_int(s.files)} 文件）")
        lines.append(f"{'文件':<50} {'空行':>6} {'注释':>6} {'代码':>6}")
        lines.append("-" * 72)
        for rel, b, c, k in sorted(s.rows, key=lambda r: -r[3]):
            lines.append(f"{rel[:50]:<50} {b:>6,} {c:>6,} {k:>6,}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    # 统一以 UTF-8 输出，避免 Windows 控制台 / 管道中文乱码
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(
        description="按语言统计代码量（文件数 / 空行 / 注释行 / 代码行）")
    p.add_argument("path", nargs="?", default=".",
                   help="待统计的目录或文件（默认当前目录）")
    p.add_argument("--by-file", action="store_true",
                   help="在汇总表后追加逐文件明细")
    p.add_argument("--sort", choices=["code", "files", "lang"], default="code",
                   help="汇总表排序：代码行(默认) / 文件数 / 语言名")
    p.add_argument("--json", action="store_true",
                   help="以 JSON 输出（含逐语言与总计，便于程序处理）")
    args = p.parse_args(argv)

    root = args.path
    if not os.path.exists(root):
        print(f"错误：路径不存在：{root}", file=sys.stderr)
        return 2

    # 单文件：直接定位其语言统计
    if os.path.isfile(root):
        info = language_of(root)
        if info is None:
            print(f"未识别的文件类型：{root}", file=sys.stderr)
            return 1
        lang, line_c, block = info
        b, c, k = classify_file(root, line_c, block)
        stats = {lang: LangStat(1, b, c, k,
                                [(root, b, c, k)] if args.by_file else [])}
    else:
        stats = collect(root, args.by_file)

    if args.json:
        payload = {
            lang: {
                "files": s.files, "blank": s.blank,
                "comment": s.comment, "code": s.code, "total": s.total,
            }
            for lang, s in stats.items()
        }
        tot = LangStat()
        for s in stats.values():
            tot.files += s.files
            tot.blank += s.blank
            tot.comment += s.comment
            tot.code += s.code
        payload["__total__"] = {
            "files": tot.files, "blank": tot.blank,
            "comment": tot.comment, "code": tot.code, "total": tot.total,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not stats:
        print(f"在 {root} 下未找到可统计的源码文件。")
        return 0

    print(render_table(stats, args.sort))
    if args.by_file:
        print(render_by_file(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
