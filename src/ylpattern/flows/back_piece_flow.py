"""后片独立裁片流程：净样提取 -> 缩水 -> 缝边 -> 刀口投影（后片裁片.md）。

build_back_piece(main_ctx) 从整版 ctx 提取后片主裁片净样闭合轮廓。裁片分离
（§1）：后片独立裁片**不含腰头与机头**，沿机头下口线截断分离，取其下多边形；
上边界三形态条件矩阵：
  - A. back_yoke 开（标准牛仔）：上边 top = back.yoke_bottom_seg{i} 链
    （P0->PN，空链回退直线 P0->PN 同 yoke 口径）；后浪边自 P0、侧缝边自 PN
    取整版链后缀（量取定位与 back_yoke_steps 同式同源：两端点沿链弧长量取
    已上版，直接读点、自该点取后缀，直/弯腰头无差别）。
  - B. 无 yoke + 直腰头：上边 waist = 后腰头线弧（A -> B，弧原方向即
    cb -> side 侧），后浪/侧缝自腰头线两端点起完整链。
  - C. 无 yoke + 弯腰头：上边 waist = 后下腰头线（O' -> X'，同向），
    后浪/侧缝自下腰头两端点起（沿链再下移 W 的后缀）。
后省（back_dart 开时）：省尖低于上边界（省穿越裁片区）则边界按图提取 +
stderr 告警，省腿在裁片内部分进 marks（省量吸收主口径是 back_waist_dart
约克转移，与机头 §2.2 绕尖旋转不联动，不改变本片边界）。
缝边（§2）：BackSeamAllowances 按语义边独立缝宽；后浪浪尖（后浪弧末端 ∩
内侧缝起点）角部由 back_piece_crotch_corner 开关控制（默认开 = 镜像折角/
反折角，防缝合翻折缺角缺肉；关闭 = 尖角跟随净样轮廓，贝塞尔多项式自然
外延求交成尖，不抹圆）。缩水（§3 顺序 1~3）：先提取净样 -> 再缩水 -> 后加
缝边（缝份为绝对值不乘缩水率），主面料率 back_piece_shrinkage_*（None 回退
全局）。刀口（§4）：脚口折边 / 后中拼接 / 浪尖对位 / 口袋对位 / 膝围 + 臀围、
横裆（§5 基准点），净样刀口沿外法向投影至毛样外沿（与前片同款 flow 私有
实现，不动 cutter 公开 API）。内部线（§5）：臀围/膝围水平截断 + 毗围斜量线
1:1（横裆线不画--用户口径：毗围线即其测量基准，横裆水平线冗余；横裆高度
交点仍进 §4 刀口）+ 后贴袋顶线拷贝、贴袋上端两顶点进 drills 定位孔（§6）；
丝缕线竖向（经向 = 局部 Y，与全局纱向平行一致），均随缩水同比例变换。
自含裁片，非 FlowRunner 编排（同 build_waistband / build_yoke /
build_front_piece 口径），不在 FULL_FLOW 内。
"""

from __future__ import annotations

import sys
from collections.abc import Mapping

from ..cutter import add_seam_allowance, apply_shrinkage
from ..draft import DraftContext
from ..draft import curves
from ..geometry import CubicBezier, LineSegment, Point, Vector
from ..params import WaistbandType
from ..pieces import PatternPiece, PieceEdge


# ---------- 几何小工具（与 front_piece_flow / yoke_flow 同款自备口径）----------

def _to_local_geom(g: LineSegment | CubicBezier, origin: Point
                   ) -> LineSegment | CubicBezier:
    """主版坐标 -> 裁片局部坐标：关于过 origin 的水平线反射
    local=(x−origin.x, origin.y−y)。X 不翻（保侧缝在左、后浪在右，避免镜像）、
    Y 翻（主版 Y 向上 -> 局部 +Y 朝下，腰头在上、裤身向下），与 piece_svg 的
    Y 向下不翻转口径一致。反射反向（det=−1），由 build_back_piece 自定向
    重新正序保 shoelace<0。origin = 后浪链首顶点（有 yoke = P0；无 yoke =
    A 直腰头 / O′ 弯腰头）。"""
    def f(p: Point) -> Point:
        return Point(p.x - origin.x, origin.y - p.y)
    if isinstance(g, LineSegment):
        return LineSegment(f(g.a), f(g.b))
    return CubicBezier(f(g.p0), f(g.p1), f(g.p2), f(g.p3))


