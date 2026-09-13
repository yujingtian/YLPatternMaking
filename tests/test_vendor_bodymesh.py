# -*- coding: utf-8 -*-
"""MakeHuman vendor 产物金标（webapp/frontend/public/bodymesh/{base.bin, targets.json}）。

数据缺席整文件 skip（先例 test_reverse_gold_5015.py）。锚值 = 2026-09-13 默认参数
vendor（切割+站直姿势链）运行的手工核读——**站直姿势**：官方 rigs 数据
（default.mhskel 骨架 + default_weights.mhw 蒙皮权重，CC0）clean-room LBS 逐关节
角度（大腿绕髋 θ_t≈6.52°、小腿绕移动后膝补 θ_k≈2.79°、脚绕移动后踝反补
−θ_c≈−9.31°——髋/膝/踝三点铅垂；臀带由 upperleg01 权重自然携带）。早前
「零姿势修改」口径退役——自研姿势手术撕裂臀线，官方连续权重场无此问题
（演进史 .doc/决策日志.md §十一）；形态调节 = 官方 12 个 measure target
（腰/臀/大腿/膝/小腿/踝）+ 身高 macro ±（共 14 场）运行时叠加（原生场固有
缺陷原样呈现）。身高预设（2026-09-13）= 按切割前全身实测 ΔH 换算权重
（meta.height，测量驱动、不假设官方 macro 混合约定）：

    地标高度（cm，脚底=0、+Z 前）：crotch 78.6 / hip 84.6 / waist 105.6 /
        knee 48.1 / calf 34.0（小腿肚=右腿围度局部极大）/ ankle 12.5
        （较 A-pose 链整体 +1.0：站直裆下切向拖拽 + 脚底重归一抬升站高，
         1cm 检测网格量化后取整）
    w=0 基网格站点围度（cm）：waist 69.03 / hips 97.63 / thigh 右腿 53.67 /
        knee 右腿 34.43 / calf 右腿 35.06 / ankle 右腿 20.24
        （站直解剖归正：hips −1.05 大腿内倾回收，膝/小腿/踝斜切转正各微降）
    w=1 官方场站点响应（cm）：waist+ +10.55 / waist− −10.15 / hips+ +19.35 /
        hips− −9.65 / thigh+ +5.95 / thigh− −3.92 / knee+ +6.48 / knee− −3.69 /
        calf+ +10.05 / calf− −9.99 / ankle+ +5.93 / ankle− −5.93
        （官方场在自家站方向响应全部成立——重映射正确性守卫；量级断言只锁方向
         与下限不锁精确值：thigh 峰值带 crotch−14 与站点 crotch−3 天然错位。
         hips+ 19.35 与 A-pose 链 19.36 一致——随帧旋转的线性角必须取归一角
         〔−6.5° 而非 atan2+π 原值 353.5°：整周旋转对位置无损，但乘部分权重 w
         后 353°×w 会把单侧增量翻转半个平面，hips+ 单侧内凹实发；vendor 侧
         exit 13 域守卫 + 本文件镜像对称守卫双保险〕）
    站直腿轴（站直守卫）：右腿环质心 cx@crotch−10 = 10.05 → cx@crotch−30 =
        10.80 → cx@crotch−45 = 11.66（髋/膝/踝铅垂的腿自然剖面；A-pose 回归
        时 crotch−10→−45 差爆到 ~5.9，过度内收/并腿则反向塌缩）
    身高场实测（meta.height）：base 167.36 / plusCmAtW1 +72.02 /
        minusCmAtW1 −36.69（切割前全身网格 w=1，线性偏差 0.0、脚底漂移 ≤0.23；
        官方 macro 域极宽——全身 ±1 跨 130.7~239.4cm，预设只用小权重区）。
        切割网格上 w=1 顶降：height− −30.93 / height+ +58.88（全身 ΔH 的可见
        份额），脚底 min y ≥ −0.23。预设权重换算：155→−0.337 / 160→−0.201 /
        165→−0.064 / 170→+0.037（全部 ∈ [−1,1]，回算身高逐档精确）
    合成顶点场增量（2026-09-13）：切缝交点 152 + 封盖质心 1 按切缝边两原始
        端点线性插值/环均值补增量（height± 覆盖全部 4311 顶点）——否则身高场
        把交点下方顶点整体压下/拉起而切缝环原地不动，顶缘撕出数 cm 拉伸带
    网格：V 4311 / F 8618 / E 12927，水密（每边恰 2 面），欧拉 = 2
        （较 A-pose 链 +35/+70：站直抬腰 ~1cm 使精裁面多切一层三角形，预期内）

守卫口径：布局契约（尾部残留防爆）、拓扑跨 morph 恒定（裁切后顶点索引冻结）、
朝向（脚趾 +Z）、地标高度带（防地标检测回归）、围度锚带（防站点漂移）、
官方场方向响应（防重映射错位）、官方场增量镜像对称（防随帧旋转线性角未归一
的单侧翻转）、站直守卫（腿轴竖直/膝铅垂/脚平底/左右镜像，双向防 A-pose 与
过度内收回归）、pose meta（姿势名/角度镜相对于）、meta.height（预设换算
基准：基高域/ΔH 双向/四档可达互逆）、身高场方向（顶降 + 脚底锚地）。"""
import struct
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_BIN = _ROOT / "webapp" / "frontend" / "public" / "bodymesh" / "base.bin"
_META = _ROOT / "webapp" / "frontend" / "public" / "bodymesh" / "targets.json"

