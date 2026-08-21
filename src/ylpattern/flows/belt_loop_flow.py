"""裤耳独立裁片流程：净尺寸长方形直接成片（裤耳裁片.md §1~§4）。

build_belt_loop(main_ctx) 不从整版提取边界--裤耳是纯净尺寸裁片
（§2 尺寸计算即成品净尺寸集合），整根连裁一条（车缝时再剪断）：
  宽 = belt_loop_width（成品净宽，§2）；
  长 = belt_loop_unit_length × belt_loop_count + belt_loop_waste
      （单根成品长 × 总根数 + 裁剪/车缝损耗，§2）。
无缝边无缝份（§1 毛边/不折边设计），不进 cutter（无缩水、无缝边、
无刀口）--净样四边即毛样轮廓，gross_polygon 直接取净样角点。

丝缕（§3）：直丝缕（经向）= 长度方向，局部系 Y 向下竖向贯穿；与前后片
主体经向一致由排料保证（裁片自身只标方向，§3 原理说明）。
裁片内部标记（§4）：款号/数量/净裁工艺备注走 notes 与 label（SVG 标注）。
自含裁片，非 FlowRunner 编排（同 watch_pocket_flow.build_watch_pocket
口径）；main_ctx 仅取 options，不依赖整版几何（可独立构建）。
"""

from __future__ import annotations

from ..draft import DraftContext
from ..geometry import LineSegment, Point
from ..pieces import PatternPiece, PieceEdge


def build_belt_loop(main_ctx: DraftContext) \
        -> tuple[PatternPiece, DraftContext]:
    """构建裤耳裁片：净宽 × (单根长 × 根数 + 损耗) 长方形（裤耳裁片.md §2）。

    返回 (PatternPiece, 局部 DraftContext)：前者供 SVG/DXF 输出，后者含
    命名元素供 trace/调试。净裁无缝份，毛样 = 净样四角。
    """
    o = main_ctx.options
    w = o.belt_loop_width
    length = o.belt_loop_unit_length * o.belt_loop_count + o.belt_loop_waste
    # 局部系 Y 向下（与 piece_svg 口径一致）：长度方向竖直向下 = 经向
    pts = (Point(0.0, 0.0), Point(w, 0.0),
           Point(w, length), Point(0.0, length))
    net_edges = (
        PieceEdge("top", LineSegment(pts[0], pts[1])),
        PieceEdge("side", LineSegment(pts[1], pts[2])),
        PieceEdge("bottom", LineSegment(pts[2], pts[3])),
        PieceEdge("side", LineSegment(pts[3], pts[0])),
    )
    # 丝缕线：竖向贯穿（bbox 中心 x，上下各留 15% 边距，同小表袋口径）
    margin = length * 0.15
    grain = LineSegment(Point(w / 2.0, margin), Point(w / 2.0, length - margin))
    piece = PatternPiece(
        "belt_loop", "裤耳裁片", net_edges, grain=grain,
        notes=(f"净裁：宽 {w:.2f} × 长 {length:.2f} cm"
               f"（单根 {o.belt_loop_unit_length:.2f} × "
               f"{o.belt_loop_count} 根 + 损耗 {o.belt_loop_waste:.2f}，"
               "裤耳裁片.md §2）",
               "毛边/不折边，无缝份（裤耳裁片.md §1）",
               "共裁 1 条，车缝时剪断（裤耳裁片.md §1）"))
    # 净裁：毛样轮廓 = 净样角点（无缝边，不走 cutter）
    piece = piece.with_gross(pts, (), piece.notes)
    # 局部 ctx 留命名元素供 trace/调试
    local = DraftContext(main_ctx.measurements, o)
    step = "build_belt_loop"
    for i, e in enumerate(net_edges):
        local.add_line(f"belt_loop.edge{i}", e.geom, step=step,
                       basis=f"裤耳裁片净样边 {e.name}（裤耳裁片.md §2）",
                       label=f"{e.name}边{i}")
    return piece, local