def _to_local_point(p: Point, origin: Point) -> Point:
    return Point(p.x - origin.x, origin.y - p.y)


def _reverse_geom(g: LineSegment | CubicBezier) -> LineSegment | CubicBezier:
    """反向几何：直线 a,b->b,a；三次贝塞尔 p0,p1,p2,p3->p3,p2,p1,p0（弧长不变）。"""
    if isinstance(g, LineSegment):
        return LineSegment(g.b, g.a)
    return CubicBezier(g.p3, g.p2, g.p1, g.p0)


def _geom_sample(g: LineSegment | CubicBezier, n: int = 32) -> list[Point]:
    return [g.a, g.b] if isinstance(g, LineSegment) else g.sample(n)


def _geom_length(g: LineSegment | CubicBezier) -> float:
    """几何长（LineSegment.length 为属性、CubicBezier.length() 为方法，API 不一）。"""
    return g.length if isinstance(g, LineSegment) else g.length()


def _signed_area(geoms: list[LineSegment | CubicBezier]) -> float:
    """闭合几何链的 shoelace 符号面积（cutter 外法向要求 < 0，同 yoke 口径）。"""
    pts: list[Point] = []
    for g in geoms:
        pts.extend(_geom_sample(g))
    s, n = 0.0, len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        s += a.x * b.y - b.x * a.y
    return s


def _chain_suffix(chain: list[LineSegment | CubicBezier], d: float
                  ) -> list[LineSegment | CubicBezier]:
    """自链上弧长 d 处 -> 链尾的子链（d=0 即原链）。

    首个被部分消费的段在 d 处切开取后缀（直线取中间点、贝塞尔
    bezier_subrange 保形），其后各段整体保留、之前的整段丢弃。"""
    out: list[LineSegment | CubicBezier] = []
    rem = d
    for g in chain:
        L = _geom_length(g)
        if rem >= L - 1e-9:            # 整段在起点之前，丢弃
            rem -= L
            continue
        if rem > 1e-9:                 # 起点落在本段内：切开取后缀
            if isinstance(g, LineSegment):
                p = g.a + (g.b - g.a).normalized().scale(rem)
                out.append(LineSegment(p, g.b))
            else:
                out.append(curves.bezier_subrange(g, g.t_at_length(rem), 1.0))
        else:
            out.append(g)
        rem = 0.0
    return out


def _reverse_bezier(b: CubicBezier) -> CubicBezier:
    """反向三次贝塞尔：终点 -> 起点重参数化，弧长不变（同 yoke_flow 口径）。"""
    return CubicBezier(b.p3, b.p2, b.p1, b.p0)


def _vertical_grain(net_edges: tuple[PieceEdge, ...]) -> LineSegment:
    """丝缕线：经向 = 裤长方向 = 局部 Y（§5 与全局纱向平行一致）。
    竖向贯穿裁片（bbox 中心 x，上下各留 15% 边距），同 yoke 口径。"""
    xs, ys = [], []
    for e in net_edges:
        for p in _geom_sample(e.geom):
            xs.append(p.x)
            ys.append(p.y)
    cx = (min(xs) + max(xs)) / 2
    y0, y1 = min(ys), max(ys)
    margin = (y1 - y0) * 0.15
    return LineSegment(Point(cx, y0 + margin), Point(cx, y1 - margin))


def _sa_for(name: str, sa) -> float:
    """语义边缝份（与 cutter._sa_amount 同口径的鸭子类型分派）。"""
    if isinstance(sa, Mapping):
        return float(sa.get(name, 0.0))
    return float(getattr(sa, name, 0.0))


