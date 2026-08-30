"""Ring/OpenLine 纯几何算子（.doc/工厂DXF逆向解析.md §2，mm 域）。

measure.py 的测量口径全部落到这里的算子上；本模块不 import ezdxf、
不碰参数层，只依赖 geometry.Point/Vector。跨码顶点数漂移（188→195）
是常态，**任何算子禁止用顶点索引做跨片对应**——需要对应时用等弧长
重采样（``ring_gap_best``）。
"""

from __future__ import annotations

import math

from ..geometry import Point, Vector
from .model import Ring

_EPS = 1e-9          # mm 域几何容差
_DEDUP = 1e-7        # 交点去重半径（顶点恰在测量线上时双侧重复计）


def _cross(v: Vector, w: Vector) -> float:
    return v.dx * w.dy - v.dy * w.dx


def _dot(v: Vector, w: Vector) -> float:
    return v.dx * w.dx + v.dy * w.dy


# ---- 点-边界距离（缝份/归属判定） ----


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    """点到线段的最短距离（投影钳到 [0,1]）。"""
    v = b - a
    vv = _dot(v, v)
    if vv < _EPS:
        return p.distance_to(a)
    t = max(0.0, min(1.0, _dot(p - a, v) / vv))
    return p.distance_to(a + v.scale(t))


def point_ring_distance(p: Point, ring: Ring) -> float:
    """点到闭合折线边界的最短距离。"""
    return min(point_segment_distance(p, a, b) for a, b in ring.segments())


def point_ring_nearest(p: Point, ring: Ring) -> Point:
    """点到闭合折线边界的最近点（缝份方向分类：净顶点 -> 毛边最近点
    的方向即该处放缝方向）。"""
    best: Point | None = None
    best_d = float("inf")
    for a, b in ring.segments():
        v = b - a
        vv = _dot(v, v)
        t = 0.0
        if vv >= _EPS:
            t = max(0.0, min(1.0, _dot(p - a, v) / vv))
        q = a + v.scale(t)
        d = p.distance_to(q)
        if d < best_d:
            best, best_d = q, d
    assert best is not None
    return best


def nearest_vertex(ring: Ring, p: Point) -> int:
    """最近顶点索引（同距取先到——锚定角点用，勿用于跨片对应）。"""
    best, best_d = 0, float("inf")
    for i, v in enumerate(ring.pts):
        d = v.distance_to(p)
        if d < best_d:
            best, best_d = i, d
    return best


def vertex_gaps(gross: Ring, net: Ring) -> list[float]:
    """净样各顶点到毛样边界的最小距离（缝份采样；按语义边过滤由
    measure 决定，此处只给全顶点序列）。"""
    return [point_ring_distance(p, gross) for p in net.pts]


# ---- 测量线 / 导线弦宽（围度族口径） ----


def line_ring_intersections(ring: Ring, a: Point, b: Point) -> list[Point]:
    """过 a→b 的**无限直线**与环边的交点，沿 a→b 方向排序。

    顶点恰落在测量线上时相邻两侧会重复计同一点，按 ``_DEDUP`` 去重；
    边与线共线（工厂导线不会发生）整段跳过。
    """
    d = b - a
    if d.length < _EPS:
        raise ValueError("测量线两端点重合")
    out: list[Point] = []
    n = len(ring.pts)
    for i in range(n):
        p, q = ring.pts[i], ring.pts[(i + 1) % n]
        cp, cq = _cross(d, p - a), _cross(d, q - a)
        if cp == 0.0 and cq == 0.0:
            continue                      # 边共线
        denom = cp - cq
        if cp * cq > 0.0 or abs(denom) < _EPS:
            continue                      # 同侧不相交
        t = cp / denom                    # 交点在边上的参数（0/1 = 顶点）
        if -1e-9 <= t <= 1.0 + 1e-9:
            out.append(p.lerp(q, t))
    dedup: list[Point] = []
    for pt in out:
        if not any(pt.distance_to(u) < _DEDUP for u in dedup):
            dedup.append(pt)
    u = d.normalized()
    dedup.sort(key=lambda pt: _dot(pt - a, u))
    return dedup


def chord_span_mm(ring: Ring, a: Point, b: Point) -> float | None:
    """导线弦宽：无限直线穿环的首末交点距（臀围/中裆/脚口/毗围线弦）。

    导线一次横穿裁片时恰两交点；不足两交点返回 None（测量线没切到）。
    """
    pts = line_ring_intersections(ring, a, b)
    if len(pts) < 2:
        return None
    return pts[0].distance_to(pts[-1])


