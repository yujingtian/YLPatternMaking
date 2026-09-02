"""S2 白名单/枚举值域 + 视觉确认 prompt 构造（与款式判据手册同源）。

模型直接经手的仅 23 键（5 分类轴 + 11 款式开关 + 7 形态枚举），其余全部代码
产出（87 键覆盖面内的数值键走 derive/families 查表；模型不口算绝对 cm）。

- MODEL_KEYS：白名单与值域，与 PatternOptions 校验器同源（options.py：
  mouth_mode L679 bulge/tangent/polyline、facing_mode L708 tangent/offset/bulge、
  watch_pocket_mode L784 custom/facing_intersect、back_patch_shape L869 四值、
  WaistbandType L16、Fit L34）。
- build_prompt：注入 ①已解析尺寸（只读）②代码轴预判 ③部件惯例先验
  ④判据手册段落（_CRITERIA，与 .doc/参数预测/款式判据手册.md 同源维护），
  尾随**预填模板**——模型任务=编辑确认，推翻预判必须 evidence 写视觉特征
  且 confidence>0.5，看不清保持预判。
"""

from __future__ import annotations

import json

_BOOL = "bool"

# 白名单：键 -> 值域（_BOOL 为布尔开关）
MODEL_KEYS: dict[str, tuple | str] = {
    # 分类轴 5（B 表）
    "waist_position": ("low", "mid_low", "mid", "mid_high", "high"),
    "gender": ("female", "male"),
    "body_shape": ("straight", "standard", "curvy"),
    "fit_level": ("skinny", "slim", "regular", "loose", "wide"),
    "stretch": ("none", "low", "high"),
    # 款式开关 10（D 表先验；front_pouch 袋布不在模型面——内部件照片看不到、
    # 无判据通道，未分析到不发射，判据手册补条目后再加回）
    "front_pocket": _BOOL,
    "front_pocket_facing": _BOOL,
    "front_patch": _BOOL,
    "watch_pocket": _BOOL,
    "back_patch": _BOOL,
    "back_yoke": _BOOL,
    "back_dart": _BOOL,
    "belt_loop": _BOOL,
    "fly": _BOOL,
    "fly_separate": _BOOL,
    # 形态枚举 7（视觉判据，引擎值域；mouth_depth 为弧深伪轴——只分档不报数）
    "waistband_type": ("straight", "curved"),
    "fit": ("skinny", "slim", "regular", "loose"),
    "back_patch_shape": ("rectangle", "baker_shield", "angular", "custom"),
    "front_pocket_mouth_mode": ("bulge", "tangent", "polyline"),
    "front_pocket_mouth_depth": ("shallow", "standard", "deep"),
    "front_pocket_facing_mode": ("tangent", "offset", "bulge"),
    "watch_pocket_mode": ("custom", "facing_intersect"),
}

AXIS_KEYS = ("waist_position", "gender", "body_shape", "fit_level", "stretch")
SWITCH_KEYS = ("front_pocket", "front_pocket_facing", "front_patch",
               "watch_pocket", "back_patch", "back_yoke", "back_dart", "belt_loop",
               "fly", "fly_separate")
ENUM_KEYS = ("waistband_type", "fit", "back_patch_shape", "front_pocket_mouth_mode",
             "front_pocket_mouth_depth", "front_pocket_facing_mode",
             "watch_pocket_mode")

# 枚举键的引擎默认（无照片/无预判时的预填值，options.py 同源；mouth_depth
# 伪轴默认 standard → families 弧深 0.4）
ENUM_DEFAULTS = {"waistband_type": "straight", "fit": "regular",
                 "back_patch_shape": "rectangle", "front_pocket_mouth_mode": "bulge",
                 "front_pocket_mouth_depth": "standard",
                 "front_pocket_facing_mode": "offset",
                 "watch_pocket_mode": "facing_intersect"}

# 无锚点轴的惯例预填（conf 0.3，提示模型重点看照片）
_AXIS_FALLBACK = {"waist_position": ("mid", "无 front_rise 锚点，按惯例预填，请照片确认"),
                  "body_shape": ("standard", "无腰臀尺寸，按惯例预填，请照片确认"),
                  "fit_level": ("regular", "无脚口/臀围锚点，按惯例预填，请照片确认")}

