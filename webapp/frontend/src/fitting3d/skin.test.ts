// SDF 蒙皮金标（2026-09-09：tubeMesh 三管装配体 -> 单张水密隐式蒙皮，
// 本文件承接其绕向/水密金标并加站点围度/支配/解耦不变量）。
// 夹具 165/66A（与 fitting3d.test.ts 同款：waist98/hip86/crotch78/
// knee42/hem0，围 66/90/54/35），关键手工演算：
//   · 臀站支配余量：腿顶环钳位在 84（a=27/6.0161=4.488），y=86 处穹顶
//     sD=√(1−(2/2.5)²)=0.6 → 腿穹顶壁 9.9+0.6×4.488=12.593；骨盆 86 环
//     a=90/5.8997=15.255，两腿场相等 +2.662 → 腿群 smin 值 2.662−kLL/4
//     =2.412 ≥ kPL=0.75（余量 1.662）→ 臀站逐射线 R_skin == pelvis 精确
//     1e-6（换指数 smin / k 抬升即红，兼 smin 族选型回归守卫）
//   · y=79 侧向：腿壁 9.9+a79=9.9+7.564=17.464，骨盆场 +2.946 ≥ kPL →
//     精确 min，R_skin=17.463（emergence 带实测下沿）
//   · thigh 站 y=75：内腿缝中点本被骨盆楔占据（楔 a(75)=8.43，
//     (0,75,0) 场 ≈ −6.58 负——会阴被填带属预期），腿对 smin 谷底在
//     楔底下方：y=70 处 (0,70,0) 场 ≈ +0.39 > 0 不桥接、谷成浅沟
//   · thigh 围度尺则（裆侧回退）：从腿中心 360 射线，首穿 r_exit ≤
//     ring+0.5（融合带表面）取 r_exit，深融向（r_exit 越窗——楔接管带
//     与切向放大首穿）回退取 ring——会阴属骨盆不属于大腿轮廓。实测
//     回退 91/360 方向、围度漂移 +1.95%（漂移由回退带边界 2~4 个切向
//     放大方向主导，对 k 微扰敏感）；**深融向按环回退不计入，融合外凸
//     上界由下方「解耦」两测度金标把守**（2026-09-09 四轮：原
//     maxExcess ≤ k/4 断言系恒真构造，已删）
//   · 解耦双测度（渲染蒙皮 vs 解析并集=碰撞/摆位几何本体）：
//     ①并集表面点法向位移 −F_skin/|∇F_skin| ≤ garmentGap=1.2（实测最坏
//       0.81 @hip75×thigh80 内壁融合带；标准 165/66A 0.23 @楔底 y≈73）；
//     ②轴心/腿心射线首穿−并集末次出射 ≤ 1.2（实测最坏 0.76 @瘦小
//       55/75/40/30 y=75 裆侧；标准 0.49）。原单 k=2 在 165/66A 腿心
//       y=75 θ≈295°（楔前壁×对侧腿前内壁近切向接触带，|∇F|≈0.3）实测
//       +1.66 超 1.2——k/4 只是场值下压上界、非表面位移上界，此即四轮
//       per-pair 融合半径（kPL=0.75/kLL=1.0）的由来
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../types'
import type { BodyGirths } from './bodyProfile'
import { buildMannequin, radiusAt, sectionAt, type Mannequin } from './mannequin'
import { SKIN_PRIOR, SOLVER_PRIOR } from './priors'
import { buildSkinMesh, skinField, tubeSlice, unionField } from './skin'

const BODY: FittingResult['body'] = {
  stations: [
    { key: 'waist', y: 98, girth_finished: 70, per: 'body' },
    { key: 'hip', y: 86, girth_finished: 96, per: 'body' },
    { key: 'crotch', y: 78, girth_finished: null, per: 'body' },
    { key: 'knee', y: 42, girth_finished: 46, per: 'leg' },
    { key: 'hem', y: 0, girth_finished: 36, per: 'leg' },
  ],
  points: {
    front_crotch_vertex: [15, 78],
    back_crotch_vertex: [30, 77.04],
  },
  crotch_drop: 0.96,
  waistband_width: 4,
  waistband_type: 'straight',
  outseam: 102,
}
const GIRTHS = { waist: 66, hip: 90, thigh: 54, knee: 35 }
const GAP = SOLVER_PRIOR.garmentGap

