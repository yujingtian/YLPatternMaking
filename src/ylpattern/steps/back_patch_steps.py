"""后贴袋绘制步骤：表面外贴式（PATCH）独立样板（后贴袋绘制.md §一~§三）。

对应 打版流程.md「后贴袋绘制」：
  - 独立定位（基于育克底线 ∩ 后浪线的角点，§一 参照坐标系 Σ_Back）：
    原点 O = 后机头下口线后浪端点（back.yoke_cb_point，落在后浪线上）；
    局部坐标系 û = 自后浪朝侧缝（沿约克底线 P0->PN 方向）、v̂ = û 下方法向
    （朝脚口、入裤身）；定位点 P0（袋口近后浪侧顶点）=
    O + inset_x·û + drop_y·v̂，即"距离后浪线的距离"沿约克底线朝侧缝、
    "距离约克底线的距离"向下；
  - 净形四形态（§二.1 形态路由）：rectangle / baker_shield / angular / custom，
    局部 u-v 系（u 朝侧缝 +、v 向下 +，V0=(0,0) 近后浪侧）生成顶点序列；
  - 全局仿射（§二.2）：P_i = P0 + R(θ)·V_i，θ 顺时针为正，绕 P0 旋转；
    θ=0 时袋口沿 û（约克底线方向）≈ 平行后腰线（打版流程.md：默认平行后腰线）。

依赖后机头（back_yoke）：定位原点为机头下口线后浪端点，须先开 back_yoke。
先画后裁：只上版净样边界（表面定位标记 02_MARKING / 净样板 03_PATCH_NET），
不做布尔裁除；缝份/缩水留待裁切层。形态路由与边形态口径同前贴袋
（前口袋绘制.md §四、§五），区别仅在定位基准（前贴袋自腰外缝顶点、
后贴袋自育克底线 ∩ 后浪线）与局部坐标系方向（u 朝侧缝）。
"""

from __future__ import annotations

import math

from ..draft import DraftContext, NamedCurve, NamedLine
from ..draft import curves
from ..geometry import LineSegment, Point


