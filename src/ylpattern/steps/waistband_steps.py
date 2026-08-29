"""腰头裁片绘制步骤（腰头裁片.md §三、§四；v0.9 真拼合 + 整根均匀圆弧）。

在独立 DraftSheet 局部坐标系中绘制（原点 O=后中，+Y 朝下，X 向右）。
直腰头：代数求和矩形（单几何，路径零改动）。弯腰头：下口线 = 前后腰弧**真拼合
链**（flows/waistband_flow 闭省 + 侧缝跨缝反射拼合 + 局部系化）重整成的
**一条均匀圆弧**（curves.uniform_arc_cubic，起端=后中原点、起端切向水平
（后中镜像 C1/C2）、弧长=链净长（缝制硬约束）、总转角=链末切向角
（「保持拼合的弯曲」——sag/裆深经它传入））——曲率全弧均匀，后段/前段
同弯度、无集中肘弯，侧缝处不再有夹角；端点位置为派生量（独立带状裁片
端点无装配语义）。上口沿端点法向偏移 W（端切向保持）。半片置于
右侧（x>0，后中->前中），waistband_full_piece=True 时镜像至左侧 + 左端外延
门襟搭门量。步骤签名 (ctx, spec) -> NamedElement——自含裁片，非 FlowRunner
编排（同 flows/closure.py 口径：提取为标量/几何输入，不入 flow）。

弯/直腰头边数同为 8（下口右/左 + 上口右/左 + 两端封边 + 两搭门），段数不随
省数变化，同一 options 跨码恒定（推码跨码对应，多码 DXF 不漂移边数）。
数值计算走 draft.curves / geometry，经验常数读 PatternOptions。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..draft import DraftContext, NamedCurve, NamedLine, NamedPoint
from ..geometry import CubicBezier, LineSegment, Point, Vector
from ..params import WaistbandGrain


@dataclass(frozen=True)
class WaistbandSpec:
    """腰头净长与拼合几何提取结果（腰头裁片.md §三/§四.分支B v0.9）。

    直腰头：bottom_arc 为 None，l_* 为代数求和（省宽仅扣长）；弯腰头：
    l_* 为闭省后拼合链实长（报表/丝缕用），bottom_arc 为整根均匀圆弧
    （局部系，t=0 后中原点 -> t=1 前中；弧长=l_half 精确、总转角=链末
    切向角）。刀口不随净长提取（§四.2 v0.4：仅后中对位 +
    两端边界，中段不打省位/侧缝对位刀口）。
    """
    l_front: float                              # 前片净长（直=扣前省；弯=闭省后链实长）
    l_back: float                               # 后片净长（直=扣后省；弯=闭省后链实长）
    l_half: float                               # 半片总净长 = l_front + l_back
    bottom_arc: CubicBezier | None = None       # 弯腰头下口整根均匀圆弧（局部系）


_STEP = "draw_waistband"


def _is_curved(spec: WaistbandSpec) -> bool:
    return spec.bottom_arc is not None


def _start_pt(g: CubicBezier | LineSegment) -> Point:
    return g.a if isinstance(g, LineSegment) else g.p0


def _end_pt(g: CubicBezier | LineSegment) -> Point:
    return g.b if isinstance(g, LineSegment) else g.p3


def _bottom_right_geom(spec: WaistbandSpec) -> CubicBezier | LineSegment:
    """半片下口线（后中(0,0) -> 前中）：直=直线；弯=整根均匀圆弧。"""
    return spec.bottom_arc if _is_curved(spec) else _bottom_geom(spec.l_half)


def _bottom_geom(l_half: float) -> LineSegment:
    """直腰头半片下口线（后中(0,0) -> 前中，直线）。"""
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
    """上口线 = 下口线沿端点上方法向偏移 W。

    直线退化为整体竖直平移；曲线仅两端控制点各用端法向平移——端切向与
    下口严格平行（平移性质），端部宽度 W 沿法向量取。
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
    """下口线半片（后中(0,0)->前中，§四）：直=直线；弯=整根均匀圆弧。
    同时上版镜像左半片（左前中->后中）与门襟搭门延伸（沿左前中切线外延）。"""
    o = ctx.options
    fly = o.waistband_fly_extension
    right = _bottom_right_geom(spec)
    front = _end_pt(right)
    # 左半：镜像后反向（左前中->后中，逆时针走向）
    left = _reverse(_mirror_x(right))
    # 搭门沿左前中处下口切线外延（曲线顺势外伸，弯腰头随弧端斜出、直腰头水平）
    m = _mirror_x(right)
    left_front = _end_pt(m)
    t_out = _end_tangent(m, at_front=True)
    fly_end = left_front + t_out.scale(fly)
    bot_fly = LineSegment(fly_end, left_front)

    ctx.add_point("wb.back_center", Point(0, 0), step=_STEP,
                  basis="腰头局部坐标系原点=后中（腰头裁片.md §四）",
                  label="后中O")
    ctx.add_point("wb.front_center", front, step=_STEP,
                  basis=f"下口线前中端（净长 {spec.l_half:.2f}）", label="前中")
    _add_edge(ctx, "wb.bottom_right", right, "bottom",
              "下口线右半片（真拼合整根均匀弧，后中->前中方向）"
              if _is_curved(spec) else
              f"下口线右半片（后中->前中，长 {spec.l_half:.2f}）")
    _add_edge(ctx, "wb.bottom_left", left, "bottom",
              "下口线左半片（后中轴镜像，左前中->后中）")
    _add_edge(ctx, "wb.bottom_fly", bot_fly, "bottom",
              f"下口线门襟搭门延伸（沿左前中切线外延 {fly}，外端->左前中）")
    return ctx.sheet.get("wb.bottom_right")


