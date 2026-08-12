---
name: code-stats
description: 统计项目中各类语言的代码量（文件数 / 空行 / 注释行 / 代码行）。当用户想了解代码规模、语言分布、某个目录或某种语言有多少代码、要求“代码统计 / 统计各语言代码情况 / 代码行数 / 多少行代码 / count lines / cloc 风格报告”时使用。自带零依赖 Python 脚本，输出按语言分组的表格，支持逐文件明细与 JSON。
---

# 代码统计 (code-stats)

按语言分类统计代码量，输出 cloc 风格的「文件数 / 空行 / 注释行 / 代码行」表格。脚本位于本目录的 `count.py`，仅用 Python 标准库，跨平台。

## 何时使用

用户问到下列任意一种时触发：

- “统计一下代码情况 / 各语言的代码 / 代码量 / 代码规模”
- “这个项目有多少行代码 / 某目录有多少代码”
- “按语言统计 / 语言分布 / 哪种语言最多”
- “count lines / cloc / lines of code”

## 如何运行

在**仓库根目录**执行（脚本默认统计当前目录）：

```bash
python .claude/skills/code-stats/count.py              # 整个仓库
python .claude/skills/code-stats/count.py src          # 指定子目录
python .claude/skills/code-stats/count.py src --by-file  # 附逐文件明细
python .claude/skills/code-stats/count.py --sort files   # 按文件数排序
python .claude/skills/code-stats/count.py --json         # JSON 输出（便于画图/二次处理）
```

参数：

| 参数 | 说明 |
| --- | --- |
| `路径` | 待统计的目录或单文件，默认当前目录 |
| `--by-file` | 在汇总表后追加逐文件明细（按代码行降序） |
| `--sort` | `code`(默认) / `files` / `lang` |
| `--json` | 输出 JSON，键为语言名，末尾 `__total__` 为合计 |

脚本规则：
- 按扩展名识别语言（Python `#` 与三引号、C 系 `//` 与 `/* */`、HTML `<!-- -->`、TOML/YAML/Shell `#`、SQL `--` 等均有注释识别；Markdown/JSON/Text 全部计为内容行）。
- 整行只有注释 → 注释行；既有代码又有注释 → 代码行；空白 → 空行。
- 自动排除生成物：`__pycache__/`、`*.egg-info/`、`node_modules/`、`venv/`、`out/`、`.git/`、`.pyc` 等二进制后缀。

## 如何呈现结果

1. **默认把表格原样贴给用户**——它是等宽对齐的，直接放在代码块里可读。
2. 表格下方附**一两句解读**：指出主体语言及其代码行占比、代码行/总行比例。例如“Python 占主体（7,313 行，约 72% 代码行），文档量(Markdown)与代码量比例约 1:3”。
3. 用户若问“哪个文件最大”等，追加 `--by-file` 再贴明细。
4. 用户若要画图/做仪表盘，用 `--json` 并把输出交给后续步骤处理。

## 注意

- 若在子目录下运行，请先用脚本绝对路径或先 `cd` 到仓库根，避免路径歧义。
- 注释识别为行级简化（不解析字符串内的注释符），与 cloc 行为一致，足够用于规模评估。