# 手工演算锚值（见模块 docstring；容差吸收 girth 切片步进的舍入）
ANCHOR_LANDMARKS = {"crotch": 78.6, "hip": 84.6, "waist": 105.6, "knee": 48.1, "calf": 34.0, "ankle": 12.5}
ANCHOR_GIRTH_W0 = {"waist": 69.03, "hips": 97.63, "thigh": 53.67, "knee": 34.43, "calf": 35.06, "ankle": 20.24}
# (场名, 站名, w=1 响应锚值, 方向下限)
ANCHOR_RESPONSE = [
    ("waist+", "waist", 10.55, 2.0), ("waist-", "waist", -10.15, -2.0),
    ("hips+", "hips", 19.35, 2.0), ("hips-", "hips", -9.65, -2.0),
    ("thigh+", "thigh", 5.95, 1.0), ("thigh-", "thigh", -3.92, -1.0),
    ("knee+", "knee", 6.48, 1.0), ("knee-", "knee", -3.69, -1.0),
    ("calf+", "calf", 10.05, 2.0), ("calf-", "calf", -9.99, -2.0),
    ("ankle+", "ankle", 5.93, 1.0), ("ankle-", "ankle", -5.93, -1.0),
]
TOL_LANDMARK = 2.0
TOL_GIRTH = 1.0
TOL_RESPONSE = 1.5