# ---------- 净边装配（§1 三形态，主版自然 CCW 序）----------

def _yoke_bottom_chain(ctx: DraftContext) -> list[LineSegment | CubicBezier]:
    """机头下口线段链 back.yoke_bottom_seg{i}（P0->PN 有序，line/arc/bezier）。"""
    geoms: list[LineSegment | CubicBezier] = []
    i = 1
    while f"back.yoke_bottom_seg{i}" in ctx.sheet:
        geoms.append(ctx.sheet.get(f"back.yoke_bottom_seg{i}").geom)
        i += 1
    return geoms


def _net_edges(ctx: DraftContext, o) -> tuple[list[tuple[str, LineSegment
                                                          | CubicBezier]], Point]:
    """主版坐标净边装配（自然 CCW 序）：上边 -> 外侧缝（下行三段同名）->
    脚口 -> 内侧缝（上行两段同名）-> 后浪（上行曲线+斜线残段同名），闭合。

    返回 (edges, cb_top)：cb_top = 后浪链首顶点（有 yoke = P0 / 无 yoke =
    A 直腰头 / O′ 弯腰头），作局部化 origin。后浪/侧缝下行链：
      后浪 = (rise_slant, rise_curve)（A -> 臀围内缝点 -> 裆尖）；
      侧缝 = (反向髋腰弧, outseam_upper, outseam_lower)（腰端 -> 臀 -> 膝 -> 脚口）；
    自链首顶点（A/B 或 P0/PN，即上边界端点）取后缀 -- 有 yoke 时两端点由
    back_yoke_steps 沿链量取上版（弯腰头再含下移 W），读点即可；无 yoke 时
    后缀起点 = 链首（直）或链上 W 处（弯，下腰头剥离，§1 分离基准同前片）。"""
    curved = o.waistband_type is WaistbandType.CURVED
    hw = ctx.curve("back.outseam_hip_waist")            # t=0 臀 -> t=1 腰 X/B
    # 后浪/侧缝下行链
    cb_chain = [ctx.line("back.rise_slant"), ctx.curve("back.rise_curve")]
    side_chain = [_reverse_bezier(hw), ctx.curve("back.outseam_upper"),
                  ctx.curve("back.outseam_lower")]

    has_yoke = o.back_yoke and "back.yoke_cb_point" in ctx.sheet
    if has_yoke:
        # 形态 A：上边 = 机头下口线链；后浪/侧缝自 P0/PN 取后缀
        p0 = ctx.point("back.yoke_cb_point")
        pn = ctx.point("back.yoke_side_point")
        top = _yoke_bottom_chain(ctx) or [LineSegment(p0, pn)]
        edges: list[tuple[str, LineSegment | CubicBezier]] = \
            [("top", g) for g in top]
        # d_cb/d_side：自链首（A/B）沿链到 P0/PN 的弧长，与 back_yoke_steps
        # 量取口径同式同源（弯腰头再含下移 W）
        d_cb = o.waistband_width + o.back_yoke_cb_dist if curved \
            else o.back_yoke_cb_dist
        d_side = o.waistband_width + o.back_yoke_side_dist if curved \
            else o.back_yoke_side_dist
        cb_top = p0
    elif curved:
        # 形态 C：上边 = 后下腰头线（O' -> X'，弧原方向即 cb->side 侧），
        # 链自下腰头两端点起（沿链再下移 W 的后缀）
        edges = [("waist", ctx.curve("back.lower_waistline_arc"))]
        d_cb = d_side = o.waistband_width
        cb_top = ctx.point("back.lower_waist_center_point")   # O'
    else:
        # 形态 B：上边 = 后腰头线弧（A -> B，弧原方向即 cb->side 侧），
        # 链自腰头线两端点起完整
        edges = [("waist", ctx.curve("back.waistline_arc"))]
        d_cb = d_side = 0.0
        cb_top = ctx.point("back.rise_top_point")

    # 外侧缝下行（PN/X'/B -> 脚口外缝顶点）
    edges += [("side", g) for g in _chain_suffix(side_chain, d_side)]
    # 脚口（外缝顶点 -> 内缝顶点，back.hem 原方向即此）
    edges.append(("hem", ctx.curve("back.hem")))
    # 内侧缝上行（脚口内缝顶点 -> 膝 -> 裆尖，两段反向）
    edges += [("inseam", _reverse_geom(ctx.curve("back.inseam_lower"))),
              ("inseam", _reverse_geom(ctx.curve("back.inseam_upper")))]
    # 后浪上行（裆尖 -> 臀围内缝点 -> P0/A/O'：下行后缀逆序逐段反向）
    cb_suffix = _chain_suffix(cb_chain, d_cb)
    edges += [("cb", _reverse_geom(g)) for g in reversed(cb_suffix)]
    return edges, cb_top


