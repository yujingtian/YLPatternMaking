"""reverse.identify 金标测试（fixture 合成 5015/5028 形状的工厂方言）。

头注演算（mm 域）：
- 5015 形状合成件：
  - 前 = 前片矩形净 (0,0)-(400,960)，高 960 ≥600 -> front_body 置信 1；
  - 机头融合块 2 子片：后片净 (0,0)-(395,962) 面积 379990 > 真机头
    (0,1000)-(245,1067) 面积 16415 -> 按面积降序对位 back_body/yoke，
    高度检查 962≥600 / 67≤150 均过；
  - 腰净 (0,0)-(744,43)：长短边比 744/43≈17.3 ≥4 且带宽 43≤120 ->
    waistband 置信 1；
  - 前代净 (0,0)-(129,127) 近方（比例 1.016）+ 层 8 袋口弧 160（100~200）
    -> fused_pocket 置信 1；
  - 匿名 2 子片：后贴袋净 (0,0)-(380x420) 面积 159600 > 表袋
    (0,600)-(100x60) 6000 -> back_patch/watch_pocket；
  - 双排/单排/裤耳命名小块角色到位；
  - 首尾相接 -> 6 测量关键角色齐、无缺角色告警。
- 5028 形状合成件：匿名 5 子件其中一件 156x52（比例 3.0 ≥3）->
  unknown_strip 告警行 + 映射；其余匿名件进 unassigned。
- 款号识别：头标 STYLE NAME "5015#" -> PROFILE_5015；无头标款号时
  块名 "5028#." 多数表决 -> PROFILE_5028；未知款号 9999 -> ReverseError。
"""

from __future__ import annotations

import pytest

ezdxf = pytest.importorskip("ezdxf")

from ylpattern.reverse import (ReverseError, assign_roles, detect_profile,
                               read_dxf)
from ylpattern.reverse.profiles import get_profile

from _reverse_fixture import write_fixture

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def _rect(x0, y0, w, h, inset=0.0):
    """(毛样, 净样) 矩形点列；净样四边内缩 inset。"""
    gross = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
    i = inset
    net = [(x0 + i, y0 + i), (x0 + w - i, y0 + i),
           (x0 + w - i, y0 + h - i), (x0 + i, y0 + h - i)]
    return gross, net


def _blocks_5015():
    g, n = _rect(0, 0, 400, 960, 10)
    front = {"gross": g, "net": n}
    g_back, n_back = _rect(0, 0, 395, 962, 10)
    g_yoke, n_yoke = _rect(0, 1000, 245, 67, 5)
    g_wb, n_wb = _rect(0, 0, 744, 43, 0)          # 腰头无缝份直条
    fused = {"gross": [(0, 0), (140, 0), (140, 140), (0, 140)],
             "net": [(0, 0), (129, 0), (129, 127), (0, 127)],
             "internal": [[(10, 60), (80, 20), (119, 50)]]}   # 弧长≈160
    small = {"gross": [(0, 0), (60, 0), (60, 60), (0, 60)],
             "net": [(0, 0), (50, 0), (50, 50), (0, 50)]}
    loop = {"gross": [(0, 0), (300, 0), (300, 40), (0, 40)],
            "net": [(0, 0), (300, 0), (300, 40), (0, 40)]}
    anon = [{"gross": [(0, 0), (390, 0), (390, 430), (0, 430)],
             "net": [(0, 0), (380, 0), (380, 420), (0, 420)]},
            {"gross": [(0, 600), (110, 600), (110, 670), (0, 670)],
             "net": [(0, 600), (100, 600), (100, 660), (0, 660)]}]
    return [
        ("前", "S", [front]),
        ("机头", "S", [{"gross": g_back, "net": n_back},
                    {"gross": g_yoke, "net": n_yoke}]),
        ("腰", "S", [{"gross": g_wb, "net": n_wb}]),
        ("前代", "S", [fused]),
        ("双排", "S", [small]), ("单排", "S", [dict(small)]),
        ("裤耳", "S", [loop]),
        ("", "S", anon),
    ]


def _read_5015(tmp_path, style="5015#", sample="S"):
    path = tmp_path / "p5015.dxf"
    write_fixture(path, _blocks_5015(), sample_size=sample, style=style)
    return read_dxf(str(path))


def test_detect_profile_by_header_and_blocks(tmp_path):
    doc = _read_5015(tmp_path)
    assert detect_profile(doc).key == "5015"
    assert detect_profile(doc, "5015").key == "5015"
    # 头标无款号数字（TST 无 3 位数字段）-> 块名多数表决走 5028
    path = tmp_path / "p5028.dxf"
    write_fixture(path, _blocks_5015(), sample_size="S", style="TST#")
    # 块名仍是 TST#（款号在块名里才有用）：改用真 5028 块名前缀
    path2 = tmp_path / "p5028b.dxf"
    write_fixture(path2, [("前", "M", [_blocks_5015()[0][2][0]]),
                          ("腰", "M", _blocks_5015()[2][2]),
                          ("火机袋", "M", [_blocks_5015()[7][2][1]])],
                  sample_size="M", style="5028#")
    doc2 = read_dxf(str(path2))
    assert detect_profile(doc2).key == "5028"
    with pytest.raises(ReverseError):
        detect_profile(doc, "9999")


