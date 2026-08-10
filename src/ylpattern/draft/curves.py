"""公共弧线库：参数化生成打版曲线（设计文档 §5.3.1）。

规则：
- 形状仅由参数区分的弧线一律用本库，保证同类弧线画法统一；
- 共用不强制 —— 裁片特有曲线允许步骤函数自行构造贝塞尔控制点；
- 所有参数必须是有物理意义的量（cm、角度、弦长比例），禁止魔法数。
"""

from __future__ import annotations

import math

from ..geometry import LineSegment, Point, Vector, CubicBezier

# 三次贝塞尔逼近"控制点弦"关系的常用系数：
# 弧顶在 t=0.5 时，弧高 ≈ 0.375 * 控制点相对弦的偏移，故放大 8/3
_BULGE_TO_CTRL = 8 / 3


def arc_through(end_a: Point, end_b: Point, *,
                bulge: float, bulge_at: float = 0.5) -> CubicBezier:
    """过两端点、按弧高控制的通用浅弧（脚口弧、膝围过渡等）。

    参数：
        bulge     弧高（弦的垂直方向凸起量，cm，正值向左手法向凸）
        bulge_at  弧顶位置（弦长比例 0~1，默认中点）
    """
    chord = end_b - end_a
    normal = chord.normalized().perpendicular()
    ctrl_offset = bulge * _BULGE_TO_CTRL
    p1 = end_a.lerp(end_b, bulge_at * 0.5) + normal.scale(ctrl_offset)
    p2 = end_a.lerp(end_b, (1 + bulge_at) * 0.5) + normal.scale(ctrl_offset)
    return CubicBezier(end_a, p1, p2, end_b)


def crotch_curve(start: Point, end: Point, *,
                 tangent_angle_deg: float, depth: float,
                 tension: float = 1.0) -> CubicBezier:
    """裆弯弧：起点切线约束 + 凹入深度控制。

    前后裆弯共用机制，凹深、切线角参数各自独立传入
    （前小裆 H/20、后大裆 H/10，见 前后片臀围推导.md §三.2）。

    参数：
        tangent_angle_deg 起点切线角（度，自 +X 轴逆时针），通常贴立裆线方向
        depth              裆弯凹入深度（cm），即起点沿切线方向的伸出控制长度
        tension            终点侧曲率松紧（>1 更饱满，默认 1.0）
    """
    rad = math.radians(tangent_angle_deg)
    t1 = Vector(math.cos(rad), math.sin(rad))
    p1 = start + t1.scale(depth * tension)

    chord = end - start
    p2 = end - chord.normalized().scale(chord.length / 3 * tension)
    return CubicBezier(start, p1, p2, end)


def front_rise(a: Point, b: Point, c: Point, *,
               target_length: float,
               handle_ratio: float = 1 / 3) -> tuple[Point, CubicBezier]:
    """前浪复合线：斜线 AB + 裆弯凹弧 BC，按总前浪长闭合反推 A 点。

    依据 前浪绘制.md：
      - 弧线 BC 起点切线沿 AB 延伸方向（B 点无折角），终点切线水平（贴立裆线）；
      - 控制柄长 k1 = k2 = |B−C| × handle_ratio（§4 标准控制柄）；
      - 弧长闭合：L_AB = target_length − ArcLength(BC)，
        A 沿 AB 反方向移动至 A_new（§4 方案"延伸点 A"）。

    参数：
        a              前中内收点（初始位置，仅用于确定斜线方向）
        b              臀围线内缝点（拐点）
        c              前小裆宽顶点（底裆点）
        target_length  目标总前浪长（cm，即量体的前浪尺寸）
        handle_ratio   控制柄长 / 弦长比例（默认 1/3，前浪绘制.md §4）

    返回：(a_new, 弧线 BC)；斜线段由调用方以 a_new、b 构造。
    """
    d_ab = (b - a).normalized()
    k = b.distance_to(c) * handle_ratio
    arc = CubicBezier(b, b + d_ab.scale(k), c + Vector(-k, 0.0), c)
    l_ab = target_length - arc.length()
    if l_ab <= 0:
        raise ValueError(
            f"前浪长 {target_length:.2f} 小于裆弯弧长 {arc.length():.2f}，"
            "无法闭合：请加大前浪或减小裆宽/直裆深")
    return b + d_ab.scale(-l_ab), arc