# ---------- 内部辅助线 / 口袋对位 / 定位孔（§4、§5）----------

def _clip_h_line(chain: list[LineSegment | CubicBezier], y: float
                 ) -> LineSegment | None:
    """水平辅助线 y 按净边链折线采样裁剪截断（§5，与前片同款）：取与链的全部
    交点 x 的 min/max 连成净样范围内线段（后片横向贯穿，正常两交点；角点/
    切点触线等奇异情形 min/max 容忍）。无两个交点返回 None。"""
    xs: list[float] = []
    for g in chain:
        pts = _geom_sample(g, 64)
        for a, b in zip(pts, pts[1:]):
            if (a.y - y) * (b.y - y) < 0:
                xs.append(a.x + (b.x - a.x) * (y - a.y) / (b.y - a.y))
            elif a.y == y:
                xs.append(a.x)
    if len(xs) < 2:
        return None
    return LineSegment(Point(min(xs), y), Point(max(xs), y))


def _chain_hit(chain: list[LineSegment | CubicBezier],
               seg: LineSegment) -> Point | None:
    """线段 seg 与净边链折线采样的最近交点（自 seg.a 起正向最近，§4 口袋
    对位刀口定位用；无交点返回 None）。"""
    best: Point | None = None
    best_d = float("inf")
    for g in chain:
        pts = _geom_sample(g, 64)
        for p, q in zip(pts, pts[1:]):
            ex, ey = q.x - p.x, q.y - p.y
            fx, fy = seg.b.x - seg.a.x, seg.b.y - seg.a.y
            det = ex * fy - ey * fx
            if abs(det) < 1e-12:
                continue
            rx, ry = p.x - seg.a.x, p.y - seg.a.y
            s = (ex * ry - ey * rx) / det      # seg 上参数（>0 = 沿射向前方）
            u = (fx * ry - fy * rx) / det      # 边折线段上参数
            if 1e-9 < s < best_d and -1e-9 <= u <= 1.0 + 1e-9:
                best_d = s
                best = Point(seg.a.x + fx * s, seg.a.y + fy * s)
    return best


def _h_cross_points(chain: list[LineSegment | CubicBezier], y: float
                    ) -> list[Point]:
    """水平线 y 与净边链折线采样的全部交点（§5 围度线 ∩ 外轮廓基准点）。

    后片横裆线常高于臀围外缝点：侧缝交点落在髋腰弧（而非大腿弧）、内侧交点
    落在后浪弧（而非内缝弧），故按整条净边链求交、不预设载体边。正常两交点
    （左 = 外侧缝、右 = 后浪/内缝）。"""
    pts: list[Point] = []
    for g in chain:
        samples = _geom_sample(g, 64)
        for a, b in zip(samples, samples[1:]):
            if (a.y - y) * (b.y - y) < 0:
                x = a.x + (b.x - a.x) * (y - a.y) / (b.y - a.y)
                pts.append(Point(x, y))
            elif a.y == y:
                pts.append(Point(a.x, y))
    # 去重（相邻段公共端点触线会重复报点）
    uniq: list[Point] = []
    for p in sorted(pts, key=lambda q: q.x):
        if not uniq or uniq[-1].distance_to(p) > 1e-9:
            uniq.append(p)
    return uniq