# ---- 环上链提取（腰弧/浪链/外缝链） ----


def chain_above(ring: Ring, y: float) -> list[Point]:
    """近水平切割：环边界在 y **严格以上**的那条链（入口交点 → 上方
    顶点 → 出口交点）。近水平线切简单闭曲线恰两交点；多对交点时取
    第一条含上方顶点的链；切不到（含切割线恰过顶点的退化位）返回
    []——measure 对空链告警，不静默。

    腰弧长（前片腰缝、机头上口）= ``chain_length_mm(chain_above(ring,
    y_ref))``，y_ref 取腰线与下一条导线之间的任一水平参考。
    """
    n = len(ring.pts)
    cross: list[tuple[int, Point]] = []
    for i in range(n):
        p, q = ring.pts[i], ring.pts[(i + 1) % n]
        if (p.y > y) != (q.y > y):
            t = (y - p.y) / (q.y - p.y)
            cross.append((i, p.lerp(q, t)))
    if len(cross) < 2:
        return []
    for k in range(len(cross)):
        i0, p0 = cross[k]
        j, p1 = cross[(k + 1) % len(cross)]
        j %= n
        chain = [p0]
        idx = (i0 + 1) % n
        while True:
            chain.append(ring.pts[idx])
            if idx == j:
                break
            idx = (idx + 1) % n
        chain.append(p1)
        inner = chain[1:-1]
        if any(p.y > y for p in inner):
            return chain
    return []


def chain_between(ring: Ring, i0: int, i1: int) -> list[Point]:
    """顶点 i0 → i1 的前向（环绕序）链，含两端顶点。角点锚定的边链
    （浪链/外缝链）由 measure 选定锚点索引后调用。"""
    n = len(ring.pts)
    start, end = i0 % n, i1 % n
    out = [ring.pts[start]]
    idx = start
    while idx != end:
        idx = (idx + 1) % n
        out.append(ring.pts[idx])
    return out


def arc_pair(ring: Ring, i0: int, i1: int) -> tuple[list[Point], list[Point]]:
    """两锚点把环分成的前向/后向两段（measure 按语义选段用）。"""
    return chain_between(ring, i0, i1), chain_between(ring, i1, i0)


def chain_length_mm(points: list[Point]) -> float:
    """折线长（ET 弧已离散成密顶点，分段求和即弧长）。"""
    return sum(a.distance_to(b) for a, b in zip(points, points[1:]))


# ---- 条带与拼合 ----


def strip_width_mm(ring: Ring) -> float:
    """闭合条带（腰头）带宽：面积/中线长。

    弯条带 bbox 高会被矢高虚高，禁止用 bbox；闭式解
    ``W² − (P/2)W + A = 0`` 取小根（矩形精确成立，同心圆弧带精确成立；
    一般弯带为一级近似）。等周不等式保证判别式 ≥0，退化回退 A/(P/2)。
    """
    half = ring.total_length() / 2.0
    area = ring.area()
    if half < _EPS:
        return 0.0
    disc = half * half - 4.0 * area
    if disc >= 0.0:
        w = (half - math.sqrt(disc)) / 2.0
        if w > 0.0:
            return w
    return area / half


def extreme_point(ring: Ring, axis: str = "y", side: str = "max") -> Point:
    """极值顶点（裆尖 = 前片净样 x 极值侧的角点，measure 决定朝向）。"""
    if axis not in ("x", "y") or side not in ("min", "max"):
        raise ValueError(f"非法轴/侧：{axis}/{side}")
    key = (lambda p: p.x) if axis == "x" else (lambda p: p.y)
    return max(ring.pts, key=key) if side == "max" else min(ring.pts, key=key)


def rigid_fit_offset(src: list[Point], dst: list[Point]) -> tuple[Vector, float]:
    """纯平移刚体拟合：返回 (平移向量, 平移后残差 RMS)。

    点数须一致（调用方先等弧长重采样）。用于袋口弧全等校验、机头
    拼回大片顶边等"只许平移不许旋转"的口径。
    """
    if len(src) != len(dst) or not src:
        raise ValueError(f"点数不一致或为空：{len(src)} vs {len(dst)}")
    n = len(src)
    cs = Point(sum(p.x for p in src) / n, sum(p.y for p in src) / n)
    cd = Point(sum(p.x for p in dst) / n, sum(p.y for p in dst) / n)
    off = cd - cs
    sq = sum((p + off).distance_to(q) ** 2 for p, q in zip(src, dst))
    return off, math.sqrt(sq / n)