def back_rise(a: Point, b: Point, c: Point, *,
              target_length: float,
              alpha: float = 0.40, beta: float = 0.50
              ) -> tuple[Point, CubicBezier]:
    """后浪复合线：后中斜线 AB + 大裆弯深凹弧 BC，按总后浪长闭合反推 A 点。

    依据 后浪绘制.md：
      - 弧线 BC 起点切线严格共线于 AB 延伸方向（B 点无折角，§1.2），
        终点切线水平（平行立裆线，§1.2）；
      - 控制柄 k1 = α·|B−C|、k2 = β·|B−C|（§3.1：后裆弯深于前浪，
        α∈[0.38,0.42]、β∈[0.48,0.55]，紧身提臀 β 取 0.55）；
      - 弧长闭合：L_AB = target_length − ArcLength(BC)，
        A 沿 AB 反方向延伸至 A_new（§4 反推点 A 延伸法；
        延伸量即后翘高的自然结果）。

    参数：
        a              后中内收点（初始位置，仅用于确定斜线方向）
        b              臀围线内缝点（拐点）
        c              后大裆宽顶点（底裆点）
        target_length  目标总后浪长（cm，即量体的后浪尺寸）
        alpha          上控制柄系数（k1/弦长，§3.1）
        beta           下控制柄系数（k2/弦长，§3.1）

    返回：(a_new, 弧线 BC)；斜线段由调用方以 a_new、b 构造。
    """
    d_ab = (b - a).normalized()
    chord = b.distance_to(c)
    arc = CubicBezier(b, b + d_ab.scale(alpha * chord),
                      c + Vector(-beta * chord, 0.0), c)
    l_ab = target_length - arc.length()
    if l_ab <= 0:
        raise ValueError(
            f"后浪长 {target_length:.2f} 小于大裆弯弧长 {arc.length():.2f}，"
            "无法闭合：请加大后浪或减小裆宽/直裆深")
    return b + d_ab.scale(-l_ab), arc


def lower_leg_mid(knee: Point, hem: Point, alpha: float) -> Point:
    """小腿段中介控制点 P_mid/Q_mid（前片弧线推导.md §三）。

    M = 膝口与脚口的直线中点，横向自适应补偿 α·(X膝 − X脚口)：
    Δx = 0（直筒）时退化为中点，曲线成 100% 直线；
    Δx > 0（上宽下窄）向肌肉侧微凸；Δx < 0（喇叭）微凹展开。
    """
    m = knee.midpoint(hem)
    return Point(m.x + alpha * (knee.x - hem.x), m.y)


def sag_curve(end_a: Point, end_b: Point, *, sag: float) -> CubicBezier:
    """过两端点的浅弧，弧顶（t=0.5）精确偏离弦 sag cm（正值向左手法向凸）。

    对称控制点位于弦的 1/4、3/4 处，偏移 4/3·sag（三次贝塞尔中点
    偏移 = 3/4 × 控制点偏移）；sag = 0 时退化为直线。
    用于脚口弧等需要"弧高"语义精确的场合（区别于 arc_through 的
    bulge 经验系数）。
    """
    normal = (end_b - end_a).normalized().perpendicular()
    ctrl = normal.scale(sag * 4 / 3)
    p1 = end_a.lerp(end_b, 0.25) + ctrl
    p2 = end_a.lerp(end_b, 0.75) + ctrl
    return CubicBezier(end_a, p1, p2, end_b)


def waist_sag_p2(p0: Point, p3: Point, p1: Point, *, at: float,
                 sag: float) -> Point:
    """腰弧下凹控制点 P2：令弧参数中点（t=0.5）相对弦 P0P3 的下凹量
    精确等于 sag。

    三次贝塞尔中点偏差 = 3/8 ×（P1 偏差 + P2 偏差），故
    P2 偏差 = 8/3·sag − P1 偏差 —— 自动补偿直角平顺段（P1）对弦的
    偏离，保证前/后片同一 sag 值得到同一视觉凹度（前后片弦斜率、
    正交段方向都不同，不补偿则同一 sag 实际凹度可差数倍）。

    参数：
        p0, p3  弧两端点（弦）
        p1      已确定的起点侧控制点（90° 正交平顺段）
        at      P2 在弦上的落点位置（弦长比例 0~1，决定凹峰偏位）
        sag     弧中点相对弦的下凹量（cm，0 = 中点压弦）
    """
    d = (p3 - p0).normalized()
    n = d.perpendicular()
    if n.dy > 0:
        n = n.scale(-1)                      # 取下凹侧（朝 −Y）法向
    dev_p1 = (p1 - p0).dx * n.dx + (p1 - p0).dy * n.dy
    dev_p2 = sag * 8 / 3 - dev_p1
    on_chord = p0.lerp(p3, at)
    return on_chord + n.scale(dev_p2)


