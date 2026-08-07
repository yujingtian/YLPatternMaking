"""前口袋绘制步骤：挖削嵌入式（INSET）主切口（前口袋绘制.md §二、§三.1~§三.2）。

本轮只实现主切口边界（先画后裁，布尔裁减层未建）：
  锚点 P1（腰弧）/ P2（外缝弧）沿弧量取 → 袋口设计净线 C(t)（弧高式 /
  两端垂直式 / 折角式三种模式）→
  共线渐变撇削（C_cut(t) = C(t) + V·(1−t)ⁿ，V 沿腰头线、省顶点 P1′ 落在
  腰头线上，吃省向侧缝端衰减至 0）→
  挖除区边界（O→P1 腰弧子段、P1→P1′ 吃省边、切削线、P2→O 外缝弧子段）
  上版为结构元素。
不实现：PATCH 管线、袋布贴偏置、底袋、明线、DXF 图层。

与其他步骤一致：数值计算走 geometry / draft.curves，经验常数收敛到
PatternOptions（front_pocket_*），步骤间元素只经 DraftContext 读取。
"""

from __future__ import annotations

from ..draft import DraftContext, NamedCurve, NamedLine
from ..draft import curves
from ..geometry import CubicBezier, LineSegment, Point, Vector


def draw_front_pocket(ctx: DraftContext) -> NamedCurve | NamedLine | None:
    """前口袋挖削嵌入式主切口（打版流程.md「前口袋打版过程」，可选步骤）：
    开关 front_pocket 开启才绘制，否则整步跳过。

    定位锚点（前口袋绘制.md §二，局部原点 O = 腰侧交点，即腰围外缝顶点 B）：
      - P1：腰弧（B → 前浪顶点 A）上自腰外缝顶点 B（即局部原点 O）
        朝前浪顶点沿弧量取 front_pocket_p1_dist；
      - P2：外缝弧（臀围外缝顶点 → B）上自 B 向下沿弧量取
        front_pocket_p2_drop。
    袋口设计净线 C(t)（§二 曲线控制函数，三种模式）：
      - "bulge" 弧高式：P1 → P2 三次贝塞尔浅弧，弧高
        front_pocket_mouth_bulge（正值向裤片内侧凹入加深勺口），弧顶位置
        front_pocket_mouth_bulge_at（弦长比例 0~1，偏侧缝端取 0.6~0.7）；
      - "tangent" 两端垂直式：P1 端切线 ⟂ 腰弧切线、P2 端切线 ⟂ 外缝弧
        切线（均指向裤片内部），形状由两端切线柄长 front_pocket_mouth_h1 /
        h2 控制；
      - "polyline" 折角式（带倒角折线）：P1 → K1 → … → Kn → P2 多段直线，
        折角列表 front_pocket_mouth_corners 逐角给（弦上位置， 内推深度），
        位置须严格递增；空列表 = 直袋口。
    净线即净线袋布贴的对位线。
    共线渐变撇削吃省（§三.1，免去空间旋转，无省尖）：
      P1′ = P1 沿腰弧朝前浪顶点量取 ΔW（腰头吃省总宽
      front_pocket_dart_width），撇削向量 V = P1′ − P1 沿腰头线方向；
      前大片实际切削线为设计净线的共线渐变偏置
      C_cut(t) = C(t) + V·(1−t)ⁿ（n = front_pocket_paring_n 衰减幂指数）——
      共线：整条袋口线沿同一方向（腰头走向）偏置，省顶点 C_cut(0) = P1′
      落在腰头线上，不向裤片内折；渐变：(1−t)ⁿ 衰减，t=1 侧缝端偏置为 0
      与 P2 严格重合；弧线模式以控制点渐变偏置近似，折角模式折角 K 按
      (1−corner_at)ⁿ 偏置；ΔW = 0 时 C_cut = C(t)。
    挖除区边界（§三.2，Ω_cutout = O → P1 → C_cut(t) → P2 → O）：
      - 腰侧边界 O→P1 为腰弧的精确子段（de Casteljau 细分）；
      - 吃省边 P1→P1′ 沿腰头线（结构线）；
      - 侧缝边界 P2→O 为外缝弧的精确子段（de Casteljau 细分，
        与裁片外缝线重合；布尔裁减待裁切层）。
    依据：打版流程.md「前口袋打版过程」；前口袋绘制.md §二、§三.1~§三.2。
    """
    o = ctx.options
    if not o.front_pocket:
        return None                     # 开关关闭，可选步骤跳过

    step = "draw_front_pocket"
    b = ctx.point("front.waist_side_point")     # O：腰侧交点（局部原点）
    w_arc = ctx.curve("front.waistline_arc")    # t=0 在 B，t=1 在前浪顶点
    s_arc = ctx.curve("front.outseam_arc")      # t=0 在臀围外缝顶点，t=1 在 B

    # P1：腰弧自腰外缝顶点（t=0 端，即局部原点 O）朝前浪顶点沿弧量取
    lw = w_arc.length()
    if o.front_pocket_p1_dist >= lw:
        raise ValueError(
            f"P1 弧长距离 {o.front_pocket_p1_dist} 超过腰弧总长 {lw:.2f}")
    t1 = w_arc.t_at_length(o.front_pocket_p1_dist)
    p1 = w_arc.point_at(t1)

    # P2：外缝弧自腰外缝顶点（t=1 端）向下沿弧量取
    ls = s_arc.length()
    if o.front_pocket_p2_drop >= ls:
        raise ValueError(
            f"P2 弧长深度 {o.front_pocket_p2_drop} 超过外缝弧总长 {ls:.2f}")
    t2 = s_arc.t_at_length(ls - o.front_pocket_p2_drop)
    p2 = s_arc.point_at(t2)

    # 共线渐变撇削（§三.1）：P1′ 在腰弧上（朝前浪顶点量 ΔW），撇削向量
    # V = P1′ − P1 沿腰头线方向；整条袋口线按 V·(1−t)ⁿ 共线渐变偏置，
    # 省顶点落在腰头线上不内折，侧缝端衰减至 0 与 P2 重合；
    # ΔW = 0 = 不吃省，切削线 = 设计净线
    dw, pw = o.front_pocket_dart_width, o.front_pocket_paring_n
    if dw > 0 and o.front_pocket_p1_dist + dw >= lw:
        raise ValueError(
            f"P1 弧长距离 {o.front_pocket_p1_dist} 与腰头吃省总宽 {dw} "
            f"之和超过腰弧总长 {lw:.2f}")
    p1r = p1 if dw == 0 else w_arc.point_at_length(
        o.front_pocket_p1_dist + dw)
    v = p1r - p1

    # 挖除区边界：O→P1 腰弧精确子段；P2→O 外缝弧子段（与裁片外缝线重合）
    waist_edge = w_arc.split(t1)[0]
    outseam_edge = s_arc.split(t2)[1]

    ctx.add_point("front.pocket_p1", p1,
                  step=step,
                  basis=f"腰弧自腰外缝顶点沿弧量取 {o.front_pocket_p1_dist}"
                        "（前口袋绘制.md §二）",
                  label="袋口腰侧锚点P1")
    ctx.add_point("front.pocket_p2", p2,
                  step=step,
                  basis=f"外缝弧自腰外缝顶点向下沿弧量取 {o.front_pocket_p2_drop}"
                        "（前口袋绘制.md §二）",
                  label="袋口侧缝锚点P2")

    # 袋口设计净线 C(t)（§二 曲线控制函数，三种模式）+ 切削线
    mode = o.front_pocket_mouth_mode
    if mode == "polyline":
        # 折角式（带倒角折线）：P1 → K1 → … → Kn → P2 多段直线；
        # 折角 Ki = 弦上 ui 处沿左手法向（向裤片内侧，同 bulge 口径）推进 di；
        # 撇削偏置：各折角按其位置 (1−ui)ⁿ 渐变衰减
        n = (p2 - p1).normalized().perpendicular()
        ks = [p1.lerp(p2, u) + n.scale(d)
              for u, d in o.front_pocket_mouth_corners]
        krs = [k + v.scale((1 - u) ** pw)
               for (u, _), k in zip(o.front_pocket_mouth_corners, ks)]
        net_pts = [p1, *ks, p2]
        cut_pts = [p1r, *krs, p2]
        for i, ((u, d), k) in enumerate(
                zip(o.front_pocket_mouth_corners, ks), 1):
            ctx.add_point(f"front.pocket_mouth_corner{i}", k,
                          step=step,
                          basis=f"弦上 {u} 处向内推进 {d}"
                                "（带倒角折线折角，前口袋绘制.md §二）",
                          label=f"袋口折角点{i}")
        for i in range(len(net_pts) - 1):
            ctx.add_line(f"front.pocket_mouth_baseline_seg{i + 1}",
                         LineSegment(net_pts[i], net_pts[i + 1]),
                         step=step,
                         basis=f"净线第 {i + 1} 段（净线袋布贴对位线，§二）",
                         label=f"袋口净线{i + 1}段", role="struct")
    elif mode == "tangent":
        # 两端垂直式：P1 端切线 ⟂ 腰弧切线、P2 端切线 ⟂ 外缝弧切线，
        # 均取指向裤片内部的一侧（以裤中线立裆点判定）；形状由两端
        # 切线柄长 front_pocket_mouth_h1 / h2 控制
        interior = ctx.point("front.crease_point")

        def _inward(t: Vector, anchor: Point) -> Vector:
            if (t.dx * (interior.x - anchor.x)
                    + t.dy * (interior.y - anchor.y)) < 0:
                t = t.scale(-1)
            return t

        t_w = _inward(w_arc.tangent_at(t1).normalized().perpendicular(), p1)
        t_s = _inward(s_arc.tangent_at(t2).normalized().perpendicular(), p2)
        design = CubicBezier(p1, p1 + t_w.scale(o.front_pocket_mouth_h1),
                             p2 + t_s.scale(o.front_pocket_mouth_h2), p2)
        basis_design = (f"P1→P2 袋口设计净线（两端垂直式：P1 端切线 ⟂ 腰弧、"
                        f"P2 端切线 ⟂ 外缝弧，柄长 {o.front_pocket_mouth_h1}"
                        f"/{o.front_pocket_mouth_h2}，前口袋绘制.md §二）")
    else:
        # 弧高式：浅弧，弧高、弧顶位置可调
        design = curves.arc_through(
            p1, p2, bulge=o.front_pocket_mouth_bulge,
            bulge_at=o.front_pocket_mouth_bulge_at)
        basis_design = (f"P1→P2 袋口设计净线，弧高 {o.front_pocket_mouth_bulge}"
                        f"、弧顶位置 {o.front_pocket_mouth_bulge_at}"
                        "（净线袋布贴对位线，前口袋绘制.md §二）")
    if mode != "polyline":
        ctx.add_curve("front.pocket_mouth_baseline", design,
                      step=step,
                      basis=basis_design,
                      label="袋口设计净线")

    if dw > 0:
        ctx.add_point("front.pocket_p1_transfer", p1r,
                      step=step,
                      basis=f"P1 沿腰弧朝前浪顶点量取吃省 {dw}（省顶点在腰头线上，"
                            "前口袋绘制.md §三.1）",
                      label="吃省顶点P1′")
        ctx.add_line("front.pocket_cut_start", LineSegment(p1, p1r),
                     step=step,
                     basis=f"P1 → P1′：沿腰头线的吃省撇削边（吃省 {dw}，"
                           "前口袋绘制.md §三.1）",
                     label="吃省撇削边", role="struct")
    ctx.add_curve("front.pocket_waist_edge", waist_edge,
                  step=step,
                  basis="腰弧 O→P1 子段（de Casteljau 细分，"
                        "Ω_cutout 边界，前口袋绘制.md §三.2）",
                  label="挖除区腰侧边界")
    ctx.add_curve("front.pocket_outseam_edge", outseam_edge,
                  step=step,
                  basis="外缝弧 P2→O 子段（de Casteljau 细分，与裁片外缝线重合，"
                        "Ω_cutout 边界，前口袋绘制.md §三.2）",
                  label="挖除区侧缝边界")

    if mode == "polyline":
        if dw > 0:
            for i, ((u, _), kr) in enumerate(
                    zip(o.front_pocket_mouth_corners, krs), 1):
                ctx.add_point(f"front.pocket_mouth_corner_cut{i}", kr,
                              step=step,
                              basis=f"折角切削点{i}：K{i} + V·(1−{u})^{pw}"
                                    "（共线渐变撇削，§三.1）",
                              label=f"袋口折角切削点{i}")
        last = None
        for i in range(len(cut_pts) - 1):
            last = ctx.add_line(f"front.pocket_mouth_seg{i + 1}",
                                LineSegment(cut_pts[i], cut_pts[i + 1]),
                                step=step,
                                basis=f"切削线第 {i + 1} 段（吃省 {dw} "
                                      "共线渐变偏置，§三.1）",
                                label=f"袋口切削线{i + 1}段", role="struct")
        return last

    cut = CubicBezier(
        design.p0 + v,                                     # (1−0)ⁿ = 1 → P1′
        design.p1 + v.scale((2 / 3) ** pw),
        design.p2 + v.scale((1 / 3) ** pw),
        design.p3)                                         # (1−1)ⁿ = 0 → P2
    return ctx.add_curve("front.pocket_mouth", cut,
                         step=step,
                         basis=f"切削线 C_cut(t) = C(t) + V·(1−t)^{pw}（V 沿腰头线，"
                               f"|V| = 吃省 {dw}）：腰头端吃省最大、侧缝端衰减至 0"
                               "（前口袋绘制.md §三.1）",
                         label="袋口切削线")
