"""发射层：测量结果 -> 尺寸单 TOML（.doc/工厂DXF逆向解析.md §5）。

- 手写 TOML 序列化器（核心层零依赖：tomllib 只读不写；`_` 前缀键 =
  备注行，与 Measurements/PatternOptions.from_dict 的忽略口径一致）。
- **发射前回验**：构造 Measurements.from_dict + PatternOptions.from_dict，
  未知键 TypeError / 非法值 ValueError 在写文件前拦截（emit 层白名单 =
  dataclasses.fields(PatternOptions)，measure 层保证只发射已量测键）。
- 圆整口径：测量 0.1 / 选项 0.01 / 档差 0.01（§5.2）。
- 子表（front_piece_seam_allowances）排在 [options] 标量键之后
  （TOML 主表/子表次序硬约束，examples 尺寸单同款口径）。
"""

from __future__ import annotations

import dataclasses
from typing import Any

from ..params.measurements import Measurements
from ..params.options import PatternOptions
from .measure import MeasuredSize

# 发射键 -> 注释（与 examples/ 尺寸单注释同源，量不到的不出现）
_MEASURE_NOTES = {
    "waist": "腰围（成品）",
    "hip": "臀围 = 净臀围 + 放松量",
    "knee": "膝围",
    "hem": "裤口（脚口围）",
    "front_rise": "前浪（前裆长，含腰头）",
    "back_rise": "后浪（后立裆长，含腰头）",
    "outseam": "裤长（外侧缝长）",
    "thigh": "大腿围（0 = 未录入）",
}

