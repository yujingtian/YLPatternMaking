// M0 静态摆位金标（二期复活，方案 .claude/plans/3d试穿二期-复活.md 里程碑）：
// y-warp 过点/外推/单调/失配抛错；布料网格拓扑（三角化面积比 ≥99%、
// 最小角 >15°、边界环聚合段）；支撑半径场（双线性、θ 环绕、y 夹取）；
// 摆位镜像对称（x 中位差 <0.1cm）与穿透（真产物人台 <50 点、最深 <2cm）；
// 11 缝计数；直腰头布片（pin=腰头全体、对账）/弯腰头回退（视觉环带+
// 腰口 pin）；育克装配链（16 缝：侧缝链式拆分、腰缝后侧改育克上口、
// 育克下口缝后片上口）与数据一致性守卫。
// 夹具 = 引擎 payload（fixture_fitting.json 默认直腰头 / fixture_fitting_yoke.json
// back_yoke 开启，引擎 build_fitting_payload 直出 + 补 ok/warnings）；
// 人台 = public/bodymesh 真产物（bodymesh.test.ts 同盘读法 + landmarkHeights）。
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../types'
import { bodyLandmarksOf, buildWarp } from './align'
import { buildClothMesh, runIndexAt } from './mesh'
import type { ClothMesh, EdgeRun } from './mesh'
import {
  BodyField, buildBodyField, placePoint, penetrationStats,
} from './placement'
import { buildGarment, buildWaistRing } from './seams'
import type { Garment, GarmentMeshes } from './seams'
import { checkBandLength } from './band'
import { MESH_PRIOR, SOLVER_PRIOR } from './priors'

const HERE = import.meta.dirname   // src/fitting3d/garment

const result: FittingResult = JSON.parse(
  readFileSync(`${HERE}/fixture_fitting.json`, 'utf8'))
const resultYoke: FittingResult = JSON.parse(
  readFileSync(`${HERE}/fixture_fitting_yoke.json`, 'utf8'))

// ---- 真产物人台（w=0） ----
function loadBodyFromDisk(): {
  positions: Float32Array; indices: Uint32Array;
  landmarks: Record<string, number>;
  stations: Record<string, { y: number; per: 'body' | 'leg' }>;
} {
  const meta = JSON.parse(
    readFileSync(`${HERE}/../../../public/bodymesh/targets.json`, 'utf8'))
  const bytes = readFileSync(`${HERE}/../../../public/bodymesh/base.bin`)
  // 布局见 bin.ts：<III> V F T + V 顶点 + F 三角 + T 场（little-endian）
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  let off = 0
  const u32 = () => { const x = dv.getUint32(off, true); off += 4; return x }
  const f32 = () => { const x = dv.getFloat32(off, true); off += 4; return x }
  const V = u32(), F = u32(); u32()
  const positions = new Float32Array(3 * V)
  for (let i = 0; i < positions.length; i++) positions[i] = f32()
  const indices = new Uint32Array(3 * F)
  for (let i = 0; i < indices.length; i++) indices[i] = u32()
  const stations: Record<string, { y: number; per: 'body' | 'leg' }> = {}
  for (const s of meta.stations) stations[s.name] = { y: s.y, per: s.per }
  return { positions, indices, landmarks: meta.landmarkHeights, stations }
}

function buildOnBody(override?: (r: FittingResult) => FittingResult): {
  garment: Garment; field: BodyField;
  meshes: GarmentMeshes;
} {
  const body = loadBodyFromDisk()
  const r = override ? override(result) : result
  const asset = {
    ...body, height: 120.64, heightInfo: { baseCm: 167, plusCm: 72, minusCm: -36 },
    targets: [],
  } as Parameters<typeof bodyLandmarksOf>[0]
  const warp = buildWarp(r.body.stations, bodyLandmarksOf(asset))
  const field = buildBodyField(body.positions, body.indices)
  const yokePiece = r.pieces.find((p) => p.key === 'back_yoke')
  const meshes: GarmentMeshes = {
    front: buildClothMesh(r.pieces.find((p) => p.key === 'front_piece')!),
    back: buildClothMesh(r.pieces.find((p) => p.key === 'back_piece')!),
    ...(yokePiece ? { yoke: buildClothMesh(yokePiece) } : {}),
  }
  return { garment: buildGarment(meshes, r, warp, field), field, meshes }
}

