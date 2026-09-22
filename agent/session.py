"""会话数据模型：append-only 事件流 + 账本投影 + JSON（eval 脚本同格式）。

口径（2026-09-21 智能体一期，.doc/python工程设计.md §10.9）：
- 事件流永不改写；账本 = 对 user 事件逐条 parse_describe 的重放投影，
  **后答覆盖先答**（「改口」天然支持，旧值留在事件流里可追溯）；
  回滚 = 截断到 turn N 后重放；
- 照片本体不进会话（前端 IndexedDB / CLI 持路径），事件只记指纹
  （sha256 前 12 位）；VLM 识别证据以 Observation 快照整份缓存
  （session.vlm_cache），无新照片的轮次零模型调用、重传是显式动作；
- 会话持前端、后端无状态：JSON 每轮随请求往返（webapp 薄壳不落盘
  口径延续）；
- eval 对话脚本 = 本格式子集：{"turns": [{"text": "…", "photos": […]}]}
  固定轮次输入 → 断言末态（tests/test_agent_chat.py 金标）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from .extract.parse import Observation, ObservationEntry, parse_describe


def photo_digest(data: bytes) -> str:
    """照片指纹（事件/缓存的引用键；本体留在会话外）。"""
    return hashlib.sha256(data).hexdigest()[:12]


# -- Observation 序列化（vlm_cache 载体；值域 bool/str，JSON 直存） -------------

def observation_to_dict(obs: Observation) -> dict:
    return {"entries": {k: {"value": e.value, "confidence": e.confidence,
                            "evidence": e.evidence}
                        for k, e in obs.entries.items()},
            "dropped": list(obs.dropped)}


def observation_from_dict(d: dict) -> Observation:
    return Observation(
        entries={k: ObservationEntry(e["value"], e["confidence"], e["evidence"])
                 for k, e in d.get("entries", {}).items()},
        dropped=list(d.get("dropped", [])))


# -- 事件与会话 ----------------------------------------------------------------

@dataclass
class Event:
    """一轮对话记录：用户输入 / 智能体求援卡 / 交卷。append-only。"""

    turn: int
    role: str            # "user" | "agent"
    kind: str            # user: "input"；agent: "card" | "deliver"
    text: str = ""
    photos: list[str] = field(default_factory=list)   # 照片指纹引用
    data: dict = field(default_factory=dict)          # 卡片/交卷快照（瘦身版）


@dataclass
class Session:
    """会话状态：事件流 + VLM 证据缓存（唯一可变派生态）。"""

    events: list[Event] = field(default_factory=list)
    # {"photos": [指纹…], "entries": {键: {value/confidence/evidence}},
    #  "dropped": […]}——photos = 已识别批次指纹全集，去重判定依据
    vlm_cache: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"events": [{"turn": e.turn, "role": e.role, "kind": e.kind,
                            "text": e.text, "photos": list(e.photos),
                            "data": e.data} for e in self.events],
                "vlm_cache": self.vlm_cache}

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        return cls(
            events=[Event(e["turn"], e["role"], e["kind"],
                         text=e.get("text", ""),
                         photos=list(e.get("photos", [])),
                         data=dict(e.get("data", {})))
                    for e in d.get("events", [])],
            vlm_cache=dict(d.get("vlm_cache", {})))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "Session":
        return cls.from_dict(json.loads(text))


# -- 账本投影（用户亲说键；款式终值在交卷 payload keys 里，不在此重复） --------

@dataclass
class LedgerRow:
    """账本行：值 + 落定轮次 + 溯源摘录。"""

    value: object
    turn: int
    evidence: str


@dataclass
class Ledger:
    """replay 投影：尺寸/描述倾向/码号/缩水的跨轮累积（后答覆盖先答）。"""

    measurements: dict[str, LedgerRow] = field(default_factory=dict)
    hints: dict[str, LedgerRow] = field(default_factory=dict)
    size_label: LedgerRow | None = None
    shrinkage: LedgerRow | None = None


def replay(session: Session) -> Ledger:
    """事件流 → 账本：逐轮 parse_describe，同键后轮覆盖前轮。"""
    led = Ledger()
    for ev in session.events:
        if ev.role != "user" or not ev.text:
            continue
        parsed = parse_describe(ev.text)
        for k, v in parsed.measurements.items():
            led.measurements[k] = LedgerRow(v, ev.turn,
                                            parsed.evidence.get(k, ""))
        for k, v in parsed.hints.items():
            led.hints[k] = LedgerRow(v, ev.turn, "描述词")
        if parsed.size_label is not None:
            led.size_label = LedgerRow(parsed.size_label, ev.turn, "尺码标签")
        if parsed.shrinkage is not None:
            led.shrinkage = LedgerRow(parsed.shrinkage, ev.turn, "缩水率摘录")
    return led


def load_script(source: dict | list) -> Session:
    """eval 对话脚本 → Session（固定轮次用户输入；断言在测试侧写）。

    格式：{"turns": [{"text": "…", "photos": ["…"]}]} 或等价 list。
    与真实会话 JSON 同构——export 一段真会话 events 即回归用例。
    """
    turns = source.get("turns") if isinstance(source, dict) else source
    events = [Event(i, "user", "input", text=t.get("text", ""),
                    photos=list(t.get("photos", [])))
              for i, t in enumerate(turns or [], 1)]
    return Session(events=events)
