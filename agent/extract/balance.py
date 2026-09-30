"""腰围前后分配守卫（A 组 2026-09-29）：前侧收量塌零谓词 + 回喂。

口径（.doc/参数预测/腰围前后分配预测.md；决策日志 2026-09-29 臀腰同调条）：
- waist_balance = Δ 终值（臀腰同调）后代入引擎精确律（2026-09-29 实测
  校准，金标 tests/test_extract_balance.py）：
  fi = (H−W)/4 + (waist_balance − Δ) − 前腰长调节 − 袋口吃省 ΔW
  ——①前中内收**不进 fi**（改形不改腰长：前浪顶点由腰长闭合反推，
  waist_side_point 由腰长定位，① 只挪前浪起点）；故 fi 塌零的驱动只有
  balance−Δ 偏离与省口/腰长调节吃量，前片腰侧点与臀侧点共竖直线
  （实测症状）；
- 谓词只看前侧塌零：fi < 0.5 且 H−W ≥ 10（< 10 直筒身材前侧近铅垂合法，
  豁免不警不治）；后侧不设带——balance 前减后加 1:1 对搬，前侧抬起来
  后侧自动让位；curvy 大差款 fi > bi 接受（后片吃量靠育克与省道）；
- 回喂复用毗围闭环哲学：balance += 0.25 步进**整版重跑**（probe._run_once
  毫秒级，闭包不变量自动保持），不做版上补丁；≤2 轮、累计 |Δ| ≤ 1.0；
  每步 balance +0.25 即 fi +0.25（精确律斜率 1）；
  到顶仍塌取最接近版 + 披露「建议核对腰臀尺寸」；
- 用户亲说优先：waist_balance ∈ seed_overrides（调版账本设定过）时守卫
  只量只披露、不改值（挂载处在 extract_from_input 判定）。

score 的「前侧收量塌零」警项与本守卫共用同一谓词（本模块单源）：
score 只警不改，守卫负责改。
"""

from __future__ import annotations

import math

# 塌零阈值 0.5 定稿（用户口径 2026-09-29，不做工厂定标；后续若见矫正
# 过度/不足只调这一个数）
GUARD_THRESHOLD = 0.5
GUARD_STEP = 0.25          # balance 步进
GUARD_MAX_ROUNDS = 2       # 重跑轮数上限
GUARD_MAX_SHIFT = 1.0      # 累计 |Δbalance| 上限
_EXEMPT_DIFF = 10.0        # H−W < 10 直筒身材豁免


def _dist(p, q) -> float:
    return math.hypot(p.x - q.x, p.y - q.y)


def front_intake_cm(ctx) -> float | None:
    """前侧收量 fi = 前臀宽弦长 − 前腰净宽弦长（cm；元素缺失返回 None）。

    点名 front.waist_side_point / front.hip_outseam_point 等与 score 旧 S3
    同源（先画后量，不重复推导）。
    """
    try:
        fw = _dist(ctx.point("front.waist_side_point"),
                   ctx.point("front.rise_top_point"))
        fh = _dist(ctx.point("front.hip_outseam_point"),
                   ctx.point("front.hip_inner_point"))
    except (KeyError, TypeError, ValueError):
        return None
    return fh - fw


def is_collapsed(measurements: dict, fi: float | None) -> bool:
    """塌零谓词（score 警项与守卫回喂单源）：fi < 0.5 且 H−W ≥ 10。"""
    w, h = measurements.get("waist"), measurements.get("hip")
    if w is None or h is None or h - w < _EXEMPT_DIFF:
        return False
    return fi is not None and fi < GUARD_THRESHOLD


def rebalance(measurements: dict, options: dict, ctx) -> tuple[dict, list[str],
                                                               object]:
    """塌零回喂：balance += 0.25 步进整版重跑，≤2 轮、累计 |Δ| ≤ 1.0。

    返回 (options', notes, ctx')——ctx' 为最终采用版的 DraftContext（调用
    方以它替换 probe.ctx 供 score/守卫读数）；到顶仍塌取最接近版 + 披露。
    每轮重跑失败（引擎拒画）即停，保持上一成功版。
    """
    from .probe import _run_once   # 惰性：谓词使用方（score）不拖引擎

    opts = dict(options)
    base = opts.get("waist_balance", 0.0)
    base = float(base) if isinstance(base, (int, float)) \
        and not isinstance(base, bool) else 0.0
    fi0 = front_intake_cm(ctx)
    notes = [f"侧缝守卫：前侧收量 {fi0:.2f} 塌零（阈值 {GUARD_THRESHOLD}，"
             f"步进抬回）"]
    cur_ctx, cur_fi, cur_bal = ctx, fi0, base
    for _ in range(GUARD_MAX_ROUNDS):
        cand = round(cur_bal + GUARD_STEP, 2)
        if abs(cand - base) > GUARD_MAX_SHIFT + 1e-9:
            break
        trial = dict(opts)
        trial["waist_balance"] = cand
        ok, msg, _keys, tctx = _run_once(measurements, trial)
        if not ok:
            notes.append(f"试抬 waist_balance {cur_bal:.2f}→{cand:.2f} 引擎"
                         f"拒画（{msg[:80]}），保持 {cur_bal:.2f}")
            break
        opts, cur_ctx, cur_bal = trial, tctx, cand
        cur_fi = front_intake_cm(tctx)
        if not is_collapsed(measurements, cur_fi):
            notes.append(f"waist_balance {base:.2f}→{cand:.2f} 重跑抬回前侧"
                         f"收量 {cur_fi:.2f}")
            return opts, notes, cur_ctx
    if cur_bal == base:
        notes.append("守卫未能抬升（首轮即拒画），建议核对腰臀尺寸")
    else:
        notes.append(f"守卫步进到 {cur_bal:.2f}（≤{GUARD_MAX_ROUNDS} 轮/累计"
                     f"≤{GUARD_MAX_SHIFT}）前侧收量 {cur_fi:.2f} 仍塌，已取"
                     "最接近版，建议核对腰臀尺寸")
    return opts, notes, cur_ctx
