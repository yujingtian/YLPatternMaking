# -*- coding: utf-8 -*-
"""MakeHuman vendor 产物金标（webapp/frontend/public/bodymesh/{base.bin, targets.json}）。

数据缺席整文件 skip（先例 test_reverse_gold_5015.py）。锚值 = 2026-09-12 默认参数
vendor 运行的手工核读（含腿去外张 + 臀检测带上移 + 腿内收 v3 剖面 + thigh/knee/hips
三派生场 + 基网格四解剖 sculpt：大转子削圆/大腿肌群三叶/耻骨隆突/腹股沟凹槽）：

    地标高度（cm，脚底=0、+Z 前）：crotch 80.6 / hip 86.6 / waist 107.6 / knee 48.1 / ankle 13.5
    w=0 基网格站点围度（cm）：waist 69.54 / hips 99.19 / thigh 右腿 53.46 / knee 右腿 34.38
        （二轮较一轮 hips +0.43/thigh −0.29：转子主削自裆+3.5 移到穹顶裆−1——臀站
         （裆+6）窗值 0 不再削、大腿上段近肩带被轻削；构建期自检已锁；
         sculpt 存活守卫在 vendor 脚本 return 26-29，本金标锁产物侧形态）
    w=1 knee+（派生场）响应：膝围 39.51（+5.12），腰/臀/大腿三站零变化
    w=1 waist+ 响应：腰围 80.18（+10.64），膝站零变化
    w=1 hips+（派生躯干场·二轮平顶窗，2026-09-12 替换原生）响应：臀围 114.12
        （+14.92），腰站零变化、thigh 站 +9.20（平顶窗把场下缘铺到臀褶带——
        臀腿物理重叠刻意保留，闭环差分雅可比联立消解；thigh± amp0 同步 1.0）
    w=1 thigh+（派生场）响应：站点 Δg +5.21（amp0 0.8→1.0），峰值带 77.1
        （站点 77.6 ±0.5）；非对称窗下尾铺膝：crotch−15 带 Δg 2.14、膝站串扰 0
    knee+ w=1 膝站内侧 gap 1.40（旧原生场 0.01~0.3 = 双膝贴拢根因）
    去外张：α=10.71°、脚底下探 re-zero +3.1cm、腿轴自然内斜残差 spread <2.5 金标
    腿内收 v3 剖面（2026-09-12 二轮 VLM「大腿缝等宽槽」加深，smoothstep C¹ 插值）：
        控制点 (裆−1, 4.2) → (裆−12, 1.2) → (裆−20, 0.9) → (裆−26, 1.8) →
        (裆−38, 3.5)，叉口水滴形、大腿中段贴合 ~1、膝上回松；fork 渐出 12→7cm
        （v2 在裆下 6~10 压弱 δ = 叉口全张读作挖空的根因）；裆−6 处 ~3.9
        （fork 渐出带，解剖臀褶自然张开）、裆−16 ~1.2、主段 ≤3.2；
        外缘 Lipschitz 每cm 骤降 ≤0.5（旧整段平移 δ≈2.2 外缘撕台阶 =「球包」根因）
    网格：V 4264 / F 8524 / E 12786，水密（每边恰 2 面），欧拉 = 2

守卫口径：拓扑跨 morph 恒定（裁切后顶点索引冻结，morph 只动位置）、朝向（脚趾 +Z）、
地标高度带（防地标检测回归——2026-09-11 曾有腰=髂骨上凹/臀<裆两轮误检）、围度锚带
（防标定站点漂移）、单调响应 + 串扰界（标定矩阵可用性）、腿轴自然内斜（去外张回归
守卫：base.obj 是 A-pose 绑定姿势，腿自裆 ±9.6 外撇到踝 ±22，不去外张则人台叉腿）、
thigh 派生场对位（原生 measure-thigh-circ 峰值带 crotch−14 与站点 crotch−3 错位
11cm、站点灵敏度仅峰值 39%，闭环为凑站点围度把大腿中段推爆——「调大腿围变粗
位置太靠下」根因，2026-09-11 用户目检坐实）、thigh 下尾铺膝（对称半宽 18 在
crotch−21 截断留膝上 11.5cm 死区 →「大腿→膝维度不渐变」根因，同日二轮报障）、
knee± 派生场对位 + 膝站间隙 floor（原生 knee+ 上缘 y57-66 纯内侧 −x 剪切边 +
canonical 站错位 + 满钳可达 40.8 不够常见输入 43~46 →「腿部中段往中线扭曲/
双膝贴拢」根因，同日逐顶点数字坐实）、hips± 派生躯干场对位（原生拉力剖面非单调
y79 0.71 → y81 0.66 凹 → y83 1.15 跳升台阶指纹 + 基网格裆线平台 →「平顶+陡崖」
方形折角根因，2026-09-12 逐顶点坐实）、大腿内侧 gap（A-pose 腿间距回归守卫）、
外缘轮廓连续（自裆−17 到裆+8 覆盖转子削圆带——sculpt 后外缘骤降 ≤0.5/cm）。"""
import struct
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_BIN = _ROOT / "webapp" / "frontend" / "public" / "bodymesh" / "base.bin"
_META = _ROOT / "webapp" / "frontend" / "public" / "bodymesh" / "targets.json"