_OPTION_NOTES = {
    "delta": "前后片臀围单侧调节量 Δ（反解析：前后臀围线弦差之半）",
    "waist_balance": "前后片腰围调节量（反解析：机头上口 vs 前腰段+袋口段）",
    "knee_adjust": "膝围前后片调节量（反解析：中裆线前后弦差之半）",
    "hem_adjust": "脚口前后片调节量（反解析：脚口线前后弦差之半）",
    "rise_adjust": "直裆修正（反解析：CF 腰角->裆尖竖直距 + 腰头 − 0.25H）",
    "front_intake_adjust": "前中内收修正量（反解析：实测内收 − 默认系数分量，"
                           "ratio 保持默认）",
    "back_intake": "后中内收比例模数 X（反解析：机头拼回后腰/臀 CB 斜率×15）",
    "front_pocket_p1_dist": "袋口 P1 腰弧锚距（反解析：前代顶边袋口段 P1→B′×weft）",
    "front_pocket_p2_drop": "袋口 P2 外缝锚深（反解析：前代侧边段 B′→P2×warp）",
    "front_pocket_mouth_mode": "袋口净线模式（反解析：还原后弦法向剖面——"
                               "有折角=折线式 / 平滑单峰=弧高式；tangent 不可辨识）",
    "front_pocket_mouth_bulge": "袋口弧高（反解析：剖面峰值÷2——arc_through "
                                "渲染弧高 = 2×bulge，真弧高减半发射）",
    "front_pocket_mouth_bulge_at": "袋口弧顶弦位（反解析：峰值弦位映射 "
                                   "(f−0.3125)/0.375，0=腰头端）",
    "front_pocket_mouth_corners": "袋口折角表 (弦位, 内推深度)（反解析：剖面 ≥8° 转角）",
    "front_pocket_facing_width": "袋贴腰头宽（反解析：前代顶边 P1→A 段×weft，"
                                 "引擎同锚 P1 沿腰弧朝前浪顶点）",
    "front_pocket_facing_side_w": "袋贴侧缝深（反解析：前代右边 P2→C 段×warp，"
                                  "引擎同锚 P2 沿外缝弧向下）",
    "front_pocket_facing_mode": "bulge = 前代净边大弧形态（内边弧高式，tangent/"
                                "offset 不可辨识不发射）",
    "front_pocket_facing_bulge": "袋贴内边弧高（反解析：净边大弧剖面峰值÷2——"
                                 "arc_through 渲染弧高 = 2×bulge，背离袋口弦"
                                 "为正 = 向裤身内侧凹入）",
    "front_pocket_facing_bulge_at": "袋贴内边弧顶弦位（反解析：峰值弦位映射 "
                                    "(f−0.3125)/0.375，弧顶仅可表达弦中段 "
                                    "0.31~0.69，0=腰端 P_fw）",
    "watch_pocket": "小表袋开关（反解析：裁片在场即开，位置未量测自设默认）",
    "watch_pocket_mode": "小表袋模式（反解析：净样可定向还原 = custom 原样；"
                         "对折片歧义/超宽回退 facing_intersect 默认）",
    "watch_pocket_points": "custom 净样锚点表 cm、dy 向下、参考点 = 顶边外端"
                           "（反解析：净环丝缕定向还原 + 共线顶点折叠，"
                           "TOML 数组 dy 同向）",
    "watch_pocket_edges": "custom 逐边形态（line / arc=弧高+弧顶分位）"
                          "（反解析：段内弦高 ≥0.1cm 发射弧边，弧高已换算"
                          "引擎单位 = 真弧高 ÷2；边数 = 锚点数闭合）",
    "watch_pocket_offset_from_top": "小表袋顶边深（反解析自设默认：custom = 解析"
                                    "重建袋口弧最深可见顶边；回退态 = 0.42×"
                                    "袋口侧深 p2，顶边恒在袋口弧 O 侧可见）",
    "watch_pocket_offset_from_side": "小表袋外端距侧缝腰点（反解析自设默认："
                                     "custom = 0.5；回退态 = 0.12×腰锚 p1）",
    "watch_pocket_width": "小表袋袋口宽（仅回退态发射：0.55×腰锚 p1，"
                          "右端 0.67×p1 避开 P1 处弧线贴腰浅水区；"
                          "custom 由 points 决定形状不用它）",
    "back_patch": "后贴袋开关（反解析：裁片在场即开，位置自设默认"
                  "三定则——机头下方/对齐后腰中点/袋底保持毗围线上方）",
    "back_patch_shape": "后贴袋净形（反解析：净环丝缕定向还原可量测 = "
                        "custom 原样；不可用回退 rectangle 默认并披露）",
    "back_patch_custom_points": "custom 净形角点 cm、u 朝侧缝 +、v 向下 +、"
                                "V0 = 袋口近后浪侧顶点（反解析：净环还原"
                                "原样；铺版图无可观测手性，取向自设袋口"
                                "x 小端靠后浪）",
    "back_patch_custom_edges": "custom 逐边形态 (弧高, 弧顶位)、弧高 0 = "
                               "直线（反解析：段内弦高 ≥0.1cm 发射弧边，"
                               "弧高换算引擎单位 = 真弧高 ÷2；**外凸为负**"
                               "——引擎局部->全局 180° 旋转（û=后浪->侧缝"
                               "=全局 −X̂）保定向、全局环 CCW，arc_through "
                               "正 bulge = 左手法向 = 内凹；边数 = 角点数"
                               "闭合）",
    "back_patch_inset_x": "距后浪线沿约克底线（反解析自设默认 = "
                          "(约克底线还原长 − 袋口宽)/2 居中 ≈ 对齐后腰"
                          "中点；引擎约克底线与工厂还原长的残差即居中"
                          "偏心，披露不修正）",
    "back_patch_drop_y": "距约克底线向下（反解析自设默认 3.5 = 引擎常规；"
                         "袋底保持毗围线上方 ≥0.5，放不下先上提后钳 0.5 "
                         "披露越线）",
    "waistband_width": "腰头宽（反解析：腰头条带面积/中线闭式解）",
    "waistband_type": "腰头类型（反解析：长边矢高 >2mm = 弯腰头）",
    "waistband_grain": "腰头经向方向（反解析：丝缕线与长边夹角 <45° = length）",
    "back_yoke_cb_dist": "机头后中深（反解析：机头 CB 端弧×warp）",
    "back_yoke_side_dist": "机头侧缝深（反解析：机头侧端弧×warp）",
    "shrinkage_warp": "全局经向缩水率（还原系数同时是再打版的放大率）",
    "shrinkage_weft": "全局纬向缩水率",
    "size_label": "尺码标签（头标 SAMPLE SIZE）",
}

# 嵌套 dict 选项（TOML 子表 [options.<key>]；其余为标量键）
_SUBTABLE_KEYS = ("front_piece_seam_allowances",)

