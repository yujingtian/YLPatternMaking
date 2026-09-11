# -*- coding: utf-8 -*-
"""MakeHuman vendor 产物金标（webapp/frontend/public/bodymesh/{base.bin, targets.json}）。

数据缺席整文件 skip（先例 test_reverse_gold_5015.py）。锚值 = 2026-09-11 默认参数
vendor 运行的手工核读（含腿去外张 + 臀检测带上移 + 腿内收 + thigh 派生场四修复）：

    地标高度（cm，脚底=0、+Z 前）：crotch 80.6 / hip 86.6 / waist 107.6 / knee 48.1 / ankle 13.5
    w=0 基网格站点围度（cm）：waist 69.54 / hips 98.76 / thigh 右腿 54.15 / knee 右腿 34.38
    w=1 knee+ 响应：膝围 40.83（+6.46），腰/臀/大腿三站零变化
    w=1 waist+ 响应：腰围 80.18（+10.64），膝站零变化
    w=1 thigh+（派生场）响应：站点 Δg ≈ +3.9~4.2，峰值带 78.1（站点 77.6 ±0.5）
    去外张：α=10.71°、脚底下探 re-zero +3.1cm、腿轴竖直残差 spread <1.2 金标
    腿内收：大腿段（膝上）gap 5.3~6.5 → ≤2.1、小腿段 → ≤3.5、脚部原生（8~11 自然外展）
    网格：V 4264 / F 8524 / E 12786，水密（每边恰 2 面），欧拉 = 2

守卫口径：拓扑跨 morph 恒定（裁切后顶点索引冻结，morph 只动位置）、朝向（脚趾 +Z）、
地标高度带（防地标检测回归——2026-09-11 曾有腰=髂骨上凹/臀<裆两轮误检）、围度锚带
（防标定站点漂移）、单调响应 + 串扰界（标定矩阵可用性）、腿轴竖直（去外张回归守卫：
base.obj 是 A-pose 绑定姿势，腿自裆 ±9.6 外撇到踝 ±22，不去外张则人台叉腿）、
thigh 派生场对位（原生 measure-thigh-circ 峰值带 crotch−14 与站点 crotch−3 错位
11cm、站点灵敏度仅峰值 39%，闭环为凑站点围度把大腿中段推爆——「调大腿围变粗
位置太靠下」根因，2026-09-11 用户目检坐实）、大腿内侧 gap（A-pose 腿间距回归守卫）。"""
import struct
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_BIN = _ROOT / "webapp" / "frontend" / "public" / "bodymesh" / "base.bin"
_META = _ROOT / "webapp" / "frontend" / "public" / "bodymesh" / "targets.json"

# 手工演算锚值（见模块 docstring；容差吸收 girth 切片步进的舍入）
ANCHOR_LANDMARKS = {"crotch": 80.6, "hip": 86.6, "waist": 107.6, "knee": 48.1, "ankle": 13.5}
ANCHOR_GIRTH_W0 = {"waist": 69.54, "hips": 98.76, "thigh": 54.15, "knee": 34.38}
TOL_LANDMARK = 2.0
TOL_GIRTH = 1.0


