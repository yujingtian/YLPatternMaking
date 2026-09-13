#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MakeHuman CC0 数据 vendor（切割+站直姿势链，2026-09-13 定型）：base.obj →
下半身站直人台 → webapp/frontend/public/bodymesh/{base.bin, targets.json}。

口径（用户 2026-09-13 拍板）：**站直姿势 = 官方 rigs 数据 + clean-room LBS**
（default.mhskel 骨架 + default_weights.mhw 蒙皮权重，均 CC0 内嵌 license，
只借数据零 AGPL 代码）。早间「零姿势修改」口径退役——其成立前提是自研
姿势手术撕裂臀线（窗口化旋转/平移无法规避腿-臀交界耦合，2026-09-12 四轮
报障坐实）；官方蒙皮权重是连续影响场，臀带由 upperleg01 权重自然携带，
交界带光滑（探针实测：w=1 刚性偏差 0.006cm、混合带围长损失 ≤1.7cm、
外缘包络零台阶）。逐关节角度：大腿绕髋 θ_t（髋→膝竖直化）、小腿绕移动后
膝补 θ_k（净角 θ_c = 髋→踝竖直化）、脚绕移动后踝反补 −θ_c（脚底回水平）
——髋/膝/踝三点落铅垂线。`--pose apose` 可退回 A-pose 原样切割（复现口径）。
形态调节仍由官方 12 个 measure target 在运行时叠加（原生场固有缺陷如
thigh 膝上死区原样呈现）。

流程：解析 base.obj（只取 g body、dm→cm、+Z 前自检、脚底=0）→
女性 macro 烘底（DEFAULT_FEMALE="" 恒等占位，保 --female-target 复现
口径）→ **站直姿势（官方 rigs 蒙皮 LBS，逐关节角度；切割前最后一个
全网格操作）** → 粗裁 0.73H + 最大连通域过滤（去臂/手；裁切面须低于
腋窝褶 ~0.75H，否则臂-躯干连通无法过滤）→ 地标检测（姿势无关：裆 =
2环→1环拓扑合并、臀/腰 = 围度切片极值、膝/踝 = 右腿围度局部极小、
小腿肚 = 右腿围度局部极大）→ 精裁 腰+15cm → 封盖 → 紧凑化 →
水密/欧拉自检 → 官方 12 场按裁切后索引重映射（.target 索引即 base.obj
原始顶点号，经 vmap→keep_map→remap 三级映射到紧凑切割网格；增量
dm→cm 后按逐顶点累积角随帧旋转——官方场从绑定帧跟到站直帧）。

base.bin 布局（little-endian）：
    <III> V F T；V×<3f> 顶点 cm（Y-up、脚底=0、+Z 前）；
    F×<3I> 三角 0-based；每 target：<I> n、n×<I> idx、3n×<f> d（cm）。
targets.json：schema 2（无标定矩阵——闭环链已退役）：目标名/文件、
地标顶点索引与高度、站点（body/leg 口径）、裁切面、姿势（名/角度/数据源）、
内容指纹、溯源。

