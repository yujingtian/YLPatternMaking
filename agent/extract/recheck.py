"""定向复查执行器（2026-09-29 D，.doc/智能体闭环一期设计.md §3）：

「带着上次答案的质证」，不是重掷骰子——用户说「后贴袋你再仔细看看」时，
先看上次怎么判的（vlm_cache 基线），再带**该部位组**的判据、**该类别**
的照片重新问一次，只许改这几个键、推翻必须写视觉证据。

- 部位组路由表（§3.2）：组名 -> focus 键（MODEL_KEYS 子集）+ 照片类别
  （front/back）；target 词表与 adjust 映射 prompt 规则 0 同源（别名把
  surface 分组名归一到复查组名）。
- 防翻烧饼三道闸（§3.5）：①基线注入（prompt 预填上次值，看不清保持）
  ②conf 门槛（降低 <0.7 的推翻在 sanitize 后仍带 conf，交卷 diff 披露
  让用户看见证据）③diff 披露（key/old/new/evidence 全量进 delivery）。

分工红线不变：LLM 只在键面/档位上判断，值域白名单由 sanitize 收口；
本模块永不抛（调用失败 -> (None, [], 原因)，converse 零打扰降级）。
"""

from __future__ import annotations

import json

from .parse import Observation, parse_model_json, sanitize
from .schema import ENUM_DEFAULTS, MODEL_KEYS, _CRITERIA

# -- 部位组路由（§3.2 表；keys ⊆ MODEL_KEYS） -----------------------------------

ROUTING: dict[str, dict] = {
    "前口袋": {
        "keys": ("front_pocket", "front_pocket_facing", "front_patch",
                 "front_pocket_mouth_mode", "front_pocket_mouth_depth",
                 "front_pocket_facing_mode", "watch_pocket",
                 "watch_pocket_mode"),
        "cats": ("front",),
    },
    "后贴袋": {
        "keys": ("back_patch", "back_patch_shape"),
        "cats": ("back",),
    },
    "腰头": {
        "keys": ("waistband_type", "belt_loop"),
        "cats": ("front", "back"),
    },
    "育克后片": {
        "keys": ("back_yoke", "back_dart"),
        "cats": ("back",),
    },
    "门襟": {
        "keys": ("fly", "fly_separate"),
        "cats": ("front",),
    },
    "版型腰位": {
        "keys": ("fit", "fit_level", "waist_position"),
        "cats": ("front", "back"),
    },
}

GROUP_LABELS = {**{g: g for g in ROUTING}, "兜底": "整版"}

# adjust surface 部位分组名别名（params_meta GROUP_ORDER 里的叫法 -> 复查组）
_ALIASES = {
    "袋口": "前口袋", "袋贴": "前口袋", "小表袋": "前口袋",
    "前贴袋": "前口袋", "后育克": "育克后片", "省道": "育克后片",
    "全局": "版型腰位", "脚口": "版型腰位", "小腿": "版型腰位",
}


def route_target(target: str) -> str:
    """模型 target 串 -> 规范组名；空/未知/别整词 -> 「兜底」（全键）。

    只做归一不猜部位：目标含糊时宁可全量复查（focus=全键 + 全类别照片），
    不替用户缩小范围。
    """
    t = (target or "").strip()
    if t in ROUTING:
        return t
    if t in _ALIASES:
        return _ALIASES[t]
    for name in ROUTING:                       # 「后贴袋 再看看」等含组名串
        if name in t:
            return name
    return "兜底"


def focus_keys(group: str) -> tuple[str, ...]:
    """组 -> focus 键；兜底 = 模型面全键（§3.2 兜底行）。"""
    if group in ROUTING:
        return ROUTING[group]["keys"]
    return tuple(MODEL_KEYS)


def focus_cats(group: str) -> tuple[str, ...]:
    """组 -> 可用照片类别；兜底 = 三类全收。"""
    if group in ROUTING:
        return ROUTING[group]["cats"]
    return ("front", "back", "other")


# -- 聚焦 prompt -----------------------------------------------------------------

def _fmt(v) -> str:
    if v is None:
        return "（未判断）"
    if isinstance(v, bool):
        return "开" if v else "关"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _prefill(keys: tuple[str, ...], prior_entries: dict | None) -> dict:
    """复查模板预填：基线优先，缺键回落枚举默认/开关惯例先验（conf 打折）。

    与 build_template 同风格但只覆盖 focus 键——值是「上次的答案」，模型
    要么维持要么带着证据推翻。
    """
    prior_entries = prior_entries or {}
    from .prejudge import prior_switches          # 局部 import：prejudge 不依赖本模块
    switches = prior_switches()
    out: dict[str, dict] = {}
    for k in keys:
        e = prior_entries.get(k)
        if e is not None:
            out[k] = {"value": e.value,
                      "confidence": round(float(e.confidence), 2),
                      "evidence": f"基线（上次判断）：{e.evidence}"}
        elif k in ENUM_DEFAULTS:
            out[k] = {"value": ENUM_DEFAULTS[k], "confidence": 0.4,
                      "evidence": "引擎默认（上次未判断）"}
        elif k in switches:
            out[k] = {"value": switches[k], "confidence": 0.4,
                      "evidence": "惯例先验（上次未判断）"}
        else:                                    # 轴键无基线：让模型直接判
            out[k] = {"value": None, "confidence": 0.3,
                      "evidence": "无基线，按照片直接判断"}
    return out