describe('align：y-warp 分段线性（纸样高 -> 人台高）', () => {
  // 手工锚（夹具站高 0/42/78/86/98 → 人台地标；thigh 站 78 与 crotch 同高
  // 去重留 crotch）
  const lm = { ankle: 8, knee: 45, crotch: 79, hip: 90, waist: 104 }
  const stations = result.body.stations

  it('节点精确过点（站名对齐表显式写死，勿按名匹配）', () => {
    const warp = buildWarp(stations, lm)
    expect(warp(0)).toBeCloseTo(8, 9)     // hem ↔ ankle
    expect(warp(42)).toBeCloseTo(45, 9)   // knee ↔ knee
    expect(warp(78)).toBeCloseTo(79, 9)   // crotch ↔ crotch（thigh 同高去重）
    expect(warp(86)).toBeCloseTo(90, 9)   // hip ↔ hip
    expect(warp(98)).toBeCloseTo(104, 9)  // waist ↔ waist
  })

  it('越界按首尾段斜率外推（腰头上沿 > 腰站、低腰 < 脚口站）', () => {
    const warp = buildWarp(stations, lm)
    // 上外推：98→104 段斜率 (104-90)/(98-86)
    expect(warp(102)).toBeCloseTo(104 + 4 * (14 / 12), 9)
    // 下外推：0→42 段斜率 (45-8)/42
    expect(warp(-5)).toBeCloseTo(8 - 5 * (37 / 42), 9)
  })

  it('全域单调；节点不足 / 地标错配必须炸', () => {
    const warp = buildWarp(stations, lm)
    let prev = -Infinity
    for (let y = -10; y <= 110; y += 5) {
      const v = warp(y)
      expect(v).toBeGreaterThan(prev)
      prev = v
    }
    expect(() => buildWarp([stations[0]], lm)).toThrow(/不足 2/)
    expect(() => buildWarp(stations, { ...lm, knee: 5 })).toThrow(/非单调/)
  })
})

