// 3D 试穿纯几何/数据层单测（three 不进测试：视图层另行肉眼验收）。
// 金标风格：手工推演值 + 强断言。
//   1. 人台：腰环折线周长 == 体型腰围（±1.5% 标定公差）；radiusAt
//      轴向 == 半轴；sectionAt 端点夹取
//   1b. 互嵌接合：拓扑三盖不共面；嵌入环 containment 金标（上插环退入
//      骨盆 (1−m) 内切 + 48 顶点最坏范数）；接合支撑金标（侧向 emergence
//      带 / 会阴被填带 + 带外逐位零漂移锚）
//   1c. （已迁移）tubeMesh 绕向/水密金标随 tubeMesh 删除整体迁至
//      skin.test.ts——蒙皮三角形法线·∇F>0（外向绕向）+ 无向边恰共享
//      2 次 + 闭合流形 V−E+F=2
//   2. estimateBody：成衣 − 先验松量 + 0.85 下限
//   3. 体型库：默认估计激活、预设存在、自定义增删、JSON 导入导出
//   4. 网格：三角化欧拉公式 V−E+F=1（圆盘）、边名聚合段、locate 权重和 1
//   5. 摆位：左半片 x<=0 / 右半片 x>=0（θ 约定）、前中 +Z / 后中 −Z
//   6. 碰撞：体内粒子推出到 R+skin（radiusAt 单位向量口径强断言——修复
//      前未归一化输入使判据退化为 dist ≥ R/dist，断言空转）
//   6b. 入口守卫：畸形/退化/极端围度 payload 不抛且环严格降序
//   7. PBD：全 pin 收敛 settled 且位置不动；自由落体 y 单调下降且有限
//   8. 应变：静止长 = 0、拉长 > 0；色带 红(紧)/绿(贴合)/蓝(松) 单调
import { describe, expect, it, vi } from 'vitest'
import type { FittingPiece, FittingResult } from '../types'
import { estimateBody, validateGirths } from './bodyProfile'
import {
  BODY_PRESETS, exportProfiles, findProfile, importProfiles, loadStore,
  removeCustom, upsertCustom,
} from './bodyProfileStore'
import { BODY_RATIO } from './priors'
import {
  buildMannequin, radiusAt, ringPoint, sectionAt, superellipsePerimeter,
} from './mannequin'
import { buildClothMesh, runIndexAt } from './mesh'
import { placePoint, surfaceRadius } from './seams'
import { collideOne } from './pbd/collide'
import { createSim, stepSim } from './pbd/solver'
import type { Garment, GarmentPart } from './seams'
import { computeStrain, strainColor } from './heatmap'

// ---- 测试夹具：165/66A 系典型尺寸（与引擎金标 M 同族量级） ----
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
// 夹具站点派生（硬编码高度值会随夹具漂移失联，最坏静默跳过断言环）
const Y_CROTCH = BODY.stations.find((s) => s.key === 'crotch')!.y
const Y_HIP = BODY.stations.find((s) => s.key === 'hip')!.y

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

