"""reverse CLI 端到端测试（合成工厂 DXF，ezdxf 缺失整文件 skip）。

合成件复用 test_reverse_measure 的合成几何（8 键/选项金标见该文件头注）：
- end-to-end：reverse -> TOML ->（emit 回验过的） Measurements/Options 构造、
  关键值落位、结构开关（双排门襟片在 -> fly_separate）；
- --probe：只出清单报告（件清单/角色指派），无测量段、不写 TOML；
- 错误路径：未知款号档案退出码 2；文件不存在退出码 2。
"""

from __future__ import annotations

import pytest

pytest.importorskip("ezdxf")

from ylpattern.cli import main as cli_main
from ylpattern.params import Measurements, PatternOptions
from ylpattern.params.sizefile import load_size_file
from ylpattern.reverse.reader import read_dxf
from _reverse_fixture import write_fixture
from test_reverse_measure import (BAND, BACK, B_GUIDES, FRONT, H_GUIDES,
                                  MOUTH_ARC, POUCH, YOKE)


def _pts(line) -> list[tuple[float, float]]:
    """Ring/OpenLine -> 点元组列（fixture 输入形态）。"""
    return [(p.x, p.y) for p in line.pts]


def _blocks() -> list:
    fly = [(2000.0, 2000.0), (2177.8, 2000.0), (2177.8, 2082.5),
           (2000.0, 2082.5)]
    return [
        ("前", "S", [{"net": _pts(FRONT),
                      "internal": [_pts(l) for l in H_GUIDES],
                      "meta_at": (60, 580)}]),
        ("机头", "S", [{"net": _pts(BACK),
                        "internal": [_pts(l) for l in B_GUIDES],
                        "meta_at": (570, 560)},
                       {"net": _pts(YOKE), "meta_at": (640, 750)}]),
        ("腰", "S", [{"net": _pts(BAND), "grain": ((175, 40), (175, 110)),
                      "meta_at": (10, 95)}]),
        ("前代", "S", [{"net": _pts(POUCH), "internal": [_pts(MOUTH_ARC)],
                        "meta_at": (10, 165)}]),
        ("双排", "S", [{"net": fly, "meta_at": (2010, 2080)}]),
    ]


@pytest.fixture(scope="module")
def factory_dxf(tmp_path_factory):
    path = tmp_path_factory.mktemp("rev") / "5015_test.dxf"
    write_fixture(path, _blocks(), sample_size="S", style="5015")
    return path


def test_reverse_end_to_end(factory_dxf, tmp_path):
    size = tmp_path / "rev.toml"
    report = tmp_path / "rep.txt"
    rc = cli_main(["reverse", "--dxf", str(factory_dxf),
                   "--size", str(size), "--report", str(report)])
    assert rc == 0
    assert size.exists() and report.exists()
    raw = load_size_file(str(size))
    m = Measurements.from_dict(raw["measurements"])
    # 合成几何测量金标（test_reverse_measure 头注；圆整 0.1）
    assert m.hip == pytest.approx(94.18, abs=0.06)
    assert m.waist == pytest.approx(29.75, abs=0.06)
    assert m.back_rise == pytest.approx(38.25, abs=0.06)
    assert m.outseam == pytest.approx(62.38, abs=0.06)
    o = PatternOptions.from_dict(raw["options"])
    assert o.delta == pytest.approx(2.0)               # 钳制后值
    assert o.back_intake == pytest.approx(2.62, abs=0.01)
    assert o.back_yoke is True and o.front_pocket is True
    assert o.fly_separate is True                      # 双排门襟片在场
    assert o.thigh_limit is True
    text = report.read_text(encoding="utf-8")
    assert "尺寸单 8 键 [S]（基码）" in text
    assert "delta 实测 2.29" in text                   # 钳制告警留原值


def test_probe_mode(factory_dxf, tmp_path, capsys):
    report = tmp_path / "probe.txt"
    rc = cli_main(["reverse", "--dxf", str(factory_dxf), "--probe",
                   "--report", str(report)])
    assert rc == 0
    text = report.read_text(encoding="utf-8")
    assert "件清单" in text and "角色指派" in text
    assert "尺寸单 8 键" not in text                    # probe 不测量
    assert not list(tmp_path.glob("*.toml"))            # 不写 TOML


def test_probe_stdout(factory_dxf, capsys):
    rc = cli_main(["reverse", "--dxf", str(factory_dxf), "--probe"])
    assert rc == 0
    assert "件清单" in capsys.readouterr().out


def test_unknown_style_exit_2(factory_dxf, capsys):
    rc = cli_main(["reverse", "--dxf", str(factory_dxf), "--style", "9999"])
    assert rc == 2
    assert "未登记的款号" in capsys.readouterr().err


def test_missing_file_exit_2(tmp_path, capsys):
    rc = cli_main(["reverse", "--dxf", str(tmp_path / "nope.dxf")])
    assert rc == 2
    assert "错误" in capsys.readouterr().err


def test_reader_roundtrip_block_split(factory_dxf):
    """读取层聚类：机头块拆 2 子片（后片+真机头），码集 = ("S",)。"""
    doc = read_dxf(str(factory_dxf))
    assert doc.sizes == ("S",)
    assert len(doc.by_block("机头", "S")) == 2
    assert len(doc.pieces) == 6
