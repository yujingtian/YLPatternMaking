// 3D 试穿纯几何/数据层单测（three 不进测试：视图层另行肉眼验收）。
// 金标风格：手工推演值 + 强断言。
//   1. mannequin 适配层：radiusAt 轴向 == 半轴 / hf 柄短路返回裸 R；
//      sectionAt 端点夹取 + cx 线性插值（人台几何金标在 bodymesh.test.ts
//      + Python 侧 tests/test_vendor_bodymesh.py；旧环模型 describe 已随
//      2026-09-11 换轨退役，演进史见决策日志 §十一）
//   2. estimateBody：成衣 − 先验松量 + 0.85 下限
//   3. 体型库：默认估计激活、预设存在、自定义增删、JSON 导入导出
//   4. 网格：三角化欧拉公式 V−E+F=1（圆盘）、边名聚合段、locate 权重和 1
//   5. 摆位：左半片 x<=0 / 右半片 x>=0（θ 约定）、前中 +Z / 后中 −Z
//   6. 碰撞：体内粒子推出到 R+skin（radiusAt 单位向量口径强断言——修复
//      前未归一化输入使判据退化为 dist ≥ R/dist，断言空转）
//   7. PBD：全 pin 收敛 settled 且位置不动；自由落体 y 单调下降且有限
//   8. 应变：静止长 = 0、拉长 > 0；色带 红(紧)/绿(贴合)/蓝(松) 单调
import { describe, expect, it, vi } from 'vitest'
import type { FittingPiece } from '../types'
import { estimateBody, validateGirths } from './bodyProfile'
import {
  BODY_PRESETS, exportProfiles, findProfile, importProfiles, loadStore,
  removeCustom, upsertCustom,
} from './bodyProfileStore'
import { radiusAt, sectionAt } from './mannequin'
import type { Mannequin, SectionParams, Tube } from './mannequin'
import { buildClothMesh, runIndexAt } from './mesh'
import { placePoint } from './seams'
import { collideOne } from './pbd/collide'
import { createSim, stepSim } from './pbd/solver'
import type { Garment, GarmentPart } from './seams'
import { computeStrain, strainColor } from './heatmap'

// ---- 人台夹具：手搓三管 Tube（显式 a/bF/bB/e/cx、无 hf） ----
// 摆位/碰撞/解算测试只消费三管契约（管域门控 + sectionAt/radiusAt），
// 无 hf 恰好回归超椭圆解析分支（网格路径 hf 金标在 bodymesh.test.ts）。
// 锚值分段线性（y 严格降序、量级仿 165/66A）
const anchorAt = (anchors: [number, number][], y: number): number => {
  if (y >= anchors[0][0]) return anchors[0][1]
  for (let i = 0; i < anchors.length - 1; i++) {
    const [y0, v0] = anchors[i], [y1, v1] = anchors[i + 1]
    if (y <= y0 && y >= y1) return v0 + ((y0 - y) / (y0 - y1)) * (v1 - v0)
  }
  return anchors[anchors.length - 1][1]
}

function fixtureMannequin(): Mannequin {
  const PELVIS_A: [number, number][] = [
    [116, 11], [98, 11.6], [86, 15.7], [36, 10],
  ]
  const pelvisRings: SectionParams[] = []
  for (let y = 116; y >= 36 - 1e-9; y -= 4) {
    const a = anchorAt(PELVIS_A, y)
    pelvisRings.push({ y, cx: 0, a, bF: 0.75 * a, bB: 0.84 * a, e: 2.2 })
  }
  const LEG_A: [number, number][] = [[80, 7], [42, 6], [-8, 5]]
  const mkLeg = (sign: number): Tube => {
    const rings: SectionParams[] = []
    for (let y = 80; y >= -8 - 1e-9; y -= 4) {
      const a = anchorAt(LEG_A, y)
      rings.push({ y, cx: sign * 6.5, a, bF: a, bB: a, e: 2 })
    }
    return { rings }
  }
  return {
    pelvis: { rings: pelvisRings },
    legs: [mkLeg(-1), mkLeg(1)],
    topY: 116, bottomY: -8,
  }
}

