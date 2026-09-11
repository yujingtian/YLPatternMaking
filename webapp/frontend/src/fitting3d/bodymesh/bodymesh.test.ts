// bodymesh 模块合成网格金标（node vitest 无 fetch/public——真数据金标在
// Python 侧 tests/test_vendor_bodymesh.py；此处验证 TS 链路数学：切片/
// morph/对齐/围度闭环/高度场/整链 buildMeshMannequin）。
// 合成体：躯干椭圆管（a=8、b=6，y∈[30,50]）+ 双腿圆柱（r=4、x=±5、
// y∈[0,30]），环距 2.5、24 边侧壁三角带（封盖不必要：切片环/碰撞/渲染
// 测试只消费侧壁；crotch=30、hem=0、knee=15 与 payload 站恒等 -> 对齐
// a=1、b=0 精确可断言）。两个 target：waist+ = 躯干环径向 ×10%
//（crotch 环除外）-> 围度解析 g(w)=g0·(1+0.1w)；thigh+ = 腿环
// y∈(20,30) 绕腿轴径向 ×10%（盖 thigh 站 27、不碰 knee 站 15）——
// 派生径向保形场的合成替身（宽钳档）。
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../types'
import type { BodyGirths } from '../bodyProfile'
import { BODYMESH_PRIOR } from '../priors'
import { radiusAt, sectionAt } from '../mannequin'
import { applyVertical, fitVerticalAlign } from './align'
import { buildMeshMannequin } from './build'
import { calibrateWeights } from './calibrate'
import { buildTubeFields, sampleField } from './heightfield'
import { morphPositions } from './morph'
import { sliceLoops, stationGirth } from './slice'
import type { BodyMeshAsset, BodyMeshMeta, CalibrationMatrix, TargetName } from './types'

const SEG = 24

function syntheticBody(): { positions: Float32Array; indices: Uint32Array } {
  const pos: number[] = []
  const idx: number[] = []
  const band = (
    y0: number, y1: number, fx: (th: number) => [number, number],
  ) => {
    const ring = (y: number) => {
      const base = pos.length / 3
      for (let i = 0; i < SEG; i++) {
        const [x, z] = fx((i / SEG) * Math.PI * 2)
        pos.push(x, y, z)
      }
      return base
    }
    const r0 = ring(y0), r1 = ring(y1)
    for (let i = 0; i < SEG; i++) {
      const a = r0 + i, b = r0 + (i + 1) % SEG
      const c = r1 + (i + 1) % SEG, d = r1 + i
      idx.push(a, b, c, a, c, d)
    }
  }
  const torso = (th: number): [number, number] => [8 * Math.sin(th), 6 * Math.cos(th)]
  for (let y = 50; y > 30 + 1e-9; y -= 2.5) {
    band(y, Math.max(y - 2.5, 30), torso)
  }
  const leg = (cx: number) => (th: number): [number, number] =>
    [cx + 4 * Math.sin(th), 4 * Math.cos(th)]
  for (const cx of [-5, 5]) {
    for (let y = 30; y > 0 + 1e-9; y -= 2.5) {
      band(y, Math.max(y - 2.5, 0), leg(cx))
    }
  }
  return {
    positions: new Float32Array(pos),
    indices: new Uint32Array(idx),
  }
}

// 首个满足谓词的顶点号（地标选取：躯干带先建 -> y=30 首命中即躯干环）
function findVertex(
  pos: Float32Array, pred: (x: number, y: number, z: number) => boolean,
): number {
  for (let i = 0; i < pos.length / 3; i++) {
    if (pred(pos[3 * i], pos[3 * i + 1], pos[3 * i + 2])) return i
  }
  throw new Error('合成网格找不到地标顶点')
}

