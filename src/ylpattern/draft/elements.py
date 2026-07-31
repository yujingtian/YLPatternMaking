"""具名绘图元素：所有绘制产物的载体，携带身份三重信息。

- name：语义名（如 "front.crotch_point"）
- step：生成它的步骤函数名
- basis：依据（公式/文档章节），用于报表与调试
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from ..geometry import Point, LineSegment, CubicBezier


@dataclass(frozen=True)
class NamedPoint:
    name: str
    geom: Point
    step: str
    basis: str = ""
    label: str = ""    # 中文标注（SVG/报表显示用，缺省回退 name）


@dataclass(frozen=True)
class NamedLine:
    name: str
    geom: LineSegment
    step: str
    basis: str = ""
    label: str = ""
    role: str = "ref"    # 线型角色：ref 参考线（虚线）/ struct 结构线（实线）


@dataclass(frozen=True)
class NamedCurve:
    name: str
    geom: CubicBezier
    step: str
    basis: str = ""
    label: str = ""


NamedElement = Union[NamedPoint, NamedLine, NamedCurve]