// 矩形裁片（链序 waist->side->hem->rise 闭合，全局系）
function rectPiece(w: number, h: number): FittingPiece {
  const line = (a: [number, number], b: [number, number]) =>
    [a, b] as [number, number][]
  const len = (a: [number, number], b: [number, number]) =>
    Math.hypot(b[0] - a[0], b[1] - a[1])
  const e = (
    name: string, role: FittingPiece['edges'][number]['role'],
    a: [number, number], b: [number, number],
  ) => ({ name, kind: 'line' as const, role, pts: line(a, b), length: len(a, b) })
  return {
    key: 'front_piece', name: '前片',
    origin: [0, 0], frame: 'reflect_y',
    bbox: [0, 0, w, h],
    edges: [
      e('waist', 'top_chain', [0, h], [w, h]),
      e('side', 'seam', [w, h], [w, 0]),
      e('hem', 'hem', [w, 0], [0, 0]),
      e('rise', 'seam', [0, 0], [0, h]),
    ],
    marks: [], notches: [], grain: null,
  }
}

describe('mannequin 适配层（三管截面参数）', () => {
  it('radiusAt 轴向收敛到半轴；hf 柄短路返回裸 R（θ=atan2 复原）', () => {
    const man = fixtureMannequin()
    const s = sectionAt(man.pelvis, 98)
    expect(radiusAt(s, 1, 0)).toBeCloseTo(s.a, 3)
    expect(radiusAt(s, 0, 1)).toBeCloseTo(s.bF, 3)
    expect(radiusAt(s, 0, -1)).toBeCloseTo(s.bB, 3)
    // hf 存在时 radiusAt 短路查表（解析式不消费）——网格人台路径契约
    const R = 5.25
    const sh: SectionParams = {
      ...s, hf: (_y, th) => R + (Math.abs(th) < 1e-9 ? 1 : 0),
    }
    expect(radiusAt(sh, 0, 1)).toBeCloseTo(R + 1, 9)   // dz=1 -> θ=0
    expect(radiusAt(sh, 1, 0)).toBeCloseTo(R, 9)       // dx=1 -> θ=π/2
  })
  it('sectionAt 端点夹取到端环（同引用）；cx 线性插值', () => {
    const man = fixtureMannequin()
    expect(sectionAt(man.pelvis, 999)).toBe(man.pelvis.rings[0])
    expect(sectionAt(man.pelvis, -999))
      .toBe(man.pelvis.rings[man.pelvis.rings.length - 1])
    const leg = man.legs[1]
    const mid = (leg.rings[0].y + leg.rings[1].y) / 2
    expect(sectionAt(leg, mid).cx).toBeCloseTo(
      (leg.rings[0].cx + leg.rings[1].cx) / 2, 9)
  })
})

describe('bodyProfile 体型估计', () => {
  it('成衣 − 先验松量（waist 1.5 / hip 5 / thigh 4 / knee 3）', () => {
    const b = estimateBody({ waist: 70, hip: 96, thigh: 58, knee: 46 })
    expect(b.waist).toBeCloseTo(68.5, 9)
    expect(b.hip).toBeCloseTo(91, 9)
    expect(b.thigh).toBeCloseTo(54, 9)
    expect(b.knee).toBeCloseTo(43, 9)
    expect(b.estimated).toBe(true)
  })
  it('0.85 下限：小成衣防负松量翻车', () => {
    const b = estimateBody({ waist: 1, hip: 1, knee: 1 })
    expect(b.waist).toBeCloseTo(0.85, 9)
    expect(b.thigh).toBeUndefined()
  })
  it('校验范围', () => {
    expect(validateGirths({ waist: 66, hip: 90, knee: 35 })).toBeNull()
    expect(validateGirths({ waist: 140, hip: 90, knee: 35 })).toMatch(/腰围/)
  })
})

describe('bodyProfileStore 体型库', () => {
  it('默认激活估计体型；预设含标准 165/66A', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => null, setItem: () => {}, removeItem: () => {},
    })
    const s = loadStore()
    expect(s.activeId).toBe('estimated')
    expect(BODY_PRESETS.some((p) => p.id === 'std-165-66')).toBe(true)
    vi.unstubAllGlobals()
  })
  it('自定义增删改 + 查找', () => {
    const s0 = { version: 1 as const, activeId: 'estimated', customs: [] }
    const p = { id: 'c1', name: '我的体型', waist: 64, hip: 92, knee: 34 }
    const s1 = upsertCustom(s0, p)
    expect(s1.customs).toHaveLength(1)
    expect(s1.activeId).toBe('c1')
    expect(findProfile(s1, 'c1')?.name).toBe('我的体型')
    const s2 = upsertCustom(s1, { ...p, waist: 65 })
    expect(s2.customs).toHaveLength(1)
    expect(s2.customs[0].waist).toBe(65)
    const s3 = removeCustom(s2, 'c1')
    expect(s3.customs).toHaveLength(0)
    expect(s3.activeId).toBe('estimated')
  })
  it('JSON 导出/导入回环；非法条目跳过计数', () => {
    const text = exportProfiles([
      { id: 'a', name: 'A', waist: 64, hip: 90, knee: 34 },
      { id: 'b', name: 'B', waist: 64, hip: 90, knee: 34 },
    ])
    const rt = importProfiles(text)
    expect(rt.ok).toHaveLength(2)
    expect(rt.skipped).toBe(0)
    const bad = JSON.stringify({
      profiles: [
        { id: 'x', name: 'X', waist: 999, hip: 90, knee: 34 },   // 范围外
        { id: 'y', name: 'Y', waist: 64, hip: 90, knee: 34 },
      ],
    })
    const r2 = importProfiles(bad)
    expect(r2.ok.map((p) => p.id)).toEqual(['y'])
    expect(r2.skipped).toBe(1)
    expect(() => importProfiles('[]')).toThrow()
  })
})

