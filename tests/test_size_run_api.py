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
        assert f"WAISTBAND-G05-{s}" in blocks
        assert f"FRONT_PIECE-G01-{s}" in blocks
        assert f"BACK_PIECE-G02-{s}" in blocks
    headers = [e.dxf.text for e in doc.modelspace()
               if e.dxftype() == "TEXT"
               and e.dxf.text.startswith("Sample Size:")]
    assert headers == ["Sample Size: 30"]


def test_run_size_run_requires_section():
    """无 [size_run] 段：ValueError 提示走单码 run。"""
    with pytest.raises(ValueError, match="size_run"):
        run_size_run("examples/size_female_165.toml",
                     pieces_dxf="unused.dxf")


def test_size_run_from_dict_matches_file():
    """金标（手工演算）：band 腰/臀档差 2.5、基码 30（腰 77 臀 99）——
    31 码腰 77+2.5=79.5、29 码臀 99-2.5=96.5、30 码=基码原值；与文件
    路径版（test_run_size_run_end_to_end 同源 spec）逐码全等。"""
    from ylpattern.api import size_run_from_dict
    from ylpattern.params import Measurements, PatternOptions
    m = Measurements(waist=77, hip=99, knee=47.6, hem=37.5,
                     front_rise=29, back_rise=39, outseam=106)
    o = PatternOptions(size_label="30")
    spec = {"base": "30", "style": "TEST-RUN",
            "band": [{"sizes": ["29", "30", "31"],
                      "waist": 2.5, "hip": 2.5}]}
    run = size_run_from_dict(m, o, spec)
    assert run.labels == ("29", "30", "31")
    assert run.base == "30"
    assert run.style_name == "TEST-RUN"
    assert run.measurements("30").waist == pytest.approx(77)
    assert run.measurements("31").waist == pytest.approx(79.5)
    assert run.measurements("29").hip == pytest.approx(96.5)


def test_size_run_from_dict_disabled_raises():
    """enabled=false：内存入口自查报错（from_spec 只校验开关类型不校验值，
    web 端误传 false 不能展开成功——与 cli 探测口径一致）。"""
    from ylpattern.api import size_run_from_dict
    from ylpattern.params import Measurements, PatternOptions
    m = Measurements(waist=77, hip=99, knee=47.6, hem=37.5,
                     front_rise=29, back_rise=39, outseam=106)
    with pytest.raises(ValueError, match="enabled"):
        size_run_from_dict(m, PatternOptions(size_label="30"),
                           {"enabled": False})


def test_run_size_run_groups_pure(run_file):
    """内存核心：contexts/groups/rows 均按码序、逐码尺寸递变、默认开关
    每码 3 片；trace_base 缺省 False（基码追踪为空）；不落盘无 DXF 依赖。"""
    from ylpattern.api import run_size_run_groups
    from ylpattern.params import PatternOptions, load_size_run
    o = PatternOptions.from_file(str(run_file))
    run = load_size_run(str(run_file), fallback_base=o.size_label)
    contexts, groups, rows, base_trace = run_size_run_groups(run, o)
    assert list(contexts) == ["29", "30", "31"]
    assert [lbl for lbl, _ in groups] == ["29", "30", "31"]
    assert [lbl for lbl, _, _ in rows] == ["29", "30", "31"]
    assert contexts["31"].measurements.waist == pytest.approx(79.5)
    assert all(len(pieces) == 3 for _, pieces in groups)
    assert base_trace == ""


def test_examples_run_file_loads(tmp_path):
    """examples 多码尺寸单（直筒单文末 [size_run]，6 码 27-32 单段档差）加载正确。

    示例文件的 enabled 会被使用者随手开关（false = 走单码模式），细节断言
    在强制 enabled = true 的副本上做，测内容不测开关状态。"""
    import re
    from pathlib import Path
    load_size_run("examples/size_female_zhitong.toml")   # 原文件只测不抛错
    text = Path("examples/size_female_zhitong.toml").read_text(encoding="utf-8")
    f = tmp_path / "run.toml"
    f.write_text(re.sub(r"(?m)^enabled\s*=\s*false", "enabled = true", text),
                 encoding="utf-8")
    run = load_size_run(str(f))
    assert run is not None
    assert run.labels == ("27", "28", "29", "30", "31", "32")
    assert run.base == "30"
    assert run.style_name == "YL-A2708-F"
    # 基码 30 腰围 77、档差 2.5：27 码低三档 77-3*2.5、32 码高两档 77+2*2.5
    assert run.measurements("27").waist == pytest.approx(77.0 - 3 * 2.5)
    assert run.measurements("32").waist == pytest.approx(77.0 + 2 * 2.5)
