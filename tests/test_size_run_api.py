"""多码推码端到端测试（api.run_size_run + cli 探测；推码方案步 4）。

金标：3 码 TOML -> run_size_run 出多码单文件 DXF（块名 {片名}-{码}、
Sample Size=基码）、返回码序 ctx 且逐码 Measurements 确实不同（逐码
重打版）；无 [size_run] 段报错信息正确；examples 多码尺寸单可加载。
"""

import pytest

from ylpattern.api import run_size_run
from ylpattern.params import load_size_run

RUN_TOML = """\
[measurements]
waist = 77
hip = 99
knee = 47.6
hem = 37.5
front_rise = 29
back_rise = 39
outseam = 106

[options]
size_label = "30"

[size_run]
base = "30"
style = "TEST-RUN"

[[size_run.band]]
sizes = ["29", "30", "31"]
waist = 2.5
hip = 2.5
"""


@pytest.fixture()
def run_file(tmp_path):
    f = tmp_path / "run.toml"
    f.write_text(RUN_TOML, encoding="utf-8")
    return f


def test_run_size_run_end_to_end(run_file, tmp_path):
    """3 码 -> 多码 DXF + 码序 ctx + 逐码尺寸递变。"""
    ezdxf = pytest.importorskip("ezdxf")
    dxf = tmp_path / "pieces_run.dxf"
    ctxs = run_size_run(str(run_file), pieces_dxf=str(dxf))
    assert list(ctxs) == ["29", "30", "31"]
    # 逐码 Measurements 展开正确（= 逐码重打版的输入）
    assert ctxs["30"].measurements.waist == pytest.approx(77)
    assert ctxs["31"].measurements.waist == pytest.approx(79.5)
    assert ctxs["29"].measurements.hip == pytest.approx(96.5)
    # 逐码选项：size_label 跟码（DXF 块内 Size 标签数据源）
    assert ctxs["29"].options.size_label == "29"

    doc = ezdxf.readfile(str(dxf))
    blocks = [b.name for b in doc.blocks
              if not b.name.startswith(("*", "_"))]
    assert len(blocks) == 3 * 3          # 默认开关：waistband/front/back × 3 码
    for s in ("29", "30", "31"):
        assert f"WAISTBAND-{s}" in blocks
        assert f"FRONT_PIECE-{s}" in blocks
        assert f"BACK_PIECE-{s}" in blocks
    headers = [e.dxf.text for e in doc.modelspace()
               if e.dxftype() == "TEXT"
               and e.dxf.text.startswith("Sample Size:")]
    assert headers == ["Sample Size: 30"]


def test_run_size_run_requires_section():
    """无 [size_run] 段：ValueError 提示走单码 run。"""
    with pytest.raises(ValueError, match="size_run"):
        run_size_run("examples/size_female_165.toml",
                     pieces_dxf="unused.dxf")


def test_examples_run_file_loads():
    """examples 多码尺寸单（直筒单文末 [size_run]，8 码分段档差）加载正确。"""
    run = load_size_run("examples/size_female_zhitong.toml")
    assert run is not None
    assert run.labels == ("29", "30", "31", "32", "33", "34", "36", "38")
    assert run.base == "30"
    assert run.style_name == "YL-A2708-F"
    assert run.measurements("33").waist == pytest.approx(82.0 + 3.0)  # 跨段取大码段
