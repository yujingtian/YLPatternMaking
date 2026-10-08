"""求援控制器 + 多轮编排（智能体一期，2026-09-21）：零打扰三原则。

轮次算法（每轮幂等重跑整条管线，账本种子注入，后端无状态）：

  replay 账本（用户亲说累积）→ extract_from_input
  （describe=本轮叙事 + 账本摘要 context_brief / S1 补漏=全史 /
   photos=未缓存新照片 + photo_meta 三类标注 / prior_observation=VLM
   缓存；2026-09-29 B1 拆分 + C 照片三类）
  定向复查（D，2026-09-29，设计 §3）：映射判 action=recheck →
  本轮类别照片在手直接复查；无片发 directive（两段握手，Web 前端
  fulfill="recheck" 自动附片续发 / CLI :photo 补片后下一轮续执行）。
  复查 = 聚焦 VLM 一次调用（该组键 + 仅该组判据 + 基线 + 原话）→
  diff（key/old/new/evidence）→ obs_inject 注入管线幂等重跑 →
  交卷带 recheck 披露；防翻烧饼三道闸见 recheck.py 模块注释。
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

from .extract import ExtractError, clip_reasoning, extract_from_input
from .extract.adjust import (ADJUST_TABLE, ADJUST_TRIGGER, AdjustResult,
                             adjust_view_from_payload, map_adjustment)
from .extract.parse import parse_describe
from .extract.recheck import (GROUP_LABELS, diff_note, focus_cats,
                              focus_keys, focus_recheck, route_target)
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


def _missing_card(missing: list[str], seen_cats: set[str]) -> HelpCard:
    """缺必填尺寸卡：批量问数字；补拍建议按已见照片类别精准化（C6，
    2026-09-29：只见过背面 → 只提正面）；类别不可知（any=旧会话迁移/
    极端无记录）→ 旧行为（已有照片不劝补拍）。"""
    asks = [AskItem(k, _MEAS_LABELS.get(k, k),
                    "描述、码号换算与模型补漏后仍缺（不编数值）",
                    f"{_MEAS_LABELS.get(k, k)}{_SAMPLE.get(k, 74)}")
            for k in missing]
    want: list[str] = []
    if "any" not in seen_cats:          # any = 类别不可知，不猜
        if "front" not in seen_cats:
            want.append("正面平铺照")
        if "back" not in seen_cats:
            want.append("背面平铺照")
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
    """一轮产物：会话新态 + 卡/交卷/directive 三选一 + 原始结果（CLI 写盘用）。"""

    session: Session
    card: HelpCard | None
    delivery: dict | None
    result: object = None
    # D3 复查握手（2026-09-29）：{group, photo_categories, message}——Web 前端
    # 收到后自动附类别照片 fulfill="recheck" 续发；CLI 打印 + 等补片
    directive: dict | None = None

    def to_dict(self) -> dict:
        return {"session": self.session.to_dict(),
                "card": self.card.to_dict() if self.card else None,
                "delivery": self.delivery,
                "directive": self.directive}


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


def _read_photo_rows(cache: dict) -> list[dict]:
    """vlm_cache.photos 读入（C5 迁移，2026-09-29）：新格式 [{d,c,n}]
    直取；旧格式字符串迁移 {d:s, c:"any", n:""}（会话 JSON 前后向兼容，
    硬约束 4）——any=类别不可知（不猜），求援补照按旧行为。"""
    out: list[dict] = []
    for it in cache.get("photos") or ():
        if isinstance(it, str):
            out.append({"d": it, "c": "any", "n": ""})
        elif isinstance(it, dict) and it.get("d"):
            out.append({"d": str(it["d"]),
                        "c": str(it.get("c") or "any"),
                        "n": str(it.get("n") or "")})
    return out


def _norm_photo_meta(photo_meta: list[dict] | None, n: int) -> list[dict]:
    """photo_meta 规整（C4）：与 photos 按序对齐——短了补 other、长了
    截断；非法条目/未知类别回落 other（前端三槽/CLI 语法保证，这里是
    防线不是路径）。"""
    def one(m) -> dict:
        if not isinstance(m, dict):
            return {"category": "other", "note": ""}
        c = m.get("category")
        c = c if c in ("front", "back", "other") else "other"
        return {"category": c, "note": str(m.get("note") or "")}
    metas = [one(m) for m in (photo_meta or [])][:n]
    while len(metas) < n:
        metas.append({"category": "other", "note": ""})
    return metas


def _ledger_brief(led) -> str | None:
    """账本摘要（B1，2026-09-29）：多轮上下文的结构化常驻——尺寸终值
    一行 + 描述倾向一行 + 已应用调版最近 3 条（带轮次原话摘录）。

    S2 prompt 的 describe 只装本轮叙事后，早轮亲说全靠这段进模型视野；
    空账本返回 None（调用方据此回落全史拼接 = 旧行为）。
    """
    lines: list[str] = []
    if led.measurements:
        lines.append("尺寸：" + "、".join(
            f"{_MEAS_LABELS.get(k, k)}{r.value:g}"
            for k, r in led.measurements.items()))
    extras: list[str] = []
    if led.size_label is not None:
        extras.append(f"尺码{led.size_label.value:g}码")
    if led.shrinkage is not None and led.shrinkage.value:
        extras.append(f"缩水{led.shrinkage.value * 100:g}%")
    if extras:
        lines.append("、".join(extras))
    if led.hints:
        lines.append("描述倾向：" + "、".join(
            f"{k}={r.value}" for k, r in led.hints.items()))
    if led.adjustments:
        recent = sorted(led.adjustments.items(),
                        key=lambda kv: (kv[1].turn, kv[0]))[-3:]
        lines.append("已应用调版：" + "；".join(
            f"第{row.turn}轮「{row.evidence}」→ {k}={row.value}"
            for k, row in recent))
    return "\n".join(lines) if lines else None


# -- 定向复查（D，2026-09-29，设计 §3） ------------------------------------------

def _pending_directive(session: Session) -> dict | None:
    """最近一条未完成的复查 directive 事件 data；无 -> None。

    done 标记写在事件 data 内（会话 JSON 随响应往返，后端无状态）：轮次 B
    或补片轮消费时置 True——已承诺的复查不因中间隔轮失忆，也不重复执行。
    """
    for ev in reversed(session.events):
        if ev.role == "agent" and ev.kind == "directive":
            d = ev.data or {}
            if d.get("group") and not d.get("done"):
                return d
    return None


def _directive_message(group: str, cats, note: str = "") -> str:
    """directive 气泡文案（Web/CLI 同句）：复查什么 + 需要哪类照片。"""
    label = {"front": "正面", "back": "背面", "other": "其他角度"}
    need = "、".join(label.get(c, c) for c in cats) + "照片"
    head = note or f"我来重新细看{GROUP_LABELS.get(group, group)}"
    return f"{head}——需要{need}再看一遍。"


def _recheck_photo_card(group: str, cats) -> HelpCard:
    """复查降级求援卡（§3.4 空照片降级）：按类别要照片——合法求援非反问。"""
    label = {"front": "正面平铺照", "back": "背面平铺照", "other": "其他角度照片"}
    want = [label.get(c, "其他角度照片") for c in cats] or ["正面平铺照"]
    msg = (f"要复查{GROUP_LABELS.get(group, group)}，我需要一张"
           f"{'、'.join(want)}——上传后直接发送即可（我保留着之前的对话记录）。")
    return HelpCard([], want, msg)


def run_turn(session: Session, text: str, photos: tuple | list = (), *,
             photo_meta: list[dict] | None = None,
             fulfill: str | None = None,
             config_path: str | None = None, provider=None,
             thinking: str | None = None, run_probe: bool = True,
             run_score: bool = True, max_refeed: int = 2,
             progress=None) -> TurnOutcome:
    """一轮对话：append 用户事件 → 管线重跑 → 求援卡 / directive / 交卷。

    photos：本轮随请求的照片路径（CLI 跨轮全量累积；前端提交成功即清
    上传池、只发本轮新增，2026-09-24——已识别证据在 session.vlm_cache，
    后续轮零照片也安全），本函数按 vlm_cache 指纹去重，只把未识别的新
    照片送进 S2——「VLM 证据一次识别永久入账本」的落点。

    photo_meta（2026-09-29 C 照片三类）：[{category, note}] 与 photos
    按序对齐（front/back/other，用户上传时手动标注）；类别进 S2 prompt
    【照片清单】段 + 落 vlm_cache（d/c/n 行）+ 求援补照精准化。缺省
    None 全部按 other（旧调用方行为兼容）。

    fulfill（2026-09-29 D3，当前仅 "recheck"）：两段握手轮次 B——不跑
    调版映射（轮次 A 已跑）、不新增 user 事件，类别照片指纹去重绕过
    （复查照片喂聚焦调用不经 S2）。待执行 directive 缺失时按普通轮继续
    （零打扰兜底）。
    """
    turn = session.events[-1].turn + 1 if session.events else 1
    digests = [_digest_file(p) for p in photos]

    # 照片预备（C5 行迁移 + meta 对齐 + 指纹去重）：提到握手分支之前——
    # 复查轮只按类别挑照片，不走 S2 新批通道
    seen_rows = _read_photo_rows(session.vlm_cache)
    cached = {r["d"] for r in seen_rows}
    metas = _norm_photo_meta(photo_meta, len(photos))
    new_rows = [(p, d, m) for p, d, m in zip(photos, digests, metas)
                if d not in cached]
    new_photos = [r[0] for r in new_rows]
    new_metas = [r[2] for r in new_rows]
    prior = None
    if session.vlm_cache.get("entries"):
        prior = observation_from_dict(session.vlm_cache)

    # D3 轮次 B（fulfill="recheck"）：类别照片到位 → 直执行复查；空照片
    # → 按类别求援卡（§3.4 降级）；无待执行 directive → 降级普通轮
    # （fulfill 置 None，后续映射/user 事件照常——前端误发不丢话）
    recheck_ctx = None                  # {group, matching[(path, meta)], note, text}
    if fulfill == "recheck":
        pend = _pending_directive(session)
        if pend is None:
            fulfill = None
        else:
            group = str(pend["group"])
            cats = tuple(pend.get("photo_categories") or focus_cats(group))
            matching = [(p, m) for p, m in zip(photos, metas)
                        if m["category"] in cats]
            if not matching:
                # 空照片降级（§3.4）：按类别求援卡——directive 保持待办，
                # 用户按卡补片后任意一轮 catch-up 续执行（承诺不失忆）
                card = _recheck_photo_card(group, cats)
                session.events.append(Event(turn, "agent", "card",
                                            data=card.to_dict()))
                return TurnOutcome(session, card, None)
            pend["done"] = True
            recheck_ctx = {"group": group, "matching": matching,
                           "note": str(pend.get("note") or ""),
                           # 轮次 A 复查原话（聚焦 prompt 的【本轮用户原话】）
                           "text": str(pend.get("text") or "") or text}

    # 调版映射（2026-09-27，口径 .doc/python工程设计.md §10.9.2）：交卷后
    # 每轮都调（ADJUST_TRIGGER）；在 user 事件 append **之前**跑，结果随
    # 本轮事件 data 落账，replay 同轮即入种子。FakeVLM 单队列同轮出队
    # 顺序：映射 -> S1 补漏 -> S2（测试排序铁律）
    adjust_data = None
    recheck_target = None               # D3：映射判 recheck 时的部位组（缺省兜底）
    if (fulfill is None and ADJUST_TRIGGER != "off" and text.strip()
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
                res = AdjustResult(tuple(keep), res.note, tuple(drop),
                                   res.action, res.target)
            if res.entries or res.note or res.dropped or res.action != "adjust":
                adjust_data = res.to_dict()
            if res.action == "recheck":
                recheck_target = res.target or "兜底"

    # 映射结果随事件 data["adjust"] 落账（replay/history/_build_delivery
    # 三处同键读取；无映射轮 data 空）；复查续轮（fulfill）不新增 user
    # 事件——这组照片在事件流里属轮次 A 的用户动作（§3.4）
    if fulfill is None:
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

    describe_all = "；".join(e.text for e in session.events
                             if e.role == "user" and e.text)
    # B1 拆分（2026-09-29）：S2 prompt 的 describe 只装本轮叙事，多轮
    # 上下文走结构化账本摘要（context_brief）——旧轮叙事不再整段复述、
    # 尺寸/倾向/调版按需重取；首轮（turn==1）或空账本不注摘要 = 与旧口径
    # 逐位一致。回退开关：context_brief 恒 None → describe=全史拼接旧行为
    context_brief = _ledger_brief(led) if turn > 1 else None

    # D3 同轮直执行（§3.3）：映射判 recheck 且本轮类别照片在手 → 直接复查
    # （CLI 照片常驻 / 前端顺手带片）；类别不合或无片 → directive 握手
    # （Web 轮次 B 自动附片续发；CLI 补 :photo 后下一轮照片到位即续执行）
    if recheck_target is not None:
        group = route_target(recheck_target)
        cats = focus_cats(group)
        matching = [(p, m) for p, m in zip(photos, metas)
                    if m["category"] in cats]
        if matching:
            recheck_ctx = {"group": group, "matching": matching,
                           "note": str((adjust_data or {}).get("note") or ""),
                           "text": text}
        else:
            note = str((adjust_data or {}).get("note") or "")
            msg = _directive_message(group, cats, note)
            # 原话随 directive 落事件流：轮次 B 聚焦 prompt 的【本轮用户
            # 原话】段用它（续轮 text 为空）
            session.events.append(Event(
                turn, "agent", "directive",
                data={"group": group, "photo_categories": list(cats),
                      "note": note, "text": text}))
            return TurnOutcome(session, None, None, directive={
                "group": group, "photo_categories": list(cats),
                "message": msg})
    elif fulfill is None and photos:
        # 补片续执行：directive 仍待办且本轮照片类别到位（CLI :photo 补片
        # 后任意一轮 / Web 卡在别处再补传）——已承诺的复查不失忆
        pend = _pending_directive(session)
        if pend is not None:
            group = str(pend["group"])
            cats = tuple(pend.get("photo_categories") or focus_cats(group))
            matching = [(p, m) for p, m in zip(photos, metas)
                        if m["category"] in cats]
            if matching:
                pend["done"] = True
                recheck_ctx = {"group": group, "matching": matching,
                               "note": str(pend.get("note") or ""),
                               "text": str(pend.get("text") or "") or text}

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

    # D3 聚焦复查（§3.3）：一次带判据/基线的定向 VLM 调用 -> diff +
    # obs_inject（B2 缝）——类别照片全喂聚焦调用，不经 S2
    obs_inject = None
    recheck_diff: list[dict] = []
    recheck_note = ""
    if recheck_ctx is not None:
        group = recheck_ctx["group"]
        rc_note = recheck_ctx["note"]
        rc_provider = provider or _mapping_provider(config_path)
        obs_new, recheck_diff, rc_err = focus_recheck(
            group, recheck_ctx["text"],
            [p for p, _m in recheck_ctx["matching"]], prior,
            rc_provider,
            photo_meta=[m for _p, m in recheck_ctx["matching"]])
        # 复查思考段（恒深度模式必有草稿）：与 S2 同款折叠展示透传
        recheck_reasoning = getattr(rc_provider, "last_reasoning", "") or ""
        if obs_new is not None:
            obs_inject = obs_new
            recheck_note = "；".join(x for x in (
                rc_note, diff_note(group, recheck_diff, focus_keys(group)))
                if x)
        else:
            # VLM 缺/失败：零打扰降级——保持原判断照常交卷，diff 空、note 披露
            recheck_note = ("；".join(x for x in (rc_note, rc_err) if x)
                            or "复查未执行，保持原判断")

    try:
        result = extract_from_input(
            describe=(text if context_brief is not None else describe_all),
            s1_history=(describe_all or None),
            context_brief=context_brief,
            photos=([] if recheck_ctx is not None else new_photos),
            photo_meta=(None if recheck_ctx is not None
                        else (new_metas or None)),
            obs_inject=obs_inject,
            provider=provider,
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
        # 已见照片类别（缓存行 ∪ 本轮）：补拍建议精准化（C6）；有观测
        # 但无照片行记录（极端旧会话）→ 类别不可知，按 any 不猜
        seen_cats = ({r["c"] for r in seen_rows}
                     | {m["category"] for m in metas})
        if prior is not None and not seen_cats:
            seen_cats = {"any"}
        card = _missing_card(e.missing, seen_cats)
        session.events.append(Event(turn, "agent", "card", data=card.to_dict()))
        return TurnOutcome(session, card, None)

    # VLM 缓存落账：快照为 merged（旧批次 ∪ 新批次，新覆盖旧同键）；
    # 照片行 = 旧行（含 any 迁移）∪ 本轮新行 {d, c, n}（C5 新格式）。
    # 复查轮（D3）：快照同样入账（obs_inject 已并入 result.observation），
    # 照片行按复查 matching 计——新片聚焦调用看过即入账；**降级轮**
    # （obs_inject None）不动缓存，新片保持未识别、可再喂
    if result.observation is not None and recheck_ctx is None and new_photos:
        snap = observation_to_dict(result.observation)
        by_d = {r["d"]: r for r in seen_rows}
        for _p, d, m in new_rows:
            by_d[d] = {"d": d, "c": m["category"], "n": m["note"]}
        snap["photos"] = sorted(by_d.values(), key=lambda r: r["d"])
        session.vlm_cache = snap
    elif (recheck_ctx is not None and obs_inject is not None
            and result.observation is not None):
        snap = observation_to_dict(result.observation)
        by_d = {r["d"]: r for r in seen_rows}
        pd = dict(zip(photos, digests))
        for p, m in recheck_ctx["matching"]:
            d = pd.get(p) or _digest_file(p)
            by_d[d] = {"d": d, "c": m["category"], "n": m["note"]}
        snap["photos"] = sorted(by_d.values(), key=lambda r: r["d"])
        session.vlm_cache = snap

    if run_probe and result.probe.stage == "L4":
        card = _probe_card(result)
        session.events.append(Event(turn, "agent", "card", data=card.to_dict()))
        return TurnOutcome(session, card, None, result=result)

    delivery = _build_delivery(result, led, turn, adjust_data)
    if recheck_ctx is not None:
        # D 复查披露（§3.5 闸③）：key/old/new/evidence 全量 + 结论一句话
        # + 思考段（恒深度草稿，clip 同 S2；2026-10-08）
        delivery["recheck"] = {"group": recheck_ctx["group"],
                               "diff": recheck_diff,
                               "note": recheck_note,
                               "reasoning": clip_reasoning(recheck_reasoning)}
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
        # 侧缝守卫披露（2026-09-29 A5）：塌零量测 + waist_balance 抬回
        # 轨迹全句（自动抬回 / 调版亲说只量不改）；空表 = 未触发
        "balance_guard": list(result.balance_notes),
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
