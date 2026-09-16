// 裁片网格与摆位金标（2026-09-15 重建一期口径：整裤缝合/解算链已删，
// 只测单片地基）：布料网格拓扑（三角化面积比 ≥99%、最小角 >15°、边界
// 环聚合段）；支撑半径场（双线性、θ 环绕、y 夹取）；placePoint 前/后
// 扇区摆位与镜像；穿透统计口径。
// 夹具 = 引擎 payload（fixture_fitting.json 默认直腰头，引擎
// build_fitting_payload 直出 + 补 ok/warnings）。
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../types'
import { buildClothMesh, runIndexAt } from './mesh'
import { BodyField, placePoint, penetrationStats } from './placement'
import { HANG_PRIOR } from './priors'

const HERE = import.meta.dirname   // src/fitting3d/garment

const result: FittingResult = JSON.parse(
  readFileSync(`${HERE}/fixture_fitting.json`, 'utf8'))

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
    // 实测（fixture）：细长三角形全部贴边界（front 39/2421）
    // ——边界弧长重采样点近共线 + Delaunay 的固有产物，旧链原样保留不修；
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

  it('placePoint：front 90° 前扇区、右半镜像 θ→−θ', () => {
    const rows = 2, bins = 16, rowStep = 100
    const f = new BodyField(new Float32Array(rows * bins).fill(10),
      rows, rowStep, bins)
    const gap = HANG_PRIOR.garmentGap
    // front t=0 → θ=−π/2（侧缝、wearer 左侧 = −X）
    const fL = placePoint('front', 'L', 0, 50, 0, 100, f)
    expect(fL[0]).toBeCloseTo(-(10 + gap), 9)
    expect(fL[2]).toBeCloseTo(0, 9)
    expect(fL[1]).toBeCloseTo(50, 9)
    // front t=1 → θ=0（前中 +Z）
    const fFront = placePoint('front', 'L', 100, 50, 0, 100, f)
    expect(fFront[2]).toBeCloseTo(10 + gap, 9)
    expect(fFront[0]).toBeCloseTo(0, 9)
    expect(fFront[1]).toBeCloseTo(50, 9)
    // 镜像：R 侧 θ 取反 → x 翻号、z/y 不动
    const fR = placePoint('front', 'R', 0, 50, 0, 100, f)
    expect(fR[0]).toBeCloseTo(-fL[0], 9)
    expect(fR[2]).toBeCloseTo(fL[2], 9)
    expect(fR[1]).toBeCloseTo(fL[1], 9)
  })

  it('placePoint：back 90° 后扇区（侧缝 −90° → 后中 −180°）、右半镜像', () => {
    const rows = 2, bins = 16, rowStep = 100
    const f = new BodyField(new Float32Array(rows * bins).fill(10),
      rows, rowStep, bins)
    const gap = HANG_PRIOR.garmentGap
    // back t=0 → θ=−π/2（侧缝，与 front 同角——穿着拓扑侧缝相邻）
    const bL = placePoint('back', 'L', 0, 50, 0, 100, f)
    expect(bL[0]).toBeCloseTo(-(10 + gap), 9)
    expect(bL[2]).toBeCloseTo(0, 9)
    expect(bL[1]).toBeCloseTo(50, 9)
    // back t=1 → θ=−π（后中 −Z，与前中 +Z 相对）
    const bCb = placePoint('back', 'L', 100, 50, 0, 100, f)
    expect(bCb[2]).toBeCloseTo(-(10 + gap), 9)
    expect(bCb[0]).toBeCloseTo(0, 9)
    // 镜像：R 侧 θ 取反（+90° → +180°）→ x 翻号、z 同号
    const bR = placePoint('back', 'R', 0, 50, 0, 100, f)
    expect(bR[0]).toBeCloseTo(-bL[0], 9)
    expect(bR[2]).toBeCloseTo(bL[2], 9)
    const bRCb = placePoint('back', 'R', 100, 50, 0, 100, f)
    expect(bRCb[2]).toBeCloseTo(bCb[2], 9)   // 两半后中同在 −Z 闭合
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
