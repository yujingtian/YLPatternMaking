#!/usr/bin/env python3
"""MakeHuman CC0 数据 vendor：base.obj + .target → 前端 bodymesh 二进制包。

数据来源：makehumancommunity/makehuman tag v1.3.0（commit 1f508f60），
捆绑资产 CC0 1.0（LICENSE.ASSETS.md，§D 输出物无主张）——只借数据不移植代码（AGPL 红线）。

用法（仓库根）：
    python scripts/vendor_makehuman.py                       # 常规：vendor/ → public/bodymesh/
    python scripts/vendor_makehuman.py --probe               # 只出诊断报告（地标/围度/宽度表），不写产物
    python scripts/vendor_makehuman.py --cut-above-waist 15  # 裁切高度（腰上 cm，默认 15）

流程：解析 base.obj（dm→cm、+Z 前自检）→ 应用女性 macro（烘进基网格）→ 腿去外张
（A-pose → 腿轴竖直）→ 腿内收（A-pose 腿间距 gap 5~6.5cm → ≤2cm，逐高度共向平移、
切片周长不变）→ 两阶段裁切（先粗裁 ~0.73H + 最大连通域过滤去臂/手〔裁切面必须低于
腋窝褶 ~0.75H，否则手臂经肩与躯干连通无法过滤〕→ 检测地标 → 按腰+cut 精裁 → 再过滤
→ 边界环质心扇形封盖）→ target 顶点索引按裁切重映射（thigh±/knee± 除外——原生
measure-*-circ 的 canonical 站与我们站点错位〔thigh 峰 crotch−14 vs 站 crotch−3、
knee 峰 ~45.5 vs 站 48.06，站点灵敏度仅峰值 39%，闭环为凑站点围度把权重推大〕，
且原生 knee+ 上缘 y57-66 是纯内侧 −x 剪切边、满钳 1.0 可达膝围 40.8 够不着常见
输入 43~46 → 常年满钳把大腿中段往中线拖〔「腿部中段往中间扭曲」根因，2026-09-11
逐顶点数字坐实〕，二者改用派生径向保形场替换，见 derived_thigh_targets /
derived_knee_targets）
→ 地标存顶点索引（morph 后运行时重读）→ w=0/0.5/1 站点围度预标定（影响矩阵）
→ 产出 base.bin + targets.json。

产物坐标：cm，y 轴向上、原点 = 脚底中心（sole=0）、+Z = 身体前方、+X = 模特右（镜像对称体）。
对齐（缩放/平移到 payload 站系）是运行时行为，不在本脚本。

base.bin 布局（little-endian）：
    uint32 V, uint32 F, uint32 T
    float32 × 3V     顶点位置（cm）
    uint32  × 3F     三角形索引（0-based）
    每个 target 依次：uint32 n；uint32 × n 顶点索引；float32 × 3n 增量（cm）
targets.json：目标名（与 T 顺序一致）/ 地标顶点索引 / 站点高度 / 预标定影响矩阵 / 来源溯源。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import struct
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# 站点定义：名 → (per, 相对地标的 canonical 高度来源)。thigh 取裆下 3cm（对齐现引擎缺省口径）。
STATIONS = [
    ("waist", "body"),
    ("hips", "body"),
    ("thigh", "leg"),
    ("knee", "leg"),
]
MEASURE_TARGETS = {
    "waist": ("measure-waist-circ-incr.target", "measure-waist-circ-decr.target"),
    "hips": ("measure-hips-circ-incr.target", "measure-hips-circ-decr.target"),
    "thigh": ("measure-thigh-circ-incr.target", "measure-thigh-circ-decr.target"),
    "knee": ("measure-knee-circ-incr.target", "measure-knee-circ-decr.target"),
}
DEFAULT_FEMALE = ""  # base.obj 本身 = universal female young average（实测 universal-female-* 为 0 增量 identity），无需女性 macro

EPS = 1e-9


# ---------------------------------------------------------------- 解析

def parse_obj(path: Path, group: str = "body"):
    """返回 (verts[dm], faces[四边形 0-based 索引])，只保留指定 g 组（默认 body 皮肤面；
    helper-tights/joint-*/helper-genital 等辅助几何全部丢弃——body 组自身水密且裆部平滑）。
    OBJ 面索引 1-based、可带 v/t/n 斜杠。"""
    verts: list[list[float]] = []
    faces: list[list[int]] = []
    cur = None
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ln.startswith("g "):
            cur = ln.split()[1] if len(ln.split()) > 1 else ""
        elif ln.startswith("v "):
            _, x, y, z = ln.split()[:4]
            verts.append([float(x), float(y), float(z)])
        elif ln.startswith("f ") and cur == group:
            faces.append([int(tok.split("/")[0]) - 1 for tok in ln.split()[1:]])
    return verts, faces


def parse_target(path: Path) -> dict[int, tuple[float, float, float]]:
    """返回 {顶点索引(0-based): (dx,dy,dz) dm}。索引基数由自检语义校验兜底（MPFB2/maketarget 均 0-based）。"""
    deltas: dict[int, tuple[float, float, float]] = {}
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ln.startswith("#") or not ln.strip():
            continue
        p = ln.split()
        if len(p) == 4:
            deltas[int(p[0])] = (float(p[1]), float(p[2]), float(p[3]))
    return deltas


def quads_to_tris(faces: list[list[int]]) -> list[tuple[int, int, int]]:
    tris: list[tuple[int, int, int]] = []
    for f in faces:
        if len(f) < 3:
            continue
        for k in range(1, len(f) - 1):
            tris.append((f[0], f[k], f[k + 1]))
    return tris


# ---------------------------------------------------------------- 网格手术

def apply_target(verts: list[list[float]], target: dict[int, tuple[float, float, float]], w: float):
    """pos = base + w·Δ（就地拷贝语义：返回新列表；dm×10=cm 的换算在读取后统一已做）。"""
    out = [list(v) for v in verts]
    for i, d in target.items():
        if i < len(out):
            out[i][0] += w * d[0]
            out[i][1] += w * d[1]
            out[i][2] += w * d[2]
    return out


def cut_below(verts, tris, y_cut: float):
    """平面裁剪保留 y ≤ y_cut 部分。跨面三角形按边插值裁出下半多边形再三角化。
    返回 (新顶点表[原顶点 + 交点], 新三角形, keep_map[原索引→新索引], cut_count)。"""
    n = len(verts)
    out_v = [list(v) for v in verts]
    keep = {i for i in range(n) if verts[i][1] <= y_cut}
    new_tris: list[tuple[int, int, int]] = []
    crossings = 0
    ip_cache: dict[tuple[int, int], int] = {}  # 无序边 → 交点索引（相邻三角形共享切缝顶点，否则边界环断裂、不水密）

    def edge_ip(a: int, b: int) -> int:
        key = (a, b) if a < b else (b, a)
        if key in ip_cache:
            return ip_cache[key]
        va, vb = verts[a], verts[b]
        t = (y_cut - va[1]) / (vb[1] - va[1])
        out_v.append([
            va[0] + t * (vb[0] - va[0]),
            y_cut,
            va[2] + t * (vb[2] - va[2]),
        ])
        ip_cache[key] = len(out_v) - 1
        return ip_cache[key]

    for (a, b, c) in tris:
        above = [i for i in (a, b, c) if verts[i][1] > y_cut]
        if not above:
            new_tris.append((a, b, c))
        elif len(above) == 3:
            continue
        else:
            crossings += 1
            # 展开为有向边序列，逐边裁剪（Sutherland–Hodgman 风格，保绕向）
            poly: list[int] = []
            ring = (a, b, c)
            for k in range(3):
                p, q = ring[k], ring[(k + 1) % 3]
                pv, qv = verts[p][1] <= y_cut, verts[q][1] <= y_cut
                if pv:
                    poly.append(p)
                if pv != qv:
                    poly.append(edge_ip(p, q))
            for k in range(1, len(poly) - 1):
                new_tris.append((poly[0], poly[k], poly[k + 1]))
    keep_map = {old: new for new, old in enumerate(range(n)) if old in keep}
    return out_v, new_tris, keep_map, crossings


def largest_component(tris):
    """面邻接 BFS，返回 (最大连同域三角形列表, 各连同域面数列表)。"""
    import collections
    vert_tris = collections.defaultdict(list)
    for t_i, t in enumerate(tris):
        for v in t:
            vert_tris[v].append(t_i)
    seen = [False] * len(tris)
    sizes = []
    best_c: list[int] | None = None
    for t_i in range(len(tris)):
        if seen[t_i]:
            continue
        queue = [t_i]
        seen[t_i] = True
        comp = []
        while queue:
            cur = queue.pop()
            comp.append(cur)
            for v in tris[cur]:
                for nb in vert_tris[v]:
                    if not seen[nb]:
                        seen[nb] = True
                        queue.append(nb)
        sizes.append(len(comp))
        if best_c is None or len(comp) > len(best_c):
            best_c = comp
    best = [tris[i] for i in sorted(best_c)] if best_c is not None else []
    return best, sizes


def boundary_loops(tris):
    """有向边界环。闭合定向流形中相邻三角形共享边互为反向对 (a,b)/(b,a)——
    判据是有向计数 != 反向计数（相等=内部、单侧=真边界、不等重数=撕裂也暴露）。"""
    import collections
    edge_count = collections.Counter()
    for (a, b, c) in tris:
        for e in ((a, b), (b, c), (c, a)):
            edge_count[e] += 1
    boundary = {e for e in edge_count if edge_count[e] != edge_count.get((e[1], e[0]), 0)}
    nxt = {a: b for a, b in boundary}
    loops = []
    while nxt:
        start, follow = next(iter(nxt.items()))
        loop = [start]
        nxt.pop(start)
        while follow != start:
            loop.append(follow)
            follow = nxt.pop(follow)
        loops.append(loop)
    return loops


def cap_loops(verts, tris, loops):
    """边界环质心扇形封盖。共享边反向规则：已有面含 a→b，盖面用 (b, a, c)。"""
    import statistics
    for loop in loops:
        cx = statistics.fmean(verts[i][0] for i in loop)
        cy = statistics.fmean(verts[i][1] for i in loop)
        cz = statistics.fmean(verts[i][2] for i in loop)
        verts.append([cx, cy, cz])
        c = len(verts) - 1
        for k in range(len(loop)):
            a, b = loop[k], loop[(k + 1) % len(loop)]
            tris.append((b, a, c))
    return verts, tris


def compact(verts, tris):
    """删除无引用顶点，返回 (紧凑顶点表, 新三角形, old→new 映射)。"""
    used = sorted({v for t in tris for v in t})
    remap = {old: new for new, old in enumerate(used)}
    new_verts = [verts[i] for i in used]
    new_tris = [(remap[a], remap[b], remap[c]) for a, b, c in tris]
    return new_verts, new_tris, remap


def check_watertight(tris) -> tuple[bool, int]:
    """每条无向边恰被 2 面共享 → 水密。返回 (水密?, 边数)。"""
    import collections
    ec = collections.Counter()
    for (a, b, c) in tris:
        for e in ((a, b), (b, c), (c, a)):
            ec[(min(e), max(e))] += 1
    bad = sum(1 for n in ec.values() if n != 2)
    return bad == 0, len(ec)


# ---------------------------------------------------------------- 地标与围度

def band_stat(verts, y0, y1, axis, reducer, side=None):
    """[y0,y1) 带内顶点在 axis 上的 reducer（side='+' 只取 x>0，'-' 只取 x<0）。"""
    vals = [v[axis] for v in verts if y0 <= v[1] < y1 and (side is None or (side == "+" and v[0] > 0) or (side == "-" and v[0] < 0))]
    return reducer(vals) if vals else None


def detect_landmarks(verts, tris, probe: dict):
    """启发式地标（返回高度 dict；顶点索引由 nearest_vertex 补）。
    裆=腿分离带向上首个中线收敛处；腰/臀/膝/踝全部走切片围度（顶点带 x 极值有
    ~2cm 顶点行锯齿伪影，弃用）。"""
    sole = min(v[1] for v in verts)
    height = max(v[1] for v in verts) - sole
    probe["sole"] = sole
    probe["height"] = height

    step = 1.0

    def inner_clear(y):  # 带内最小 |x|（裆下腿分离 → 大；会阴 → ~0）
        vals = [abs(v[0]) for v in verts if y <= v[1] < y + step]
        return min(vals) if vals else None

    # 裆：自大腿中部向上扫，腿分离带（|x| 大）首次收敛到 <0.6cm 处 = 会阴
    #    （不能自上而下扫——躯干前/后中线上永远有 |x|≈0 顶点，会在腰腹误触发；
    #     上界放宽到 mesh 顶——粗裁后 mesh 高度可能不足 0.60H×全身，而腿下方永不会误触发）
    y = sole + 0.40 * height
    crotch = None
    while y < sole + height - step:
        ic = inner_clear(y)
        if ic is not None and ic < 0.6:
            crotch = y
            break
        y += step
    if crotch is None:
        raise RuntimeError("裆地标检测失败（自 0.40H 向上无 |x|<0.6 带）")

    # 臀：[crotch+1, crotch+9] 切片围度最大带（标准臀围=最丰满处周长，最宽点在大转子
    # 一带≈裆±2cm；搜索带必须在裆上方——裆下切片跨双腿围度求和会虚高）。
    # 腰：[crotch+12, crotch+28] 切片围度平滑最小（自然腰=臀上最细处，约 crotch+20；
    # MakeHuman 自家 waist target 增量带同带佐证）。
    # 两处均弃用「顶点 x 极值宽度」：顶点行 ~2cm 间距使逐带 min/max 严重锯齿
    # （稀疏带宽度假窄，实测把腰拽到髂骨上凹、把臀拽到裆下大腿顶）。
    # 搜索带须在裆叉喇叭带之上（2026-09-12 实测旧带 crotch+1..+9 把叉环伪值
    # ~115 当臀；真臀 max 在裆+6..12 一带）
    ys = _frange(crotch + 6, crotch + 14, step)
    gs = [girth_at(verts, tris, y + 0.5) or 0.0 for y in ys]
    hip = ys[_local_extremum(gs, "max")]
    ys = _frange(crotch + 12, crotch + 28, step)
    gs = [girth_at(verts, tris, y + 0.5) or 0.0 for y in ys]
    waist = ys[_local_extremum(gs, "min")]

    # 膝：右腿围度在 [crotch-35, crotch-15] 的局部极小
    knee = _girth_local_min(verts, tris, crotch - 35.0, crotch - 15.0)
    # 踝：右腿围度在 [sole+2, knee-8] 的局部极小
    ankle = _girth_local_min(verts, tris, sole + 2.0, knee - 8.0)
    return {"sole": sole, "crotch": crotch, "hip": hip, "waist": waist, "knee": knee, "ankle": ankle, "height": height}


def _girth_local_min(verts, tris, y0, y1):
    """右腿切片围度在 [y0,y1) 的局部极小高度（1cm 步、3 点平滑）。"""
    import statistics
    ys = _frange(y0, y1, 1.0)
    gs = []
    for y in ys:
        g = girth_at(verts, tris, y + 0.5, leg_side="+")
        gs.append(g if g else 0.0)
    sm = [statistics.fmean(gs[max(0, i - 1): i + 2]) for i in range(len(gs))]
    best_i = min(range(len(sm)), key=lambda i: sm[i])
    return ys[best_i] + 0.5


def _frange(a, b, step):
    out = []
    y = a
    while y < b - EPS:
        out.append(round(y, 4))
        y += step
    return out


def _local_extremum(vals, mode):
    """序列（含 None 防御）平滑后返回极小/极大值位置（索引）。"""
    import statistics
    clean = [v if v is not None else (statistics.fmean([x for x in vals if x is not None])) for v in vals]
    sm = [statistics.fmean(clean[max(0, i - 1): i + 2]) for i in range(len(clean))]
    best_i, best_v = 0, (max(sm) if mode == "min" else min(sm))
    for i, v in enumerate(sm):
        if (mode == "min" and v < best_v) or (mode == "max" and v > best_v):
            best_i, best_v = i, v
    return best_i


def nearest_vertex(verts, y, side_axis=None, side_sign=1.0):
    """离 (x=side 约束, y, z=0) 最近的顶点索引——地标锚点。"""
    best, bd = 0, float("inf")
    for i, v in enumerate(verts):
        if abs(v[1] - y) > 2.0:
            continue
        d = (v[1] - y) ** 2 + v[2] ** 2
        if side_axis == 0 and v[0] * side_sign <= 0:
            d += 1e6
        if d < bd:
            best, bd = i, d
    return best


def _slice_loops(verts, tris, y):
    """平面切片闭环：返回 [(环点列, 质心 x)]。与 girth_at 原实现同口径
    （交点按无序边坐标哈希共享、顶点恰在平面上计入「下」）。"""
    segs = []
    for (a, b, c) in tris:
        vs = [verts[a], verts[b], verts[c]]
        ds = [v[1] - y for v in vs]
        if all(d <= 0 for d in ds) or all(d > 0 for d in ds):
            continue
        pts = []
        ring = ((0, 1), (1, 2), (2, 0))
        for i, j in ring:
            if ds[i] <= 0 < ds[j] or ds[j] <= 0 < ds[i]:
                t = ds[i] / (ds[i] - ds[j])
                pts.append((
                    vs[i][0] + t * (vs[j][0] - vs[i][0]),
                    vs[i][2] + t * (vs[j][2] - vs[i][2]),
                ))
        if len(pts) == 2 and (pts[0] != pts[1]):
            segs.append((pts[0], pts[1]))
    if not segs:
        return []
    def key(p):
        return (round(p[0], 3), round(p[1], 3))
    from collections import defaultdict
    ends = defaultdict(list)
    for i, (p, q) in enumerate(segs):
        ends[key(p)].append(i)
        ends[key(q)].append(i)
    used = [False] * len(segs)
    loops = []
    for i in range(len(segs)):
        if used[i]:
            continue
        loop = [segs[i]]
        used[i] = True
        cur = segs[i][1]
        while True:
            cands = [j for j in ends[key(cur)] if not used[j]]
            if not cands:
                break
            j = cands[0]
            used[j] = True
            nxt = segs[j][1] if key(segs[j][0]) == key(cur) else segs[j][0]
            loop.append(segs[j])
            cur = nxt
        pts = [s[0] for s in loop]
        cx = sum(p[0] for s in loop for p in s) / (2 * len(loop))
        loops.append((pts, cx))
    return loops


def _leg_cx(verts, tris, y, side):
    """指定侧腿环质心 x（该侧 |cx| 最大的环；无环返回 None）。"""
    loops = _slice_loops(verts, tris, y)
    cand = [l for l in loops if (l[1] > 0 if side == "+" else l[1] < 0)]
    if not cand:
        return None
    return max(cand, key=lambda l: abs(l[1]))[1]


def girth_at(verts, tris, y, leg_side=None):
    """平面切片围度（cm）。三角形与平面求交 → 线段 → 链环 → 周长。
    leg_side='+' 取质心 x>0 的环（右腿），'-' 左腿，None 全部环之和。"""
    total = 0.0
    for pts, cx in _slice_loops(verts, tris, y):
        if leg_side == "+" and cx <= 0:
            continue
        if leg_side == "-" and cx >= 0:
            continue
        total += sum(((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5
                     for p, q in zip(pts, pts[1:] + pts[:1]))
    return total or None


# ---------------------------------------------------------------- 腿去外张

def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 3.0 * t * t - 2.0 * t * t * t


def desplay_legs(verts, tris):
    """A-pose 绑定姿势腿去外张（base.obj 实测：腿环质心自裆 ±9.6 外撇到踝 ±22，
    ≈10.3°/腿）。人台需要并拢站立腿。

    每顶点 XY 平面旋转（z 不动）：pivot = 中轴 (0, crotch+6)，角度 = 腿轴
    LSQ 斜率反演；权重 = y 向 smoothstep〔裆−8 全量 → 裆+8 零〕× |x| 向
    smoothstep〔|x|≤2 会阴中带刚性 → |x|≥7 全量〕——中带保护使裆顶点
    （x≈0）不被左右两侧相反方向的旋转撕裂，blend 带内连续剪切保水密。
    返回 (新顶点, tris 原样, phi[紧凑索引], 诊断 dict)；phi 供 targets
    增量随各自顶点同旋转（morph 语义 = 旋转后场：R(p)+w·d = R(p+w·d)）。"""
    sole = min(v[1] for v in verts)
    height = max(v[1] for v in verts) - sole
    # 裆粗定位（同 detect_landmarks 的 inner_clear 口径，独立轻量版）
    y = sole + 0.35 * height
    crotch = None
    while y < sole + height - 1.0:
        vals = [abs(v[0]) for v in verts if y <= v[1] < y + 1.0]
        if vals and min(vals) < 0.6:
            crotch = y
            break
        y += 1.0
    if crotch is None:
        raise RuntimeError("去外张：裆高度检测失败")
    # 腿轴斜率 LSQ：右腿环质心 over [20, crotch−12]（踝上、blend 带下全域）
    cxs = []
    for yy in _frange(20.0, crotch - 12.0 + EPS, 4.0):
        c = _leg_cx(verts, tris, yy, "+")
        if c is not None:
            cxs.append((yy, c))
    if len(cxs) < 3:
        raise RuntimeError(f"去外张：腿轴采样不足（{len(cxs)} 点）")
    n = len(cxs)
    yb = sum(a for a, _ in cxs) / n
    cb = sum(c for _, c in cxs) / n
    slope = sum((a - yb) * (c - cb) for a, c in cxs) / sum((a - yb) ** 2 for a, _ in cxs)
    alpha = math.atan(-slope)
    if not (0.03 < alpha < 0.30):
        raise RuntimeError(f"去外张：外张角 {math.degrees(alpha):.1f}° 超合理带 [1.7°, 17°]")
    y_pivot = crotch + 6.0
    out = []
    phi = [0.0] * len(verts)
    for i, (x, yy, z) in enumerate(verts):
        wy = _smoothstep((crotch + 8.0 - yy) / 16.0)
        wx = _smoothstep((abs(x) - 2.0) / 5.0)
        w = wy * wx
        # 右腿 (x>0) 向内 = 负角；左腿镜像正角；x=0 顶点零旋转
        f = (alpha if x < 0 else -alpha) * w if x != 0 else 0.0
        phi[i] = f
        if f == 0.0:
            out.append([x, yy, z])
            continue
        cf, sf = math.cos(f), math.sin(f)
        out.append([x * cf - (yy - y_pivot) * sf,
                    y_pivot + x * sf + (yy - y_pivot) * cf, z])
    # 自检：去外张后腿轴竖直（裆下三点质心差 < 1.2cm）
    checks = [round(yy, 1) for yy in (crotch - 10.0, crotch - 25.0, crotch - 45.0)]
    cxs2 = {yy: _leg_cx(out, tris, yy, "+") for yy in checks}
    spread = max(cxs2.values()) - min(cxs2.values())
    if spread > 1.2:
        raise RuntimeError(f"去外张：残差外张 {spread:.2f}cm（{cxs2}）")
    # 旋转使腿长微缩、脚下探 → 重新归零脚底
    drop = min(v[1] for v in out)
    out = [[v[0], v[1] - drop, v[2]] for v in out]
    return out, tris, phi, {
        "crotchRaw": round(crotch, 2), "alphaDeg": round(math.degrees(alpha), 2),
        "soleDrop": round(drop, 2), "samples": len(cxs),
        "axisAfter": {k: round(v, 2) for k, v in cxs2.items()},
    }


# ---------------------------------------------------------------- 腿内收

def adduct_thighs(verts, tris, crotch, gap_thigh=2.0, gap_calf=3.5, y_bot=30.0,
                  fork_ramp_cm=12.0):
    """A-pose 腿间距内收（去外张只对直腿轴、pivot 在裆上，裆下腿轴间距 ~19cm
    原样保留：膝上 gap 5.3~6.5、膝下 6.2~7.7，真实并拢站姿应 ≤2/3.5）。逐 1cm
    高度量右腿环内侧间隙 gap(y)=2·min|x|，单侧内收 δ(y)=max(0, gap−target)/2
    （分段目标：大腿段〔膝上〕→2、小腿段〔膝下〕→3.5〔胫骨微内翻多留 1.5〕，
    ±2cm 线性过渡；踝上 6cm 渐入 ramp；脚部原生不动——gap 8~11 是自然外展
    站姿）。

    **叉部渐出 fork_ramp_cm（2026-09-12「球包/腿往中间收拢」根因修复）**：
    大腿上部与臀胯长在一起，δ 若在裆下即达全量（旧版实测 dy−2 处 δ≈2.1），
    等于把大腿干从臀线正下方整体拽进 2.2cm——外缘在裆下 3cm 内撕出 2.6cm
    台阶（desplay 后自然锥线 18.3→16.9 每cm仅降0.2，平移后 18.32→15.95），
    正视读作「大腿外侧球包+凹口+腿往中线收拢」。修法：δ 自 crotch−2 起
    12cm 线性渐出至全量——臀线锚定不动，gap 剖面变「裆下 ~6 渐收、裆下
    15cm 处到 2」（=环模型时代用户拍板「裆下 ~5cm 内分开、大腿中段 ≥2」），
    腿轴由竖直改自然内斜（股骨斜度 ~2.3°）。平移是刚体 → 围度/地标高度/
    水密/裁切面零影响，纯位置修复。自检 1 守卫带随之收窄到渐出带以下；
    自检 2 竖直改共线（斜轴是设计意图，弯轴才是回归）；新增自检 3 外缘
    Lipschitz（每cm 骤降 ≤0.5，旧台阶 0.85~1.0 必红）。"""
    knee_line = crotch - 32.0

    def tgt_at(y):
        if y <= knee_line - 2.0:
            return gap_calf
        if y >= knee_line + 2.0:
            return gap_thigh
        t = (y - (knee_line - 2.0)) / 4.0
        return gap_calf + t * (gap_thigh - gap_calf)

    ys2 = [round(y + 0.5, 3) for y in _frange(y_bot, crotch - 0.5, 1.0)]
    raw = {}
    for y in ys2:
        loops = _slice_loops(verts, tris, y)
        cand = [(pts, cx) for pts, cx in loops if cx > 2.0]
        if not cand:
            continue  # 切片失败的孤立带（顶点行恰在平面上），事后线性填充
        pts, _ = max(cand, key=lambda l: l[1])
        gap = 2.0 * min(p[0] for p in pts)
        ramp = min(1.0, (y - y_bot) / 6.0)  # 踝上渐入，脚不动
        fork = min(1.0, max(0.0, ((crotch - 2.0) - y) / fork_ramp_cm))  # 叉部渐出
        raw[y] = max(0.0, (gap - tgt_at(y)) / 2.0) * ramp * fork
    if len(raw) < len(ys2) * 0.5:
        raise RuntimeError(f"腿内收：gap 采样不足（{len(raw)}/{len(ys2)}）")
    # 缺测带线性填充（端点取最近有效值）
    filled = []
    for y in ys2:
        if y in raw:
            filled.append(raw[y])
            continue
        prev = [raw[k] for k in ys2 if k < y and k in raw]
        nxt = [raw[k] for k in ys2 if k > y and k in raw]
        if prev and nxt:
            filled.append(0.5 * (prev[-1] + nxt[0]))
        else:
            filled.append(prev[-1] if prev else (nxt[0] if nxt else 0.0))
    sm = [sum(filled[max(0, i - 1): i + 2]) / len(filled[max(0, i - 1): i + 2])
          for i in range(len(filled))]

    def d_at(y):
        if y <= ys2[0]:
            return sm[0]
        if y >= ys2[-1]:
            return sm[-1]
        for k in range(1, len(ys2)):
            if y <= ys2[k]:
                t = (y - ys2[k - 1]) / (ys2[k] - ys2[k - 1])
                return sm[k - 1] + t * (sm[k] - sm[k - 1])
        return sm[-1]

    out = []
    for x, y, z in verts:
        if y <= y_bot or y >= crotch - 0.5 or x == 0.0:
            out.append([x, y, z])  # 脚/踝下/骨盆带不动；x=0 顶点无归属
            continue
        d = d_at(y)
        out.append([x - d if x > 0 else x + d, y, z])

    # 自检 1：收后相对各自带目标的残差（3 点平滑削峰 ~1cm，容差 1.2）——
    # 守卫带收窄到叉部渐出带以下（渐出带 gap 高于目标是设计意图，见 docstring）
    max_over = 0.0
    for y in _frange(y_bot + 6.0, crotch - 3.0 - fork_ramp_cm, 2.0):
        loops = _slice_loops(out, tris, y + 0.5)
        cand = [(pts, cx) for pts, cx in loops if cx > 2.0]
        if not cand:
            continue
        pts, _ = max(cand, key=lambda l: l[1])
        max_over = max(max_over, 2.0 * min(p[0] for p in pts) - tgt_at(y + 0.5))
    if max_over > 1.2:
        raise RuntimeError(f"腿内收不足：残 gap 超带目标 {max_over:.2f} > 1.2")
    # 自检 2：腿轴散布（叉部渐出后轴自然内斜，spread 放宽到 2.5；方向守卫保留：
    # 低处不得比高处更外 >1.0——外撇才是回归。共线口径弃用：质心轴本身带解剖
    # 弯度〔pre-adduct 二阶差分 ~0.95、旧出货 ~1.8〕，0.8 阈值定错红过）
    cxs = [_leg_cx(out, tris, y, "+") for y in (crotch - 10.0, crotch - 25.0, crotch - 45.0)]
    if any(c is None for c in cxs):
        raise RuntimeError(f"腿内收自检：腿环缺失 {cxs}")
    spread = max(cxs) - min(cxs)
    if spread > 2.5:
        raise RuntimeError(f"腿内收破坏腿轴：spread {spread:.2f}cm > 2.5（δ 曲线过陡）")
    if cxs[2] > cxs[0] + 1.0:
        raise RuntimeError(f"腿轴低处显著更外（{cxs[2]:.2f} > {cxs[0]:.2f}+1.0，外张未去净）")
    # 自检 3：外缘轮廓连续（叉部渐出的存在意义）——裆下 17 到裆上+1 每cm
    # 外缘骤降 ≤0.5cm（旧版整段平移实测 0.6~1.0 = 球包/台阶；自然锥度 0.2~0.4；
    # 升序采样、相邻差取 upper−lower = 向下的骤降，_frange 不支持负步长）
    edge = []
    for y in _frange(crotch - 17.0, crotch + 1.0, 1.0):
        loops = _slice_loops(out, tris, y)
        if not loops:
            continue
        edge.append(max(abs(p[0]) for l in loops for p in l[0]))
    cliff = max((edge[i + 1] - edge[i] for i in range(len(edge) - 1)), default=0.0)
    if cliff > 0.5:
        raise RuntimeError(f"外缘台阶 {cliff:.2f}cm/cm > 0.5（叉部渐出失效，球包回归）")
    # 自检 4：渐出不得引入新回升——post 剖面相邻回升 ≤ pre 剖面回升 +0.3。
    # post = pre − 2δ(y) 且 δ 沿向下单调不减 → 结构上 post 回升恒 ≤ pre 回升；
    # 唯能红的是 δ 剖面自 wiobble（回摆）。旧的「post 单调不升」绝对口径与
    # 解剖相悖（臀褶带 pre gap 本自然回升 ~0.9，fork≈0 处 post 忠实跟随 pre，
    # 曾误报 0.90）且守卫带相位依赖 crotchRaw 估计，2026-09-12 改 pre 相对口径
    gaps = []
    gaps_pre = []
    for d in range(2, 17, 2):
        val = []
        for mesh in (out, verts):
            loops = _slice_loops(mesh, tris, crotch - d)
            cand = [(pts, cx) for pts, cx in loops if cx > 2.0]
            if not cand:
                val = []
                break
            pts, _ = max(cand, key=lambda l: l[1])
            val.append(2.0 * min(p[0] for p in pts))
        if val:
            gaps.append(val[0])
            gaps_pre.append(val[1])
    rises = max((gaps[i + 1] - gaps[i] for i in range(len(gaps) - 1)), default=0.0)
    rises_pre = max((gaps_pre[i + 1] - gaps_pre[i]
                     for i in range(len(gaps_pre) - 1)), default=0.0)
    if rises > rises_pre + 0.3:
        raise RuntimeError(f"gap 剖面回升 {rises:.2f} > pre 解剖回升 {rises_pre:.2f}"
                           "+0.3（渐出带 δ 剖面回摆）")
    return out, {"gapThigh": gap_thigh, "gapCalf": gap_calf, "yBot": y_bot,
                 "dMax": round(max(sm), 2), "maxOver": round(max_over, 2),
                 "axisSpread": round(spread, 2), "outerCliff": round(cliff, 2),
                 "gapRampRise": round(rises, 2)}


def _derived_radial_field(verts, tris, y_st, half_below, half_above, amp0, medial_att):
    """派生径向保形场构建核心（thigh±/knee± 共用）。逐顶点相对**该高度腿环
    质心**的径向增量（截面形状保持 base 解剖轮廓），cos² 窗**非对称**——下半
    宽 half_below、上半宽 half_above，窗值与一阶导在两缘精确归零（与相邻场
    无缝衔接，无剪切边）；峰值幅度 amp0 cm@w=1；内侧（径向指向中线）幅度
    ×medial_att（互穿防线，按各站间隙预算取值，见两包装函数 docstring）；
    dy≡0 站点高度不漂（踝/膝对齐地标不受累）。腿环在裆上并入整圈躯干，
    窗上半自动失效（增量止于大腿分离带）。返回 (plus, minus) 增量 dict。"""
    y_lo, y_hi = y_st - half_below, y_st + half_above

    def window(y):
        half = half_below if y <= y_st else half_above
        return math.cos(math.pi * (y - y_st) / (2.0 * half)) ** 2

    centers = {}
    for y in _frange(y_lo, y_hi, 1.0):
        loops = _slice_loops(verts, tris, y + 0.5)
        cand = [(pts, cx) for pts, cx in loops if cx > 2.0]
        if not cand:
            continue
        pts, cx = max(cand, key=lambda l: l[1])
        centers[round(y + 0.5, 3)] = (cx, sum(p[1] for p in pts) / len(pts))
    cys = sorted(centers)
    if len(cys) < 10:
        raise RuntimeError(f"派生径向场：腿环采样不足（{len(cys)}）")

    def center_at(y):
        if y <= cys[0] or y >= cys[-1]:
            return None
        for k in range(1, len(cys)):
            if y <= cys[k]:
                t = (y - cys[k - 1]) / (cys[k] - cys[k - 1])
                a, b = centers[cys[k - 1]], centers[cys[k]]
                return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        return None

    plus, minus = {}, {}
    for i, (x, y, z) in enumerate(verts):
        # |x|<0.9 = 裆中带顶点不加增量（防内列顶点跨侧歧义）；大腿/膝最内列
        # （adduct 后 min|x|≈1.0）保留在内——胖腿时根部贴合（内侧衰减兜底）
        if not (y_lo <= y <= y_hi) or abs(x) < 0.9:
            continue
        c = center_at(y)
        if c is None:
            continue
        cx, cz = c
        if x < 0:
            cx = -cx  # 左腿镜像质心（网格左右对称）
        dx, dz = x - cx, z - cz
        r = math.hypot(dx, dz)
        if r < 1e-6:
            continue
        amp = amp0 * window(y)
        ux, uz = dx / r, dz / r
        if (x > 0 and ux < 0) or (x < 0 and ux > 0):
            amp *= medial_att  # 内侧衰减：病理权重下两腿互穿防线
        plus[i] = (amp * ux, 0.0, amp * uz)
        minus[i] = (-amp * ux, 0.0, -amp * uz)
    return plus, minus


def derived_thigh_targets(verts, tris, crotch, knee_y):
    """派生 thigh± target：以 payload thigh 站（crotch−3）为峰值的**径向保形
    膨胀场**，替换 MakeHuman 原生 measure-thigh-circ（原生 Δgirth 峰值带在
    crotch−14 = 它自家 canonical 站，与我们站点错位 11cm：站点灵敏度仅峰值
    39%，闭环为凑站点围度把权重推大、大腿中段被撑爆、根部反而紧——「调
    大腿围变粗位置太靠下」根因，2026-09-11 用户目检 + _diag_thigh 数字坐实）。

    非对称窗（2026-09-11 二轮报障「大腿→膝维度不渐变」修复）：下半宽 =
    站点到膝标（≈29.5，W(膝站)=0 精确归零 → 膝围串扰≈0），**下尾自大腿根
    部峰值单调递减一路铺到膝**——替代旧对称半宽 18 在 crotch−21 截断留下的
    膝上 11.5cm 死区（死区+台阶 =「调大腿围时大腿→膝收窄突变」根因）。
    上半 15：裆上被腿环并入躯干自然截断（实测对臀站泄漏 0）。峰值幅度
    0.8cm@w=1（站点 Δg≈4.1，与原生同量级 → 闭环权重量级不变）；内侧 ×0.7
    （thigh 站间隙预算 4.7 宽松）。返回 {'thigh+': Δ⁺, 'thigh-': Δ⁻}。"""
    y_st = crotch - 3.0
    plus, minus = _derived_radial_field(verts, tris, y_st, y_st - knee_y, 15.0, 0.8, 0.7)
    if len(plus) < 200:
        raise RuntimeError(f"派生 thigh target 增量过少（{len(plus)}）")
    return {"thigh+": plus, "thigh-": minus}


def derived_knee_targets(verts, tris, knee_y):
    """派生 knee± target：以膝站为峰值的径向保形场，替换 MakeHuman 原生
    measure-knee-circ。弃用原生三重根因（2026-09-11「腿部中段往中线扭曲」
    报障，逐顶点数字坐实）：
    ① 原生上缘 y∈[57,66] 是**纯内侧 −x 剪切**（dz≡0，内柱 dx −0.54/w、
      外柱≈0）而径向主体在 y≈45-55——原生膝围基准 34.38 + 响应 6.44/w 使
      常见输入（34~43）权重 >1 常年钳 1.0，剪切边永久生效把大腿中段往全局
      X=0 拖，与 thigh 场旧死区（已另修）叠加成褶/扭曲；
    ② canonical 站错位（原生峰 ~45.5 vs 我们膝站 48.06，thigh 同类教训）；
    ③ 满钳 1.0 可达膝围 40.82 够不着常见输入 43~46。

    派生场：站 y=膝标、half 15 双侧、amp0=1.25（站点 Δg/w≈6.4 对齐原生
    量级 → 闭环权重量级不变）、内侧 ×0.30——膝站间隙预算 2.0 的解析约束
    att ≤ (gap0−floor)/(2·amp0·weightClamp) = (2.0−0.5)/(2×1.25×2.0)，
    满钳 w=2 后间隙恰落 0.5 不互穿；w=1 间隙 1.25、est-default 膝 43 →
    w≈1.35 间隙 ≈0.96，双膝常态分离。小腿代价：原生 knee+ 曾顺带
    +2.8@y36.5，派生 half15 尾 ≈+0.8 → 高膝围档小腿每侧 ~0.28cm 变细
    （VLM 复验核对，可接受差）。返回 {'knee+': Δ⁺, 'knee-': Δ⁻}。"""
    plus, minus = _derived_radial_field(verts, tris, knee_y, 15.0, 15.0, 1.25, 0.30)
    if len(plus) < 200:
        raise RuntimeError(f"派生 knee target 增量过少（{len(plus)}）")
    return {"knee+": plus, "knee-": minus}


# ---------------------------------------------------------------- 主流程

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="MakeHuman CC0 数据 vendor（base.obj+targets → bodymesh 包）")
    ap.add_argument("--src", type=Path, default=_ROOT / "vendor" / "makehuman", help="原始数据目录")
    ap.add_argument("--out", type=Path, default=_ROOT / "webapp" / "frontend" / "public" / "bodymesh", help="产物目录")
    ap.add_argument("--cut-above-waist", type=float, default=15.0, help="精裁切面 = 腰上 N cm（裤顶=腰+13，默认 15 留 2cm 余量；上限受腋窝褶 ~0.75H 约束）")
    ap.add_argument("--female-target", default=DEFAULT_FEMALE, help="女性 macro target 文件名")
    ap.add_argument("--probe", action="store_true", help="只出诊断不写产物")
    ap.add_argument("--dump", action="store_true", help="打印宽度/围度调参表")
    args = ap.parse_args(argv)

    src = args.src
    if not (src / "base.obj").exists():
        print(f"[ERR] {src}/base.obj 不存在——先放置原始数据（scripts 内注释有下载来源）", file=sys.stderr)
        return 2

    report: dict = {}
    probe: dict = {}

    # 1) 解析 + 单位（dm→cm）+ 轴自检；紧凑化到 body 组引用顶点（vmap 供 target 索引换算）
    verts_dm, faces = parse_obj(src / "base.obj")
    used = sorted({v for f in faces for v in f})
    vmap = {old: new for new, old in enumerate(used)}
    verts = [[verts_dm[i][0] * 10.0, verts_dm[i][1] * 10.0, verts_dm[i][2] * 10.0] for i in used]
    sole_raw = min(v[1] for v in verts)
    verts = [[v[0], v[1] - sole_raw, v[2]] for v in verts]  # 脚底 = 0（body 组自身的脚底，不含 joint-ground 等辅助件）
    tris = quads_to_tris([[vmap[v] for v in f] for f in faces])
    report["source"] = {"verts": len(used), "faces": len(faces), "tris": len(tris)}
    # +Z 前自检：脚带（sole..sole+15）z_max 应 ≥ 18cm（脚趾前伸），否则朝向可疑
    feet_zmax = max(v[2] for v in verts if v[1] < 15)
    probe["feetZmax"] = feet_zmax
    if feet_zmax < 18:
        print(f"[ERR] 脚带 z_max={feet_zmax:.1f}cm < 18，+Z 不是前方？检查轴朝向", file=sys.stderr)
        return 3
    height = max(v[1] for v in verts)

    # 2) 女性 macro（烘进基网格；索引换算到紧凑顶点表）
    female_raw = parse_target(src / "targets" / "macrodetails" / args.female_target) if args.female_target else {}
    female = {vmap[i]: d for i, d in female_raw.items() if i in vmap}
    verts = apply_target(verts, female, 1.0)
    report["femaleMacro"] = {"name": args.female_target, "deltas": len(female), "dropped": len(female_raw) - len(female)}

    # 2.5) 腿去外张（A-pose → 并拢站立；phi 按紧凑 body 索引留供 target 增量旋转）
    verts, tris, phi, desplay = desplay_legs(verts, tris)
    probe["desplay"] = desplay
    # 2.6) 腿内收（A-pose 腿间距 gap 5~6.5cm → ≤2cm；共向平移，围度/地标零影响）
    verts, adduct = adduct_thighs(verts, tris, desplay["crotchRaw"])
    probe["adduct"] = adduct
    # 去外张使腿微缩、脚底下探后 re-zero 抬升整体（实测 +3.1cm）——身高/粗裁/
    # 精裁自检基准必须重算，否则精裁面被旧身高的余量带误拒
    height = max(v[1] for v in verts)

    # 3) 粗裁 0.73H + 最大连通域过滤（去臂/手；裁切面低于腋窝褶是前提——实测腋窝 ≈0.75H：
    #    0.74H 仍 3 连通域、0.76H 臂-躯干连通成 1 域无法过滤，0.73H 留 ~5cm 余量）
    rough = cut_below(verts, tris, 0.73 * height)
    rough_v, rough_t = rough[0], rough[1]
    comp_t, comp_sizes = largest_component(rough_t)
    probe["componentsAfterRoughCut"] = comp_sizes
    if len(comp_sizes) != 3:
        print(f"[WARN] 粗裁后连同域 {comp_sizes}（预期 3：躯干+双臂），臂可能未被分离", file=sys.stderr)

    # 4) 地标（在无臂下半身上检测；粗裁把躯干截到 0.66H，腰/裆都在）
    kept0 = sorted({i for t in comp_t for i in t})
    sub_map = {old: new for new, old in enumerate(kept0)}
    sub_v = [rough_v[i] for i in kept0]
    sub_t = [(sub_map[a], sub_map[b], sub_map[c]) for a, b, c in comp_t]
    lm = detect_landmarks(sub_v, sub_t, probe)
    probe["landmarks"] = lm

    # 5) 精裁 腰 + cut（自检 < 腋窝带：用粗裁域数验证过）→ 再过滤 → 封盖 → 紧凑化
    y_cut = lm["waist"] + args.cut_above_waist
    if y_cut > 0.73 * height - 1.0:
        print(f"[ERR] 精裁面 {y_cut:.1f} 超过粗裁面 {0.66 * height:.1f}，臂未被隔离", file=sys.stderr)
        return 4
    cut_v, cut_t, keep_map, crossings = cut_below(verts, tris, y_cut)
    comp_t, comp_sizes = largest_component(cut_t)
    probe["componentsAfterFinalCut"] = comp_sizes
    # 精裁面高于指尖(~0.54H)时小臂+手成对称孤岛是预期（largest_component 丢弃）——
    # 守卫「最大域=躯干」用跨距判别：躯干从脚底 y≈0 贯通到切面，臂碎片只覆盖上部。
    torso_ys = [cut_v[i][1] for t in comp_t for i in t]
    if min(torso_ys) > 5.0 or max(torso_ys) < y_cut - 2.0:
        print(f"[ERR] 最大连通域跨距 [{min(torso_ys):.0f}, {max(torso_ys):.0f}] 不覆盖脚底..切面 {y_cut:.0f}（臂-躯干连通或误选）", file=sys.stderr)
        return 5
    loops = boundary_loops(comp_t)
    if len(loops) != 1:
        print(f"[ERR] 边界环 {len(loops)} 个 ≠ 1", file=sys.stderr)
        return 6
    cap_loops(cut_v, comp_t, loops)
    tight_v, tight_t, remap = compact(cut_v, comp_t)
    ok, edges = check_watertight(tight_t)
    euler = len(tight_v) - edges + len(tight_t)
    probe["mesh"] = {"verts": len(tight_v), "tris": len(tight_t), "edges": edges, "watertight": ok, "euler": euler}
    if not ok or euler != 2:
        print(f"[ERR] 不水密或欧拉 {euler} ≠ 2", file=sys.stderr)
        return 7
    # 臂残留自检：精裁面下 5cm 带全宽不应超过臀宽 1.1 倍
    w_cut = _band_width(tight_v, y_cut - 6, y_cut - 4)
    w_hip = _band_width(tight_v, lm["hip"], lm["hip"] + 2)
    probe["widthNearCut"], probe["widthHip"] = w_cut, w_hip
    if w_cut > w_hip * 1.1:
        print(f"[ERR] 裁切带附近宽 {w_cut:.1f} > 臀宽×1.1={w_hip * 1.1:.1f}，臂残留", file=sys.stderr)
        return 8

    # 6) 地标 → 紧凑网格顶点索引
    #    索引链：原始 0-based → vmap → 紧凑 body 表 → keep_map → cut 表 → remap → 最终表
    compact2tight = {c: remap[n] for c, n in keep_map.items() if n in remap}
    orig2tight = {old: compact2tight[c] for old, c in vmap.items() if c in compact2tight}
    lm_idx = {}
    for name, side in [("sole", None), ("crotch", None), ("waist", None), ("hip", None), ("knee", "+"), ("ankle", "+")]:
        cand = nearest_vertex(tight_v, lm[name], side_axis=0 if side == "+" else None)
        lm_idx[name] = cand
    probe["landmarkIdx"] = lm_idx

    # 7) target 重映射 + 语义自检（knee+ w=1 时膝围增量 > 腰围增量）
    targets_out = []
    dropped_stats = {}
    for station, (incr, decr) in MEASURE_TARGETS.items():
        if station in ("thigh", "knee"):
            continue  # 原生 canonical 站与我们站点错位（thigh 峰 crotch−14 vs 站
            # crotch−3；knee 峰 ~45.5 vs 站 48.06）+ 原生 knee+ 上缘纯内侧 −x 剪切
            # 边（大腿中段往中线拖的向量）→ 7.5 派生径向场替换
        for direction, fname in (("+", incr), ("-", decr)):
            raw = parse_target(src / "targets" / "measure" / fname)
            remapped = {}
            dropped = 0
            for old_i, d in raw.items():
                j = orig2tight.get(old_i)
                if j is None:
                    dropped += 1
                    continue
                # 增量随去外张同旋转（R(p)+w·d = R(p+w·d)；线性缩放与旋转可换序）
                c = vmap.get(old_i)
                f = phi[c] if c is not None else 0.0
                if f:
                    cf, sf = math.cos(f), math.sin(f)
                    d = (d[0] * cf - d[1] * sf, d[0] * sf + d[1] * cf, d[2])
                remapped[j] = (d[0] * 10.0, d[1] * 10.0, d[2] * 10.0)  # dm→cm
            targets_out.append({"name": f"{station}{direction}", "file": fname, "deltas": remapped})
            dropped_stats[f"{station}{direction}"] = dropped
    probe["droppedTargetDeltas"] = dropped_stats

    # 7.5) 派生 thigh±/knee±（原生弃用理由见两函数 docstring）。thigh± 插入
    #      hips± 之后、knee± 追加末尾——名字序 waist±/hips±/thigh±/knee± 与
    #      base.bin 槽序契约（load.ts SLOT_ORDER）保持，运行时按名消费零感知
    derived_th = derived_thigh_targets(tight_v, tight_t, lm["crotch"], lm["knee"])
    pos4 = next(i for i, t in enumerate(targets_out) if t["name"] == "hips-") + 1
    targets_out[pos4:pos4] = [
        {"name": "thigh+", "file": "derived:radial@crotch-3", "deltas": derived_th["thigh+"]},
        {"name": "thigh-", "file": "derived:radial@crotch-3", "deltas": derived_th["thigh-"]},
    ]
    derived_kn = derived_knee_targets(tight_v, tight_t, lm["knee"])
    targets_out.extend([
        {"name": "knee+", "file": "derived:radial@knee-station", "deltas": derived_kn["knee+"]},
        {"name": "knee-", "file": "derived:radial@knee-station", "deltas": derived_kn["knee-"]},
    ])

    # 8) 预标定影响矩阵：每 target 在 w=0/0.5/1 于四站量围度
    station_y = {"waist": lm["waist"], "hips": lm["hip"], "thigh": lm["crotch"] - 3.0, "knee": lm["knee"]}
    calib = {}
    for t in targets_out:
        row = {}
        for st_name, st_per in STATIONS:
            side = "+" if st_per == "leg" else None
            vals = []
            for w in (0.0, 0.5, 1.0):
                pos = apply_target(tight_v, t["deltas"], w) if w else tight_v
                g = girth_at(pos, tight_t, station_y[st_name], leg_side=side)
                vals.append(round(g, 4) if g else None)
            row[st_name] = vals
        calib[t["name"]] = row
    probe["stationY"] = station_y
    probe["calibration"] = calib
    # 语义自检
    kg = calib["knee+"]["knee"]; wg = calib["knee+"]["waist"]
    if kg and wg and (kg[2] - kg[0]) <= (wg[2] - wg[0]):
        print(f"[ERR] knee+ 语义自检失败：膝围增量 {kg[2]-kg[0]:.2f} ≤ 腰围增量 {wg[2]-wg[0]:.2f}（索引基数可疑）", file=sys.stderr)
        return 9
    # thigh 派生场对位自检：峰值带对齐站点 + 站点响应量级 + 对角性 + 下尾铺膝
    # （防将来换数据/调参退回「原生错位」或「半宽截断死区」形态——都是观感事故根因）
    th_deltas = next(t["deltas"] for t in targets_out if t["name"] == "thigh+")
    v_th = apply_target(tight_v, th_deltas, 1.0)
    dg_curve = []
    for y in _frange(lm["crotch"] - 34.0, lm["crotch"] + 2.0, 1.0):
        g0 = girth_at(tight_v, tight_t, y + 0.5, leg_side="+")
        g1 = girth_at(v_th, tight_t, y + 0.5, leg_side="+")
        if g0 and g1:
            dg_curve.append((g1 - g0, y + 0.5))
    if not dg_curve:
        print("[ERR] thigh 派生场 Δgirth 曲线全空", file=sys.stderr)
        return 10
    peak_dg, peak_y = max(dg_curve)
    probe["thighDerived"] = {"peakY": round(peak_y, 2), "peakDg": round(peak_dg, 2),
                             "stationY": station_y["thigh"]}
    if abs(peak_y - station_y["thigh"]) > 3.5:
        print(f"[ERR] thigh+ 峰值带 {peak_y:.1f} 偏离站点 {station_y['thigh']:.1f} 超 3.5cm", file=sys.stderr)
        return 11
    trow = calib["thigh+"]["thigh"]
    st_dg = trow[2] - trow[0]
    if not (3.0 <= st_dg <= 8.0):
        print(f"[ERR] thigh+ 站点响应 {st_dg:.2f} 不在 [3,8]cm 量级带", file=sys.stderr)
        return 12
    for far in ("waist", "knee"):
        frow = calib["thigh+"][far]
        if abs(frow[2] - frow[0]) > 0.3:
            print(f"[ERR] thigh+ 串扰 {far} 站 {frow[2] - frow[0]:.2f} > 0.3（对角性破坏）", file=sys.stderr)
            return 13
    # 下尾铺膝守卫：crotch−15 带 Δg ≥ 2.0（旧对称半宽 18 场在此仅 ~1.08——
    # 膝上死区台阶的数字指纹）+ 膝→峰单调递增（容差 0.4 吸收切片抖动）
    g0m = girth_at(tight_v, tight_t, lm["crotch"] - 15.0, leg_side="+")
    g1m = girth_at(v_th, tight_t, lm["crotch"] - 15.0, leg_side="+")
    dg_mid = (g1m - g0m) if (g0m and g1m) else None
    probe["thighDerived"]["dgAtCrotchMinus15"] = round(dg_mid, 2) if dg_mid is not None else None
    if dg_mid is None or dg_mid < 2.0:
        print(f"[ERR] thigh+ 下尾 crotch−15 Δg {dg_mid} < 2.0（半宽截断死区回归）", file=sys.stderr)
        return 14
    asc = sorted(dg_curve, key=lambda s: s[1])
    pk = max(range(len(asc)), key=lambda i: asc[i][0])
    for a, b in zip(asc[:pk], asc[1:pk + 1]):
        if b[0] < a[0] - 0.4:
            print(f"[ERR] thigh+ 膝→峰非单调：Δg@{a[1]:.1f}={a[0]:.2f} → @{b[1]:.1f}={b[0]:.2f}", file=sys.stderr)
            return 15
    # knee 派生场自检（镜像 thigh 四守卫 + 内侧间隙 floor——两膝贴拢回归防线）
    kn_deltas = next(t["deltas"] for t in targets_out if t["name"] == "knee+")
    v_kn = apply_target(tight_v, kn_deltas, 1.0)
    kn_curve = []
    for y in _frange(lm["knee"] - 18.0, lm["knee"] + 18.0, 1.0):
        g0 = girth_at(tight_v, tight_t, y + 0.5, leg_side="+")
        g1 = girth_at(v_kn, tight_t, y + 0.5, leg_side="+")
        if g0 and g1:
            kn_curve.append((g1 - g0, y + 0.5))
    if not kn_curve:
        print("[ERR] knee 派生场 Δgirth 曲线全空", file=sys.stderr)
        return 16
    kn_peak_dg, kn_peak_y = max(kn_curve)
    kn_gap = None
    kn_loops = _slice_loops(v_kn, tight_t, station_y["knee"])
    kn_cand = [(pts, cx) for pts, cx in kn_loops if cx > 2.0]
    if kn_cand:
        kn_pts, _ = max(kn_cand, key=lambda l: l[1])
        kn_gap = 2.0 * min(p[0] for p in kn_pts)
    probe["kneeDerived"] = {"peakY": round(kn_peak_y, 2), "peakDg": round(kn_peak_dg, 2),
                            "stationY": station_y["knee"],
                            "gapAtStationW1": round(kn_gap, 2) if kn_gap is not None else None}
    if abs(kn_peak_y - station_y["knee"]) > 3.5:
        print(f"[ERR] knee+ 峰值带 {kn_peak_y:.1f} 偏离站点 {station_y['knee']:.1f} 超 3.5cm", file=sys.stderr)
        return 17
    krow = calib["knee+"]["knee"]
    kn_st_dg = krow[2] - krow[0]
    if not (4.0 <= kn_st_dg <= 9.0):
        print(f"[ERR] knee+ 站点响应 {kn_st_dg:.2f} 不在 [4,9]cm 量级带", file=sys.stderr)
        return 18
    for far in ("waist", "hips", "thigh"):
        frow = calib["knee+"][far]
        if abs(frow[2] - frow[0]) > 0.3:
            print(f"[ERR] knee+ 串扰 {far} 站 {frow[2] - frow[0]:.2f} > 0.3（对角性破坏）", file=sys.stderr)
            return 19
    if kn_gap is None or kn_gap < 0.5:
        print(f"[ERR] knee+ w=1 膝站内侧 gap {kn_gap} < 0.5（两膝贴拢回归）", file=sys.stderr)
        return 20

    if args.dump:
        _dump_tables(tight_v, tight_t, lm)

    report.update(probe)
    print(json.dumps(report, ensure_ascii=False, indent=1, default=str))

    if args.probe:
        print("[probe] 不写产物")
        return 0

    # 9) 产出
    args.out.mkdir(parents=True, exist_ok=True)
    bin_path = args.out / "base.bin"
    with open(bin_path, "wb") as f:
        f.write(struct.pack("<III", len(tight_v), len(tight_t), len(targets_out)))
        for v in tight_v:
            f.write(struct.pack("<3f", *v))
        for t in tight_t:
            f.write(struct.pack("<3I", *t))
        for t in targets_out:
            idx = sorted(t["deltas"])
            f.write(struct.pack("<I", len(idx)))
            f.write(struct.pack(f"<{len(idx)}I", *idx))
            flat = [c for i in idx for c in t["deltas"][i]]
            f.write(struct.pack(f"<{len(flat)}f", *flat))

    meta = {
        "schema": 1,
        "units": "cm",
        "frame": {"yAxis": "up", "origin": "sole-center", "front": "+z"},
        # base.bin 内容指纹：load.ts 以 ?v=<sha8> 拉二进制——重跑 vendor 后
        # URL 变化即击穿浏览器缓存（2026-09-12「改了没变化」事故：base.bin
        # 更新后旧缓存照常命中，用户看到的一直是旧人台）
        "baseSha256": hashlib.sha256(bin_path.read_bytes()).hexdigest()[:8],
        "vertexCount": len(tight_v),
        "triangleCount": len(tight_t),
        "targets": [{"name": t["name"], "file": t["file"], "count": len(t["deltas"])} for t in targets_out],
        "landmarks": lm_idx,
        "landmarkHeights": {k: round(v, 3) for k, v in lm.items() if k != "height"},
        "cut": {"aboveWaistCm": args.cut_above_waist, "planeY": round(y_cut, 2)},
        "stations": [{"name": s, "per": p, "y": round(station_y[s], 3)} for s, p in STATIONS],
        "calibration": calib,
        "provenance": {
            "repo": "makehumancommunity/makehuman",
            "tag": "v1.3.0",
            "commit": "1f508f60",
            "license": "CC0-1.0 (bundled assets)",
            "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted(src.rglob("*")) if p.is_file()},
        },
    }
    (args.out / "targets.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    lic_src = src / "LICENSE.ASSETS.md"
    if lic_src.exists():
        shutil.copy(lic_src, args.out / "LICENSE.ASSETS.md")
    print(f"[OK] {bin_path} ({bin_path.stat().st_size} bytes) + targets.json")
    return 0


def _sub(verts, keep):
    return [verts[i] for i in sorted(keep)]


def _band_width(verts, y0, y1):
    xs = [v[0] for v in verts if y0 <= v[1] < y1]
    return (max(xs) - min(xs)) if xs else 0.0


def _dump_tables(verts, tris, lm):
    print("--- width vs y（1cm 步）---")
    for y in _frange(0, max(v[1] for v in verts), 1.0):
        w = _band_width(verts, y, y + 1)
        r = band_stat(verts, y, y + 1, 0, max, side="+")
        print(f"y={y:6.1f} width={w:6.2f} outerR={r if r is not None else float('nan'):6.2f}")
    print("--- girth vs y（2cm 步）---")
    for y in _frange(0, max(v[1] for v in verts), 2.0):
        g = girth_at(verts, tris, y)
        gl = girth_at(verts, tris, y, leg_side="+")
        print(f"y={y:6.1f} girth={g if g else float('nan'):7.2f} rightLeg={gl if gl else float('nan'):7.2f}")
    print(f"landmarks={lm}")


if __name__ == "__main__":
    raise SystemExit(main())