def draw_back_patch_pocket(ctx: DraftContext) -> NamedLine | NamedCurve | None:
    """后贴袋（表面外贴式 PATCH，打版流程.md「后贴袋绘制」，可选步骤）：
    开关 back_patch 开启才绘制，否则整步跳过。

    独立定位（后贴袋绘制.md §一 参照坐标系 Σ_Back）：
      原点 O = 育克底线 ∩ 后浪线 = 后机头下口线后浪端点（back.yoke_cb_point，
      由后机头步骤沿后浪线量取 D_cb 得到，落在后浪线上）；故依赖 back_yoke。
      局部坐标系：û = 自后浪朝侧缝（沿约克底线 P0->PN 方向，§一 X 轴）、
      v̂ = û 的下方法向（朝脚口、入裤身，§一 Y 轴）；定位点 P0（袋口近后浪
      侧顶点）= O + inset_x·û + drop_y·v̂（"距离后浪线的距离"沿约克底线朝侧缝、
      "距离约克底线的距离"向下，§一.2）。
    净形四形态（§二.1，局部 u-v：u 朝侧缝 +、v 向下 +，V0=(0,0) 近后浪侧，顺时针）：
      - "rectangle" 方底四边形；
      - "baker_shield" 盾形尖底：底边换为底中尖点（额外加深
        back_patch_tip_depth）的五边形；
      - "angular" 底角斜切：两底角各斜切 back_patch_chamfer 的六边形；
      - "custom" 全自定义：角点列表 back_patch_custom_points（局部 u-v，
        v 向下为正），每边形态 back_patch_custom_edges 逐边给
        （直线或带弧高/弧顶弧线）。
      袋底宽 back_patch_bottom_width 可独立于袋口宽（0 = 同宽，底边两侧
      对称内收；rectangle/custom 不涉及）。
    全局仿射（§二.2）：P_i = P0 + R(θ)·V_i，θ = back_patch_rotate_deg
    （顺时针为正，局部 v 向下系的顺时针），绕 P0 旋转；θ=0 时袋口沿 û
    （约克底线方向）≈ 平行后腰线（打版流程.md：默认平行后腰线）。
    缝份与缩水不在本步处理：工程口径为先画后裁，裁片分离后由裁切层
    统一加缩水与缝边。
    依据：打版流程.md「后贴袋绘制」；后贴袋绘制.md §一~§三。
    """
    o = ctx.options
    if not o.back_patch:
        return None                     # 开关关闭，可选步骤跳过

    if "back.yoke_cb_point" not in ctx.sheet:
        raise ValueError("后贴袋依赖后机头下口线定位，请先开启 back_yoke"
                         "（打版流程.md：后贴袋以育克底线 ∩ 后浪线为原点）")

    step = "draw_back_patch_pocket"
    origin = ctx.point("back.yoke_cb_point")        # O：育克底线 ∩ 后浪线
    pn = ctx.point("back.yoke_side_point")          # PN：机头侧缝端点
    # 局部坐标系（§一）：û 自后浪朝侧缝（沿约克底线）、v̂ 向下（入裤身）
    u_hat = (pn - origin).normalized()
    v_hat = u_hat.perpendicular()
    if v_hat.dy > 0:
        v_hat = v_hat.scale(-1)
    # P0：袋口近后浪侧顶点 = O + inset_x·û + drop_y·v̂
    p0 = (origin
          + u_hat.scale(o.back_patch_inset_x)
          + v_hat.scale(o.back_patch_drop_y))
    w, h = o.back_patch_width, o.back_patch_height
    shape = o.back_patch_shape

    # 净形局部顶点（§二.1，u 朝侧缝 +、v 向下 +，V0=(0,0) 近后浪侧，顺时针）；
    # 袋底宽可独立于袋口宽（底边两侧对称内收 bi，负值 = 外扩）
    bw = o.back_patch_bottom_width or w
    bi = (w - bw) / 2
    if shape == "baker_shield":
        local = [(0.0, 0.0), (w, 0.0),
                 (w - bi, h), (w / 2, h + o.back_patch_tip_depth), (bi, h)]
    elif shape == "angular":
        c = o.back_patch_chamfer
        local = [(0.0, 0.0), (w, 0.0),
                 (w, h - c), (w - c, h), (c, h), (0.0, h - c)]
    elif shape == "custom":
        local = [(float(u), float(v)) for u, v in o.back_patch_custom_points]
    else:                                           # rectangle
        local = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]

    # 全局仿射（§二.2）：P_i = P0 + R(θ)·V_i，θ 顺时针为正（v 向下系）
    theta = math.radians(o.back_patch_rotate_deg)
    ct, st = math.cos(theta), math.sin(theta)

    def _to_global(u: float, v: float) -> Point:
        # R(θ) 在 v 向下系为顺时针：u' = u·cosθ − v·sinθ、v' = u·sinθ + v·cosθ
        u_rot = u * ct - v * st
        v_rot = u * st + v * ct
        return p0 + u_hat.scale(u_rot) + v_hat.scale(v_rot)

    net = [_to_global(u, v) for u, v in local]

    ctx.add_point("back.patch_origin", origin,
                  step=step,
                  basis="育克底线 ∩ 后浪线（后机头下口线后浪端点，"
                        "后贴袋绘制.md §一 原点 O）",
                  label="后贴袋定位原点")
    ctx.add_point("back.patch_anchor", p0,
                  step=step,
                  basis=f"原点 + inset_x {o.back_patch_inset_x}·û"
                        f" + drop_y {o.back_patch_drop_y}·v̂"
                        "（距后浪线 / 距约克底线，后贴袋绘制.md §一.2 P0）",
                  label="后贴袋袋口近后浪侧顶点P0")

    last: NamedCurve | NamedLine | None = None
    n = len(net)
    for i in range(n):
        ctx.add_point(f"back.patch_net_pt{i + 1}", net[i],
                      step=step,
                      basis=f"净形角点 {i + 1}（{shape}，"
                            "后贴袋绘制.md §二.1）",
                      label=f"后贴袋净角{i + 1}")
        nxt = net[(i + 1) % n]
        bulge, at = (o.back_patch_custom_edges[i]
                     if shape == "custom" else (0.0, 0.5))
        if shape == "custom" and bulge != 0.0:
            last = ctx.add_curve(
                f"back.patch_net_seg{i + 1}",
                curves.arc_through(net[i], nxt, bulge=bulge, bulge_at=at),
                step=step,
                basis=f"净样第 {i + 1} 段：弧线，弧高 {bulge}、"
                      f"弧顶位置 {at}（custom，§二.1）",
                label=f"后贴袋净样{i + 1}段")
        else:
            last = ctx.add_line(f"back.patch_net_seg{i + 1}",
                                LineSegment(net[i], nxt),
                                step=step,
                                basis=f"净样第 {i + 1} 段（表面定位标记，§三）",
                                label=f"后贴袋净样{i + 1}段", role="struct")
    return last
