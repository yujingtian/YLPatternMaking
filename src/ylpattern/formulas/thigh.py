"""毗围（脾围）闭环修正公式。

依据：.doc/前后片毗围推导.md §三（实测检验与智能分流修正策略）。

实测总长与目标总长差量 ΔW = W_target − W_measured（正 = 需加宽）：
  - 片间分配：|ΔW| ≤ 0.2cm 平分；|ΔW| > 0.2cm 强制 前20% : 后80%
    （防畸变红线：严禁 50:50 平分大差量，后侧承担核心调拨量）；
  - 双轨分流：|ΔW| ≤ 0.3cm 单动侧缝（锁死裆尖）；
    |ΔW| > 0.3cm 内外联动（侧缝 70% + 内缝裆宽 30%）；
  - 裆尖调拨（内缝 30% 部分）：前小裆 0.09·ΔW（钳 ±0.4，防卡耻骨）、
    后大裆 0.21·ΔW（钳 ±1.0，防下蹲崩破）；
  - 防内凹红线：侧缝收窄调控不得跨越臀围至膝围点的线性连接轴。

纯 float 函数；经验常数命名导出作默认参数，调用方（闭环层）
通过 PatternOptions 覆盖（thigh_* 选项），步骤层不硬编码。
"""


# ---- 阈值与比例常数默认值（推导.md §三，PatternOptions.thigh_* 可覆盖） ----
PIECE_SPLIT_MAX = 0.2      # 片间分配分界：|ΔW| ≤ 0.2cm 平分，否则 20:80
DUAL_TRACK_MIN = 0.3       # 双轨分流阈值：|ΔW| ≤ 0.3cm 单动侧缝
FRONT_SHARE_LARGE = 0.2    # 大差量前片分配比（后片 0.8）
FRONT_CROTCH_COEF = 0.09   # 前小裆尖调拨系数 = 0.30 × 30%（§三.2）
BACK_CROTCH_COEF = 0.21    # 后大裆尖调拨系数 = 0.70 × 30%（§三.2）
FRONT_CROTCH_MAX = 0.4     # 前小裆最大调整上限（防卡耻骨，极值红线）
BACK_CROTCH_MAX = 1.0      # 后大裆最大调整上限（防下蹲崩破，极值红线）


def _clamp(v: float, limit: float) -> float:
    return max(-limit, min(limit, v))


def front_share_ratio(dw: float, split_max: float = PIECE_SPLIT_MAX,
                      share_large: float = FRONT_SHARE_LARGE) -> float:
    """前片分配比。|ΔW| ≤ split_max 平分 0.5；大差量强制 share_large
    （§三.1 红线：严禁 50:50 平分大差量）。"""
    return 0.5 if abs(dw) <= split_max else share_large


def front_crotch_shift(dw: float, dual_track_min: float = DUAL_TRACK_MIN,
                       coef: float = FRONT_CROTCH_COEF,
                       max_abs: float = FRONT_CROTCH_MAX) -> float:
    """前小裆尖调整量 ΔX_front_crotch（+X 裆湾方向为加宽）。

    |ΔW| ≤ dual_track_min 单动侧缝 → 0；内外联动 → coef·ΔW，
    钳 ±max_abs（防卡耻骨，§三.2 私密空间约束上限）。
    """
    if abs(dw) <= dual_track_min:
        return 0.0
    return _clamp(coef * dw, max_abs)


def back_crotch_shift(dw: float, dual_track_min: float = DUAL_TRACK_MIN,
                      coef: float = BACK_CROTCH_COEF,
                      max_abs: float = BACK_CROTCH_MAX) -> float:
    """后大裆尖调整量 ΔX_back_crotch（+X 裆湾方向为加宽）。

    |ΔW| ≤ dual_track_min → 0；内外联动 → coef·ΔW，钳 ±max_abs
    （防下蹲崩破，§三.2）。
    """
    if abs(dw) <= dual_track_min:
        return 0.0
    return _clamp(coef * dw, max_abs)


def cap_crotch_total(applied: float, request: float, limit: float) -> float:
    """裆尖累计调整量钳制（极值红线针对全程累计量，§三.2）。

    闭环迭代逐轮叠加裆尖调整时，累计量 applied + request 不得突破
    ±limit（前小裆 0.4 防卡耻骨 / 后大裆 1.0 防下蹲崩破），
    返回钳制后的累计值；本轮实际增量 = 返回值 − applied。
    """
    return _clamp(applied + request, limit)


def outseam_shifts(dw: float, fc: float | None = None,
                   bc: float | None = None, *,
                   split_max: float = PIECE_SPLIT_MAX,
                   share_large: float = FRONT_SHARE_LARGE
                   ) -> tuple[float, float]:
    """前后片侧缝（外缝）承担的调整量（正 = 加宽毗围）。

    片分配（平分或 share_large 大差量比 20:80）减去裆尖已承担部分，
    剩余全部由侧缝承担：单动侧缝时裆尖为 0，即全量；裆尖钳制产生的
    残余回流侧缝（尽可能靠近目标，不破坏裆部结构）。
    fc / bc 缺省时按 ΔW 默认参数求裆尖调整量；闭环迭代中应传本轮
    实际增量（累计钳制后），保证残余正确回流。
    """
    if fc is None:
        fc = front_crotch_shift(dw)
    if bc is None:
        bc = back_crotch_shift(dw)
    share = front_share_ratio(dw, split_max, share_large)
    return share * dw - fc, (1 - share) * dw - bc


def clamp_outseam_target(x_cur: float, dw_out: float, x_chord: float) -> float:
    """外缝目标 x 的防内凹钳制（§三.2 红线）。

    本坐标系外缝朝 −X：加宽（dw_out > 0）目标向 −X 移，天然远离
    连接轴不钳；收窄时目标向 +X 移，不得跨越臀围至膝围点的线性
    连接轴（弦 x_chord），钳在弦上。

    参数：
        x_cur    外缝在测量高度的当前 x
        dw_out   侧缝承担的调整量（正 = 加宽）
        x_chord  臀围外缝点 → 膝围外缝点连线在测量高度的 x
    """
    return min(x_cur - dw_out, x_chord)