def slope_between(p0: Point, p1: Point) -> float:
    """dx/dy（后中内收斜率口径：腰 CB → 臀 CB 的每 cm 落降内缩量）。
    dy 近零返回 inf（水平）。"""
    dy = p1.y - p0.y
    if abs(dy) < _EPS:
        return math.inf
    return (p1.x - p0.x) / dy


def ring_gap_best(a: Ring, b: Ring, n: int = 200) -> float:
    """两环等弧长重采样后的最小平均点距（含环绕移位与镜像对齐）。

    顶点数漂移下的全等/对称校验（袋布轴对称、跨码形状比对）走这里，
    禁止逐顶点索引对应。
    """
    ra, rb = a.resample(n), b.resample(n)
    br = Ring(tuple(reversed(b.pts)), layer=b.layer)
    rbr = br.resample(n)

    def _mean_shift(base: list[Point], probe: list[Point]) -> float:
        best = float("inf")
        for shift in range(n):
            s = sum(base[i].distance_to(probe[(i + shift) % n])
                    for i in range(n)) / n
            best = min(best, s)
        return best

    return min(_mean_shift(ra, rb), _mean_shift(ra, rbr))


# ---- 角点 / 条带分解（measure 锚定用） ----


def corner_turns(points: list[Point],
                 min_turn_deg: float = 50.0) -> list[tuple[int, Point, float]]:
    """折线角点：相邻段方向变化 |Δ角| ≥ 阈值（角度差取 ±180 环绕最短）。

    返回 (顶点序号, 点, 带符号转角)。顶链上的腰角/袋口拐点识别用。
    """
    out: list[tuple[int, Point, float]] = []
    for i in range(1, len(points) - 1):
        v1 = points[i] - points[i - 1]
        v2 = points[i + 1] - points[i]
        if v1.length < _EPS or v2.length < _EPS:
            continue
        a1 = math.atan2(v1.dy, v1.dx)
        a2 = math.atan2(v2.dy, v2.dx)
        da = math.degrees(a2 - a1)
        while da > 180.0:
            da -= 360.0
        while da < -180.0:
            da += 360.0
        if abs(da) >= min_turn_deg:
            out.append((i, points[i], da))
    return out


def strip_long_edges(ring: Ring) -> tuple[list[Point], list[Point]]:
    """条带环（腰头）两条长边链：段方向缓（|dx|≥|dy|）游程最长的两段。

    端帽（陡段）与长边（缓段）方向差 >45°，是稳定的结构签名；返回
    两链（无序），缝边（下口）与上口由调用方按长短/语义区分。
    """
    runs = _shallow_runs(ring)
    runs.sort(key=lambda r: -r[1])
    edges: list[list[Point]] = []
    for start, length in runs[:2]:
        edges.append(_run_chain(ring, start, length))
    if len(edges) < 2:
        raise ValueError("条带环未找到两条长边（非条带形状？）")
    return edges[0], edges[1]


def _shallow_runs(ring: Ring) -> list[tuple[int, int]]:
    """缓段游程 (start_seg, len)；环绕首尾同缓时拼接（start 可为负）。"""
    n = len(ring.pts)
    runs: list[tuple[int, int]] = []
    cur_start, cur_len = None, 0
    for i in range(n):
        a, b = ring.pts[i], ring.pts[(i + 1) % n]
        if abs(b.x - a.x) >= abs(b.y - a.y):
            if cur_start is None:
                cur_start, cur_len = i, 1
            else:
                cur_len += 1
        else:
            if cur_start is not None:
                runs.append((cur_start, cur_len))
            cur_start, cur_len = None, 0
    if cur_start is not None:
        runs.append((cur_start, cur_len))
    if len(runs) >= 2 and runs[0][0] == 0 and runs[-1][0] + runs[-1][1] == n:
        first, last = runs[0], runs[-1]
        runs = [(last[0] - n, last[1] + first[1])] + runs[1:-1]
    return runs


def _run_chain(ring: Ring, start: int, length: int) -> list[Point]:
    """游程 (start, len) -> 顶点链（start 可为负，环绕取模）。"""
    n = len(ring.pts)
    idx = start % n
    chain = [ring.pts[idx]]
    for _ in range(length):
        idx = (idx + 1) % n
        chain.append(ring.pts[idx])
    return chain


