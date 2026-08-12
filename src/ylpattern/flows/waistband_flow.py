"""腰头裁片流程：提取净长 -> 绘制净样 -> 缩水 -> 缝边（腰头裁片.md §三~§五）。

build_waistband(main_ctx) 从整版 ctx 提取前后腰弧净长与省位（代数求和），
在独立 DraftSheet 局部坐标系绘制腰头净样，经 cutter 三段处理产出 PatternPiece。
自含裁片，非 FlowRunner 编排（提取长度为标量输入；同 closure.py 口径）。
"""

from __future__ import annotations

import math

from ..cutter import add_seam_allowance, apply_shrinkage, edge_length
from ..draft import DraftContext
from ..geometry import CubicBezier, Point
from ..params import WaistbandGrain, WaistbandType
from ..pieces import PatternPiece, PieceEdge
from ..steps import waistband_steps as ws
from ..steps.waistband_steps import WaistbandSpec


def _arc_length_of_point(curve: CubicBezier, p: Point, *, n: int = 256) -> float:
    """点 p 在曲线上的最近点弧长（自 t=0 起算）。

    采样定位最近段 + 三分搜索精确化（邻域距离极小），返回
    ``curve.split(t)[0].length()``。用于后省 p_in（腰头构造线上）投影到
    后腰弧得其弧长位（腰头裁片.md §三 后腰后段）。
    """
    pts = curve.sample(n)
    best_i, best_d = 0, pts[0].distance_to(p)
    for i in range(1, n + 1):
        d = pts[i].distance_to(p)
        if d < best_d:
            best_d, best_i = d, i
    lo = max(0.0, (best_i - 1) / n)
    hi = min(1.0, (best_i + 1) / n)
    for _ in range(50):
        m1 = lo + (hi - lo) / 3
        m2 = hi - (hi - lo) / 3
        if curve.point_at(m1).distance_to(p) < curve.point_at(m2).distance_to(p):
            hi = m2
        else:
            lo = m1
    t = (lo + hi) / 2
    return curve.split(t)[0].length()


def _auto_drop(front_arc: CubicBezier, back_arc: CubicBezier,
               hip_front: Point, hip_back: Point) -> float:
    """侧缝拼合后前中相对后中的纵向落差（§四.分支B 动态推算）。

    读取前后片**真实侧缝线**（侧缝腰点 B → 臀围外缝点 H，而非腰弧在 B 处的
    切线）的倾角。以侧缝腰点为圆心旋转前片腰弧，令前片侧缝线与后片侧缝线完全
    重合（模拟纸样侧缝拼合）；旋转后前中 A_front 相对后中 A_back 的纵向高度差
    即下沉量（plan §三「2D 拼合推算」）。

    旧法取腰弧端点切线对齐（强制切线连续）会向上过旋、抵消落差，在 side_rise +
    curve_sag 同时存在时坍塌为 ~0。真实侧缝线是结构稳定特征，不受腰弧塑形影响，
    结果稳健（实测 side_rise/sag 开关 ±0.1cm）。主版坐标系 Y 向上，A_back.y −
    A_front.y > 0 即前中更低，该落差量作为腰头弧深喂入 waistband_curve，曲线向下凸（∪，后中下凹），凸向与测量正负号解耦。
    """
    B_front, A_front = front_arc.p0, front_arc.p3
    A_back, B_back = back_arc.p0, back_arc.p3
    af = math.atan2(hip_front.y - B_front.y, hip_front.x - B_front.x)
    ab = math.atan2(hip_back.y - B_back.y, hip_back.x - B_back.x)
    theta = ab - af                        # 令前片侧缝重合于后片侧缝的旋转角
    rotated = (A_front - B_front).rotate(math.degrees(theta))
    a_front_joined_y = B_back.y + rotated.dy
    return A_back.y - a_front_joined_y     # + = 后中更高（前中更低）；作弧深喂入下凸曲线