# 视觉判据段落（prompt ②类知识唯一来源；与 .doc/参数预测/款式判据手册.md
# 逐条同源——改判据先改手册、后同步此处，金标测试 test_extract_schema 校验）
_CRITERIA: dict[str, list[str]] = {
    "waistband_type": [
        "straight 直腰头：腰头是等宽直条，侧缝处上口平齐，腰头与裤身缝线分明。",
        "curved 弯腰头：腰头上口在侧缝处呈下凹弧线，腰头与裤身一体顺接、无硬折角。",
    ],
    "front_pocket_mouth_mode": [
        "bulge 弧线袋口：袋口为一道弯月弧线（弧深三档见 front_pocket_mouth_depth）。",
        "tangent 直切袋口：袋口近似直线斜切，仅在端部小圆角。",
        "polyline 折角袋口：袋口由两段直线构成，折点明显。",
    ],
    "front_pocket_mouth_depth": [
        "浅 shallow：弧线微弯近直，弧深（最深处到袋口弦的垂距）不足弦长 12%；",
        "标准 standard：经典五袋弯月，弧深约占弦长 20%（约 2.5cm）；",
        "深 deep：明显深月牙，弧深超弦长 25%（约 3.5cm，工厂经典款实测 3.36）；",
        "（目测基准：袋口弦长即袋口两端点直线距离，约 11~13cm；仅 bulge 弧线"
        "袋口时有意义，只分档不报数）。",
    ],
    "back_patch_shape": [
        "rectangle 方袋：袋底两角小圆角，底边宽度≈袋口宽（底部收窄但底中无尖点的梯形也归此）。",
        "baker_shield 盾形袋底：底中点尖出——底部是两条斜线在底中交汇成一个尖点，底中没有水平段，整袋轮廓 5 个角（Lee 经典盾形）。",
        "angular 切角袋：底部两角各斜切一刀，切完后底中仍留一段水平底边，整袋轮廓 6 个角。",
        "（判别口诀：数底部——两条斜线交于底中一点=baker_shield；底部有水平段仅两角被斜切=angular；底边平直无尖无切=rectangle。）",
    ],
    "fly_separate": [
        "true 独立门襟：门襟明线呈独立 J 形，门襟料与裤身分片缝制（现代主流）。",
        "false 连裁门襟：门襟与前片一体裁出，明线与袋口线连通（复古工艺，较少见）。",
    ],
    "back_yoke": [
        "true 后机头：后片腰下有一道横向分割线（水平或 V 形约克）。",
        "false 无机头：后片腰口到臀围之间无分割线（较少见，需照片证据）。",
    ],
    "back_dart": [
        "true 后腰省：后片可见竖向省道缝线（通常被机头掩盖，可靠度低，无把握勿报 true）。",
    ],
    "watch_pocket": [
        "true 有小表袋：正面右袋口上方可见一枚小袋（第五袋，经典五袋配置）。",
        "false 无小表袋：正面无小袋，或小袋缝死成装饰（需照片证据）。",
    ],
    "belt_loop": [
        "true 有裤耳：腰头上可见袢带；false 无裤耳（松紧腰常见，需照片证据）。",
    ],
    "waist_position": [
        "照片腰头落位：低腰卡胯骨 / 中腰脐下 1~2cm / 高腰盖过肚脐至自然腰线。",
    ],
    "fit_level": [
        "裤腿廓形：紧身包腿 skinny / 修身微锥 slim / 直筒常规 regular / 宽松 loose / 阔腿喇叭 wide。",
    ],
    "back_patch": [
        "true 有后贴袋：后片臀部可见贴袋（经典双袋）；false 无贴袋（需照片证据）。",
    ],
}

_MEAS_LABELS = {"waist": "腰围", "hip": "臀围", "knee": "膝围", "hem": "脚口",
                "front_rise": "前浪", "back_rise": "后浪", "outseam": "裤长",
                "thigh": "大腿围"}