function syntheticAsset(): BodyMeshAsset {
  const { positions, indices } = syntheticBody()
  const V = positions.length / 3
  // waist+ 增量：躯干 y>30 环径向 ×10%（crotch 环不动）
  const tIdx: number[] = []
  const tD: number[] = []
  for (let i = 0; i < V; i++) {
    const x = positions[3 * i], y = positions[3 * i + 1], z = positions[3 * i + 2]
    if (y > 30 + 1e-9) {
      tIdx.push(i)
      tD.push(0.1 * x, 0, 0.1 * z)
    }
  }
  const idx = new Uint32Array(tIdx)
  const d = new Float32Array(tD)
  // thigh+ 增量：腿环 y∈(20,30) 绕各自腿轴径向 ×10%
  const t2Idx: number[] = []
  const t2D: number[] = []
  for (let i = 0; i < V; i++) {
    const x = positions[3 * i], y = positions[3 * i + 1], z = positions[3 * i + 2]
    if (y > 20 + 1e-9 && y < 30 - 1e-9) {
      const cx = x > 0 ? 5 : -5
      t2Idx.push(i)
      t2D.push(0.1 * (x - cx), 0, 0.1 * z)
    }
  }
  const idx2 = new Uint32Array(t2Idx)
  const d2 = new Float32Array(t2D)
  // 预标定矩阵（解析）：waist+ 影响躯干站（waist/hips 均缩放）、thigh+
  // 只影响 thigh 站；其余站不受影响
  const g0 = (y: number, per: 'body' | 'leg') =>
    stationGirth(positions, indices, y, per)!
  const gW = g0(40, 'body'), gH = g0(35, 'body')
  const gT = g0(27, 'leg'), gK = g0(15, 'leg')
  const sc = (g: number): (number | null)[] => [g, g * 1.05, g * 1.1]
  const flat = (g: number): (number | null)[] => [g, g, g]
  const calibration = {} as CalibrationMatrix
  for (const t of ['waist+', 'waist-', 'hips+', 'hips-',
    'thigh+', 'thigh-', 'knee+', 'knee-'] as TargetName[]) {
    calibration[t] = { waist: [null, null, null], hips: [null, null, null],
      thigh: [null, null, null], knee: [null, null, null] }
  }
  calibration['waist+'] = {
    waist: sc(gW), hips: sc(gH), thigh: flat(gT), knee: flat(gK),
  }
  calibration['thigh+'] = {
    waist: flat(gW), hips: flat(gH), thigh: sc(gT), knee: flat(gK),
  }
  const meta: BodyMeshMeta = {
    vertexCount: V,
    triangleCount: indices.length / 3,
    targets: [{ name: 'waist+', file: 'synthetic', count: idx.length },
      { name: 'thigh+', file: 'synthetic', count: idx2.length }],
    landmarks: {
      sole: findVertex(positions, (_x, y, _z) => y < 1e-9),
      crotch: findVertex(positions, (_x, y, _z) => Math.abs(y - 30) < 1e-9),
      knee: findVertex(positions, (_x, y, _z) => Math.abs(y - 15) < 1e-9),
    },
    landmarkHeights: {},
    cut: { aboveWaistCm: 0, planeY: 50 },
    stations: [
      { name: 'waist', per: 'body', y: 40 },
      { name: 'hips', per: 'body', y: 35 },
      { name: 'thigh', per: 'leg', y: 27 },
      { name: 'knee', per: 'leg', y: 15 },
    ],
    calibration,
  }
  return {
    positions, indices,
    targets: [{ name: 'waist+', idx, d }, { name: 'thigh+', idx: idx2, d: d2 }],
    meta,
  }
}

const BODY: FittingResult['body'] = {
  stations: [
    { key: 'waist', y: 40, girth_finished: 60, per: 'body' },
    { key: 'hip', y: 35, girth_finished: 80, per: 'body' },
    { key: 'crotch', y: 30, girth_finished: null, per: 'body' },
    { key: 'knee', y: 15, girth_finished: 25, per: 'leg' },
    { key: 'hem', y: 0, girth_finished: 25, per: 'leg' },
  ],
  points: { front_crotch_vertex: [15, 30], back_crotch_vertex: [30, 29] },
  crotch_drop: 1, waistband_width: 4, waistband_type: 'straight', outseam: 70,
}