describe('mesh：裁片三角化拓扑', () => {
  const piece = result.pieces.find((p) => p.key === 'front_piece')!
  const mesh = buildClothMesh(piece)

  it('三角化合法：索引在域、无 NaN、质心过滤后无外溢三角形', () => {
    const N = mesh.xy.length / 2
    expect(mesh.tri.length % 3).toBe(0)
    expect(mesh.tri.length).toBeGreaterThan(0)
    for (let i = 0; i < mesh.tri.length; i++) {
      expect(mesh.tri[i]).toBeLessThan(N)
    }
    for (let i = 0; i < mesh.xy.length; i++) {
      expect(Number.isFinite(mesh.xy[i])).toBe(true)
    }
  })

  it('面积比 ≥99%（Shoelace 边界环 vs Σ三角形）', () => {
    let area2 = 0
    for (let i = 0; i < mesh.loop.length; i++) {
      const a = mesh.loop[i], b = mesh.loop[(i + 1) % mesh.loop.length]
      area2 += mesh.xy[2 * a] * mesh.xy[2 * b + 1]
        - mesh.xy[2 * b] * mesh.xy[2 * a + 1]
    }
    const polyArea = Math.abs(area2) / 2
    let triArea = 0
    for (let t = 0; t < mesh.tri.length; t += 3) {
      const a = mesh.tri[t] * 2, b = mesh.tri[t + 1] * 2, c = mesh.tri[t + 2] * 2
      triArea += Math.abs(
        (mesh.xy[b] - mesh.xy[a]) * (mesh.xy[c + 1] - mesh.xy[a + 1])
        - (mesh.xy[c] - mesh.xy[a]) * (mesh.xy[b + 1] - mesh.xy[a + 1])) / 2
    }
    expect(polyArea).toBeGreaterThan(100)          // 前片 ~几百 cm²
    expect(triArea / polyArea).toBeGreaterThanOrEqual(0.99)
  })

  it('最小角：内部三角形 >15°；边界细长三角形为旧链原样行为', () => {
    // 实测（fixture）：细长三角形全部贴边界（front 39/2421、back 68/2737）
    // ——边界弧长重采样点近共线 + Delaunay 的固有产物，旧链原样复活不修；
    // 只把住内部栅格三角形质量与无精确退化（无重复顶点/零长边）。
    const loopSet = new Set(mesh.loop)
    let minInterior = Infinity
    let zeroEdge = 0
    for (let t = 0; t < mesh.tri.length; t += 3) {
      const v = [mesh.tri[t], mesh.tri[t + 1], mesh.tri[t + 2]]
      const onLoop = v.some((i) => loopSet.has(i))
      for (let e = 0; e < 3; e++) {
        const i = v[e], j = v[(e + 1) % 3]
        const len = Math.hypot(mesh.xy[2 * j] - mesh.xy[2 * i],
          mesh.xy[2 * j + 1] - mesh.xy[2 * i + 1])
        if (len < 1e-9) zeroEdge++
      }
      if (onLoop) continue
      for (let e = 0; e < 3; e++) {
        const p = v.map((i) => [mesh.xy[2 * i], mesh.xy[2 * i + 1]])
        const a = p[(e + 1) % 3], b = p[e], c = p[(e + 2) % 3]
        const u = [a[0] - b[0], a[1] - b[1]], v2 = [c[0] - b[0], c[1] - b[1]]
        const cos = (u[0] * v2[0] + u[1] * v2[1])
          / (Math.hypot(u[0], u[1]) * Math.hypot(v2[0], v2[1]) || 1)
        minInterior = Math.min(minInterior,
          Math.acos(Math.max(-1, Math.min(1, cos))))
      }
    }
    expect(zeroEdge).toBe(0)
    expect(minInterior).toBeGreaterThan((15 * Math.PI) / 180)
  })

  it('同名边聚合段（side ×3 分段合一）与 runIndexAt 端点', () => {
    const side = mesh.runs.find((r) => r.name === 'side')!
    const sideEdges = piece.edges.filter((e) => e.name === 'side')
    expect(sideEdges.length).toBe(3)
    expect(side.length).toBeCloseTo(
      sideEdges.reduce((a, e) => a + e.length, 0), 6)
    expect(runIndexAt(side, 0)).toBe(side.indices[0])
    expect(runIndexAt(side, 1)).toBe(side.indices[side.indices.length - 1])
    const waist = mesh.runs.find((r) => r.role === 'top_chain')!
    expect(waist.name).toBe('waist')
  })
})

