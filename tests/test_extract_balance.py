"""A5 侧缝守卫金标（agent/extract/balance.py，2026-09-29）。

fi 引擎精确律（2026-09-29 实测校准，H82/W68 逐项验证）：

    fi = (H−W)/4 + (waist_balance − delta) − front_waist_dart − 袋口吃省ΔW

- H82/W68（q=3.5）b=d=1、无省口：fi=3.5；
- balance 每步 +0.25 → fi 精确 +0.25（斜率 1）；
- front_waist_dart / front_pocket_dart_width 各 1:1 吃 fi；
- **①前中内收（front_intake_ratio）不进 fi**：改形不改腰长——前浪顶点由
  腰长闭合反推、waist_side_point 由腰长定位，① 只挪前浪起点（ratio
  0.2/0.9 实测 fi 逐位相同）。设计稿 §1.2 的 ① 项据此修正，
  正确算术见 .doc/参数预测/腰围前后分配预测.md。

守卫行为金标：症状抬回（两轮步进）/ 到顶取最接近版 / 引擎拒画保持 /
用户亲说跳过（挂载层 extract_from_input）/ 豁免区不误伤（score 侧）。
"""

from __future__ import annotations

import pytest

from agent.extract import extract_from_input
from agent.extract.balance import (GUARD_STEP, front_intake_cm, is_collapsed,
                                   rebalance)
from agent.extract.probe import _run_once, probe_loop
from agent.extract.provider import FakeVLM
from agent.extract.score import score_features

# H82/W68：q=(H−W)/4=3.5、d=14≥10（不落豁免区）、standard 身材 delta=1.0
# （纯路径探针配比；全套派生键下该身材后外缝臀侧饱满度越带，管线挂载
# 金标用 W74/H91 健康窗配比，见 _DESC2）
_M = dict(waist=68, hip=82, knee=44, hem=34, front_rise=25, back_rise=33,
          outseam=102, thigh=58)

# 管线挂载配比：W74/H91（d=17≥10）全套派生键 L0 健康窗；深前腰长调节
# 塌零配方 = fwd 3.1（fi0=0.35）。watch_pocket 随调版关：深腰长调节挪腰侧
# 几何会触发小表袋射线不相交（已知默认几何缺口，存档见决策日志），此处
# 借调版态绕行、不修引擎
_DESC2 = ("女款中腰小脚牛仔裤，腰围74 臀围91 膝围44 脚口34 前浪25 后浪33 "
          "裤长102 大腿围58")
_SEED_COLLAPSE = {"front_waist_dart": (3.1, "调版：前腰长调节"),
                  "watch_pocket": (False, "调版：关小表袋")}


def _ctx_fi(measurements, options):
    """探针真跑后量 fi（ok 必须成立，塌零是形状病不是构造病）。"""
    out = probe_loop(dict(measurements), dict(options))
    assert out.ok, out.message
    return front_intake_cm(out.ctx)


# -- 精确律 ------------------------------------------------------------------------


def test_fi_exact_law():
    """fi = q + (balance−delta) − 前腰长调节 − 袋口吃省；① ratio 不进。"""
    base = {"front_pocket": True, "delta": 1.0, "waist_balance": 1.0,
            "front_pocket_dart_width": 1.0, "size_label": "27"}
    # b=d=1、省口 1.0 → fi = 3.5 − 1.0 = 2.5
    assert _ctx_fi(_M, base) == pytest.approx(2.5, abs=1e-6)
    # balance 步进斜率 1：1.0→1.5 即 fi +0.5
    assert _ctx_fi(_M, dict(base, waist_balance=1.5)) == \
        pytest.approx(3.0, abs=1e-6)
    # 前腰长调节 1:1 吃量：2.5 → fi 0.0（塌零配方）
    assert _ctx_fi(_M, dict(base, front_waist_dart=2.5)) == \
        pytest.approx(0.0, abs=1e-6)
    # ①前中内收改形不改腰长：ratio 0.2/0.9 fi 逐位相同
    assert _ctx_fi(_M, dict(base, front_intake_ratio=0.2)) == \
        pytest.approx(_ctx_fi(_M, dict(base, front_intake_ratio=0.9)),
                      abs=1e-9)


