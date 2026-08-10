"""前口袋绘制步骤：挖削嵌入式（INSET）主切口（前口袋绘制.md §二、§三.1~§三.2）。

本轮只实现主切口边界（先画后裁，布尔裁减层未建）：
  锚点 P1（腰弧）/ P2（外缝弧）沿弧量取 → 袋口设计净线 C(t)（弧高式 /
  两端垂直式 / 折角式三种模式）→
  共线渐变撇削（C_cut(t) = C(t) + V·(1−t)ⁿ，V 沿腰头线、省顶点 P1′ 落在
  腰头线上，吃省向侧缝端衰减至 0）→
  挖除区边界（O→P1 腰弧子段、P1→P1′ 吃省边、切削线、P2→O 外缝弧子段）
  上版为结构元素。
PATCH（表面外贴式）管线见本模块 draw_front_patch_pocket（§四）。
不实现：袋布贴偏置、底袋、明线、DXF 图层。

与其他步骤一致：数值计算走 geometry / draft.curves，经验常数收敛到
PatternOptions（front_pocket_*），步骤间元素只经 DraftContext 读取。
"""

from __future__ import annotations

from ..draft import DraftContext, NamedCurve, NamedLine
from ..draft import curves
from ..geometry import CubicBezier, LineSegment, Point, Vector
from ..params import WaistbandType
from .front_steps import effective_waist