// 通用射线首穿：从 (ox,oy,oz) 沿 (sinθ,0,cosθ) 0.25cm 步进找第一个
// 负→正换号区间再二分 60 次（精度 ~1e-15，粗扫防多根取首根）
function rayHitF(
  f: (x: number, y: number, z: number) => number,
  ox: number, oy: number, oz: number, th: number,
): number {
  const dx = Math.sin(th), dz = Math.cos(th)
  if (f(ox, oy, oz) >= 0) return NaN    // 原点在体外：无首穿
  let rPrev = 0
  for (let r = 0.25; r <= 60; r += 0.25) {
    if (f(ox + dx * r, oy, oz + dz * r) >= 0) {
      let lo = rPrev, hi = r
      for (let it = 0; it < 60; it++) {
        const m = 0.5 * (lo + hi)
        if (f(ox + dx * m, oy, oz + dz * m) < 0) lo = m
        else hi = m
      }
      return 0.5 * (lo + hi)
    }
    rPrev = r
  }
  return NaN
}
const rayHit = (man: Mannequin, ox: number, oy: number, oz: number, th: number) =>
  rayHitF((x, y, z) => skinField(man, x, y, z), ox, oy, oz, th)

// 射线末次出射（并集外轮廓参照）：最后一个负→正换号点的二分根；到 60cm
// 仍为负（不该发生）返回 NaN
function rayLastExitF(
  f: (x: number, y: number, z: number) => number,
  ox: number, oy: number, oz: number, th: number,
): number {
  const dx = Math.sin(th), dz = Math.cos(th)
  if (f(ox, oy, oz) >= 0) return NaN
  let last = NaN, prevNeg = true
  for (let r = 0.25; r <= 60; r += 0.25) {
    const neg = f(ox + dx * r, oy, oz + dz * r) < 0
    if (prevNeg && !neg) {
      let lo = r - 0.25, hi = r
      for (let it = 0; it < 60; it++) {
        const m = 0.5 * (lo + hi)
        if (f(ox + dx * m, oy, oz + dz * m) < 0) lo = m
        else hi = m
      }
      last = 0.5 * (lo + hi)
    }
    prevNeg = neg
  }
  return last
}

// N 射线折线周长（参考=同 N 射线在标定环上的折线，杜绝「平滑周长 vs
// 48 边形」口径混淆——参考值一律现场派生，不硬编码围度数）
function polylineGirth(
  radii: number[], cx: number,
): number {
  let per = 0
  for (let i = 0; i < radii.length; i++) {
    const th0 = (i / radii.length) * Math.PI * 2
    const th1 = ((i + 1) / radii.length) * Math.PI * 2
    per += Math.hypot(
      cx + Math.sin(th1) * radii[(i + 1) % radii.length]
      - cx - Math.sin(th0) * radii[i],
      Math.cos(th1) * radii[(i + 1) % radii.length]
      - Math.cos(th0) * radii[i])
  }
  return per
}