def shallow_run_at_extreme(ring: Ring, side: str) -> list[Point]:
    """含 y 极值顶点的缓段游程链：机头上/下口、后片顶边的直线边提取。

    bbox 角点锚在斜端（机头后中端内收 5.5/15）会被虚拟角吸偏、顶弧
    被污染；含极值顶点的缓段游程不受端部倾斜影响。side="top" 取含
    ymax 顶点者，"bottom" 取 ymin。
    """
    if side not in ("top", "bottom"):
        raise ValueError(f"非法 side：{side}")
    n = len(ring.pts)
    key = (lambda p: p.y)
    v_ext = max(ring.pts, key=key) if side == "top" else min(ring.pts, key=key)
    i_ext = ring.pts.index(v_ext)
    for start, length in _shallow_runs(ring):
        segs = {s % n for s in range(start, start + length)}
        if i_ext in segs or (i_ext - 1) % n in segs:
            return _run_chain(ring, start, length)
    raise ValueError(f"未找到含 {'ymax' if side == 'top' else 'ymin'} 顶点的缓段游程")


def chain_between_shorter(ring: Ring, i0: int, i1: int) -> list[Point]:
    """两锚点间取较短弧（边链提取：袋口侧短边、机头侧端等）。"""
    a, b = arc_pair(ring, i0, i1)
    return a if chain_length_mm(a) <= chain_length_mm(b) else b


def chord_profile(points: list[Point], interior_ref: Point,
                  corner_deg: float = 8.0
                  ) -> tuple[float, float, list[tuple[float, float]]]:
    """开放链对首末弦的法向偏差剖面 -> (弧高, 弧顶弦位, 折角表)。

    挖削袋口弧形态反推用（measure 还原到成衣空间后调用）：
    - 弧高带符号——偏差朝 ``interior_ref``（环内部参考点）一侧为正，
      与袋口参数「向裤片内侧凹入为正」同号；
    - 弧顶弦位 = \|偏差\| 最大点在弦上的投影参数（链首端 0、链末端 1）；
    - 折角表 = [(弦位, 内推深度)]，转角 ≥ ``corner_deg`` 的顶点按链序
      （平滑密采样弧的离散转角远小于 8°，不会误报折角）。
    """
    p0, p1 = points[0], points[-1]
    u = p1 - p0
    length = u.length
    if length < _EPS:
        return 0.0, 0.0, []
    ux, uy = u.dx / length, u.dy / length
    nx, ny = -uy, ux

    def dev(p: Point) -> float:
        w = p - p0
        return w.dx * nx + w.dy * ny

    def chord_at(p: Point) -> float:
        w = p - p0
        return min(max((w.dx * ux + w.dy * uy) / length, 0.0), 1.0)

    flip = 1.0 if dev(interior_ref) >= 0.0 else -1.0
    devs = [flip * dev(p) for p in points]
    k = max(range(len(points)), key=lambda i: abs(devs[i]))
    corners = [(chord_at(points[i]), devs[i])
               for i, _, _ in corner_turns(points, corner_deg)]
    return devs[k], chord_at(points[k]), corners


def resample_chain(points: list[Point], n: int) -> list[Point]:
    """开放折线等弧长重采样 n 点（首尾含端点；``Ring.resample`` 是闭环绕
    向、会把收口弦摊进弧长，开放链禁用）。"""
    if n < 2:
        raise ValueError(f"重采样点数须 ≥ 2，得到 {n}")
    cum = [0.0]
    for a, b in zip(points, points[1:]):
        cum.append(cum[-1] + a.distance_to(b))
    total = cum[-1]
    if total < _EPS:
        return [points[0]] * n
    out: list[Point] = []
    seg_i = 0
    for k in range(n):
        # 先除后乘 + 钳制：total*k/(n-1) 左结合会在 k=n-1 时因舍入
        # 微超 total，游标走完末段后越界（5028 真件触发）
        s = min(total * (k / (n - 1)), total)
        while seg_i + 1 < len(cum) and cum[seg_i + 1] < s:
            seg_i += 1
        a, b = points[seg_i], points[seg_i + 1]
        seg_len = cum[seg_i + 1] - cum[seg_i]
        t = 0.0 if seg_len < _EPS else (s - cum[seg_i]) / seg_len
        out.append(a.lerp(b, t))
    return out


def chain_congruence_rms(a: list[Point], b: list[Point],
                         n: int = 32) -> float:
    """两开放折线的平移全等 RMS（袋口弧前片 vs 袋布/袋贴校验）。

    铺版嵌套可把片镜像摆放，取 正向/反向 两种走 向的平移拟合最小值
    （只许平移不许旋转——弧本身就是同一根）。
    """
    ra = resample_chain(a, n)
    best = float("inf")
    for cand in (resample_chain(b, n),
                 list(reversed(resample_chain(b, n)))):
        _, rms = rigid_fit_offset(ra, cand)
        best = min(best, rms)
    return best