def _point_in_chain(p: Point, chain: list[LineSegment | CubicBezier]) -> bool:
    """点是否在净边链围成的多边形内（折线采样 + 射线法，省尖穿越判定用）。"""
    poly: list[Point] = []
    for g in chain:
        poly.extend(_geom_sample(g, 32))
    inside = False
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if (a.y > p.y) != (b.y > p.y):
            x_at = a.x + (b.x - a.x) * (p.y - a.y) / (b.y - a.y)
            if x_at > p.x:
                inside = not inside
    return inside


def _clip_seg_inside(seg: LineSegment,
                     chain: list[LineSegment | CubicBezier]) -> LineSegment | None:
    """线段保留落在净边链多边形内的子段（省腿进 marks 用，64 采样首末在内点）。"""
    inside = [seg.a.lerp(seg.b, i / 64) for i in range(65)
              if _point_in_chain(seg.a.lerp(seg.b, i / 64), chain)]
    if len(inside) < 2:
        return None
    return LineSegment(inside[0], inside[-1])


def _dart_marks(ctx: DraftContext,
                chain: list[LineSegment | CubicBezier]
                ) -> list[LineSegment]:
    """后省处理（§1 分离基准）：省尖落在裁片区内（省穿越上边界）时边界仍按
    图提取（省量吸收主口径是 back_waist_dart 约克转移），stderr 告警一次，
    省腿在裁片内的子段进 marks 提示车缝。"""
    marks: list[LineSegment] = []
    warned = False
    for i in (1, 2):
        if f"back.dart{i}_apex" not in ctx.sheet:
            continue
        apex = ctx.point(f"back.dart{i}_apex")
        if not _point_in_chain(apex, chain):
            continue                     # 省尖在上边界之上：省全由机头吸收
        if not warned:
            print("警告：后省尖低于裁片上边界（省穿越后片裁片区）-> 边界按图"
                  "提取，省腿进内部标记（省量吸收主口径为 back_waist_dart）",
                  file=sys.stderr)
            warned = True
        for leg_name in (f"back.dart{i}_leg_inner", f"back.dart{i}_leg_outer"):
            sub = _clip_seg_inside(ctx.line(leg_name), chain)
            if sub is not None:
                marks.append(sub)
    return marks


def _pocket_refs(ctx: DraftContext,
                 chain: list[LineSegment | CubicBezier]
                 ) -> tuple[list[Point], list[Point], list[LineSegment]]:
    """后贴袋引用（§4 口袋对位刀口 / §5 贴袋顶线 + 定位孔）：

    notch：贴袋顶线（back.patch_net_seg1，pt1 近后浪 -> pt2 近侧缝）自 pt2
    沿袋口方向延长 ∩ 侧缝（净边链）的交点，作口袋高度/倾斜车缝参考；
    drills：贴袋上端两顶点（§5 建议钻孔定位）；
    marks：贴袋顶线原样拷贝（§5 必须保留的袋位高度参考线）。贴袋未上版
    时三者皆空。"""
    if "back.patch_net_seg1" not in ctx.sheet:
        return [], [], []
    pt1 = ctx.point("back.patch_net_pt1")
    pt2 = ctx.point("back.patch_net_pt2")
    d = (pt2 - pt1).normalized()
    hit = _chain_hit(chain, LineSegment(pt2, pt2 + d.scale(100.0)))
    notch = [hit] if hit is not None else []
    top_geom = ctx.sheet.get("back.patch_net_seg1").geom
    return notch, [pt1, pt2], [top_geom]


