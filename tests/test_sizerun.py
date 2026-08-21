"""尺码表（SizeRun）展开测试（推码方案步 1；params 层金标）。

金标（.doc/臀围线推导.md §四 W26~W34 表）：
- 基码 W30（腰 76 / 臀 96），单段档差腰 5.0 / 臀 4.0（W26~W34 为
  2 英寸码，1 英寸 ≈ 2.5cm 腰围，故逐码步进 = 2×2.5 / 2×2.0）：
  腰 66/71/76/81/86、臀 88/92/96/100/104，展开逐一相等；
- 未给步进的参数（knee/hem/rise/outseam）继承基码，全码等值；
- 跨段步进取 i+1 所属段、双向累加自基码向两侧展开；
- 显式覆盖优先；纯显式形态；字母码声明序保持；thigh 特例。
"""

import dataclasses

import pytest

from ylpattern.params import (Measurements, PatternOptions, SizeRun,
                              load_size_run)

M = Measurements(waist=76, hip=96, knee=46, hem=36,
                 front_rise=25, back_rise=33, outseam=102)


def _spec(**section) -> dict:
    return {"measurements": {"waist": 76, "hip": 96, "knee": 46, "hem": 36,
                             "front_rise": 25, "back_rise": 33,
                             "outseam": 102},
            "size_run": section}


def test_expand_golden_w26_w34():
    """① 展开金标：单段档差腰 5.0/臀 4.0 -> W26~W34 与 §四表逐一相等。"""
    raw = _spec(base="W30", order=["W26", "W28", "W30", "W32", "W34"],
                band=[{"sizes": ["W26", "W28", "W30", "W32", "W34"],
                       "waist": 5.0, "hip": 4.0}])
    run = SizeRun.from_spec(M, raw)
    gold = {"W26": (66.0, 88.0), "W28": (71.0, 92.0), "W30": (76.0, 96.0),
            "W32": (81.0, 100.0), "W34": (86.0, 104.0)}
    assert run.labels == ("W26", "W28", "W30", "W32", "W34")
    assert run.base == "W30"
    for label, (w, h) in gold.items():
        mm = run.measurements(label)
        assert mm.waist == pytest.approx(w)
        assert mm.hip == pytest.approx(h)
    # 未给步进的参数继承基码（步进 0），全码等值
    assert all(run.measurements(l).outseam == 102 for l in run.labels)
    assert run.base_measurements() == M


def test_cross_band_step_and_backward():
    """② 跨段步进取 i+1 所属段（32->33 取大码段）、反向累加一致。"""
    raw = _spec(base="32",
                band=[{"sizes": ["29", "30", "31", "32"],
                       "waist": 2.5, "hip": 2.5},
                      {"sizes": ["33", "34"], "waist": 3.0, "hip": 3.0}])
    run = SizeRun.from_spec(M, raw)
    assert run.labels == ("29", "30", "31", "32", "33", "34")
    # 向前：33 = 32 + 大段步进 3.0；34 = 33 + 3.0
    assert run.measurements("33").waist == pytest.approx(76 + 3.0)
    assert run.measurements("34").waist == pytest.approx(76 + 6.0)
    # 向后：29 = 基码 − 3×小段步进 2.5 = 68.5
    assert run.measurements("29").waist == pytest.approx(76 - 3 * 2.5)
    assert run.measurements("31").hip == pytest.approx(96 - 2.5)


def test_explicit_override_wins():
    """③ 显式覆盖优先：覆盖键生效、未覆盖键继承展开值。"""
    raw = _spec(base="30",
                band=[{"sizes": ["29", "30", "31"], "waist": 2.5}],
                sizes={"31": {"waist": 80.2, "front_rise": 29.4}})
    run = SizeRun.from_spec(M, raw)
    m31 = run.measurements("31")
    assert m31.waist == pytest.approx(80.2)
    assert m31.front_rise == pytest.approx(29.4)
    assert m31.hip == pytest.approx(96)      # 未覆盖键继承（无步进）
    assert run.measurements("29").waist == pytest.approx(76 - 2.5)


def test_pure_explicit_form():
    """④ 纯显式形态：无 band、逐码全 8 键，码序取声明序。"""
    raw = _spec(base="28",
                sizes={"28": {"waist": 71, "hip": 92, "knee": 45, "hem": 36,
                              "front_rise": 24.5, "back_rise": 32.5,
                              "outseam": 101, "thigh": 58},
                       "30": {"waist": 76, "hip": 96, "knee": 46, "hem": 37,
                              "front_rise": 25, "back_rise": 33,
                              "outseam": 102, "thigh": 60}})
    run = SizeRun.from_spec(M, raw)
    assert run.labels == ("28", "30")
    assert run.measurements("30").waist == 76
    assert run.measurements("28").thigh == 58
    assert run.base == "28"


def test_letter_size_declaration_order():
    """⑤ 字母码/"36L" 无数值解析，按声明序展开。"""
    raw = _spec(base="M",
                order=["S", "M", "L", "36L"],
                band=[{"sizes": ["S", "M", "L"], "waist": 3.0},
                      {"sizes": ["36L"], "waist": 4.0}])
    run = SizeRun.from_spec(M, raw)
    assert run.labels == ("S", "M", "L", "36L")
    assert run.measurements("S").waist == pytest.approx(76 - 3.0)
    assert run.measurements("L").waist == pytest.approx(76 + 3.0)
    assert run.measurements("36L").waist == pytest.approx(76 + 3.0 + 4.0)


