"""求援控制器 + 多轮编排（智能体一期，2026-09-21）：零打扰三原则。

轮次算法（每轮幂等重跑整条管线，账本种子注入，后端无状态）：

  replay 账本（用户亲说累积）→ extract_from_input
  （describe=全轮拼接 / photos=未缓存新照片 / prior_observation=VLM 缓存）
  ├─ ExtractError(missing) → 求援卡：缺尺寸批量问一次（要照片优先于问行话）
  ├─ probe L4（四轮兜底全败）→ 求援卡：请用户核对尺寸
  └─ 其余（含 L1~L3 自愈回退）→ 交卷：payload + 账本摘要 + 待确认标注，
     **不打断**（能画就画；回退键/低置信键/评分警告进 review 披露）

求援卡文案为模板拼装（说人话、不吐行话键名给用户）；LLM 润色节点
（卡片自然语言化 + 自由回答映射）为二期增强，结构已按卡片的
asks/want_photos/message 三段预留。

口径：.doc/python工程设计.md §10.9；会话数据模型见 agent/session.py。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .extract import ExtractError, extract_from_input
from .extract.adjust import (ADJUST_TABLE, ADJUST_TRIGGER, AdjustResult,
                             adjust_view_from_payload, map_adjustment)
from .extract.parse import parse_describe
from .extract.schema import _MEAS_LABELS
from .session import (Event, Session, observation_from_dict,
                      observation_to_dict, replay)


# -- 求援卡 --------------------------------------------------------------------

@dataclass
class AskItem:
    """单条求援项：键（内部名）+ 人话标签 + 原因 + 回答示例。"""

    key: str
    label: str
    why: str
    example: str


@dataclass
class HelpCard:
    """批量求援卡：一轮只发一张，所有缺口合并在此。"""

    asks: list[AskItem]
    want_photos: list[str]      # 建议补拍清单（要照片优先于问行话）
    message: str                # 面向用户的总文案（说人话）

    def to_dict(self) -> dict:
        return {"asks": [{"key": a.key, "label": a.label, "why": a.why,
                          "example": a.example} for a in self.asks],
                "want_photos": list(self.want_photos),
                "message": self.message}


def _missing_card(missing: list[str], has_photos: bool) -> HelpCard:
    """缺必填尺寸卡：批量问数字；无照片时顺带建议补照（照片比行话便宜）。"""
    asks = [AskItem(k, _MEAS_LABELS.get(k, k),
                    "描述、码号换算与模型补漏后仍缺（不编数值）",
                    f"{_MEAS_LABELS.get(k, k)}{_SAMPLE.get(k, 74)}")
            for k in missing]
    want = [] if has_photos else ["正面平铺照", "背面平铺照"]
    labels = "、".join(a.label for a in asks)
    msg = (f"还差 {len(missing)} 项基本尺寸：{labels}。"
           "直接回复数字即可，写在一句里也行（例：腰围74 前浪25 裤长102）；"
           "或报尺码（如 29码，我来换算腰围）")
    if want:
        msg += "；也可以补一张平铺照片"
    return HelpCard(asks, want, msg + "。")


# 各键回答示例的顺手值（人话示范，非默认值）
_SAMPLE = {"waist": 74, "hip": 91, "knee": 44, "hem": 34, "front_rise": 25,
           "back_rise": 33, "outseam": 102, "thigh": 58}


def _probe_card(result) -> HelpCard:
    """探针 L4 卡：参数组合画不出合法整版，请用户重点核对尺寸。"""
    keys = list(getattr(result.probe, "error_keys", []) or [])
    meas = [k for k in keys if k in _MEAS_LABELS] or ["waist", "hip",
                                                      "front_rise"]
    asks = [AskItem(k, _MEAS_LABELS.get(k, k), "引擎四轮兜底仍画不出整版",
                    f"{_MEAS_LABELS.get(k, k)}{_SAMPLE.get(k, 74)}")
            for k in meas]
    labels = "、".join(a.label for a in asks)
    msg = ("这组参数我画不出一张合法的版（引擎多轮兜底都失败）。"
           f"多半是尺寸量得不准，麻烦重点核对：{labels}；"
           "也可以直接改口重报（例：腰围74），我按新值重画。")
    return HelpCard(asks, ["正面平铺照"], msg)


# -- 轮次编排 ------------------------------------------------------------------

@dataclass
class TurnOutcome:
    """一轮产物：会话新态 + 卡/交卷二选一 + 原始结果（CLI 写盘用）。"""

    session: Session
    card: HelpCard | None
    delivery: dict | None
    result: object = None

    def to_dict(self) -> dict:
        return {"session": self.session.to_dict(),
                "card": self.card.to_dict() if self.card else None,
                "delivery": self.delivery}


def _digest_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def _mapping_provider(config_path: str | None):
    """调版映射节点 provider（显式注入优先；测试 monkeypatch 注入 FakeVLM）。

    未配置返回 None——映射静默跳过，绝不 503（零打扰口径）。
    """
    try:
        from .extract.provider import OpenAICompatibleVLM, VLMConfig
        return OpenAICompatibleVLM(VLMConfig.load(config_path))
    except Exception:
        return None


def _last_adjust_view(session: Session) -> dict | None:
    """最近一次交卷的映射面快照（probe 回退后的真实值）。

    旧会话（无 adjust_view）-> None：映射跳过，本次交卷写入后恢复——
    降级安全。
    """
    for ev in reversed(session.events):
        if ev.role == "agent" and ev.kind == "deliver":
            view = ev.data.get("adjust_view")
            if view:
                return view
    return None


def run_turn(session: Session, text: str, photos: tuple | list = (), *,
             config_path: str | None = None, provider=None,
             thinking: str | None = None, run_probe: bool = True,
             run_score: bool = True, max_refeed: int = 2,
             progress=None) -> TurnOutcome:
    """一轮对话：append 用户事件 → 管线重跑 → 求援卡或交卷。

    photos：本轮随请求的照片路径（CLI 跨轮全量累积；前端提交成功即清
    上传池、只发本轮新增，2026-09-24——已识别证据在 session.vlm_cache，
    后续轮零照片也安全），本函数按 vlm_cache 指纹去重，只把未识别的新
    照片送进 S2——「VLM 证据一次识别永久入账本」的落点。
    """
    turn = session.events[-1].turn + 1 if session.events else 1
    digests = [_digest_file(p) for p in photos]

    # 调版映射（2026-09-27，口径 .doc/python工程设计.md §10.9.2）：交卷后
    # 每轮都调（ADJUST_TRIGGER）；在 user 事件 append **之前**跑，结果随
    # 本轮事件 data 落账，replay 同轮即入种子。FakeVLM 单队列同轮出队
    # 顺序：映射 -> S1 补漏 -> S2（测试排序铁律）
    adjust_data = None
    if (ADJUST_TRIGGER != "off" and text.strip()
            and any(e.role == "agent" and e.kind == "deliver"
                    for e in session.events)):
        view = _last_adjust_view(session)
        if view is not None:
            mp = provider or _mapping_provider(config_path)
            history = [{"turn": e.turn, "text": e.text,
                        "adjust": e.data.get("adjust")}
                       for e in session.events
                       if e.role == "user" and e.text]
            res = map_adjustment(history, view, text, mp)
            # 同轮碰撞：本轮词典（parse_describe.hints）命中的键亲说优先，
            # 映射同键剔除进 dropped（「本轮已按你的明确说法处理」）
            spoken = set(parse_describe(text).hints)
            if spoken and res.entries:
                keep, drop = [], list(res.dropped)
                for ent in res.entries:
                    if ent.key in spoken:
                        drop.append(f"本轮已按你的明确说法处理：{ent.key}")
                    else:
                        keep.append(ent)
                res = AdjustResult(tuple(keep), res.note, tuple(drop))
            if res.entries or res.note or res.dropped:
                adjust_data = res.to_dict()

    # 映射结果随事件 data["adjust"] 落账（replay/history/_build_delivery
    # 三处同键读取；无映射轮 data 空）
    session.events.append(Event(turn, "user", "input", text=text,
                                photos=digests,
                                data={"adjust": adjust_data}
                                if adjust_data else {}))
    led = replay(session)

    # 调版回退表（L0.5 用）：本轮映射键 -> 上一版值（取自上个交卷的
    # adjust_view 快照；探针 L0 失败先撤回重试，版面保持原样不截肢）
    adjust_revert = None
    if adjust_data:
        prev = _last_adjust_view(session)   # 本轮只 append 了 user 事件
        if prev:
            adjust_revert = {
                e["key"]: prev[e["key"]]
                for e in adjust_data.get("entries") or []
                if isinstance(e, dict) and e.get("key") in prev}

    cached = set(session.vlm_cache.get("photos", ()))
    new_photos = [p for p, d in zip(photos, digests) if d not in cached]
    prior = None
    if session.vlm_cache.get("entries"):
        prior = observation_from_dict(session.vlm_cache)
    describe_all = "；".join(e.text for e in session.events
                             if e.role == "user" and e.text)

    # 种子装配：词典 hint + 调版账本分通道。hint 通道同键与亲说词典比
    # 轮次（跨轮后轮胜、同轮平手亲说胜——账本后写覆盖时序天然如此）；
    # override 通道走绝对值直写（虚键已落 bulge 绝对值）
    seed_hints = {k: r.value for k, r in led.hints.items()}
    seed_overrides: dict[str, tuple] = {}
    for k, row in led.adjustments.items():
        spec = ADJUST_TABLE.get(k)
        if spec is None:
            continue                      # 表演进删键 -> 重放静默休眠
        if spec.channel == "hint":
            h = led.hints.get(k)
            if h is None or row.turn > h.turn:
                seed_hints[k] = row.value
        else:
            seed_overrides[k] = (row.value, f"调版：{row.evidence}")

    try:
        result = extract_from_input(
            describe=describe_all, photos=new_photos, provider=provider,
            thinking=thinking, run_probe=run_probe, run_score=run_score,
            max_refeed=max_refeed, config_path=config_path,
            progress=progress,
            seed_measurements={k: (r.value, r.evidence)
                               for k, r in led.measurements.items()},
            seed_hints=seed_hints,
            seed_overrides=seed_overrides or None,
            adjust_revert=adjust_revert,
            seed_size_label=(led.size_label.value
                             if led.size_label is not None else None),
            seed_shrinkage=(led.shrinkage.value
                            if led.shrinkage is not None else None),
            prior_observation=prior)
    except ExtractError as e:
        if not e.missing:
            raise                 # 配置类（无 missing 清单）→ 上层 503 口径
        # 有照片证据 = 本轮带了照片，或会话 vlm_cache 已有照片观测
        #（前端清池口径 2026-09-24：照片已提交但本轮未重发，不再建议补拍）
        card = _missing_card(e.missing,
                             has_photos=bool(digests) or prior is not None)
        session.events.append(Event(turn, "agent", "card", data=card.to_dict()))
        return TurnOutcome(session, card, None)

    # VLM 缓存落账：快照为 merged（旧批次 ∪ 新批次，新覆盖旧同键）
    if new_photos and result.observation is not None:
        snap = observation_to_dict(result.observation)
        snap["photos"] = sorted({*cached, *(d for d in digests
                                            if d not in cached)})
        session.vlm_cache = snap

    if run_probe and result.probe.stage == "L4":
        card = _probe_card(result)
        session.events.append(Event(turn, "agent", "card", data=card.to_dict()))
        return TurnOutcome(session, card, None, result=result)

    delivery = _build_delivery(result, led, turn, adjust_data)
    session.events.append(Event(
        turn, "agent", "deliver",
        data={"summary": delivery["summary"], "review": delivery["review"],
              # 映射面快照（probe 回退后的真实值）：下轮映射的当前值/门控
              # 基线；账本绝对值独立于此（重放永不依赖快照）
              "adjust_view": adjust_view_from_payload(delivery["options"])}))
    return TurnOutcome(session, None, delivery, result=result)


def _build_delivery(result, led, turn: int, adjust_data: dict | None = None) -> dict:
    """交卷体：一期 payload + 待确认标注（review）+ 账本摘要（ledger）
    + 调版披露（adjust，2026-09-27；无调版轮缺省不带该键）。"""
    payload = result.to_web_payload()
    keys = payload["keys"]
    review = {
        # 探针自愈回退键（引擎默认接管，非用户确认值）
        "reverted": list(result.reverted),
        # 低置信键（预填惯例 0.3~0.4 档）：交卷不阻断，确认屏兜底
        "low_confidence": sorted(
            k for k, m in keys.items()
            if m["confidence"] < 0.5 and k not in result.measurements),
        "score_warnings": [s["feature"] for s in payload["score"]
                           if s["verdict"] == "warn"],
    }
    ledger = {"measurements": {k: {"value": r.value, "turn": r.turn,
                                   "evidence": r.evidence}
                               for k, r in led.measurements.items()},
              "size_label": ({"value": led.size_label.value,
                              "turn": led.size_label.turn}
                             if led.size_label is not None else None)}
    summary = {"turn": turn, "model": result.model_name,
               "photo_count": result.photo_count}
    delivery = {**payload, "review": review, "ledger": ledger,
                "summary": summary}
    if adjust_data:
        from .extract.probe import fallback_value
        adj = dict(adjust_data)
        applied = []
        for e in adj.get("entries") or []:
            k = e.get("key")
            if k in keys:
                applied.append({"key": k, "value": keys[k]["value"]})
            elif k in result.reverted:
                # probe 回退键已从 keys 弹出：引擎默认值兜底显示（诚实读数）
                applied.append({"key": k, "value": fallback_value(k)})
        # 被回退的映射键：note 追加披露（下轮如仍要求会再试并再披露）
        reverted_adj = sorted({e.get("key") for e in adj.get("entries") or []
                               if e.get("key") in result.reverted})
        note = str(adj.get("note") or "")
        if reverted_adj:
            labels = "、".join(
                ADJUST_TABLE[k].label if k in ADJUST_TABLE else k
                for k in reverted_adj)
            note = (f"{note}；" if note else "") + (
                f"引擎校验回退：{labels}（回默认，下轮如仍要求会再试并再披露）")
        # L0.5 调版回退（2026-09-27）：本轮调整未生效、值保持上一版——
        # 键仍在 keys（值即上一版值），note 换措辞披露
        kept = dict(getattr(getattr(result, "probe", None),
                            "adjust_kept", None) or {})
        entry_keys = {e.get("key") for e in adj.get("entries") or []}
        kept_adj = sorted(k for k in kept if k in entry_keys)
        if kept_adj:
            labels = "、".join(
                ADJUST_TABLE[k].label if k in ADJUST_TABLE else k
                for k in kept_adj)
            note = (f"{note}；" if note else "") + (
                f"本轮调整未生效：{labels}（引擎校验未过，已保持上一版；"
                "下轮如仍要求会再试并再披露）")
        delivery["adjust"] = {"note": note, "applied": applied,
                              "dropped": list(adj.get("dropped") or []),
                              "reverted": reverted_adj}
    return delivery


# -- 中间版（until 逐段试画，CLI --staged / 前端版生长展示同源） -----------------

MILESTONE_STEPS = ("draw_front_rise", "draw_front_inseam_curves",
                   "draw_back_rise")


def render_milestones(m, o, out_dir: str) -> list[str]:
    """三里程碑中间版 SVG：版按打版真实顺序「长」出来的落点。"""
    from ylpattern.exporters import svg as svg_exp
    from ylpattern.flows.closure import run_with_thigh_closure

    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    out: list[str] = []
    for i, step in enumerate(MILESTONE_STEPS, 1):
        ctx, _ = run_with_thigh_closure(m, o, until=step)
        path = base / f"sheet_{i:02d}_{step}.svg"
        svg_exp.write_sheet_svg(ctx.sheet, str(path),
                                show_labels=o.show_labels)
        out.append(str(path))
    return out