describe('placement：支撑半径场与摆位', () => {
  it('BodyField：行双线性 + y 夹取 + θ 环形回绕', () => {
    const rows = 10, bins = 8, rowStep = 1
    const table = new Float32Array(rows * bins)
    for (let r = 0; r < rows; r++) {
      for (let b = 0; b < bins; b++) table[r * bins + b] = 10 + r * 0.5
    }
    const f = new BodyField(table, rows, rowStep, bins)
    expect(f.radiusAt(0, 0.3)).toBeCloseTo(10, 9)
    expect(f.radiusAt(2.5, 1.0)).toBeCloseTo(11.25, 9)
    expect(f.radiusAt(-5, 1.0)).toBeCloseTo(10, 9)       // 下夹取
    // 上夹取钳在末行 −0.0001（实现护栏），与末行值差 <1e-3
    expect(f.radiusAt(99, 1.0)).toBeCloseTo(14.5, 3)
    // θ 环绕：2π 与 0 同值；−θ 与 2π−θ 同值
    expect(f.radiusAt(1.25, Math.PI * 2)).toBeCloseTo(f.radiusAt(1.25, 0), 9)
    expect(f.radiusAt(1.25, -0.4)).toBeCloseTo(
      f.radiusAt(1.25, Math.PI * 2 - 0.4), 9)
  })

  it('placePoint：front/back 90° 扇区、band 整圈、右半镜像 θ→−θ', () => {
    const rows = 2, bins = 16, rowStep = 100
    const f = new BodyField(new Float32Array(rows * bins).fill(10),
      rows, rowStep, bins)
    const id = (y: number) => y
    const gap = SOLVER_PRIOR.garmentGap
    // front t=0 → θ=−π/2（wearer 左侧 = −X）
    const fL = placePoint('front', 'L', 0, 50, 0, 100, id, f)
    expect(fL[0]).toBeCloseTo(-(10 + gap), 9)
    expect(fL[2]).toBeCloseTo(0, 9)
    expect(fL[1]).toBeCloseTo(50, 9)
    // front t=1 → θ=0（前中 +Z）；back x 低端 = 侧缝 → θ=270°（wearer 左侧
    // −X，与 front 侧缝相接）；back x 高端（CB）→ θ=π（后中 −Z）——
    // 2026-09-14 修反装：back/yoke 用 1−t 反向走扇区（旧 t 正向把侧缝放到
    // 后中、CB 放到左侧，cb 镜像对/侧缝对初始差 30~35cm = 扭转错位根因）
    const fFront = placePoint('front', 'L', 100, 50, 0, 100, id, f)
    expect(fFront[2]).toBeCloseTo(10 + gap, 9)
    expect(fFront[0]).toBeCloseTo(0, 9)
    const bSide = placePoint('back', 'L', 0, 50, 0, 100, id, f)
    expect(bSide[0]).toBeCloseTo(-(10 + gap), 9)
    expect(bSide[2]).toBeCloseTo(0, 9)
    const bCb = placePoint('back', 'L', 100, 50, 0, 100, id, f)
    expect(bCb[2]).toBeCloseTo(-(10 + gap), 9)
    expect(bCb[0]).toBeCloseTo(0, 9)
    // band t=0 → θ=π（后中，与腰缝环序一致）；t=1 回到 π（整圈）
    const b0 = placePoint('band', 'L', 0, 50, 0, 100, id, f)
    expect(b0[2]).toBeCloseTo(-(10 + gap), 9)
    const b1 = placePoint('band', 'L', 100, 50, 0, 100, id, f)
    expect(b1[2]).toBeCloseTo(-(10 + gap), 9)
    // 镜像：R 侧 θ 取反 → x 翻号、z/y 不动（band 不镜像）
    const fR = placePoint('front', 'R', 0, 50, 0, 100, id, f)
    expect(fR[0]).toBeCloseTo(-fL[0], 9)
    expect(fR[2]).toBeCloseTo(fL[2], 9)
  })

  it('penetrationStats：同心圆零穿透、内陷计数/深度', () => {
    const rows = 2, bins = 16, rowStep = 100
    const f = new BodyField(new Float32Array(rows * bins).fill(10),
      rows, rowStep, bins)
    const pos = new Float32Array([
      12, 50, 0,    // r=12 > 10：在外
      9, 50, 0,     // r=9 < 10−0.3：穿透 1cm
      0, 50, 0,     // 轴心跳过（dist≈0）
    ])
    const st = penetrationStats(pos, f, 0.3)
    expect(st.count).toBe(1)
    expect(st.worst).toBeCloseTo(0.7, 6)   // 深度 = dist − (r − skin) = 9 − 9.7
  })
})

