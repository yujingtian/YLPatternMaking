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
from ..geometry import CubicBezier, LineSegment, Point
from ..params import WaistbandType


@dataclass(frozen=True)
class WaistbandSpec:
    """腰头净长与刀口位（代数求和，腰头裁片.md §三）。"""
    l_front: float                              # 前片净长（扣前省）
    l_back: float                               # 后片净长（扣后省）
    l_half: float                               # 半片总净长 = l_front + l_back
    computed_drop: float                        # 弯腰头弧深（自动推算或用户覆盖；直腰头=0；曲线向下凸呈 ∪）
    side_notch: float                           # 侧缝刀口（自后中弧长 = l_back）
    back_dart_notches: tuple[float, ...]        # 后省刀口（自后中弧长，已扣前序省宽）
    front_dart_notch: float | None              # 前省刀口（自后中弧长 = l_back + p1_dist）
    has_front_dart: bool
    has_back_dart: bool


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


def _translate_y(geom: CubicBezier | LineSegment, dy: float
                 ) -> CubicBezier | LineSegment:
    """几何体整体 y 平移 dy（上口线 = 下口线上移 W 用）。"""
    if isinstance(geom, LineSegment):
        return LineSegment(Point(geom.a.x, geom.a.y + dy),
                           Point(geom.b.x, geom.b.y + dy))
    return CubicBezier(Point(geom.p0.x, geom.p0.y + dy),
                       Point(geom.p1.x, geom.p1.y + dy),
                       Point(geom.p2.x, geom.p2.y + dy),
                       Point(geom.p3.x, geom.p3.y + dy))


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


def _point_at_arc(geom: CubicBezier | LineSegment, s: float,
                  total: float) -> Point:
    """下口线上自后中(0,0)起弧长 s 处的点。"""
    if isinstance(geom, CubicBezier):
        return geom.point_at_length(s)
    return geom.a.lerp(geom.b, s / total if total else 0.0)


# ---- 半片基础轮廓 ----

def draw_wb_bottom(ctx: DraftContext, spec: WaistbandSpec) -> NamedCurve | NamedLine:
    """下口线半片（后中(0,0)->前中，§四）：直=直线、弯=`waistband_curve`。
    同时上版镜像左半片 `wb.bottom_left` 与门襟搭门延伸 `wb.bottom_fly`。"""
    o = ctx.options
    W = o.waistband_width
    bot = _bottom_geom(o, spec.computed_drop, spec.l_half)
    fly = o.waistband_fly_extension
    # 右前中端点（右半片末端）
    front = bot.b if isinstance(bot, LineSegment) else bot.p3
    # 左半片自然镜像（后中(0,0)->左前中(-X,drop)）；逆时针走向需反向（左前中->后中）
    bot_mirror = _mirror_x(bot)
    left_front = (bot_mirror.b if isinstance(bot_mirror, LineSegment)
                  else bot_mirror.p3)
    fly_end = Point(left_front.x - fly, left_front.y)
    # 逆时针：bottom_fly 外端->左前中（右行），bottom_left 左前中->后中（右行）
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
              f"下口线门襟搭门延伸（外延 {fly}，外端->左前中）")
    return ctx.sheet.get("wb.bottom_right")


def draw_wb_top(ctx: DraftContext, spec: WaistbandSpec) -> NamedCurve | NamedLine:
    """上口线（下口线上移 W，§四.分支B 法向偏移近似为平移）。
    右半片 `wb.top_right`（前中->后中，逆时针走向）、左半镜像、搭门延伸。"""
    o = ctx.options
    W = o.waistband_width
    fly = o.waistband_fly_extension
    bot = _bottom_geom(o, spec.computed_drop, spec.l_half)
    top = _translate_y(bot, -W)                 # 上移 W：(0,-W)->(X,drop-W)
    # 逆时针走向：右半上口 前中->后中（左行）= 反向；左半 后中->左前中（左行）= 镜像
    top_right = _reverse(top)
    top_mirror = _mirror_x(top)                 # (0,-W)->(-X,drop-W)
    top_left = top_mirror
    left_front = (top_mirror.b if isinstance(top_mirror, LineSegment)
                  else top_mirror.p3)
    top_fly = LineSegment(left_front, Point(left_front.x - fly, left_front.y))

    _add_edge(ctx, "wb.top_right", top_right, "top",
              f"上口线右半片（下口上移 {W}，前中->后中）")
    _add_edge(ctx, "wb.top_left", top_left, "top", "上口线左半片（后中->左前中，镜像）")
    _add_edge(ctx, "wb.top_fly", top_fly, "top",
              f"上口线门襟搭门延伸（外延 {fly}，左前中->外端）")
    return ctx.sheet.get("wb.top_right")


