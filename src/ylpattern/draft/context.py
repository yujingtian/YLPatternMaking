"""DraftContext：步骤函数之间唯一的协作通道。

规则（设计文档 §5.2）：步骤函数只能通过 context 读取前面步骤的元素，
禁止函数间直接传参几何体 —— 保证任意中断点处的 sheet 都完整自洽。
"""

from __future__ import annotations

from ..geometry import Point, LineSegment, CubicBezier
from ..params import Measurements, PatternOptions
from .elements import NamedElement, NamedPoint, NamedLine, NamedCurve
from .sheet import DraftSheet


class DraftContext:
    def __init__(self, measurements: Measurements,
                 options: PatternOptions) -> None:
        self.measurements = measurements
        self.options = options
        self.sheet = DraftSheet()

    # ---- 上版（步骤函数调用，自动记录来源步骤名） ----

    def add_point(self, name: str, geom: Point, step: str,
                  basis: str = "", label: str = "") -> NamedPoint:
        el = NamedPoint(name, geom, step, basis, label)
        self.sheet.add(el)
        return el

    def add_line(self, name: str, geom: LineSegment, step: str,
                 basis: str = "", label: str = "", role: str = "ref") -> NamedLine:
        el = NamedLine(name, geom, step, basis, label, role)
        self.sheet.add(el)
        return el

    def add_curve(self, name: str, geom: CubicBezier, step: str,
                  basis: str = "", label: str = "",
                  role: str = "struct") -> NamedCurve:
        el = NamedCurve(name, geom, step, basis, label, role)
        self.sheet.add(el)
        return el

    # ---- 取前面步骤的元素 ----

    def _get_typed(self, name: str, cls: type, kind: str):
        el = self.sheet.get(name)
        if not isinstance(el, cls):
            raise TypeError(f"元素 '{name}' 是 {type(el).__name__}，不是{kind}")
        return el.geom

    def point(self, name: str) -> Point:
        return self._get_typed(name, NamedPoint, "点")

    def line(self, name: str) -> LineSegment:
        return self._get_typed(name, NamedLine, "线")

    def curve(self, name: str) -> CubicBezier:
        return self._get_typed(name, NamedCurve, "曲线")
