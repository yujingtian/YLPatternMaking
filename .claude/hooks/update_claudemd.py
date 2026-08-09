#!/usr/bin/env python
"""Stop 钩子：开发结束后提示 Claude 同步更新 CLAUDE.md。

设计要点
- 防循环：Stop hook 拦截后会再触发一次 Stop；用 stdin 里的 ``stop_hook_active``
  判定——为 True 表示上一轮已要求继续、本轮直接放行，否则会无限套娃。
- 只在「真有开发」时触发：检查 git 工作区是否有除 CLAUDE.md / .claude 之外的
  改动；纯问答/查代码不拦截，省一轮 token。
- 输出 ``{"decision": "block", "reason": ...}``，reason 回喂给 Claude 作为
  本轮的收尾任务：把本次实现细节补进 CLAUDE.md 对应小节。
"""
import json
import subprocess
import sys
from pathlib import Path

# .claude/hooks/update_claudemd.py → 上两级 = 仓库根
REPO = Path(__file__).resolve().parents[2]

# 更新提示：引导 Claude 写进 CLAUDE.md 的正确小节，而不是泛泛重写
_REASON = (
    "本次开发结束。请同步更新 CLAUDE.md，把这次涉及的关键实现细节沉淀进去，"
    "让后续新窗口不必重新摸索：\n"
    "- 新增/改动的步骤函数、公式、PatternOptions 选项 → 更新「关键约定」与"
    "「当前实现状态」小节；\n"
    "- 新的几何 API 用法、命名约定、role/SVG 渲染细节 → 补进「工程速查」对应小节；\n"
    "- 踩过的坑、易读反的坐标方向、Unicode 编辑注意点 → 记到「工程速查」。\n"
    "只补这次真正变化的点，不要重写整篇；写完即结束，无需额外汇报。"
    "若本次其实只是问答、未改动代码，跳过即可。"
)


def code_has_changes() -> bool:
    """工作区里是否有 CLAUDE.md / .claude 之外的改动（含新增未跟踪文件）。"""
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
        # 排除文档自身与钩子配置，避免自激触发
        if path == "CLAUDE.md" or path.startswith(".claude/"):
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

    # 3) 要求 Claude 在停止前同步更新 CLAUDE.md
    json.dump({"decision": "block", "reason": _REASON}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
