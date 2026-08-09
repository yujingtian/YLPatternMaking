"""公式层：纯函数公式库，与打版文档章节一一对应。

约束：只依赖标准库；输入输出均为 float 基础类型。
"""

from . import hip, leg, crotch, waist, thigh, fly

__all__ = ["hip", "leg", "crotch", "waist", "thigh", "fly"]
