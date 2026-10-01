"""S2 白名单/枚举值域 + 视觉确认 prompt 构造（与款式判据手册同源）。

模型直接经手的仅 26 键（5 分类轴 + 10 款式开关 + 7 形态枚举 + 4 比例读图），
其余全部代码产出（87 键覆盖面内的数值键走 derive/families 查表；模型不口算
绝对 cm——比例键只报 0~1 小数，cm 换算在 derive）。

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
    # 比例读图 4（K5-d，2026-09-30 起；10-01 扩 p2/小表袋宽）：值域 = 浮点
    # 窗（parse 窗，出窗丢弃=未观测）；物理窗在 derive 钳制。模型只报 0~1
    # 比例、绝不报 cm
    "ratio_front_pocket_p1": (0.10, 0.90),
    "ratio_front_pocket_p2": (0.10, 0.90),
    "ratio_watch_pocket_width": (0.10, 0.90),
    "ratio_back_patch_width": (0.10, 0.90),
}

AXIS_KEYS = ("waist_position", "gender", "body_shape", "fit_level", "stretch")
SWITCH_KEYS = ("front_pocket", "front_pocket_facing", "front_patch",
               "watch_pocket", "back_patch", "back_yoke", "back_dart", "belt_loop",
               "fly", "fly_separate")
ENUM_KEYS = ("waistband_type", "fit", "back_patch_shape", "front_pocket_mouth_mode",
             "front_pocket_mouth_depth", "front_pocket_facing_mode",
             "watch_pocket_mode")

# 比例读图键（K5-d）：MODEL_KEYS 里 float 窗值域的键（parse 窗）；物理窗
# （p1 [0.40,0.65] / p2 [0.20,0.40] / 小表袋宽 [0.22,0.40] / 贴袋宽
# [0.55,0.80]）在 derive._adopted_ratio 钳制
RATIO_KEYS = ("ratio_front_pocket_p1", "ratio_front_pocket_p2",
              "ratio_watch_pocket_width", "ratio_back_patch_width")

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
        "straight 直腰头：腰头是等宽直条，上口整体走平——门襟顶、侧缝、后中大致同高。",
        "curved 弯腰头：腰头上口沿腰弧下凹——前中呈下凹弧线、顺门襟 V 尖下落，后中随后弧下落，"
        "侧缝处反而是整条腰头的最高点（低腰款最常见）。",
        "判读口诀：一看门襟顶——上口顺 V 尖下落=curved、走平=straight；二看后中——上口下落=curved。"
        "侧缝不作判据（弯腰头侧缝处平直且最高，看侧缝必误判成 straight）；"
        "腰头是否独立缝线、有无裤耳、有无硬 V 折角均不作判据，只认上口前后中走向。",
    ],
    "front_pocket_mouth_mode": [
        "bulge 弧线袋口：袋口为一道弯月弧线，弧度肉眼明显（弧深三档见 front_pocket_mouth_depth）。",
        "tangent 直切袋口：袋口近似直线斜切，仅在端部小圆角。",
        "polyline 折角袋口：袋口由两段直线构成，折点明显。",
        "（判型总则：近垂直优先 tangent——打版师手画线不可能百分百垂直，目测"
        "近乎垂直/近直的袋口一律判 tangent；弯月弧形态清晰可辨才判 bulge、"
        "折点肉眼可辨才判 polyline。）",
    ],
    "front_pocket_mouth_depth": [
        "浅 shallow：弧线微弯近直，弧深（最深处到袋口弦的垂距）不足弦长 12%；",
        "标准 standard：经典五袋弯月，弧深约占弦长 20%（约 2.5cm）；",
        "深 deep：明显深月牙，弧深超弦长 25%（约 3.5cm，工厂经典款实测 3.36）；",
        "（目测基准：袋口弦长即袋口两端点直线距离，约 11~13cm；仅 bulge 弧线"
        "袋口时有意义，只分档不报数）。",
    ],
    "back_patch_shape": [
        "rectangle 方袋：底边一条直线通到底，无尖点也无切角（底部收窄但底中无尖点无切角的梯形也归此）。",
        "baker_shield 盾形袋底：底中点尖出——底部两条斜边直接相交于底中一点（交点即最低处），夹角不论大小、钝角浅尖也算尖；底中没有水平段，整袋轮廓 5 个角（Lee 经典盾形）。",
        "angular 切角袋：底部两角各斜切一刀，切完后底中仍留一段水平底边（两条斜边被这段水平边隔开、不直接相交），整袋轮廓 6 个角。",
        "（判别口诀：数底部——两条斜边交于底中一点=baker_shield，夹角大小不管；底中留水平段仅两角被斜切=angular；底边一条直线到底无尖无切=rectangle。盾形与切角唯一分界=底中有没有水平段。）",
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

# 照片类别 → 重点看清单（C6【照片清单】段；类别=用户上传时手动标注，
# 2026-09-29 口径不做自动分类）
_PHOTO_FOCUS = {"front": "正面平铺：重点看前口袋形态与弧深、门襟、小表袋",
                "back": "背面平铺：重点看后贴袋形状、育克分割线、后腰省",
                "other": "其他"}


def build_template(measurements: dict[str, float],
                   prejudged: dict[str, tuple[str, str]],
                   priors: dict[str, bool]) -> dict[str, dict]:
    """构造预填模板：轴=预判（缺锚点惯例预填）、开关=先验、枚举=引擎默认、
    比例键=null 未观测（K5-d，模型看照片目测比例后填）。"""
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
    for key in RATIO_KEYS:   # K5-d 比例读图：null=未观测，模型看照片才填
        template[key] = {"value": None, "confidence": 0.0,
                         "evidence": "未观测（看不清保持 null；只报比例、绝不报 cm）"}
    return template


def build_prompt(describe: str, measurements: dict[str, float],
                 prejudged: dict[str, tuple[str, str]], priors: dict[str, bool],
                 photo_count: int, context_brief: str | None = None,
                 prior_obs=None, photo_meta: list[dict] | None = None) -> str:
    """S2 视觉确认主调用 prompt：预填模板 + 四级知识注入。

    context_brief / prior_obs（2026-09-29 B1/B3 多轮注入）：账本摘要
    （尺寸终值/描述倾向/已应用调版）与上次视觉判断基线，均缺省 None
    ——单发/首轮行为与历史逐位一致。prior_obs 逐键可见 + 推翻须证据，
    模型首次能看见早前批次的判断（此前只在后台 merge、模型无感知）。

    photo_meta（2026-09-29 C6 照片三类）：[{category, note}] 按/photos/
    顺序对齐（超 photo_count 截断），渲染【照片清单】逐张一行（类别 →
    重点看清单 + 用户说明）；缺省 None 不注段——单发 `agent extract`
    路径 prompt 逐位不变（硬约束 5）。类别是用户标注，与照片明显不符
    以照片为准并在 evidence 说明（防标错槽位硬伤）。
    """
    lines = [
        "你是资深牛仔裤打版师的确认助手。用户提供了 "
        f"{photo_count} 张牛仔裤照片和一段文字描述。",
        "你的任务不是设计，而是「编辑确认」下方预填好的 JSON 模板：",
        "- 模板每项都由代码按尺寸与工业惯例算好；看照片逐项确认。",
        "- 只有明确看到不同才改 value，且必须在 evidence 写你看见的具体视觉特征"
        "（判据见下方手册段落），confidence 给 0.7 以上。",
        "- 前口袋袋口是必看项，先判形态再量弧深：①形态 front_pocket_mouth_mode——"
        "袋口是一道平滑弯月弧线=保持 bulge、近似直线斜切仅端部小圆角=改 tangent、"
        "两段直线折点明显=改 polyline（判据见手册）；②弧深 front_pocket_mouth_depth"
        "（仅 bulge 时）——目测弧线最深处到袋口弦（袋口两端点连线）的垂距占弦长比例"
        "——不足 12% 改 shallow、约 20% 保持 standard、超 25% 改 deep，"
        "evidence 写目测比例（例「弧深约为弦长 28%」）。",
        "- 腰头形态是必看项，先判 waistband_type（口诀见手册：一看门襟顶——"
        "上口顺 V 尖下落=curved、走平=straight；二看后中——上口下落=curved）。"
        "照片清单中有「工程自动辅助图」字样的腰头区放大图时，以它为准细读上口走向；"
        "没有辅助图时，顺上口缝线从两侧外缝水平追踪到前中纽扣处再判。",
        "- 后贴袋形状是必看项，先判 back_patch_shape（口诀见手册：数底部——"
        "两条斜边交于底中一点=baker_shield 夹角大小不管、底中留水平段仅两角被斜切"
        "=angular、一条直线到底无尖无切=rectangle）。照片清单中有「工程自动辅助图」"
        "字样的后贴袋区放大图时，以它为准细读袋底轮廓再判。",
        "- 比例读图是必看项（只报 0~1 的小数比例、绝不报 cm，代码会乘已知尺寸"
        "换算；横向比例的分母一律用**单侧腰宽**=该侧侧缝腰点到前中门襟纽扣"
        "中线（背面照则后中到侧缝腰点）的腰头可见长度，约为整条腰头全宽的"
        "一半，勿用全宽）：① ratio_front_pocket_p1——正面照前口袋袋口上端"
        "（靠侧缝一端）到侧缝腰点的距离 ÷ 该侧单侧前腰宽，"
        "目测约几成（例 0.55）；② ratio_back_patch_width——背面照单只后贴袋"
        "袋口宽 ÷ 贴袋所在那一侧的单侧后腰宽；③ ratio_front_pocket_p2——"
        "正面照前口袋袋口下端（靠侧缝一端）到腰头下缘（腰头与裤身交界的"
        "缝线）的竖直距离 ÷ 腰头下缘到裆底（两腿分叉处）的竖直距离"
        "（例 0.30）；④ ratio_watch_pocket_width——正面照小表袋（前口袋"
        "袋口内的小袋）袋口宽 ÷ 该侧单侧前腰宽。evidence 写「约 55%」式"
        "目测读数；看不清/被遮挡/照片没拍到就保持 null 不填。",
        "- 看不清 / 被遮挡 / 照片没拍到：保持预判值不动，confidence 下调。",
        "- 尺寸数值（cm）不在你的职责内，不要改任何数字、不要新增尺寸。",
        "- 只输出一个 JSON 对象（可包 json 代码围栏），不要输出其它文字。",
        "",
    ]
    if photo_meta:
        lines.append("【照片清单（类别为用户标注，与照片内容明显不符时以照片为准"
                     "并在 evidence 说明）】")
        for i, m in enumerate(photo_meta[:photo_count], 1):
            c = str((m or {}).get("category") or "other")
            focus = _PHOTO_FOCUS.get(c, _PHOTO_FOCUS["other"])
            note = str((m or {}).get("note") or "").strip()
            if note:
                lines.append(f"第{i}张 {focus}（用户说明：{note}）："
                             "以说明为准，重点核实所指特征")
            elif c == "other":
                lines.append(f"第{i}张 其他：无说明，按画面内容判断")
            else:
                lines.append(f"第{i}张 {focus}")
        lines.append("")
    lines.append(f"【文字描述】{describe}")
    if context_brief:
        lines.append("【已确认状态（多轮累积终值——早轮亲说/已定倾向都在这，"
                     "与照片冲突时以照片为准但须证据）】")
        lines.append(context_brief)
    lines.append("【已解析尺寸 cm（来自描述，只读）】")
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
    prior_entries = getattr(prior_obs, "entries", None) or {}
    if prior_entries:
        lines.append("")
        lines.append("【上次视觉判断（基线，早前照片批次）——本轮照片推翻必须 "
                     "evidence 写视觉特征；看不清保持基线值】")
        for k, e in prior_entries.items():
            v = getattr(e, "value", None)
            v = ("有" if v is True else "无" if v is False else v)
            lines.append(f"- {k}: {v}（{getattr(e, 'evidence', '')}）")
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