describe('mannequin 人台', () => {
  it('腰环折线周长标定到体型腰围（±1.5%）', () => {
    const man = buildMannequin(BODY, GIRTHS)
    const waistRing = man.pelvis.rings.find((r) => Math.abs(r.y - 98) < 1e-9)
    expect(waistRing).toBeDefined()
    const per = superellipsePerimeter(
      waistRing!.a, waistRing!.bF, waistRing!.bB, waistRing!.e)
    expect(Math.abs(per - 66) / 66).toBeLessThan(0.015)
    // 臀环同理（站点环精确采样在站点 y 上）
    const hipRing = man.pelvis.rings.find((r) => Math.abs(r.y - 86) < 1e-9)
    const hipPer = superellipsePerimeter(
      hipRing!.a, hipRing!.bF, hipRing!.bB, hipRing!.e)
    expect(Math.abs(hipPer - 90) / 90).toBeLessThan(0.015)
  })

  it('拓扑：躯干顶 = 腰+18、骨盆底 = 裆下楔底、腿顶 = 裆+6 上插、腿底 = 脚口−8', () => {
    const man = buildMannequin(BODY, GIRTHS)
    expect(man.pelvis.rings[0].y).toBeCloseTo(98 + 18, 6)
    // 骨盆底 = 裆 − 5（裆下楔底），不再是裸裆环
    expect(man.pelvis.rings[man.pelvis.rings.length - 1].y)
      .toBeCloseTo(78 - BODY_RATIO.wedgeDropBelowCrotch, 6)
    expect(man.pelvis.rings.length).toBe(13)   // 上段 11 环逐位不变 + 楔 2 环
    // 腿顶上插：min(裆+6, 臀−1) = 84（165/66A = hip−2，不越过臀峰）
    expect(man.legs[0].rings[0].y)
      .toBeCloseTo(Math.min(Y_CROTCH + BODY_RATIO.legRiseAboveCrotch, Y_HIP - 1), 6)
    expect(man.legs[0].rings.length).toBe(26)  // 上插 2 环 + 下段 24 环
    expect(man.legs[0].rings[man.legs[0].rings.length - 1].y).toBeCloseTo(-8, 6)
    // 三盖不共面不变量（z-fighting 根源消除）：楔底 73 / 腿顶 84 / 腿底 −8
    expect(new Set([
      man.pelvis.rings[man.pelvis.rings.length - 1].y,
      man.legs[0].rings[0].y,
      man.legs[0].rings[man.legs[0].rings.length - 1].y,
    ]).size).toBe(3)
    // 双腿中心左右对称（下段 cx 常量 ∓9.9；上插后 ring5 已移至 y≈67.7）
    expect(man.legs[0].rings[5].cx).toBeCloseTo(-man.legs[1].rings[5].cx, 9)
    expect(man.legs[0].rings[5].y).toBeCloseTo(203 / 3, 6)   // 75→42 站 9 等分
  })

  it('嵌入环 containment 金标：上插环整体退入骨盆 (1−m) 内切', () => {
    const man = buildMannequin(BODY, GIRTHS)
    const m = BODY_RATIO.embedMarginRatio
    for (const leg of man.legs) {
      for (const r of leg.rings) {
        if (r.y <= Y_CROTCH) continue
        const P = sectionAt(man.pelvis, r.y)
        expect(Math.abs(r.cx) + r.a)
          .toBeLessThanOrEqual((1 - m) * P.a + 1e-9)
        expect(r.bF).toBeLessThanOrEqual((1 - m) * P.bF + 1e-9)
        expect(r.bB).toBeLessThanOrEqual((1 - m) * P.bB + 1e-9)
      }
    }
    // 手工演算 165/66A（per_hip=5.8997、per_default=6.0161）：
    // 81 环 k = (0.96·aP(81) − 9.9) / a81 = (14.2787 − 9.9) / 6.8211
    //        = 0.6419，恰饱和 |cx|+a = (1−m)·aP(81)（a: 6.8211 → 4.379）；
    // 84 环 k = 1（容纳余量 0.96·aP(84) − 9.9 = 4.793 > a = 4.488，不触发）
    const r81 = man.legs[0].rings.find((r) => Math.abs(r.y - 81) < 1e-9)!
    expect(r81.a).toBeCloseTo(4.379, 3)
    expect(Math.abs(r81.cx) + r81.a)
      .toBeCloseTo((1 - m) * sectionAt(man.pelvis, 81).a, 9)
    // 48 顶点最坏骨盆范数：81 环 +X 极值点恰落 (1−m)·aP 界上，
    // 范数 = (1−m)^e_hip = 0.96^2.3 = 0.9104 < 1（嵌入头整体在骨盆体内，
    // 顶盖零外露）；全上插环上限断言 0.92
    let worst = 0
    for (const leg of man.legs) {
      for (const r of leg.rings) {
        if (r.y <= Y_CROTCH) continue
        const P = sectionAt(man.pelvis, r.y)
        for (let i = 0; i < 48; i++) {
          const [px, pz] = ringPoint(r.a, r.bF, r.bB, r.e, i / 48)
          const norm = Math.pow(Math.abs(r.cx + px) / P.a, P.e)
            + Math.pow(Math.abs(pz) / (pz >= 0 ? P.bF : P.bB), P.e)
          worst = Math.max(worst, norm)
        }
      }
    }
    expect(worst).toBeCloseTo(0.9104, 3)
    expect(worst).toBeLessThanOrEqual(0.92)
  })

  it('接合支撑金标（165/66A 手工演算）', () => {
    const man = buildMannequin(BODY, GIRTHS)
    // 侧向 emergence 带 (78,81)：腿管外缘开始挑大梁，支撑 +2.946(79)/
    // +1.175(80)；81 以上逐位零漂移（surfaceRadius === 骨盆半轴）
    expect(surfaceRadius(man, 79, Math.PI / 2)).toBeCloseTo(17.463, 3)
    expect(surfaceRadius(man, 81, Math.PI / 2))
      .toBeCloseTo(sectionAt(man.pelvis, 81).a, 9)
    // 上段站点表逐位不变锚：82 环 a = 88.8 / per_hip = 15.052
    expect(surfaceRadius(man, 82, Math.PI / 2)).toBeCloseTo(15.052, 3)
    // 会阴被填带 (75.5,78) 后中：+1.395(76)/+3.07(77)——fixture 后浪尖
    // 77.04 落带内（旧口径裆下夹取 78 环导致布料塌陷，属预期口径变更）
    expect(surfaceRadius(man, 76, Math.PI)).toBeCloseTo(9.076, 3)
    // 楔底(73)低于腿撑：74 处支撑仍由腿管决定（带外零漂移锚）
    expect(surfaceRadius(man, 74, Math.PI))
      .toBeCloseTo(sectionAt(man.legs[0], 74).bB, 9)
    expect(sectionAt(man.legs[0], 74).bB).toBeCloseTo(7.575, 3)
  })

  it('radiusAt 轴向收敛到半轴；sectionAt 端点夹取', () => {
    const man = buildMannequin(BODY, GIRTHS)
    const s = sectionAt(man.pelvis, 98)
    expect(radiusAt(s, 1, 0)).toBeCloseTo(s.a, 3)
    expect(radiusAt(s, 0, 1)).toBeCloseTo(s.bF, 3)
    expect(radiusAt(s, 0, -1)).toBeCloseTo(s.bB, 3)
    // 骨盆 y 范围外夹取到端环（同引用值）
    expect(sectionAt(man.pelvis, 999).y).toBe(man.pelvis.rings[0].y)
    expect(sectionAt(man.pelvis, -999).y)
      .toBe(man.pelvis.rings[man.pelvis.rings.length - 1].y)
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
  const man = buildMannequin(BODY, GIRTHS)
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
  const man = buildMannequin(BODY, GIRTHS)
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

describe('buildMannequin 入口守卫（畸形/退化/极端 payload）', () => {
  const strictlyDown = (t: { rings: { y: number }[] }): boolean =>
    t.rings.every((r, i) => i === 0 || t.rings[i - 1].y > r.y)
  // 改站点 y / 追加站点，其余夹具字段不动
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
  it('crotch y=88 ≥ hip 86：clamp 到 hip−2，两管严格降序、containment 不抛', () => {
    const man = buildMannequin(withStations({ crotch: 88 }), GIRTHS)
    expect(strictlyDown(man.pelvis)).toBe(true)
    expect(strictlyDown(man.legs[0])).toBe(true)
    // 腿首环 = min(clamp 裆 84 + 6, 臀 86 − 1) = 85
    expect(man.legs[0].rings[0].y).toBeCloseTo(85, 6)
  })
  it('thigh 站 y=78 == crotch（集成夹具真实场景）：clamp 到 77.5，无重复 y 环', () => {
    const man = buildMannequin(withStations({},
      [{ key: 'thigh', y: 78, girth_finished: null, per: 'leg' }]), GIRTHS)
    expect(strictlyDown(man.legs[0])).toBe(true)
    expect(man.legs[0].rings.some((r) => Math.abs(r.y - 77.5) < 1e-9)).toBe(true)
  })
  it('浅裆（hip 80 / crotch 78，间隔 2 为入口 clamp 下限）：楔独立成立', () => {
    // 注：入口 clamp 保证 yHip−yCrotch ≥ 2，故 yTop ≤ crotch+0.5 的
    // 「放弃上插」分支为防御性代码；本例取 clamp 下限验证浅裆下几何仍完备
    const man = buildMannequin(withStations({ hip: 80 }), GIRTHS)
    expect(man.pelvis.rings[man.pelvis.rings.length - 1].y).toBeCloseTo(73, 6)
    expect(strictlyDown(man.legs[0])).toBe(true)
    expect(man.legs[0].rings[0].y).toBeCloseTo(79, 6)   // min(78+6, 80−1)
  })
  it('极端围度比：hip75×thigh80 / hip130（thigh 缺省）：头环自动退到容纳上限不抛', () => {
    // 隐藏头围挂 hip 派生（0.30×hip），极端 thigh 不影响容纳能力
    const slim = buildMannequin(BODY, { waist: 60, hip: 75, thigh: 80, knee: 32 })
    expect(slim.legs[0].rings[0].y).toBeCloseTo(84, 6)
    const wide = buildMannequin(BODY, { waist: 100, hip: 130, knee: 44 })
    expect(wide.legs[0].rings[0].y).toBeCloseTo(84, 6)
    expect(strictlyDown(wide.legs[0])).toBe(true)
  })
  it('胖腰粗腿病理体型（waist130/hip70/thigh90 逐字段合法）：降级放弃上插不抛', () => {
    // 腰围≫臀围使骨盆裆上环 CR 欠冲（围 ≈0.92×hip）+ 腿头巨大，81 环
    // k ≈ 0.28 < 0.3 真实放不下：整段放弃上插（腿顶回 crotch 平盖旧观感），
    // 不抛错——抛错会被解算层 catch 掉使 3D tab 静默空白；楔与严格降序
    // 不受影响
    const man = buildMannequin(
      BODY, { waist: 130, hip: 70, thigh: 90, knee: 35 })
    expect(strictlyDown(man.pelvis)).toBe(true)
    expect(strictlyDown(man.legs[0])).toBe(true)
    expect(man.legs[0].rings[0].y).toBeCloseTo(Y_CROTCH, 6)   // 上插段整体移除
    expect(man.legs[0].rings.every((r) => r.y <= Y_CROTCH + 1e-9)).toBe(true)
    expect(man.pelvis.rings[man.pelvis.rings.length - 1].y)
      .toBeCloseTo(Y_CROTCH - BODY_RATIO.wedgeDropBelowCrotch, 6)
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
