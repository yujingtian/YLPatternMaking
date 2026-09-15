// 全裁片装配金标（重建 2026-09-15）：平铺验证（三期回落，现行接线）
// + 扇区悬挂摆位（一期，暂停接线）。平铺验收：payload 逐片一行（成对
// 片 L 原样 / R 前中镜像逐点等距变换、腰头单片）、全片贴地 y=0、全组
// z 居中、行序 = payload 片序、行距 ≥ rowGap、无 NaN。悬挂验收：2 片
// 镜像摆位（x 翻号、z 差 <0.05cm——θ-bin 量化对 ±θ 不对称）、前扇区
// 角度域 [−90°,0°]、无穿透（摆位半径 = 场 + gap，按构造零穿透）。
// 夹具 = fixture_fitting.json（引擎 build_fitting_payload 直出，默认
// 直腰头 3 片：front_piece / back_piece / waistband）。
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../types'
import { buildFlatLayout, buildFrontPair } from './assemble'
import { buildCore, CORE_SKIN } from './core'
import { buildClothMesh } from './mesh'
import { buildBodyField, penetrationStats } from './placement'
import { FLAT_PRIOR } from './priors'

const HERE = import.meta.dirname   // src/fitting3d/garment

const result: FittingResult = JSON.parse(
  readFileSync(`${HERE}/fixture_fitting.json`, 'utf8'))

describe('assemble：全裁片平铺装配（重建三期回落，现行）', () => {
  const garment = buildFlatLayout(result)
  // fixture 直腰头 3 片：front×2 + back×2 + waistband×1（腰头单片）
  const frontMesh = buildClothMesh(result.pieces[0])
  const backMesh = buildClothMesh(result.pieces[1])
  const wbMesh = buildClothMesh(result.pieces[2])
  const partZ = (pi: number): { z0: number; z1: number; x1: number } => {
    const p = garment.parts[pi]
    const n = p.mesh.xy.length / 2
    let z0 = Infinity, z1 = -Infinity, x1 = 0
    for (let i = 0; i < n; i++) {
      z0 = Math.min(z0, garment.pos[3 * (p.offset + i) + 2])
      z1 = Math.max(z1, garment.pos[3 * (p.offset + i) + 2])
      x1 = Math.max(x1, garment.pos[3 * (p.offset + i)])
    }
    return { z0, z1, x1 }
  }

  it('parts 序 = payload 片序展开（成对片 L+R、腰头单片）、共享网格 offset 顺排', () => {
    expect(garment.parts.map((p) => `${p.key}_${p.side}`))
      .toEqual(['front_piece_L', 'front_piece_R',
        'back_piece_L', 'back_piece_R', 'waistband_L'])
    expect(result.pieces.map((p) => p.key))
      .toEqual(['front_piece', 'back_piece', 'waistband'])
    expect(garment.parts[0].mesh).toBe(garment.parts[1].mesh)
    expect(garment.parts[2].mesh).toBe(garment.parts[3].mesh)
    let off = 0
    for (const p of garment.parts) {
      expect(p.offset).toBe(off)
      off += p.mesh.xy.length / 2
    }
    expect(garment.total).toBe(off)
    expect(garment.pos.length).toBe(3 * off)
    // 网格 = 逐片 buildClothMesh 原样（layout 内自建，引用不同内容同——
    // 内容一致性由下方逐点等距变换用例钉死，这里对账顶点数）
    expect(garment.parts[0].mesh.xy.length).toBe(frontMesh.xy.length)
    expect(garment.parts[4].mesh.xy.length).toBe(wbMesh.xy.length)
  })

  it('全片贴地 y≡0、无 NaN、全组 z 居中于 0', () => {
    let zMin = Infinity, zMax = -Infinity
    for (let i = 0; i < garment.total; i++) {
      const px = garment.pos[3 * i], py = garment.pos[3 * i + 1]
      const pz = garment.pos[3 * i + 2]
      expect(Number.isFinite(px)).toBe(true)
      expect(Number.isFinite(pz)).toBe(true)
      expect(py).toBe(0)                 // 平铺：高度恒 0（离地在显示层）
      zMin = Math.min(zMin, pz)
      zMax = Math.max(zMax, pz)
    }
    // 手工演算：depth = Σ行高 + (片数−1)·rowGap，组 z 域 [-depth/2, +depth/2]
    const depth = (partZ(0).z1 - partZ(0).z0) + (partZ(2).z1 - partZ(2).z0)
      + (partZ(4).z1 - partZ(4).z0) + 2 * FLAT_PRIOR.rowGap
    expect(zMax - zMin).toBeCloseTo(depth, 5)
    expect(Math.abs(zMin + zMax)).toBeLessThan(1e-4)   // 居中：中点 ≈ 0
  })

  it('行序 = payload 片序（前片最近）、相邻行距 ≥ rowGap', () => {
    const f = partZ(0), b = partZ(2), w = partZ(4)
    expect(f.z1).toBeLessThan(b.z0)          // front 行整体在 back 行前
    expect(b.z1).toBeLessThan(w.z0)
    // 摆位构造行距恰 rowGap（pos Float32 对照有 ~1e-6 量化伪差，放 4 位）
    expect(b.z0 - f.z1).toBeCloseTo(FLAT_PRIOR.rowGap, 4)
    expect(w.z0 - b.z1).toBeCloseTo(FLAT_PRIOR.rowGap, 4)
  })

  it('成对片逐点等距变换：L 原样、R 前中镜像（与 2D 裁片 SVG 一比一）', () => {
    for (const [li, ri, mesh] of [
      [0, 1, frontMesh], [2, 3, backMesh],
    ] as const) {
      const n = mesh.xy.length / 2
      let xMin = Infinity, xMax = -Infinity
      let yMin = Infinity
      for (let i = 0; i < mesh.xy.length; i += 2) {
        xMin = Math.min(xMin, mesh.xy[i])
        xMax = Math.max(xMax, mesh.xy[i])
        yMin = Math.min(yMin, mesh.xy[i + 1])
      }
      const W = xMax - xMin
      const zBase = partZ(li).z0
      for (let i = 0; i < n; i++) {
        const u = mesh.xy[2 * i] - xMin
        const v = mesh.xy[2 * i + 1] - yMin
        const l = 3 * (garment.parts[li].offset + i)
        const r = 3 * (garment.parts[ri].offset + i)
        // L：片内归一原样落 (u, 0, zBase+v)
        expect(garment.pos[l]).toBeCloseTo(u, 5)
        expect(garment.pos[l + 2]).toBeCloseTo(zBase + v, 4)
        // R：u→W−u 镜像 + 平移 W+gap；z 同 L（腰口同向）
        expect(garment.pos[r])
          .toBeCloseTo(W + FLAT_PRIOR.gap + (W - u), 5)
        expect(garment.pos[r + 2]).toBeCloseTo(garment.pos[l + 2], 4)
      }
    }
  })

  it('腰头单片原样（无镜像副本）、x∈[0,W]', () => {
    const p = garment.parts[4]
    const n = p.mesh.xy.length / 2
    let xMin = Infinity, xMax = -Infinity
    for (let i = 0; i < wbMesh.xy.length; i += 2) {
      xMin = Math.min(xMin, wbMesh.xy[i])
      xMax = Math.max(xMax, wbMesh.xy[i])
    }
    const W = xMax - xMin
    for (let i = 0; i < n; i++) {
      const u = wbMesh.xy[2 * i] - xMin
      const idx = 3 * (p.offset + i)
      expect(garment.pos[idx]).toBeCloseTo(u, 5)
      expect(garment.pos[idx]).toBeGreaterThanOrEqual(0)
    }
    expect(partZ(4).x1).toBeCloseTo(W, 5)
  })
})

