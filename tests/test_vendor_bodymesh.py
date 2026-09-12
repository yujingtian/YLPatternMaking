# -*- coding: utf-8 -*-
"""MakeHuman vendor 产物金标（webapp/frontend/public/bodymesh/{base.bin, targets.json}）。

数据缺席整文件 skip（先例 test_reverse_gold_5015.py）。锚值 = 2026-09-13 默认参数
vendor（纯切割链）运行的手工核读——**零姿势修改**：腿去外张/内收/解剖雕塑/
派生场/预标定矩阵全部退役（姿势手术撕裂臀线，演进史 .doc/决策日志.md §十一），
形态调节 = 官方 12 个 measure target（腰/臀/大腿/膝/小腿/踝）运行时叠加
（原生场固有缺陷原样呈现）：

    地标高度（cm，脚底=0、+Z 前）：crotch 77.6 / hip 83.6 / waist 104.6 /
        knee 47.1 / calf 34.0（小腿肚=右腿围度局部极大）/ ankle 12.5
        （较姿势链 crotch−3：不去外张腿自然 A-pose，腿环质心外移使裆合并点
        上移带轻微差）
    w=0 基网格站点围度（cm）：waist 69.27 / hips 98.68 / thigh 右腿 54.74 /
        knee 右腿 34.59 / calf 右腿 35.37 / ankle 右腿 20.36
    w=1 官方场站点响应（cm）：waist+ +10.60 / waist− −10.20 / hips+ +19.36 /
        hips− −9.66 / thigh+ +6.39 / thigh− −4.15 / knee+ +6.71 / knee− −3.79 /
        calf+ +10.01 / calf− −9.99 / ankle+ +5.97 / ankle− −5.97
        （官方场在自家站方向响应全部成立——重映射正确性守卫；注意 thigh 峰值带
         crotch−14 与站点 crotch−3 天然错位，量级断言只锁方向与下限，不锁精确值）
    A-pose 腿轴外张（零姿势修改守卫）：右腿环质心 cx@crotch−10 = 12.47 →
        cx@crotch−45 = 18.38（base.obj 绑定姿势腿自裆 ±9.6 外撇到踝 ±22 的
        自然剖面；若混入内收/去外张回归，此差值塌缩）
    网格：V 4276 / F 8548 / E 12822，水密（每边恰 2 面），欧拉 = 2

守卫口径：布局契约（尾部残留防爆）、拓扑跨 morph 恒定（裁切后顶点索引冻结）、
朝向（脚趾 +Z）、地标高度带（防地标检测回归）、围度锚带（防站点漂移）、
官方场方向响应（防重映射错位）、A-pase 外张差（防姿势手术回归混入）。"""
import struct
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_BIN = _ROOT / "webapp" / "frontend" / "public" / "bodymesh" / "base.bin"
_META = _ROOT / "webapp" / "frontend" / "public" / "bodymesh" / "targets.json"

# 手工演算锚值（见模块 docstring；容差吸收 girth 切片步进的舍入）
ANCHOR_LANDMARKS = {"crotch": 77.6, "hip": 83.6, "waist": 104.6, "knee": 47.1, "calf": 34.0, "ankle": 12.5}
ANCHOR_GIRTH_W0 = {"waist": 69.27, "hips": 98.68, "thigh": 54.74, "knee": 34.59, "calf": 35.37, "ankle": 20.36}
# (场名, 站名, w=1 响应锚值, 方向下限)
ANCHOR_RESPONSE = [
    ("waist+", "waist", 10.60, 2.0), ("waist-", "waist", -10.20, -2.0),
    ("hips+", "hips", 19.36, 2.0), ("hips-", "hips", -9.66, -2.0),
    ("thigh+", "thigh", 6.39, 1.0), ("thigh-", "thigh", -4.15, -1.0),
    ("knee+", "knee", 6.71, 1.0), ("knee-", "knee", -3.79, -1.0),
    ("calf+", "calf", 10.01, 2.0), ("calf-", "calf", -9.99, -2.0),
    ("ankle+", "ankle", 5.97, 1.0), ("ankle-", "ankle", -5.97, -1.0),
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
        self.assertEqual(len(self.targets), 12)
        # 纯切割链：12 场全部是官方 measure 文件，无派生场
        self.assertEqual(
            sorted(t["name"] for t in self.meta["targets"]),
            sorted([f"{s}{d}" for s in ("waist", "hips", "thigh", "knee", "calf", "ankle") for d in "+-"]))
        for t in self.meta["targets"]:
            self.assertTrue(t["file"].startswith("measure-"), f"{t['name']} 应为官方场（纯切割链无派生）")
            self.assertGreater(t["count"], 100)

    def test_topology_watertight(self):
        from collections import Counter
        ec = Counter()
        for (a, b, c) in self.faces:
            for e in ((a, b), (b, c), (c, a)):
                ec[(min(e), max(e))] += 1
        self.assertTrue(all(n == 2 for n in ec.values()), "不水密（存在非 2 共享边）")
        euler = len(self.pos) - len(ec) + len(self.faces)
        self.assertEqual(euler, 2, f"欧拉示性数 {euler} ≠ 2（亏格异常）")
        self.assertEqual(len(self.pos), 4276)
        self.assertEqual(len(self.faces), 8548)

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

    def test_leg_axis_natural_splay(self):
        """A-pose 腿轴自然外张（零姿势修改守卫）：下行质心外移 ≥3cm。"""
        cr = self.meta["landmarkHeights"]["crotch"]
        pos = [list(p) for p in self.pos]
        cx_hi = self.vm._leg_cx(pos, self.faces, cr - 10.0, "+")
        cx_lo = self.vm._leg_cx(pos, self.faces, cr - 45.0, "+")
        self.assertIsNotNone(cx_hi); self.assertIsNotNone(cx_lo)
        self.assertGreaterEqual(cx_lo - cx_hi, 3.0,
            f"腿轴外张塌缩（{cx_hi:.1f}→{cx_lo:.1f}）：姿势手术（去外张/内收）回归？")
        self.assertGreater(cx_hi, 5.0, "裆下腿距异常贴拢：内收回归？")

    def test_meta_schema2_no_calibration(self):
        """schema 2（纯切割链）：标定矩阵随闭环链退役，不得回流。"""
        self.assertEqual(self.meta["schema"], 2)
        self.assertNotIn("calibration", self.meta)
        self.assertIn("baseSha256", self.meta)
        self.assertEqual(self.meta["cut"]["aboveWaistCm"], 15.0)


if __name__ == "__main__":
    unittest.main()