def test_front_intake_missing_elements_none():
    """元素缺失（部件未上版/ctx 不全）返回 None，谓词 False 不误伤。"""

    class _Stub:
        def point(self, name):
            raise KeyError(name)

    assert front_intake_cm(_Stub()) is None
    assert is_collapsed({"waist": 68, "hip": 82}, None) is False


def test_is_collapsed_predicate():
    """塌零谓词：fi<0.5 且 H−W≥10；豁免区/缺尺寸/None 一律 False。"""
    big = {"waist": 68, "hip": 82}          # d=14 ≥ 10
    small = {"waist": 68, "hip": 76}        # d=8 < 10 豁免
    assert is_collapsed(big, 0.49) is True
    assert is_collapsed(big, 0.5) is False  # 阈值边界：等于不塌
    assert is_collapsed(small, 0.0) is False
    assert is_collapsed({"waist": 68}, 0.0) is False
    assert is_collapsed({}, 0.1) is False


# -- 回喂（rebalance 纯路径） -------------------------------------------------------


def test_rebalance_lifts_collapse():
    """症状抬回：fi=0.10 塌零 → 两轮 +0.25 步进抬回 0.60，披露轨迹。"""
    opts = {"front_pocket": True, "delta": 1.0, "waist_balance": 1.0,
            "front_waist_dart": 2.4, "front_pocket_dart_width": 1.0,
            "size_label": "27"}
    ok, msg, _keys, ctx = _run_once(_M, opts)
    assert ok, msg
    assert front_intake_cm(ctx) == pytest.approx(0.1, abs=1e-6)  # 症状复现
    out, notes, ctx2 = rebalance(_M, opts, ctx)
    assert out["waist_balance"] == pytest.approx(1.5)            # 1.0+2×0.25
    assert front_intake_cm(ctx2) == pytest.approx(0.6, abs=1e-6)
    assert notes[0].startswith("侧缝守卫") and "0.10" in notes[0]
    assert "1.00→1.50" in notes[-1] and "抬回" in notes[-1]
    assert "0.60" in notes[-1]


def test_rebalance_exhausted_takes_closest():
    """到顶仍塌（省口吃量超步进预算）：取最接近版 + 建议核对腰臀尺寸。"""
    opts = {"front_pocket": True, "delta": 1.0, "waist_balance": 1.0,
            "front_waist_dart": 4.0, "front_pocket_dart_width": 1.0,
            "size_label": "27"}                 # fi=3.5−4.0−1.0=−1.5
    ok, msg, _keys, ctx = _run_once(_M, opts)
    assert ok, msg
    out, notes, ctx2 = rebalance(_M, opts, ctx)
    assert out["waist_balance"] == pytest.approx(1.5)            # 2 轮到顶
    assert "最接近版" in notes[-1] and "建议核对腰臀尺寸" in notes[-1]


def test_rebalance_engine_reject_keeps_last(monkeypatch):
    """整版重跑被引擎拒画：即停保持上一成功版（重跑而非版上补丁的代价
    控制）。_run_once 惰性 import，monkeypatch 模块属性即生效。"""
    from agent.extract import probe as probe_mod

    def _fail(measurements, options):
        return False, "构造失败：试抬被守卫测试拦下", [], None

    monkeypatch.setattr(probe_mod, "_run_once", _fail)
    opts = {"front_pocket": True, "delta": 1.0, "waist_balance": 1.0,
            "front_waist_dart": 2.4, "front_pocket_dart_width": 1.0,
            "size_label": "27"}

    class _Ctx:                                  # fi 量测桩（值不参与断言）
        def point(self, name):
            class _P:
                x, y = 0.0, 0.0
            return _P()

    out, notes, ctx2 = rebalance(_M, opts, _Ctx())
    assert out["waist_balance"] == pytest.approx(1.0)            # 原值不动
    assert ctx2 is not None
    assert "拒画" in notes[-1] and "建议核对腰臀尺寸" in notes[-1]


