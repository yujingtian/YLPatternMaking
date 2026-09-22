"""extract 包门面：照片 + 文字描述 -> 尺寸单 TOML + 逐键核对报告（半自动）。

位置口径（2026-09-03 边界）：ylpattern = 纯引擎，全部大模型相关代码
（本包 + agent/cli.py + agent/app.py）收敛在 agent/；依赖方向只许
agent → ylpattern（params/validate、flows.closure），引擎侧零反向引用。

管线（模型两阶段调用，S1 补漏可免）：
```
parse_describe（S1 纯代码） → [S1 补漏小调用·纯文本] → prejudge_axes
→ build_prompt → S2 编辑确认（唯一主调用） → sanitize → merge
→ enforce_dependencies → derive_all → validate_candidate
→ probe_loop（L0~L4 回喂） → score_features → emit + report
```

依赖约定：
- provider 是唯一触网文件；本模块顶层不 import provider/urllib（无配置
  环境跑测试零影响），provider 在 extract_from_input 内惰性构造；
- 无照片且无 VLM 配置 → 纯描述路径（S2 整段跳过，轴/开关全代码预判）。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .derive import (KeyMeta, MergedView, derive_all, enforce_dependencies,  # noqa: F401 重导出
                     merge)
from .parse import Observation, parse_describe, parse_model_json, sanitize
from .prejudge import prejudge_axes, prior_switches

# 必填 7 键（thigh 可选；缺失即列清单退出，绝不编数值）
REQUIRED_MEAS = ("waist", "hip", "knee", "hem", "front_rise", "back_rise",
                 "outseam")


class ExtractError(RuntimeError):
    """提取不可继续（缺尺寸/配置）。missing 供 CLI 列清单退出码 2。"""

    def __init__(self, message: str, missing: tuple | list = ()):
        super().__init__(message)
        self.missing = list(missing)


def _noop(message: str) -> None:
    """进度回调空实现（HTTP 服务路径静默，CLI 注入 stderr 计时打印）。"""
    return None


@dataclass
class ExtractResult:
    """一条龙产物：终值 + 溯源 + 探针/评分 + 待写盘文本。"""

    measurements: dict
    merged: MergedView
    derived: dict[str, KeyMeta]
    issues: list
    probe: object
    score_items: list
    dropped: list[str]
    dep_notes: list[str]
    reverted: list[str]
    size_text: str
    report_text: str
    model_name: str
    photo_count: int
    # 尺寸逐键来源文案（parse_describe / S1 补漏写）——前端确认屏尺寸行
    # 徽章/依据的数据源（2026-09-03 前端接线补入契约；emit 同源共用）
    measurement_evidence: dict = field(default_factory=dict)
    # 会话层缝（2026-09-21 智能体一期）：S2 观察快照（VLM 证据缓存载体）
    # + 最终生效的描述倾向/码号/缩水（会话账本对账用，含种子合并结果）
    observation: object = None
    hints: dict = field(default_factory=dict)
    size_label: int | None = None
    shrinkage: float | None = None

    def options_meta(self) -> dict[str, KeyMeta]:
        """发射键全集（开关 + 派生），emit/report 共用。"""
        return {**self.merged.switches, **self.derived}

    def options_dict(self) -> dict:
        return {k: m.value for k, m in self.options_meta().items()}

    def to_web_payload(self) -> dict:
        """二期 POST /api/extract 直接 JSON 化（前端预填现有表单）。"""
        keys = {**self.merged.axes, **self.merged.switches,
                **self.merged.enums, **self.derived}
        # 尺寸键也进 keys（source=描述、置信顶格——显式数字非模型判断；
        # S1 补漏在 evidence 里披露"模型补漏"）：确认屏逐行徽章单契约出齐
        meas_meta = {k: KeyMeta(k, v, "描述", 1.0,
                                self.measurement_evidence.get(k, ""))
                     for k, v in self.measurements.items()}
        return {
            "measurements": self.measurements,
            "options": self.options_dict(),
            "keys": {k: {"value": m.value, "source": m.source,
                         "confidence": m.confidence, "evidence": m.evidence}
                     for k, m in {**keys, **meas_meta}.items()},
            "issues": [{"param": i.param, "message": i.message,
                        "level": i.level} for i in self.issues],
            "probe": {"stage": self.probe.stage, "ok": self.probe.ok,
                      "log": list(self.probe.log)},
            "score": [{"feature": s.feature, "value": s.value, "band": s.band,
                       "verdict": s.verdict} for s in self.score_items],
        }


def _s1_fill_missing(describe: str, missing: list[str], provider,
                     thinking: str | None) -> dict[str, float]:
    """S1 补漏小调用：纯文本、只问缺的数字键；模型答 null/超带即弃。"""
    labels = "、".join(missing)
    prompt = [
        "从下面这段服装描述文字中提取这些身体尺寸数值（单位 cm，只抄显式"
        f"数字）：{labels}。",
        "只输出一个 JSON 对象，键为上述尺寸名、值为数字或 null（描述里"
        "没有就给 null，不要估算）。",
        "",
        f"【描述】{describe}",
    ]
    try:
        raw = parse_model_json(provider.complete("\n".join(prompt), (),
                                                 thinking))
    except (ValueError, RuntimeError):
        # 补漏失败不阻断（VLMError 也是 RuntimeError）：走缺键清单退出
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for k in missing:
        v = raw.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        if 10.0 < float(v) < 200.0:   # 合理带内才算数（防口胡）
            out[k] = round(float(v), 1)
    return out


def _provider_or_none(config_path: str | None, need: bool):
    """惰性构造真实 provider；无配置且无照片 → None（纯描述路径）。"""
    try:
        from .provider import OpenAICompatibleVLM, VLMConfig
        return OpenAICompatibleVLM(VLMConfig.load(config_path))
    except Exception:
        if need:
            raise
        return None


def extract_from_input(*, describe: str, photos: tuple | list = (),
                       provider=None, thinking: str | None = None,
                       run_probe: bool = True, run_score: bool = True,
                       max_refeed: int = 2,
                       config_path: str | None = None,
                       progress: Callable[[str], None] | None = None,
                       seed_measurements: dict[str, tuple] | None = None,
                       seed_hints: dict[str, str] | None = None,
                       seed_size_label: int | None = None,
                       seed_shrinkage: float | None = None,
                       prior_observation=None
                       ) -> ExtractResult:
    """一条龙：描述+照片 -> ExtractResult（size_text/report_text 待写盘）。

    progress：阶段性进度回调（一行一句）；缺省静默（HTTP 服务同步等待
    无处展示，CLI 注入 stderr 计时打印）。模型调用是最长环节，发起前后
    各报一条。

    会话层注入缝（2026-09-21 智能体一期，converse.run_turn 专用；单发
    调用全部缺省，行为与历史逐位一致）：
    - seed_*：会话账本重放值（多轮累积、后答覆盖先答）。种子优先于本轮
      parse 的单文本结果——describe 传「全轮拼接」时种子兜住轮次语义；
    - prior_observation：历史照片批的 S2 观察快照。本轮 photos 只放
      **未缓存新照片**（调用方按指纹去重）；有新照片时新证据覆盖旧批次
      同键（后补照片更相关），无新照片时直接复用缓存——零模型调用。
    """
    p = progress or _noop
    parsed = parse_describe(describe)
    measurements: dict[str, float] = dict(parsed.measurements)
    evidence: dict[str, str] = dict(parsed.evidence)
    hints: dict[str, str] = dict(parsed.hints)
    size_label: int | None = parsed.size_label
    shrinkage: float | None = parsed.shrinkage
    if seed_measurements:
        for k, (v, ev) in seed_measurements.items():
            measurements[k] = v
            evidence[k] = ev
    if seed_hints:
        hints.update(seed_hints)
    if seed_size_label is not None:
        size_label = seed_size_label
    if seed_shrinkage is not None:
        shrinkage = seed_shrinkage
    photo_count = len(photos)

    model_name = "（纯描述路径，未调用模型）"
    if provider is None and (photo_count or describe.strip()):
        provider = _provider_or_none(config_path, need=photo_count > 0)
    if provider is not None:
        cfg = getattr(provider, "config", None)
        model_name = getattr(cfg, "model", None) or type(provider).__name__

    p(f"描述解析完成：{len(measurements)} 项尺寸，照片 {photo_count} 张")

    # S1 补漏（有 provider 才发；仍缺 → 清单退出，不编数值）
    missing = [k for k in REQUIRED_MEAS if k not in measurements]
    if missing and provider is not None and describe.strip():
        p(f"S1 补漏：向模型询问缺失尺寸 {'、'.join(missing)}（纯文本调用）…")
        filled = _s1_fill_missing(describe, missing, provider, thinking)
        for k, v in filled.items():
            measurements[k] = v
            evidence[k] = "模型补漏：从描述文字读出的显式数字"
        missing = [k for k in REQUIRED_MEAS if k not in measurements]
    if missing:
        raise ExtractError(
            "描述与模型补漏后仍缺必填尺寸（不编数值）：" + "、".join(missing),
            missing)

    prejudged = prejudge_axes(measurements, hints, size_label)
    priors = prior_switches()

    obs = Observation()
    dropped: list[str] = []
    if photo_count and provider is not None:
        from .schema import build_prompt
        prompt = build_prompt(describe, measurements, prejudged, priors,
                              photo_count)
        p(f"S2 视觉确认：调用 {model_name} 读 {photo_count} 张照片"
          "（最耗时环节，thinking 开启时可达分钟级）…")
        t_vlm = time.monotonic()
        obs_new = sanitize(parse_model_json(
            provider.complete(prompt, list(photos), thinking)))
        p(f"S2 视觉确认完成（耗时 {time.monotonic() - t_vlm:.1f}s）")
        if prior_observation is not None:
            obs = Observation(
                entries={**prior_observation.entries, **obs_new.entries},
                dropped=[*prior_observation.dropped, *obs_new.dropped])
        else:
            obs = obs_new
        dropped = list(obs.dropped)
    elif prior_observation is not None:
        obs = prior_observation        # 缓存命中：本轮无新照片，零模型调用
        dropped = list(obs.dropped)

    merged = merge(obs, measurements, prejudged, priors, hints,
                   size_label)
    dep_notes = enforce_dependencies(merged)
    derived = derive_all(measurements, merged, size_label,
                         shrinkage)

    options = {**{k: m.value for k, m in merged.switches.items()},
               **{k: m.value for k, m in derived.items()}}
    from .validate import validate_candidate
    ok_static, issues = validate_candidate(measurements, options)

    p(f"参数派生完成：发射 {len(derived)} 键，静态校验 "
      f"{'通过' if ok_static else '有问题'}")

    from .probe import ProbeOutcome, probe_loop
    if run_probe:
        probe = probe_loop(measurements, options, max_refeed, progress=p)
    else:
        # ok=False：--draft 拒绝直出（探针未运行 = 未验证，不许跳过人工核对）
        probe = ProbeOutcome(False, "跳过", "--no-geometry：探针未运行")

    reverted = list(getattr(probe, "reverted", []))
    for k in reverted:   # 回退/降级键不进产物（引擎默认接管），报告披露
        merged.switches.pop(k, None)
        derived.pop(k, None)
    options_final = {**{k: m.value for k, m in merged.switches.items()},
                     **{k: m.value for k, m in derived.items()}}

    score_items: list = []
    if run_score and getattr(probe, "ctx", None) is not None:
        from .score import score_features
        p("打版后合理性评分…")
        score_items = score_features(probe.ctx, measurements, options_final)

    from .emit import build_size_text
    summary = describe.strip().replace("\n", " ")
    header = [
        "照片参数提取（agent extract）——人工核对后喂 draft",
        f"描述摘要：{summary[:60]}{'…' if len(summary) > 60 else ''}",
        f"照片 {photo_count} 张 · 视觉确认 {model_name}",
        f"探针 {probe.stage}" + ("" if probe.ok else " 未通过——仅供人工核查"),
    ]
    size_text = build_size_text(measurements, evidence,
                                {**merged.switches, **derived}, header)

    from .report import render_extract_report
    report_text = render_extract_report(
        describe=describe, photo_count=photo_count, model=model_name,
        measurements=measurements, evidence=evidence, merged=merged,
        derived=derived, issues=issues, probe=probe, score_items=score_items,
        dropped=dropped, dep_notes=dep_notes, reverted=reverted)
    p("提取完成")
    return ExtractResult(measurements=measurements, merged=merged,
                         derived=derived, issues=issues, probe=probe,
                         score_items=score_items, dropped=dropped,
                         dep_notes=dep_notes, reverted=reverted,
                         size_text=size_text, report_text=report_text,
                         model_name=model_name, photo_count=photo_count,
                         measurement_evidence=evidence,
                         observation=obs, hints=hints,
                         size_label=size_label, shrinkage=shrinkage)
