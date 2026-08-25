"""整版标注显示总开关 show_labels 测试（出口层显示控制，不改几何）。

金标（合成小版：参考线 腰围线 (0,100)-(50,100)、结构线 侧缝 (0,0)-(0,100)、
关键点 原点 (0,0)）：
- 默认（show_labels=True）恰 3 处 <text>（reflabel/structlabel/ptlabel 各 1）；
- show_labels=False：0 处 <text>，线（refline/structline）与关键点圆
  （class="pt"）照常绘制，画布尺寸不变（画布只由几何算，与文字无关）。
"""

from ylpattern.draft import DraftSheet
from ylpattern.draft.elements import NamedLine, NamedPoint
from ylpattern.exporters.svg import render_sheet
from ylpattern.geometry import LineSegment, Point
from ylpattern.params import PatternOptions


def _sheet() -> DraftSheet:
    sheet = DraftSheet()
    sheet.add(NamedLine("t.waistline", LineSegment(Point(0, 100), Point(50, 100)),
                        "draw_test", label="腰围线", role="ref"))
    sheet.add(NamedLine("t.seam", LineSegment(Point(0, 0), Point(0, 100)),
                        "draw_test", label="侧缝", role="struct"))
    sheet.add(NamedPoint("t.p0", Point(0, 0), "draw_test", label="原点"))
    return sheet


def test_svg_default_shows_all_labels():
    svg = render_sheet(_sheet())
    assert svg.count("<text") == 3
    assert 'class="reflabel"' in svg and "腰围线" in svg
    assert 'class="structlabel"' in svg and "侧缝" in svg
    assert 'class="ptlabel"' in svg and "原点" in svg


def test_svg_hidden_labels_keeps_lines_points_and_canvas():
    shown = render_sheet(_sheet())
    hidden = render_sheet(_sheet(), show_labels=False)
    assert hidden.count("<text") == 0            # 三类文字标注全隐藏
    assert 'class="refline"' in hidden           # 参考线照常
    assert 'class="structline"' in hidden        # 结构线照常
    assert hidden.count('class="pt"') == 1       # 关键点圆照常
    # 画布只由几何决定：两种模式同尺寸
    w = [ln for ln in shown.splitlines() if ln.startswith("<svg")][0]
    h = [ln for ln in hidden.splitlines() if ln.startswith("<svg")][0]
    assert w == h


def test_options_flag_constructible():
    assert PatternOptions().show_labels is True
    assert PatternOptions(show_labels=False).show_labels is False
    assert PatternOptions.from_dict({"show_labels": False}).show_labels is False