_SUBTABLE_NOTES = {
    "front_piece_seam_allowances": "前片裁片缝份（反解析：净顶点->毛边"
                                   "最近点向量分类，横向=缝边/竖向脚口=卷边）",
}


def options_whitelist() -> frozenset[str]:
    """PatternOptions 字段名全集（emit 层防未知键的第一道闸）。"""
    return frozenset(f.name for f in dataclasses.fields(PatternOptions))


def _fmt(v: Any) -> str:
    """TOML 字面量：布尔/数值直写（整数无小数点、浮点去尾零），字符串
    加引号，元组/列表递归成数组（mouth_corners 折角表）。"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return repr(round(v, 4))
    if isinstance(v, str):
        return _quote(v)
    if isinstance(v, (tuple, list)):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    return str(v)


def _quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_size_file(base: MeasuredSize, options: dict,
                    size_run: dict | None = None) -> dict:
    """测量结果 -> 尺寸单原始 dict（load_size_file 同构；发射前回验）。

    测量圆整 0.1、选项/档差 0.01；size_run 为 None（单码）或
    ``{"base":…, "style":…, "order":[…], "band":[{…}]}``（层 3，grade.py
    产出）。回验失败（TypeError/ValueError）直接上抛——宁可不写文件，
    不写引擎读不进的文件。
    """
    measures = {k: round(v, 1) for k, v in base.values.items()}
    flat: dict[str, Any] = {}
    subtables: dict[str, dict] = {}
    for k, v in options.items():
        if k in _SUBTABLE_KEYS and isinstance(v, dict):
            subtables[k] = {kk: round(vv, 2) for kk, vv in v.items()}
        else:
            flat[k] = v
    data: dict[str, Any] = {"measurements": measures,
                            "options": {**flat, **subtables}}
    if size_run is not None:
        data["size_run"] = size_run
    # 回验：构造即校验（未知键/非法值在这里拦截）
    Measurements.from_dict(dict(measures))
    PatternOptions.from_dict(dict(flat, **{k: dict(v) for k, v in subtables.items()}))
    return data


def render_toml(data: dict, header: list[str]) -> str:
    """尺寸单 dict -> TOML 文本（header 为文件头注释行）。"""
    out: list[str] = ["# " + line for line in header]
    out.append("")
    out.append("[measurements]")
    for k, v in data["measurements"].items():
        note = _MEASURE_NOTES.get(k)
        out.append(f"{k} = {_fmt(v)}" + (f"    # {note}" if note else ""))
    opts = data.get("options", {})
    if opts:
        out.append("")
        out.append("[options]")
        for k, v in opts.items():
            if isinstance(v, dict):
                continue                     # 子表延后
            note = _OPTION_NOTES.get(k)
            out.append(f"{k} = {_fmt(v)}" + (f"    # {note}" if note else ""))
        for k, v in opts.items():
            if not isinstance(v, dict):
                continue
            out.append("")
            note = _SUBTABLE_NOTES.get(k)
            if note:
                out.append(f"# {note}")
            out.append(f"[options.{k}]")
            for kk, vv in v.items():
                out.append(f"{kk} = {_fmt(vv)}")
    sr = data.get("size_run")
    if sr is not None:
        out.append("")
        out.append("# 推码尺码表（反解析层 3：逐码独立测量再差分；"
                   "enabled = false 或删本段走单码）")
        out.append("[size_run]")
        out.append("enabled = true")
        out.append(f"base = {_quote(str(sr['base']))}")
        out.append(f"style = {_quote(str(sr['style']))}")
        if sr.get("order"):
            order = ", ".join(_quote(str(s)) for s in sr["order"])
            out.append(f"order = [{order}]")
        for band in sr.get("band", ()):
            out.append("")
            sizes = ", ".join(_quote(str(s)) for s in band["sizes"])
            out.append("[[size_run.band]]")
            out.append(f"sizes = [{sizes}]")
            for k in ("waist", "hip", "knee", "hem", "front_rise",
                      "back_rise", "outseam", "thigh"):
                if k in band:
                    out.append(f"{k} = {_fmt(band[k])}")
    return "\n".join(out) + "\n"


def write_size_file(path: str, data: dict, header: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(render_toml(data, header))
