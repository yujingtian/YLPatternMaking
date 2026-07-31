"""FlowRunner：按序执行打版步骤，支持中断与追踪（设计文档 §5.4）。"""

from __future__ import annotations

from typing import Callable, Iterable

from ..draft import DraftContext, NamedElement
from ..params import Measurements, PatternOptions

StepFn = Callable[[DraftContext], NamedElement]


class FlowRunner:
    def __init__(self, measurements: Measurements,
                 options: PatternOptions) -> None:
        self.ctx = DraftContext(measurements, options)
        self.trace_log: list[str] = []

    def run(self, flow: Iterable[StepFn], *,
            until: str | None = None,
            trace: bool = False) -> DraftContext:
        """按序执行流程。

        参数：
            until  执行到该步骤（含）后停止，用于输出中间版调版
            trace  逐步记录"步骤名 → 生成元素 → 依据"
        """
        for fn in flow:
            name = fn.__name__
            element = fn(self.ctx)
            if trace:
                self.trace_log.append(
                    f"[{name}] -> {element.name}"
                    + (f"  ({element.basis})" if element.basis else ""))
            if until == name:
                return self.ctx
        return self.ctx

    def trace_text(self) -> str:
        return "\n".join(self.trace_log)