def _load_vendor_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("vendor_makehuman", _ROOT / "scripts" / "vendor_makehuman.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_bin(path: Path):
    """按 scripts/vendor_makehuman.py 头注布局解析 base.bin。"""
    data = path.read_bytes()
    v, f, t = struct.unpack_from("<III", data, 0)
    off = 12
    verts = list(struct.unpack_from(f"<{3 * v}f", data, off))
    off += 12 * v
    tris = list(struct.unpack_from(f"<{3 * f}I", data, off))
    off += 12 * f
    targets = []
    for _ in range(t):
        (n,) = struct.unpack_from("<I", data, off)
        off += 4
        idx = list(struct.unpack_from(f"<{n}I", data, off))
        off += 4 * n
        flat = list(struct.unpack_from(f"<{3 * n}f", data, off))
        off += 12 * n
        deltas = {i: tuple(flat[3 * k: 3 * k + 3]) for k, i in enumerate(idx)}
        targets.append(deltas)
    assert off == len(data), f"base.bin 尾部残留 {len(data) - off} 字节"
    pos = [tuple(verts[3 * i: 3 * i + 3]) for i in range(v)]
    faces = [tuple(tris[3 * i: 3 * i + 3]) for i in range(f)]
    return pos, faces, targets


@unittest.skipUnless(_BIN.exists() and _META.exists(), "bodymesh 数据缺席（先跑 scripts/vendor_makehuman.py）")
class TestVendorBodymesh(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        cls.pos, cls.faces, cls.targets = read_bin(_BIN)
        cls.meta = json.loads(_META.read_text(encoding="utf-8"))
        cls.by_name = {t["name"]: deltas for t, deltas in zip(cls.meta["targets"], cls.targets)}
        cls.vm = _load_vendor_module()

    def girth(self, pos, y, leg_side=None):
        return self.vm.girth_at([list(p) for p in pos], self.faces, y, leg_side=leg_side)

    def test_counts_match_meta(self):
        self.assertEqual(len(self.pos), self.meta["vertexCount"])
        self.assertEqual(len(self.faces), self.meta["triangleCount"])
        self.assertEqual(len(self.targets), len(self.meta["targets"]))
        self.assertEqual(len(self.targets), 14)
        # 纯官方场链：12 measure + 身高 macro ±，无派生场
        self.assertEqual(
            sorted(t["name"] for t in self.meta["targets"]),
            sorted([f"{s}{d}" for s in ("waist", "hips", "thigh", "knee", "calf", "ankle", "height") for d in "+-"]))
        for t in self.meta["targets"]:
            self.assertTrue(t["file"].startswith(("measure/", "macrodetails/height/")),
                            f"{t['name']} 应为官方场（纯官方场链无派生）")
            self.assertGreater(t["count"], 100)
        # 身高场覆盖全网格（含切缝交点/封盖质心的插值增量）——顶环随身体同步升降
        for t in self.meta["targets"]:
            if t["name"].startswith("height"):
                self.assertEqual(t["count"], self.meta["vertexCount"],
                                 f"{t['name']} 应覆盖全部顶点（合成顶点插值缺席？）")

    def test_topology_watertight(self):
        from collections import Counter
        ec = Counter()
        for (a, b, c) in self.faces:
            for e in ((a, b), (b, c), (c, a)):
                ec[(min(e), max(e))] += 1
        self.assertTrue(all(n == 2 for n in ec.values()), "不水密（存在非 2 共享边）")
        euler = len(self.pos) - len(ec) + len(self.faces)
        self.assertEqual(euler, 2, f"欧拉示性数 {euler} ≠ 2（亏格异常）")
        self.assertEqual(len(self.pos), 4311)
        self.assertEqual(len(self.faces), 8618)

    def test_topology_constant_across_morph(self):
        """morph 只动位置：w=1 全场叠加后索引/面恒定、无越界。"""
        v1 = [list(p) for p in self.pos]
        for deltas in self.targets:
            for i, d in deltas.items():
                self.assertLess(i, len(v1))
                v1[i][0] += d[0]; v1[i][1] += d[1]; v1[i][2] += d[2]
        self.assertEqual(len(v1), len(self.pos))

    def test_orientation_front_is_plus_z(self):
        zmax = max(p[2] for p in self.pos if p[1] < 15)
        self.assertGreaterEqual(zmax, 18, f"脚带 z_max={zmax:.1f} < 18，+Z 不是前方")

    def test_landmark_heights(self):
        lm = self.meta["landmarkHeights"]
        for k, anchor in ANCHOR_LANDMARKS.items():
            self.assertAlmostEqual(lm[k], anchor, delta=TOL_LANDMARK, msg=f"地标 {k} 漂移")
        self.assertLess(lm["knee"], lm["crotch"])
        self.assertLess(lm["crotch"], lm["hip"])
        self.assertLess(lm["hip"], lm["waist"])
        self.assertLess(lm["waist"], self.meta["cut"]["planeY"])
        # 下行链有序：膝 > 小腿肚 > 踝（小腿肚在膝/踝两极小之间）
        self.assertLess(lm["calf"], lm["knee"])
        self.assertGreater(lm["calf"], lm["ankle"])
        # 站高与地标一致性（thigh = 裆−3）
        st = {s["name"]: s["y"] for s in self.meta["stations"]}
        self.assertAlmostEqual(st["thigh"], lm["crotch"] - 3.0, delta=0.01)
        self.assertAlmostEqual(st["waist"], lm["waist"], delta=0.01)
        self.assertAlmostEqual(st["hips"], lm["hip"], delta=0.01)
        self.assertAlmostEqual(st["knee"], lm["knee"], delta=0.01)
        self.assertAlmostEqual(st["calf"], lm["calf"], delta=0.01)
        self.assertAlmostEqual(st["ankle"], lm["ankle"], delta=0.01)

    def test_girth_anchors_w0(self):
        st = {s["name"]: (s["y"], s["per"]) for s in self.meta["stations"]}
        for k, anchor in ANCHOR_GIRTH_W0.items():
            y, per = st[k]
            g = self.girth(self.pos, y, leg_side=("+" if per == "leg" else None))
            self.assertAlmostEqual(g, anchor, delta=TOL_GIRTH, msg=f"w=0 站点围度 {k} 漂移")

    def test_official_target_response_direction(self):
        """官方场自家站方向响应（重映射正确性）：锚值带 + 方向下限双锁。"""
        leg_st = {"thigh", "knee", "calf", "ankle"}
        st = {s["name"]: s["y"] for s in self.meta["stations"]}
        g0 = {s: self.girth(self.pos, y, leg_side=("+" if s in leg_st else None))
              for s, y in st.items()}
        for name, station, anchor, floor in ANCHOR_RESPONSE:
            with self.subTest(field=name):
                v1 = self.vm.apply_target([list(p) for p in self.pos], self.by_name[name], 1.0)
                g1 = self.girth(v1, st[station], leg_side=("+" if station in leg_st else None))
                dg = g1 - g0[station]
                self.assertAlmostEqual(dg, anchor, delta=TOL_RESPONSE)
                if floor > 0:
                    self.assertGreater(dg, floor)
                else:
                    self.assertLess(dg, floor)

    def test_meta_height(self):
        """meta.height（切割前全身实测的预设换算基准）：基高域、ΔH 双向、
        四档预设（155/160/165/170）权重可达且换算互逆。"""
        h = self.meta["height"]
        base, plus, minus = h["baseCm"], h["plusCmAtW1"], h["minusCmAtW1"]
        self.assertTrue(160.0 <= base <= 180.0, f"基高 {base} 出域")
        self.assertGreater(plus, 1.0, "ΔH+ 异常（场文件错？）")
        self.assertLess(minus, -1.0, "ΔH− 异常（场文件错？）")
        for target in (155.0, 160.0, 165.0, 170.0):
            with self.subTest(preset=target):
                w = (target - base) / plus if target >= base else (base - target) / minus
                self.assertGreaterEqual(w, -1.0, f"预设 {target} 超官方 macro 域下限")
                self.assertLessEqual(w, 1.0, f"预设 {target} 超官方 macro 域上限")
                back = base + (w * plus if w >= 0 else -w * minus)
                self.assertAlmostEqual(back, target, delta=0.01, msg="身高↔权重换算不互逆")

    def test_height_field_direction(self):
        """身高场方向（切割网格 w=1）：height− 顶降 / height+ 顶升 / 脚底锚地。
        锚值 = 2026-09-13 实测 dTop −30.93 / +58.88（全身 ΔH −36.69 / +72.02 的
        可见份额——切割面下增量按高度衰减）；切缝/封盖合成顶点已按边端点插值
        补增量，顶环随身体同步升降无撕裂带。"""
        h0 = max(p[1] for p in self.pos)
        for name, anchor in (("height-", -30.93), ("height+", 58.88)):
            with self.subTest(field=name):
                v1 = self.vm.apply_target([list(p) for p in self.pos], self.by_name[name], 1.0)
                d = max(p[1] for p in v1) - h0
                self.assertAlmostEqual(d, anchor, delta=1.0)
                if anchor < 0:
                    self.assertLess(d, -2.0, "height− 未压低身体")
                else:
                    self.assertGreater(d, 2.0, "height+ 未拉高身体")
                self.assertGreaterEqual(min(p[1] for p in v1), -1.0, "身高场抬脚离地/穿地 > 1cm")

    def test_official_targets_mirror_symmetric(self):
        """官方 12 场增量镜像对称：随帧旋转的线性角未归一时（atan2+π 原值
        ~353°×部分权重）会把一侧增量翻转半个平面——hips+ 单侧内凹实发穿透
        全部旧守卫；官方权重 L/R 精确镜像、归一角旋转保对称（基线 0.000）。"""
        import math
        cell = {}
        for j, q in enumerate(self.pos):
            cell.setdefault((round(q[1]), round(q[2])), []).append(j)
        pairs = []
        for i, p in enumerate(self.pos):
            if p[0] <= 0.5:
                continue
            best, bd = None, 1e9
            for j in cell.get((round(p[1]), round(p[2])), []):
                q = self.pos[j]
                if q[0] >= -0.5:
                    continue
                dd = (q[0] + p[0]) ** 2 + (q[1] - p[1]) ** 2 + (q[2] - p[2]) ** 2
                if dd < bd:
                    bd, best = dd, j
            if best is not None and bd < 0.04:
                pairs.append((i, best))
        self.assertGreater(len(pairs), 1000, "镜像配对退化（基网格不对称？）")
        for name, deltas in zip((t["name"] for t in self.meta["targets"]), self.targets):
            with self.subTest(field=name):
                worst, n = 0.0, 0
                for i, j in pairs:
                    di, dj = deltas.get(i), deltas.get(j)
                    if di and dj:
                        worst = max(worst, math.dist(di, [-dj[0], dj[1], dj[2]]))
                        n += 1
                self.assertGreater(n, 150, f"{name} 镜像覆盖对过少（配对退化？）")
                self.assertLessEqual(worst, 0.01, f"{name} 增量镜像破缺 {worst:.3f}cm")

    def test_leg_axis_standing_vertical(self):
        """站直守卫（双向防回归）：腿轴竖直 + 膝铅垂 + 不并腿。"""
        cr = self.meta["landmarkHeights"]["crotch"]
        pos = [list(p) for p in self.pos]
        cx10 = self.vm._leg_cx(pos, self.faces, cr - 10.0, "+")
        cx30 = self.vm._leg_cx(pos, self.faces, cr - 30.0, "+")
        cx45 = self.vm._leg_cx(pos, self.faces, cr - 45.0, "+")
        self.assertIsNotNone(cx10); self.assertIsNotNone(cx30); self.assertIsNotNone(cx45)
        # 竖直：踝段相对大腿根漂移 ≤2cm（A-pose 回归时差 ~5.9；过度内收反向塌缩）
        self.assertLessEqual(abs(cx45 - cx10), 2.0,
            f"腿轴不竖直（cx crotch−10 {cx10:.1f} → crotch−45 {cx45:.1f}）：A-pose/过度内收回归？")
        # 膝在铅垂线上：防「整腿绕髋一转」简化回归（膝弓残留时 |cx30−cx10| 抬升）
        self.assertLessEqual(abs(cx30 - cx10), 1.5,
            f"膝偏离铅垂线（cx crotch−30 {cx30:.1f} vs crotch−10 {cx10:.1f}）")
        # 不并腿/不交叉
        self.assertGreater(cx10, 5.0, "裆下腿距异常贴拢：内收回归？")

    def test_sole_flat_and_mirror(self):
        """站直守卫：左右脚底触点同高（脚平）；膝/小腿肚/踝带左右环质心镜像。"""
        feet = [p for p in self.pos if p[1] < 1.0]
        min_l = min(p[1] for p in feet if p[0] < 0.0)
        min_r = min(p[1] for p in feet if p[0] > 0.0)
        self.assertLessEqual(abs(min_l - min_r), 0.1, "左右脚底最低点差 > 0.1（脚底倾斜）")
        pos = [list(p) for p in self.pos]
        lm = self.meta["landmarkHeights"]
        for name in ("knee", "calf", "ankle"):
            cx_l = self.vm._leg_cx(pos, self.faces, lm[name], "-")
            cx_r = self.vm._leg_cx(pos, self.faces, lm[name], "+")
            self.assertIsNotNone(cx_l); self.assertIsNotNone(cx_r)
            self.assertLessEqual(abs(cx_l + cx_r), 0.3, f"{name} 带左右镜像破缺")

    def test_meta_schema2_no_calibration(self):
        """schema 2（切割+站直链）：标定矩阵随闭环链退役，不得回流。"""
        self.assertEqual(self.meta["schema"], 2)
        self.assertNotIn("calibration", self.meta)
        self.assertIn("baseSha256", self.meta)
        self.assertEqual(self.meta["cut"]["aboveWaistCm"], 15.0)
        # 站直姿势 meta：名 + L/R 镜像角（t 大腿 / k 膝上补角 / ca 小腿合成）
        self.assertEqual(self.meta["pose"]["name"], "standing")
        th = self.meta["pose"]["thetasDeg"]
        for k in ("t", "k", "ca"):
            self.assertAlmostEqual(th["L"][k], -th["R"][k], delta=0.01, msg=f"θ_{k} 左右不镜像")
        for k in ("t", "ca"):
            self.assertTrue(4.0 <= abs(th["R"][k]) <= 12.0, f"θ_{k} 超站直合理域")


if __name__ == "__main__":
    unittest.main()
