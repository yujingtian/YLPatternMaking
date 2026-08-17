"""腰头裁片绘制步骤（腰头裁片.md §三、§四）。

在独立 DraftSheet 局部坐标系中绘制（原点 O=后中，Y 向下，X 向右）。
半片置于右侧（x>0，后中->前中），waistband_full_piece=True 时镜像至左侧 +
左端外延门襟搭门量。步骤签名 (ctx, spec) -> NamedElement -- 自含裁片，
非 FlowRunner 编排（同 flows/closure.py 口径：提取长度为标量输入，不入 flow）。

数值计算走 draft.curves / geometry，经验常数读 PatternOptions。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..draft import DraftContext, NamedCurve, NamedLine, NamedPoint
from ..draft import curves
from ..geometry import CubicBezier, LineSegment, Point, Vector
from ..params import WaistbandGrain, WaistbandType


@dataclass(frozen=True)
class WaistbandSpec:
    """腰头净长提取结果（代数求和，腰头裁片.md §三）。

    省宽仅作长度扣减；刀口不随净长提取（§四.2 v0.4：仅后中对位 + 两端
    边界，中段不打省位/侧缝对位刀口），由 draw_wb_notches 在净样端点定位。
    """
    l_front: float                              # 前片净长（扣前省）
    l_back: float                               # 后片净长（扣后省）
    l_half: float                               # 半片总净长 = l_front + l_back
    computed_drop: float                        # 弯腰头弧深（自动推算或用户覆盖；直腰头=0；曲线向下凸呈 ∪）


_STEP = "draw_waistband"


def _is_curved(o) -> bool:
    return o.waistband_type is WaistbandType.CURVED


def _bottom_geom(o, drop: float, l_half: float) -> CubicBezier | LineSegment:
    """半片下口线（后中(0,0) -> 前中，弧长 = l_half）。

    drop 来自 spec.computed_drop（侧缝夹角自动推算或用户手动覆盖，§四.分支B）。
    """
    if _is_curved(o):
        return curves.waistband_curve(l_half, drop)
    return LineSegment(Point(0, 0), Point(l_half, 0))


def _end_tangent(geom: CubicBezier | LineSegment, at_front: bool) -> Vector:
    """下口线端点的单位切线（沿 P0->P3 走向）。

    at_front=True 取末端（前中）、False 取首端（后中）。直线切向处处相同。
    用于搭门沿切线外延、封边沿法向封闭时取端点切向。
    """
    if isinstance(geom, LineSegment):
        v = geom.b - geom.a
    else:
        v = geom.tangent_at(1.0 if at_front else 0.0)
    return v.normalized() if v.length > 0 else Vector(1.0, 0.0)


def _up_normal(geom: CubicBezier | LineSegment, at_front: bool) -> Vector:
    """端点处指向腰头一侧（−Y）的单位法向。

    = 端点切线逆时针转 90° 后取 dy<0 者（下口线 y≤0，上口在其上方）。
    直腰头两端皆退化为 (0,-1)。
    """
    n = _end_tangent(geom, at_front).perpendicular()
    return n.scale(-1) if n.dy > 0 else n


def _top_geom(bot: CubicBezier | LineSegment, W: float
              ) -> CubicBezier | LineSegment:
    """上口线 = 下口线沿端点上方法向偏移 W（腰头裁片.md §四.分支B 真法向 offset）。

    P0/P1 按后中法向、P2/P3 按前中法向偏移——端点切线 (P1−P0)/(P3−P2) 逐点保留，
    故上下口在两端切线严格平行，封边沿法向时端点成直角；中段为真法向 offset 的
    贝塞尔近似。直腰头两端法向皆 (0,−1)，退化为整体竖直平移 W（=原平移行为）。
    """
    n_back = _up_normal(bot, at_front=False)
    n_front = _up_normal(bot, at_front=True)
    if isinstance(bot, LineSegment):
        return LineSegment(bot.a + n_back.scale(W), bot.b + n_front.scale(W))
    return CubicBezier(bot.p0 + n_back.scale(W), bot.p1 + n_back.scale(W),
                       bot.p2 + n_front.scale(W), bot.p3 + n_front.scale(W))


def _reverse(geom: CubicBezier | LineSegment) -> CubicBezier | LineSegment:
    """几何体反向（a->b 变 b->a / P0P1P2P3 变 P3P2P1P0）。"""
    if isinstance(geom, LineSegment):
        return LineSegment(geom.b, geom.a)
    return CubicBezier(geom.p3, geom.p2, geom.p1, geom.p0)


def _mirror_x(geom: CubicBezier | LineSegment) -> CubicBezier | LineSegment:
    """几何体沿 x=0 镜像（x 取负，y 不变）。"""
    if isinstance(geom, LineSegment):
        return LineSegment(Point(-geom.a.x, geom.a.y),
                           Point(-geom.b.x, geom.b.y))
    return CubicBezier(Point(-geom.p0.x, geom.p0.y),
                       Point(-geom.p1.x, geom.p1.y),
                       Point(-geom.p2.x, geom.p2.y),
                       Point(-geom.p3.x, geom.p3.y))


# ---- 半片基础轮廓 ----

def draw_wb_bottom(ctx: DraftContext, spec: WaistbandSpec) -> NamedCurve | NamedLine:
    """下口线半片（后中(0,0)->前中，§四）：直=直线、弯=`waistband_curve`。
    同时上版镜像左半片 `wb.bottom_left` 与门襟搭门延伸 `wb.bottom_fly`
    （搭门沿左前中切线外延，与下口线顺势顺滑相接）。"""
    o = ctx.options
    bot = _bottom_geom(o, spec.computed_drop, spec.l_half)
    fly = o.waistband_fly_extension
    # 右前中端点（右半片末端）
    front = bot.b if isinstance(bot, LineSegment) else bot.p3
    # 左半片自然镜像（后中(0,0)->左前中）；逆时针走向需反向（左前中->后中）
    bot_mirror = _mirror_x(bot)
    left_front = (bot_mirror.b if isinstance(bot_mirror, LineSegment)
                  else bot_mirror.p3)
    # 搭门沿左前中处下口切线外延（曲线顺势外伸，弯腰头随弧端斜出、直腰头水平）
    t_out = _end_tangent(bot_mirror, at_front=True)
    fly_end = left_front + t_out.scale(fly)
    # 逆时针：bottom_fly 外端->左前中（沿切线内收），bottom_left 左前中->后中
    bot_fly = LineSegment(fly_end, left_front)
    bot_left = _reverse(bot_mirror)

    ctx.add_point("wb.back_center", Point(0, 0), step=_STEP,
                  basis="腰头局部坐标系原点=后中（腰头裁片.md §四）",
                  label="后中O")
    ctx.add_point("wb.front_center", front, step=_STEP,
                  basis=f"下口线前中端（弧长 {spec.l_half:.2f}）", label="前中")
    _add_edge(ctx, "wb.bottom_right", bot, "bottom",
              f"下口线右半片（后中->前中，弧长 {spec.l_half:.2f}）")
    _add_edge(ctx, "wb.bottom_left", bot_left, "bottom",
              "下口线左半片（左前中->后中，后中轴镜像）")
    _add_edge(ctx, "wb.bottom_fly", bot_fly, "bottom",
              f"下口线门襟搭门延伸（沿左前中切线外延 {fly}，外端->左前中）")
    return ctx.sheet.get("wb.bottom_right")


def draw_wb_top(ctx: DraftContext, spec: WaistbandSpec) -> NamedCurve | NamedLine:
    """上口线（下口沿端点法向偏移 W，§四.分支B）。
    右半片 `wb.top_right`（前中->后中，逆时针走向）、左半镜像、搭门沿切线延伸。"""
    o = ctx.options
    W = o.waistband_width
    fly = o.waistband_fly_extension
    bot = _bottom_geom(o, spec.computed_drop, spec.l_half)
    top = _top_geom(bot, W)                      # 沿端点法向偏移 W（两端切线保留）
    # 逆时针走向：右半上口 前中->后中（左行）= 反向；左半 后中->左前中（左行）= 镜像
    top_right = _reverse(top)
    top_mirror = _mirror_x(top)
    top_left = top_mirror
    left_front = (top_mirror.b if isinstance(top_mirror, LineSegment)
                  else top_mirror.p3)
    # 搭门沿左前中处上口切线外延（与下口搭门同向、随弧端斜出）
    t_out = _end_tangent(top_mirror, at_front=True)
    fly_top = left_front + t_out.scale(fly)
    top_fly = LineSegment(left_front, fly_top)

    _add_edge(ctx, "wb.top_right", top_right, "top",
              f"上口线右半片（下口沿法向偏移 {W}，前中->后中）")
    _add_edge(ctx, "wb.top_left", top_left, "top", "上口线左半片（后中->左前中，镜像）")
    _add_edge(ctx, "wb.top_fly", top_fly, "top",
              f"上口线门襟搭门延伸（沿左前中切线外延 {fly}，左前中->外端）")
    return ctx.sheet.get("wb.top_right")


def draw_wb_ends(ctx: DraftContext, spec: WaistbandSpec) -> NamedLine:
    """左右端封边（§四，沿端点法向封闭——与上下口切线成直角）。

    右端=前中（下口前中端 -> 上口前中端）、左端=搭门外端（上外端 -> 下外端）。
    封边向量即上下口同侧端点之差，因上口沿法向偏移故天然落在端点法向上；
    搭门外端=左前中沿端点切线外延 fly（与搭门边成直角）。
    """
    o = ctx.options
    W = o.waistband_width
    fly = o.waistband_fly_extension
    bot = _bottom_geom(o, spec.computed_drop, spec.l_half)
    top = _top_geom(bot, W)
    # 右端：下口前中 -> 上口前中（沿前中法向，直角封闭）
    front = bot.b if isinstance(bot, LineSegment) else bot.p3
    front_top = top.b if isinstance(top, LineSegment) else top.p3
    right_end = LineSegment(front, front_top)
    # 左端：搭门外端 上->下（沿左前中法向，直角封闭）
    bot_mirror = _mirror_x(bot)
    top_mirror = _mirror_x(top)
    left_front = (bot_mirror.b if isinstance(bot_mirror, LineSegment)
                  else bot_mirror.p3)
    left_front_top = (top_mirror.b if isinstance(top_mirror, LineSegment)
                      else top_mirror.p3)
    fly_bottom = left_front + _end_tangent(bot_mirror, at_front=True).scale(fly)
    fly_top = left_front_top + _end_tangent(top_mirror, at_front=True).scale(fly)
    left_end = LineSegment(fly_top, fly_bottom)
    _add_edge(ctx, "wb.right_end", right_end, "right_end", "右端封边（沿前中法向，前中）")
    _add_edge(ctx, "wb.left_end", left_end, "left_end", "左端封边（沿左前中法向，搭门外端）")
    return ctx.sheet.get("wb.right_end")


# ---- 刀口（§四.2） ----

def draw_wb_notches(ctx: DraftContext, spec: WaistbandSpec) -> NamedPoint | None:
    """腰头刀口净样位（§四.2 v0.4）：后中对位 + 左右两端上下顶点，中段不打
    省位/侧缝对位刀口。

    版上标记净样角点（后中 O、左/右端各下顶点+上顶点）；裁片毛样刀口位由
    flows/waistband_flow 换算至缝边——下顶点沿腰头宽线交下口缝边、上顶点
    沿腰头线交端头缝边（§四.2.2/§四.2.3「沿着…和缝边相交的地方」）。
    刀口附垂直短记号线（下顶点朝下、上顶点朝上，均朝净样外侧 0.4cm）。
    """
    o = ctx.options
    W = o.waistband_width
    fly = o.waistband_fly_extension
    bot = _bottom_geom(o, spec.computed_drop, spec.l_half)
    top = _top_geom(bot, W)
    front = bot.b if isinstance(bot, LineSegment) else bot.p3
    front_top = top.b if isinstance(top, LineSegment) else top.p3
    bot_mirror = _mirror_x(bot)
    top_mirror = _mirror_x(top)
    left_front = (bot_mirror.b if isinstance(bot_mirror, LineSegment)
                  else bot_mirror.p3)
    left_front_top = (top_mirror.b if isinstance(top_mirror, LineSegment)
                      else top_mirror.p3)
    fly_bottom = left_front + _end_tangent(bot_mirror, at_front=True).scale(fly)
    fly_top = left_front_top + _end_tangent(top_mirror, at_front=True).scale(fly)

    positions: list[tuple[str, Point, float, str]] = [
        ("back_center", Point(0, 0), 0.4,
         "后中对位刀口（净样位；毛样位=原点垂线∩下口缝边，§四.2.1）"),
        ("left_bottom", fly_bottom, 0.4,
         "左下顶点刀口（净样位；毛样位=腰头宽线∩下口缝边，§四.2.2）"),
        ("left_top", fly_top, -0.4,
         "左上顶点刀口（净样位；毛样位=腰头线∩左端缝边，§四.2.2）"),
        ("right_bottom", front, 0.4,
         "右下顶点刀口（净样位；毛样位=腰头宽线∩下口缝边，§四.2.3）"),
        ("right_top", front_top, -0.4,
         "右上顶点刀口（净样位；毛样位=腰头线∩右端缝边，§四.2.3）"),
    ]
    last: NamedPoint | None = None
    for name, p, tick_dy, note in positions:
        last = ctx.add_point(f"wb.notch_{name}", p, step=_STEP,
                             basis=f"{note}（腰头裁片.md §四.2 v0.4）",
                             label=f"{name}刀口")
        ctx.add_line(f"wb.notch_{name}_tick",
                     LineSegment(p, Point(p.x, p.y + tick_dy)),
                     step=_STEP, basis="刀口垂直短记号", role="struct")
    return last


def draw_wb_grain(ctx: DraftContext, spec: WaistbandSpec) -> NamedLine:
    """丝缕线（经向，双向箭头，§五.2 缩水经向基准）。

    方向由 ``waistband_grain`` 决定：WIDTH（默认）宽向=经 -> 竖向（沿裤长 Y）；
    LENGTH 长向=经 -> 水平（沿腰头周向 X）。经向是面料属性，与前后片裤中线=裤长一致。
    """
    o = ctx.options
    W = o.waistband_width
    fly = o.waistband_fly_extension
    bot = _bottom_geom(o, spec.computed_drop, spec.l_half)
    front = bot.b if isinstance(bot, LineSegment) else bot.p3
    x_right = front.x
    x_left = -front.x - fly
    if o.waistband_grain is WaistbandGrain.LENGTH:
        # 长向=经：水平丝缕线（沿 X），长向留 margin
        margin = 2.0
        y_mid = -W / 2
        seg = LineSegment(Point(x_left + margin, y_mid),
                          Point(x_right - margin, y_mid))
        basis = "丝缕线：长向=经向（waistband_grain=LENGTH，缩水 warp 沿 X）"
    else:
        # 宽向=经（默认）：竖向丝缕线（沿 Y，=裤长方向），宽向留小 margin（W≈4 远小于长向）
        margin = 0.5
        x_mid = (x_left + x_right) / 2
        seg = LineSegment(Point(x_mid, -W + margin), Point(x_mid, -margin))
        basis = "丝缕线：宽向=经向（waistband_grain=WIDTH，缩水 warp 沿 Y）"
    return ctx.add_line("wb.grain", seg, step=_STEP,
                        basis=basis, label="丝缕线", role="struct")


# ---- 辅助 ----

def _add_edge(ctx: DraftContext, name: str,
              geom: CubicBezier | LineSegment, role_name: str,
              basis: str) -> None:
    """上版一条裁片边（曲线/直线），role_name 为语义边名（存 basis 前缀）。"""
    if isinstance(geom, CubicBezier):
        ctx.add_curve(name, geom, step=_STEP,
                      basis=f"[{role_name}] {basis}", label=name)
    else:
        ctx.add_line(name, geom, step=_STEP,
                     basis=f"[{role_name}] {basis}", label=name, role="struct")


# 裁片边装配顺序（逆时针，自后中(0,0)起；语义边名用于缝边外扩）
EDGE_ORDER: tuple[tuple[str, str], ...] = (
    ("wb.bottom_right", "bottom"),
    ("wb.right_end", "right_end"),
    ("wb.top_right", "top"),
    ("wb.top_left", "top"),
    ("wb.top_fly", "top"),
    ("wb.left_end", "left_end"),
    ("wb.bottom_fly", "bottom"),
    ("wb.bottom_left", "bottom"),
)