describe('skin SDF 蒙皮', () => {
  const man = buildMannequin(BODY, GIRTHS)

  it('helper 自校：射线二分周长对解析球场 = 2πr ±0.1%', () => {
    // 半径 10 球场（心 (0,40,0)）：y=40 截面圆周长 2π×10=62.83
    const f = (x: number, y: number, z: number) =>
      Math.hypot(x, y - 40, z) - 10
    const N = 360
    const radii: number[] = []
    for (let i = 0; i < N; i++) {
      radii.push(rayHitF(f, 0, 40, 0, (i / N) * Math.PI * 2))
    }
    expect(radii.every((r) => Number.isFinite(r))).toBe(true)
    expect(Math.abs(polylineGirth(radii, 0) - 2 * Math.PI * 10)
      / (2 * Math.PI * 10)).toBeLessThan(0.001)
  })

  it('场符号：体内负、体外正；smin ≤ min 单侧性（蒙皮永不陷并集内）', () => {
    expect(skinField(man, 0, 86, 0)).toBeLessThan(0)      // 臀站骨盆心
    expect(skinField(man, 9.9, 42, 3)).toBeLessThan(0)    // 膝站腿内
    expect(skinField(man, 0, 86, 30)).toBeGreaterThan(0)  // 臀前远场
    expect(skinField(man, 30, 42, 0)).toBeGreaterThan(0)  // 膝外侧远场
    // 单侧性：任意采样点 skinField ≤ unionField（融合只向外鼓；
    // 相等出现在融合窗外精确 min 区）
    let equal = 0
    for (const [x, y, z] of [[0, 86, 0], [9.9, 75, 3], [-4, 75, 5.9],
      [0, 70, 0], [2, 79, 12], [0, 116, 2], [9.9, -8, 0], [-13, 42, -4],
      [0, 73.5, 2], [5, 75, -6], [-9.9, 50, 0]]) {
      expect(skinField(man, x, y, z))
        .toBeLessThanOrEqual(unionField(man, x, y, z) + 1e-12)
      if (Math.abs(skinField(man, x, y, z) - unionField(man, x, y, z)) < 1e-12) {
        equal++
      }
    }
    expect(equal).toBeGreaterThan(0)   // 精确 min 区非空（紧支性成立）
  })

  it('单原语站精确支配（smin 族回归守卫）：36 向 R_skin==radiusAt ±1e-6', () => {
    // 紧支 smin |a−b|≥k 严格 =min：单原语站（他管场 ≥ k 正）蒙皮面与
    // 碰撞面逐点重合。腰 98：腿穹顶止于 84+2.5=86.5，腿场=98−86.5=11.5；
    // 臀 86：腿穹顶场 2.662、腿群值 2.412（余量 1.662，见头注）；膝 42/
    // 脚口 0：骨盆底穹顶止于 73−2.5=70.5，骨盆场 ≥ 28.5。换指数式 smin
    // （全域支撑）或 k 抬升都会在此红——smin 族/半径选型锁死
    const stations: [string, number, 'pelvis' | 'leg', number][] = [
      ['腰 98', 98, 'pelvis', 0],
      ['臀 86', 86, 'pelvis', 0],
      ['膝 42', 42, 'leg', sectionAt(man.legs[1], 42).cx],
      ['脚口 0', 0, 'leg', sectionAt(man.legs[1], 0).cx],
    ]
    for (const [name, y, which, ox] of stations) {
      const tube = which === 'pelvis' ? man.pelvis : man.legs[1]
      for (let i = 0; i < 36; i++) {
        const th = (i / 36) * Math.PI * 2
        const r = rayHit(man, ox, y, 0, th)
        const ref = radiusAt(sectionAt(tube, y), Math.sin(th), Math.cos(th))
        expect(Number.isFinite(r)).toBe(true)
        expect(Math.abs(r - ref)).toBeLessThan(1e-6)
      }
      void name
    }
  })

  it('站点场级围度：单原语站 ±0.5%；thigh ±2%（裆侧环回退尺则）', () => {
    const N = 360
    // 单原语站：参考 = 同 N 射线在标定环上的折线（现场派生）
    const stationCases: [string, number, 'pelvis' | 'leg', number][] = [
      ['腰', 98, 'pelvis', 0],
      ['臀', 86, 'pelvis', 0],
      ['膝', 42, 'leg', sectionAt(man.legs[1], 42).cx],
      ['脚口', 0, 'leg', sectionAt(man.legs[1], 0).cx],
    ]
    for (const [name, y, which, ox] of stationCases) {
      const tube = which === 'pelvis' ? man.pelvis : man.legs[1]
      const skin: number[] = [], ref: number[] = []
      for (let i = 0; i < N; i++) {
        const th = (i / N) * Math.PI * 2
        skin.push(rayHit(man, ox, y, 0, th))
        ref.push(radiusAt(sectionAt(tube, y), Math.sin(th), Math.cos(th)))
      }
      const perS = polylineGirth(skin, ox), perR = polylineGirth(ref, ox)
      expect(Math.abs(perS - perR) / perR)
        .toBeLessThan(SKIN_PRIOR.girthTolStation)
      void name
    }
    // thigh 75：裆侧回退尺则——首穿 ≤ ring+0.5（融合带表面）取首穿，
    // 深融向（楔接管带/切向放大首穿）回退取 ring（会阴属骨盆）。
    // 断言：回退方向数 ≤120（实测 91，钉住裆侧楔接管带弧宽——楔参数
    // 变宽/腿内移即红）+ 围度总漂移 ≤2%（实测 +1.95%）。非回退子集的
    // 逐向外凸上界由构造 ≤0.5 恒成立（2026-09-09 四轮删原恒真断言），
    // 真实融合外凸上界见解耦双测度金标
    const ox = sectionAt(man.legs[1], 75).cx
    const skin: number[] = [], ref: number[] = []
    let fallback = 0
    for (let i = 0; i < N; i++) {
      const th = (i / N) * Math.PI * 2
      const ring = radiusAt(sectionAt(man.legs[1], 75), Math.sin(th), Math.cos(th))
      const exit = rayHit(man, ox, 75, 0, th)
      const r = exit <= ring + 0.5 ? exit : ring
      if (exit > ring + 0.5) fallback++
      skin.push(r)
      ref.push(ring)
    }
    expect(fallback).toBeLessThanOrEqual(120)
    const perS = polylineGirth(skin, ox), perR = polylineGirth(ref, ox)
    expect(Math.abs(perS - perR) / perR).toBeLessThan(SKIN_PRIOR.girthTolThigh)
  })

  it('融合带与内腿缝：y=79 侧向精确 min=17.463；楔下方不桥接', () => {
    // emergence 带：腿壁 9.9+a79=17.464、骨盆场 +2.946≥kPL 精确 min
    // （融合窗外——R_skin==腿壁；上界 +0.1 为数值护栏带）
    const r79 = rayHit(man, 0, 79, 0, Math.PI / 2)
    expect(r79).toBeGreaterThanOrEqual(17.463 - 1e-3)
    expect(r79).toBeLessThanOrEqual(17.463 + 0.1)
    // (0,75,0) 在骨盆楔内（会阴被填带，场负属预期）；楔底穹顶下方
    // 两腿 smin 谷底 > 0：不桥接、谷成浅沟（≈真人腿根）
    expect(skinField(man, 0, 75, 0)).toBeLessThan(0)
    expect(skinField(man, 0, 70, 0)).toBeGreaterThan(0)
  })

  it('MC 水密+外向+质量（标准夹具）', () => {
    const mesh = buildSkinMesh(man)
    const V = mesh.positions.length / 3
    const F = mesh.triangles
    expect(mesh.positions.length).toBe(mesh.normals.length)
    // 位置全有限 + 法线归一
    for (let i = 0; i < mesh.positions.length; i++) {
      expect(Number.isFinite(mesh.positions[i])).toBe(true)
    }
    for (let v = 0; v < V; v++) {
      const n = Math.hypot(mesh.normals[3 * v], mesh.normals[3 * v + 1],
        mesh.normals[3 * v + 2])
      expect(Math.abs(n - 1)).toBeLessThan(1e-6)
    }
    // 无向边恰共享 2 次（水密流形）
    const edges = new Map<number, number>()
    for (let t = 0; t < F; t++) {
      for (let e = 0; e < 3; e++) {
        const i = mesh.indices[3 * t + e], j = mesh.indices[3 * t + (e + 1) % 3]
        const key = i < j ? i * V + j : j * V + i
        edges.set(key, (edges.get(key) ?? 0) + 1)
      }
    }
    expect([...edges.values()].every((c) => c === 2)).toBe(true)
    // 标准夹具拓扑球：V−E+F=2（原 tubeMesh 1c 金标迁移）
    expect(V - edges.size + F).toBe(2)
    // 外法线：逐三角几何法线·∇F > 0（抽样 ≥100；∇F 六点差分）
    const step = Math.max(1, Math.floor(F / 150))
    let sampled = 0
    for (let t = 0; t < F; t += step) {
      const a = 3 * mesh.indices[3 * t], b = 3 * mesh.indices[3 * t + 1]
      const c = 3 * mesh.indices[3 * t + 2]
      const P = mesh.positions
      const ux = P[b] - P[a], uy = P[b + 1] - P[a + 1], uz = P[b + 2] - P[a + 2]
      const vx = P[c] - P[a], vy = P[c + 1] - P[a + 1], vz = P[c + 2] - P[a + 2]
      const fx = uy * vz - uz * vy, fy = uz * vx - ux * vz, fz = ux * vy - uy * vx
      const cx = (P[a] + P[b] + P[c]) / 3
      const cy = (P[a + 1] + P[b + 1] + P[c + 1]) / 3
      const cz = (P[a + 2] + P[b + 2] + P[c + 2]) / 3
      const d = 0.5
      const gx = skinField(man, cx + d, cy, cz) - skinField(man, cx - d, cy, cz)
      const gy = skinField(man, cx, cy + d, cz) - skinField(man, cx, cy - d, cz)
      const gz = skinField(man, cx, cy, cz + d) - skinField(man, cx, cy, cz - d)
      expect(fx * gx + fy * gy + fz * gz).toBeGreaterThan(0)
      sampled++
    }
    expect(sampled).toBeGreaterThanOrEqual(100)
    // 三角预算（预算循环收敛后恒 ≤ maxTriangles）与栅格点预算
    expect(F).toBeLessThanOrEqual(SKIN_PRIOR.maxTriangles)
    let extX = 0, extZ = 0
    for (const tube of [man.pelvis, man.legs[0], man.legs[1]]) {
      for (const r of tube.rings) {
        extX = Math.max(extX, Math.abs(r.cx) + r.a)
        extZ = Math.max(extZ, r.bF, r.bB)
      }
    }
    const mXZ = Math.max(SKIN_PRIOR.blendKPelvisLeg, SKIN_PRIOR.blendKLegLeg) + 2
    const h = mesh.spacing
    const gridPts = (Math.ceil((2 * extX + 2 * mXZ) / h) + 1)
      * (Math.ceil((man.topY + SKIN_PRIOR.capDomePelvisTop + 1.5
        - (man.bottomY - SKIN_PRIOR.capDomeLeg - 1.5)) / h) + 1)
      * (Math.ceil((2 * extZ + 2 * mXZ) / h) + 1)
    expect(gridPts).toBeLessThanOrEqual(450000)
  })

  it('穹顶符号：骨盆顶/楔底/踝，端内负端外正（平端盖彻底消失）', () => {
    const topY = man.topY
    const wedgeY = man.pelvis.rings[man.pelvis.rings.length - 1].y
    const botY = man.bottomY
    const cx = sectionAt(man.legs[1], botY).cx
    expect(skinField(man, 0, topY + SKIN_PRIOR.capDomePelvisTop / 2, 0))
      .toBeLessThan(0)
    expect(skinField(man, 0, topY + SKIN_PRIOR.capDomePelvisTop + 0.1, 0))
      .toBeGreaterThan(0)
    expect(skinField(man, 0, wedgeY - SKIN_PRIOR.capDomePelvisBottom / 2, 0))
      .toBeLessThan(0)
    // 楔底端外取 −L−0.5（−0.1 处与腿场 smin 混合余量仅 ~0.07，取稳点）
    expect(skinField(man, 0, wedgeY - SKIN_PRIOR.capDomePelvisBottom - 0.5, 0))
      .toBeGreaterThan(0)
    expect(skinField(man, cx, botY - SKIN_PRIOR.capDomeLeg / 2, 0))
      .toBeLessThan(0)
    expect(skinField(man, cx, botY - SKIN_PRIOR.capDomeLeg - 0.1, 0))
      .toBeGreaterThan(0)
  })

  // ---- 解耦双测度（2026-09-09 四轮：替换原 surfaceRadius 参照版——
  // 逐管凸支撑取 max 恒 ≥ 并集轮廓，系统性低估外凸；且轴心原点+15° 稀疏
  // 方向永不命中腿心尖峰方向。新参照=解析并集本体，测度①表面点法向位移、
  // 测度②射线首穿−末次出射，断言 ≤ garmentGap=1.2（布料初始摆位在
  // surfaceRadius+gap ≥ 并集轮廓+gap 上，蒙皮越并集 ≤gap 才不吞布料） ----

  it('解耦①并集表面点法向外凸 ≤ garmentGap（标准+病理最坏两夹具）', () => {
    // p 取各管表面（含穹顶缩放截面）且不严格陷入他管（=并集表面点），
    // 外凸 = −F_skin(p)/|∇F_skin(p)|（smin≤min 单侧性保证恒 ≥0）
    const cases: [string, BodyGirths, number, number][] = [
      // 实测：标准 0.23（楔底 y≈73 带）；hip75×thigh80 0.80（粗腿内壁
      // 融合带，四轮 kLL=2 时 1.62 的修复验证位）；滑杆极值 0.20
      ['标准 165/66A', GIRTHS, 0.5, 360],
      ['hip75×thigh80', { waist: 60, hip: 75, thigh: 80, knee: 32 }, 1, 180],
      ['滑杆极值 120/130/80/60', { waist: 120, hip: 130, thigh: 80, knee: 60 },
        1, 180],
    ]
    for (const [name, g, dy, thN] of cases) {
      const m = buildMannequin(BODY, g)
      let worst = 0
      for (const [tube, dHi, dLo] of [
        [m.pelvis, SKIN_PRIOR.capDomePelvisTop, SKIN_PRIOR.capDomePelvisBottom],
        [m.legs[0], SKIN_PRIOR.capDomeLeg, SKIN_PRIOR.capDomeLeg],
        [m.legs[1], SKIN_PRIOR.capDomeLeg, SKIN_PRIOR.capDomeLeg],
      ] as const) {
        const yTop = tube.rings[0].y + dHi
        const yBot = tube.rings[tube.rings.length - 1].y - dLo
        for (let y = yBot; y <= yTop; y += dy) {
          const sl = tubeSlice(tube, y, dHi, dLo)
          if (sl.a < 1e-6) continue
          const st = sectionAt(tube, y)
          for (let i = 0; i < thN; i++) {
            const th = (i / thN) * Math.PI * 2
            const r = radiusAt({ ...st, a: sl.a, bF: sl.bF, bB: sl.bB },
              Math.sin(th), Math.cos(th))
            if (!(r > 0)) continue
            const px = sl.cx + r * Math.sin(th), pz = r * Math.cos(th)
            // p 在本管表面上（本管场≈0），并集场 <−1e-6 即严格陷入他管
            // （=并集内部点，非并集表面），跳过
            if (unionField(m, px, y, pz) < -1e-6) continue
            const f0 = skinField(m, px, y, pz)
            const d = 0.5
            const gx = (skinField(m, px + d, y, pz)
              - skinField(m, px - d, y, pz)) / (2 * d)
            const gy = (skinField(m, px, y + d, pz)
              - skinField(m, px, y - d, pz)) / (2 * d)
            const gz = (skinField(m, px, y, pz + d)
              - skinField(m, px, y, pz - d)) / (2 * d)
            const g = Math.hypot(gx, gy, gz)
            if (g < 1e-6) continue
            worst = Math.max(worst, -f0 / g)
          }
        }
      }
      expect(worst).toBeLessThanOrEqual(GAP)
      void name
    }
  })

  it('解耦②射线首穿−并集末次出射 ≤ garmentGap（轴心+双腿心，1° 向）', () => {
    // 实测最坏：标准 0.49 @y72 轴心裆前；瘦小 55/75/40/30 0.76 @y75
    // 腿心裆侧（原单 k=2 同口径 1.66 @165/66A 腿心 y75——四轮修复位）
    const cases: [string, BodyGirths, number[]][] = [
      ['标准 165/66A', GIRTHS, [70, 71, 72, 73, 74, 75, 76, 78, 79, 81, 84]],
      ['瘦小 55/75/40/30', { waist: 55, hip: 75, thigh: 40, knee: 30 },
        [72, 73, 74, 75, 76, 77, 78]],
    ]
    for (const [name, g, heights] of cases) {
      const m = buildMannequin(BODY, g)
      let worst = -Infinity, covered = 0
      for (const y of heights) {
        const cxs = [0, sectionAt(m.legs[0], y).cx, sectionAt(m.legs[1], y).cx]
        for (const ox of cxs) {
          for (let i = 0; i < 360; i++) {
            const th = (i / 360) * Math.PI * 2
            const s = rayHit(m, ox, y, 0, th)
            const u = rayLastExitF(
              (x, yy, z) => unionField(m, x, yy, z), ox, y, 0, th)
            if (!Number.isFinite(s) || !Number.isFinite(u)) continue
            covered++
            worst = Math.max(worst, s - u)
          }
        }
      }
      expect(covered).toBeGreaterThanOrEqual(500)   // 覆盖非空
      expect(worst).toBeLessThanOrEqual(GAP)
      void name
    }
  }, 30000)

  it('边界格恒正（bbox 闭合前提）', () => {
    // bbox 界定公式复刻：X/Z 全环极值外扩 max(kPL,kLL)+2；Y 上下各扩
    // 穹顶长+1.5。边界面场恒正（实测最小值 = Y 边距 1.5，穹顶 cap 下界恰触）
    let extX = 0, extZ = 0
    for (const tube of [man.pelvis, man.legs[0], man.legs[1]]) {
      for (const r of tube.rings) {
        extX = Math.max(extX, Math.abs(r.cx) + r.a)
        extZ = Math.max(extZ, r.bF, r.bB)
      }
    }
    const m = Math.max(SKIN_PRIOR.blendKPelvisLeg, SKIN_PRIOR.blendKLegLeg) + 2
    const xMin = -extX - m, xMax = extX + m, zMin = -extZ - m, zMax = extZ + m
    const yMin = man.bottomY - (SKIN_PRIOR.capDomeLeg + 1.5)
    const yMax = man.topY + (SKIN_PRIOR.capDomePelvisTop + 1.5)
    for (let t = 0; t <= 50; t++) {
      const q = t / 50
      const x = xMin + (xMax - xMin) * q
      const z = zMin + (zMax - zMin) * q
      const y = yMin + (yMax - yMin) * q
      for (const v of [
        skinField(man, x, yMin, z), skinField(man, x, yMax, z),
        skinField(man, xMin, y, z), skinField(man, xMax, y, z),
        skinField(man, x, y, zMin), skinField(man, x, y, zMax),
      ]) {
        expect(v).toBeGreaterThan(0)
      }
    }
  })
})