def draw_wb_top(ctx: DraftContext, spec: WaistbandSpec) -> NamedCurve | NamedLine:
    """上口线（§四）：直=法向偏移直线；弯=拟合弧端法向偏移（端切向平行下口）。

    右半上口 前中->后中（逆时针）、左半镜像（后中->左前中）、搭门沿切线延伸。
    """
    o = ctx.options
    W = o.waistband_width
    fly = o.waistband_fly_extension
    top = _top_geom(_bottom_right_geom(spec), W)
    top_right = _reverse(top)
    top_left = _mirror_x(top)
    left_front_top = _end_pt(top_left)
    # 搭门沿左前中处上口切线外延（与下口搭门同向、随弧端斜出）
    t_out = _end_tangent(top_left, at_front=True)
    fly_top = left_front_top + t_out.scale(fly)
    top_fly = LineSegment(left_front_top, fly_top)

    _add_edge(ctx, "wb.top_right", top_right, "top",
              "上口线右半片（前中->后中，端法向偏移 W）")
    _add_edge(ctx, "wb.top_left", top_left, "top",
              "上口线左半片（后中->左前中，镜像）")
    _add_edge(ctx, "wb.top_fly", top_fly, "top",
              f"上口线门襟搭门延伸（沿左前中切线外延 {fly}，左前中->外端）")
    return ctx.sheet.get("wb.top_right")


def draw_wb_ends(ctx: DraftContext, spec: WaistbandSpec) -> NamedLine:
    """左右端封边（§四，沿端点法向封闭——与上下口切线成直角）。

    右端=前中（下口前中端 -> 上口前中端）、左端=搭门外端（上外端 -> 下外端）。
    """
    right_end = LineSegment(ctx.point("wb.front_center"),
                            _top_front_point(ctx))
    left_end = LineSegment(_end_pt(ctx.sheet.get("wb.top_fly").geom),
                           _start_pt(ctx.sheet.get("wb.bottom_fly").geom))
    _add_edge(ctx, "wb.right_end", right_end, "right_end",
              "右端封边（沿前中法向，前中）")
    _add_edge(ctx, "wb.left_end", left_end, "left_end",
              "左端封边（沿左前中法向，搭门外端）")
    return ctx.sheet.get("wb.right_end")