def extract_waistband_spec(main_ctx: DraftContext) -> WaistbandSpec:
    """从整版 ctx 提取腰头净长与刀口位（腰头裁片.md §三 代数求和）。

    口径：直/弯腰头统一读上腰弧 ``front/back.waistline_arc``（用户指引阶段4/3；
    弯腰头下腰弧为贴身边，差 <0.5cm，代数求和容忍）。
    """
    o = main_ctx.options
    front_arc = main_ctx.curve("front.waistline_arc")   # t=0 侧缝 B -> t=1 前中 A
    back_arc = main_ctx.curve("back.waistline_arc")     # t=0 后中 A -> t=1 侧缝 B

    # 后省：投影 p_in（省口内侧=后中侧）到后腰弧得后腰后段弧长
    back_widths: list[float] = []
    back_notches: list[float] = []
    for i in range(1, o.back_dart_count + 1):
        name = f"back.dart{i}_leg_inner"
        if name not in main_ctx.sheet:
            continue                    # 省量为 0 或开关关 -> 未上版，跳过
        w = o.back_dart_width[i - 1]
        if w <= 0:
            continue
        p_in = main_ctx.line(name).b    # LineSegment(apex, p_in) -> .b 为省口点
        back_notches.append(_arc_length_of_point(back_arc, p_in))
        back_widths.append(w)
    l_back = back_arc.length() - sum(back_widths)

    # 前省（前口袋吃省）：P1 自侧缝沿腰弧量取 front_pocket_p1_dist
    front_w = 0.0
    front_notch = None
    if o.front_pocket and o.front_pocket_dart_width > 0:
        front_w = o.front_pocket_dart_width
        front_notch = l_back + o.front_pocket_p1_dist
    l_front = front_arc.length() - front_w

    # 弯腰头弧深（§四.分支B）：用户手动覆盖 > 真实侧缝线夹角自动推算；直腰头=0
    if o.waistband_type is WaistbandType.CURVED:
        if o.waistband_front_drop is not None:
            computed_drop = o.waistband_front_drop
        else:
            hip_front = main_ctx.point("front.hip_outseam_point")
            hip_back = main_ctx.point("back.hip_outseam_point")
            computed_drop = _auto_drop(front_arc, back_arc, hip_front, hip_back)
    else:
        computed_drop = 0.0

    return WaistbandSpec(
        l_front=l_front,
        l_back=l_back,
        l_half=l_front + l_back,
        computed_drop=computed_drop,
        side_notch=l_back,
        back_dart_notches=tuple(back_notches),
        front_dart_notch=front_notch,
        has_front_dart=front_w > 0,
        has_back_dart=bool(back_widths),
    )


def _collect_notches(ctx: DraftContext) -> tuple[Point, ...]:
    """按顺序收集腰头刀口点（后省 -> 侧缝 -> 前省，各含左半镜像）。"""
    o = ctx.options
    names: list[str] = []
    for i in range(1, o.back_dart_count + 1):
        if f"wb.notch_back_dart{i}" in ctx.sheet:
            names += [f"wb.notch_back_dart{i}", f"wb.notch_back_dart{i}_mirror"]
    names += ["wb.notch_side", "wb.notch_side_mirror"]
    if "wb.notch_front_dart" in ctx.sheet:
        names += ["wb.notch_front_dart", "wb.notch_front_dart_mirror"]
    return tuple(ctx.point(n) for n in names if n in ctx.sheet)


def build_waistband(main_ctx: DraftContext) -> tuple[PatternPiece, DraftContext]:
    """整版跑完后构建腰头裁片：净样 -> 缩水 -> 缝边（腰头裁片.md §五）。

    返回 (PatternPiece, 局部 DraftContext)：前者供 SVG 输出，后者含命名元素
    供 trace/调试。
    """
    o = main_ctx.options
    spec = extract_waistband_spec(main_ctx)

    local = DraftContext(main_ctx.measurements, o)
    ws.draw_wb_bottom(local, spec)
    ws.draw_wb_top(local, spec)
    ws.draw_wb_ends(local, spec)
    ws.draw_wb_notches(local, spec)
    ws.draw_wb_grain(local, spec)

    # 装配净样边（逆时针顺序，语义边名用于缝边外扩）
    # fly_extension=0 等退化情形产生零长搭门边（首尾重合，无切线、令缝边偏移触发
    # 零向量归一化）——装配时即滤除；其相邻有效边本在同点相接，跳过后闭合不受影响
    net_edges = tuple(
        PieceEdge(role, g) for name, role in ws.EDGE_ORDER
        if (g := local.sheet.get(name).geom) and edge_length(g) > 1e-9)
    notches = _collect_notches(local)
    grain = local.line("wb.grain")
    piece = PatternPiece("waistband", "腰头裁片", net_edges,
                         notches=notches, grain=grain)

    # 裁切三段：缩水 -> 缝边（缝份不叠加缩水，§五）
    # 缩水率按面料经/纬（warp/weft）给；映射到腰头局部 X/Y 轴由经向方向决定
    # （§五.2）：LENGTH 长向(X)=经 -> X 吃 warp；WIDTH 宽向(Y)=经 -> Y 吃 warp
    if o.waistband_grain is WaistbandGrain.LENGTH:
        x_rate, y_rate = o.shrinkage_warp, o.shrinkage_weft
    else:  # WIDTH（默认）
        x_rate, y_rate = o.shrinkage_weft, o.shrinkage_warp
    piece = apply_shrinkage(piece, x_rate, y_rate)
    piece = add_seam_allowance(piece, o.waistband_seam_allowances)
    return piece, local
