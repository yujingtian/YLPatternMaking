"""⑥ validate + probe 测试。

- validate：复用 build_issues 的构造归因 + 派生区间 warning；
- probe：L0~L4 状态机。引擎真跑用标准 165/68A 尺寸（_FALLBACK_M 同源值）；
  L1/L2/L3 阶梯用 monkeypatch 注入确定性失败（不依赖引擎特定炸法），
  成功路径（L0）走真实 run_with_thigh_closure。
金标：L0 全默认零选项通过；L1 归因回退后通过；L2 数值回退保留款式；
L3 关开关；L4 header 拒直出注记。
"""

from __future__ import annotations

import pytest

import agent.extract.probe as probe_mod
from agent.extract.probe import (
    ProbeOutcome,
    _attribute,
    fallback_value,
    probe_loop,
    run_with_thigh_closure,
)
from agent.extract.validate import derive_sanity, issue_keys, validate_candidate

# 常规女裤 165/68A（与 validate._FALLBACK_M / examples/size_female_165 同源）
_M = dict(waist=68, hip=91, knee=44, hem=34, front_rise=25, back_rise=33,
          outseam=102, thigh=58)


# -- validate -------------------------------------------------------------------


def test_validate_candidate_ok_and_measurement_error():
    ok, issues = validate_candidate(dict(_M), {"delta": 1.0})
    assert ok and not issues
    bad = dict(_M, hip=60)   # 臀围 <= 腰围：跨字段关系命中触发键
    ok, issues = validate_candidate(bad, {})
    assert not ok
    assert issue_keys(issues) & {"hip", "waist"}


def test_validate_candidate_options_error():
    ok, issues = validate_candidate(dict(_M), {"delta": 3.0})
    assert not ok                      # 引擎 post_init 越界（delta 0~2.0 硬校验）
    assert "delta" in issue_keys(issues)


def test_derive_sanity_ranges():
    assert derive_sanity({"back_intake": 5.5}) != []
    assert derive_sanity({"rise_adjust": -4.0}) != []
    assert derive_sanity({"front_pocket_dart_width": 1.6}) != []
    assert derive_sanity({"back_intake": 3.5, "rise_adjust": 0.75,
                          "front_pocket_dart_width": 0.8,
                          "front_intake_ratio": 0.538, "delta": 1.0,
                          "waist_balance": 0.0}) == []
    # 区间复核是 warning 级：单独跑不阻断
    ok, _ = validate_candidate(dict(_M), {"front_intake_ratio": 0.05})
    assert ok  # 0.05 恰在界内
    assert derive_sanity({"front_intake_ratio": 0.04}) != []


# -- fallback / 归因 --------------------------------------------------------------


def test_fallback_value_engine_defaults():
    assert fallback_value("front_pocket") is False
    assert fallback_value("belt_loop_count") == 5
    assert fallback_value("back_yoke_mid_anchors") == ()
    assert fallback_value("不存在键") is None


def test_attribute_longest_key_wins():
    keys = _attribute("back_yoke_cb_dist 越界", {"back_yoke": True,
                                                 "back_yoke_cb_dist": 6.0})
    assert keys == ["back_yoke_cb_dist"]


# -- probe 阶梯 ------------------------------------------------------------------


def test_probe_l0_real_engine_run():
    """真实引擎：标准尺寸 + 典型部件开关，L0 直接过（探针金标）。"""
    out = probe_loop(dict(_M), {"front_pocket": True, "back_yoke": True,
                                "belt_loop": True, "delta": 1.0})
    assert out.ok and out.stage == "L0"
    assert out.ctx is not None
    assert out.header == ""


def test_probe_l0_construction_error():
    out = probe_loop(dict(_M, hem=-5), {"delta": 1.0})
    assert not out.ok and out.stage == "L4"
    assert "构造失败" in out.message
    assert "探针未通过" in out.header and "--draft" in out.header


def test_probe_l1_targeted_revert(monkeypatch):
    """归因键回退后通过：注入首轮点名 front_pocket_p2_drop 的引擎异常。"""
    calls: list[dict] = []
    real = run_with_thigh_closure

    def fake(m, o, **kw):
        calls.append({"p2": getattr(o, "front_pocket_p2_drop", None),
                      "rise": getattr(o, "rise_adjust", None)})
        if getattr(o, "front_pocket_p2_drop", None) == 99.0:
            raise ValueError("front_pocket_p2_drop 越界（探针注入）")
        return real(m, o, **kw)

    monkeypatch.setattr(probe_mod, "run_with_thigh_closure", fake)
    out = probe_loop(dict(_M), {"front_pocket": True,
                                "front_pocket_p2_drop": 99.0})
    assert out.ok and out.stage.startswith("L1")
    assert out.reverted == ["front_pocket_p2_drop"]
    assert len(calls) == 2          # 失败一轮 + 回退一轮
    assert calls[1]["p2"] == 7.5    # 回退到引擎默认


def test_probe_l2_numeric_revert(monkeypatch):
    """无键可归因 → 数值键全回退、款式开关保留。"""
    real = run_with_thigh_closure

    def fake(m, o, **kw):
        if getattr(o, "rise_adjust", 0.0) != 0.0 or \
                getattr(o, "delta", 1.0) != 1.0:
            raise RuntimeError("几何自相交（探针注入，无键名）")
        assert o.front_pocket is True     # 款式保留
        return real(m, o, **kw)

    monkeypatch.setattr(probe_mod, "run_with_thigh_closure", fake)
    out = probe_loop(dict(_M), {"front_pocket": True, "rise_adjust": 3.75,
                                "delta": 1.35})
    assert out.ok and out.stage == "L2"
    assert set(out.reverted) >= {"rise_adjust", "delta"}
    assert "front_pocket" not in out.reverted


def test_probe_l3_switch_off(monkeypatch):
    """数值回退仍炸（开关组合炸）→ 关可选开关跑基线。"""
    real = run_with_thigh_closure

    def fake(m, o, **kw):
        if o.front_pocket or o.back_yoke or o.belt_loop:
            raise RuntimeError("部件组合炸（探针注入，无键名）")
        return real(m, o, **kw)

    monkeypatch.setattr(probe_mod, "run_with_thigh_closure", fake)
    out = probe_loop(dict(_M), {"front_pocket": True, "back_yoke": True,
                                "rise_adjust": 2.25})
    assert out.ok and out.stage == "L3"
    assert "front_pocket" in out.reverted and "rise_adjust" in out.reverted


def test_probe_l4_header(monkeypatch):
    def fake(m, o, **kw):
        raise RuntimeError("永远炸（探针注入）")

    monkeypatch.setattr(probe_mod, "run_with_thigh_closure", fake)
    out = probe_loop(dict(_M), {"front_pocket": True})
    assert not out.ok and out.stage == "L4"
    assert out.ctx is None
    assert out.header.startswith("探针未通过（L4）")


def test_probe_outcome_dataclass_defaults():
    po = ProbeOutcome(False, "L4", "msg")
    assert po.error_keys == [] and po.log == [] and po.reverted == []
    assert po.ctx is None and po.header == ""


# -- 真实引擎 L1（不注入）：watch_pocket 纯默认几何缺口兜底 ------------------------


def test_probe_watch_pocket_companion_survives():
    """配套包（offset_from_side=2.0 + facing）必须 L0 通过（缺口绕行金标）。"""
    out = probe_loop(dict(_M), {
        "front_pocket": True, "front_pocket_facing": True,
        "watch_pocket": True, "watch_pocket_mode": "facing_intersect",
        "watch_pocket_offset_from_side": 2.0,
    })
    assert out.ok, out.message