def _notches(ctx: DraftContext, chain: list[LineSegment | CubicBezier],
             sa_hem: float) -> list[Point]:
    """净样刀口集（主版坐标，§4 关键对位 + §5 围度线基准点）：

    脚口折边双刀口（卷边翻折对位）、后中拼接刀口 P0（后浪 ∩ 机头拼接交点，
    无 yoke 时为腰缝后中端点）、浪尖对位刀口（后浪 ∩ 内侧缝交界，防扭腿）、
    膝围双刀口（最关键上下对位点）、臀围/横裆线 ∩ 侧缝+内缝刀口（§5 绝对
    基准点）、毗围双刀口（大腿围录入时）、口袋对位刀口（贴袋顶线延长 ∩ 侧缝）。"""
    pts = [ctx.point("back.knee_outseam_point"),
           ctx.point("back.knee_inseam_point"),
           ctx.point("back.hip_outseam_point"),
           ctx.point("back.hip_inner_point"),
           ctx.point("back.crotch_vertex"),
           ctx.curve("back.outseam_lower").point_at_y(sa_hem),
           ctx.curve("back.inseam_lower").point_at_y(sa_hem)]
    # 横裆线（髀围线）∩ 净边链：侧缝/后浪侧两基准点（§5，载体边不预设）
    pts += _h_cross_points(chain, ctx.line("back.crotch_line").a.y)
    pocket, _drills, _marks = _pocket_refs(ctx, chain)
    pts += pocket
    if "back.thigh_line" in ctx.sheet:
        pts.append(ctx.point("back.thigh_outseam_point"))
        if "back.thigh_inseam_point" in ctx.sheet:   # d=0 时内端 = 裆尖角点
            pts.append(ctx.point("back.thigh_inseam_point"))
    return pts


def _internal_marks(ctx: DraftContext,
                    chain: list[LineSegment | CubicBezier]
                    ) -> list[LineSegment | CubicBezier]:
    """内部辅助线（§5）：臀围线、膝围线按净边链水平截断；毗围线存在时
    （大腿围录入）**1:1 拷贝真实测量线**--它是外缝点 -> 裆端/内边界的
    **斜量线**（d=0 自立裆线斜量到裆尖、d>0 下移后斜量，两端点本就落在
    净边上），按水平截断会在 d=0 时与横裆线同高重合叠影、且丢掉斜量方向；
    横裆线不画（用户口径：毗围线即其测量基准，横裆水平线冗余；其高度交点
    仍进 §4 刀口）；后贴袋顶线原样保留（_pocket_refs，直线/弧顶线均保留）。"""
    marks: list[LineSegment | CubicBezier] = []
    for name in ("back.hip_line", "back.knee_line"):
        if name not in ctx.sheet:
            continue
        seg = _clip_h_line(chain, ctx.line(name).a.y)
        if seg is not None:
            marks.append(seg)
    if "back.thigh_line" in ctx.sheet:
        marks.append(ctx.line("back.thigh_line"))
    _notch, _drills, pocket_marks = _pocket_refs(ctx, chain)
    marks += pocket_marks
    return marks


# ---------- 刀口法向投影（§4，与前片同款 flow 私有实现）----------

def _edge_distance_tangent(g: LineSegment | CubicBezier, p: Point
                           ) -> tuple[float, Vector]:
    """点 p 到边 geom 的（距离, 单位切线）：直线参数投影 clamp、贝塞尔 64
    采样最近点（切线取采样点处，与 cutter 采样口径同级精度）。"""
    if isinstance(g, LineSegment):
        v = g.b - g.a
        if v.length == 0:
            return p.distance_to(g.a), Vector(1.0, 0.0)
        t = max(0.0, min(1.0, ((p.x - g.a.x) * v.dx + (p.y - g.a.y) * v.dy)
                       / (v.dx * v.dx + v.dy * v.dy)))
        q = g.a + v.scale(t)
        return p.distance_to(q), v.normalized()
    pts = g.sample(64)
    best_i, best_d = 0, float("inf")
    for i, q in enumerate(pts):
        d = p.distance_to(q)
        if d < best_d:
            best_i, best_d = i, d
    return best_d, g.tangent_at(best_i / 64).normalized()