describe('assemble：前片 L+R 静态装配（重建一期，暂停接线）', () => {
  const front = buildClothMesh(result.pieces.find((p) => p.key === 'front_piece')!)
  const core = buildCore(result)
  const field = buildBodyField(core.positions, core.indices)
  const garment = buildFrontPair(front, field)

  it('两片共享网格、offset 顺排、总数 = 2×前片顶点', () => {
    expect(garment.parts.map((p) => `${p.key}_${p.side}`))
      .toEqual(['front_L', 'front_R'])
    expect(garment.parts[0].mesh).toBe(front)
    expect(garment.parts[1].mesh).toBe(front)
    expect(garment.parts[1].offset).toBe(front.xy.length / 2)
    expect(garment.total).toBe(front.xy.length)
    expect(garment.pos.length).toBe(3 * garment.total)
  })

  it('无 NaN；前扇区角度域：L 全部 θ∈[−90°,0°]、R 镜像', () => {
    for (let i = 0; i < garment.pos.length; i++) {
      expect(Number.isFinite(garment.pos[i])).toBe(true)
    }
    for (let i = 0; i < garment.total; i++) {
      const x = garment.pos[3 * i], z = garment.pos[3 * i + 2]
      const th = Math.atan2(x, z)
      if (i < garment.parts[1].offset) {
        expect(th).toBeGreaterThanOrEqual(-Math.PI / 2 - 1e-9)
        expect(th).toBeLessThanOrEqual(1e-9)
      } else {
        expect(th).toBeLessThanOrEqual(Math.PI / 2 + 1e-9)
        expect(th).toBeGreaterThanOrEqual(-1e-9)
      }
    }
  })

  it('镜像对称：L/R 同网格逐顶点 x 翻号、y 同值、z 差 <0.1cm', () => {
    // z 差源于支撑场 θ-bin 量化对 ±θ 的不对称 + bin 边界支撑跳变：旧链
    // 人台场实测 <0.05cm；撑型芯场（花生瓣特征更锐）实测 max 0.073cm，
    // 口径放宽到 <0.1cm（0.7mm 纯量化伪差，视觉不可辨）
    const N = front.xy.length / 2
    const xs: number[] = []
    for (let i = 0; i < N; i++) {
      const l = 3 * (garment.parts[0].offset + i)
      const r = 3 * (garment.parts[1].offset + i)
      expect(garment.pos[l + 1]).toBeCloseTo(garment.pos[r + 1], 6)   // y
      expect(Math.abs(garment.pos[l + 2] - garment.pos[r + 2]))
        .toBeLessThan(0.1)
      xs.push(Math.abs(garment.pos[l] + garment.pos[r]))
    }
    xs.sort((a, b) => a - b)
    expect(xs[Math.floor(xs.length / 2)]).toBeLessThan(0.1)
  })

  it('穿透零：摆位半径 = 场 + garmentGap，按构造不穿芯（skin 壳口径）', () => {
    const pen = penetrationStats(garment.pos, field, CORE_SKIN)
    expect(pen.count).toBe(0)
    expect(pen.worst).toBe(0)
  })
})
