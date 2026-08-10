"""后机头/育克绘制步骤：每个函数对应手工打版的一笔。

对应 打版流程.md「后机头/育克绘制」：
  - 端点定位：弯腰头自下腰头顶点、直腰头自腰头线顶点，沿后浪线/外缝线
    向下量取弧长得机头下口两端点（后机头绘制.md §1 弧长量取驱动）；
  - 下口线：两端点连线，中间可插任意控制锚点，逐段 line/arc/bezier
    （§2 N-Point 分段拓扑）；无锚点即直线。

先画后裁：只上版分割下口线与端点/锚点，机头裁片分离、缝份/缩水留待裁切层。
不实现：§4 后中正交约束（首段法向自动锁定）、§5 吃势补偿与对位标记（工艺层）；
省量吸收（§3）已由 PatternOptions.back_waist_dart（约克转移量）在后腰长口径体现。
"""

from __future__ import annotations

from ..draft import DraftContext, NamedCurve, NamedLine
from ..draft import curves
from ..geometry import CubicBezier, LineSegment, Point
from ..params import WaistbandType


def _reverse_bezier(b: CubicBezier) -> CubicBezier:
    """反向三次贝塞尔：终点 -> 起点重参数化，弧长不变。

    用于沿外缝髋腰弧自腰端（t=1）向下量取：原曲线 臀(t=0)->腰(t=1)，
    反向后 腰(t=0)->臀(t=1)，point_at_length(d) 即自腰端下行 d 处。
    """
    return CubicBezier(b.p3, b.p2, b.p1, b.p0)


def draw_back_yoke(ctx: DraftContext) -> NamedCurve | NamedLine | None:
    """后机头/育克下口分割线（打版流程.md「后机头/育克绘制」，可选步骤）：
    开关 back_yoke 开启才绘制，否则整步跳过。

    端点定位（后机头绘制.md §1 弧长量取驱动）：
      - P0（后浪端点）：自腰头内缝顶点沿后浪线（后中斜线 + 大裆弯弧复合链）
        向下量取 back_yoke_cb_dist（D_cb）；
      - PN（侧缝端点）：自腰头外缝顶点沿外缝线（髋腰弧反向 + 大腿弧 + 小腿弧
        复合链，自腰端向下）量取 back_yoke_side_dist（D_side）。
      弯腰头时腰头独立成片、机头上口为下腰头线，量取起点改为下腰头两端点
      （沿后浪线/外缝线再下移腰头宽 W）；直腰头量取起点即腰头线两端点。
      D_cb − D_side = 倾斜落差 ΔH（§1）。

    下口线（§2 N-Point 分段拓扑）：
      - 中间控制锚点 back_yoke_mid_anchors：每个 (u, depth)，u = P0->PN 弦上
        位置比例 0~1（严格递增）、depth = 偏离弦的深度（cm，正值向下凸入裤身、
        0 = 压弦、负值上凸）；空列表 = 直线下口（打版流程.md：无锚点即直线）。
      - 逐段形态 back_yoke_edges（个数 = 锚点数 + 1）：line/arc/bezier，
        与袋布/小表袋边形态同口径（curves.edge_geom）。
    先画后裁：只上版下口分割线与端点/锚点；上口（腰头线/下腰头线）已存在，
    两侧（后浪/外缝）为既有曲线，不重画--裁片分离、缝份/缩水留待裁切层。
    依据：打版流程.md「后机头/育克绘制」；后机头绘制.md §1、§2。
    """
    o = ctx.options
    if not o.back_yoke:
        return None

    step = "draw_back_yoke"
    curved = o.waistband_type is WaistbandType.CURVED
    W = o.waistband_width

    # 量取起点：弯腰头 = 下腰头两端点（沿接缝再下移 W）；直腰头 = 腰头线两端点
    if curved:
        cb_top = ctx.point("back.lower_waist_center_point")   # O'
        side_top = ctx.point("back.lower_waist_side_point")   # X'
        d_cb = W + o.back_yoke_cb_dist
        d_side = W + o.back_yoke_side_dist
        ref = "下腰头顶点"
    else:
        cb_top = ctx.point("back.rise_top_point")             # O
        side_top = ctx.point("back.waist_side_point")         # X
        d_cb = o.back_yoke_cb_dist
        d_side = o.back_yoke_side_dist
        ref = "腰头线顶点"

    # P0：沿后浪线（后中斜线 + 大裆弯弧）自 cb_top 向下量取 d_cb
    rise_slant = ctx.line("back.rise_slant")
    rise_curve = ctx.curve("back.rise_curve")
    p0 = curves.point_along_chain((rise_slant, rise_curve), d_cb)

    # PN：沿外缝线自 side_top 向下量取 d_side
    #   髋腰弧原方向 臀(t=0)->腰(t=1)，反向得 腰->臀；再接大腿弧（臀->膝）、
    #   小腿弧（膝->脚口），构成自腰端向下的复合链
    hw = ctx.curve("back.outseam_hip_waist")
    upper = ctx.curve("back.outseam_upper")
    lower = ctx.curve("back.outseam_lower")
    pn = curves.point_along_chain(
        (_reverse_bezier(hw), upper, lower), d_side)

    ctx.add_point("back.yoke_cb_point", p0,
                  step=step,
                  basis=f"沿后浪线自{ref}向下量取 D_cb {o.back_yoke_cb_dist}"
                        + (f"（链上 {d_cb} = W {W} + D_cb，" if curved else "（")
                        + "后机头绘制.md §1）",
                  label="机头后浪端点P0")
    ctx.add_point("back.yoke_side_point", pn,
                  step=step,
                  basis=f"沿外缝线自{ref}向下量取 D_side {o.back_yoke_side_dist}"
                        + (f"（链上 {d_side} = W {W} + D_side，" if curved else "（")
                        + "后机头绘制.md §1）",
                  label="机头侧缝端点PN")

    # 下口线节点链：P0 -> [中间锚点] -> PN
    #   锚点 = 弦上 u 处 + 法向 depth；n 取朝下（入裤身）一侧，depth 正值下凸
    chord = pn - p0
    n = chord.normalized().perpendicular()
    if n.dy > 0:
        n = n.scale(-1)
    pts: list[Point] = [p0]
    for i, (u, depth) in enumerate(o.back_yoke_mid_anchors, 1):
        mid = p0.lerp(pn, u) + n.scale(depth)
        ctx.add_point(f"back.yoke_mid_pt{i}", mid,
                      step=step,
                      basis=f"下口中间锚点 {i}：弦上 {u} 处，法向偏移 {depth}"
                            "（正值下凸，后机头绘制.md §2）",
                      label=f"机头下口锚点{i}")
        pts.append(mid)
    pts.append(pn)

    # 逐段形态（line/arc/bezier，edge_geom 同袋布/小表袋口径）
    last: NamedCurve | NamedLine | None = None
    for i, spec in enumerate(o.back_yoke_edges):
        a, b = pts[i], pts[i + 1]
        geom = curves.edge_geom(a, b, spec)
        basis = f"下口线第 {i + 1} 段（{spec[0]}，后机头绘制.md §2.2）"
        if isinstance(geom, LineSegment):
            last = ctx.add_line(f"back.yoke_bottom_seg{i + 1}", geom,
                                step=step, basis=basis,
                                label=f"机头下口{i + 1}段", role="struct")
        else:
            last = ctx.add_curve(f"back.yoke_bottom_seg{i + 1}", geom,
                                 step=step, basis=basis,
                                 label=f"机头下口{i + 1}段")
    return last
