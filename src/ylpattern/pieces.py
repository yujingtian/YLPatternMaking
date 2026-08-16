"""裁片层：PatternPiece -- 独立裁片的三态载体（净样/缩水/毛样）。

设计文档 §5.6：裁片 = 净样轮廓 + 对位记号 + 丝缕线 + 标注，
经裁切层（cutter.py）应用缩水与缝边后填充毛样态。

腰头裁片为首例落地（腰头裁片.md §五）；本模块保持通用，供后续前/后片
等裁片复用。依赖方向：cutter/pieces -> draft -> geometry -> params
（裁切层在流程层之上、输出层之下，禁止反向）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import CubicBezier, LineSegment, Point


@dataclass(frozen=True)
class PieceEdge:
    """裁片的一条命名边（闭合轮廓的一段）。

    name 取语义边名（腰头：top/bottom/left_end/right_end）；
    geom 为直线段或三次贝塞尔曲线。
    """
    name: str
    geom: LineSegment | CubicBezier


@dataclass(frozen=True)
class PatternPiece:
    """独立裁片：净样 -> 缩水 -> 毛样三态（腰头裁片.md §五）。

    net_edges      步骤层绘制的净样轮廓（直线/贝塞尔，精确，先画后裁的"画"产物）；
    shrunk_edges   apply_shrinkage 后的含缩水净样（仿射缩放保持贝塞尔性，§五.2）；
    gross_polygon  add_seam_allowance 后的毛样裁切轮廓（采样折线，§五.3）-- 缝边
                   外扩为折线近似（曲线真法向 offset 留待精化）。
    notches / shrunk_notches / gross_notches
                   三态刀口；毛样刀口 = 缩水后刀口（刀口标在缝合线=缩水净样边上，
                   缝份向外另裁，§五.3 注）。
    """
    name: str                                   # 裁片名（如 "waistband"）
    label: str                                  # 中文标注
    net_edges: tuple[PieceEdge, ...]            # 净样闭合轮廓（有序）
    notches: tuple[Point, ...] = ()             # 净样刀口（在轮廓上）
    grain: LineSegment | None = None            # 丝缕线（净样坐标系）
    shrunk_edges: tuple[PieceEdge, ...] = ()    # 缩水后净样轮廓
    shrunk_notches: tuple[Point, ...] = ()
    gross_polygon: tuple[Point, ...] = ()       # 毛样裁切轮廓（折线，闭合）
    gross_notches: tuple[Point, ...] = ()
    notes: tuple[str, ...] = ()                 # 裁切过程记录（缩水率/缝份等）
    marks: tuple[LineSegment | CubicBezier, ...] = ()
                                                # 内部标记弧线（净样坐标，随缩水
                                                #   同比例变换，前片裁片.md §3.3；
                                                #   如袋贴必须保留的袋口净线/省弧线
                                                #   前口袋裁片.md §1.1、前片内部
                                                #   辅助线 臀围/膝围/毗围线）

    def with_shrunk(self, edges: tuple[PieceEdge, ...],
                    notches: tuple[Point, ...]) -> "PatternPiece":
        return PatternPiece(self.name, self.label, self.net_edges,
                            self.notches, self.grain, edges, notches,
                            self.gross_polygon, self.gross_notches, self.notes,
                            self.marks)

    def with_gross(self, polygon: tuple[Point, ...],
                   notches: tuple[Point, ...],
                   notes: tuple[str, ...]) -> "PatternPiece":
        return PatternPiece(self.name, self.label, self.net_edges,
                            self.notches, self.grain, self.shrunk_edges,
                            self.shrunk_notches, polygon, notches, notes,
                            self.marks)
