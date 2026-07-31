"""DraftSheet：整张版的元素容器。

前片、后片在同一坐标系、同一张版上依次绘制（先画后裁，见设计文档 §一）。
元素只增不改；提供按名称/类型/步骤的查询。
"""

from __future__ import annotations

from typing import Iterator, TypeVar

from .elements import NamedElement, NamedPoint, NamedLine, NamedCurve


class DraftSheet:
    def __init__(self) -> None:
        self._elements: list[NamedElement] = []
        self._by_name: dict[str, NamedElement] = {}

    def add(self, element: NamedElement) -> None:
        if element.name in self._by_name:
            raise ValueError(f"元素名重复：{element.name}（已由 "
                             f"{self._by_name[element.name].step} 生成）")
        self._elements.append(element)
        self._by_name[element.name] = element

    def get(self, name: str) -> NamedElement:
        try:
            return self._by_name[name]
        except KeyError:
            raise KeyError(f"版上不存在元素 '{name}'，"
                           f"请检查流程顺序或步骤名") from None

    def __contains__(self, name: str) -> bool:
        return name in self._by_name

    def __iter__(self) -> Iterator[NamedElement]:
        return iter(self._elements)

    T = TypeVar("T", bound=NamedElement)

    def of_type(self, cls: type[T]) -> list[T]:
        return [e for e in self._elements if isinstance(e, cls)]

    @property
    def points(self) -> list[NamedPoint]:
        return self.of_type(NamedPoint)

    @property
    def lines(self) -> list[NamedLine]:
        return self.of_type(NamedLine)

    @property
    def curves(self) -> list[NamedCurve]:
        return self.of_type(NamedCurve)