def _top_front_point(ctx: DraftContext) -> Point:
    """上口前中端（top_right 反向序起端）。"""
    return _start_pt(ctx.sheet.get("wb.top_right").geom)


# ---- 刀口（§四.2） ----

def draw_wb_notches(ctx: DraftContext, spec: WaistbandSpec) -> NamedPoint | None:
    """腰头刀口净样位（§四.2 v0.4）：后中对位 + 左右两端上下顶点，中段不打
    省位/侧缝对位刀口。

    版上标记净样角点（后中 O、左/右端各下顶点+上顶点）；裁片毛样刀口位由
    flows/waistband_flow 换算至缝边——下顶点沿腰头宽线交下口缝边、上顶点
    沿腰头线交端头缝边（§四.2.2/§四.2.3「沿着…和缝边相交的地方」）。
    刀口附垂直短记号线（下顶点朝下、上顶点朝上，均朝净样外侧 0.4cm）。
    """
    front = ctx.point("wb.front_center")
    front_top = _top_front_point(ctx)
    fly_bottom = _start_pt(ctx.sheet.get("wb.bottom_fly").geom)
    fly_top = _end_pt(ctx.sheet.get("wb.top_fly").geom)

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


def _bottom_y_at(ctx: DraftContext, spec: WaistbandSpec, x_tgt: float) -> float:
    """下口右半线上 x 最近 x_tgt 处的 y（丝缕线定位用；直腰头恒 0）。"""
    if not _is_curved(spec):
        return 0.0
    best_y, best_d = 0.0, float("inf")
    for p in ctx.sheet.get("wb.bottom_right").geom.sample(33):
        d = abs(p.x - x_tgt)
        if d < best_d:
            best_d, best_y = d, p.y
    return best_y


def draw_wb_grain(ctx: DraftContext, spec: WaistbandSpec) -> NamedLine:
    """丝缕线（经向，双向箭头，§五.2 缩水经向基准）。

    方向由 ``waistband_grain`` 决定：WIDTH（默认）宽向=经 -> 竖向（沿裤长 Y）；
    LENGTH 长向=经 -> 水平（沿腰头周向 X）。经向是面料属性，与前后片裤中线=裤长一致。
    弯腰头弧中段 y 随拼合弧起伏，丝缕线取 x 中点处下口 y 定位（贴弧不越界）。
    """
    o = ctx.options
    W = o.waistband_width
    fly = o.waistband_fly_extension
    front = ctx.point("wb.front_center")
    x_right = front.x
    x_left = -front.x - fly
    if o.waistband_grain is WaistbandGrain.LENGTH:
        # 长向=经：水平丝缕线（沿 X），长向留 margin
        margin = 2.0
        y_mid = _bottom_y_at(ctx, spec, 0.0) - W / 2
        seg = LineSegment(Point(x_left + margin, y_mid),
                          Point(x_right - margin, y_mid))
        basis = "丝缕线：长向=经向（waistband_grain=LENGTH，缩水 warp 沿 X）"
    else:
        # 宽向=经（默认）：竖向丝缕线（沿 Y，=裤长方向），宽向留小 margin（W≈4 远小于长向）
        margin = 0.5
        x_mid = (x_left + x_right) / 2
        y0 = _bottom_y_at(ctx, spec, x_mid)
        seg = LineSegment(Point(x_mid, y0 - W + margin), Point(x_mid, y0 - margin))
        basis = "丝缕线：宽向=经向（waistband_grain=WIDTH，缩水 warp 沿 Y）"
    return ctx.add_line("wb.grain", seg, step=_STEP,
                        basis=basis, label="丝缕线", role="struct")


# ---- 装配序（弯/直同构恒 8 项；语义边名用于缝边外扩）----

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
"""裁片净边装配顺序（逆时针，自后中(0,0)起；fly=0 时搭门段零长由装配滤除）。"""


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
