"""缝边显示总开关 show_seam_allowance 测试（出口层显示控制，不改几何）。

金标（合成矩形净样 10×4，四边缝份 1.0，未缩水；裁片局部系 Y 向下，
绕向逆时针 = (0,0)->(0,4)->(10,4)->(10,0)，外法向外扩）：
- 毛样 = 12×6 矩形（-1,-1）~（11,5）；SVG 默认（show_seam=True）
  含 id="gross" 层、画布 12*10+80=200 × 6*10+80=140；
- show_seam=False：无 gross 层、画布收缩回净样 10*10+80=180 × 4*10+80=120、
  净样虚线照常、刀口整层不绘制（缝边刀口随缝边同步隐藏，notchpt 0 个）；
- SVG 显示缝边出毛样刀口 cx = 11*10+50 = 160.0（with_gross 投影至毛样外沿
  (11,2)，ox 含毛样 x0=-1 偏移）、cy = 2*10+50 = 70.0；隐藏后无刀口元素；
- DXF（ezdxf 在场时逐条 importorskip）：show_seam=False 后块内层 "1"
  无 POLYLINE（CUT 隐藏，层 1 文本照常）、层 "14" 净样闭合环恰 1 条照常；
  刀口 POINT（层 "4"）y 坐标随刀口口径切换：
  显示 = (5-2)*10 = 30mm（毛样 bbox y1=5）、隐藏 = (4-2)*10 = 20mm
  （净样 bbox y1=4，净线刀口）。
- PatternOptions(show_seam_allowance=False) 直接可构造（from_file 走
  cls(**data) 自动透传，无需白名单）。
"""

import pytest

from ylpattern.cutter import add_seam_allowance
from ylpattern.exporters.piece_svg import render_piece_svg
from ylpattern.geometry import LineSegment, Point
from ylpattern.params import PatternOptions
from ylpattern.pieces import PatternPiece, PieceEdge

_SA = {"bottom": 1.0, "right": 1.0, "top": 1.0, "left": 1.0}


def _piece() -> PatternPiece:
    """合成裁片：10×4 矩形净样（Y 向下系逆时针绕向）+ 四边 1.0 缝份 ->
    12×6 毛样（-1,-1）~（11,5）。净线刀口 (10,2) 落右边中点。"""
    a, d, c, b = Point(0, 0), Point(0, 4), Point(10, 4), Point(10, 0)
    net = (PieceEdge("bottom", LineSegment(a, d)),
           PieceEdge("right", LineSegment(d, c)),
           PieceEdge("top", LineSegment(c, b)),
           PieceEdge("left", LineSegment(b, a)))
    return add_seam_allowance(PatternPiece("demo", "演示", net,
                                           notches=(Point(10.0, 2.0),)),
                              _SA)


def _projected_notch_piece() -> PatternPiece:
    """刀口投影至毛样外沿的裁片（模拟 front_piece/back_piece 等投影刀口流：
    gross_notches 落在毛样边界、净线刀口保留在 notches/shrunk_notches）。"""
    p = _piece()
    assert p.gross_notches == (Point(10.0, 2.0),)   # cutter：毛样刀口 = 净刀口
    # 刀口沿右边外法向（+x）移至毛样外沿 x=11
    return p.with_gross(p.gross_polygon, (Point(11.0, 2.0),), p.notes)


def test_svg_default_shows_gross():
    svg = render_piece_svg(_piece())
    assert 'id="gross"' in svg
    assert 'width="200"' in svg and 'height="140"' in svg   # 12×6 毛样入画布


def test_svg_hidden_seam_drops_gross_and_shrinks_canvas():
    svg = render_piece_svg(_piece(), show_seam=False)
    assert 'id="gross"' not in svg
    assert 'width="180"' in svg and 'height="120"' in svg   # 画布收缩回 10×4
    assert 'id="net"' in svg                                # 净样虚线照常
    assert svg.count('class="notchpt"') == 0                # 刀口随缝边隐藏
    assert 'id="notches"' not in svg                        # 刀口整层不绘制
    shown = render_piece_svg(_piece())
    assert shown.count('class="notchpt"') == 1              # 默认视图刀口 1 个


def test_svg_notch_hidden_with_seam():
    shown = render_piece_svg(_projected_notch_piece())
    hidden = render_piece_svg(_projected_notch_piece(), show_seam=False)
    # 显示：毛样外沿刀口 (11,2)，ox = 40-(-1*10) = 50 -> cx=160 / cy=70
    assert 'cx="160.0"' in shown and 'cy="70.0"' in shown
    assert 'cx="140.0"' not in shown
    # 隐藏：刀口整层不绘制（缝边刀口随缝边同步隐藏，净线位刀口一并隐藏）
    assert 'id="notches"' not in hidden
    assert hidden.count('class="notchpt"') == 0


def _block(doc):
    ins = doc.modelspace().query("INSERT")[0]
    return doc.blocks[ins.dxf.name]


def test_dxf_hidden_seam_drops_cut_keeps_net():
    pytest.importorskip("ezdxf")
    from ylpattern.exporters.piece_dxf import render_pieces_dxf
    # embed_codes=False：合成片名 "demo" 不在排料赋码表（缝边显示开关
    # 测试与编号植入解耦，编号金标在 test_piece_dxf.py）
    doc = render_pieces_dxf([_piece()], size="30", show_seam=False,
                            embed_codes=False)
    blk = _block(doc)
    layer1_poly = [e for e in blk if e.dxftype() == "POLYLINE"
                   and e.dxf.layer == "1"]
    assert layer1_poly == []                       # CUT 闭合折线不发
    assert any(e.dxftype() == "TEXT" and e.dxf.layer == "1"
               for e in blk)                       # 层 1 文本照常
    net_poly = [e for e in blk if e.dxftype() == "POLYLINE"
                and e.dxf.layer == "14"]
    assert len(net_poly) == 1                      # 净样闭合环照常恰 1 条


def test_dxf_notch_switches_to_net_line_when_hidden():
    pytest.importorskip("ezdxf")
    from ylpattern.exporters.piece_dxf import render_pieces_dxf
    shown = render_pieces_dxf([_projected_notch_piece()], size="30",
                              embed_codes=False)
    hidden = render_pieces_dxf([_projected_notch_piece()], size="30",
                               show_seam=False, embed_codes=False)

    def notch_ys(doc) -> list[float]:
        blk = _block(doc)
        return [round(e.dxf.location[1], 3) for e in blk
                if e.dxftype() == "POINT" and e.dxf.layer == "4"]

    # 显示：毛样 bbox y1=5，刀口 y=2 -> (5-2)*10 = 30mm（毛样外沿刀口）
    assert notch_ys(shown) == [30.0]
    # 隐藏：净样 bbox y1=4，净线刀口 y=2 -> (4-2)*10 = 20mm（净线口径回退）
    assert notch_ys(hidden) == [20.0]


def test_options_flag_constructible():
    assert PatternOptions(show_seam_allowance=False).show_seam_allowance is False
    assert PatternOptions().show_seam_allowance is True
