"""DXF 输出：全部独立裁片平铺合一张（AAMA/ASTMA 服装 CAD 口径；R12 / mm）。

与 piece_svg.py 的差异：
- **AAMA 结构**：服装 CAD（ET/富怡/格柏）不识别自定义英文层名与散线
  裁片。每片定义为一个 BLOCK（片内局部 mm 坐标），Model Space 仅放
  INSERT 引用（插入点 = 平铺偏移）；图层用 AAMA 数字层（见 _LAYER_MAP）。
- 坐标：裁片局部系 **Y 向下**，块内变换 X=(x-x0)*10、Y=(y1-y)*10
  --翻转后 DXF（Y 向上）显示与 SVG 屏幕视觉逐点重合，手性不变
  （裁片不镜像，裁床切出的物理片与 SVG 打印件一致）；平铺偏移全部
  落在 INSERT 插入点上，块内容与片一一对应。
- 刀口 = 图层 4 POINT，必须附组码 30（Z 深度，默认 1.524）与组码 50
  （开口角度，取刀口法向在 mm 输出系方向；缺角度 CAD 不知开口朝向、
  不显示）；且 ET 按裁切折线**顶点**吸附挂接刀口符号，段中间的刀口点
  不显示（腰头刀口恰与阶梯角顶点重合而能显示、机头延长线交点全在段中
  而不显示，即此坑）-> 裁切折线把刀口点共线插入为顶点（几何不变）；
  图层 3 存普通轮廓顶点/放码点，非刀口层。定位孔 = 图层 13
  单纯 POINT（CAD 读 AAMA 见层 13 POINT 自动渲染标准、不受缩放影响的
  钻孔符号）。丝缕线省略箭头仅 LINE + TEXT "GRAIN"。
- AAMA 裁片信息：块中央三行 TEXT（PIECE/SIZE/QTY，size/qty 由调用方
  传入，默认 "-" / 1）。
- 全 ASCII：块名/标注取 piece.name 与净长宽数字，中文 label 留在 SVG。
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

from ..geometry import Point, Vector
from ..pieces import PatternPiece
from . import _dxf_base as base

PIECE_GAP_CM = 3.0      # 平铺片间距
ROW_LIMIT_CM = 200.0    # 行宽上限（典型裁床门幅内）

UNITS_NOTE = "UNITS=MM (DXF R12)"
AAMA_NOTE = "ANSI/AAMA"

# 语义层 -> AAMA 数字图层映射（服装 CAD 只认数字层名，自定义英文名
# 解析失败是 ET 08 等老软件黑屏的主因之一）：
#   1=外轮廓/裁切线（含片名与信息文本）、8=净样/缝合线（含缩水净样与
#   内部画线）、3=普通轮廓顶点/放码点（勿放刀口）、4=刀口专属层
#   （POINT 附组码 30/50）、13=定位孔专属层（POINT 自动渲染钻孔符号）、
#   7=纱向线
_LAYER_MAP: dict[str, str] = {
    "CUT": "1",
    "NET": "8",
    "SHRUNK": "8",
    "MARK": "8",
    "NOTCH": "4",   # 刀口专属层（层 3 是普通轮廓顶点/放码点）
    "DRILL": "13",  # 定位孔专属层（CAD 自动渲染钻孔符号）
    "GRAIN": "7",
    "TEXT": "1",
}

_LAYERS: dict[str, base.LayerSpec] = {
    "1": (7, "CONTINUOUS"),   # 毛样裁切轮廓（闭合折线）+ 文本
    "8": (8, "DASHED"),       # 净样/缝合线（含缩水净样 + 内部画线）
    "4": (4, "CONTINUOUS"),   # 刀口（POINT + 组码 30=1.524 / 50=角度）
    "13": (6, "CONTINUOUS"),  # 定位孔（POINT，自动渲染钻孔符号）
    "7": (5, "CONTINUOUS"),   # 丝缕线
}

_BLOCK_NAME_RE = re.compile(r"[^A-Za-z0-9_]")
BLOCK_NAME_MAX = 31          # R12 符号表名长度上限


def _piece_bounds(piece: PatternPiece) -> tuple[float, float, float, float]:
    """裁片全内容 bbox（含 marks/drills，DXF 输出应完整；比 piece_svg 的
    _bounds 口径更宽，供平铺布局用）。"""
    xs: list[float] = []
    ys: list[float] = []

    def add(p: Point) -> None:
        xs.append(p.x)
        ys.append(p.y)

    for p in piece.gross_polygon:
        add(p)
    for edges in (piece.net_edges, piece.shrunk_edges):
        for e in edges:
            for p in base.flatten_geom(e.geom):
                add(p)
    for g in piece.marks:
        for p in base.flatten_geom(g):
            add(p)
    for p in piece.notches + piece.shrunk_notches + piece.gross_notches:
        add(p)
    for p in piece.drills:
        add(p)
    if piece.grain is not None:
        add(piece.grain.a)
        add(piece.grain.b)
    if not xs:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), min(ys), max(xs), max(ys)


def _layout(pieces: Sequence[PatternPiece], gap_cm: float
            ) -> list[tuple[PatternPiece, float, float]]:
    """shelf 行装箱：按传入顺序左->右摆放，行内底边对齐（bbox 下沿同高），
    累计行宽超 ROW_LIMIT_CM 换行，行高取该行最高片。返回 (piece, offx, offy)。"""
    placements: list[tuple[PatternPiece, float, float]] = []
    x = 0.0
    y = 0.0
    row_h = 0.0
    for piece in pieces:
        x0, _y0, x1, y1 = _piece_bounds(piece)
        w = x1 - x0
        h = y1 - _y0
        if placements and x + w > ROW_LIMIT_CM:
            x = 0.0
            y += row_h + gap_cm
            row_h = 0.0
        placements.append((piece, x, y))
        x += w + gap_cm
        row_h = max(row_h, h)
    return placements


def _notch_segment(p: Point, polygon: tuple[Point, ...]
                   ) -> tuple[Point, Point]:
    """刀口方向短线（SVG 口径共用）：p 在毛样轮廓上，取垂直轮廓、指向裁片
    内部（质心方向）的 NOTCH_LEN_CM 短线；轮廓缺失/退化时回退竖直向下
    （局部系 Y 向下，与 piece_svg 刀口 y+4px 向下同口径）。
    DXF 用其方向（内法向）换算刀口 POINT 的组码 50 开口角度--层 4 刀口
    必须带 30/50 组码才显示（见 _render_piece_into 刀口段）。"""
    n = len(polygon)
    if n < 3:
        return p, p + Vector(0.0, base.NOTCH_LEN_CM)
    idx = min(range(n), key=lambda i: p.distance_to(polygon[i]))
    tangent = polygon[(idx + 1) % n] - polygon[(idx - 1) % n]
    if tangent.length < 1e-12:
        normal = Vector(0.0, 1.0)
    else:
        normal = tangent.normalized().perpendicular()
    cx = sum(q.x for q in polygon) / n
    cy = sum(q.y for q in polygon) / n
    inward = Vector(cx - p.x, cy - p.y)
    if inward.dx * normal.dx + inward.dy * normal.dy < 0.0:
        normal = Vector(-normal.dx, -normal.dy)
    return p, p + normal.scale(base.NOTCH_LEN_CM)


def _block_name(piece_name: str, used: set[str]) -> str:
    """AAMA 块名：ASCII 大写下划线、<=31 字符、全局唯一（重名加序号）。"""
    name = _BLOCK_NAME_RE.sub("_", piece_name).upper()[:BLOCK_NAME_MAX]
    if not name:
        name = "PIECE"
    unique, i = name, 2
    while unique in used:
        suffix = f"_{i}"
        unique = name[:BLOCK_NAME_MAX - len(suffix)] + suffix
        i += 1
    used.add(unique)
    return unique


def _with_notch_vertices(poly: tuple[Point, ...], notches: Sequence[Point]
                         ) -> list[Point]:
    """裁切折线共线插入刀口点为顶点（ET 顶点吸附）。

    服装 CAD（ET 等）挂接层 4 刀口符号按裁切折线**顶点**吸附，段中间的
    刀口点不显示；共线加点不改折线几何（其他 CAD 无副作用）。刀口点落在
    某段内（垂距 <= 1e-3cm）且严格段中（非既有顶点）才插；不在折线上的
    刀口（如无毛样时的净样位刀口）不插。逐刀口在最新折线上重扫描，同段
    多刀口被先前插入分段后各自命中，亦正确。
    """
    out = list(poly)
    for q in notches:
        for i in range(len(out)):
            a, b = out[i], out[(i + 1) % len(out)]
            ex, ey = b.x - a.x, b.y - a.y
            ll = ex * ex + ey * ey
            if ll < 1e-18:
                continue
            t = ((q.x - a.x) * ex + (q.y - a.y) * ey) / ll
            if not (1e-9 <= t <= 1.0 - 1e-9):     # 严格段中（顶点处无需插）
                continue
            dx = q.x - (a.x + ex * t)
            dy = q.y - (a.y + ey * t)
            if dx * dx + dy * dy <= 1e-6:         # 垂距 <= 1e-3cm，在段上
                out.insert(i + 1, q)
                break
    return out


def _render_piece_into(block, piece: PatternPiece, to_mm: base.ToMm,
                       tolerance_cm: float) -> None:
    """单片写入 BLOCK（图层顺序同 piece_svg：CUT/NET/SHRUNK/MARK/GRAIN/
    DRILL/NOTCH，层名经 _LAYER_MAP 映射为 AAMA 数字层）。"""
    notch_pts = piece.gross_notches or piece.shrunk_notches or piece.notches
    # 毛样（最终裁切线，闭合；刀口点共线插入为顶点——ET 按顶点吸附挂符号）
    if piece.gross_polygon:
        base.add_polyline(block, _with_notch_vertices(piece.gross_polygon,
                                                      notch_pts),
                          to_mm, layer=_LAYER_MAP["CUT"], closed=True)
    # 净样（淡虚线；已缩水时省略--同 piece_svg，只留一条内轮廓基准线）
    if not piece.shrunk_edges:
        for e in piece.net_edges:
            base.add_polyline(block, base.flatten_geom(e.geom, tolerance_cm),
                              to_mm, layer=_LAYER_MAP["NET"])
    if piece.shrunk_edges:
        for e in piece.shrunk_edges:
            base.add_polyline(block, base.flatten_geom(e.geom, tolerance_cm),
                              to_mm, layer=_LAYER_MAP["SHRUNK"])
    # 内部标记线（净样坐标，如袋口净线/省弧/围度辅助线）
    for g in piece.marks:
        base.add_polyline(block, base.flatten_geom(g, tolerance_cm),
                          to_mm, layer=_LAYER_MAP["MARK"])
    # 丝缕线（省略箭头）
    if piece.grain is not None:
        block.add_line(to_mm(piece.grain.a), to_mm(piece.grain.b),
                       dxfattribs={"layer": _LAYER_MAP["GRAIN"]})
        base.add_text(block, "GRAIN", piece.grain.a, to_mm,
                      layer=_LAYER_MAP["TEXT"], height_mm=2.0)
    # 定位孔：图层 13 单纯 POINT--CAD 读 AAMA 见层 13 POINT 自动渲染标准、
    # 不受缩放影响的钻孔十字/圆圈符号（真实 CIRCLE r=0.5mm 过小不可见）
    for q in piece.drills:
        x, y = to_mm(q)
        block.add_point((x, y), dxfattribs={"layer": _LAYER_MAP["DRILL"]})

    # 刀口：图层 4 POINT，必须附组码 30（Z 深度 1.524）与组码 50（开口
    # 角度）--缺角度 CAD 不知刀口朝哪个方向开、不显示。角度取刀口内法向
    # 在 mm 输出系的方向（局部系 Y 向下、输出 Y 翻转向上，故 dy 取负）
    for q in notch_pts:
        x, y = to_mm(q)
        tip = _notch_segment(q, piece.gross_polygon)[1]
        d = tip - q
        angle = math.degrees(math.atan2(-d.dy, d.dx))
        block.add_point((x, y, base.NOTCH_Z_MM),
                        dxfattribs={"layer": _LAYER_MAP["NOTCH"],
                                    "angle": angle})


def _add_piece_info(block, piece: PatternPiece, x0: float, y0: float,
                    x1: float, y1: float, to_mm: base.ToMm,
                    size: str, qty: int) -> None:
    """AAMA 裁片信息三行 TEXT（片 bbox 中央，自下而上每 4mm 一行）。"""
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    lines = (f"PIECE: {piece.name}",
             f"SIZE: {size}",
             f"QTY: {qty}")
    for i, text in enumerate(lines):
        # 每行间隔 0.4cm=4mm；局部系 y 越小屏上越高（Y 翻转），自下而上排
        base.add_text(block, text, Point(cx, cy - 0.4 * i), to_mm,
                      layer=_LAYER_MAP["TEXT"],
                      height_mm=base.TEXT_HEIGHT_MM)


def render_pieces_dxf(pieces: Sequence[PatternPiece], *,
                      tolerance_cm: float = base.FLATTEN_TOL_CM,
                      gap_cm: float = PIECE_GAP_CM,
                      size: str = "-", qty: int = 1):
    """把全部裁片平铺渲染为一张 AAMA 风格 R12 DXF 文档（ezdxf Drawing）。

    每片一个 BLOCK（局部 mm 坐标）+ Model Space INSERT（插入点 = 平铺
    偏移）；size/qty 进片中央 AAMA 信息文本（PatternPiece 不携带尺码/
    数量，由调用方按订单给出，默认 "-" / 1）。
    """
    doc = base.new_doc(_LAYERS)
    msp = doc.modelspace()
    used: set[str] = set()
    for piece, offx, offy in _layout(pieces, gap_cm):
        x0, y0, x1, y1 = _piece_bounds(piece)

        def to_mm(p: Point, x0=x0, y1=y1) -> tuple[float, float]:
            return ((p.x - x0) * base.MM_PER_CM,
                    (y1 - p.y) * base.MM_PER_CM)

        block = doc.blocks.new(name=_block_name(piece.name, used),
                               base_point=(0.0, 0.0, 0.0))
        # 块与块引用必须显式落层 1：默认层 0 会被 ET 08 直接过滤丢弃
        block.block.dxf.layer = _LAYER_MAP["CUT"]
        _render_piece_into(block, piece, to_mm, tolerance_cm)
        _add_piece_info(block, piece, x0, y0, x1, y1, to_mm, size, qty)
        msp.add_blockref(block.name,
                         insert=(offx * base.MM_PER_CM,
                                 offy * base.MM_PER_CM),
                         dxfattribs={"layer": _LAYER_MAP["CUT"]})
        # 片名 + 净长宽标注：置于片 bbox 上沿之上（局部系 y 向上为负）
        net_pts = [q for e in piece.net_edges
                   for q in base.flatten_geom(e.geom, tolerance_cm)]
        base.add_text(block, piece.name, Point(x0, y0 - 0.8), to_mm,
                      layer=_LAYER_MAP["TEXT"])
        if net_pts:
            nw = max(q.x for q in net_pts) - min(q.x for q in net_pts)
            nh = max(q.y for q in net_pts) - min(q.y for q in net_pts)
            base.add_text(block, f"NET {nw * 10:.0f}x{nh * 10:.0f}MM",
                          Point(x0, y0 - 1.8), to_mm,
                          layer=_LAYER_MAP["TEXT"])
    # 单位/AAMA 声明：全局原点下方（全部内容 y >= 0，不与任何片重叠）
    def _mm(p: Point) -> tuple[float, float]:
        return (p.x * base.MM_PER_CM, p.y * base.MM_PER_CM)

    base.add_text(msp, AAMA_NOTE, Point(0.0, -1.0), _mm,
                  layer=_LAYER_MAP["TEXT"])
    base.set_extents(doc)      # 回填 $EXTMIN/$EXTMAX（含 INSERT 展开）
    return doc


def write_pieces_dxf(pieces: Sequence[PatternPiece], path: str, *,
                     tolerance_cm: float = base.FLATTEN_TOL_CM,
                     gap_cm: float = PIECE_GAP_CM,
                     size: str = "-", qty: int = 1) -> None:
    doc = render_pieces_dxf(pieces, tolerance_cm=tolerance_cm,
                            gap_cm=gap_cm, size=size, qty=qty)
    base.save_doc(doc, path, comment=AAMA_NOTE)   # 前置 999 注释组