describe('mesh 布料网格', () => {
  const mesh = buildClothMesh(rectPiece(10, 20))
  it('欧拉公式 V−E+F=1（三角化圆盘）+ 无退化', () => {
    const V = mesh.xy.length / 2
    const F = mesh.tri.length / 3
    const edges = new Map<number, number>()
    for (let t = 0; t < mesh.tri.length; t += 3) {
      const v = [mesh.tri[t], mesh.tri[t + 1], mesh.tri[t + 2]]
      for (let e = 0; e < 3; e++) {
        const i = v[e], j = v[(e + 1) % 3]
        const k = i < j ? i * V + j : j * V + i
        edges.set(k, (edges.get(k) ?? 0) + 1)
      }
    }
    expect(V - edges.size + F).toBe(1)
    // 每条边至多共享两次（流形）
    expect([...edges.values()].every((c) => c <= 2)).toBe(true)
  })
  it('边名聚合段沿链序，弧长累计 = 边长', () => {
    expect(mesh.runs.map((r) => r.name)).toEqual(['waist', 'side', 'hem', 'rise'])
    expect(mesh.runs[1].length).toBeCloseTo(20, 6)
    expect(runIndexAt(mesh.runs[1], 0)).toBe(mesh.runs[1].indices[0])
    expect(runIndexAt(mesh.runs[1], 1))
      .toBe(mesh.runs[1].indices[mesh.runs[1].indices.length - 1])
  })
  it('locate：内部命中且权重和 1，外部 null', () => {
    const loc = mesh.locate(5, 10)
    expect(loc).not.toBeNull()
    const w = loc!.w[0] + loc!.w[1] + loc!.w[2]
    expect(w).toBeCloseTo(1, 9)
    expect(mesh.locate(-1, 10)).toBeNull()
    expect(mesh.locate(5, 25)).toBeNull()
  })
})

describe('seams 摆位约定', () => {
  const man = fixtureMannequin()
  it('左半 x<=0 / 右半 x>=0；前中 +Z、后中 −Z', () => {
    const fSide = placePoint('front', 'L', 0, 90, 0, 20, man)
    expect(fSide[0]).toBeLessThanOrEqual(0)
    expect(Math.abs(fSide[2])).toBeLessThan(1e-9)      // θ=−90°：正侧方
    const fRise = placePoint('front', 'L', 20, 90, 0, 20, man)
    expect(Math.abs(fRise[0])).toBeLessThan(1e-9)
    expect(fRise[2]).toBeGreaterThan(0)                // 前中 +Z
    const bCb = placePoint('back', 'L', 0, 90, 0, 20, man)
    expect(Math.abs(bCb[0])).toBeLessThan(1e-9)
    expect(bCb[2]).toBeLessThan(0)                     // 后中 −Z
    const bSideR = placePoint('back', 'R', 20, 90, 0, 20, man)
    expect(bSideR[0]).toBeGreaterThanOrEqual(0)
    // 摆位半径 = 体表支撑 + 松量 > 0
    expect(fSide[0]).toBeLessThan(0)
  })
  it('高度直通：全局 y 即身体高度', () => {
    const p = placePoint('front', 'L', 10, 55.5, 0, 20, man)
    expect(p[1]).toBeCloseTo(55.5, 9)
  })
})