def build_focus_prompt(group: str, keys: tuple[str, ...],
                       prior_entries: dict | None, text: str) -> str:
    """复查 prompt：组名 + 仅该组判据段落 + 基线 + 本轮原话 + 预填模板。"""
    label = GROUP_LABELS.get(group, group)
    criteria_lines = [line for k in keys if k in _CRITERIA
                      for line in _CRITERIA[k]]
    criteria = "\n".join(f"- {ln}" for ln in criteria_lines) or "（本组无专门判据，按照片直判）"
    baseline = prior_entries or {}
    base_lines = [f"- {k}: {_fmt(baseline[k].value)}（{baseline[k].evidence}）"
                  for k in keys if k in baseline]
    base = "\n".join(base_lines) or "（上次未见本组判断——全部按照片直判）"
    template = _prefill(keys, baseline)
    tpl = json.dumps(template, ensure_ascii=False, indent=1)
    return (
        f"你是资深牛仔裤打版师的复查助手。用户要求重新仔细看【{label}】。\n"
        "这是带着上次判断的质证，不是重新猜一遍：\n"
        "- 只输出下面模板里列出的键，其他键一律不管；\n"
        "- 上次判断已预填在 \"value\" 里——推翻必须 evidence 写这次看见的具体"
        "视觉特征（形状/线条/位置），confidence 0.7 以上；\n"
        "- 看不清、无新证据：保持基线值原样返回，不要硬改。\n"
        f"【判据手册】（仅本组相关）\n{criteria}\n\n"
        f"【上次判断（基线）】\n{base}\n\n"
        f"【本轮用户原话】\n{text.strip() or '（无——请按照片复查）'}\n\n"
        f"【输出模板（编辑确认后原样返回，可包代码围栏）】\n{tpl}\n"
    )


# -- 基线 diff -------------------------------------------------------------------

def diff_obs(prior: Observation | None, obs: Observation,
             keys: tuple[str, ...]) -> list[dict]:
    """新观察 vs 基线：只记**变化**（旧值无 = 新判断；值相同不记）。"""
    old = (prior.entries if prior is not None else {})
    out: list[dict] = []
    for k in keys:
        if k not in obs.entries:
            continue
        new = obs.entries[k]
        if k in old and old[k].value == new.value:
            continue
        out.append({"key": k,
                    "old": None if k not in old else old[k].value,
                    "new": new.value,
                    "evidence": new.evidence})
    return out


def diff_note(group: str, diff: list[dict], keys: tuple[str, ...]) -> str:
    """复查结论一句话（禁「暂不改动」式不作为表述）。"""
    label = GROUP_LABELS.get(group, group)
    if diff:
        joined = "、".join(f"{d['key']} {_fmt(d['old'])}→{_fmt(d['new'])}"
                           for d in diff)
        return f"复查{label}：{len(diff)} 处更新（{joined}）"
    return f"复查{label}：细看后维持原判断（{len(keys)} 键未变，未见需推翻的证据）"


# -- 一次聚焦复查调用（永不抛） ----------------------------------------------------

def focus_recheck(group: str, text: str, photos, prior: Observation | None,
                  provider, thinking: str | None = None,
                  photo_meta: list[dict] | None = None):
    """一次聚焦 VLM 复查：prompt + 类别照片 -> (obs | None, diff, note)。

    provider 缺 / 无照片 / 调用失败 / 解析失败 -> (None, [], 原因一句话)，
    调用方（converse）零打扰降级。obs 只保留 focus 键（防模型多嘴改别组）。
    腰头/后贴袋组附裁剪放大辅助图（2026-09-30 特征尺度修复——整照里
    特征区低于模型可分辨阈值，复查「维持原判断」同陷阱；失败静默降级
    整照）。临时目录必须在 complete 之后才清理（首版用 with 块在调用前
    就删了图，辅助图从未真正送达——provider 读盘即 FileNotFoundError）。
    """
    keys = focus_keys(group)
    if provider is None:
        return None, [], "复查需要视觉模型，当前未配置"
    photos = list(photos or ())
    if not photos:
        return None, [], "该部位没有可用类别的照片"
    crop_paths: list = []
    tmp_crop = None
    if group in ("腰头", "后贴袋"):
        import tempfile
        try:
            from .crops import make_back_pocket_crops, make_waistband_crops
            tmp_crop = tempfile.TemporaryDirectory(prefix="yl_focus_crops_")
            if group == "腰头":
                crop_paths, _m, _n = make_waistband_crops(
                    photos, photo_meta, tmp_crop.name)
            else:
                crop_paths, _m, _n = make_back_pocket_crops(
                    photos, photo_meta, tmp_crop.name)
        except Exception:
            crop_paths = []
            if tmp_crop is not None:
                tmp_crop.cleanup()
                tmp_crop = None
    prompt = build_focus_prompt(group, keys,
                                prior.entries if prior else None, text)
    try:
        raw = parse_model_json(provider.complete(
            prompt, list(photos) + crop_paths, thinking, purpose="recheck"))
        obs = sanitize(raw)
    except (ValueError, RuntimeError):
        # VLMError 也是 RuntimeError：复查失败不阻断主流程
        return None, [], "视觉模型调用失败，保持原判断"
    finally:
        if tmp_crop is not None:
            tmp_crop.cleanup()
    entries = {k: v for k, v in obs.entries.items() if k in keys}
    if not entries:
        return None, [], "模型输出无可采纳的本组判断，保持原判断"
    obs = Observation(entries=entries,
                      dropped=[d for d in obs.dropped])
    return obs, diff_obs(prior, obs, keys), ""
