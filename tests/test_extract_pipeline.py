"""⑨ 管线缝合 + CLI 测试：FakeVLM 全程不触网（真实端到端见验证清单）。

- S1 全中 → 零模型调用（FakeVLM([]) 空队列即哨兵：多打一次就炸）；
- S1 漏键 → 恰一次补漏调用并采纳带内值；带外值丢弃 → ExtractError 清单；
- S2 编辑确认：照片 override（conf>0.5 + evidence）进 merged，白名单外键披露；
- --no-geometry 跳探针（ok=False，--draft 拒直出）；
- to_web_payload 形状（二期 POST /api/extract 直用）；
- CLI：纯描述 exit 0 出双产物 + --draft 直出 sheet.svg；缺必填 exit 2 列清单。
"""

from __future__ import annotations

import json

from agent.extract import ExtractError, extract_from_input
from agent.extract.provider import FakeVLM

_DESC = ("女款高腰小脚牛仔裤，腰围74 臀围91 膝围44 脚口34 前浪25 后浪33 "
         "裤长102 大腿围58，微弹面料，五袋款带小表袋裤耳")
_DESC_MISSING = "女款小脚牛仔裤，腰围74 臀围91 膝围44 脚口34 前浪25 裤长102"

_S2_REPLY = json.dumps({
    "front_patch": {"value": True, "confidence": 0.9,
                    "evidence": "正面照腰下明贴袋，双针明线可见"},
    "waistband_type": {"value": "curved", "confidence": 0.85,
                       "evidence": "腰头上口在侧缝处下凹弧线，与裤身一体顺接"},
    "bogus_key": 1,
}, ensure_ascii=False)


def test_s1_complete_zero_calls():
    """描述 8 键全中：空队列 FakeVLM 不被调用（多打一次即 AssertionError）。"""
    result = extract_from_input(describe=_DESC, provider=FakeVLM([]))
    assert result.measurements["waist"] == 74.0
    assert result.probe.ok
    assert not result.dropped


def test_s1_fill_missing_single_call():
    vlm = FakeVLM(['{"back_rise": 33}'])
    result = extract_from_input(describe=_DESC_MISSING, provider=vlm)
    assert len(vlm.calls) == 1                       # 恰一次补漏，无 S2（无照片）
    assert "back_rise" in vlm.calls[0]["prompt"]
    assert result.measurements["back_rise"] == 33.0
    assert "模型补漏" in result.size_text


def test_s1_fill_out_of_band_discarded():
    """补漏答案 999 超合理带 → 弃，仍缺 → ExtractError 列清单退出。"""
    vlm = FakeVLM(['{"back_rise": 999}'])
    try:
        extract_from_input(describe=_DESC_MISSING, provider=vlm)
    except ExtractError as e:
        assert e.missing == ["back_rise"]
    else:
        raise AssertionError("缺必填尺寸未报 ExtractError")


def test_s2_photo_override_and_dropped():
    vlm = FakeVLM([_S2_REPLY])
    result = extract_from_input(describe=_DESC, photos=("f.jpg", "b.jpg"),
                                provider=vlm, run_probe=False)
    assert len(vlm.calls) == 1
    assert len(vlm.calls[0]["images"]) == 2          # 两张照片进同一次调用
    # 开关 override：front_patch 惯例先验 False → 照片翻 True，来源照片
    fp = result.merged.switches["front_patch"]
    assert fp.value is True and fp.source == "照片"
    assert "明贴袋" in fp.evidence
    # 枚举 override：弯腰头
    assert result.merged.enums["waistband_type"].value == "curved"
    assert "bogus_key" in result.dropped             # 白名单外键披露
    assert result.probe.stage == "跳过" and not result.probe.ok


def test_no_geometry_skips_probe():
    result = extract_from_input(describe=_DESC, run_probe=False)
    assert result.probe.stage == "跳过"
    assert not result.probe.ok                        # --draft 拒直出
    assert result.score_items == []                   # 无 ctx 无从评分


def test_to_web_payload_shape():
    result = extract_from_input(describe=_DESC, run_probe=False)
    payload = result.to_web_payload()
    assert set(payload) >= {"measurements", "options", "keys", "issues",
                            "probe", "score"}
    assert payload["measurements"]["waist"] == 74.0
    assert "delta" in payload["options"]
    k = payload["keys"]["delta"]
    assert set(k) == {"value", "source", "confidence", "evidence"}
    # 尺寸键也进 keys（source=描述、置信顶格、evidence 带 parse 溯源文案）
    mw = payload["keys"]["waist"]
    assert mw["source"] == "描述" and mw["confidence"] == 1.0
    assert mw["evidence"]


# -- CLI ------------------------------------------------------------------

def _cli(argv):
    from agent.cli import main
    return main(argv)


def test_cli_pure_describe_with_draft(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                       # 隔离项目根 vlm.toml
    rc = _cli(["extract", "--describe", _DESC, "--out-dir", "out", "--draft"])
    assert rc == 0
    assert (tmp_path / "out" / "extracted.toml").is_file()
    assert (tmp_path / "out" / "extract_report.md").is_file()
    assert (tmp_path / "out" / "sheet.svg").is_file()   # 探针过 → 直出


def test_cli_missing_keys_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = _cli(["extract", "--describe", _DESC_MISSING, "--out-dir", "out"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "back_rise" in err and "缺失" in err
    assert not (tmp_path / "out" / "extracted.toml").is_file()


def test_cli_no_geometry_refuses_draft(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = _cli(["extract", "--describe", _DESC, "--out-dir", "out",
               "--no-geometry", "--draft"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "拒绝" in err
    assert not (tmp_path / "out" / "sheet.svg").exists()
