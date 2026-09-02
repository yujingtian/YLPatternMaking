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

    def options_meta(self) -> dict[str, KeyMeta]:
        """发射键全集（开关 + 派生），emit/report 共用。"""
        return {**self.merged.switches, **self.derived}

    def options_dict(self) -> dict:
        return {k: m.value for k, m in self.options_meta().items()}

    def to_web_payload(self) -> dict:
        """二期 POST /api/extract 直接 JSON 化（前端预填现有表单）。"""
        keys = {**self.merged.axes, **self.merged.switches,
                **self.merged.enums, **self.derived}
        return {
            "measurements": self.measurements,
            "options": self.options_dict(),
            "keys": {k: {"value": m.value, "source": m.source,
                         "confidence": m.confidence, "evidence": m.evidence}
                     for k, m in keys.items()},
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
                       config_path: str | None = None) -> ExtractResult:
    """一条龙：描述+照片 -> ExtractResult（size_text/report_text 待写盘）。"""
    parsed = parse_describe(describe)
    measurements: dict[str, float] = dict(parsed.measurements)
    evidence: dict[str, str] = dict(parsed.evidence)
    photo_count = len(photos)

    model_name = "（纯描述路径，未调用模型）"
    if provider is None and (photo_count or describe.strip()):
        provider = _provider_or_none(config_path, need=photo_count > 0)
    if provider is not None:
        cfg = getattr(provider, "config", None)
        model_name = getattr(cfg, "model", None) or type(provider).__name__

    # S1 补漏（有 provider 才发；仍缺 → 清单退出，不编数值）
    missing = [k for k in REQUIRED_MEAS if k not in measurements]
    if missing and provider is not None and describe.strip():
        filled = _s1_fill_missing(describe, missing, provider, thinking)
        for k, v in filled.items():
            measurements[k] = v
            evidence[k] = "模型补漏：从描述文字读出的显式数字"
        missing = [k for k in REQUIRED_MEAS if k not in measurements]
    if missing:
        raise ExtractError(
            "描述与模型补漏后仍缺必填尺寸（不编数值）：" + "、".join(missing),
            missing)

    prejudged = prejudge_axes(measurements, parsed.hints, parsed.size_label)
    priors = prior_switches()

    obs = Observation()
    dropped: list[str] = []
    if photo_count and provider is not None:
        from .schema import build_prompt
        prompt = build_prompt(describe, measurements, prejudged, priors,
                              photo_count)
        obs = sanitize(parse_model_json(
            provider.complete(prompt, list(photos), thinking)))
        dropped = list(obs.dropped)

    merged = merge(obs, measurements, prejudged, priors, parsed.hints,
                   parsed.size_label)
    dep_notes = enforce_dependencies(merged)
    derived = derive_all(measurements, merged, parsed.size_label,
                         parsed.shrinkage)

    options = {**{k: m.value for k, m in merged.switches.items()},
               **{k: m.value for k, m in derived.items()}}
    from .validate import validate_candidate
    ok_static, issues = validate_candidate(measurements, options)

    from .probe import ProbeOutcome, probe_loop
    if run_probe:
        probe = probe_loop(measurements, options, max_refeed)
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
    return ExtractResult(measurements=measurements, merged=merged,
                         derived=derived, issues=issues, probe=probe,
                         score_items=score_items, dropped=dropped,
                         dep_notes=dep_notes, reverted=reverted,
                         size_text=size_text, report_text=report_text,
                         model_name=model_name, photo_count=photo_count)