def point_along_chain(geoms: tuple, distance: float) -> Point:
    """自链首端起，沿几何体链 geoms（直线 LineSegment / 曲线 CubicBezier，
    已按 首端→远端 顺序排列）量取弧长 distance 处的点。

    用于"沿接缝量取腰头宽"定位弯腰头下腰缝端点：前/后浪 = 前中/后中斜线
    （LineSegment）+ 裆弯弧（CubicBezier）的复合链，自浪顶向下量取腰头宽 W
    （前腰头绘制推导.md §4.3 A'、后腰头绘制推导.md §4 O'）。
    LineSegment.length 为属性、CubicBezier.length() 为方法，分支处理；
    distance 超过链总长时抛 ValueError。
    """
    remaining = distance
    for g in geoms:
        if isinstance(g, LineSegment):
            total = g.length
            if remaining <= total:
                return g.point_at(remaining / total)
            remaining -= total
        else:                                   # CubicBezier
            total = g.length()
            if remaining <= total:
                return g.point_at_length(remaining)
            remaining -= total
    raise ValueError(
        f"量取距离 {distance} 超过几何体链总长，无法沿接缝定位下腰缝端点")


def bezier_subrange(c: CubicBezier, ta: float, tb: float) -> CubicBezier:
    """取曲线参数 [ta, tb] 子段（两次 split 组合）。

    用于"侧缝/腰弧的精确子段"截取：弯腰头时下腰头把外缝弧、腰弧的有效
    范围截到下侧缝腰点 B'（参数 t_side < 1），挖削区边界、袋布固定边界
    等按 [t2, t_side] / [0, t_side] 取子段（前口袋绘制.md §三.2）。
    ta <= 0、tb >= 1 分别短路为 split(tb)[0] / split(ta)[1]。
    """
    if ta <= 0.0 and tb >= 1.0:
        return c
    if ta <= 0.0:
        return c.split(tb)[0]
    if tb >= 1.0:
        return c.split(ta)[1]
    _, second = c.split(ta)
    return second.split((tb - ta) / (1.0 - ta))[0]


def foot_on_bezier(curve: CubicBezier, p: Point, *, n: int = 128) -> Point:
    """点 p 在三次贝塞尔曲线上的法足（正交投影垂足）：曲线上使
    (point_at(t) − p) ⟂ tangent_at(t) 的点，即过 p 的曲线法线之垂足
    （平缓段亦为曲线上离 p 最近点）。

    用于弯腰头口袋省位延长：下腰头线上的袋口腰侧锚点 P1 / 吃省顶点 P1′
    沿垂直于上腰头线（front.waistline_arc）方向延长到上腰头线，法足即
    上腰头线上的延长落点（打版流程.md「前口袋打版过程」：弯腰头 + 有省量
    时延长至上腰头，延长线垂直于上腰头线）。

    采样定位离 p 最近的段 + 二分法足方程 C'(t)·(C(t)−p)=0（邻域单调过零、
    精度高；端点等退化情况回退三分距离极小）。与 t_at_y / t_at_length
    同款"采样定位 + 迭代"风格。
    """
    pts = curve.sample(n)
    best_i, best_d = 0, pts[0].distance_to(p)
    for i in range(1, n + 1):
        d = pts[i].distance_to(p)
        if d < best_d:
            best_d, best_i = d, i
    lo = max(0.0, (best_i - 1) / n)
    hi = min(1.0, (best_i + 1) / n)

    def _f(t: float) -> float:
        # 法足方程：曲线 t 处切线与 (曲线点 − p) 的点积，法足处 = 0
        c = curve.point_at(t)
        tg = curve.tangent_at(t)
        return (c.x - p.x) * tg.dx + (c.y - p.y) * tg.dy

    flo, fhi = _f(lo), _f(hi)
    if flo * fhi > 0:
        # 邻域未含法足零点（法足落端点等）--退化为三分距离极小
        for _ in range(60):
            m1 = lo + (hi - lo) / 3
            m2 = hi - (hi - lo) / 3
            if curve.point_at(m1).distance_to(p) < curve.point_at(m2).distance_to(p):
                hi = m2
            else:
                lo = m1
        return curve.point_at((lo + hi) / 2)
    # 法足方程 _f(t)=0 在邻域单调过零，二分至高精度
    for _ in range(60):
        mid = (lo + hi) / 2
        fmid = _f(mid)
        if abs(fmid) <= 1e-12:
            break
        if flo * fmid <= 0:
            hi = mid
            fhi = fmid
        else:
            lo = mid
            flo = fmid
    return curve.point_at((lo + hi) / 2)


