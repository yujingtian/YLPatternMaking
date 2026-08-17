"""腰头裁片流程：提取净长 -> 绘制净样 -> 缩水 -> 缝边（腰头裁片.md §三~§五）。

build_waistband(main_ctx) 从整版 ctx 提取前后腰弧净长（代数求和），在独立
DraftSheet 局部坐标系绘制腰头净样，经 cutter 三段处理产出 PatternPiece。
自含裁片，非 FlowRunner 编排（提取长度为标量输入；同 closure.py 口径）。
"""

from __future__ import annotations

import math

from ..cutter import add_seam_allowance, apply_shrinkage, edge_length
from ..draft import DraftContext
from ..geometry import CubicBezier, LineSegment, Point, Vector
from ..params import WaistbandGrain, WaistbandType
from ..pieces import PatternPiece, PieceEdge
from ..steps import waistband_steps as ws
from ..steps.waistband_steps import WaistbandSpec


def _dir(geom: LineSegment | CubicBezier, at_end: bool) -> Vector:
    """几何体端部单位切向（直线取 a->b 整体方向，贝塞尔取端点切线）。"""
    if isinstance(geom, LineSegment):
        v = geom.b - geom.a
    else:
        v = geom.tangent_at(1.0 if at_end else 0.0)
    return v.normalized() if v.length > 0 else Vector(1.0, 0.0)


def _sa_crossing(corner: Point, notch_dir: Vector, sa_tangent: Vector,
                 sa_amt: float, sx: float, sy: float) -> Point:
    """角点刀口的毛样位：刀口线（过 corner 沿 notch_dir）与缝边线（sa_tangent
    所在边沿外法向偏 sa_amt）的交点（腰头裁片.md §四.2 v0.4「沿着…和缝边
    相交的地方」）。

    两线先按缩水比例 (sx, sy) 仿射变换再求交——缩水先于缝边、缝份不叠加缩水
    （§五），各向异性缩水后垂直角点的两线不再正交，故取真交点而非法向平移。
    外法向 = 存储走向切线逆时针转 90°（与 cutter._offset_edge_points 同口径）；
    两线平行（数值退化）回退法向平移一个缝份。
    """
    c = Point(corner.x * sx, corner.y * sy)
    d = Vector(notch_dir.dx * sx, notch_dir.dy * sy).normalized()
    t = Vector(sa_tangent.dx * sx, sa_tangent.dy * sy).normalized()
    n = t.perpendicular()
    off = c + n.scale(sa_amt)
    det = d.dx * t.dy - d.dy * t.dx
    if abs(det) < 1e-9:
        return c + n.scale(sa_amt)
    r = off - c
    u = (r.dx * t.dy - r.dy * t.dx) / det
    return c + d.scale(u)


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
    """从整版 ctx 提取腰头净长（腰头裁片.md §三 代数求和）。

    口径：直/弯腰头统一读上腰弧 ``front/back.waistline_arc``（用户指引阶段4/3；
    弯腰头下腰弧为贴身边，差 <0.5cm，代数求和容忍）。省宽仅作长度扣减，
    省位/侧缝弧长不再提取（§四.2 v0.4 刀口只打后中与两端边界）。
    """
    o = main_ctx.options
    front_arc = main_ctx.curve("front.waistline_arc")   # t=0 侧缝 B -> t=1 前中 A
    back_arc = main_ctx.curve("back.waistline_arc")     # t=0 后中 A -> t=1 侧缝 B

    # 后省：省宽求和扣减（省口未上版或省量 0 的不计）
    back_w = sum(o.back_dart_width[i - 1]
                 for i in range(1, o.back_dart_count + 1)
                 if f"back.dart{i}_leg_inner" in main_ctx.sheet
                 and o.back_dart_width[i - 1] > 0)
    l_back = back_arc.length() - back_w

    # 前省（前口袋吃省）：省宽扣减
    front_w = (o.front_pocket_dart_width
               if o.front_pocket and o.front_pocket_dart_width > 0 else 0.0)
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
    )