describe('pbd 碰撞与解算', () => {
  const man = fixtureMannequin()
  it('体内粒子推出到 R+skin（radiusAt 单位向量口径）', () => {
    const s = sectionAt(man.pelvis, 98)
    // 轴向粒子：推出后恰在 s.a + skin（位移纯法向，摩擦项切向分量为 0）
    const pos = new Float32Array([s.cx + s.a * 0.5, 98, 0])
    const prev = pos.slice()
    collideOne(pos, prev, 0, man, 0.3, 0.5)
    expect(pos[0] - s.cx).toBeCloseTo(s.a + 0.3, 3)
    // 斜向粒子 (3,4)：归一化后支撑半径不被距离稀释（修复前未归一化口径
    // 均衡点 ≈√R≈3.8cm、粒子可沉入体表 ~10cm——修复后此断言才有强度）
    const pos2 = new Float32Array([s.cx + 3, 98, 4])
    const prev2 = pos2.slice()
    collideOne(pos2, prev2, 0, man, 0.3, 0.5)
    const dx = pos2[0] - s.cx, dz = pos2[2]
    const dist = Math.hypot(dx, dz)
    expect(dist).toBeGreaterThanOrEqual(
      radiusAt(s, dx / dist, dz / dist) + 0.3 - 1e-6)
  })
  it('全 pin：收敛 settled 且位置钉住', () => {
    const mesh = buildClothMesh(rectPiece(6, 12))
    const n = mesh.xy.length / 2
    const pos = new Float32Array(3 * n)
    for (let i = 0; i < n; i++) {
      pos[3 * i] = mesh.xy[2 * i]
      pos[3 * i + 1] = 120 + mesh.xy[2 * i + 1]
      pos[3 * i + 2] = 8
    }
    const garment: Garment = {
      parts: [{ key: 'front', side: 'L', mesh, offset: 0 } as GarmentPart],
      pos,
      seam: new Int32Array(0),
      pinIdx: Uint32Array.from({ length: n }, (_, i) => i),
      pinTarget: pos.slice(),
      total: n,
    }
    const sim = createSim(garment, man)
    let st = 'running'
    for (let k = 0; k < 80 && st === 'running'; k++) st = stepSim(sim)
    expect(st).toBe('settled')
    for (let i = 0; i < 3 * n; i++) {
      expect(Math.abs(sim.pos[i] - pos[i])).toBeLessThan(0.05)
    }
  })
  it('无 pin 自由落体：y 单调下降且有限', () => {
    const mesh = buildClothMesh(rectPiece(6, 12))
    const n = mesh.xy.length / 2
    const pos = new Float32Array(3 * n)
    for (let i = 0; i < n; i++) {
      pos[3 * i] = mesh.xy[2 * i]
      pos[3 * i + 1] = 200 - mesh.xy[2 * i + 1]   // 身体上方悬空
      pos[3 * i + 2] = 60
    }
    const garment: Garment = {
      parts: [{ key: 'front', side: 'L', mesh, offset: 0 } as GarmentPart],
      pos, seam: new Int32Array(0),
      pinIdx: new Uint32Array(0), pinTarget: new Float32Array(0), total: n,
    }
    const sim = createSim(garment, man)
    const y0 = sim.pos[1]
    for (let k = 0; k < 10; k++) stepSim(sim)
    expect(sim.pos[1]).toBeLessThan(y0)
    for (let i = 0; i < 3 * n; i++) {
      expect(Number.isFinite(sim.pos[i])).toBe(true)
    }
  })
})

describe('heatmap 应变', () => {
  it('静止长 0 / 拉长为正；色带 红-绿-蓝 单调', () => {
    const mesh = buildClothMesh(rectPiece(4, 8))
    const n = mesh.xy.length / 2
    const pos = new Float32Array(3 * n)
    for (let i = 0; i < n; i++) {
      pos[3 * i] = mesh.xy[2 * i]
      pos[3 * i + 1] = 100 + mesh.xy[2 * i + 1]
      pos[3 * i + 2] = 0
    }
    const garment: Garment = {
      parts: [{ key: 'front', side: 'L', mesh, offset: 0 } as GarmentPart],
      pos, seam: new Int32Array(0),
      pinIdx: new Uint32Array(0), pinTarget: new Float32Array(0), total: n,
    }
    const s0 = computeStrain(garment, pos)
    // rest 存 Float32（相对精度 ~1e-7），零应变容差取 1e-5
    for (let i = 0; i < n; i++) expect(Math.abs(s0[i])).toBeLessThan(1e-5)
    pos[2] += 1      // 拉开 0 号粒子：其邻接应变转正
    const s1 = computeStrain(garment, pos)
    expect(s1[0]).toBeGreaterThan(0)
    // 色带：紧=红分量最大、贴合=绿、松=蓝分量最大
    const [rT, , bT] = strainColor(0.08)
    const [, gF] = strainColor(0)
    const [rL, , bL] = strainColor(-0.08)
    expect(rT).toBeGreaterThan(bT)
    expect(gF).toBeGreaterThan(0.7)
    expect(bL).toBeGreaterThan(rL)
  })
})