def build_template(measurements: dict[str, float],
                   prejudged: dict[str, tuple[str, str]],
                   priors: dict[str, bool]) -> dict[str, dict]:
    """构造预填模板：轴=预判（缺锚点惯例预填）、开关=先验、枚举=引擎默认。"""
    template: dict[str, dict] = {}
    for axis in AXIS_KEYS:
        if axis in prejudged:
            value, ev = prejudged[axis]
            template[axis] = {"value": value, "confidence": 0.6,
                              "evidence": f"预判：{ev}"}
        else:
            value, note = _AXIS_FALLBACK.get(axis, (None, None))
            if value is None:   # gender/stretch 在 prejudge 恒有值，兜底防缺
                value, note = ("female", "默认女款，请照片确认") \
                    if axis == "gender" else ("low", "缺省 low，请照片确认")
            template[axis] = {"value": value, "confidence": 0.3,
                              "evidence": f"预填：{note}"}
    for key, prior in priors.items():
        template[key] = {"value": prior, "confidence": 0.5,
                         "evidence": "惯例先验（牛仔裤工业惯例，未见照片反例请保持）"}
    for key, default in ENUM_DEFAULTS.items():
        if key == "fit" and "fit_level" in prejudged:
            fl = prejudged["fit_level"][0]
            default = "loose" if fl == "wide" else fl
            template[key] = {"value": default, "confidence": 0.6,
                             "evidence": f"预判：fit_level {fl} 轴映射（wide→loose）"}
            continue
        template[key] = {"value": default, "confidence": 0.4,
                         "evidence": "引擎默认（照片可见形态差异时改值并写判据）"}
    return template


def build_prompt(describe: str, measurements: dict[str, float],
                 prejudged: dict[str, tuple[str, str]], priors: dict[str, bool],
                 photo_count: int) -> str:
    """S2 视觉确认主调用 prompt：预填模板 + 四级知识注入。"""
    lines = [
        "你是资深牛仔裤打版师的确认助手。用户提供了 "
        f"{photo_count} 张牛仔裤照片和一段文字描述。",
        "你的任务不是设计，而是「编辑确认」下方预填好的 JSON 模板：",
        "- 模板每项都由代码按尺寸与工业惯例算好；看照片逐项确认。",
        "- 只有明确看到不同才改 value，且必须在 evidence 写你看见的具体视觉特征"
        "（判据见下方手册段落），confidence 给 0.7 以上。",
        "- 前口袋袋口弧线是必看项：目测弧线最深处到袋口弦（袋口两端点连线）的"
        "垂距占弦长比例——不足 12% 改 shallow、约 20% 保持 standard、超 25% 改 "
        "deep，evidence 写目测比例（例「弧深约为弦长 28%」）。",
        "- 看不清 / 被遮挡 / 照片没拍到：保持预判值不动，confidence 下调。",
        "- 尺寸数值（cm）不在你的职责内，不要改任何数字、不要新增尺寸。",
        "- 只输出一个 JSON 对象（可包 json 代码围栏），不要输出其它文字。",
        "",
        f"【文字描述】{describe}",
        "【已解析尺寸 cm（来自描述，只读）】",
    ]
    if measurements:
        lines.append("、".join(
            f"{_MEAS_LABELS.get(k, k)} {v:g}" for k, v in measurements.items()))
    else:
        lines.append("（描述未提供尺寸）")
    lines.append("【代码轴预判（数字锚点优先，照片仅可带证据推翻）】")
    for axis, (value, ev) in prejudged.items():
        lines.append(f"- {axis}: {value}（{ev}）")
    lines.append("【部件惯例先验（按你的版型上下文算好，只报偏离）】")
    lines.append("、".join(f"{k}={'有' if v else '无'}" for k, v in priors.items()))
    lines.append("")
    lines.append("【视觉判据手册】")
    for key, rules in _CRITERIA.items():
        lines.append(f"- {key}：" + " ".join(rules))
    template = build_template(measurements, prejudged, priors)
    lines.append("")
    lines.append("【预填模板（编辑确认后原样返回）】")
    lines.append("```json")
    lines.append(json.dumps(template, ensure_ascii=False, indent=2))
    lines.append("```")
    return "\n".join(lines)
