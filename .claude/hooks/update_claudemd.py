#!/usr/bin/env python
"""Stop 钩子：开发结束后提示 Claude 按核心/细节分流同步文档。

设计要点
- 防循环：Stop hook 拦截后会再触发一次 Stop；用 stdin 里的 ``stop_hook_active``
  判定为 True 表示上一轮已要求继续、本轮直接放行，否则会无限套娃。
- 只在「真有代码改动」时触发：工作区有除文档（CLAUDE.md / .doc/ / *.md）与
  .claude/ 之外的改动才拦截；纯问答或只改文档不拦截，省一轮 token。
- 输出 {"decision": "block", "reason": ...}，ensure_ascii=True 输出纯 ASCII
  JSON，避免中文在管道里乱码。reason 回喂给 Claude 作收尾任务：实现细节补进
  .doc/python工程设计.md §十，核心约定才改 CLAUDE.md。
"""
import json
import subprocess
import sys
from pathlib import Path

# .claude/hooks/update_claudemd.py → 上两级 = 仓库根
REPO = Path(__file__).resolve().parents[2]

# 更新提示：引导 Claude 按核心/细节分流写进对应文档，而不是泛泛重写
_REASON = """本次开发结束。请按核心/细节分流同步文档，让后续新窗口不必重新摸索：
- 新增/改动的步骤函数、公式、PatternOptions 选项、当前实现状态 → 更新 .doc/python工程设计.md §十（10.6 当前实现状态）；新增步骤文件还要补 CLAUDE.md「文档驱动的开发方式」的改动链条；
- 几何 API 用法、命名约定、role/SVG 渲染、局部特征框、踩过的坑/Unicode 注意点 → 补进 .doc/python工程设计.md §十 对应小节；
- 只有核心全局约定变化（新约定、架构规则、坐标/腰头/调节量方向等）才改 CLAUDE.md「关键约定」。
CLAUDE.md 现在只留核心全局指导，实现细节都在 .doc/python工程设计.md §十，别把细节塞回 CLAUDE.md。只补这次真正变化的点，不要重写整篇；写完即结束，无需额外汇报。若本次只是问答、未改动代码，跳过即可。"""


def code_has_changes() -> bool:
    """工作区里是否有文档（CLAUDE.md / .doc/ / *.md）与 .claude/ 之外的改动（含新增未跟踪文件）。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except Exception:
        # git 不可用就保守不触发，宁可漏一次也别误拦
        return False
    for line in out.splitlines():
        if not line.strip():
            continue
        raw = line[3:]  # 跳过 "XY " 两字符状态 + 空格
        if " -> " in raw:  # 重命名：取目标路径
            raw = raw.split(" -> ", 1)[1]
        path = raw.strip().strip('"')
        # 排除文档（CLAUDE.md/.doc/*.md）与钩子配置，避免自激触发
        if (path == "CLAUDE.md" or path.startswith(".claude/") or path.startswith(".doc/") or path.endswith(".md")):
            continue
        return True
    return False


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    # 1) 防循环：上一轮 Stop hook 已要求继续，本轮不再拦
    if payload.get("stop_hook_active"):
        sys.exit(0)

    # 2) 没有代码改动（纯问答）就不打扰
    if not code_has_changes():
        sys.exit(0)

    # 3) 要求 Claude 在停止前按核心/细节分流同步文档
    json.dump({"decision": "block", "reason": _REASON}, sys.stdout, ensure_ascii=True)


if __name__ == "__main__":
    main()
