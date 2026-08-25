"""整版 SVG 元素身份测试（二期拖拽：SVG ⇄ 引擎元素可关联）。

金标（合成小版）：
- 参考线 t.waistline (0,100)-(50,100)、结构线 t.seam (0,0)-(0,100)、
  点 t.p0 (0,0) / t.p1 (25,100.25)、平弧 t.hem CubicBezier(5,0)(15,0)(30,0)(40,0)
  （y 全取 0/100.25 等二进制精确值，包围盒断言可精确到 float）。
- 包围盒：x∈[0,50]、y∈[0,100.25] →
  compute_view = (width 560, height 1062.5, top 1032.5, ox 30)
  （SCALE=10 px/cm、MARGIN=30 px；top=30+100.25×10、ox=30−0）。
- 元素身份：每条线/点/曲线带 id="{name}"，文字标注带 data-name；
  show_labels=False 时 id 照常、text/data-name 全隐藏。
- 根元素 data-scale/data-ox/data-top 全精度下发（px→cm 逆变换权威源）。
"""

from ylpattern.draft import DraftSheet
from ylpattern.draft.elements import NamedCurve, NamedLine, NamedPoint
from ylpattern.exporters.svg import compute_view, render_sheet
from ylpattern.geometry import CubicBezier, LineSegment, Point


def _sheet() -> DraftSheet:
    sheet = DraftSheet()
    sheet.add(NamedLine("t.waistline", LineSegment(Point(0, 100), Point(50, 100)),
                        "draw_test", label="腰围线", role="ref"))
    sheet.add(NamedLine("t.seam", LineSegment(Point(0, 0), Point(0, 100)),
                        "draw_test", label="侧缝", role="struct"))
    sheet.add(NamedPoint("t.p0", Point(0, 0), "draw_test", label="原点"))
    sheet.add(NamedPoint("t.p1", Point(25, 100.25), "draw_test", label="顶点"))
    sheet.add(NamedCurve("t.hem",
                         CubicBezier(Point(5, 0), Point(15, 0),
                                     Point(30, 0), Point(40, 0)),
                         "draw_test", label="脚口弧"))
    return sheet


def test_compute_view_golden():
    # width=(50-0)×10+60、height=(100.25-0)×10+60、top=30+100.25×10、ox=30-0
    assert compute_view(_sheet()) == (560.0, 1062.5, 1032.5, 30.0)


def test_svg_element_ids():
    svg = render_sheet(_sheet())
    assert '<line id="t.waistline" class="refline"' in svg      # 参考线 id
    assert '<line id="t.seam" class="structline"' in svg        # 结构线 id
    assert '<circle id="t.p0" class="pt"' in svg                # 点 id
    assert '<circle id="t.p1" class="pt"' in svg
    assert '<polyline id="t.hem" class="curve"' in svg          # 曲线 id


def test_svg_root_transform_attrs():
    svg = render_sheet(_sheet())
    # 全精度（不沿用坐标 .1f 的 0.1px 舍入），px→cm 逆变换的权威源
    assert 'data-scale="10.0"' in svg
    assert 'data-ox="30"' in svg
    assert 'data-top="1032.5"' in svg


def test_labels_carry_data_name():
    svg = render_sheet(_sheet())
    assert '<text class="reflabel" data-name="t.waistline"' in svg
    assert '<text class="structlabel" data-name="t.seam"' in svg
    assert '<text class="ptlabel" data-name="t.p0"' in svg


def test_hidden_labels_keep_ids():
    svg = render_sheet(_sheet(), show_labels=False)
    assert svg.count("<text") == 0
    assert svg.count("data-name") == 0
    # 元素 id 与几何无关，照常下发
    assert '<circle id="t.p0"' in svg
    assert '<polyline id="t.hem"' in svg
    assert '<line id="t.seam"' in svg