def lower_leg_curve(knee: Point, hem: Point, mid: Point) -> CubicBezier:
    """小腿段自适应二次贝塞尔（膝口 → 脚口），升阶为三次返回（§三）。

    二次曲线 (knee, mid, hem) 升阶：
    P1 = knee + 2/3·(mid − knee)，P2 = hem + 2/3·(mid − hem)。
    """
    p1 = knee + (mid - knee).scale(2 / 3)
    p2 = hem + (mid - hem).scale(2 / 3)
    return CubicBezier(knee, p1, p2, hem)


def thigh_inseam_curve(crotch: Point, knee: Point, mid: Point, *,
                       k1: float, ky: float, k2_ratio: float) -> CubicBezier:
    """内缝大腿段三次贝塞尔（前小裆顶点 → 膝围内缝点，前片弧线推导.md §四）。

    P1 = (X裆 − k1·ΔX, Y裆 − ky·ΔY) 控制小裆弧弯度急缓；
    P2 锁死在 mid → knee 射线延伸方向上（k2 = k2_ratio·ΔY），
    与小腿段膝口切线严格共线（C1 连续，§六）。
    """
    dx = crotch.x - knee.x
    dy = crotch.y - knee.y
    p1 = Point(crotch.x - k1 * dx, crotch.y - ky * dy)
    p2 = knee + (knee - mid).normalized().scale(k2_ratio * dy)
    return CubicBezier(crotch, p1, p2, knee)


def thigh_outseam_curve(hip: Point, crotch_y: float, knee: Point,
                        mid: Point, *,
                        delta_x: float, m2_ratio: float) -> CubicBezier:
    """外缝大腿段三次贝塞尔（臀围外缝顶点 → 膝围外缝点，前片弧线推导.md §五）。

    Q1 = (X臀 − δx, 立裆线高) 控制大转子外凸饱满度（δx=0 为顺直）；
    Q2 锁死在 mid → knee 射线延伸方向上（m2 = m2_ratio·ΔY），
    与小腿段膝口切线严格共线（C1 连续，§六）。
    """
    q1 = Point(hip.x - delta_x, crotch_y)
    q2 = knee + (knee - mid).normalized().scale(m2_ratio * (crotch_y - knee.y))
    return CubicBezier(hip, q1, q2, knee)


def hip_waist_outseam_curve(hip: Point, waist: Point, *,
                            dx1: float, k1: float,
                            dx2: float, k2: float) -> CubicBezier:
    """髋腰侧缝段三次贝塞尔（最终臀围外缝顶点 → 后腰头外缝顶点，
    后片弧线推导.md §五）。

    W1 = (X臀 + δx1, Y臀 + k1·ΔY) 控制骨盆外圆弧饱满度
    （δx1 ≈ 0~0.3，k1 ∈ [0.35, 0.45]，ΔY = Y腰 − Y臀）；
    W2 = (X腰 − δx2, Y腰 − k2·ΔY) 控制腰头收边顺直度
    （δx2 = 0，k2 ∈ [0.20, 0.30]）。

    注：δx 的"向外"方向按推导文档自身坐标系（外缝朝 +X）书写；
    调用方坐标系若外缝朝 −X，需取负传入（见 back_steps 调用处）。
    """
    dy = waist.y - hip.y
    w1 = Point(hip.x + dx1, hip.y + k1 * dy)
    w2 = Point(waist.x - dx2, waist.y - k2 * dy)
    return CubicBezier(hip, w1, w2, waist)