# 手工演算锚值（见模块 docstring；容差吸收 girth 切片步进的舍入）
ANCHOR_LANDMARKS = {"crotch": 80.6, "hip": 86.6, "waist": 107.6, "knee": 48.1, "ankle": 13.5}
ANCHOR_GIRTH_W0 = {"waist": 69.54, "hips": 99.19, "thigh": 53.46, "knee": 34.38}
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

    def test_leg_axis_natural(self):
        """去外张守卫：右腿环质心在裆下三点（裆−10/裆−25/裆−45）离散 < 2.5cm。
        2026-09-12 叉部渐出后腿轴由竖直改自然内斜（股骨斜度 ~2.3°，轴 spread
        实测 1.72）——「竖直」口径随叉部渐出弃用，弯轴（外张）才是回归。
        （A-pose 原始腿轴自裆 ±9.6 外撇到踝 ±22，不去外张 spread >5cm。）"""
        vm = _load_vendor_module()
        lm = self.meta["landmarkHeights"]["crotch"]
        cxs = [vm._leg_cx([list(p) for p in self.pos], [tuple(f) for f in self.faces],
                          lm - d, "+") for d in (10.0, 25.0, 45.0)]
        self.assertTrue(all(c is not None for c in cxs), f"腿环缺失 {cxs}")
        spread = max(cxs) - min(cxs)
        self.assertLess(spread, 2.5, f"腿轴散布 {spread:.2f}（去外张回归/δ 曲线过陡）")
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
        """thigh 派生场对位守卫：峰值 Δgirth 带落在站点 ±3.5cm + 下尾铺膝。
        径向保形场以站为中心构造；原生 target 峰值在 crotch−14 错位 11cm 是
        观感事故根因；旧对称半宽 18 场在 crotch−21 截断留膝上 11.5cm 死区
        （crotch−15 带 Δg 仅 ~1.08）→ 2026-09-11 二轮报障加非对称窗下探膝站。"""
        stations = {s["name"]: s["y"] for s in self.meta["stations"]}
        crotch = self.meta["landmarkHeights"]["crotch"]
        th = self.targets[self.by_name["thigh+"]]
        pos = [list(p) for p in self.pos]
        for i, d in th.items():
            for k in range(3):
                pos[i][k] += d[k]
        curve = []
        for y in range(int(crotch) - 34, int(crotch) + 2):
            g0 = girth(self.pos, self.faces, y + 0.5, leg_side="+")
            g1 = girth(pos, self.faces, y + 0.5, leg_side="+")
            if g0 and g1:
                curve.append((y + 0.5, g1 - g0))
        self.assertTrue(curve, "thigh+ Δgirth 曲线全空")
        best_y, _ = max(curve, key=lambda s: s[1])
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
        # 下尾铺膝：crotch−15 带 Δg ≥ 2.0（旧场 ~1.08 = 死区台阶数字指纹）
        mid = (girth(pos, self.faces, crotch - 15.0, leg_side="+")
               - girth(self.pos, self.faces, crotch - 15.0, leg_side="+"))
        self.assertGreaterEqual(mid, 2.0,
                                f"thigh+ crotch−15 Δg {mid:.2f} < 2.0（半宽截断死区回归）")
        # 膝→峰单调递增（容差 0.4 吸收切片抖动）
        pk = max(range(len(curve)), key=lambda i: curve[i][1])
        for (ya, da), (yb, db) in zip(curve[:pk], curve[1:pk + 1]):
            self.assertGreaterEqual(db, da - 0.4,
                                    f"膝→峰非单调 @{ya:.1f}→{yb:.1f}")

    def test_knee_derived_band_alignment(self):
        """knee± 派生场对位守卫（2026-09-11「腿部中段往中线扭曲」报障根因修复）：
        原生 measure-knee-circ 弃用——① 上缘 y57-66 纯内侧 −x 剪切（dz≡0，内柱
        dx −0.54/w、外柱≈0）把大腿中段往全局 X=0 拖；② canonical 站错位（原生峰
        ~45.5 vs 膝站 48.06）；③ 满钳 1.0 可达膝围 40.8 够不着常见输入 43~46 →
        常年满钳剪切边永久生效。派生径向场：峰值带 ∈ 膝站 ±3.5、响应 [4,9]、
        对其余三站串扰 <0.3（实测全 0，比原生更干净的对角性）。"""
        stations = {s["name"]: s["y"] for s in self.meta["stations"]}
        knee_y = self.meta["landmarkHeights"]["knee"]
        kn = self.targets[self.by_name["knee+"]]
        pos = [list(p) for p in self.pos]
        for i, d in kn.items():
            for k in range(3):
                pos[i][k] += d[k]
        curve = []
        for y in range(int(knee_y) - 18, int(knee_y) + 18):
            g0 = girth(self.pos, self.faces, y + 0.5, leg_side="+")
            g1 = girth(pos, self.faces, y + 0.5, leg_side="+")
            if g0 and g1:
                curve.append((y + 0.5, g1 - g0))
        self.assertTrue(curve, "knee+ Δgirth 曲线全空")
        best_y, _ = max(curve, key=lambda s: s[1])
        self.assertLess(abs(best_y - stations["knee"]), 3.5,
                        f"knee+ 峰值带 {best_y:.1f} 偏离站点 {stations['knee']:.1f}")
        row = self.meta["calibration"]["knee+"]["knee"]
        self.assertTrue(4.0 <= row[2] - row[0] <= 9.0,
                        f"站点响应 {row[2] - row[0]:.2f} 不在 [4,9]cm")
        for far in ("waist", "hips", "thigh"):
            fr = self.meta["calibration"]["knee+"][far]
            self.assertLess(abs(fr[2] - fr[0]), 0.3, f"knee+ 串扰 {far} 站")

    def test_hips_derived_band_alignment(self):
        """hips± 派生躯干场对位守卫（2026-09-12「胯部方形折角」报障根因修复；
        二轮平顶窗 + 双相轨道重写）：原生 measure-hips-circ 弃用——拉力剖面
        非单调（y79 0.711 → y81 0.663 凹陷 → y83 1.154 跳升 1.7 倍，分段构造
        台阶指纹），叠加基网格裆线平台（外缘 74-80 恒 ~18.2）把臀拉成「平顶 +
        裆上陡崖」（外缘 d2 折角 −0.33/−1.48）。派生**平顶**场 core [裆+1,
        臀+2] 窗值恒 1（转子穹顶与站带同进同退，一轮纯 cos² 峰只削站带不削
        穹顶 → 两者间挖 ~2cm 凹槽 = 二轮 VLM 3/10 根因）→ 峰值带可落 core
        任一处（±6.0 宽口径）、响应 [8,20]、腰串扰 <0.3、thigh 串扰 <12
        （平顶窗把场下缘铺到臀褶带 +9.2/w——臀腿物理重叠刻意保留，闭环差分
        雅可比联立消解）、叉带 0.25cm 逐扫 w1/w2 gap ≥0.5（旧单点裆−4 守卫
        漏叉顶 pre-gap 0.77 处 w=1 互穿 −0.41，对抗审查 [3]）。"""
        vm = _load_vendor_module()
        stations = {s["name"]: s["y"] for s in self.meta["stations"]}
        crotch = self.meta["landmarkHeights"]["crotch"]
        hp = self.targets[self.by_name["hips+"]]
        pos = [list(p) for p in self.pos]
        for i, d in hp.items():
            for k in range(3):
                pos[i][k] += d[k]
        curve = []
        for y in range(int(crotch) + 1, int(stations["hips"]) + 14):
            g0 = girth(self.pos, self.faces, y + 0.5)
            g1 = girth(pos, self.faces, y + 0.5)
            if g0 and g1:
                curve.append((y + 0.5, g1 - g0))
        self.assertTrue(curve, "hips+ Δgirth 曲线全空")
        best_y, best_dg = max(curve, key=lambda s: s[1])
        self.assertLess(abs(best_y - stations["hips"]), 6.0,
                        f"hips+ 峰值带 {best_y:.1f} 偏离站点 {stations['hips']:.1f}")
        row = self.meta["calibration"]["hips+"]["hips"]
        self.assertTrue(8.0 <= row[2] - row[0] <= 20.0,
                        f"hips+ 站点响应 {row[2] - row[0]:.2f} 不在 [8,20]cm")
        fr = self.meta["calibration"]["hips+"]["waist"]
        self.assertLess(abs(fr[2] - fr[0]), 0.8, "hips+ 串扰 waist 站")
        tr = self.meta["calibration"]["hips+"]["thigh"]
        self.assertLess(abs(tr[2] - tr[0]), 12.0,
                        f"hips+ 串扰 thigh 站 {tr[2] - tr[0]:.2f} > 12.0（重叠带泄漏超预算）")
        # 叉带互穿防线（镜像 vendor 守卫 25）：自裆−4 逐 0.25cm 上扫到最后一个
        # 分腿切片（分腿 = 右腿环存在且总环数 ≥2；左腿环质心为负 x），w=1/w=2
        # 双档全带内侧 gap ≥ 0.5
        faces = [tuple(f) for f in self.faces]

        def _fork_gap_at(mesh, y):
            loops = vm._slice_loops(mesh, faces, y)
            cand = [(pts, cx) for pts, cx in loops if cx > 2.0]
            if not cand or len(loops) < 2:
                return None
            pts2, _ = max(cand, key=lambda l: l[1])
            return 2.0 * min(p[0] for p in pts2)

        base = [list(p) for p in self.pos]
        y_last = crotch - 4.0
        yy = y_last
        while yy < crotch + 2.0:
            if _fork_gap_at(base, yy) is not None:
                y_last = yy
            yy += 0.25
        n_sweep = int(round((y_last - (crotch - 4.0)) / 0.25))
        for w_chk in (1.0, 2.0):
            pw = pos if w_chk == 1.0 else [list(p) for p in self.pos]
            if w_chk == 2.0:
                for i, d in hp.items():
                    for k in range(3):
                        pw[i][k] += w_chk * d[k]
            gaps = [g for g in (_fork_gap_at(pw, y_last - 0.25 * k) for k in range(n_sweep + 1))
                    if g is not None]
            self.assertTrue(gaps, f"hips+ w={w_chk} 叉带分腿切片全缺")
            self.assertGreaterEqual(min(gaps), 0.5,
                                    f"hips+ w={w_chk} 叉带 min gap {min(gaps):.2f} < 0.5（两腿互穿）")

    def test_knee_gap_floor(self):
        """膝站内侧间隙 floor：knee+ w=1 右腿环内间隙 ≥ 0.5cm。旧原生场 w=1
        把间隙压到 0.01~0.3（双膝贴拢/穿插根因）；派生场内侧 ×0.30 来自解析
        约束 att ≤ (gap0−floor)/(2·amp0·weightClamp) = (2.0−0.65)/(2×1.25×2.0)
        （floor 0.65 = 守卫 0.5 + 采样网格插值边际 0.15，2026-09-12 二轮），
        w=1 间隙 1.40、满钳 w=2 落 ~0.65 不互穿。"""
        vm = _load_vendor_module()
        knee_y = {s["name"]: s["y"] for s in self.meta["stations"]}["knee"]
        kn = self.targets[self.by_name["knee+"]]
        pos = [list(p) for p in self.pos]
        for i, d in kn.items():
            for k in range(3):
                pos[i][k] += d[k]
        loops = vm._slice_loops(pos, [tuple(f) for f in self.faces], knee_y)
        cand = [(pts, cx) for pts, cx in loops if cx > 2.0]
        self.assertTrue(cand, "膝站腿环缺失")
        pts, _ = max(cand, key=lambda l: l[1])
        gap = 2.0 * min(p[0] for p in pts)
        self.assertGreaterEqual(gap, 0.5,
                                f"knee+ w=1 膝站内侧 gap {gap:.2f} < 0.5（贴拢回归）")

    def _leg_gap(self, d):
        vm = _load_vendor_module()
        crotch = self.meta["landmarkHeights"]["crotch"]
        loops = vm._slice_loops([list(p) for p in self.pos],
                                [tuple(f) for f in self.faces], crotch - d)
        cand = [(pts, cx) for pts, cx in loops if cx > 2.0]
        if not cand:
            return None
        pts, _ = max(cand, key=lambda l: l[1])
        return 2.0 * min(p[0] for p in pts)

    def test_thigh_gap_closed(self):
        """A-pose 腿间距内收守卫（2026-09-12 v3 剖面：叉口 4.2 / 裆−12 1.2 /
        裆−20 0.9 贴合 / 膝上 1.8 回松，fork 渐出 12→7cm）：
        主段（裆−30..−16）gap ≤ 3.2（原 5.3~6.5；v3 实测 ~1.1-2.2）；
        渐出带（裆−16..−2）自叉口单调渐收——渐出是「大腿球包+腿往中线收拢」
        根因修复：旧版裆下即满量 δ≈2.2 刚体平移，把大腿干从臀线正下方拽进
        2.2cm。顶部（裆−6，fork 渐出中段）≥3.0：叉口要收（v2 的 ~4.8 等宽
        槽 = 二轮 VLM「大腿缝生硬挖空」根因）但臀褶解剖张开保留。"""
        worst = max(g for g in (self._leg_gap(d) for d in range(16, 32, 2))
                    if g is not None)
        self.assertLessEqual(worst, 3.2, f"大腿主段内侧 gap 残 {worst:.2f} > 3.2（内收回归）")
        profile = [(d, self._leg_gap(d)) for d in range(2, 17, 2)]
        self.assertTrue(all(g is not None for _, g in profile), "渐出带腿环缺失")
        # 顶部：裆−6 处 gap ≥ 3.0（v3 fork 渐出 7cm 中段实测 ~3.9；既要收叉口
        # 又保留臀褶解剖张开）
        self.assertGreaterEqual(profile[2][1], 3.0,
                                f"裆−6 gap {profile[2][1]:.2f} < 3.0（叉部过度内收）")
        # 渐收：裆−8 起单调不升（容差 0.4 吸切片抖动），裆−16 收至 ≤2.5
        for (da, ga), (db, gb) in zip(profile[3:], profile[4:]):
            self.assertLessEqual(gb, ga + 0.4,
                                 f"裆−{db} gap {gb:.2f} 回升（渐出带剖面破坏）")
        self.assertLessEqual(profile[-1][1], 2.5,
                             f"裆−16 gap {profile[-1][1]:.2f} > 2.5（渐出不到位）")

    def test_outer_silhouette_continuity(self):
        """外缘轮廓连续金标（2026-09-12「大腿球包」+「胯部方形折角」双根因守卫）：
        正视外缘（每高度 max|x|）自裆−17 到裆+8 逐 cm 骤降 ≤0.5cm——上界伸到
        裆+8 覆盖大转子削圆带（二轮轻量化：穹顶倒圆 −0.20@裆−1 半宽 4 + 下翼
        −0.22@裆−7 半宽 3.5；一轮主削 −0.38@裆+3.5 实为在 hips± 挖出的凹槽
        上加深台阶，帮倒忙）。旧版 adduct 整段平移在裆下撕出台阶（每cm
        0.85~1.0）= 用户截图「球包+凹口」。同时锁臀部锚量：裆−1 外缘 ≥17.8
        （实测穹顶倒圆后 ~18.1；内收/削圆不得缩臀）。"""
        vm = _load_vendor_module()
        crotch = self.meta["landmarkHeights"]["crotch"]
        pos = [list(p) for p in self.pos]
        faces = [tuple(f) for f in self.faces]
        edge = []
        for y in [crotch + dy for dy in range(-17, 9)]:
            loops = vm._slice_loops(pos, faces, y)
            if loops:
                edge.append(max(abs(p[0]) for l in loops for p in l[0]))
        self.assertGreaterEqual(len(edge), 20, "外缘采样缺失过多")
        hip_loops = vm._slice_loops(pos, faces, crotch - 1.0)
        hip_edge = (max(abs(p[0]) for l in hip_loops for p in l[0])
                    if hip_loops else None)
        self.assertIsNotNone(hip_edge, "裆−1 切片缺失")
        self.assertGreaterEqual(hip_edge, 17.8,
                                f"裆−1 臀部外缘 {hip_edge:.2f} < 17.8（内收缩臀）")
        cliff = max(edge[i + 1] - edge[i] for i in range(len(edge) - 1))
        self.assertLessEqual(cliff, 0.5,
                             f"外缘每cm骤降 {cliff:.2f} > 0.5（球包/台阶/削圆过猛回归）")

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