# -- 挂载层（extract_from_input：抬回 + 用户亲说跳过） -----------------------------


def test_guard_lifts_through_pipeline():
    """管线挂载：L0 过后量 fi → 塌零步进抬回，derived/评分/报告三处落账。
    W74/H91 全套派生键 L0 健康；调版深前腰长调节 3.1 → fi0=0.35 塌零 →
    守卫一轮 1.00→1.25 抬回 0.60。"""
    result = extract_from_input(describe=_DESC2, provider=FakeVLM([]),
                                seed_overrides=dict(_SEED_COLLAPSE))
    assert result.probe.ok and result.probe.stage == "L0"
    assert result.derived["delta"].value == pytest.approx(1.0)
    assert result.derived["waist_balance"].value == pytest.approx(1.25)
    assert "抬回" in result.derived["waist_balance"].evidence
    assert result.balance_notes[0].startswith("侧缝守卫") and \
        "0.35" in result.balance_notes[0]
    assert "1.00→1.25" in result.balance_notes[-1] and \
        "0.60" in result.balance_notes[-1]
    # score 用抬回后的 ctx：塌零警项转 ok
    item = next(i for i in result.score_items if "塌零" in i.feature)
    assert item.verdict == "ok" and item.value == "0.60cm"
    assert "侧缝守卫" in result.report_text


def test_guard_skips_user_set_balance():
    """用户亲说优先：waist_balance ∈ seed_overrides（调版账本设定过）时
    只量只披露不改——值保持 0.0、评分警 warn、报告照常披露。"""
    result = extract_from_input(
        describe=_DESC2, provider=FakeVLM([]),
        seed_overrides={**_SEED_COLLAPSE,
                        "waist_balance": (0.0, "调版：上一轮设定")})
    assert result.probe.ok and result.probe.stage == "L0"
    assert result.derived["waist_balance"].value == pytest.approx(0.0)
    assert any("已由调版设定" in n for n in result.balance_notes)
    item = next(i for i in result.score_items if "塌零" in i.feature)
    assert item.verdict == "warn"
    assert "侧缝守卫" in result.report_text


def test_guard_idle_on_healthy_config():
    """健康配比守卫静默：balance_notes 空、报告无守卫披露（不误触发）；
    臀腰同调基线 waist_balance == delta。"""
    result = extract_from_input(describe=_DESC2, provider=FakeVLM([]))
    assert result.probe.ok and result.probe.stage == "L0"
    assert result.balance_notes == []
    assert "侧缝守卫" not in result.report_text
    assert result.derived["waist_balance"].value == \
        pytest.approx(result.derived["delta"].value)   # 臀腰同调基线


# -- score 侧豁免（谓词单源的端到端复核） -------------------------------------------

def test_score_exempt_small_diff():
    """H−W<10 直筒身材豁免：同塌零配比 fi 再小也不警（不误伤）。"""
    m = dict(_M, hip=76)          # 76−68=8 < 10
    opts = {"front_pocket": True, "delta": 1.0, "waist_balance": 0.0,
            "front_waist_dart": 2.5, "front_pocket_dart_width": 1.0,
            "size_label": "27"}
    out = probe_loop(m, dict(opts))
    assert out.ok, out.message
    items = score_features(out.ctx, m, opts)
    item = next(i for i in items if "塌零" in i.feature)
    assert item.verdict == "ok"
    assert GUARD_STEP == 0.25     # 步进常量钉死（口径数字，改动需过设计）