describe('bodymesh 合成网格链路', () => {
  const asset = syntheticAsset()
  const { positions, indices } = asset

  it('slice：躯干单环椭圆周长 / 双腿环 / per=leg 取右腿', () => {
    const loops40 = sliceLoops(positions, indices, 40)
    expect(loops40).toHaveLength(1)
    expect(loops40[0].closed).toBe(true)
    // Ramanujan 椭圆周长 π[3(a+b)−√((3a+b)(a+3b))] ≈ 44.20；24 边内接折线
    // 偏低 ~0.5%
    expect(loops40[0].girth).toBeGreaterThan(43.5)
    expect(loops40[0].girth).toBeLessThan(44.2)
    const loops15 = sliceLoops(positions, indices, 15)
    expect(loops15).toHaveLength(2)
    expect(loops15.every((l) => l.closed)).toBe(true)
    // 右腿（cx>0）：24 边内接圆周 2×24×4×sin(π/24) ≈ 25.06
    const g = stationGirth(positions, indices, 15, 'leg')
    expect(g!).toBeGreaterThan(24.8)
    expect(g!).toBeLessThan(25.14)
  })

  it('morph：稀疏叠加精确、未列入顶点不动', () => {
    const i0 = asset.targets[0].idx[0]
    const x0 = positions[3 * i0], z0 = positions[3 * i0 + 2]
    const out = morphPositions(asset, { 'waist+': 0.5 })
    expect(out.length).toBe(positions.length)
    expect(out[3 * i0]).toBeCloseTo(x0 * 1.05, 5)   // float32 存储舍入
    expect(out[3 * i0 + 2]).toBeCloseTo(z0 * 1.05, 5)
    const out0 = morphPositions(asset, {})
    for (let k = 0; k < positions.length; k++) {
      expect(out0[k]).toBe(positions[k])   // w=0 逐位恒等
    }
  })

  it('align：节点精确过点 + 段内线性 + 顶上斜率 1.0；applyVertical 只动 y', () => {
    const al = fitVerticalAlign(
      { crotch: 30, knee: 15, sole: 0 },
      { crotch: 30, knee: 15, hem: 0 })
    expect(al.mapY(0)).toBeCloseTo(0, 9)
    expect(al.mapY(15)).toBeCloseTo(15, 9)
    expect(al.mapY(30)).toBeCloseTo(30, 9)
    expect(al.mapY(50)).toBeCloseTo(50, 9)   // 顶上斜率 1.0
    expect(al.groundY).toBeCloseTo(0, 9)
    // 真数据口径（mesh 短大腿/长躯干 vs payload）：四节点精确 + 中点线性插值
    //   段斜率：膝上 36/29.5=1.2203、裆上 20/27.0=0.7407（仿射单尺度两头顾不上）
    const al2 = fitVerticalAlign(
      { sole: 0, knee: 47.144, crotch: 76.644, waist: 103.64 },
      { hem: 0, knee: 42, crotch: 78, waist: 98 })
    expect(al2.mapY(0)).toBeCloseTo(0, 9)
    expect(al2.mapY(47.144)).toBeCloseTo(42, 9)
    expect(al2.mapY(76.644)).toBeCloseTo(78, 9)
    expect(al2.mapY(103.64)).toBeCloseTo(98, 9)
    expect(al2.mapY(60)).toBeCloseTo(42 + (36 / 29.5) * (60 - 47.144), 6)
    expect(al2.mapY(118.64)).toBeCloseTo(113, 9)   // 98 + (118.64−103.64)
    // 逆映射回环（含顶上段直解 + 下方二分）
    expect(al2.unmapY(98)).toBeCloseTo(103.64, 6)
    expect(al2.unmapY(al2.mapY(60))).toBeCloseTo(60, 6)
    expect(al2.unmapY(110)).toBeCloseTo(115.64, 9)
    // 比例退化节点丢弃：waist 与 crotch 重合 -> 退化为三点分段仍可用
    const al3 = fitVerticalAlign(
      { sole: 0, knee: 47, crotch: 76.6, waist: 76.6 },
      { hem: 0, knee: 42, crotch: 78, waist: 98 })
    expect(al3.nodes.length).toBe(3)
    expect(al3.mapY(76.6)).toBeCloseTo(78, 9)
    // 踝路径（真数据口径，地标高度取自真资产）：踝精确过点、脚底 slope 1.0
    // 保真脚高、膝-踝段独立定斜率 44/34.562（脚整体落在腿场底之下）
    const al4 = fitVerticalAlign(
      { sole: 0.47, ankle: 13.5, knee: 48.062, crotch: 80.562 },
      { hem: 0, ankle: -2, knee: 42, crotch: 78 })
    expect(al4.mapY(13.5)).toBeCloseTo(-2, 9)
    expect(al4.mapY(0.47)).toBeCloseTo(-2 - 13.03, 9)
    expect(al4.groundY).toBeCloseTo(-2 - 13.5, 9)   // mapY(0)：mesh y=0 再低 0.47
    expect(al4.mapY(48.062)).toBeCloseTo(42, 9)
    expect(al4.mapY(30)).toBeCloseTo(42 - (44 / 34.562) * (48.062 - 30), 6)
    expect(al4.unmapY(-2)).toBeCloseTo(13.5, 6)
    const pos = new Float32Array([1, 10, 2, -3, 20, 4])
    const mapped = applyVertical(pos, al2)
    expect(mapped[0]).toBe(1)
    expect(mapped[2]).toBe(2)
    expect(mapped[3]).toBe(-3)
    expect(mapped[1]).toBeCloseTo(al2.mapY(10), 5)   // float32 存储舍入
    expect(pos[1]).toBe(10)   // 原数组不被改写
  })

  it('heightfield：三管 R(y,θ) 与合成体表一致；裆下并集保守', () => {
    const f = buildTubeFields(positions, indices, {
      crotch: 30, top: 50, pelvisBottom: 27, legTop: 37, legBottom: -2,
    })
    // 骨盆：腰带椭圆半轴 θ=0 前向 6 / θ=90° 侧向 8（±0.1 表离散）
    expect(sampleField(f.pelvis, 40, 0)).toBeCloseTo(6, 1)
    expect(sampleField(f.pelvis, 40, Math.PI / 2)).toBeCloseTo(8, 1)
    // 腿：膝带圆柱 r=4（相对腿轴 cx≈5）
    expect(sampleField(f.legR, 15, 0)).toBeCloseTo(4, 1)
    expect(sampleField(f.legL, 15, Math.PI / 2)).toBeCloseTo(4, 1)
    // 裆下（<crotch）骨盆 = 双腿并集：侧向 R ≈ 5+4 = 9
    expect(sampleField(f.pelvis, 28, Math.PI / 2)).toBeCloseTo(9, 1)
    // 头带（>crotch 单环分喂）：R 相对腿轴，外缘 cx+R ≈ 8（躯干半宽连续）
    const row33 = Math.round((f.legR.yTop - 33) / f.legR.dy)
    expect(f.legR.cx[row33] + sampleField(f.legR, 33, Math.PI / 2))
      .toBeCloseTo(8, 1)
    // 底部越界（脚口下延伸行持有）：不 NaN、有限
    expect(Number.isFinite(sampleField(f.legR, -1, 0))).toBe(true)
    // 轴符号：右腿正、左腿负（rows 抽查）
    expect(f.legR.cx[f.legR.rows - 1]).toBeGreaterThan(4)
    expect(f.legL.cx[f.legL.rows - 1]).toBeLessThan(-4)
  })

  it('calibrate：差分雅可比反演收敛到 w≈0.2（阻尼+容差内）', () => {
    const gW = stationGirth(positions, indices, 40, 'body')!
    const gH = stationGirth(positions, indices, 35, 'body')!
    const gT = stationGirth(positions, indices, 27, 'leg')!
    const gK = stationGirth(positions, indices, 15, 'leg')!
    const res = calibrateWeights(asset,
      { waist: gW * 1.02, hip: gH * 1.02, thigh: gT, knee: gK },
      { waist: 40, hips: 35, thigh: 27, knee: 15 })
    expect(res.converged).toBe(true)
    // g(w)=g0(1+0.1w) -> 目标 +2% 即 w=0.2；阻尼 0.8 + 容差 0.015 下
    // 迭代停在 |残差|<1.5%（w≈0.16 即达标，0.1~0.3 窗口收纳）
    const w = res.weights['waist+'] ?? 0
    expect(w).toBeGreaterThan(0.1)
    expect(w).toBeLessThan(0.3)
    expect(Math.abs(res.residual.waist)).toBeLessThan(0.015)
    expect(Math.abs(res.residual.knee)).toBeLessThan(1e-9)
  })

  it('calibrate：耦合联立——waist+ 溢出 hips 站一并满足（最小权重无对消）', () => {
    const gW = stationGirth(positions, indices, 40, 'body')!
    const gH = stationGirth(positions, indices, 35, 'body')!
    const gT = stationGirth(positions, indices, 27, 'leg')!
    const gK = stationGirth(positions, indices, 15, 'leg')!
    // 合成 waist+ 场同时缩放 waist/hips 两站（cos² 窗重叠耦合的合成替身）；
    // hips+ target 不存在（响应列全 0）——差分雅可比量出溢出后由 waist+
    // 一并满足两站，不需要（也不允许）另起 hips 权重对消。单 target 对角
    // 近似（旧三点表反演）hips+ 行为 null，hips 误差恒 5% 永不收敛
    const res = calibrateWeights(asset,
      { waist: gW * 1.05, hip: gH * 1.05, thigh: gT, knee: gK },
      { waist: 40, hips: 35, thigh: 27, knee: 15 })
    expect(res.converged).toBe(true)
    const w = res.weights['waist+'] ?? 0
    expect(w).toBeGreaterThan(0.3)
    expect(w).toBeLessThan(0.5)
    expect(res.weights['hips+'] ?? 0).toBe(0)
    expect(res.weights['hips-'] ?? 0).toBe(0)
    expect(Math.abs(res.residual.hips)).toBeLessThan(0.015)
  })

  it('calibrate：分档钳界——原生 target 钳 nativeWeightClamp、派生 thigh 宽钳 weightClamp', () => {
    const gW = stationGirth(positions, indices, 40, 'body')!
    const gH = stationGirth(positions, indices, 35, 'body')!
    const gT = stationGirth(positions, indices, 27, 'leg')!
    const gK = stationGirth(positions, indices, 15, 'leg')!
    // 极端腰目标（w 需 3.0）：原生档钳 nativeWeightClamp=1.0（作者化域
    // [0,1] 外位移分布未作者化），欠量残差披露不静默收敛（2026-09-11
    // 扭曲报障的合成金标）
    const rw = calibrateWeights(asset,
      { waist: gW * 1.3, hip: gH, thigh: gT, knee: gK },
      { waist: 40, hips: 35, thigh: 27, knee: 15 })
    expect(rw.converged).toBe(false)
    expect(rw.weights['waist+']).toBe(BODYMESH_PRIOR.nativeWeightClamp)
    expect(rw.residual.waist).toBeLessThan(0)      // 欠量（正=偏大）
    // 极端大腿目标（同需 w=3.0）：派生径向场宽钳 weightClamp=2.0
    const rt = calibrateWeights(asset,
      { waist: gW, hip: gH, thigh: gT * 1.3, knee: gK },
      { waist: 40, hips: 35, thigh: 27, knee: 15 })
    expect(rt.converged).toBe(false)
    expect(rt.weights['thigh+']).toBe(BODYMESH_PRIOR.weightClamp)
    expect(rt.residual.thigh).toBeLessThan(0)
  })

  it('buildMeshMannequin：整链出口契约（环降序/hf/bottomY/围度/半径）', () => {
    const gW = stationGirth(positions, indices, 40, 'body')!
    const gH = stationGirth(positions, indices, 35, 'body')!
    const gT = stationGirth(positions, indices, 27, 'leg')!
    const gK = stationGirth(positions, indices, 15, 'leg')!
    const girths: BodyGirths = {
      waist: gW * 1.02, hip: gH * 1.02, thigh: gT, knee: gK,
    }
    const man = buildMeshMannequin(asset, BODY, girths)
    expect(man.sourceMesh).toBeDefined()
    expect(man.bottomY).toBeCloseTo(0, 6)      // sole↔hem 恒等对齐
    expect(man.topY).toBeCloseTo(50, 1)
    // 管环 y 严格降序 + hf 柄传播
    for (const tube of [man.pelvis, man.legs[0], man.legs[1]]) {
      for (let i = 1; i < tube.rings.length; i++) {
        expect(tube.rings[i - 1].y).toBeGreaterThan(tube.rings[i].y)
      }
      expect(tube.rings[0].hf).toBeDefined()
    }
    // 左右腿管轴符号
    const cxR = man.legs[1].rings[man.legs[1].rings.length - 1].cx
    expect(cxR).toBeGreaterThan(4)
    expect(man.legs[0].rings[man.legs[0].rings.length - 1].cx).toBeLessThan(-4)
    // 适配层查询：radiusAt 走 hf 查表（θ=0 前向 ≈ 6×1.02、θ=90° ≈ 8×1.02）
    const s40 = sectionAt(man.pelvis, 40)
    expect(radiusAt(s40, 0, 1)).toBeCloseTo(6 * 1.016, 1)
    expect(radiusAt(s40, 1, 0)).toBeCloseTo(8 * 1.016, 1)
    const s15 = sectionAt(man.legs[1], 15)
    expect(radiusAt(s15, 0, 1)).toBeCloseTo(4, 1)
    // morph 后源网格站点围度 = 目标 ±1.5%（同环标定口径）
    const gAfter = stationGirth(man.sourceMesh!.positions,
      man.sourceMesh!.indices, 40, 'body')!
    expect(Math.abs(gAfter - girths.waist) / girths.waist).toBeLessThan(0.015)
    const gKnee = stationGirth(man.sourceMesh!.positions,
      man.sourceMesh!.indices, 15, 'leg')!
    expect(Math.abs(gKnee - girths.knee) / girths.knee).toBeLessThan(0.001)
  })
})