数据来源（下载后不要改动，PROVENANCE.md 记哈希）：
    https://github.com/makehumancommunity/makehuman tag v1.3.0
    base.obj ≈ 1.7MB；targets/measure/*.target 文本 `idx dx dy dz`（dm）；
    rigs/{default.mhskel,default_weights.mhw} JSON（data/rigs/，v1.3.0）。
"""
import argparse
import hashlib
import json
import math
import shutil
import struct
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# 站点定义：名 → (per, 高度来源)。thigh 取裆下 3cm（对齐引擎缺省口径）；
# calf = 小腿肚（右腿围度局部极大）、ankle = 踝（右腿围度局部极小）。
STATIONS = [
    ("waist", "body"),
    ("hips", "body"),
    ("thigh", "leg"),
    ("knee", "leg"),
    ("calf", "leg"),
    ("ankle", "leg"),
]
MEASURE_TARGETS = {
    "waist": ("measure-waist-circ-incr.target", "measure-waist-circ-decr.target"),
    "hips": ("measure-hips-circ-incr.target", "measure-hips-circ-decr.target"),
    "thigh": ("measure-thigh-circ-incr.target", "measure-thigh-circ-decr.target"),
    "knee": ("measure-knee-circ-incr.target", "measure-knee-circ-decr.target"),
    "calf": ("measure-calf-circ-incr.target", "measure-calf-circ-decr.target"),
    "ankle": ("measure-ankle-circ-incr.target", "measure-ankle-circ-decr.target"),
}
DEFAULT_FEMALE = ""  # base.obj 本身 = universal female young average（实测 universal-female-* 为 0 增量 identity），无需女性 macro

EPS = 1e-9


# ---------------------------------------------------------------- 站直姿势（官方 rigs 蒙皮 clean-room LBS）

_LEG_UPPER = ("upperleg01", "upperleg02")   # 大腿两段（髋枢轴，线性角 θ_t）
_LEG_LOWER = ("lowerleg01", "lowerleg02")   # 小腿两段（膝上补角，净线性角 θ_c）
_FOOT_PREFIX = "foot"                       # 脚 + toe*（踝反补 −θ_c，线性部分 = I）


def load_rigs(src: Path):
    """返回 (joints, weights)。mhskel joints：关节名→顶点索引组（引用 base.obj
    **全量**顶点表——关节组顶点在 helper 几何组，不在 g body 组内，绝不能走
    vmap 压缩表）；mhw weights：骨名→[[顶点索引, 权重]...]（同样全量索引，
    约四成项挂 helper 顶点，消费侧按 vmap 过滤）。"""
    skel = json.loads((src / "rigs" / "default.mhskel").read_text(encoding="utf-8"))
    weights = json.loads((src / "rigs" / "default_weights.mhw").read_text(encoding="utf-8"))["weights"]
    return skel["joints"], weights


def pose_standing(verts, verts_dm, vmap, sole_raw, joints, weights, probe):
    """A-pose → 站直（LBS，逐关节角度）。返回 (posed_verts, pose_angles,
    thetas_deg, checks)。pose_angles：{base.obj 原始索引: 增量应旋转角} =
    Σ w·(该骨线性角)——官方 measure 场增量随帧旋转用（方向旋转，平移无关）。

    角度（每侧独立，符号由 atan2 自动定——探针同款公式，右腿为负/左腿为正）：
      θ_t  = atan2(knee.x−hip.x,  knee.y−hip.y)  + π  大腿绕髋 → 大腿轴竖直
      θ_ca = atan2(ank.x−knee.x,  ank.y−knee.y)  + π  小腿总转角（膝→踝竖直化）
      θ_k  = θ_ca − θ_t                               小腿绕移动后膝的补角
    臀无骨骼参与：臀带皮肤由 upperleg01 权重部分携带（「臀部控制着一部分
    大腿」的蒙皮实现）。LBS 为旋转与恒等的凸组合，det 恒正、法线不翻。"""
    def joint(name):
        pts = [[verts_dm[i][0] * 10.0, verts_dm[i][1] * 10.0 - sole_raw, verts_dm[i][2] * 10.0]
               for i in joints[name]]
        return [sum(p[k] for p in pts) / len(pts) for k in range(3)]

    def rot_z(p, piv, ang):
        c, s = math.cos(ang), math.sin(ang)
        dx, dy = p[0] - piv[0], p[1] - piv[1]
        return [piv[0] + dx * c - dy * s, piv[1] + dx * s + dy * c, p[2]]

    bone_xform: dict[str, tuple] = {}   # 骨名 -> (变换函数, 线性角)
    thetas: dict[str, dict] = {}
    checks: dict[str, dict] = {}

    def _norm(a):
        # atan2+π 落在 [0,2π)；L 侧外张使角度绕到 ~353°（≡−6.5°）。整周旋转对
        # **位置**无损（周期性），但当**线性角**乘权重 w 后 353°×w ≠ −6.5°×w
        # ——部分权重顶点（髋带 w≈0.5 → ~177°）的 measure 增量被翻转半个平面
        # （hips+ 单侧内凹，2026-09-13 实发穿透全部守卫）。必须归一后再用。
        return (a + math.pi) % (2.0 * math.pi) - math.pi

    for S in "LR":
        hip = joint(f"upperleg01.{S}____head")
        knee = joint(f"lowerleg01.{S}____head")
        ank = joint(f"foot.{S}____head")
        t_t = _norm(math.atan2(knee[0] - hip[0], knee[1] - hip[1]) + math.pi)
        t_ca = _norm(math.atan2(ank[0] - knee[0], ank[1] - knee[1]) + math.pi)
        t_k = _norm(t_ca - t_t)
        knee_m = rot_z(knee, hip, t_t)
        ank_m = rot_z(rot_z(ank, hip, t_t), knee_m, t_k)   # 移动后踝（全链枢轴）

        def m_upper(p, hip=hip, t=t_t):
            return rot_z(p, hip, t)

        def m_lower(p, hip=hip, knee_m=knee_m, t1=t_t, t2=t_k):
            return rot_z(rot_z(p, hip, t1), knee_m, t2)

        def m_foot(p, hip=hip, knee_m=knee_m, ank_m=ank_m, t1=t_t, t2=t_k, tc=t_ca):
            return rot_z(m_lower(p, hip, knee_m, t1, t2), ank_m, -tc)

        for nm in _LEG_UPPER:
            bone_xform[f"{nm}.{S}"] = (m_upper, t_t)
        for nm in _LEG_LOWER:
            bone_xform[f"{nm}.{S}"] = (m_lower, t_ca)
        for b in [f"{_FOOT_PREFIX}.{S}"] + [n for n in weights
                                            if n.startswith("toe") and n.endswith(f".{S}")]:
            bone_xform[b] = (m_foot, 0.0)
        thetas[S] = {"t": t_t, "k": t_k, "ca": t_ca}
        # 自检值：移动后膝/踝相对髋的 x 偏差（三点铅垂）
        checks[S] = {"kneeDx": m_upper(knee)[0] - hip[0], "ankleDx": m_foot(ank)[0] - hip[0]}

    # 逐顶点 LBS：p' = p + Σ w·(M_b(p) − p)（权重索引过 vmap，helper 项丢弃）
    w_by_new: dict[int, list] = {}
    pose_angles: dict[int, float] = {}
    dropped = 0
    for bone, (fn, lin) in bone_xform.items():
        for entry in weights.get(bone, []):
            i, w = int(entry[0]), float(entry[1])
            j = vmap.get(i)
            if j is None:
                dropped += 1
                continue
            w_by_new.setdefault(j, []).append((w, fn))
            pose_angles[i] = pose_angles.get(i, 0.0) + w * lin

    out = [list(v) for v in verts]
    for j, pairs in w_by_new.items():
        p = verts[j]
        q = list(p)
        for w, fn in pairs:
            m = fn(p)
            q = [q[k] + w * (m[k] - p[k]) for k in range(3)]
        out[j] = q

    # 脚底重归一（姿势后 min y → 0，保帧契约）。脚链踝上反补后脚底平面回水平
    # （线性部分恰为 I）；绑定脚底本有 0~0.4cm 自然坡（逐点分布姿势前后一致），
    # 平整度用**左右脚最低点差**把关——脚底倾斜才会拉开，自然坡不会。
    sole2 = min(v[1] for v in out)
    out = [[v[0], v[1] - sole2, v[2]] for v in out]
    feet = [v for v in out if v[1] < 8.0]
    min_l = min(v[1] for v in feet if v[0] < 0.0)
    min_r = min(v[1] for v in feet if v[0] > 0.0)

    def _deg(a):  # 归一到 (−180,180]（atan2+π 天然落在 [0,360)）
        return round((math.degrees(a) + 180.0) % 360.0 - 180.0, 3)
    thetas_deg = {S: {k: _deg(v) for k, v in d.items()} for S, d in thetas.items()}
    checks["soleLevel"] = round(abs(min_l - min_r), 3) if feet else None
    checks["soleShift"] = round(sole2, 3)
    probe["pose"] = {"thetasDeg": thetas_deg, "helperWeightDropped": dropped, "checks": checks}
    return out, pose_angles, thetas_deg, checks



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
    """pos = base + w·Δ（返回新列表；增量已是 cm）。"""
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


def _band_width(verts, y0, y1):
    xs = [v[0] for v in verts if y0 <= v[1] < y1]
    return (max(xs) - min(xs)) if xs else 0.0


# ---------------------------------------------------------------- 地标与围度

def detect_landmarks(verts, tris, probe: dict):
    """启发式地标（返回高度 dict；顶点索引由 nearest_vertex 补）。
    裆=腿分离带向上首个 2环→1环 拓扑合并点；腰/臀/膝/小腿肚/踝全部走切片
    围度（顶点带 x 极值有 ~2cm 顶点行锯齿伪影，弃用）。全部姿势无关——
    A-pose 自然腿距与并拢腿距下同口径成立。"""
    sole = min(v[1] for v in verts)
    height = max(v[1] for v in verts) - sole
    probe["sole"] = sole
    probe["height"] = height

    step = 1.0

    # 裆：腿分离→并环的拓扑合并点（2 环→1 环、上方持续单环）= 会阴。
    # 环数合并不受腿距/贴合深度影响（旧「首个 |x|<0.6 带」口径在贴合腿
    # 误触发，2026-09-12 弃用）。自 0.40H 向上扫、上界放宽到 mesh 顶。
    y = sole + 0.40 * height
    crotch = None
    run2 = 0
    while y < sole + height - step:
        n_loops = len(_slice_loops(verts, tris, y + 0.5))
        if n_loops >= 2:
            run2 += 1
        elif n_loops == 1 and run2 >= 3 and all(
                len(_slice_loops(verts, tris, y + 0.5 + k)) == 1 for k in (1.0, 2.0, 3.0)):
            crotch = y
            break
        y += step
    if crotch is None:
        raise RuntimeError("裆地标检测失败（自 0.40H 向上无 2环→1环 合并带）")

    # 臀：[crotch+6, crotch+14] 切片围度最大带（标准臀围=最丰满处周长；搜索带
    # 必须在裆叉喇叭带之上——裆下切片跨双腿围度求和会虚高）。
    # 腰：[crotch+12, crotch+28] 切片围度平滑最小（自然腰=臀上最细处）。
    ys = _frange(crotch + 6, crotch + 14, step)
    gs = [girth_at(verts, tris, y + 0.5) or 0.0 for y in ys]
    hip = ys[_local_extremum(gs, "max")]
    ys = _frange(crotch + 12, crotch + 28, step)
    gs = [girth_at(verts, tris, y + 0.5) or 0.0 for y in ys]
    waist = ys[_local_extremum(gs, "min")]

    # 膝：右腿围度在 [crotch-35, crotch-15] 的局部极小
    knee = _girth_extremum(verts, tris, crotch - 35.0, crotch - 15.0, "min")
    # 踝：右腿围度在 [sole+2, knee-8] 的局部极小
    ankle = _girth_extremum(verts, tris, sole + 2.0, knee - 8.0, "min")
    # 小腿肚：右腿围度在 [ankle+2, knee-2] 的局部极大（解剖小腿最丰满处；
    # 膝极小与踝极小之间的唯一峰，带端各留 2cm 防蹭到极小平台）
    calf = _girth_extremum(verts, tris, ankle + 2.0, knee - 2.0, "max")
    return {"sole": sole, "crotch": crotch, "hip": hip, "waist": waist, "knee": knee, "calf": calf, "ankle": ankle, "height": height}


def _girth_extremum(verts, tris, y0, y1, mode):
    """右腿切片围度在 [y0,y1) 的局部极小/极大高度（1cm 步、3 点平滑）。"""
    import statistics
    ys = _frange(y0, y1, 1.0)
    gs = []
    for y in ys:
        g = girth_at(verts, tris, y + 0.5, leg_side="+")
        gs.append(g if g else 0.0)
    sm = [statistics.fmean(gs[max(0, i - 1): i + 2]) for i in range(len(gs))]
    pick = min if mode == "min" else max
    best_i = pick(range(len(sm)), key=lambda i: sm[i])
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
    """平面切片闭环：返回 [(环点列, 质心 x)]（交点按无序边坐标哈希共享、
    顶点恰在平面上计入「下」）。"""
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


# ---------------------------------------------------------------- 主流程

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="MakeHuman CC0 数据 vendor（切割+站直姿势链：base.obj+rigs+targets → bodymesh 包）")
    ap.add_argument("--src", type=Path, default=_ROOT / "vendor" / "makehuman", help="原始数据目录")
    ap.add_argument("--out", type=Path, default=_ROOT / "webapp" / "frontend" / "public" / "bodymesh", help="产物目录")
    ap.add_argument("--cut-above-waist", type=float, default=15.0, help="精裁切面 = 腰上 N cm（裤顶=腰+13，默认 15 留 2cm 余量；上限受腋窝褶 ~0.75H 约束）")
    ap.add_argument("--female-target", default=DEFAULT_FEMALE, help="女性 macro target 文件名（默认恒等）")
    ap.add_argument("--pose", choices=("standing", "apose"), default="standing",
                    help="standing=官方 rigs 蒙皮 LBS 站直（默认）；apose=A-pose 原样（复现口径）")
    ap.add_argument("--probe", action="store_true", help="只出诊断不写产物")
    args = ap.parse_args(argv)

    src = args.src
    if not (src / "base.obj").exists():
        print(f"[ERR] {src}/base.obj 不存在——先放置原始数据（scripts 内注释有下载来源）", file=sys.stderr)
        return 2

    report: dict = {}
    probe: dict = {}

    # 1) 解析：g body、dm→cm、脚底=0、+Z 前自检
    verts_dm, faces = parse_obj(src / "base.obj")
    used = sorted({v for f in faces for v in f})
    vmap = {old: new for new, old in enumerate(used)}
    verts = [[verts_dm[i][0] * 10.0, verts_dm[i][1] * 10.0, verts_dm[i][2] * 10.0] for i in used]
    sole_raw = min(v[1] for v in verts)
    verts = [[v[0], v[1] - sole_raw, v[2]] for v in verts]
    tris = quads_to_tris([[vmap[v] for v in f] for f in faces])
    report["source"] = {"verts": len(used), "faces": len(faces), "tris": len(tris)}
    feet_zmax = max(v[2] for v in verts if v[1] < 15)
    probe["feetZmax"] = feet_zmax
    if feet_zmax < 18:
        print(f"[ERR] 脚带 z_max={feet_zmax:.1f}cm < 18，+Z 不是前方？检查轴朝向", file=sys.stderr)
        return 3
    height = max(v[1] for v in verts)

    # 2) 女性 macro 烘底（默认恒等；保 --female-target 复现口径）
    female_raw = parse_target(src / "targets" / "macrodetails" / args.female_target) if args.female_target else {}
    female = {vmap[i]: d for i, d in female_raw.items() if i in vmap}
    verts = apply_target(verts, female, 1.0)
    report["femaleMacro"] = {"name": args.female_target, "deltas": len(female), "dropped": len(female_raw) - len(female)}

    # 2.5) 站直姿势（官方 rigs 蒙皮 clean-room LBS，逐关节角度；--pose apose 跳过）
    pose_angles: dict[int, float] = {}
    pose_meta: dict = {"name": args.pose}
    if args.pose == "standing":
        try:
            joints, rig_weights = load_rigs(src)
        except FileNotFoundError as e:
            print(f"[ERR] --pose standing 需要 rigs 数据：{e.filename}（下载来源见脚本头注）", file=sys.stderr)
            return 11
        verts, pose_angles, thetas_deg, pose_checks = pose_standing(
            verts, verts_dm, vmap, sole_raw, joints, rig_weights, probe)
        pose_meta.update({"thetasDeg": thetas_deg,
                          "rigFiles": ["rigs/default.mhskel", "rigs/default_weights.mhw"]})
        for S in "LR":
            if abs(pose_checks[S]["kneeDx"]) > 0.5 or abs(pose_checks[S]["ankleDx"]) > 0.5:
                print(f"[ERR] 站直自检失败：{S} 膝/踝 x 偏差 {pose_checks[S]} > 0.5cm（三点不铅垂）", file=sys.stderr)
                return 12
            if not (4.0 <= abs(thetas_deg[S]["t"]) <= 12.0 and 4.0 <= abs(thetas_deg[S]["ca"]) <= 12.0):
                print(f"[ERR] 站直自检失败：θ({S})={thetas_deg[S]} 超出 [4°,12°] 域", file=sys.stderr)
                return 12
        if pose_checks.get("soleLevel") is None or pose_checks["soleLevel"] > 0.1:
            print(f"[ERR] 站直自检失败：左右脚最低点差 {pose_checks.get('soleLevel')}cm > 0.1（脚底倾斜）", file=sys.stderr)
            return 12
        # 线性角域守卫：pose_angles = Σw·θ 必为小幅角（|a| ≤ 2×max|θ_c| 即可；
        # atan2+π 未归一的 ~353° 值乘权重会翻转增量方向——hips+ 单侧内凹实发）
        a_max = max((abs(v) for v in pose_angles.values()), default=0.0)
        if a_max > math.radians(25.0):
            print(f"[ERR] 站直自检失败：pose_angles 最大 |a|={math.degrees(a_max):.1f}° > 25°（角度未归一？）", file=sys.stderr)
            return 13

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

    # 5) 精裁 腰 + cut（自检 < 粗裁面，留 0.5cm 余量——站直姿势把腰站抬 ~1cm
    #    （裆下切向拖拽 + 脚底重归一，1cm 检测网格量化），原 1.0 防御余量不再
    #    合身；功能约束 = 精裁面严格低于粗裁面，臂隔离即成立）→ 再过滤 → 封盖 → 紧凑化
    y_cut = lm["waist"] + args.cut_above_waist
    if y_cut > 0.73 * height - 0.5:
        print(f"[ERR] 精裁面 {y_cut:.1f} 超过粗裁面 {0.73 * height:.1f}，臂未被隔离", file=sys.stderr)
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

    # 6) 地标 → 紧凑网格顶点索引（索引链：原始 0-based → vmap → keep_map → remap）
    compact2tight = {c: remap[n] for c, n in keep_map.items() if n in remap}
    orig2tight = {old: tight for old, c in vmap.items() if (tight := compact2tight.get(c)) is not None}
    lm_idx = {}
    for name, side in [("sole", None), ("crotch", None), ("waist", None), ("hip", None), ("knee", "+"), ("calf", "+"), ("ankle", "+")]:
        lm_idx[name] = nearest_vertex(tight_v, lm[name], side_axis=0 if side == "+" else None)
    probe["landmarkIdx"] = lm_idx

    # 7) 官方 12 场全部重映射（.target 索引 = base.obj 原始顶点号 → 紧凑切割网格；
    #    增量 dm→cm ×10 后按逐顶点累积角 pose_angles 随帧旋转（upperleg*=θ_t、
    #    lowerleg*=θ_c、脚骨 0）——官方场从绑定帧跟到站直帧。被裁掉顶点丢弃并计数）
    targets_out = []
    dropped_stats = {}
    for station, (incr, decr) in MEASURE_TARGETS.items():
        for direction, fname in (("+", incr), ("-", decr)):
            raw = parse_target(src / "targets" / "measure" / fname)
            remapped = {}
            dropped = 0
            for old_i, d in raw.items():
                j = orig2tight.get(old_i)
                if j is None:
                    dropped += 1
                    continue
                dx, dy, dz = d[0] * 10.0, d[1] * 10.0, d[2] * 10.0
                a = pose_angles.get(old_i, 0.0)
                if a:
                    c, s = math.cos(a), math.sin(a)
                    dx, dy = dx * c - dy * s, dx * s + dy * c
                remapped[j] = (dx, dy, dz)
            targets_out.append({"name": f"{station}{direction}", "file": fname, "deltas": remapped})
            dropped_stats[f"{station}{direction}"] = dropped
    probe["droppedTargetDeltas"] = dropped_stats

    # 8) 站点 + 语义自检：官方场在自家站点方向响应成立（原生场带作者化窗口，
    #    只锁方向与量级带——原生缺陷如 thigh 膝上死区属原样呈现，不做形态断言）
    station_y = {"waist": lm["waist"], "hips": lm["hip"], "thigh": lm["crotch"] - 3.0,
                 "knee": lm["knee"], "calf": lm["calf"], "ankle": lm["ankle"]}
    probe["stationY"] = station_y
    leg_st = {s for s, p in STATIONS if p == "leg"}
    station_g0 = {s: girth_at(tight_v, tight_t, station_y[s],
                              leg_side=("+" if p == "leg" else None))
                  for s, p in STATIONS}
    probe["stationGirthW0"] = {k: round(v, 2) if v else None for k, v in station_g0.items()}
    by_name = {t["name"]: t["deltas"] for t in targets_out}
    resp = {}
    for station, _ in STATIONS:
        for name in (f"{station}+", f"{station}-"):
            v1 = apply_target(tight_v, by_name[name], 1.0)
            g1 = girth_at(v1, tight_t, station_y[station],
                          leg_side=("+" if station in leg_st else None))
            resp[name] = round((g1 or 0.0) - (station_g0[station] or 0.0), 2)
    probe["targetResponseW1"] = resp
    if resp["waist+"] < 2.0 or resp["waist-"] > -2.0:
        print(f"[ERR] waist± 官方场站点方向响应异常 {resp}（重映射错位？）", file=sys.stderr)
        return 9
    if resp["hips+"] <= 0.0 or resp["hips-"] >= 0.0:
        print(f"[ERR] hips± 官方场站点方向响应异常 {resp}（重映射错位？）", file=sys.stderr)
        return 10

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
        "schema": 2,
        "units": "cm",
        "frame": {"yAxis": "up", "origin": "sole-center", "front": "+z"},
        # base.bin 内容指纹：产物版本标记（vendor 重跑后指纹必变，可作缓存击穿键）
        "baseSha256": hashlib.sha256(bin_path.read_bytes()).hexdigest()[:8],
        "vertexCount": len(tight_v),
        "triangleCount": len(tight_t),
        "targets": [{"name": t["name"], "file": t["file"], "count": len(t["deltas"])} for t in targets_out],
        "landmarks": lm_idx,
        "landmarkHeights": {k: round(v, 3) for k, v in lm.items() if k != "height"},
        "cut": {"aboveWaistCm": args.cut_above_waist, "planeY": round(y_cut, 2)},
        "pose": pose_meta,
        "stations": [{"name": s, "per": p, "y": round(station_y[s], 3)} for s, p in STATIONS],
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


if __name__ == "__main__":
    sys.exit(main())
