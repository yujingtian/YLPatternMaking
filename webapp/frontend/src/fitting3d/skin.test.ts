// SDF 蒙皮金标（2026-09-09：tubeMesh 三管装配体 -> 单张水密隐式蒙皮，
// 本文件承接其绕向/水密金标并加站点围度/支配/解耦不变量；2026-09-10
// 人台人体化后锚值随并集重校）。
// 夹具 165/66A（与 fitting3d.test.ts 同款：waist98/hip86/crotch78/
// knee42/hem0，围 66/90/54/35），关键实测/演算：
//   · 臀站支配余量：腿顶头带环在 83（穹顶止 85.5），y=86 腿场 ≈ +0.5、
//     腿群 smin ≈ 0.35，骨盆 86 环 a=W_h=15.703（四轮 bias 标定）场
//     −15.703 → |差| ≥ kPL 精确 min → 臀站逐射线 R_skin == pelvis 精确
//     1e-6（换指数 smin / k 抬升即红，兼 smin 族选型回归守卫）
//   · y=79 侧向：盆壁 a=14.902（五轮b 填充锚下沉后盆壁仍主导），
//     骨盆场 ≥ kPL → 精确 min，R_skin==腿壁（emergence 带腿外缘接管）
//   · 腿间缝隙（五轮：旧 68~78 大腿接触带已废，过零锚上移 y=73）：
//     (0,75,0) 在楔内场负（会阴被填带）；(0,72,0) 过零锚下轴带场已
//     转正（断言点离分离点 ≥0.5）；(0,66,0) 中腿缝 2×2.0 稳可辨——
//     内腿缝浅沟（≈真人腿根形态）
//   · thigh 围度尺则（裆侧回退）：从腿中心 360 射线，首穿 r_exit ≤
//     ring+0.5（融合带表面）取 r_exit，深融向（r_exit 越窗——楔接管带
//     与切向放大首穿）回退取 ring——会阴属骨盆不属于大腿轮廓。实测
//     回退 87/360 方向、围度漂移 +1.82%（漂移由回退带边界 2~4 个切向
//     放大方向主导，对 k 微扰敏感）；**深融向按环回退不计入，融合外凸
//     上界由下方「解耦」两测度金标把守**（2026-09-09 四轮：原
//     maxExcess ≤ k/4 断言系恒真构造，已删）
//   · 解耦双测度（渲染蒙皮 vs 解析并集=碰撞/摆位几何本体）：
//     ①并集表面点法向位移 −F_skin/|∇F_skin| ≤ garmentGap=1.2。2026-09-10
//       人体化后最坏 1.065 @(0,68,0) 接触带出口（kLL=1.0 时 1.774 超
//       预算——大腿接触带使两内侧壁切向擦碰、|∇F|≈0.14 放大 k/4，
//       kLL 1.0→0.6 即此由来；①是全局最终裁决）
//     ②腿心/轴心射线首穿−并集末次出射 ≤ 1.2。轴心原点仅 y≥70（会阴
//       楔区）：y<70 的轴心 θ≈0° 射线落在设计接触带的腿间凹谷（并集
//       凹区，布料按凸支撑 surfaceRadius+gap 摆位永不进谷，谷内外凸由
//       ①把守）；腿心原点全域（含接触带出口 66-69，实测 0.000）
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../types'
import type { BodyGirths } from './bodyProfile'
import { buildMannequin, radiusAt, sectionAt, type Mannequin } from './mannequin'
import { FOOT_PRIOR, SKIN_PRIOR, SOLVER_PRIOR } from './priors'
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
    // 腿心 x 锚 = 各高度实测 cx（逐环派生，勿写字面量——改梯子即失联）
    const cx75 = sectionAt(man.legs[1], 75).cx     // 7.396
    const cx42 = sectionAt(man.legs[1], 42).cx     // 6.951
    expect(skinField(man, 0, 86, 0)).toBeLessThan(0)      // 臀站骨盆心
    expect(skinField(man, cx42, 42, 3)).toBeLessThan(0)   // 膝站腿内
    expect(skinField(man, 0, 86, 30)).toBeGreaterThan(0)  // 臀前远场
    expect(skinField(man, 30, 42, 0)).toBeGreaterThan(0)  // 膝外侧远场
    // 单侧性：任意采样点 skinField ≤ unionField（融合只向外鼓；
    // 相等出现在融合窗外精确 min 区）
    let equal = 0
    for (const [x, y, z] of [[0, 86, 0], [cx75, 75, 3], [-4, 75, 5.9],
      [0, 70, 0], [2, 79, 12], [0, 116, 2],
      [sectionAt(man.legs[1], -8).cx, -8, 0], [-13, 42, -4],
      [0, 73.5, 2], [5, 75, -6], [-sectionAt(man.legs[1], 50).cx, 50, 0]]) {
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
    // 碰撞面逐点重合。腰 98：腿穹顶止于 83+2.5=85.5，腿场=98−85.5=12.5；
    // 臀 86：腿穹顶场 ≈ +0.5、腿群 smin ≈ 0.35（余量见头注）；膝 42/
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
    // 断言：回退方向数 ≤120（实测 87，钉住裆侧楔接管带弧宽——楔参数
    // 变宽/腿内移即红）+ 围度总漂移 ≤2%（实测 +1.82%）。非回退子集的
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

  it('融合带与内腿缝：y=79 侧向 min=14.902；分离带轴心不桥接', () => {
    // emergence 带：五轮b 填充锚下沉（hip−5+0.995）后 79 仍是盆壁主导
    // （盆 a 14.902 > 腿 |cx|+a 14.86——五轮c 小腹降峰保围微调 −0.014，
    // 骨盆场 ≥ kPL 精确 min；上界 +0.2 收 smin 融合外凸，实测 ≈+0.16
    // < garmentGap 预算）
    const r79 = rayHit(man, 0, 79, 0, Math.PI / 2)
    expect(r79).toBeGreaterThanOrEqual(14.902 - 1e-3)
    expect(r79).toBeLessThanOrEqual(14.902 + 0.2)
    // (0,75,0) 在骨盆楔内（会阴被填带，场负属预期）；五轮缝隙带：过零
    // 锚 yGapOpen=73 下轴带场转正（72 断言点离分离点 ≥0.5、留穹顶/桥接
    // 余量），中腿 66 缝 2×2.0——smin 谷底 > 0 不桥接、缝成浅沟
    expect(skinField(man, 0, 75, 0)).toBeLessThan(0)
    expect(skinField(man, 0, 72, 0)).toBeGreaterThan(0)
    expect(skinField(man, 0, 66, 0)).toBeGreaterThan(0)
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
    // 三角预算（预算循环收敛后恒 ≤ maxTriangles）与栅格点预算（公式
    // 镜像 marchOnce bbox：脚盒 AABB 含盒心偏移 |c|——漏 c 即脚尖出界，
    // mXZ = K_FAR+2 含 kLF；yMin = bottomY−1.5——脚平底贴地无腿穹顶下延）
    expect(F).toBeLessThanOrEqual(SKIN_PRIOR.maxTriangles)
    let extX = 0, extZ = 0
    for (const tube of [man.pelvis, man.legs[0], man.legs[1]]) {
      for (const r of tube.rings) {
        extX = Math.max(extX, Math.abs(r.cx) + r.a)
        extZ = Math.max(extZ, r.bF, r.bB)
      }
    }
    for (const f of man.feet) {
      const ca = Math.abs(Math.cos(f.yaw)), sa = Math.abs(Math.sin(f.yaw))
      for (const b of f.boxes) {
        const ex = Math.abs(b.c[0]) + b.h[0] + f.round
        const ez = Math.abs(b.c[2]) + b.h[2] + f.round
        extX = Math.max(extX, Math.abs(f.origin[0]) + ex * ca + ez * sa)
        extZ = Math.max(extZ, Math.abs(f.origin[2]) + ex * sa + ez * ca)
      }
    }
    const mXZ = Math.max(SKIN_PRIOR.blendKPelvisLeg, SKIN_PRIOR.blendKLegLeg,
      SKIN_PRIOR.blendKLegFoot) + 2
    const h = mesh.spacing
    const gridPts = (Math.ceil((2 * extX + 2 * mXZ) / h) + 1)
      * (Math.ceil((man.topY + SKIN_PRIOR.capDomePelvisTop + 1.5
        - (man.bottomY - 1.5)) / h) + 1)
      * (Math.ceil((2 * extZ + 2 * mXZ) / h) + 1)
    expect(gridPts).toBeLessThanOrEqual(450000)
  })

  it('穹顶符号：骨盆顶/楔底端内负端外正 + 脚平底贴地（平端盖彻底消失）', () => {
    const topY = man.topY
    const wedgeY = man.pelvis.rings[man.pelvis.rings.length - 1].y
    const botY = man.bottomY
    expect(skinField(man, 0, topY + SKIN_PRIOR.capDomePelvisTop / 2, 0))
      .toBeLessThan(0)
    expect(skinField(man, 0, topY + SKIN_PRIOR.capDomePelvisTop + 0.1, 0))
      .toBeGreaterThan(0)
    expect(skinField(man, 0, wedgeY - SKIN_PRIOR.capDomePelvisBottom / 2, 0))
      .toBeLessThan(0)
    // 楔底端外（−L−0.5）取 z=+6 偏轴点：中轴线 (0,70,0) 落设计大腿
    // 接触带（68~78，腿贴腿桥接场负属预期），z=6 已出两腿内壁与楔穹
    // 侧向范围（实测 +1.59），楔底平端盖消失断言仍有效
    expect(skinField(man, 0, wedgeY - SKIN_PRIOR.capDomePelvisBottom - 0.5, 6))
      .toBeGreaterThan(0)
    // 脚（2026-09-10 第四轮替代旧踝穹顶断言——腿穹顶藏进脚盒 smin 融合，
    // 独立可见的端部语义换成脚平底贴地）：后盒核底 = groundY、圆角面恰
    // 触地——脚体中高断面内负、地面下 0.5 正（无任何原语沉入地下；
    // bbox yMin=bottomY−1.5 兜住）。z=2 取后盒 z 跨度中部（yaw 7° 旋转
    // 下仍远离 ±5.5 端缘）
    const fxAbs = Math.abs(sectionAt(man.legs[1], botY).cx)
    expect(skinField(man, fxAbs, FOOT_PRIOR.groundY + 2.5, 2)).toBeLessThan(0)
    expect(skinField(man, fxAbs, FOOT_PRIOR.groundY - 0.5, 2)).toBeGreaterThan(0)
  })

  // ---- 解耦双测度（2026-09-09 四轮：替换原 surfaceRadius 参照版——
  // 逐管凸支撑取 max 恒 ≥ 并集轮廓，系统性低估外凸；且轴心原点+15° 稀疏
  // 方向永不命中腿心尖峰方向。新参照=解析并集本体，测度①表面点法向位移、
  // 测度②射线首穿−末次出射，断言 ≤ garmentGap=1.2（布料初始摆位在
  // surfaceRadius+gap ≥ 并集轮廓+gap 上，蒙皮越并集 ≤gap 才不吞布料） ----

  it('解耦①并集表面点法向外凸 ≤ garmentGap（标准+病理最坏两夹具）', () => {
    // p 取各管表面（含穹顶缩放截面）且不严格陷入他管（=并集表面点），
    // 外凸 = −F_skin(p)/|∇F_skin(p)|（smin≤min 单侧性保证恒 ≥0）。
    // 实测（2026-09-10 人体化+kLL=0.6）：三夹具最坏同为 1.065
    // @(0,68,0) 大腿接触带出口（kLL=1.0 时 1.774——两内侧壁切向擦碰
    // |∇F|≈0.14 放大，kLL 降 0.6 的直接动因）；①是全局最终裁决
    const cases: [string, BodyGirths, number, number][] = [
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
  }, 30000)

  it('解耦②射线首穿−并集末次出射 ≤ garmentGap（腿心全域+轴心楔区，1° 向）', () => {
    // 作用域（2026-09-10 五轮缝隙带重校）：腿心原点全域（66-69 旧接触带
    // 出口已随开缝消失，实测 0.000）；轴心原点 y≥70 含新过零锚 73 附近
    // （72-74 段 smin 谷桥场仍接近 0——缝刚打开、两内侧壁切向贴近）；
    // 70 以下轴心场已转正、smin=严格 min、自动安全。原单 k=2 修复位：
    // 165/66A 腿心 y75 θ≈295° +1.66（四轮）
    const cases: [string, BodyGirths, number[], number[]][] = [
      // [名, 围, 腿心 heights, 轴心 heights]
      ['标准 165/66A', GIRTHS,
        [66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 78, 79, 81, 84],
        [70, 72, 73, 74, 76, 78, 79, 81, 84]],
      ['瘦小 55/75/40/30', { waist: 55, hip: 75, thigh: 40, knee: 30 },
        [70, 72, 74, 75, 76, 77, 78], [72, 74, 76, 78]],
    ]
    for (const [name, g, legYs, axisYs] of cases) {
      const m = buildMannequin(BODY, g)
      let worst = -Infinity, covered = 0
      for (const y of legYs) {
        for (const ox of [sectionAt(m.legs[0], y).cx, sectionAt(m.legs[1], y).cx]) {
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
      for (const y of axisYs) {
        for (let i = 0; i < 360; i++) {
          const th = (i / 360) * Math.PI * 2
          const s = rayHit(m, 0, y, 0, th)
          const u = rayLastExitF(
            (x, yy, z) => unionField(m, x, yy, z), 0, y, 0, th)
          if (!Number.isFinite(s) || !Number.isFinite(u)) continue
          covered++
          worst = Math.max(worst, s - u)
        }
      }
      expect(covered).toBeGreaterThanOrEqual(500)   // 覆盖非空
      expect(worst).toBeLessThanOrEqual(GAP)
      void name
    }
    // 90s：单跑 ~25s，全量并行 CPU 争抢下文件级可到 ~60s（30s 预算曾致
    // 间歇超时假红——几何断言全过，纯 harness 预算；integration 60s 同性质）
  }, 90000)

  it('边界格恒正（bbox 闭合前提）', () => {
    // bbox 界定公式复刻（与 marchOnce 同式，含脚盒 AABB——盒心偏移 |c|
    // 不可漏）：X/Z 极值外扩 K_FAR+2；Y 上扩穹顶长+1.5、下扩 1.5（脚平底
    // 贴地无穹顶）。边界面场恒正（实测最小值 = Y 边距 1.5，穹顶 cap 下界恰触）
    let extX = 0, extZ = 0
    for (const tube of [man.pelvis, man.legs[0], man.legs[1]]) {
      for (const r of tube.rings) {
        extX = Math.max(extX, Math.abs(r.cx) + r.a)
        extZ = Math.max(extZ, r.bF, r.bB)
      }
    }
    for (const f of man.feet) {
      const ca = Math.abs(Math.cos(f.yaw)), sa = Math.abs(Math.sin(f.yaw))
      for (const b of f.boxes) {
        const ex = Math.abs(b.c[0]) + b.h[0] + f.round
        const ez = Math.abs(b.c[2]) + b.h[2] + f.round
        extX = Math.max(extX, Math.abs(f.origin[0]) + ex * ca + ez * sa)
        extZ = Math.max(extZ, Math.abs(f.origin[2]) + ex * sa + ez * ca)
      }
    }
    const m = Math.max(SKIN_PRIOR.blendKPelvisLeg, SKIN_PRIOR.blendKLegLeg,
      SKIN_PRIOR.blendKLegFoot) + 2
    const xMin = -extX - m, xMax = extX + m, zMin = -extZ - m, zMax = extZ + m
    const yMin = man.bottomY - 1.5
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
    ['胖腰粗腿 130/70/90（cx 恒正降级）', BODY,
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
      // 新口径无容纳降级路径：粗腿体型的外缘超标是「腿确实比盆宽」的
      // 诚实降级（gap 下限绑定 cx>a−1.5 恒正），smin 自动融合分叉
      expect(mesh.triangles).toBeGreaterThan(0)
    })
  }
})