def _notch_normal(edges: tuple[PieceEdge, ...], p: Point, sa
                  ) -> tuple[Vector, float]:
    """刀口 p 的（外法向, 所在边缝份）：与 p 距离 ≤1e-6 的边为命中--角点
    命中多条边（浪尖、膝围点等）时法向取各边外法向均值（角平分方向）；无命中
    回退全链最近边（数值兜底）。shoelace<0 走向下切线逆时针 90° 即朝外，
    与 cutter 外扩同约定。"""
    scored = [(*_edge_distance_tangent(e.geom, p), e.name) for e in edges]
    near = [s for s in scored if s[0] <= 1e-6]
    if not near:
        near = [min(scored, key=lambda s: s[0])]
    nx = ny = 0.0
    for _d, tan, _name in near:
        n = tan.perpendicular()
        nx += n.dx
        ny += n.dy
    normal = Vector(nx, ny)
    _, ref_tan, ref_name = min(near, key=lambda s: s[0])
    if normal.length <= 1e-12:            # 对向法向相消（数值奇异）回退单边
        normal = ref_tan.perpendicular()
    return normal.normalized(), _sa_for(ref_name, sa)


def _project_notch(p: Point, n: Vector, sa_amt: float,
                   poly: tuple[Point, ...]) -> Point:
    """刀口 p 沿外法向 n 的射线与毛样折线的最近交点（§4 法向延伸投影）；
    无命中（折线数值开缝）回退法向平移一个缝份。"""
    best_s: float | None = None
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        ex, ey = b.x - a.x, b.y - a.y
        det = ex * n.dy - ey * n.dx
        if abs(det) < 1e-12:
            continue
        rx, ry = a.x - p.x, a.y - p.y
        s = (ex * ry - ey * rx) / det
        u = (n.dx * ry - n.dy * rx) / det
        if s > 1e-9 and -1e-9 <= u <= 1.0 + 1e-9 \
                and (best_s is None or s < best_s):
            best_s = s
    if best_s is None:
        return p + n.scale(sa_amt)
    return p + n.scale(best_s)


def _project_notches(piece: PatternPiece, sa, notch_type: str) -> PatternPiece:
    """净样刀口沿外法向延伸投影到毛样外沿，整体替换 gross_notches（§4）。

    载体边基于缩水后净边（无缩水退化净样，与 cutter base 同口径）；缝合线位
    刀口（shrunk_notches）保留不丢信息，piece_svg 三级回退自动取毛样刀口。
    刀口类型仅记 notes（I/V 型几何差异由输出层绘制，同前片/后贴袋先例）。"""
    base = piece.shrunk_edges or piece.net_edges
    notches = piece.shrunk_notches or piece.notches
    if not notches or not piece.gross_polygon:
        return piece
    projected = []
    for p in notches:
        n, amt = _notch_normal(base, p, sa)
        projected.append(_project_notch(p, n, amt, piece.gross_polygon))
    note = (f"刀口：{notch_type} 型 ×{len(projected)}，净样刀口沿外法向"
            "投影至毛样外沿（后片裁片.md §4）",)
    return piece.with_gross(piece.gross_polygon, tuple(projected),
                            piece.notes + note)


# ---------- 主入口 ----------

