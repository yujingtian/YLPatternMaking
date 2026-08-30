"""测量层：识别结果 -> 尺寸单 8 键（层 1）+ 可直接量测选项（层 2）。

全部口径经 5015 真件实证（.doc/工厂DXF逆向解析.md §4，金标：
hip=95.3 / W=64.8 / back_intake≈5.5 / delta 原始≈2.2）：

- **还原**：成品cm = 净样mm ×(1−率)÷10；横(围度/X)=weft、直(裤长/Y)=warp
  （文件名 W15%-L8% 主源，块内 Annotation 交叉校验，冲突即 ReverseError）。
- **围度结构分化**（最大陷阱）：臀围线在裆上、四片合围，hip = 2×(前弦+后弦)；
  毗围/中裆/脚口在腿管上、前后两片合围，单腿围 = (前弦+后弦) 直取。
- **导线签名**：毗围线 = 一端落裆尖另一端落侧缝（端点即裆尖）；臀围线 =
  前中端落在浪弧上（高于裆尖）；三根近水平线按 y 序 = 膝/毗/臀。
- **腰围主口径** = 腰头独立裁片两长边中的**缝边（下口，较长那条）**×0.85
  ——弯腰头体侧向下展宽、下口弧长于上口；交叉核对 = 组成式
  2×(前腰段 + 袋口段 + 机头上口)，前片/机头顶边与腰头缝边互差 >0.5cm 告警。
- **机头是覆合件**：后大片顶边(238.2) ≌ 机头底边(239.4)，腰口在机头上弧；
  back_intake = 机头刚体平移拼回后片后，成衣腰 CB → 臀 CB 的 |dx|/|dy|
  ×(0.85/0.92)×15。
- **前片挖削**：腰口 = 腰边(CF→袋口起) + 前代融合片顶边越过袋口弧 CF 端
  的那段（袋口段，非袋贴顶边全长——后者含 25mm 搭面板）；袋口弧前后
  两处(162.6mm)互为全等校验。
- **浪/缝含腰头**：净浪链×0.92 + 腰头带宽×0.92（带宽竖直 = 经向）。
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from .errors import ReverseError
from .geomops import (chain_above, chain_between_shorter, chain_congruence_rms,
                      chain_length_mm, chord_profile, chord_span_mm,
                      corner_turns, nearest_vertex, point_ring_nearest,
                      resample_chain, rigid_fit_offset, shallow_run_at_extreme,
                      strip_long_edges, strip_width_mm)
from .model import FactoryDoc, OpenLine, Point, Ring, SubPiece
from .reader import parse_shrinkage_annotation, parse_shrinkage_filename

# 层 1 的 8 个测量键（与 params.measurements 对齐；cm）
SIZE_KEYS = ("waist", "hip", "thigh", "knee", "hem",
             "front_rise", "back_rise", "outseam")

_GUIDE_TOL = 6.0        # 导线端点贴环容差（mm）
_TURN_DEG = 50.0        # 顶链角点阈值（度）
_MEASURE_ROLES = ("front_body", "back_body", "waistband", "fused_pocket",
                  "yoke")


@dataclass(frozen=True)
class Calibration:
    """缩水标定：weft=横(围度/X)、warp=直(裤长/Y)。"""

    weft: float
    warp: float
    source: str

    @classmethod
    def from_doc(cls, doc: FactoryDoc) -> "Calibration":
        fw, fp = parse_shrinkage_filename(doc.path)
        anns = {p.meta.annotation for p in doc.pieces
                if p.meta.annotation}
        aw = ap = None
        for text in anns:
            w, p = parse_shrinkage_annotation(text)
            if w is not None:
                aw, ap = w, p
        if fw is not None and aw is not None and \
                (abs(fw - aw) > 0.005 or abs(fp - ap) > 0.005):
            raise ReverseError(
                f"缩水双源冲突：文件名 W{fw:.0%}-L{fp:.0%} vs 注记 "
                f"横{aw:.0%}直{ap:.0%}")
        if fw is not None:
            return cls(weft=fw, warp=fp, source="文件名")
        if aw is not None:
            return cls(weft=aw, warp=ap, source="Annotation")
        raise ReverseError("缩水率缺失：文件名无 W%-L% 标记且无 Annotation 注记")

    def x_cm(self, mm: float) -> float:
        """横/围度向：mm -> 成品 cm。"""
        return mm * (1.0 - self.weft) / 10.0

    def y_cm(self, mm: float) -> float:
        """直/裤长向：mm -> 成品 cm。"""
        return mm * (1.0 - self.warp) / 10.0


@dataclass
class BodyGeom:
    """一个身片（前/后）的锚定几何。"""

    role: str
    ring: Ring
    hip: OpenLine
    thigh: OpenLine
    knee: OpenLine
    cb_side: str                 # 前中(CF)/后中(CB)所在 x 极值侧
    crotch_tip: Point            # 裆尖（毗围线前中端点）
    waist_cb: Point              # 腰口前中/后中角点
    waist_side: Point            # 腰口侧缝角点（前片 = 袋口侧端）
    hem_side_idx: int            # 脚口侧缝角点顶点序
    notes: list[str] = field(default_factory=list)

    def chord_mm(self, line: OpenLine) -> float:
        span = chord_span_mm(self.ring, line.pts[0], line.pts[-1])
        if span is None:
            raise ReverseError(
                f"{self.role} 导线未切到净样环：{line.pts[0]}->{line.pts[-1]}")
        return span

    def hem_chord_mm(self) -> float:
        """脚口弦：贴底的近水平线（脚口边近似水平）。"""
        x0, ymin, x1, _ = self.ring.bbox()
        span = chord_span_mm(self.ring, Point(x0 - 100.0, ymin + 0.5),
                             Point(x1 + 100.0, ymin + 0.5))
        if span is None:
            raise ReverseError(f"{self.role} 脚口弦测量失败")
        return span


def _is_horizontal(ln: OpenLine) -> bool:
    s = ln.slope_deg()
    return abs(s) <= 10.0 or abs(s) >= 170.0


def body_geometry(sub: SubPiece, role: str) -> BodyGeom:
    """身片锚定：三导线识别 + 裆尖/腰角点定位。"""
    ring = sub.net_or_gross()
    guides = [ln for ln in sub.internals if _is_horizontal(ln)]
    if len(guides) != 3:
        raise ReverseError(
            f"{role} 近水平导线 {len(guides)} 根（期望 3：膝/毗/臀）——"
            "导线结构变化，人工核对")
    guides.sort(key=lambda ln: ln.midpoint().y)
    knee, thigh, hip = guides
    if not (knee.midpoint().y < thigh.midpoint().y < hip.midpoint().y):
        raise ReverseError(f"{role} 导线 y 序异常")

    # 前中/后中侧：膝线~臀线+80 窗口内的 x 极值侧（裆区）
    lo, hi = knee.midpoint().y - 50.0, hip.midpoint().y + 80.0
    window = [p for p in ring.pts if lo <= p.y <= hi]
    if not window:
        raise ReverseError(f"{role} 裆区窗口为空")
    cb_side = ("min" if min(p.x for p in window)
               <= ring.bbox()[0] + 1.0 else "max")
    pick = (lambda pts: min(pts, key=lambda p: p.x)) if cb_side == "min" \
        else (lambda pts: max(pts, key=lambda p: p.x))
    extreme = pick(window)

    # 毗围线签名：前中端点贴裆区极值点（裆尖）
    def cb_end(ln: OpenLine) -> Point:
        a, b = ln.pts[0], ln.pts[-1]
        return a if a.distance_to(extreme) < b.distance_to(extreme) else b

    if cb_end(thigh).distance_to(extreme) > _GUIDE_TOL:
        raise ReverseError(
            f"{role} 毗围线端点不贴裆尖（距 "
            f"{cb_end(thigh).distance_to(extreme):.1f}mm）——毗围/臀围误配")
    crotch_tip = cb_end(thigh)

    # 顶链（臀线以上）与腰角点（角点 = 方向突变 ≥ 阈值；离散弧段内
    # 逐顶点转角小，真折角集中在单顶点）
    top = chain_above(ring, hip.midpoint().y)
    if not top:
        raise ReverseError(f"{role} 臀线以上无顶链")
    turns = corner_turns(top, _TURN_DEG)
    # 侧缝端参考取自顶链（裆区窗口上限 hip+80 会切掉高位侧腰角）
    side_pt = max(top, key=lambda p: p.x) if cb_side == "min" \
        else min(top, key=lambda p: p.x)
    candidates = [p for _, p, _ in turns] or [top[0], top[-1]]
    waist_cb = min(candidates, key=lambda p: p.distance_to(extreme))
    waist_side = min(candidates, key=lambda p: p.distance_to(side_pt))

    x0, ymin, x1, _ = ring.bbox()
    hem_corner = Point(x1, ymin) if cb_side == "min" else Point(x0, ymin)
    hem_side_idx = nearest_vertex(ring, hem_corner)

    notes: list[str] = []
    if len(turns) not in (2, 3):
        notes.append(f"{role} 顶链角点 {len(turns)} 个（常态 2~3），锚点取最近")
    return BodyGeom(role=role, ring=ring, hip=hip, thigh=thigh, knee=knee,
                    cb_side=cb_side, crotch_tip=crotch_tip, waist_cb=waist_cb,
                    waist_side=waist_side, hem_side_idx=hem_side_idx,
                    notes=notes)


@dataclass
class MeasuredSize:
    """一个码的 8 键测量 + 口径追踪行。"""

    size: str
    values: dict[str, float]
    trace: list[str]
    extras: dict[str, float] = field(default_factory=dict)   # 组成式等旁证


def _shorter_arc(ring: Ring, i0: int, i1: int) -> list[Point]:
    return chain_between_shorter(ring, i0, i1)


def yoke_edges(yoke_ring: Ring) -> tuple[list[Point], list[Point]]:
    """机头两长边（上 = 腰口弧、下 = 拼后片直边），CB 端（x 小侧）在链首。

    缓段游程提取（``shallow_run_at_extreme``）：后中端内收 5.5/15 的斜端
    属陡段不入长边，两长边端点即真四角；bbox 角点锚会被斜端的虚拟角
    吸偏（实测顶弧虚长 +20mm），禁用。
    """
    top = shallow_run_at_extreme(yoke_ring, "top")
    bottom = shallow_run_at_extreme(yoke_ring, "bottom")
    for chain in (top, bottom):
        if chain[0].x > chain[-1].x:
            chain.reverse()
    return top, bottom


def _yoke_arcs(yoke_ring: Ring) -> tuple[float, float]:
    """机头 (CB 端弧, 侧端弧) 净长 mm：上口链端 -> 底边链端的较短弧。"""
    top, bottom = yoke_edges(yoke_ring)
    out = []
    for i in (0, -1):
        a = nearest_vertex(yoke_ring, top[i])
        b = nearest_vertex(yoke_ring, bottom[i])
        out.append(chain_length_mm(_shorter_arc(yoke_ring, a, b)))
    return out[0], out[1]


def _pocket_bridge(sub: SubPiece) -> tuple[float, float, list[Point]]:
    """前代融合片：袋口段（顶边越过袋口弧 CF 端部分）+ 侧边上段长。

    返回 (bridge_mm, side_edge_mm, mouth_arc_pts)。袋口段 = 从弧的顶边端
    沿顶边走到远端的链（顶边两条走链中较长者）；侧边段 = 弧侧端与顶边
    远端间的较短弧（腰口侧缝以上袋身外边）。
    """
    ring = sub.net_or_gross()
    arcs = [ln for ln in sub.internals if 100.0 <= ln.length() <= 200.0]
    if len(arcs) != 1:
        raise ReverseError(f"前代融合片层 8 袋口弧 {len(arcs)} 根（期望 1）")
    arc = arcs[0]
    a, b = arc.pts[0], arc.pts[-1]
    # 顶边端 = y 较高者（顶边在上）
    if a.y < b.y:
        a, b = b, a
    i_a = nearest_vertex(ring, a)
    i_b = nearest_vertex(ring, b)
    n = len(ring.pts)

    def level_walk(start: int, step: int) -> list[Point]:
        """沿环绕走，保持 y ≥ 沿途最大 y − 10mm（顶边走链）。"""
        out, ymax = [ring.pts[start]], ring.pts[start].y
        idx = start
        while True:
            idx = (idx + step) % n
            p = ring.pts[idx]
            if p.y < ymax - 10.0:
                break
            ymax = max(ymax, p.y)
            out.append(p)
            if idx == start:
                break
        return out

    fwd = level_walk(i_a, +1)
    rev = level_walk(i_a, -1)
    bridge = fwd if chain_length_mm(fwd) >= chain_length_mm(rev) else rev
    far_idx = nearest_vertex(ring, bridge[-1])
    side_edge = _shorter_arc(ring, i_b, far_idx)
    return chain_length_mm(bridge), chain_length_mm(side_edge), list(arc.pts)


def _facing_edges(sub: SubPiece,
                  mouth_pts: list[Point]) -> tuple[float, float, list[Point]] | None:
    """前代融合片净边袋贴弧提取（facing 内边 L_inner 的工厂对应物）。

    片净边与引擎 Ω_facing 同构（用户口径 2026-08-30：片内两根弧，内部
    = 袋口缝线、**边界大弧 = 袋贴内边**）：顶边 = 腰弧段（O→P_fw）、
    右边 = 外缝段（P_fs→O）、底部大弧 = L_inner；袋口弧两端点把两直边
    各切出袋口段（p1_dist/p2_drop，见 _pocket_bridge）与袋贴段
    （facing_width/facing_side_w）。

    提取两步：
    1. 以袋口弦 P1m→P2m 定侧，背离腰/侧角 B′ 一侧的连续负侧游程 =
       大弧 + 两端越弦的直边杂点（弦线与直边交越在 P1/P2 之外的直边上，
       5015 实测各带 1 个杂点）；
    2. 折角修剪：游程两端各延一顶点后做 ≥25° 折角检测——直边→大弧
       换向角实测 ~85°、弧内离散转角 ≤4°，阈值居中；首个/末个折角 =
       大弧端 C（贴侧端 = P_fs 对应）/A（贴腰端 = P_fw 对应），杂点
       随修剪剔除。
    返回 (A→P1m 顶边段 mm, P2m→C 右边段 mm, 大弧顶点列 A 在首)；
    净边无大弧（游程/折角不足）返回 None。
    """
    ring = sub.net_or_gross()
    pts = list(ring.pts)
    n = len(pts)
    a, b = mouth_pts[0], mouth_pts[-1]
    if a.y < b.y:
        a, b = b, a                    # a = 腰端（顶边）、b = 侧端（右边）
    i_a = nearest_vertex(ring, a)
    i_b = nearest_vertex(ring, b)
    u = pts[i_b] - pts[i_a]
    if u.length < 1e-9:
        return None
    ux, uy = u.dx / u.length, u.dy / u.length

    # 自腰端沿环走一圈，收集弦负侧（s < −1mm）连续游程 = 大弧 + 杂点
    run: list[int] = []
    started = False
    for k in range(1, n + 1):
        i = (i_a + k) % n
        w = pts[i] - pts[i_a]
        if w.dx * -uy + w.dy * ux < -1.0:
            started = True
            run.append(i)
        elif started:
            break
    if len(run) < 4:
        return None

    # 折角修剪：延伸链上首/末折角 = 大弧端 C/A
    ext = [pts[(run[0] - 1) % n]] + [pts[i] for i in run] \
        + [pts[(run[-1] + 1) % n]]
    turns = corner_turns(ext, 25.0)
    if len(turns) < 2:
        return None
    p_first = turns[0][0] - 1          # 折角在 run 内的位置（ext 偏移 1）
    p_last = turns[-1][0] - 1
    c_idx = run[p_first]
    a_idx = run[p_last]
    # A = 沿环更近腰端者（顶边袋贴段），C = 更近侧端者（右边袋贴段）
    if chain_length_mm(_shorter_arc(ring, a_idx, i_a)) > \
            chain_length_mm(_shorter_arc(ring, a_idx, i_b)):
        a_idx, c_idx = c_idx, a_idx
    inner = [pts[i] for i in run[p_first:p_last + 1]]
    if inner[0] != pts[a_idx]:
        inner.reverse()
    return (chain_length_mm(_shorter_arc(ring, a_idx, i_a)),
            chain_length_mm(_shorter_arc(ring, i_b, c_idx)), inner)


def measure_8(size: str, mapping: dict[str, SubPiece],
              calib: Calibration) -> MeasuredSize:
    """尺寸单 8 键（cm）。"""
    missing = [r for r in _MEASURE_ROLES if r not in mapping]
    if missing:
        raise ReverseError(f"码 {size} 缺测量关键角色：{', '.join(missing)}")
    fg = body_geometry(mapping["front_body"], "front")
    bg = body_geometry(mapping["back_body"], "back")
    trace: list[str] = []
    ex: dict[str, float] = {}

    f_hip, b_hip = fg.chord_mm(fg.hip), bg.chord_mm(bg.hip)
    f_th, b_th = fg.chord_mm(fg.thigh), bg.chord_mm(bg.thigh)
    f_kn, b_kn = fg.chord_mm(fg.knee), bg.chord_mm(bg.knee)
    f_hm, b_hm = fg.hem_chord_mm(), bg.hem_chord_mm()
    hip = calib.x_cm(2.0 * (f_hip + b_hip))
    thigh = calib.x_cm(f_th + b_th)
    knee = calib.x_cm(f_kn + b_kn)
    hem = calib.x_cm(f_hm + b_hm)
    trace += [
        f"hip=2*({f_hip:.1f}+{b_hip:.1f})*(1-{calib.weft:.0%}) = {hip:.2f}cm "
        "（四片合围×2）",
        f"thigh=({f_th:.1f}+{b_th:.1f})*(1-{calib.weft:.0%}) = {thigh:.2f}cm "
        "（腿管两片直取）",
        f"knee=({f_kn:.1f}+{b_kn:.1f})*.. = {knee:.2f}cm",
        f"hem=({f_hm:.1f}+{b_hm:.1f})*.. = {hem:.2f}cm",
    ]

    # 腰头独立裁片：两长边取缝边（较长=下口）
    wb_ring = mapping["waistband"].net_or_gross()
    edge_a, edge_b = strip_long_edges(wb_ring)
    la, lb = chain_length_mm(edge_a), chain_length_mm(edge_b)
    sew = max(la, lb)
    band_w_mm = strip_width_mm(wb_ring)
    waist = calib.x_cm(sew)
    trace.append(f"waist=腰头缝边(长边){sew:.1f}mm*(1-{calib.weft:.0%}) = "
                 f"{waist:.2f}cm（上口 {min(la, lb):.1f}）")
    band_cm = calib.y_cm(band_w_mm)

    # 机头两长边 + 两端弧（后片浪/外缝的腰端补足件——后大片顶边拼机头
    # 底边，腰口在机头上弧；后浪/后外缝 = 机头端弧 + 大身链）
    yoke = mapping["yoke"].net_or_gross()
    yoke_top, yoke_bottom = yoke_edges(yoke)
    yoke_top_mm = chain_length_mm(yoke_top)
    yoke_cb_arc, yoke_side_arc = _yoke_arcs(yoke)
    ex["yoke_top_mm"] = yoke_top_mm
    ex["yoke_cb_arc_mm"] = yoke_cb_arc
    ex["yoke_side_arc_mm"] = yoke_side_arc

    # 浪：腰口前/后中角点 -> 裆尖，较短弧（=浪链）×warp + 腰头竖直分量
    def rise(g: BodyGeom) -> float:
        ring = g.ring
        i_w = nearest_vertex(ring, g.waist_cb)
        i_c = nearest_vertex(ring, g.crotch_tip)
        return chain_length_mm(_shorter_arc(ring, i_w, i_c))

    f_rise = calib.y_cm(rise(fg)) + band_cm
    b_rise = calib.y_cm(rise(bg) + yoke_cb_arc) + band_cm

    # 外缝：前 = 袋口侧端 -> 脚口侧角 + 袋身侧边段；后 = 顶边侧端 -> 脚口
    def side_seam(g: BodyGeom) -> float:
        ring = g.ring
        i_w = nearest_vertex(ring, g.waist_side)
        return chain_length_mm(_shorter_arc(ring, i_w, g.hem_side_idx))

    f_side = side_seam(fg)
    b_side = side_seam(bg)
    outseam_b = calib.y_cm(b_side + yoke_side_arc) + band_cm

    # 前代融合片：袋口段 + 袋身侧边（补前片外缝腰端）
    bridge_mm, pocket_side_mm, mouth_pts = _pocket_bridge(mapping["fused_pocket"])
    outseam_f = calib.y_cm(f_side + pocket_side_mm) + band_cm
    ex["pocket_bridge_mm"] = bridge_mm
    ex["pocket_side_mm"] = pocket_side_mm

    # 袋贴内边 = 净边底部大弧（与引擎 Ω_facing 同构）：袋口弧端点把顶/
    # 右直边切出袋贴段（width/side_w 锚 = 引擎 P1→P_fw / P2→P_fs 同锚），
    # 大弧本体还原后取弦法向剖面 -> 弧高式（bulge）形态；定号参考 =
    # 袋口弦中点（恒在腰/侧角 B′ 一侧；袋口弧中点已向片内垂、可能越过
    # 内边弦线与大弧同侧，禁用），背离袋口弦为正（= 引擎正值向裤身
    # 内侧凹入，定向/镜像无关——两侧弧同向内凹、弦恒在外侧）
    facing = _facing_edges(mapping["fused_pocket"], mouth_pts)
    if facing is not None:
        fc_w_mm, fc_s_mm, inner_mm = facing
        ex["facing_waist_mm"] = fc_w_mm
        ex["facing_side_mm"] = fc_s_mm
        fx, fy = (1.0 - calib.weft) / 10.0, (1.0 - calib.warp) / 10.0
        eco = [Point(p.x * fx, p.y * fy) for p in inner_mm]
        m_mid = Point((mouth_pts[0].x + mouth_pts[-1].x) / 2.0,
                      (mouth_pts[0].y + mouth_pts[-1].y) / 2.0)
        sag, peak_at, _ = chord_profile(
            eco, Point(m_mid.x * fx, m_mid.y * fy))
        ex["facing_sagitta_cm"] = -sag
        ex["facing_peak_at"] = peak_at
        trace.append(f"袋贴内边弧：净边大弧还原后弦剖面 弧高 {-sag:.2f}cm @ "
                     f"弦位 {peak_at:.2f}（0=腰端；背离袋口弦为正）、腰段 "
                     f"{fc_w_mm:.1f} / 侧段 {fc_s_mm:.1f}mm")
    else:
        trace.append("告警：前代净边无袋贴大弧（袋口弦负侧游程缺失），"
                     "facing 内边族保持默认")

    # 袋口弧全等校验：前片袋口弧（腰边袋口角 -> 侧端）vs 融合片层 8 弧
    fr_ring = fg.ring
    top_chain = chain_above(fr_ring, fg.hip.midpoint().y)
    turns = corner_turns(top_chain, _TURN_DEG)
    side_end = nearest_vertex(fr_ring, fg.waist_side)
    if len(turns) >= 3:
        # 袋口起角 = 顶链角点中除腰 CF 角 / 袋口侧端外的剩余角（与链
        # 方向无关；离裆尖排序会把侧端角排进第 2 位，禁用）
        rest = [p for _, p, _ in turns
                if p.distance_to(fg.waist_cb) > 1e-6
                and p.distance_to(fg.waist_side) > 1e-6]
        i_cut = nearest_vertex(fr_ring, rest[0])
        mouth_body = _shorter_arc(fr_ring, i_cut, side_end)
        rms = chain_congruence_rms(mouth_body, list(mouth_pts))
        ex["mouth_congruence_rms"] = rms
        if rms > 2.0:
            trace.append(f"告警：袋口弧全等 RMS {rms:.2f}mm > 2（前片 vs 前代）")
        # 挖削袋口弧形态（mouth 参数反推用）：链定向腰端在前，各向异性
        # 还原到成衣空间（引擎净样 = 成衣尺寸）后取弦法向剖面；符号以
        # 环 bbox 中心为内侧参考（袋口恒在身片顶缘，中心必在片内）
        m_chain = list(mouth_body)
        if m_chain[0].distance_to(fr_ring.pts[i_cut]) > 1e-6:
            m_chain.reverse()
        fx, fy = (1.0 - calib.weft) / 10.0, (1.0 - calib.warp) / 10.0
        eco = [Point(p.x * fx, p.y * fy) for p in m_chain]
        x0, y0, x1, y1 = fr_ring.bbox()
        sag, peak_at, corners = chord_profile(
            eco, Point((x0 + x1) / 2.0 * fx, (y0 + y1) / 2.0 * fy))
        ex["mouth_sagitta_cm"] = sag
        ex["mouth_peak_at"] = peak_at
        ex["mouth_corners"] = corners
        trace.append(f"袋口弧形态：还原后弦法向剖面 弧高 {sag:.2f}cm @ 弦位 "
                     f"{peak_at:.2f}（0=腰头端）、折角 {len(corners)} 个"
                     f"（≥8°）")
        waist_part = chain_length_mm(_shorter_arc(
            fr_ring, nearest_vertex(fr_ring, fg.waist_cb), i_cut))
    else:
        waist_part = chain_length_mm(top_chain)
        trace.append("告警：前片顶链角点不足 3 个，腰边段退化为整顶链"
                     "（袋口挖削未识别，腰围组成式失真）")
    ex["front_waist_part_mm"] = waist_part

    # 组成式交叉核对
    comp = calib.x_cm(2.0 * (waist_part + bridge_mm + yoke_top_mm))
    ex["waist_composition_cm"] = comp
    if abs(comp - waist) > 0.5:
        trace.append(f"告警：腰围主口径 {waist:.2f} vs 组成式 {comp:.2f} 差 "
                     f"{abs(comp - waist):.2f}cm > 0.5")
    else:
        trace.append(f"waist 组成式核对 {comp:.2f}cm（前腰段 {waist_part:.1f} + "
                     f"袋口段 {bridge_mm:.1f} + 机头上口 {yoke_top_mm:.1f}）x2")

    outseam = (outseam_f + outseam_b) / 2.0
    trace += [
        f"front_rise=浪链{rise(fg):.1f}*(1-{calib.warp:.0%})+腰头{band_cm:.2f} "
        f"= {f_rise:.2f}cm",
        f"back_rise=(大身链{rise(bg):.1f}+机头CB弧{yoke_cb_arc:.1f})"
        f"*(1-{calib.warp:.0%})+腰头 = {b_rise:.2f}cm",
        f"outseam=mean(前 袋侧{pocket_side_mm:.1f}+身侧{f_side:.1f}"
        f"={f_side + pocket_side_mm:.1f}, 后 机头侧{yoke_side_arc:.1f}"
        f"+身侧{b_side:.1f}={b_side + yoke_side_arc:.1f})*(1-{calib.warp:.0%})"
        f"+腰头 = {outseam:.2f}cm（前 {outseam_f:.2f} / 后 {outseam_b:.2f}）",
    ]

    values = {"waist": waist, "hip": hip, "thigh": thigh, "knee": knee,
              "hem": hem, "front_rise": f_rise, "back_rise": b_rise,
              "outseam": outseam}
    return MeasuredSize(size=size, values=values, trace=trace, extras=ex)


def split_adjust_cm(front_mm: float, back_mm: float, calib: Calibration) -> float:
    """前后片调节量：(后−前)÷2 ×(1−weft)（前减后加口径，cm）。"""
    return calib.x_cm((back_mm - front_mm) / 2.0)


_ARC_PEAK_LO = 0.3125   # arc_through bulge_at=0 的弧顶弦位
_ARC_PEAK_SPAN = 0.375  # bulge_at 0→1 的弧顶弦位跨度


def _engine_bulge(sag_cm: float) -> float:
    """工厂真弧高 → 引擎 arc_through 的 bulge 参数（cm）。

    arc_through 控制点偏移 = bulge×8/3，其注释把双控制点偏移按单点 3/8
    计——实际三次贝塞尔中点偏移 = 3/4×控制偏移，**渲染弧高 = 2×bulge**
    （实测 bulge=2.0 → 弧高 4.00，curves.sag_curve 文档已注明该「经验
    系数」口径）。引擎默认值（mouth 0.5、outseam 0.3 等）均按此行为
    调定，故发射端换算、不动引擎（2026-08-30 用户复核发现 2× 夸张）。
    """
    return sag_cm / 2.0


def _engine_bulge_at(peak_at: float) -> tuple[float, bool]:
    """弧顶弦位 f → arc_through 的 bulge_at + 是否落在可表达域内。

    arc_through 弧顶（t=0.5，恒为最深点）弦位 = 0.375·bulge_at + 0.3125，
    即弧顶只能落在弦中段 [0.3125, 0.6875]；f 越界时钳至端点（形状近似）
    并由调用方披露。
    """
    b = (peak_at - _ARC_PEAK_LO) / _ARC_PEAK_SPAN
    return min(max(b, 0.01), 0.99), 0.0 < b < 1.0


# 小表袋 custom 形状量测阈值
_WATCH_GRAIN_TAN = 0.06     # 丝缕贴轴容差（tan ≈ 3.4°）
_WATCH_TOP_TOL = 0.5        # 顶边游程 y 容差（mm）
_WATCH_MOUTH_MIN = 5.0      # 顶边最短实长（mm）
_WATCH_TURN_DEG = 2.0       # 共线中间点折叠阈值（度，ET 直边离散）
_WATCH_ARC_SAG = 0.1        # 段内弦高超过即发射弧边（cm）
# 顶边对袋口弧安全距（cm）= 名义净距 1.2 + 框架倾斜余量 1.0：解析重建
# 在腰⊥侧缝的正交局部系里做，引擎真实框架腰在 O 倾 ~5°、侧缝内倾
# ~17°（5015 实测 |P1−O|/|P2−O| 与 p1/p2 分毫不差、真实弦长 12.24 ≠
# 模型 11.18），倾斜吃掉净距 0.46（承诺 1.2 -> 引擎回环实测 0.736，
# 金标断言 ≥1）；reverse/ 禁 import 引擎层，倾斜只能作余量吸收。
_WATCH_CLEAR = 2.2
_WATCH_MARGIN = 0.25        # 弧采样纳入顶边跨度的外扩（cm）
_WATCH_SIDE = 0.5           # 顶边外端离侧缝（cm，自设默认）


def _watch_shape(sub: SubPiece, p1_cm: float,
                 calib: Calibration) -> tuple:
    """小表袋净环 -> custom 锚点表（cm、dy 向下为正、参考点 = 顶边外端）
    + 逐边形态 + 还原顶边宽；不可用返回 (None, None, None, 原因)。

    口径（2026-08-30 用户纠偏：5015 表袋是自定义多边形、非袋贴相交）：
    丝缕线定织物轴（±3.4° 贴轴，斜向不可定向）-> x/y 向各按
    (1−weft)/(1−warp) 还原（丝缕横 = 经向贴 x、还原率对调）；顶边 =
    净环最浅顶点游程，须水平（旋转件不自设）；共线中间点（ET 直边离散）
    按转角 <2° 折叠，段内弦高 ≥0.1cm 发射弧线形态（引擎单位
    _engine_bulge；dy 向下镜像翻转 arc_through 左手法向符号，故取右手
    法向号）；光板矩形且还原顶边宽 >0.9×袋口腰锚判对折片（缝态两读：
    对折半幅/短边袋口）交回默认放置并披露（用户口径：不自己想象）。
    """
    pts = list(sub.net.pts)
    dedup = [pts[0]]
    for p in pts[1:]:                       # 去连续/闭合重复点（ET 离散杂点，
        if abs(p.x - dedup[-1].x) > 1e-6 or abs(p.y - dedup[-1].y) > 1e-6:
            dedup.append(p)                 #   重复点会吞掉相邻真角点）
    if len(dedup) > 1 and abs(dedup[0].x - dedup[-1].x) < 1e-6 and \
            abs(dedup[0].y - dedup[-1].y) < 1e-6:
        dedup.pop()
    pts = dedup
    n = len(pts)
    if n < 4 or n > 400:
        return None, None, None, "净环顶点数异常"
    if sub.grain is None or len(sub.grain.pts) < 2:
        return None, None, None, "无丝缕线，织物轴向不可定"
    gd = sub.grain.pts[-1] - sub.grain.pts[0]
    gl = gd.length
    if gl < 1e-6:
        return None, None, None, "丝缕线退化"
    if abs(gd.dx) <= _WATCH_GRAIN_TAN * gl:
        warp_x = False                      # 经向贴 y（竖）
    elif abs(gd.dy) <= _WATCH_GRAIN_TAN * gl:
        warp_x = True                       # 经向贴 x（横）
    else:
        return None, None, None, "丝缕线斜向（非贴轴），织物轴向不可定"
    fx = (1.0 - (calib.warp if warp_x else calib.weft)) / 10.0
    fy = (1.0 - (calib.weft if warp_x else calib.warp)) / 10.0
    # 顶边游程：自任一顶边顶点双向扩出整段，回转到游程起点；环序顶点
    # 任意，直接自首位起数会把锚留在顶边中间（顶宽被低估）
    y_top = max(p.y for p in pts)
    on_top = [abs(p.y - y_top) <= _WATCH_TOP_TOL for p in pts]
    if sum(on_top) < 2 or sum(on_top) >= n:
        return None, None, None, "顶边游程异常"
    s = on_top.index(True)
    i0 = s
    while on_top[(i0 - 1) % n]:
        i0 = (i0 - 1) % n
    k = 1
    while on_top[(i0 + k) % n]:
        k += 1
    # 锚 = 顶边 x 较小端（靠侧缝的外端，引擎 custom 自锚向 +x 内伸），
    # 环序自锚先走顶边：环序起点非 min-x 端时（反向环）整体重排——
    # 顶边游程倒序先走 + 身体区倒序，简单保序反转会把锚钉在环序起点
    # （max-x 端）、袋体向侧缝外伸展
    pts = pts[i0:] + pts[:i0]               # 游程起点回转到首位
    if pts[k - 1].x < pts[0].x:
        pts = ([pts[i] for i in range(k - 1, -1, -1)]
               + [pts[i] for i in range(len(pts) - 1, k - 1, -1)])
    if pts[k - 1].x < pts[0].x:
        pts = [pts[0], *pts[1:][::-1]]
    if abs(pts[k - 1].y - pts[0].y) > 1.0:
        return None, None, None, "件形旋转（顶边不水平），custom 不自设"
    if abs(pts[k - 1].x - pts[0].x) < _WATCH_MOUTH_MIN:
        return None, None, None, "顶边过短"
    n = len(pts)
    # 共线折叠（工厂 mm 空间：仿射保共线、保角阈值稳定）
    keep = [0]
    for i in range(1, n - 1):
        ux, uy = pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y
        wx, wy = pts[i + 1].x - pts[i].x, pts[i + 1].y - pts[i].y
        ul, wl = math.hypot(ux, uy), math.hypot(wx, wy)
        if ul < 1e-9 or wl < 1e-9:
            continue
        cosang = max(-1.0, min(1.0, (ux * wx + uy * wy) / (ul * wl)))
        if math.degrees(math.acos(cosang)) >= _WATCH_TURN_DEG:
            keep.append(i)
    keep.append(n - 1)
    # 还原到成衣 cm（参考点 = 顶边外端锚，dy 向下为正）
    ax, ay = pts[0].x, pts[0].y
    xy = [((p.x - ax) * fx, (ay - p.y) * fy) for p in pts]
    points_cm = [xy[i] for i in keep]
    m = len(keep)
    edges = []
    for j in range(m):
        i0, i1 = keep[j], keep[(j + 1) % m]
        seq = (list(range(i0, i1 + 1)) if i1 > i0
               else list(range(i0, n)) + list(range(0, i1 + 1)))
        run = [xy[i] for i in seq]
        a0x, a0y = run[0]
        b0x, b0y = run[-1]
        ux, uy = b0x - a0x, b0y - a0y
        length = math.hypot(ux, uy)
        sag, peak = 0.0, 0.5
        if len(run) > 2 and length > 1e-9:
            nx, ny = uy / length, -ux / length   # 右手法向（dy 向下系）
            for px, py in run[1:-1]:
                s = (px - a0x) * nx + (py - a0y) * ny
                if abs(s) > abs(sag):
                    sag, peak = s, ((px - a0x) * ux + (py - a0y) * uy) / (length ** 2)
        if abs(sag) >= _WATCH_ARC_SAG:
            b_at, _ = _engine_bulge_at(max(0.0, min(1.0, peak)))
            edges.append(("arc", round(_engine_bulge(sag), 2), round(b_at, 2)))
        else:
            edges.append(("line",))
    mouth_w = math.hypot(points_cm[1][0] - points_cm[0][0],
                         points_cm[1][1] - points_cm[0][1])
    if mouth_w > 0.9 * p1_cm:
        rect = len(points_cm) == 4 and all(e[0] == "line" for e in edges)
        return None, None, None, (
            "光板矩形疑对折片，缝态两读（对折半幅/短边袋口）不自设"
            if rect else
            f"还原顶边宽 {mouth_w:.2f}cm 超 0.9×袋口腰锚 {p1_cm:.2f}cm")
    return points_cm, edges, mouth_w, None


def _watch_anchor(p1: float, p2: float, mouth_w: float,
                  bulge: float, bulge_at: float) -> float | None:
    """自设锚位（未量测）：O 局部系（x 沿腰、y 向下）解析重建引擎袋口弧
    （arc_through 同构：端点腰锚 (p1,0)/侧缝锚 (0,p2)、控制点 = 弦分位
    lerp + 背离 O 法向 ×bulge×8/3、采样 65 点），返回水平顶边
    [_WATCH_SIDE, +宽] 的最深深度 t——顶边整体在弧 O 侧（挖削开口内）
    且留 _WATCH_CLEAR 安全距（1.2 名义净距 + 框架倾斜余量，见常量注；
    上部不被面板藏住）；袋口过浅放不下返回 None。"""
    ax, ay = p1, 0.0
    bx, by = 0.0, p2
    ux, uy = bx - ax, by - ay
    length = math.hypot(ux, uy)
    if length < 1e-9:
        return None
    nx, ny = -uy / length, ux / length
    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
    if math.hypot(mx - nx, my - ny) > math.hypot(mx + nx, my + ny):
        nx, ny = -nx, -ny                   # 取背离 O 一侧（n·mid>0）= 引擎正 bulge 凹向
    off = bulge * 8.0 / 3.0
    c1 = (ax + ux * (bulge_at * 0.5) + nx * off,
          ay + uy * (bulge_at * 0.5) + ny * off)
    c2 = (ax + ux * ((1.0 + bulge_at) * 0.5) + nx * off,
          ay + uy * ((1.0 + bulge_at) * 0.5) + ny * off)
    x1 = _WATCH_SIDE + mouth_w
    depths = []
    for i in range(65):                     # de Casteljau 采样
        t = i / 64.0
        s0, s1 = 1.0 - t, t
        abx, aby = ax * s0 + c1[0] * s1, ay * s0 + c1[1] * s1
        bcx, bcy = c1[0] * s0 + c2[0] * s1, c1[1] * s0 + c2[1] * s1
        cdx, cdy = c2[0] * s0 + bx * s1, c2[1] * s0 + by * s1
        abcx, abcy = abx * s0 + bcx * s1, aby * s0 + bcy * s1
        bcdx, bcdy = bcx * s0 + cdx * s1, bcy * s0 + cdy * s1
        px, py = abcx * s0 + bcdx * s1, abcy * s0 + bcdy * s1
        if _WATCH_SIDE - _WATCH_MARGIN <= px <= x1 + _WATCH_MARGIN:
            depths.append(py)
    if len(depths) < 5:
        return None
    t = min(depths) - _WATCH_CLEAR
    return t if t >= 0.3 else None


# 后贴袋 custom 形状/定位量测阈值（口径同小表袋 _WATCH_* 族，2026-08-30）
_PATCH_TOP_TOL = 0.5        # 袋口游程 y 容差（mm）
_PATCH_MOUTH_MIN = 30.0     # 袋口最短实长（mm）
_PATCH_TURN_DEG = 2.0       # 共线中间点折叠阈值（度，ET 直边离散）
_PATCH_ARC_SAG = 0.1        # 段内弦高超过即发射弧边（cm，真弧高）
_PATCH_SYMM_TOL = 0.3       # 主形左右对称容差（cm），超差角逐一披露
_PATCH_DROP = 3.5           # 自设默认袋口距约克底线（引擎常规 3.0~4.5）
_PATCH_THIGH_CLEAR = 0.5    # 自设默认袋底距毗围线保持 ≥ 此值（cm）
_PATCH_INSET_MIN = 0.5      # 自设默认袋口近后浪端不贴后浪（cm）


def _patch_shape(sub: SubPiece, calib: Calibration) -> tuple:
    """后贴袋净环 -> custom 角点表（cm、u 朝侧缝 +、v 向下 +、V0=袋口近
    后浪侧顶点）+ 逐边形态 (弧高, 弧顶位) + 袋口宽/身高/不对称披露；
    不可用返回 (None, None, None, None, None, 原因)。

    口径（2026-08-30 用户定则：在场即开 + 位置自设默认）：骨架同小表袋
    _watch_shape（去重 -> 丝缕贴轴定向 -> 各向异性还原 -> 袋口 = 最浅
    顶点游程须水平 -> 共线折叠 <2° -> 段内弦高 ≥0.1cm 发射弧边）。
    符号差异（关键）：引擎局部->全局是 180° 旋转（û = 后浪->侧缝 = 全局
    −X̂，det=+1 保定向），环在全局 y-上系为 CCW -> arc_through 正 bulge
    （左手法向）= 内凹，**外凸取负**（小表袋 dy 镜像反定向、外凸取正，
    勿混）。铺版图无可观测手性：主形对称即无歧义，非镜像角（袋口端
    小台阶）披露取向自设。
    """
    pts = list(sub.net.pts)
    dedup = [pts[0]]
    for p in pts[1:]:
        if abs(p.x - dedup[-1].x) > 1e-6 or abs(p.y - dedup[-1].y) > 1e-6:
            dedup.append(p)
    if len(dedup) > 1 and abs(dedup[0].x - dedup[-1].x) < 1e-6 and \
            abs(dedup[0].y - dedup[-1].y) < 1e-6:
        dedup.pop()
    pts = dedup
    n = len(pts)
    if n < 4 or n > 400:
        return None, None, None, None, None, "净环顶点数异常"
    if sub.grain is None or len(sub.grain.pts) < 2:
        return None, None, None, None, None, "无丝缕线，织物轴向不可定"
    gd = sub.grain.pts[-1] - sub.grain.pts[0]
    gl = gd.length
    if gl < 1e-6:
        return None, None, None, None, None, "丝缕线退化"
    if abs(gd.dx) <= _WATCH_GRAIN_TAN * gl:
        warp_x = False
    elif abs(gd.dy) <= _WATCH_GRAIN_TAN * gl:
        warp_x = True
    else:
        return None, None, None, None, None, "丝缕线斜向（非贴轴），织物轴向不可定"
    fx = (1.0 - (calib.warp if warp_x else calib.weft)) / 10.0
    fy = (1.0 - (calib.weft if warp_x else calib.warp)) / 10.0
    # 袋口游程（最浅顶点带内双向扩出）+ 锚 = 袋口 x 小端（自设取向：
    # 该端判近后浪侧），环序自锚先走袋口（同 _watch_shape 的防锚中置反转）
    y_top = max(p.y for p in pts)
    on_top = [abs(p.y - y_top) <= _PATCH_TOP_TOL for p in pts]
    if sum(on_top) < 2 or sum(on_top) >= n:
        return None, None, None, None, None, "袋口游程异常"
    i0 = on_top.index(True)
    while on_top[(i0 - 1) % n]:
        i0 = (i0 - 1) % n
    k = 1
    while on_top[(i0 + k) % n]:
        k += 1
    pts = pts[i0:] + pts[:i0]
    if pts[k - 1].x < pts[0].x:
        pts = ([pts[i] for i in range(k - 1, -1, -1)]
               + [pts[i] for i in range(len(pts) - 1, k - 1, -1)])
    if abs(pts[k - 1].y - pts[0].y) > 1.0:
        return None, None, None, None, None, "件形旋转（袋口不水平），custom 不自设"
    if abs(pts[k - 1].x - pts[0].x) < _PATCH_MOUTH_MIN:
        return None, None, None, None, None, "袋口过短"
    n = len(pts)
    keep = [0]
    for i in range(1, n - 1):
        ux, uy = pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y
        wx, wy = pts[i + 1].x - pts[i].x, pts[i + 1].y - pts[i].y
        ul, wl = math.hypot(ux, uy), math.hypot(wx, wy)
        if ul < 1e-9 or wl < 1e-9:
            continue
        cosang = max(-1.0, min(1.0, (ux * wx + uy * wy) / (ul * wl)))
        if math.degrees(math.acos(cosang)) >= _PATCH_TURN_DEG:
            keep.append(i)
    keep.append(n - 1)
    # 还原成衣 cm（v 向下正，同引擎 u-v；u 沿袋口自锚向 +）
    ax, ay = pts[0].x, pts[0].y
    xy = [((p.x - ax) * fx, (ay - p.y) * fy) for p in pts]
    points_cm = [xy[i] for i in keep]
    m = len(keep)
    edges = []
    for j in range(m):
        i0_, i1_ = keep[j], keep[(j + 1) % m]
        seq = (list(range(i0_, i1_ + 1)) if i1_ > i0_
               else list(range(i0_, n)) + list(range(0, i1_ + 1)))
        run = [xy[i] for i in seq]
        a0x, a0y = run[0]
        b0x, b0y = run[-1]
        ux, uy = b0x - a0x, b0y - a0y
        length = math.hypot(ux, uy)
        sag, peak = 0.0, 0.5
        if len(run) > 2 and length > 1e-9:
            nx, ny = uy / length, -ux / length   # dy-下系右手法向 = 外凸为正
            for px, py in run[1:-1]:
                s = (px - a0x) * nx + (py - a0y) * ny
                if abs(s) > abs(sag):
                    sag, peak = s, ((px - a0x) * ux + (py - a0y) * uy) / (length ** 2)
        if abs(sag) >= _PATCH_ARC_SAG:
            b_at, _ = _engine_bulge_at(max(0.0, min(1.0, peak)))
            # 全局 CCW：外凸为正的实测弧高取负才落在引擎左手法向凸侧
            edges.append((round(-_engine_bulge(sag), 2), round(b_at, 2)))
        else:
            edges.append((0.0, 0.5))
    mouth_w = math.hypot(points_cm[1][0] - points_cm[0][0],
                         points_cm[1][1] - points_cm[0][1])
    height = max(v for _, v in points_cm)
    # 左右对称性（绕袋口中点竖直轴镜像）：铺版图无手性观测，主形对称
    # 即无歧义；非镜像角（袋口端小台阶类）逐一披露、取向自设
    mx = (points_cm[0][0] + points_cm[1][0]) / 2.0
    stray = [(round(x, 2), round(v, 2))
             for x, v in points_cm
             if min(math.hypot((2.0 * mx - x) - c[0], v - c[1])
                    for c in points_cm) > _PATCH_SYMM_TOL]
    if not stray:
        asym = None
    elif len(stray) == 1:
        asym = (f"主形左右对称、袋口一端有小台阶 {stray[0][0]}×{stray[0][1]}cm"
                "（取向自设台阶端靠后浪，铺版图无可观测手性，镜像读法"
                "改 points 即可）")
    else:
        asym = (f"{len(stray)} 个角点无镜像对应（左右不对称，"
                "取向自设自袋口 x 小端，铺版图无可观测手性）")
    return points_cm, edges, mouth_w, height, asym, None


def _patch_place(l_yb_cm: float, avail_cm: float, mouth_w: float,
                 height: float) -> tuple[float, float, str | None]:
    """自设默认定位（未量测，2026-08-30 用户定则）：inset_x = (约克底线
    长 − 袋口宽)/2 居中（≈对齐后腰中点）、drop_y 默认 3.5（引擎常规
    3.0~4.5），袋底保持距毗围线 ≥0.5cm（放不下则上提，仍放不下钳 0.5
    并披露越线）。返回 (inset_x, drop_y, 越线披露)。"""
    inset = (l_yb_cm - mouth_w) / 2.0
    note = None
    if inset < _PATCH_INSET_MIN:
        inset = _PATCH_INSET_MIN
        note = (f"袋口宽 {mouth_w:.2f}cm 贴满约克底线 {l_yb_cm:.2f}cm，"
                f"inset_x 钳 {_PATCH_INSET_MIN:.2f} 不贴后浪")
    drop = _PATCH_DROP
    cap = avail_cm - height - _PATCH_THIGH_CLEAR
    if drop > cap:
        drop = cap
    if drop < 0.5:
        drop = 0.5
        extra = (f"袋身 {height:.2f}cm 深、约克底线->毗围线仅 {avail_cm:.2f}cm，"
                 f"drop_y 钳 0.50 后袋底仍越毗围线 "
                 f"{height + 0.5 - avail_cm:.2f}cm")
        note = f"{note}；{extra}" if note else extra
    return round(inset, 2), round(drop, 2), note


def _patch_avail(bg: BodyGeom, calib: Calibration) -> float:
    """后片顶边（= 约克底线拼合线，两腰角点间较短弧）弧长中点到毗围线
    的竖直距（cm，×warp 还原）——贴袋可用深的地板。"""
    ring = bg.ring
    top = chain_between_shorter(
        ring, nearest_vertex(ring, bg.waist_cb), nearest_vertex(ring, bg.waist_side))
    total = chain_length_mm(top)
    half, acc, mid = total / 2.0, 0.0, top[-1]
    for a, b in zip(top, top[1:]):
        d = a.distance_to(b)
        if acc + d >= half:
            t = (half - acc) / max(d, 1e-9)
            mid = Point(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)
            break
        acc += d
    y_th = None
    th = bg.thigh.pts
    for a, b in zip(th, th[1:]):            # 毗围线可微斜：按 x 插值
        if abs(b.x - a.x) < 1e-6:
            continue                        # 竖直退化段
        if min(a.x, b.x) <= mid.x <= max(a.x, b.x):
            y_th = a.y + (b.y - a.y) * (mid.x - a.x) / (b.x - a.x)
            break
    if y_th is None:                        # 中点 x 未被导线覆盖（兜底中值）
        y_th = sum(p.y for p in th) / len(th)
    return calib.y_cm(mid.y - y_th)


def measure_options(size: str, mapping: dict[str, SubPiece],
                    measured: MeasuredSize,
                    calib: Calibration) -> tuple[dict, list[str]]:
    """层 2：可直接量测/观测的选项子集（未量测项不出现，保持引擎默认）。

    两族：几何量测（调节量/内收/腰头/缝份/缩水）+ 识别观测（结构开关
    ——裁片在场即开，存在性直接可见，不属于形状拟合）。"""
    fg = body_geometry(mapping["front_body"], "front")
    bg = body_geometry(mapping["back_body"], "back")
    warns: list[str] = []
    out: dict = {}

    # 结构开关：裁片在场即开（识别层直接观测存在性，非形状拟合）。
    # 前代融合片在场 -> 袋贴（面料）开；袋布走口袋布里料、不在工厂打版
    # DXF，front_pouch 直接关、不推断（用户口径 2026-08-29）；双排门襟
    # 片存在时 fly_sep_double 保持默认 true，只有单排片才显式关。
    out["back_yoke"] = "yoke" in mapping
    out["front_pocket"] = "fused_pocket" in mapping
    if out["front_pocket"]:
        out["front_pocket_facing"] = True
        out["front_pouch"] = False
        warns.append("袋布走里料、不在工厂打版 DXF，front_pouch 显式关"
                     "（不从前代一体片推断）")
        # 挖削口袋参数（用户口径 2026-08-29「挖削嵌入式口袋要推测完整」）：
        # P1/P2 锚点 = 前代顶边袋口段 / 侧边段（两者恰补腰口与外缝弧长，
        # 与引擎 p1_dist/p2_drop 同锚——均自腰外缝顶点起量）；袋口形态 =
        # 前片袋口弧还原后的弦法向剖面，折线式（有折角）/ 弧高式（平滑
        # 单峰）二选一，tangent 族单根曲线不可辨识不发射。
        ex = measured.extras
        out["front_pocket_p1_dist"] = round(
            calib.x_cm(ex["pocket_bridge_mm"]), 2)
        out["front_pocket_p2_drop"] = round(
            calib.y_cm(ex["pocket_side_mm"]), 2)
        if "mouth_sagitta_cm" in ex:
            corners = [(round(t, 2), round(d, 2))
                       for t, d in ex["mouth_corners"]
                       if 0.0 < t < 1.0 and 0.0 <= d <= 5.0]
            dedup: list[tuple[float, float]] = []
            for t, d in sorted(corners):
                if not dedup or t > dedup[-1][0]:
                    dedup.append((t, d))
            if dedup:
                out["front_pocket_mouth_mode"] = "polyline"
                out["front_pocket_mouth_corners"] = tuple(dedup)
            else:
                out["front_pocket_mouth_mode"] = "bulge"
                sag = ex["mouth_sagitta_cm"]
                bulge = _engine_bulge(sag)
                if abs(bulge) > 5.0:
                    bulge = math.copysign(5.0, bulge)
                    warns.append(f"袋口弧高 {sag:.2f}cm 换算引擎 bulge "
                                 f"{sag / 2.0:.2f} 超 |5| 上限，发射钳 5.0")
                out["front_pocket_mouth_bulge"] = round(bulge, 2)
                b_at, ok = _engine_bulge_at(ex["mouth_peak_at"])
                out["front_pocket_mouth_bulge_at"] = round(b_at, 2)
                if not ok:
                    warns.append(f"袋口弧顶弦位 {ex['mouth_peak_at']:.2f} "
                                 "超出 arc_through 可表达弦中段 "
                                 "[0.31, 0.69]，bulge_at 钳至端点（形状近似）")
            warns.append(f"袋口形态 {out['front_pocket_mouth_mode']}："
                         f"弧高 {ex['mouth_sagitta_cm']:.2f}cm @ 弦位 "
                         f"{ex['mouth_peak_at']:.2f}（0=腰头端）、折角 "
                         f"{len(ex['mouth_corners'])} 个；bulge 发射按引擎"
                         "单位换算（arc_through 渲染弧高 = 2×bulge，真弧高"
                         "减半发射）；tangent 模式（h1/h2）单根曲线不可"
                         "辨识，不发射")
        else:
            warns.append("前片袋口弧未识别（顶链角点不足 3 个），mouth "
                         "形态族保持默认")
        # 吃省/撇削：dart_width 的 V·(1−t)ⁿ 偏置与设计净线作用在同一根
        # 弧上，单根曲线两未知不可分离；且弧与顶边均无省痕（有吃省会在
        # 腰头端留折角/凹口）→ 无吃省证据，两者保默认 0/2.0
        warns.append("袋口吃省 dart_width 与撇削幂 paring_n 单弧不可分离、"
                     "弧上无省痕 → 保默认 0/2.0（mouth_h1/h2 属 tangent "
                     "模式不发射）")
        # 袋贴内边族（净边大弧量测，与引擎 Ω_facing 同构）：width/side_w =
        # 两直边袋贴段（P1 沿腰弧朝前浪顶点 / P2 沿外缝向下，与引擎
        # P_fw/P_fs 同锚）、mode=bulge + 弧高/弧顶位（L_inner = 过
        # P_fw/P_fs 的浅弧族，bulge/bulge_at 换算引擎单位 _engine_bulge）；
        # h1/h2 属 tangent 模式不发射
        if "facing_waist_mm" in ex:
            width = calib.x_cm(ex["facing_waist_mm"])
            side_w = calib.y_cm(ex["facing_side_mm"])
            if 0.0 < width <= 10.0:
                out["front_pocket_facing_width"] = round(width, 2)
            else:
                warns.append(f"袋贴腰宽 {width:.2f}cm 越界（0~10），不发射")
            if 0.0 < side_w <= 15.0:
                out["front_pocket_facing_side_w"] = round(side_w, 2)
            bulge = _engine_bulge(ex["facing_sagitta_cm"])
            if abs(bulge) > 10.0:
                warns.append(f"袋贴内边弧高 {ex['facing_sagitta_cm']:.2f}cm "
                             f"换算引擎 bulge {bulge:.2f} 超 |10| 上限，"
                             "发射钳 10.0")
                bulge = math.copysign(10.0, bulge)
            out["front_pocket_facing_mode"] = "bulge"
            out["front_pocket_facing_bulge"] = round(bulge, 2)
            b_at, ok = _engine_bulge_at(ex["facing_peak_at"])
            out["front_pocket_facing_bulge_at"] = round(b_at, 2)
            if not ok:
                warns.append(f"袋贴内边弧顶弦位 {ex['facing_peak_at']:.2f} "
                             "超出 arc_through 可表达弦中段 [0.31, 0.69]，"
                             "bulge_at 钳至端点（形状近似）")
            warns.append(f"袋贴内边 = 前代净边大弧：腰段 {width:.2f}cm"
                         f"（P1→P_fw）、侧段 {side_w:.2f}cm（P2→P_fs）、"
                         f"真弧高 {ex['facing_sagitta_cm']:.2f} @ 弦位 "
                         f"{ex['facing_peak_at']:.2f}"
                         "（0=腰端；背离袋口弦为正 = 向裤身内侧凹入）→ 引擎"
                         f" bulge {out['front_pocket_facing_bulge']:.2f} @ "
                         f"{out['front_pocket_facing_bulge_at']:.2f}"
                         "（arc_through 渲染弧高 = 2×bulge，真弧高减半"
                         "发射；0.31~0.69 之外弧顶不可表达钳端点）；"
                         "h1/h2 属 tangent 模式不发射")
        else:
            warns.append("前代净边无袋贴大弧，facing 内边族保持引擎默认"
                         "（层 5）")
    out["belt_loop"] = "belt_loop" in mapping
    # 小表袋（用户口径 2026-08-30：识别到但无具体位置 -> 自设默认放置，
    # 只保证上部不被面板藏住）。件形可量测（丝缕定向还原 + 共线折叠，
    # _watch_shape）-> custom 净样原样发射，锚位对解析重建的引擎袋口弧
    # 取「不被藏住」的最深顶边（外端 0.5、净距 ≥1.2cm，_watch_anchor）；
    # 件形不可用（无丝缕/斜置/旋转/对折歧义/超宽/袋口过浅）回退
    # facing_intersect 保守矩形默认：顶边水平、深 0.42×p2（袋口侧深）、
    # 外端 0.12×p1（腰锚）、宽 0.55×p1——袋口弧只在弦中段下沉最深、
    # 水平顶边右端 0.67×p1 落在弧贴腰的浅水区之上 -> 顶边整体在挖削
    # 开口内（O 侧）可见，两侧竖直向下射线（taper 0.3 偏角 ~2°）必交
    # 袋贴内边深 U 的下弧（该模式依赖袋贴族在场 front.pocket_facing_inner）。
    if "watch_pocket" in mapping:
        if "front_pocket_p1_dist" not in out:
            warns.append("小表袋在场但袋口锚点未量测（放置依赖袋口几何），"
                         "保持默认关")
        else:
            p1 = out["front_pocket_p1_dist"]
            p2 = out["front_pocket_p2_drop"]
            points_cm, edges, mouth_w, bad = _watch_shape(
                mapping["watch_pocket"], p1, calib)
            t = None
            if bad is None:
                t = _watch_anchor(p1, p2, mouth_w,
                                  out.get("front_pocket_mouth_bulge", 0.0),
                                  out.get("front_pocket_mouth_bulge_at", 0.5))
                if t is None:
                    bad = (f"还原顶边宽 {mouth_w:.2f}cm 在袋口弧内放不下"
                           f"（安全距 {_WATCH_CLEAR:.1f}cm 含框架倾斜余量，"
                           "袋口过浅）")
            if bad is None:
                arcs = sum(1 for e in edges if e[0] == "arc")
                out["watch_pocket"] = True
                out["watch_pocket_mode"] = "custom"
                out["watch_pocket_points"] = tuple(
                    (round(dx, 2), round(dy, 2)) for dx, dy in points_cm)
                out["watch_pocket_edges"] = tuple(edges)
                out["watch_pocket_offset_from_top"] = round(t, 2)
                out["watch_pocket_offset_from_side"] = _WATCH_SIDE
                warns.append(f"小表袋在场即开、custom 净样原样（{len(points_cm)}"
                             f" 锚点、顶边宽 {mouth_w:.2f}cm、{arcs} 条弧边），"
                             f"位置自设默认：顶边深 {t:.2f}、外端 "
                             f"{_WATCH_SIDE:.2f}——对解析重建的引擎袋口弧"
                             f"留 {_WATCH_CLEAR:.1f}cm 安全距（含腰/侧缝对"
                             "正交框架的倾斜余量，引擎实测净距 ≥1，上部不被"
                             "面板藏住）；custom 不依赖袋贴族")
            else:
                out["watch_pocket"] = True
                out["watch_pocket_offset_from_top"] = round(0.42 * p2, 2)
                out["watch_pocket_offset_from_side"] = round(0.12 * p1, 2)
                out["watch_pocket_width"] = round(0.55 * p1, 2)
                warns.append(f"小表袋件形不可用（{bad}），回退袋贴相交默认"
                             f"放置：顶边深 {0.42 * p2:.2f}（0.42×袋口侧深）、"
                             f"外端 {0.12 * p1:.2f}（0.12×腰锚）、宽 "
                             f"{0.55 * p1:.2f}（0.55×腰锚）——顶边整体在袋口"
                             "弧 O 侧可见（上部不被面板藏住）、两侧竖直向下"
                             "交袋贴内边")
    # 后贴袋（用户口径 2026-08-30：在场即开 + 位置自设默认三定则——机头
    # 下方、对齐后腰中点、袋底保持毗围线上方）。件形可量测（丝缕定向
    # 还原 + 共线折叠，_patch_shape）-> custom 净样原样发射；不可用回退
    # 引擎默认 rectangle 14×16（披露），位置仍按定则（尺寸按默认算）
    if "back_patch" in mapping and not out["back_yoke"]:
        warns.append("后贴袋在场但无机头（放置基准缺失），不发射开关")
    elif "back_patch" in mapping:
        l_yb = calib.x_cm(chain_length_mm(
            yoke_edges(mapping["yoke"].net_or_gross())[1]))
        avail = _patch_avail(bg, calib)
        points_cm, edges, mouth_w, height, asym, bad = _patch_shape(
            mapping["back_patch"], calib)
        if bad is not None:
            mouth_w, height = 14.0, 16.0     # 引擎默认矩形尺寸（仅定位计算）
        inset, drop, note = _patch_place(l_yb, avail, mouth_w, height)
        out["back_patch"] = True
        out["back_patch_inset_x"] = inset
        out["back_patch_drop_y"] = drop
        if bad is None:
            out["back_patch_shape"] = "custom"
            out["back_patch_custom_points"] = tuple(
                (round(u, 2), round(v, 2)) for u, v in points_cm)
            out["back_patch_custom_edges"] = tuple(edges)
            arcs = sum(1 for b, _ in edges if b != 0.0)
            warns.append(f"后贴袋在场即开、custom 净样原样（{len(points_cm)} "
                         f"角点、袋口宽 {mouth_w:.2f}cm、{arcs} 条弧边），"
                         f"位置自设默认：inset_x {inset:.2f} = (约克底线 "
                         f"{l_yb:.2f} − 袋口宽 {mouth_w:.2f})/2 居中"
                         "（≈对齐后腰中点）、机头下方 drop_y "
                         f"{drop:.2f}（袋底距毗围线 "
                         f"{avail - drop - height:.2f}cm ≥"
                         f"{_PATCH_THIGH_CLEAR:.1f} 保持其上）")
        else:
            warns.append(f"后贴袋件形不可用（{bad}），开关开、形状保持引擎"
                         f"默认 rectangle 14×16，位置按默认尺寸自设："
                         f"inset_x {inset:.2f}、drop_y {drop:.2f}")
        if asym:
            warns.append(f"后贴袋{asym}")
        if note:
            warns.append(f"后贴袋定位钳制：{note}")
    if "front_fly_single" in mapping or "front_fly_double" in mapping:
        out["fly_separate"] = True
        if "front_fly_double" not in mapping:
            out["fly_sep_double"] = False
    if measured.values["thigh"] > 0.0:
        out["thigh_limit"] = True
        warns.append("识别到毗围线（thigh>0），发射 thigh_limit=true"
                     "（重打版闭环逼近工厂毗围；控制参数保持默认）")
    out["size_label"] = size

    # 调节量族（前减后加 = 后宽 − 前宽 之半）
    f_hip, b_hip = fg.chord_mm(fg.hip), bg.chord_mm(bg.hip)
    f_kn, b_kn = fg.chord_mm(fg.knee), bg.chord_mm(bg.knee)
    f_hm, b_hm = fg.hem_chord_mm(), bg.hem_chord_mm()
    delta_raw = split_adjust_cm(f_hip, b_hip, calib)
    out["delta"] = round(min(delta_raw, 2.0), 2)
    if delta_raw > 2.0:
        warns.append(f"delta 实测 {delta_raw:.2f}cm 超上限，发射钳 2.0"
                     "（报告留原值）")
    out["knee_adjust"] = round(split_adjust_cm(f_kn, b_kn, calib), 2)
    out["hem_adjust"] = round(split_adjust_cm(f_hm, b_hm, calib), 2)
    v = measured.values
    waist_part = measured.extras.get("front_waist_part_mm", 0.0)
    yoke_top = measured.extras.get("yoke_top_mm", 0.0)
    if waist_part and yoke_top:
        out["waist_balance"] = round(
            split_adjust_cm(waist_part + bridge_of(measured), yoke_top, calib),
            2)

    # 前中内收：腰口 CF 角与裆尖的水平距 = 内收量 + 前小裆宽（引擎口径
    # 内收自内侧缝参考线量、小裆自参考线外伸，几何上恰好相加）
    dx = abs(fg.waist_cb.x - fg.crotch_tip.x)
    raw_total = calib.x_cm(dx)
    w_crotch = v["hip"] / 20.0            # 前小裆宽（默认修正 0）
    raw_intake = raw_total - w_crotch
    base = 0.2 * (v["hip"] - v["waist"]) / 4.0
    out["front_intake_adjust"] = round(raw_intake - base, 2)
    warns.append(f"前中内收：CF-裆尖水平 {raw_total:.2f}cm − 小裆宽 "
                 f"{w_crotch:.2f} = 实测 {raw_intake:.2f}cm；ratio 隐含值 "
                 f"{raw_intake / max((v['hip'] - v['waist']) / 4.0, 1e-6):.3f}"
                 "（默认 0.2，偏差入 adjust）")

    # 后中内收：机头刚体平移拼回后片 -> 成衣腰 CB -> 臀 CB 斜率
    yoke = mapping["yoke"].net_or_gross()
    _, yoke_bottom = yoke_edges(yoke)
    back_top = shallow_run_at_extreme(bg.ring, "top")
    off, rms = rigid_fit_offset(resample_chain(yoke_bottom, 40),
                                resample_chain(back_top, 40))
    if rms > 3.0:
        warns.append(f"机头底边拼回后片顶边 RMS {rms:.2f}mm 偏大，back_intake 存疑")
    yoke_top_chain, _ = yoke_edges(yoke)
    waist_cb = yoke_top_chain[0] + off          # CB 端（链首 = x 小侧）
    hip_cb = bg.hip.pts[0] if bg.hip.pts[0].distance_to(
        _cb_extreme(bg)) < bg.hip.pts[-1].distance_to(_cb_extreme(bg)) \
        else bg.hip.pts[-1]
    ddx, ddy = abs(waist_cb.x - hip_cb.x), abs(waist_cb.y - hip_cb.y)
    slope = (ddx * (1.0 - calib.weft)) / (ddy * (1.0 - calib.warp))
    out["back_intake"] = round(slope * 15.0, 2)

    # 直裆修正：CF 腰角 -> 裆尖竖直距 ×warp + 腰头 − 0.25H
    band_cm = calib.y_cm(strip_width_mm(mapping["waistband"].net_or_gross()))
    vertical = abs(fg.waist_cb.y - fg.crotch_tip.y)
    out["rise_adjust"] = round(calib.y_cm(vertical) + band_cm
                               - 0.25 * v["hip"], 2)

    # 腰头：宽/类型（矢高>2mm = 弯腰头）/丝缕方向（沿长边 = LENGTH，
    # 横穿带宽 = WIDTH 默认不发射）
    wb_ring = mapping["waistband"].net_or_gross()
    out["waistband_width"] = round(band_cm, 2)
    edge_a, edge_b = strip_long_edges(wb_ring)
    ys = [p.y for p in edge_a]
    out["waistband_type"] = "curved" if (max(ys) - min(ys)) > 2.0 else "straight"
    grain = mapping["waistband"].grain
    if grain is not None:
        band_dir = math.atan2(edge_a[-1].y - edge_a[0].y,
                              edge_a[-1].x - edge_a[0].x)
        d = (grain.slope_deg() - math.degrees(band_dir)) % 180.0
        parallel = min(d, 180.0 - d)      # 丝缕与长边夹角（0=平行）
        if parallel < 45.0:
            out["waistband_grain"] = "length"
            warns.append("腰头丝缕沿长边（经向车长），发射 waistband_grain="
                         "length（默认为 width）")
    # 机头深（弧长沿经向）
    cb_arc, side_arc = _yoke_arcs(yoke)
    out["back_yoke_cb_dist"] = round(calib.y_cm(cb_arc), 2)
    out["back_yoke_side_dist"] = round(calib.y_cm(side_arc), 2)

    # 缩水（还原系数同时是再打版的放大率）
    out["shrinkage_warp"] = round(calib.warp, 4)
    out["shrinkage_weft"] = round(calib.weft, 4)

    # 前片缝份：净顶点 -> 毛边最近点的向量分类（竖向 = 脚口/腰口放缝、
    # 横向 = 缝边放缝）；脚口取膝线下 100mm 的竖向缝份中位数
    front = mapping["front_body"]
    if front.gross is not None:
        net_ring = front.net_or_gross()
        knee_y = fg.knee.midpoint().y
        seam_gaps: list[float] = []
        hem_gaps: list[float] = []
        for p in net_ring.pts:
            q = point_ring_nearest(p, front.gross)
            vert = abs(q.y - p.y) >= abs(q.x - p.x)
            if vert and p.y < knee_y - 100.0:
                hem_gaps.append(p.distance_to(q))
            elif not vert:
                seam_gaps.append(p.distance_to(q))
        if hem_gaps and seam_gaps:
            hem_sa = statistics.median(hem_gaps) / 10.0
            seam_sa = statistics.median(seam_gaps) / 10.0
            out["front_piece_seam_allowances"] = {
                "waist": round(seam_sa, 2), "rise": round(seam_sa, 2),
                "inseam": round(seam_sa, 2), "side": round(seam_sa, 2),
                "mouth": round(seam_sa, 2), "hem": round(hem_sa, 2)}
        else:
            warns.append("前片缝份分类不全（竖向脚口缝份或横向缝边缝份缺失），"
                         "不发射 front_piece_seam_allowances")
    return out, warns


def bridge_of(measured: MeasuredSize) -> float:
    return measured.extras.get("pocket_bridge_mm", 0.0)


def _cb_extreme(g: BodyGeom) -> Point:
    x0, _, x1, _ = g.ring.bbox()
    return Point(x0, g.crotch_tip.y) if g.cb_side == "min" \
        else Point(x1, g.crotch_tip.y)