describe('seams：真产物人台整裤构建（M0 验收）', () => {
  it('直腰头：5 布片、11 缝计数、穿透 <50 点最深 <2cm、镜像对称 <0.1cm', () => {
    const { garment: g, field, meshes } = buildOnBody()
    // 5 布片 = fL/fR/bL/bR/band（fixture 直腰头）
    expect(g.parts.map((p) => `${p.key}_${p.side}`)).toEqual(
      ['front_L', 'front_R', 'back_L', 'back_R', 'band_L'])
    expect(g.bandFallback).toBeNull()

    // 11 缝计数：n_i = max(2, round(max(La,Lb)/seamStep)) 逐缝复核
    const nFor = (a: number, b: number) =>
      Math.max(2, Math.round(Math.max(a, b) / MESH_PRIOR.seamStep))
    const run = (m: ClothMesh, name: string): EdgeRun =>
      m.runs.find((r) => r.name === name)!
    const band = g.parts[4]
    const bandLen = run(band.mesh, 'bottom').length
    const waistArcs = [run(meshes.back, 'waist'), run(meshes.front, 'waist')]
    const arcSum = 2 * waistArcs.reduce((a, r) => a + r.length, 0)
    let expected = 0
    // side/inseam 左右各一条（同 run 长度）
    expected += 2 * nFor(run(meshes.front, 'side').length, run(meshes.back, 'side').length)
    expected += 2 * nFor(run(meshes.front, 'inseam').length, run(meshes.back, 'inseam').length)
    expected += nFor(run(meshes.front, 'rise').length, run(meshes.front, 'rise').length)
    expected += nFor(run(meshes.back, 'cb').length, run(meshes.back, 'cb').length)
    // 腰缝×4：环序 back_L → front_L → front_R → back_R（左右两半同 run）
    for (const r of [...waistArcs, ...waistArcs]) {
      const seg = (r.length / arcSum) * bandLen
      expected += Math.max(2, Math.round(Math.max(seg, r.length)
        / MESH_PRIOR.seamStep))
    }
    expected += nFor(run(band.mesh, 'end_a').length, run(band.mesh, 'end_b').length)
    expect(g.seam.length / 2).toBe(expected)

    // 穿透（同一支撑场自洽 + bilinear 内插不塌陷）
    const pen = penetrationStats(g.pos, field, SOLVER_PRIOR.collisionSkin)
    expect(pen.count).toBeLessThan(50)
    expect(pen.worst).toBeLessThan(2)

    // 镜像对称：L/R 共享 2D 网格，逐顶点 x 翻号、y 同值、z 近同值
    // （z 差源于支撑场 θ-bin 量化对 ±θ 的不对称 + bin 边界支撑跳变，<0.05cm）
    const N = meshes.front.xy.length / 2
    const xs: number[] = []
    for (let i = 0; i < N; i++) {
      const l = 3 * (g.parts[0].offset + i), r = 3 * (g.parts[1].offset + i)
      expect(g.pos[l + 1]).toBeCloseTo(g.pos[r + 1], 6)   // y
      expect(Math.abs(g.pos[l + 2] - g.pos[r + 2])).toBeLessThan(0.05)
      xs.push(Math.abs(g.pos[l] + g.pos[r]))
    }
    xs.sort((a, b) => a - b)
    expect(xs[Math.floor(xs.length / 2)]).toBeLessThan(0.1)

    // pin = 腰头上沿（belt line）粒子只钉 Y（直腰头口径：高度锚整裤，
    // 底沿交腰缝、行距交真实布长；全体粒子 Y-pin 已否决——底行与面板
    // 腰口自然悬垂差 ~1.1cm 永久拔河不收敛，见 seams.ts 注）
    const topRun = band.mesh.runs.find((r) => r.name === 'top')!
    expect(g.pinIdx.length).toBe(topRun.indices.length)
    expect(g.pinYOnly).toBe(true)
    expect(g.pinTarget.length).toBe(3 * g.pinIdx.length)
  })

  it('弯腰头回退：4 布片、视觉环带参数、pin=四片腰口粒子', () => {
    const { garment: g } = buildOnBody((r) => ({
      ...r, body: { ...r.body, waistband_type: 'curved' },
    }))
    expect(g.parts.length).toBe(4)
    expect(g.bandFallback).not.toBeNull()
    expect(g.bandFallback!.width).toBeGreaterThan(0)
    const topCount = g.parts.reduce((a, p) =>
      a + (p.mesh.runs.find((rn) => rn.role === 'top_chain')?.indices.length ?? 0), 0)
    expect(g.pinIdx.length).toBe(topCount)
  })

  it('腰头对账：底长 vs 四片腰弧 >0.5% 必炸', () => {
    expect(() => checkBandLength(60, [20, 20, 20, 20])).toThrow(/偏差/)
    expect(() => checkBandLength(80.3, [20, 20, 20, 20])).not.toThrow()
  })

  it('育克整裤（业务装配链）：7 布片、16 缝计数、机头线端点重合、穿透守卫', () => {
    const { garment: g, field, meshes } = buildOnBody(() => resultYoke)
    // 7 布片 = fL/fR/bL/bR/yL/yR/band（fixture 直腰头 + back_yoke）
    expect(g.parts.map((p) => `${p.key}_${p.side}`)).toEqual(
      ['front_L', 'front_R', 'back_L', 'back_R', 'yoke_L', 'yoke_R', 'band_L'])
    expect(g.bandFallback).toBeNull()

    const run = (m: ClothMesh, name: string): EdgeRun =>
      m.runs.find((r) => r.name === name)!

    // 机头下口线两端（cb 侧 P0 / side 侧 PN）在育克 bottom 与后片 top
    // 聚合段上全局 2D 重合（rot180 反变换 + 同几何业务链的金标；链向
    // 允许相反，端点集重合即可）
    const yoke = meshes.yoke!
    const pt = (m: ClothMesh, r: EdgeRun, i: number): [number, number] =>
      [m.xy[2 * r.indices[i]], m.xy[2 * r.indices[i] + 1]]
    const yb = run(yoke, 'bottom'), bt = run(meshes.back, 'top')
    for (const [ya, ba] of [
      [pt(yoke, yb, 0), pt(meshes.back, bt, 0)],
      [pt(yoke, yb, yb.indices.length - 1), pt(meshes.back, bt, 0)],
    ] as const) {
      const [bx, by] = ba
      const d = Math.min(
        Math.hypot(ya[0] - bx, ya[1] - by),
        Math.hypot(ya[0] - pt(meshes.back, bt, bt.indices.length - 1)[0],
          ya[1] - pt(meshes.back, bt, bt.indices.length - 1)[1]))
      expect(d).toBeLessThan(0.05)
    }

    // 16 缝计数：n = max(2, round(max(|Δt|·La, |Δu|·Lb)/seamStep)) 逐缝复核
    const nFor = (a: number, b = a) =>
      Math.max(2, Math.round(Math.max(a, b) / MESH_PRIOR.seamStep))
    let expected = 0
    for (const _side of ['L', 'R'] as const) {
      // 侧缝链式拆分：后片段（脚口端对齐）+ 育克段（腰口端接续）
      expected += nFor(run(meshes.back, 'side').length)
      expected += nFor(run(yoke, 'side').length)
      expected += nFor(run(meshes.front, 'inseam').length,
        run(meshes.back, 'inseam').length)
      // 育克下口↔后片上口（同长机头线）
      expected += nFor(run(yoke, 'bottom').length, run(meshes.back, 'top').length)
    }
    expected += nFor(run(meshes.front, 'rise').length)
    expected += nFor(run(meshes.back, 'cb').length)
    expected += nFor(run(yoke, 'cb').length)
    // 腰缝×4：后侧 = 育克上口、前侧 = 前片腰口
    const band = g.parts[6]
    const bandLen = run(band.mesh, 'bottom').length
    const arcs = [run(yoke, 'top').length, run(meshes.front, 'waist').length]
    const arcSum = 2 * arcs.reduce((a, b) => a + b, 0)
    for (const len of [...arcs, ...arcs]) {
      expected += Math.max(2, Math.round(Math.max(
        (len / arcSum) * bandLen, len) / MESH_PRIOR.seamStep))
    }
    expected += nFor(run(band.mesh, 'end_a').length, run(band.mesh, 'end_b').length)
    expect(g.seam.length / 2).toBe(expected)

    // 穿透与 pin 守卫（育克同 back 扇区摆位，凸包场保证不穿体）
    const pen = penetrationStats(g.pos, field, SOLVER_PRIOR.collisionSkin)
    expect(pen.count).toBeLessThan(50)
    expect(pen.worst).toBeLessThan(2)
    const topRun = band.mesh.runs.find((r) => r.name === 'top')!
    expect(g.pinIdx.length).toBe(topRun.indices.length)
    expect(g.pinYOnly).toBe(true)
  })

  it('育克 + 弯腰头回退：6 布片、pin = 各腰口件（含育克上口）', () => {
    const { garment: g } = buildOnBody(() => ({
      ...resultYoke, body: { ...resultYoke.body, waistband_type: 'curved' },
    }))
    expect(g.parts.length).toBe(6)
    expect(g.bandFallback).not.toBeNull()
    const topCount = g.parts.reduce((a, p) =>
      a + (p.mesh.runs.find((rn) => rn.role === 'top_chain')?.indices.length ?? 0), 0)
    expect(g.pinIdx.length).toBe(topCount)
    expect(g.pinYOnly).toBe(false)
  })

  it('数据一致性守卫：后片上口为机头线但缺育克网格必炸', () => {
    const body = loadBodyFromDisk()
    const asset = {
      ...body, height: 120.64,
      heightInfo: { baseCm: 167, plusCm: 72, minusCm: -36 }, targets: [],
    } as Parameters<typeof bodyLandmarksOf>[0]
    const warp = buildWarp(resultYoke.body.stations, bodyLandmarksOf(asset))
    const field = buildBodyField(body.positions, body.indices)
    const meshes = {
      front: buildClothMesh(resultYoke.pieces.find((p) => p.key === 'front_piece')!),
      back: buildClothMesh(resultYoke.pieces.find((p) => p.key === 'back_piece')!),
    }
    expect(() => buildGarment(meshes, resultYoke, warp, field))
      .toThrow(/缺育克网格/)
  })

  it('fly 连裁拦截：前中 rise 链缺失时显式报错（金标覆盖三分支之二）', () => {
    const body = loadBodyFromDisk()
    const asset = {
      ...body, height: 120.64,
      heightInfo: { baseCm: 167, plusCm: 72, minusCm: -36 }, targets: [],
    } as Parameters<typeof bodyLandmarksOf>[0]
    const warp = buildWarp(result.body.stations, bodyLandmarksOf(asset))
    const field = buildBodyField(body.positions, body.indices)
    const meshes = {
      front: buildClothMesh(result.pieces.find((p) => p.key === 'front_piece')!),
      back: buildClothMesh(result.pieces.find((p) => p.key === 'back_piece')!),
    }
    // 模拟 fly 连裁的前片：rise 边消失（前中缝链只剩裆下残段、fly 区敞口）
    const flyCut: Record<'front' | 'back', ClothMesh> = {
      back: meshes.back,
      front: {
        ...meshes.front,
        runs: meshes.front.runs.filter((r) => r.name !== 'rise'),
      },
    }
    expect(() => buildGarment(flyCut, result, warp, field)).toThrow(/连裁门襟/)
  })

  it('buildWaistRing：沿腰口 pin 弧成环（弯腰口弧逐点跟随，两圈条带）', () => {
    // M1 fixture 是直腰头（真实布片、无环带）；覆写 curved 进回退模式
    const { garment } = buildOnBody((r) => ({
      ...r, body: { ...r.body, waistband_type: 'curved' as const },
    }))
    const ring = buildWaistRing(garment)
    const n = ring.positions.length / 6
    expect(n).toBeGreaterThanOrEqual(3)
    expect(ring.indices.length).toBe(n * 6)
    // 底圈逐点 = 腰口 pin 摆位；顶圈 = 底圈 + bandFallback 宽度
    expect(garment.bandFallback).not.toBeNull()
    const w = garment.bandFallback!.width
    for (let k = 0; k < n; k++) {
      expect(ring.positions[3 * (k + n) + 1] - ring.positions[3 * k + 1])
        .toBeCloseTo(w, 6)
    }
    // 非回退模式（直腰头真实布片）无环带可建
    expect(() => buildWaistRing({
      ...garment, bandFallback: null,
    })).toThrow(/回退模式/)
  })
})