def _collect_notches(ctx: DraftContext) -> tuple[Point, ...]:
    """收集腰头净样刀口点（§四.2 v0.4：后中 -> 左下 -> 左上 -> 右下 -> 右上）。"""
    names = ("wb.notch_back_center", "wb.notch_left_bottom",
             "wb.notch_left_top", "wb.notch_right_bottom", "wb.notch_right_top")
    return tuple(ctx.point(n) for n in names if n in ctx.sheet)


def _project_corner_notches(piece: PatternPiece, local: DraftContext,
                            sx: float, sy: float) -> PatternPiece:
    """净样刀口换算至缝边位、整体替换毛样刀口（§四.2 v0.4，flow 私有
    工艺策略，同前/后片 _project_notches 先例；方向不同——非外法向投影，
    而是文档指定的角点邻边走向）：

    下顶点沿**腰头宽线**（端封边方向）交下口缝边线；上顶点沿**腰头线**
    （上口切向）交端头缝边线；后中沿**原点垂线**（后中宽度方向 = 下口线
    起端法向）交下口缝边线。载体为局部 sheet 净样几何（角点/切向），
    缩水比例由 _sa_crossing 内仿射变换施加，与 cutter 缩水->缝边顺序一致。
    """
    o = local.options
    sa = o.waistband_seam_allowances
    right_end = local.line("wb.right_end")
    left_end = local.line("wb.left_end")
    bottom_right = local.sheet.get("wb.bottom_right").geom
    top_right = local.sheet.get("wb.top_right").geom
    # 左端相邻腰头线/下口线段：fly>0 取搭门段；fly=0 搭门段零长（切向退化，
    # 装配时已滤除），退回左半本体同点相接端（bottom_left 起端 / top_left 末端）
    if o.waistband_fly_extension > 1e-9:
        top_line = local.sheet.get("wb.top_fly").geom
        bottom_line = local.sheet.get("wb.bottom_fly").geom
        t_top, t_bottom = _dir(top_line, True), _dir(bottom_line, False)
    else:
        t_top = _dir(local.sheet.get("wb.top_left").geom, True)
        t_bottom = _dir(local.sheet.get("wb.bottom_left").geom, False)
    t_back = _dir(bottom_right, False)            # 下口线后中起端切向（水平）
    gross = (
        # 后中：原点垂线（起端切向法向）∩ 下口缝边
        _sa_crossing(Point(0, 0), t_back.perpendicular(), t_back,
                     sa.bottom, sx, sy),
        # 右下顶点：宽线（right_end 走向）∩ 下口缝边（bottom_right 末端切向）
        _sa_crossing(right_end.a, _dir(right_end, False),
                     _dir(bottom_right, True), sa.bottom, sx, sy),
        # 右上顶点：腰头线（top_right 起端切向）∩ 右端缝边（right_end 走向）
        _sa_crossing(right_end.b, _dir(top_right, False),
                     _dir(right_end, False), sa.right_end, sx, sy),
        # 左上顶点：腰头线（top_fly 末端/top_left 末端切向）∩ 左端缝边
        _sa_crossing(left_end.a, t_top, _dir(left_end, False),
                     sa.left_end, sx, sy),
        # 左下顶点：宽线（left_end 走向）∩ 下口缝边（bottom_fly 起/bottom_left 起）
        _sa_crossing(left_end.b, _dir(left_end, False), t_bottom,
                     sa.bottom, sx, sy),
    )
    return piece.with_gross(
        piece.gross_polygon, gross,
        piece.notes + ("刀口：后中/四角净线交缝边位 ×5（腰头裁片.md §四.2 v0.4）",))


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
    # 四角刀口换算至缝边位（§四.2 v0.4）：缝边交点须在缩水后几何上求取，
    # 故在缩水->缝边两段之后整体替换毛样刀口
    piece = _project_corner_notches(piece, local, 1.0 + x_rate, 1.0 + y_rate)
    return piece, local