def test_assign_roles_5015_full(tmp_path):
    doc = _read_5015(tmp_path)
    report = assign_roles(doc, detect_profile(doc))
    mapping = report.for_size("S")
    for role in ("front_body", "back_body", "yoke", "waistband",
                 "fused_pocket", "back_patch", "watch_pocket",
                 "front_fly_double", "front_fly_single", "belt_loop"):
        assert role in mapping, role
    # 机头块拆分：back_body 净高 942、yoke 净高 57（面积对位正确）
    assert mapping["back_body"].net_bbox()[3] - \
        mapping["back_body"].net_bbox()[1] == pytest.approx(942.0)
    assert mapping["yoke"].net_bbox()[3] - \
        mapping["yoke"].net_bbox()[1] == pytest.approx(57.0)
    # 匿名对位：面积大者后贴袋
    assert mapping["back_patch"].net_bbox()[2] == pytest.approx(380.0)
    assert mapping["watch_pocket"].net_bbox()[3] == pytest.approx(660.0)
    # 无缺关键角色告警、无未指派件、无低置信行
    assert not any("缺测量关键角色" in n for n in report.notes)
    assert not report.unassigned
    assert not any("低置信" in n or "得分" in n for n in report.notes)
    # one/maybe 存取
    assert report.one("front_body", "S").name_hint == "前"
    assert report.maybe("unknown_strip", "S") is None
    with pytest.raises(ReverseError):
        report.one("unknown_strip", "S")


def test_assign_roles_count_mismatch_best_effort(tmp_path):
    blocks = _blocks_5015()
    # 机头块砍掉真机头子片 -> 子片数 1 ≠ 档案 2，告警 + 尽力指派 back_body
    blocks[1] = ("机头", "S", [blocks[1][2][0]])
    path = tmp_path / "mismatch.dxf"
    write_fixture(path, blocks, sample_size="S", style="5015#")
    doc = read_dxf(str(path))
    report = assign_roles(doc, detect_profile(doc))
    assert "yoke" not in report.for_size("S")
    assert any("子片数 1 ≠ 档案 2" in n for n in report.notes)
    assert any("缺测量关键角色" in n for n in report.notes)


def test_assign_roles_fused_pocket_low_confidence(tmp_path):
    blocks = _blocks_5015()
    # 去掉层 8 袋口弧 -> 近方但无弧，谓词得分 0.4 低置信
    blocks[3] = ("前代", "S", [{k: v for k, v in blocks[3][2][0].items()
                                if k != "internal"}])
    path = tmp_path / "noarc.dxf"
    write_fixture(path, blocks, sample_size="S", style="5015#")
    doc = read_dxf(str(path))
    report = assign_roles(doc, detect_profile(doc))
    assert "fused_pocket" in report.for_size("S")
    assert any("低置信" in n for n in report.notes)


def test_assign_roles_5028_unknown_strip(tmp_path):
    # 匿名 5 子件：其中一个 156x52（比例恰 3.0）细条
    anon5 = []
    shapes = [(191, 141), (160, 97), (156, 52), (102, 157), (102, 102)]
    for i, (w, h) in enumerate(shapes):
        g, n = _rect(0, 2000 * (i + 1), w, h, 3)
        anon5.append({"gross": g, "net": n})
    blocks = [("前", "M", [_blocks_5015()[0][2][0]]),
              ("机头", "M", _blocks_5015()[1][2]),
              ("腰", "M", _blocks_5015()[2][2]),
              ("火机袋", "M", [_blocks_5015()[7][2][1]]),
              ("", "M", anon5)]
    path = tmp_path / "p5028.dxf"
    write_fixture(path, blocks, sample_size="M", style="5028#")
    doc = read_dxf(str(path))
    report = assign_roles(doc, detect_profile(doc))
    mapping = report.for_size("M")
    assert "unknown_strip" in mapping
    assert mapping["unknown_strip"].net_bbox()[2] - \
        mapping["unknown_strip"].net_bbox()[0] == pytest.approx(150.0)
    assert any("匿名细条" in n for n in report.notes)
    # 其余 4 个匿名件进 unassigned（匿名未识别）
    anon_unassigned = [r for _, r in report.unassigned
                       if r.startswith("匿名未识别")]
    assert len(anon_unassigned) == 4