def draw_front_pocket(ctx: DraftContext) -> NamedCurve | NamedLine | None:
    """前口袋挖削嵌入式主切口（打版流程.md「前口袋打版过程」，可选步骤）：
    开关 front_pocket 开启才绘制，否则整步跳过。

    定位锚点（前口袋绘制.md §二，局部原点 O = 有效腰口的侧缝腰点）：
      - 有效腰口（steps.front_steps.effective_waist）：弯腰头时腰头独立成片，
        裤身顶边为下腰头线，锚点相对下腰头线与下侧缝腰点 B' 定位；直腰头时
        相对上腰弧与腰外缝顶点 B 定位；
      - P1：腰弧（b → 前浪顶点）上自侧缝腰点 b（即局部原点 O）
        朝前浪顶点沿弧量取 front_pocket_p1_dist；
      - P2：外缝弧（臀围外缝顶点 → B）上自 b 向下沿弧量取
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
    弯腰头省位延长（打版流程.md「前口袋打版过程」）：弯腰头且吃省 ΔW > 0 时，
      P1、P1′ 沿垂直于上腰头线（front.waistline_arc）方向延长至上腰头线
      （法足正交投影），在腰头裁片顶边标出省的两个顶点；直腰头或无省时跳过。
    依据：打版流程.md「前口袋打版过程」；前口袋绘制.md §二、§三.1~§三.2。
    """
    o = ctx.options
    if not o.front_pocket:
        return None                     # 开关关闭，可选步骤跳过

    step = "draw_front_pocket"
    # 有效腰口：弯腰头相对下腰头线（下侧缝腰点 B'），直腰头相对上腰弧（B）
    b, w_arc, s_side = effective_waist(ctx)
    s_arc = ctx.curve("front.outseam_arc")      # t=0 在臀围外缝顶点，t=1 在 B
    ref = ("下侧缝腰点B'" if o.waistband_type is WaistbandType.CURVED
           else "腰外缝顶点")

    # P1：腰弧自侧缝腰点（t=0 端，即局部原点 O）朝前浪顶点沿弧量取
    lw = w_arc.length()
    if o.front_pocket_p1_dist >= lw:
        raise ValueError(
            f"P1 弧长距离 {o.front_pocket_p1_dist} 超过腰弧总长 {lw:.2f}")
    t1 = w_arc.t_at_length(o.front_pocket_p1_dist)
    p1 = w_arc.point_at(t1)

    # P2：外缝弧自侧缝腰点（弯腰头 B' / 直腰头 B）向下沿弧量取
    s_p2 = s_side - o.front_pocket_p2_drop
    if s_p2 <= 0:
        raise ValueError(
            f"P2 弧长深度 {o.front_pocket_p2_drop} 超过侧缝腰点以下外缝弧长 "
            f"{s_side:.2f}")
    t2 = s_arc.t_at_length(s_p2)
    p2 = s_arc.point_at(t2)
    t_side = s_arc.t_at_length(s_side)          # b 在外缝弧上的参数（直腰头 = 1）

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

    # 挖除区边界：O→P1 腰弧精确子段；P2→O 外缝弧子段（与裁片外缝线重合；
    # 弯腰头时 O = B'，侧缝边界截到下腰头线，不含腰头裁除区）
    waist_edge = w_arc.split(t1)[0]
    outseam_edge = curves.bezier_subrange(s_arc, t2, t_side)

    ctx.add_point("front.pocket_p1", p1,
                  step=step,
                  basis=f"腰弧自{ref}沿弧量取 {o.front_pocket_p1_dist}"
                        "（前口袋绘制.md §二）",
                  label="袋口腰侧锚点P1")
    ctx.add_point("front.pocket_p2", p2,
                  step=step,
                  basis=f"外缝弧自{ref}向下沿弧量取 {o.front_pocket_p2_drop}"
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
        # 弯腰头 + 有省量：P1 / P1′ 沿垂直于上腰头线方向延长至上腰头线
        # （法足正交投影），在腰头裁片顶边标出省位（打版流程.md 前口袋打版过程）
        if o.waistband_type is WaistbandType.CURVED:
            upper = ctx.curve("front.waistline_arc")
            p1_top = curves.foot_on_bezier(upper, p1)
            p1r_top = curves.foot_on_bezier(upper, p1r)
            ctx.add_point("front.pocket_p1_top", p1_top,
                          step=step,
                          basis="P1 沿垂直于上腰头线方向延长至上腰头线（法足，"
                                "打版流程.md 前口袋打版过程：弯腰头 + 有省量）",
                          label="袋口腰侧锚点上腰头投影P1顶")
            ctx.add_point("front.pocket_p1_transfer_top", p1r_top,
                          step=step,
                          basis="P1′ 沿垂直于上腰头线方向延长至上腰头线（法足，"
                                "打版流程.md 前口袋打版过程：弯腰头 + 有省量）",
                          label="吃省顶点上腰头投影P1′顶")
            ctx.add_line("front.pocket_p1_extend", LineSegment(p1, p1_top),
                         step=step,
                         basis="P1 → 上腰头线 垂直延长线（腰头裁片省位标记）",
                         label="P1省位延长线", role="ref")
            ctx.add_line("front.pocket_p1_transfer_extend",
                         LineSegment(p1r, p1r_top),
                         step=step,
                         basis="P1′ → 上腰头线 垂直延长线（腰头裁片省顶标记）",
                         label="P1′省顶延长线", role="ref")
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


# ---------- 分支 B：表面外贴式（PATCH）管线 ----------

def draw_front_patch_pocket(ctx: DraftContext) -> NamedLine | None:
    """前贴袋（表面外贴式 PATCH，打版流程.md「前口袋打版过程」，可选步骤）：
    开关 front_patch 开启才绘制，否则整步跳过。

    前大片保持 100% 完整、不裁切（§四.1，Ω_cutout = ∅）；贴袋为独立裁片，
    净样上版位置即表面定位标记（Drill/Placement）。

    独立定位（与 INSET 锚点解耦）：袋口外上角 = 自有效腰口的侧缝腰点垂直向下
    front_patch_top_drop、水平向内 front_patch_top_inset（弯腰头时腰头独立成片，
    裤身顶边为下腰头线，基准取下侧缝腰点 B'；直腰头取腰外缝顶点 B，行为不变，
    统一走 steps.front_steps.effective_waist）；袋口宽
    front_patch_width 向内量取，袋身高 front_patch_height 向下量取。
    净形四形态（§五 net_outline_type）：
      - "rectangle" 方底四边形；
      - "baker_shield" 盾形尖底：底边换为底中尖点（额外加深
        front_patch_tip_depth）的五边形；
      - "angular" 底角斜切：两底角各斜切 front_patch_chamfer 的六边形；
      - "custom" 全自定义：角点列表 front_patch_custom_points（相对锚点），
        每边形态 front_patch_custom_edges 逐边给（直线或带弧高/弧顶弧线）。
    袋底宽 front_patch_bottom_width 可独立于袋口宽（0 = 同宽，底边两侧
    对称内收；rectangle/custom 不涉及）；front_patch_rotate_deg 绕袋口
    外上角整体旋转（顺时针为正），各形态与 custom 均生效。
    缝份与缩水不在本步处理：工程口径为先画后裁，裁片分离后由裁切层
    统一加缩水与缝边（§四.2 的反折/包缝量届时再扩）。
    依据：打版流程.md「前口袋打版过程」；前口袋绘制.md §四、§五。
    """
    o = ctx.options
    if not o.front_patch:
        return None                     # 开关关闭，可选步骤跳过

    step = "draw_front_patch_pocket"
    b, _, _ = effective_waist(ctx)              # O：弯腰头 = 下侧缝腰点 B'，直腰头 = 腰外缝顶点 B
    a = Point(b.x + o.front_patch_top_inset,
              b.y - o.front_patch_top_drop)     # 袋口外上角（侧缝侧）
    w, h = o.front_patch_width, o.front_patch_height
    shape = o.front_patch_shape

    # 净形（顺时针：外上角 → 内上角 → 向下绕行，Y 向上坐标系）；
    # 袋底宽可独立于袋口宽（底边两侧对称内收 bi，负值 = 外扩）
    bw = o.front_patch_bottom_width or w
    bi = (w - bw) / 2
    if shape == "baker_shield":
        net = [a, Point(a.x + w, a.y),
               Point(a.x + w - bi, a.y - h),
               Point(a.x + w / 2, a.y - h - o.front_patch_tip_depth),
               Point(a.x + bi, a.y - h)]
    elif shape == "angular":
        c = o.front_patch_chamfer
        net = [a, Point(a.x + w, a.y),
               Point(a.x + w - bi, a.y - h + c),
               Point(a.x + w - bi - c, a.y - h),
               Point(a.x + bi + c, a.y - h),
               Point(a.x + bi, a.y - h + c)]
    elif shape == "custom":
        # 全自定义：角点相对锚点给定，逐边可选直线或带弧高弧线
        net = [Point(a.x + dx, a.y + dy)
               for dx, dy in o.front_patch_custom_points]
    else:                                           # rectangle
        net = [a, Point(a.x + w, a.y),
               Point(a.x + w, a.y - h),
               Point(a.x, a.y - h)]

    # 整体旋转：绕袋口外上角 a（调整贴袋摆放角度，顺时针为正，
    # Y 向上坐标系取负角）
    if o.front_patch_rotate_deg != 0:
        net = [p.rotate_around(a, -o.front_patch_rotate_deg) for p in net]

    last = None
    for i in range(len(net)):
        ctx.add_point(f"front.patch_net_pt{i + 1}", net[i],
                      step=step,
                      basis=f"净形角点 {i + 1}（{shape}，前口袋绘制.md §五）",
                      label=f"贴袋净角{i + 1}")
        nxt = net[(i + 1) % len(net)]
        bulge, at = (o.front_patch_custom_edges[i]
                     if shape == "custom" else (0.0, 0.5))
        if shape == "custom" and bulge != 0.0:
            last = ctx.add_curve(
                f"front.patch_net_seg{i + 1}",
                curves.arc_through(net[i], nxt, bulge=bulge, bulge_at=at),
                step=step,
                basis=f"净样第 {i + 1} 段：弧线，弧高 {bulge}、"
                      f"弧顶位置 {at}（custom，§五）",
                label=f"贴袋净样{i + 1}段")
        else:
            last = ctx.add_line(f"front.patch_net_seg{i + 1}",
                                LineSegment(net[i], nxt),
                                step=step,
                                basis=f"净样第 {i + 1} 段（表面定位标记，§四.1）",
                                label=f"贴袋净样{i + 1}段", role="struct")
    return last