describe('skin 病理/极端体型（优雅降级，复用入口守卫夹具集）', () => {
  const withStations = (
    over: Partial<Record<string, number>>,
    extra: FittingResult['body']['stations'] = [],
  ): FittingResult['body'] => ({
    ...BODY,
    stations: [
      ...BODY.stations.map((s) =>
        s.key in over ? { ...s, y: over[s.key]! } : s),
      ...extra,
    ],
  })
  const cases: [string, FittingResult['body'], BodyGirths][] = [
    ['胖腰粗腿 130/70/90（放弃上插）', BODY,
      { waist: 130, hip: 70, thigh: 90, knee: 35 }],
    ['hip75×thigh80', BODY, { waist: 60, hip: 75, thigh: 80, knee: 32 }],
    ['hip130 缺 thigh', BODY, { waist: 100, hip: 130, knee: 44 }],
    ['crotch=88 clamp', withStations({ crotch: 88 }), GIRTHS],
    ['thigh@crotch 重复站', withStations({},
      [{ key: 'thigh', y: 78, girth_finished: null, per: 'leg' }]), GIRTHS],
    ['滑杆上限 120/130/80/60', BODY,
      { waist: 120, hip: 130, thigh: 80, knee: 60 }],
  ]
  for (const [name, body, g] of cases) {
    it(`${name}：不抛、有限、水密（边恰共享 2）+ 预算循环收敛`, () => {
      const m = buildMannequin(body, g)
      const mesh = buildSkinMesh(m)   // 不抛
      const V = mesh.positions.length / 3
      for (let i = 0; i < mesh.positions.length; i++) {
        expect(Number.isFinite(mesh.positions[i])).toBe(true)
      }
      const edges = new Map<number, number>()
      for (let t = 0; t < mesh.triangles; t++) {
        for (let e = 0; e < 3; e++) {
          const i = mesh.indices[3 * t + e], j = mesh.indices[3 * t + (e + 1) % 3]
          const key = i < j ? i * V + j : j * V + i
          edges.set(key, (edges.get(key) ?? 0) + 1)
        }
      }
      expect([...edges.values()].every((c) => c === 2)).toBe(true)
      // 预算循环收敛（单次 ×1.15 重跑不闭合：滑杆上限单档后仍 32780
      // >30000，循环逐档放粗保证恒回预算内——2026-09-09 四轮）
      expect(mesh.triangles).toBeLessThanOrEqual(SKIN_PRIOR.maxTriangles)
      // 放弃上插的降级体型：腿顶穹顶在 crotch 上方侧伸 ~1cm 融成大转子
      // 凸（smin 自动处理分叉），拓扑可能非球（不钉 V−E+F）
      expect(mesh.triangles).toBeGreaterThan(0)
    })
  }
})
