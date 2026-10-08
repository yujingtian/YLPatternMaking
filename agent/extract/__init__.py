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

from .derive import (DESC, KeyMeta, MergedView, derive_all,  # noqa: F401 重导出
                     enforce_dependencies, merge)
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


def clip_reasoning(text: str, limit: int = 6000) -> str:
    """思考段裁剪（响应瘦身，converse 复用）：超限保头 4000 + 中略标记
    + 尾 1500——草稿动辄上万字，整段回传撑爆响应；头尾足够看出它看了
    什么、结论怎么来的。"""
    t = str(text or "")
    if len(t) <= limit:
        return t
    return t[:4000] + "\n……（中略）……\n" + t[-1500:]


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
    # 侧缝守卫披露（2026-09-29 A5）：塌零量测 + 回喂轨迹（delivery review +
    # 报告消费；空表 = 未触发）
    balance_notes: list[str] = field(default_factory=list)
    # 腰头放大辅助图披露（2026-09-30 特征尺度修复）：附了几张裁剪辅助图
    # （空表 = 未附——无照片/Pillow 缺失/裁剪失败降级）
    crop_notes: list[str] = field(default_factory=list)
    # S2 思考段原文（2026-10-08）：深度模式推理草稿（provider.last_reasoning
    # 拼接），to_web_payload 经 clip_reasoning 裁剪随响应透传——前端折叠
    # 展示「大模型思考过程」；快速模式/无 S2 轮为空串
    s2_reasoning: str = ""

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
            "reasoning": clip_reasoning(self.s2_reasoning),
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
                                                 thinking, purpose="s1"))
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
                       seed_overrides: dict[str, tuple] | None = None,
                       adjust_revert: dict | None = None,
                       seed_size_label: int | None = None,
                       seed_shrinkage: float | None = None,
                       prior_observation=None,
                       s1_history: str | None = None,
                       context_brief: str | None = None,
                       obs_inject=None,
                       photo_meta: list[dict] | None = None,
                       waistband_crops: bool = True
                       ) -> ExtractResult:
    """一条龙：描述+照片 -> ExtractResult（size_text/report_text 待写盘）。

    progress：阶段性进度回调（一行一句）；缺省静默（HTTP 服务同步等待
    无处展示，CLI 注入 stderr 计时打印）。模型调用是最长环节，发起前后
    各报一条。

    waistband_crops：特征尺度辅助裁块总开关（2026-09-30，参数名沿用
    首期）——True 时 S2 自动裁腰头区 + 后贴袋区放大辅助图附进同一次
    VLM 调用（crops.py；失败静默降级）。False 全关，images 逐位旧行为。

    会话层注入缝（2026-09-21 智能体一期，converse.run_turn 专用；单发
    调用全部缺省，行为与历史逐位一致）：
    - seed_*：会话账本重放值（多轮累积、后答覆盖先答）。种子优先于本轮
      parse 的单文本结果——describe 传「全轮拼接」时种子兜住轮次语义；
    - seed_overrides（2026-09-27 调版映射覆盖通道，converse.run_turn 专用）：
      账本调版绝对值（键 -> (值, evidence)），derive_all 之后覆写/补种。
      键 ∈ derived -> 覆写；键 ∈ merged.switches -> 覆写并幂等重跑
      enforce_dependencies（外围开关如 front_pouch 不走 merge 的 hint
      循环）；两处都无 = 该款式未发射的键 -> gate 检查（对当前开关 +
      同批种子叠加视图）通过才补种新键，否则休眠（部件重开后按绝对值
      再现）。布尔值先种（gate 要看见同批打开的开关）。单发调用缺省
      None，行为与历史逐位一致；
    - adjust_revert（2026-09-27 调版回退，converse.run_turn 专用）：
      {映射键: 上一版值}——探针 L0 失败时先撤回重试（L0.5，版面保持
      原样不截肢）；成功后 adjust_kept 值写回产物。单发调用缺省 None
      零影响；
    - 侧缝守卫（2026-09-29 A5，probe L0 直过后）：前侧收量塌零（fi<0.5
      且 H−W≥10）时 waist_balance +=0.25 步进整版重跑抬回（细节
      balance.py）；waist_balance ∈ seed_overrides = 调版账本亲说，只量
      只披露不改。产物 balance_notes 供 delivery review + 报告披露；
    - prior_observation：历史照片批的 S2 观察快照。本轮 photos 只放
      **未缓存新照片**（调用方按指纹去重）；有新照片时新证据覆盖旧批次
      同键（后补照片更相关），无新照片时直接复用缓存——零模型调用。
    - 多轮拆分（2026-09-29 B1/B2，converse.run_turn 专用）：describe 只传
      本轮叙事，多轮上下文走结构化账本摘要 context_brief（build_prompt 注
      【已确认状态】段——尺寸终值/描述倾向/已应用调版，叙事与像素按需
      重取）；S1 补漏保持全史输入（s1_history 传全轮拼接，缺省回落
      describe）。回退开关：context_brief=None 即 describe=全轮拼接的旧行为
      （单发/首轮逐位一致）；
    - obs_inject（D 定向复查缝，2026-09-29）：调用方已跑完聚焦 VLM 调用
      拿到的观察——常规 S2 整版读图跳过，与 prior_observation 按现有语义
      merge（新证据覆盖旧同键）。单发调用缺省 None 零影响；
    - photo_meta（2026-09-29 C 照片三类）：[{category, note}] 与 photos
      按序对齐（converse.run_turn 装配；超 photo_count 截断），进 build_prompt
      【照片清单】段。单发调用缺省 None——prompt 逐位不变（硬约束 5）。
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
    # B1 拆分（2026-09-29）：S2 只看本轮叙事，但 S1 补漏保持**全史**输入
    # ——早轮报过的数字仍能从历史里捞（缺省回落 describe = 单发旧行为）
    s1_src = s1_history or describe
    if missing and provider is not None and s1_src.strip():
        p(f"S1 补漏：向模型询问缺失尺寸 {'、'.join(missing)}（纯文本调用）…")
        filled = _s1_fill_missing(s1_src, missing, provider, thinking)
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
    # 腰头放大辅助图披露（S2 分支填写；复查/缓存路径恒空）
    crop_notes: list[str] = []
    # S2 思考段（S2 分支填写；复查/缓存/无照片路径恒空）
    s2_reasoning = ""
    if obs_inject is not None:
        # D 定向复查缝（2026-09-29）：调用方已跑完聚焦 VLM 调用拿到观察，
        # 常规 S2 整版读图跳过（不重复读一遍）；与 prior 按现有语义 merge
        if prior_observation is not None:
            obs = Observation(
                entries={**prior_observation.entries, **obs_inject.entries},
                dropped=[*prior_observation.dropped, *obs_inject.dropped])
        else:
            obs = obs_inject
        dropped = list(obs.dropped)
    elif photo_count and provider is not None:
        from .schema import build_prompt
        # 腰头特写裁剪支路（2026-09-30 特征尺度修复）：整照里腰头 ~200px
        # 经端点降采样低于可分辨阈值（三连实验见决策日志），自动裁上带区
        # 放大作辅助图附进同一次调用；只喂模型，不进指纹/探针/几何。
        # Pillow 缺失/解码失败/任何异常一律静默降级为零辅助图。
        crop_paths: list = []
        crop_metas: list[dict] = []
        crop_notes: list[str] = []
        tmp_crop = None
        if waistband_crops:
            import tempfile
            tmp_crop = tempfile.TemporaryDirectory(prefix="yl_wb_crops_")
            try:
                from .crops import make_waistband_crops
                crop_paths, crop_metas, crop_notes = make_waistband_crops(
                    photos, photo_meta, tmp_crop.name)
            except Exception:              # 辅助图失败不拦主提取
                crop_paths, crop_metas, crop_notes = [], [], []
            try:                           # 后贴袋区照方抓药（2026-09-30）
                from .crops import make_back_pocket_crops
                bp_paths, bp_metas, bp_notes = make_back_pocket_crops(
                    photos, photo_meta, tmp_crop.name)
                crop_paths += bp_paths
                crop_metas += bp_metas
                crop_notes += bp_notes
            except Exception:
                pass
            try:                           # 前袋口区第三贴（2026-10-02）
                from .crops import make_front_pocket_crops
                fp_paths, fp_metas, fp_notes = make_front_pocket_crops(
                    photos, photo_meta, tmp_crop.name)
                crop_paths += fp_paths
                crop_metas += fp_metas
                crop_notes += fp_notes
            except Exception:
                pass
            if crop_paths:
                p(f"放大辅助图 {len(crop_paths)} 张已附（自动裁剪）")
        if crop_paths:
            # meta 与 photos 按序对齐（build_prompt 照片清单按下标渲染）：
            # 原图缺 meta 的槽位补 None（渲染回退「其他：无说明」），尾部接辅助图
            base = list(photo_meta or [])[:len(photos)]
            base += [None] * (len(photos) - len(base))
            s2_meta = base + crop_metas
            s2_count = len(photos) + len(crop_paths)
        else:
            s2_meta = photo_meta           # 无辅助图：prompt 逐位旧行为
            s2_count = photo_count
        prompt = build_prompt(describe, measurements, prejudged, priors,
                              s2_count, context_brief=context_brief,
                              prior_obs=prior_observation,
                              photo_meta=s2_meta)
        p(f"S2 视觉确认：调用 {model_name} 读 {photo_count} 张照片"
          "（最耗时环节，thinking 开启时可达分钟级）…")
        t_vlm = time.monotonic()
        try:
            raw = parse_model_json(provider.complete(
                prompt, list(photos) + crop_paths, thinking, purpose="s2"))
            # 思考段捕获（2026-10-08）：深度模式草稿随响应透传前端折叠展示；
            # FakeVLM 等替身无 last_reasoning 属性 -> 缺省空串
            s2_reasoning = getattr(provider, "last_reasoning", "") or ""
        finally:
            if tmp_crop is not None:
                tmp_crop.cleanup()
        obs_new = sanitize(raw)
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

    # 调版覆盖通道注入（口径见 docstring seed_overrides 条）
    if seed_overrides:
        from .adjust import ADJUST_TABLE, gate_pass
        from .params_meta import default_view
        touched_switch = False
        overlay = dict(default_view())
        overlay.update({k: m.value for k, m in merged.switches.items()})
        overlay.update({k: m.value for k, m in derived.items()})
        # 布尔值先种：后续键的 gate 检查要看见同一批种子打开的开关
        for k, (v, ev) in sorted(
                seed_overrides.items(),
                key=lambda kv: not isinstance(kv[1][0], bool)):
            meta = KeyMeta(k, v, DESC, 0.9, ev)
            overlay[k] = v
            if k in derived:              # 数值/枚举键（derive_all 已发射）
                derived[k] = meta
            elif k in merged.switches:    # 开关键（含 prior 外围开关）
                merged.switches[k] = meta
                touched_switch = True
            else:                         # 未发射键：gate 在才补种，否则休眠
                spec = ADJUST_TABLE.get(k)
                if spec is None or gate_pass(spec.gate, overlay):
                    derived[k] = meta
        if touched_switch:
            dep_notes += enforce_dependencies(merged)

    options = {**{k: m.value for k, m in merged.switches.items()},
               **{k: m.value for k, m in derived.items()}}
    from .validate import validate_candidate
    ok_static, issues = validate_candidate(measurements, options)

    p(f"参数派生完成：发射 {len(derived)} 键，静态校验 "
      f"{'通过' if ok_static else '有问题'}")

    from .probe import ProbeOutcome, probe_loop
    if run_probe:
        probe = probe_loop(measurements, options, max_refeed, progress=p,
                           adjust_revert=adjust_revert)
    else:
        # ok=False：--draft 拒绝直出（探针未运行 = 未验证，不许跳过人工核对）
        probe = ProbeOutcome(False, "跳过", "--no-geometry：探针未运行")

    # 侧缝守卫（2026-09-29 A5）：挂 probe **L0 直接过**之后（L0.5/L1+ 已有
    # 回退语义，不叠加）；前侧收量塌零（fi<0.5 且 H−W≥10）时 balance +=0.25
    # 步进整版重跑抬回（守卫细节 balance.py）；waist_balance ∈ seed_overrides
    # = 调版账本亲说，只量只披露不改。披露进 delivery review + 报告
    balance_notes: list[str] = []
    if run_probe and probe.ok and probe.stage == "L0" and \
            getattr(probe, "ctx", None) is not None:
        from .balance import front_intake_cm, is_collapsed, rebalance
        fi = front_intake_cm(probe.ctx)
        if is_collapsed(measurements, fi):
            if seed_overrides and "waist_balance" in seed_overrides:
                balance_notes.append(
                    f"侧缝守卫：前侧收量 {fi:.2f} 塌零——waist_balance 已由"
                    "调版设定，只披露不改（用户亲说优先）")
            else:
                options, guard_notes, probe.ctx = rebalance(
                    measurements, options, probe.ctx)
                balance_notes += guard_notes
                if "waist_balance" in derived:
                    _m = derived["waist_balance"]
                    derived["waist_balance"] = KeyMeta(
                        _m.key, options["waist_balance"], _m.source,
                        _m.confidence, _m.evidence + "；" + guard_notes[-1])

    reverted = list(getattr(probe, "reverted", []))
    for k in reverted:   # 回退/降级键不进产物（引擎默认接管），报告披露
        merged.switches.pop(k, None)
        derived.pop(k, None)
    # L0.5 调版回退（2026-09-27）：键保留、值写回上一版——不弹键（弹了
    # 落引擎默认，会丢掉更早轮次已交卷的调整；与 L1+ 的回默认是两回事）
    for k, v in (getattr(probe, "adjust_kept", None) or {}).items():
        meta = KeyMeta(k, v, DESC, 0.9, "调版回退：保持上一版值")
        if k in derived:
            derived[k] = meta
        elif k in merged.switches:
            merged.switches[k] = meta
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
        dropped=dropped, dep_notes=dep_notes, reverted=reverted,
        balance_notes=balance_notes, crop_notes=crop_notes)
    p("提取完成")
    return ExtractResult(measurements=measurements, merged=merged,
                         derived=derived, issues=issues, probe=probe,
                         score_items=score_items, dropped=dropped,
                         dep_notes=dep_notes, reverted=reverted,
                         size_text=size_text, report_text=report_text,
                         model_name=model_name, photo_count=photo_count,
                         measurement_evidence=evidence,
                         observation=obs, hints=hints,
                         size_label=size_label, shrinkage=shrinkage,
                         balance_notes=balance_notes,
                         crop_notes=crop_notes,
                         s2_reasoning=s2_reasoning)