def draw_wb_ends(ctx: DraftContext, spec: WaistbandSpec) -> NamedLine:
    """左右端竖直封边（§四 右端垂直封闭）。右端=前中、左端=搭门外端。"""
    o = ctx.options
    W = o.waistband_width
    fly = o.waistband_fly_extension
    bot = _bottom_geom(o, spec.computed_drop, spec.l_half)
    front = bot.b if isinstance(bot, LineSegment) else bot.p3
    left_front = (_mirror_x(bot).b if isinstance(bot, LineSegment)
                  else _mirror_x(bot).p3)
    left_end_pt = Point(left_front.x - fly, left_front.y)
    right_end = LineSegment(front, Point(front.x, front.y - W))
    left_end = LineSegment(Point(left_end_pt.x, left_end_pt.y - W), left_end_pt)
    _add_edge(ctx, "wb.right_end", right_end, "right_end", "右端竖直封边（前中）")
    _add_edge(ctx, "wb.left_end", left_end, "left_end", "左端竖直封边（搭门外端）")
    return ctx.sheet.get("wb.right_end")


# ---- 刀口（§三.2） ----

def draw_wb_notches(ctx: DraftContext, spec: WaistbandSpec) -> NamedPoint | None:
    """下口线刀口（自后中沿弧长，单刀口；full_piece 左右镜像各打一个）。

    后省对位点 / 侧缝对位点 / 前省对位点；刀口为下口线上的点，附垂直短记号线。
    """
    o = ctx.options
    bot = _bottom_geom(o, spec.computed_drop, spec.l_half)
    positions: list[tuple[str, float]] = []
    for i, s in enumerate(spec.back_dart_notches, 1):
        positions.append((f"back_dart{i}", s))
    positions.append(("side", spec.side_notch))
    if spec.front_dart_notch is not None:
        positions.append(("front_dart", spec.front_dart_notch))

    last: NamedPoint | None = None
    for name, s in positions:
        p = _point_at_arc(bot, s, spec.l_half)
        p_mirror = Point(-p.x, p.y)             # 左半镜像
        last = ctx.add_point(f"wb.notch_{name}", p, step=_STEP,
                             basis=f"下口线自后中弧长 {s:.2f} 处刀口（腰头裁片.md §三.2）",
                             label=f"{name}刀口")
        ctx.add_point(f"wb.notch_{name}_mirror", p_mirror, step=_STEP,
                      basis=f"左半镜像刀口（弧长 −{s:.2f}）",
                      label=f"{name}刀口镜像")
        # 垂直短记号线（向下 0.4cm，示意刀口）
        ctx.add_line(f"wb.notch_{name}_tick", LineSegment(p, Point(p.x, p.y + 0.4)),
                     step=_STEP, basis="刀口垂直短记号", role="struct")
    return last


def draw_wb_grain(ctx: DraftContext, spec: WaistbandSpec) -> NamedLine:
    """丝缕线（腰头长向=经向，水平双向箭头，§五.2 缩水经向基准）。"""
    o = ctx.options
    W = o.waistband_width
    fly = o.waistband_fly_extension
    bot = _bottom_geom(o, spec.computed_drop, spec.l_half)
    front = bot.b if isinstance(bot, LineSegment) else bot.p3
    x_right = front.x
    x_left = -front.x - fly
    margin = 2.0
    y_mid = -W / 2
    return ctx.add_line("wb.grain",
                        LineSegment(Point(x_left + margin, y_mid),
                                    Point(x_right - margin, y_mid)),
                        step=_STEP,
                        basis="丝缕线：腰头长向=经向（缩水 warp 基准）",
                        label="丝缕线", role="struct")


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