def test_thigh_special():
    """thigh 特例：基码 0 时步进全忽略；显式 thigh>0 单码启用。"""
    raw = _spec(base="30",
                band=[{"sizes": ["29", "30", "31"], "waist": 2.5,
                       "thigh": 1.3}],
                sizes={"31": {"thigh": 61.0}})
    run = SizeRun.from_spec(M, raw)      # M.thigh 默认 0（未录入）
    assert run.measurements("29").thigh == 0.0
    assert run.measurements("30").thigh == 0.0
    assert run.measurements("31").thigh == 61.0     # 显式单码启用


def test_base_fallback():
    """base 回退：fallback_base（options.size_label）> order[0]。"""
    raw = _spec(band=[{"sizes": ["30", "31"], "waist": 2.5}])
    assert SizeRun.from_spec(M, raw).base == "30"          # order[0]
    run = SizeRun.from_spec(M, raw, fallback_base="31")
    assert run.base == "31"
    assert run.measurements("30").waist == pytest.approx(76 - 2.5)


def test_options_for_only_changes_size_label():
    """⑦ options_for 仅改 size_label，其余选项全码恒等。"""
    raw = _spec(base="30", band=[{"sizes": ["30", "31"], "waist": 2.5}])
    run = SizeRun.from_spec(M, raw)
    o = PatternOptions(delta=1.0, back_yoke=True)
    o31 = run.options_for("31", o)
    assert o31.size_label == "31"
    for f in dataclasses.fields(PatternOptions):
        if f.name != "size_label":
            assert getattr(o31, f.name) == getattr(o, f.name)


@pytest.mark.parametrize("raw_section, match", [
    # 档差段跨段重复码
    ({"band": [{"sizes": ["29", "30"], "waist": 2.5},
               {"sizes": ["30", "31"], "waist": 3.0}]}, "重复"),
    # 显式 order 缺码（band 中的码未列入）
    ({"order": ["29", "30"],
      "band": [{"sizes": ["29", "30", "31"], "waist": 2.5}]}, "缺少"),
    # 基码不在码序
    ({"base": "99", "band": [{"sizes": ["30", "31"], "waist": 2.5}]},
     "不在码序"),
    # 展开后交叉校验失败（31 码 hip<=waist），消息含码标签
    ({"base": "30",
      "band": [{"sizes": ["30", "31"], "waist": 25.0, "hip": 2.0}]},
     "码 '31'"),
    # 档差段未知参数
    ({"band": [{"sizes": ["30"], "waist": 2.5, "chest": 1.0}]}, "未知参数"),
    # 显式参数未知键
    ({"sizes": {"30": {"waist": 76, "bust": 90}}}, "未知键"),
    # style 非 ASCII
    ({"style": "订单一号",
      "band": [{"sizes": ["30", "31"], "waist": 2.5}]}, "ASCII"),
    # 无来源码（不在任何段也无显式参数）
    ({"order": ["29", "30", "31"],
      "band": [{"sizes": ["29", "30"], "waist": 2.5}]}, "无法确定尺寸"),
    # [size_run] 顶层未知键
    ({"colour": "blue",
      "band": [{"sizes": ["30", "31"], "waist": 2.5}]}, "未知键"),
])
def test_error_family(raw_section, match):
    """⑥ 错误族：中文 ValueError 含实际值/码标签。"""
    with pytest.raises(ValueError, match=match):
        SizeRun.from_spec(M, _spec(**raw_section))


def test_load_size_run_detection(tmp_path):
    """⑧ load_size_run：无 [size_run] 段返回 None（单码探测口）。"""
    plain = tmp_path / "plain.toml"
    plain.write_text(
        "[measurements]\nwaist = 76\nhip = 96\nknee = 46\nhem = 36\n"
        "front_rise = 25\nback_rise = 33\noutseam = 102\n",
        encoding="utf-8")
    assert load_size_run(str(plain)) is None

    multi = tmp_path / "multi.toml"
    multi.write_text(
        "[measurements]\nwaist = 76\nhip = 96\nknee = 46\nhem = 36\n"
        "front_rise = 25\nback_rise = 33\noutseam = 102\n"
        "\n[options]\nsize_label = \"31\"\n"
        "\n[size_run]\nstyle = \"YL-A2708-F\"\n"
        "\n[[size_run.band]]\nsizes = [\"30\", \"31\"]\nwaist = 2.5\n",
        encoding="utf-8")
    run = load_size_run(str(multi), fallback_base="31")
    assert isinstance(run, SizeRun)
    assert run.style_name == "YL-A2708-F"
    assert run.base == "31"                     # fallback 生效
    assert run.measurements("30").waist == pytest.approx(76 - 2.5)


def test_enabled_switch(tmp_path):
    """⑨ 总开关 enabled：false -> None（单码探测口）；非布尔报错。"""
    def write(enabled_line: str) -> str:
        f = tmp_path / "sw.toml"
        f.write_text(
            "[measurements]\nwaist = 76\nhip = 96\nknee = 46\nhem = 36\n"
            "front_rise = 25\nback_rise = 33\noutseam = 102\n"
            "\n[size_run]\n" + enabled_line + "\nbase = \"30\"\n"
            "\n[[size_run.band]]\nsizes = [\"30\", \"31\"]\nwaist = 2.5\n",
            encoding="utf-8")
        return str(f)

    assert load_size_run(write("enabled = true\n")) is not None
    assert load_size_run(write("enabled = false\n")) is None      # 走单码
    with pytest.raises(ValueError, match="enabled.*布尔"):
        load_size_run(write("enabled = \"false\"\n"))             # 字符串恒真陷阱