def _load_vendor_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("vendor_makehuman", _ROOT / "scripts" / "vendor_makehuman.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_bin(path: Path):
    """按 scripts/vendor_makehuman.py 头注布局解析 base.bin（TS load.ts 的规范参照）。"""
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


def girth(pos, faces, y, leg_side=None):
    vm = _load_vendor_module()
    return vm.girth_at([list(p) for p in pos], [tuple(f) for f in faces], y, leg_side=leg_side)


@unittest.skipUnless(_BIN.exists() and _META.exists(), "bodymesh 数据缺席（先跑 scripts/vendor_makehuman.py）")
class TestVendorBodymesh(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        cls.pos, cls.faces, cls.targets = read_bin(_BIN)
        cls.meta = json.loads(_META.read_text(encoding="utf-8"))
        cls.by_name = {t["name"]: i for i, t in enumerate(cls.meta["targets"])}

    def test_counts_match_meta(self):
        self.assertEqual(len(self.pos), self.meta["vertexCount"])
        self.assertEqual(len(self.faces), self.meta["triangleCount"])
        self.assertEqual(len(self.targets), len(self.meta["targets"]))
        for i, t in enumerate(self.meta["targets"]):
            self.assertEqual(len(self.targets[i]), t["count"], t["name"])

    def test_topology_watertight(self):
        from collections import Counter
        ec = Counter()
        for a, b, c in self.faces:
            for e in ((a, b), (b, c), (c, a)):
                ec[(min(e), max(e))] += 1
        self.assertTrue(all(n == 2 for n in ec.values()), "非水密")
        self.assertEqual(len(self.pos) - len(ec) + len(self.faces), 2, "欧拉示性数 ≠ 2")
        for v in range(len(self.pos)):
            for c in self.pos[v]:
                self.assertIsInstance(c, float)

    def test_topology_constant_across_morph(self):
        from collections import Counter
        for name, deltas in zip((t["name"] for t in self.meta["targets"]), self.targets):
            pos = [list(p) for p in self.pos]
            for i, d in deltas.items():
                for k in range(3):
                    pos[i][k] += d[k]
            ec = Counter()
            for a, b, c in self.faces:
                for e in ((a, b), (b, c), (c, a)):
                    ec[(min(e), max(e))] += 1
            self.assertTrue(all(n == 2 for n in ec.values()), f"{name} w=1 破坏水密")
            self.assertEqual(len(pos) - len(ec) + len(self.faces), 2, f"{name} w=1 欧拉漂移")

    def test_orientation_front_is_plus_z(self):
        zmax = max(p[2] for p in self.pos if p[1] < 15)
        self.assertGreaterEqual(zmax, 18.0, "脚带 z_max < 18：+Z 不是前方")

    def test_leg_axis_vertical(self):
        """去外张守卫：右腿环质心在裆下三点（裆−10/裆−25/裆−45）离散 < 1.2cm
        （A-pose 原始腿轴自裆 ±9.6 外撇到踝 ±22，残差 >5cm 即去外张回归）。"""
        vm = _load_vendor_module()
        lm = self.meta["landmarkHeights"]["crotch"]
        cxs = [vm._leg_cx([list(p) for p in self.pos], [tuple(f) for f in self.faces],
                          lm - d, "+") for d in (10.0, 25.0, 45.0)]
        self.assertTrue(all(c is not None for c in cxs), f"腿环缺失 {cxs}")
        spread = max(cxs) - min(cxs)
        self.assertLess(spread, 1.2, f"腿轴竖直残差 {spread:.2f}（去外张回归）")
        # 外张残留方向守卫：低处（裆−45）质心不得比高处（裆−10）更外超过 1cm
        #（解剖上胫骨微内翻：低处略内收 ~1cm 属正常，外撇才是回归）
        self.assertLess(cxs[2], cxs[0] + 1.0, "腿轴低处显著更外（外张未去净）")

    def test_landmark_heights(self):
        for name, anchor in ANCHOR_LANDMARKS.items():
            got = self.meta["landmarkHeights"][name]
            self.assertAlmostEqual(got, anchor, delta=TOL_LANDMARK, msg=f"{name} 地标漂移")
            self.assertLess(self.meta["landmarks"][name], len(self.pos), f"{name} 地标索引越界")

    def test_girth_anchors_w0(self):
        stations = {s["name"]: (s["y"], s["per"]) for s in self.meta["stations"]}
        for name, anchor in ANCHOR_GIRTH_W0.items():
            y, per = stations[name]
            side = "+" if per == "leg" else None
            g = girth(self.pos, self.faces, y, leg_side=side)
            self.assertAlmostEqual(g, anchor, delta=TOL_GIRTH, msg=f"{name} w=0 围度锚")

    def test_monotone_response_and_crosstalk(self):
        stations = {s["name"]: (s["y"], s["per"]) for s in self.meta["stations"]}

        def measure(target_name, w, station):
            y, per = stations[station]
            side = "+" if per == "leg" else None
            deltas = self.targets[self.by_name[target_name]]
            pos = [list(p) for p in self.pos]
            if w:
                for i, d in deltas.items():
                    for k in range(3):
                        pos[i][k] += w * d[k]
            return girth(pos, self.faces, y, leg_side=side)

        # 单调响应：knee+/waist+ 各自抬本站
        self.assertGreater(measure("knee+", 1.0, "knee") - measure("knee+", 0.0, "knee"), 3.0)
        self.assertGreater(measure("waist+", 1.0, "waist") - measure("waist+", 0.0, "waist"), 3.0)
        self.assertLess(measure("knee-", 1.0, "knee") - measure("knee-", 0.0, "knee"), -3.0)
        # 串扰界：knee+ 不动腰、waist+ 不动膝（近对角性 = 联合标定可解）
        self.assertLess(abs(measure("knee+", 1.0, "waist") - measure("knee+", 0.0, "waist")), 0.5)
        self.assertLess(abs(measure("waist+", 1.0, "knee") - measure("waist+", 0.0, "knee")), 0.5)

    def test_thigh_derived_band_alignment(self):
        """thigh 派生场对位守卫：峰值 Δgirth 带必须落在站点 ±3.5cm（径向保形场
        以站为中心构造；原生 target 峰值在 crotch−14 错位 11cm 是观感事故根因）。"""
        stations = {s["name"]: s["y"] for s in self.meta["stations"]}
        crotch = self.meta["landmarkHeights"]["crotch"]
        th = self.targets[self.by_name["thigh+"]]
        pos = [list(p) for p in self.pos]
        for i, d in th.items():
            for k in range(3):
                pos[i][k] += d[k]
        best_y, best_dg = None, -1e9
        for y in range(int(crotch) - 30, int(crotch) + 2):
            g0 = girth(self.pos, self.faces, y + 0.5, leg_side="+")
            g1 = girth(pos, self.faces, y + 0.5, leg_side="+")
            if g0 and g1 and g1 - g0 > best_dg:
                best_y, best_dg = y + 0.5, g1 - g0
        self.assertIsNotNone(best_y, "thigh+ Δgirth 曲线全空")
        self.assertLess(abs(best_y - stations["thigh"]), 3.5,
                        f"thigh+ 峰值带 {best_y:.1f} 偏离站点 {stations['thigh']:.1f}")
        # 站点响应量级带（与原生同量级 → 闭环权量级不变）
        row = self.meta["calibration"]["thigh+"]["thigh"]
        self.assertTrue(3.0 <= row[2] - row[0] <= 8.0,
                        f"站点响应 {row[2] - row[0]:.2f} 不在 [3,8]cm")
        # 对角性：thigh+ 不动腰/膝（hips↔thigh 串扰由闭环联合迭代消化）
        for far in ("waist", "knee"):
            fr = self.meta["calibration"]["thigh+"][far]
            self.assertLess(abs(fr[2] - fr[0]), 0.3, f"thigh+ 串扰 {far} 站")

    def test_thigh_gap_closed(self):
        """A-pose 腿间距内收守卫：大腿主段（crotch−30..crotch−6）内侧 gap ≤ 3.2
        （原 5.3~6.5；adduct_thighs 分段目标 2/3.5 共向平移；crotch−6 以内的
        V 形渐开属会阴三角区自然形态，不在守卫带）。"""
        vm = _load_vendor_module()
        crotch = self.meta["landmarkHeights"]["crotch"]
        pos = [list(p) for p in self.pos]
        faces = [tuple(f) for f in self.faces]
        worst = 0.0
        for d in range(6, 32, 2):
            loops = vm._slice_loops(pos, faces, crotch - d)
            cand = [(pts, cx) for pts, cx in loops if cx > 2.0]
            if not cand:
                continue
            pts, _ = max(cand, key=lambda l: l[1])
            worst = max(worst, 2.0 * min(p[0] for p in pts))
        self.assertLessEqual(worst, 3.2, f"大腿内侧 gap 残 {worst:.2f} > 3.2（内收回归）")

    def test_calibration_matrix_monotone(self):
        tol = 0.05  # 切片围度插值噪声 ~0.005cm；真实信号 3~16cm，0.05 只吸收抖动
        for name, row in self.meta["calibration"].items():
            for station, vals in row.items():
                g0, gh, g1 = vals
                if None in (g0, gh, g1):
                    continue
                if name.endswith("+"):
                    self.assertLessEqual(g0, gh + tol, f"{name}/{station} 非单调")
                    self.assertLessEqual(gh, g1 + tol, f"{name}/{station} 非单调")
                else:
                    self.assertGreaterEqual(g0, gh - tol, f"{name}/{station} 非单调")
                    self.assertGreaterEqual(gh, g1 - tol, f"{name}/{station} 非单调")


if __name__ == "__main__":
    unittest.main()