def build_back_piece(main_ctx: DraftContext
                     ) -> tuple[PatternPiece, DraftContext]:
    """整版跑完后构建后片独立裁片：净样 -> 缩水 -> 缝边 -> 刀口投影
    （后片裁片.md §1~§5）。

    返回 (PatternPiece, 局部 DraftContext)：前者供 SVG 输出，后者含命名元素
    供 trace/调试。需完整整版（提取已上版净样轮廓；--until 中断的中间版无
    back.hem 时抛 ValueError）。"""
    o = main_ctx.options
    if "back.hem" not in main_ctx.sheet:
        raise ValueError(
            "后片裁片需完整整版：back.hem 未上版（--until 中断的中间版"
            "不含完整后片轮廓）")
    if o.back_yoke and "back.yoke_cb_point" not in main_ctx.sheet:
        raise ValueError(
            "back_yoke 开启但 back.yoke_cb_point 未上版：机头步骤未执行"
            "（整版不完整）")
    sa = o.back_piece_seam_allowances

    edges_main, cb_top = _net_edges(main_ctx, o)
    chain = [g for _, g in edges_main]
    notches_main = _notches(main_ctx, chain, sa.hem)
    marks_main = _internal_marks(main_ctx, chain)
    marks_main += _dart_marks(main_ctx, chain)
    _pn, drills_main, _pm = _pocket_refs(main_ctx, chain)
    notches_main.append(cb_top)          # 后中拼接刀口（§4：后浪 ∩ 机头/腰缝）

    # 1. 主版 -> 局部（Y 轴反射：X 不翻避镜像、Y 翻让腰头在上），origin = cb_top
    origin = cb_top
    local_named = [(n, _to_local_geom(g, origin)) for n, g in edges_main]
    # 2. 自定向：shoelace > 0 则反转（边序 + 每条 geom 反向），目标 < 0 保 cutter 外扩
    if _signed_area([g for _, g in local_named]) > 0:
        local_named = [(n, _reverse_geom(g)) for n, g in reversed(local_named)]
    net_edges = tuple(PieceEdge(n, g) for n, g in local_named)
    # 3. 刀口、标记、定位孔同步到局部坐标（内部线方向无关渲染，不随边界反转）
    notches = tuple(_to_local_point(p, origin) for p in notches_main)
    marks = tuple(_to_local_geom(g, origin) for g in marks_main)
    drills = tuple(_to_local_point(p, origin) for p in drills_main)
    # 4. 丝缕线（竖向 = 经向，§5 与全局纱向平行一致）
    grain = _vertical_grain(net_edges)
    # 5. 净样裁片
    piece = PatternPiece("back_piece", "后片裁片", net_edges,
                         notches=notches, grain=grain, marks=marks,
                         drills=drills)
    # 6. 先缩水后缝边（§3 顺序 2/3：缝份为绝对值不乘缩水率）：主面料率
    #    None 回退全局；经向 = 局部 Y -> Y 吃 warp、X 吃 weft（换序传参，
    #    同前片/机头口径）
    warp = (o.back_piece_shrinkage_warp
            if o.back_piece_shrinkage_warp is not None else o.shrinkage_warp)
    weft = (o.back_piece_shrinkage_weft
            if o.back_piece_shrinkage_weft is not None else o.shrinkage_weft)
    piece = apply_shrinkage(piece, weft, warp)
    # 7. 缝边（§2）：后浪浪尖（后浪弧末端 ∩ 内侧缝起点）角部两态--
    #    镜像折角（back_piece_crotch_corner=True，默认）：键序 (折线边, 被镜像边)
    #    = (cb, inseam)，后浪缝份翻折贴向内侧缝时**折线是后浪缝本身**，
    #    内侧缝侧缝份边界关于后浪折线镜像，翻折后与裁片重合、防缺角缺肉
    #    （§2 工程目的；cutter 双向查键，链序 (inseam, cb) 逆序命中时
    #    _mirror_point 形参自动交换。直角退化即 miter）；
    #    False = 纯尖角跟随净样："miter" 不限长尖角自然相交（同前片裆尖口径）
    if o.back_piece_crotch_corner:
        corners = {("cb", "inseam"): "mirror"}
    else:
        corners = {("cb", "inseam"): "miter"}
    piece = add_seam_allowance(piece, sa, corners)
    # 8. 刀口法向投影到毛样外沿（§4，专属工艺策略）
    piece = _project_notches(piece, sa, o.back_piece_notch_type)
    # 9. 局部 ctx 留命名元素供 trace/调试
    local = DraftContext(main_ctx.measurements, o)
    step = "build_back_piece"
    for i, e in enumerate(net_edges):
        if isinstance(e.geom, LineSegment):
            local.add_line(f"back_piece.edge{i}", e.geom, step=step,
                           basis=f"后片裁片 净样边 {e.name}",
                           label=f"{e.name}边{i}")
        else:
            local.add_curve(f"back_piece.edge{i}", e.geom, step=step,
                            basis=f"后片裁片 净样边 {e.name}",
                            label=f"{e.name}边{i}")
    return piece, local
