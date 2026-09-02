"""⑧ emit/report 回环金标：纯描述一条龙 -> 写盘 -> from_file 回读 ->
run_with_thigh_closure 真跑通过（与 _cmd_draft 同入口，产物即最终验收）。

金标口径：描述 8 键全中（无照片无模型），S2 整段跳过；
extracted.toml 与 examples/ 同构（[measurements] -> [options]，逐键来源注释）；
报告含七段结构与探针轨迹。发射前回验：未知键 TypeError 拦截。
"""

from __future__ import annotations

import pytest

from agent.extract import extract_from_input
from agent.extract.derive import KeyMeta
from agent.extract.emit import build_size_text, write_outputs
from ylpattern.flows.closure import run_with_thigh_closure
from ylpattern.params import Measurements, PatternOptions

_DESC = ("女款27码高腰小脚牛仔裤，腰围74 臀围91 膝围44 脚口34 前浪25 后浪33 "
         "裤长102 大腿围58，微弹面料，五袋款带小表袋裤耳")


def _run(tmp_path, describe=_DESC):
    result = extract_from_input(describe=describe)
    size_path, report_path = write_outputs(str(tmp_path / "out"),
                                           result.size_text, result.report_text)
    return result, size_path, report_path


def test_round_trip_draft_runs(tmp_path):
    """回环金标：emit 的 toml 能被 draft 入口真跑出整版。"""
    result, size_path, _ = _run(tmp_path)
    assert result.probe.ok, f"{result.probe.stage}：{result.probe.message}"
    m = Measurements.from_file(str(size_path))
    o = PatternOptions.from_file(str(size_path))
    ctx, _trace = run_with_thigh_closure(m, o)
    # 真出了版不是空壳：前后片基准元素 + 部件开关对应的元素在版上
    for name in ("front.waist_side_point", "front.rise_top_point",
                 "front.pocket_p1", "back.hip_inner_final"):
        assert name in ctx.sheet, name


def test_toml_structure_and_sources(tmp_path):
    result, size_path, _ = _run(tmp_path)
    text = size_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0].startswith("# 照片参数提取")
    assert any(l.startswith("[measurements]") for l in lines)
    assert any(l.startswith("[options]") for l in lines)
    assert text.index("[measurements]") < text.index("[options]")
    # 8 键尺寸逐键来源（描述摘录）
    for k in ("waist", "hip", "knee", "hem", "front_rise", "back_rise",
              "outseam", "thigh"):
        row = next(l for l in lines if l.startswith(f"{k} = "))
        assert "# 来源：描述" in row, row
    # 选项标量段逐键 KeyMeta 注释（遇子表 [options.x] 即止）
    opt_rows = []
    opt_start = next(i for i, l in enumerate(lines) if l == "[options]")
    for l in lines[opt_start + 1:]:
        if l.startswith("["):
            break
        if "=" in l:
            assert "# 来源：" in l, l
            opt_rows.append(l)
    assert opt_rows                      # [options] 非空（开关+派生至少若干键）
    assert "size_label" in text          # 条件键发射


def test_report_sections(tmp_path):
    _, _, report_path = _run(tmp_path)
    text = report_path.read_text(encoding="utf-8")
    for sec in ("一、款式摘要", "二、款式判定轨迹", "三、尺寸", "四、派生参数",
                "五、校验与探针", "六、打版后合理性评分"):
        assert sec in text
    assert "探针轨迹" in text
    assert "waist" in text and "74" in text


def test_write_outputs_paths(tmp_path):
    result = extract_from_input(describe=_DESC)
    out = tmp_path / "产物"
    size_path, report_path = write_outputs(str(out), result.size_text,
                                           result.report_text)
    assert size_path == out / "extracted.toml"
    assert report_path == out / "extract_report.md"
    assert size_path.read_text(encoding="utf-8") == result.size_text
    assert report_path.read_text(encoding="utf-8") == result.report_text


def test_emit_rejects_unknown_option_key():
    """发射前回验：白名单外键写盘前拦截（TypeError），不产出坏 toml。"""
    meta = {"delta": KeyMeta("delta", 1.0, "查表", 0.9, "DELTA_PRESETS"),
            "no_such_key": KeyMeta("no_such_key", 1, "照片", 0.9, "口胡")}
    with pytest.raises(TypeError):
        build_size_text({"waist": 74, "hip": 91, "knee": 44, "hem": 34,
                         "front_rise": 25, "back_rise": 33, "outseam": 102},
                        {}, meta, ["测试"])
