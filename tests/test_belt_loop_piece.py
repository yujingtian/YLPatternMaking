"""裤耳独立裁片测试（裤耳裁片.md §1~§4）。

金标（belt_loop_width=1.2, unit_length=6.0, count=5, waste=3.0）：
  净裁长方形 宽 1.2 × 总长 6.0×5 + 3.0 = 33.0 cm（§2 尺寸计算即成品
  净尺寸集合，无缝份不折边，§1）；毛样轮廓 = 净样四角（不走 cutter）；
  丝缕线竖向贯穿（§3 直丝缕 = 长度方向）；无刀口（净裁无折边基准）。
断言口径：几何不变量 + 独立复算（不硬编坐标），同 test_watch_pocket_piece。
"""

from ylpattern.draft import DraftContext
from ylpattern.flows.belt_loop_flow import build_belt_loop
from ylpattern.geometry import LineSegment, Point
from ylpattern.params import Measurements, PatternOptions

M = Measurements(waist=70, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102, thigh=58)


def _build(**kw):
    o = PatternOptions(belt_loop=True, **kw)
    ctx = DraftContext(M, o)
    return build_belt_loop(ctx)


def _start(g): return g.a if isinstance(g, LineSegment) else g.p0
def _end(g):   return g.b if isinstance(g, LineSegment) else g.p3


def test_rectangle_gold():
    """金标：宽 1.2 × 长 33.0 长方形，四边闭合（§2）。"""
    piece, ctx = _build()
    ne = piece.net_edges
    assert len(ne) == 4
    assert all(isinstance(e.geom, LineSegment) for e in ne)
    # 闭合链
    for i in range(4):
        assert _end(ne[i].geom).distance_to(
            _start(ne[(i + 1) % 4].geom)) < 1e-9
    # 金标尺寸
    xs = [p.x for e in ne for p in (e.geom.a, e.geom.b)]
    ys = [p.y for e in ne for p in (e.geom.a, e.geom.b)]
    assert max(xs) - min(xs) == 1.2          # 宽 = 成品净宽
    assert max(ys) - min(ys) == 6.0 * 5 + 3.0  # 长 = 单根 × 根数 + 损耗
    # 局部 ctx 命名元素齐全（trace/调试）
    for i in range(4):
        assert f"belt_loop.edge{i}" in ctx.sheet


def test_net_cut_no_seam():
    """净裁（§1）：毛样 = 净样四角、无缩水态、无刀口。"""
    piece, _ = _build()
    assert piece.gross_polygon == (
        Point(0.0, 0.0), Point(1.2, 0.0),
        Point(1.2, 33.0), Point(0.0, 33.0))
    assert not piece.shrunk_edges
    assert not piece.notches and not piece.gross_notches


def test_grain_vertical():
    """丝缕线竖向贯穿 = 直丝缕沿长度方向（§3）。"""
    piece, _ = _build()
    g = piece.grain
    assert g is not None
    assert abs(g.a.x - g.b.x) < 1e-9        # 竖直
    assert g.a.y > 0.0 and g.b.y < 33.0     # 上下留边距在裁片内


def test_custom_params():
    """独立复算：宽 1.5 / 单根 7 / 4 根 / 损耗 2 -> 1.5 × 30。"""
    piece, _ = _build(belt_loop_width=1.5, belt_loop_unit_length=7.0,
                      belt_loop_count=4, belt_loop_waste=2.0)
    xs = [p.x for p in piece.gross_polygon]
    ys = [p.y for p in piece.gross_polygon]
    assert max(xs) - min(xs) == 1.5
    assert max(ys) - min(ys) == 30.0


def test_svg_renders():
    """SVG 可渲染（净样/毛样/丝缕图层齐全）。"""
    from ylpattern.exporters.piece_svg import render_piece_svg
    piece, _ = _build()
    s = render_piece_svg(piece)
    assert "grossline" in s and "grain" in s
