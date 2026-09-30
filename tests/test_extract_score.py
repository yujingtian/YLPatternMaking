"""⑦ score 测试：真实引擎出 ctx 后量特征（构造失衡组合出警告）。

金标：
- 基线配置（165/68A + 部件开）评分项齐全、S1/S2/S3 元素可量；
- 前中内收超大（ratio 0.9）→ 落档 warn；
- 前侧收量塌零（S3 新判据 2026-09-29）：实测症状配例 H94/W68 +
  balance 停 0（旧口径）→ warn；臀腰同调 balance=delta 抬回 → ok；
  H−W<10 直筒身材豁免；
- rise_adjust 越带 → 直裆深自洽 warn；
- 袋口弧深带（S1b）：深档 bulge 1.75 → 28% ok；引擎默认 0.5 → ≈8% 出下界 warn；
- 缺元素（front_pocket 关）→ S1 跳过不炸。

S3 旧「前后侧缝收量倒挂」判据随 curvy_waist_balance 旧口径退役
（2026-09-29）：臀腰同调后 curvy 大差款 fi > bi 接受（后片吃量靠育克
与省道），谓词单源 agent/extract/balance.py。
"""

from __future__ import annotations

from agent.extract.score import ScoreItem, score_features, warnings
from agent.extract.probe import probe_loop

_M = dict(waist=68, hip=91, knee=44, hem=34, front_rise=25, back_rise=33,
          outseam=102, thigh=58)


def _ctx(measurements=None, options=None):
    out = probe_loop(dict(measurements or _M), dict(options or {}))
    assert out.ok, out.message
    return out.ctx, dict(measurements or _M), dict(options or {})


def _find(items, keyword):
    return next(i for i in items if keyword in i.feature)


def test_score_baseline_items_present():
    ctx, meas, opts = _ctx(options={"front_pocket": True, "back_yoke": True,
                                    "belt_loop": True, "delta": 1.0,
                                    "front_intake_ratio": 0.2,
                                    "size_label": "27"})
    items = score_features(ctx, meas, opts)
    feats = [i.feature for i in items]
    assert any("袋口弦长" in f for f in feats)
    assert any("侧缝上段斜度" in f for f in feats)   # 前/后两条
    assert any("前侧收量" in f for f in feats)
    assert any("直裆深自洽" in f for f in feats)
    assert any("前中内收落档" in f for f in feats)
    # 基线自洽：直裆深与落档应 ok（ratio 0.2 → 0.2×5.75=1.15，mid 带 [1,1.5] 内）
    assert _find(items, "直裆深自洽").verdict == "ok"
    assert _find(items, "前中内收落档").verdict == "ok"
    assert isinstance(ScoreItem("f", "v", "b", "ok"), ScoreItem)


def test_score_intake_overflow_warns():
    """前中内收 0.9×5.75≈5.2：超 mid 带上限（落档 warn）。"""
    ctx, meas, opts = _ctx(options={"front_intake_ratio": 0.9,
                                    "size_label": "27"})
    items = score_features(ctx, meas, opts)
    assert _find(items, "前中内收落档").verdict == "warn"


def test_score_front_intake_collapse_warns():
    """前侧收量塌零（fi<0.5 且 H−W≥10）。fi 引擎精确律（2026-09-29 实测
    校准）：fi = (H−W)/4 + (balance−delta) − 前腰长调节 − 袋口吃省——①前中
    内收改形不改腰长不进 fi（前浪顶点由腰长闭合反推）。H82/W68（q=3.5，
    d=14≥10）：balance 停 0（旧口径症状：调节量不参与分配）+ 前腰长调节
    2.5 + 袋口吃省 1.0 → fi=−1.0 塌零 warn；同调 balance=delta=1.0 +
    常规调节 1.5 → fi=1.0 ok。"""
    m = dict(_M, hip=82)
    opts = {"front_pocket": True, "delta": 1.0, "front_pocket_dart_width": 1.0,
            "size_label": "27"}
    ctx, meas, o = _ctx(m, options=dict(opts, waist_balance=0.0,
                                        front_waist_dart=2.5))
    item = _find(score_features(ctx, meas, o), "前侧收量塌零")
    assert item.verdict == "warn" and float(item.value[:-2]) < 0.5
    ctx, meas, o = _ctx(m, options=dict(opts, waist_balance=1.0,
                                        front_waist_dart=1.5))
    item = _find(score_features(ctx, meas, o), "前侧收量塌零")
    assert item.verdict == "ok" and float(item.value[:-2]) >= 0.5


def test_score_front_intake_collapse_exempt_small_diff():
    """H−W<10 直筒身材豁免：前侧近铅垂合法，同配比塌零几何也不警。"""
    m = dict(_M, hip=76)          # 76−68=8 < 10
    ctx, meas, o = _ctx(m, options={"front_pocket": True, "delta": 1.0,
                                    "waist_balance": 0.0,
                                    "front_waist_dart": 2.5,
                                    "front_pocket_dart_width": 1.0,
                                    "size_label": "27"})
    assert _find(score_features(ctx, meas, o), "前侧收量塌零").verdict == "ok"


def test_score_rise_adjust_inconsistent_warns():
    """rise_adjust 4.5 → est 27.25 > 前浪−腰头 21：直裆深自洽 warn。"""
    ctx, meas, opts = _ctx(options={"rise_adjust": 4.5})
    items = score_features(ctx, meas, opts)
    assert _find(items, "直裆深自洽").verdict == "warn"


def test_score_mouth_sag_band():
    """S1b 袋口弧深/弦长（bulge 式）经典带 10%~32%——工厂 5015 实测真弧高
    3.36≈27% 定标。深档 bulge 1.75（真弧高 3.5）→ ok；引擎默认 0.5（渲染
    1.0cm ≈8%）→ 出下界 warn——2026-09-02「弧度和照片差距很大」配例的
    输出侧兜底哨兵（旧未校准三档 0.4/0.5 同样落此出界）。"""
    opts = {"front_pocket": True, "back_yoke": True, "belt_loop": True,
            "delta": 1.0, "front_intake_ratio": 0.2, "size_label": "27"}
    ctx, meas, o = _ctx(options=dict(opts, front_pocket_mouth_bulge=1.75))
    item = _find(score_features(ctx, meas, o), "袋口弧深")
    assert item.verdict == "ok"
    ctx, meas, o = _ctx(options=opts)          # 引擎默认 bulge 0.5
    item = _find(score_features(ctx, meas, o), "袋口弧深")
    assert item.verdict == "warn"


def test_score_skips_missing_pocket():
    ctx, meas, opts = _ctx(options={})   # front_pocket 默认关
    items = score_features(ctx, meas, opts)
    assert not any("袋口弦长" in i.feature for i in items)
    assert warnings(items) == [i for i in items if i.verdict == "warn"]
