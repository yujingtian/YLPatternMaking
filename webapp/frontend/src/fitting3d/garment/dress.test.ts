// 穿台集成金标（2026-09-18）：真 base.bin 人台 + fixture 整裤全链
// （锚定 → 人台环场 → 腿轴 → 摆位 → settle 落位 → 读数）。与 Fitting3DView
// dress 分支同源管线（本文件是它的无渲染镜像）。验收口径：
// · anchorLift canary ≈ +7.6（人台腰地标 105.644 − 纸样腰站 98——量级
//   把门：θ/坐标系错位会差出几十 cm）
// · θ 对齐 canary：前中腰角 z>0 / 后中腰角 z<0（纸样系与人台 +Z=前同构）
// · 裆地标下方 forkSearch 窗内存在双腿分离行（腿轴成立前提）
// · 初摆位 pointInRings 计数 = 0（摆位按构造体外——穿模把门）
// · 跑至 done：无 NaN、裆四尖两两 <1.0、dropF/dropB ∈ [0, maxDrop]、
//   下摆离地；**同输入双跑 DressReport 逐字段相等**（确定性——单跑
//   比较无意义红线）
// · hips+ 负松量探索例：不炸、收敛、读数在值域（宽松断言——偏小是
//   读数不是错误）
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../types'
import type { BodyMeshAsset } from '../bodymesh/bin'
import { parseBaseBin } from '../bodymesh/bin'
import type { MeshWeights } from '../bodymesh/morph'
import { morphPositions } from '../bodymesh/morph'
import { stationFactor } from '../bodymesh/height'
import { buildFullPair } from './assemble'
import {
  buildBodyField, buildLegAxisFromRings, pointInRings, shiftPositionsY,
} from './placement'
import { buildDrape, stepDrape, type DrapeSim } from './drape'
import { buildBackPanel, buildFrontPanel } from './panel'
import { buildWaistbandMesh } from './band'
import {
  buildCrotchProbeIdx, buildSettle, type DressReport, type SettleController,
  type SettlePhase,
} from './settle'
import { DRESSING_PRIOR, FIELD_PRIOR } from './priors'

const HERE = import.meta.dirname   // src/fitting3d/garment
const PUB = `${HERE}/../../../public/bodymesh`

// 真产物人台（bodymesh.test 同源路径；补 landmarks——loadBodyMesh fetch 版
// 的磁盘镜像，dress 分支依赖 a.landmarks.waist/crotch 锚定）
function loadBodyFromDisk(): BodyMeshAsset {
  const meta = JSON.parse(readFileSync(`${PUB}/targets.json`, 'utf8'))
  const { positions, indices, fields } = parseBaseBin(
    readFileSync(`${PUB}/base.bin`).buffer.slice(0))
  const lmRaw = (meta.landmarkHeights ?? {}) as Record<string, number>
  const landmarks: BodyMeshAsset['landmarks'] = {}
  for (const k of ['sole', 'crotch', 'waist', 'hip', 'knee', 'calf', 'ankle'] as const) {
    if (typeof lmRaw[k] === 'number') landmarks[k] = lmRaw[k]
  }
  return {
    positions, indices,
    targets: fields.map((f, k) => ({ ...f, name: meta.targets[k].name })),
    stations: {}, landmarks,
    height: meta.cut.planeY as number,
    heightInfo: {
      baseCm: meta.height.baseCm as number,
      plusCm: meta.height.plusCmAtW1 as number,
      minusCm: meta.height.minusCmAtW1 as number,
    },
  } as BodyMeshAsset
}

interface RunOut {
  sim: DrapeSim
  pair: ReturnType<typeof buildFullPair>
  ctrl: SettleController
  ph: SettlePhase
  report: DressReport
  anchorLift: number
}

// 穿台全管线（Fitting3DView dress 分支同源；heightW=0 地标因子 1）
function runDress(
  a: BodyMeshAsset, data: FittingResult, w: MeshWeights,
): RunOut {
  const lmWaist = a.landmarks.waist!
  const lmCrotch = a.landmarks.crotch!
  const lmAnkle = a.landmarks.ankle!
  const sf = stationFactor(a.heightInfo, 0)
  const waistSt = data.body.stations.find((s) => s.key === 'waist')!
  const anchorLift = lmWaist * sf - waistSt.y
  const mesh = Object.keys(w).length ? morphPositions(a, w) : a.positions
  // 场域下探脚底 + 腿轴止踝（2026-09-18 脚碰撞修复，与视图分支同步）
  const fieldYMin = Math.floor(-anchorLift / FIELD_PRIOR.rowStep) * FIELD_PRIOR.rowStep
  const fieldM = buildBodyField(
    shiftPositionsY(mesh, -anchorLift), a.indices, fieldYMin)
  const legAxisM = buildLegAxisFromRings(
    fieldM, lmCrotch * sf - anchorLift, lmAnkle * sf - anchorLift)
  const panel = buildFrontPanel(data)
  const backPanel = buildBackPanel(data)
  const bandMesh = buildWaistbandMesh(data)
  const pair = buildFullPair(panel.host, backPanel.host, fieldM, {
    front: legAxisM.forkY, back: legAxisM.forkY,
  }, legAxisM, bandMesh, anchorLift)
  const sim = buildDrape(pair, fieldM, anchorLift)
  const ctrl = buildSettle(sim, buildCrotchProbeIdx(pair))
  let ph: SettlePhase = ctrl.phase
  for (let k = 0; k < DRESSING_PRIOR.maxTotalFrames + 10 && ph !== 'done'; k++) {
    stepDrape(sim)
    ph = ctrl.step(sim)
  }
  return { sim, pair, ctrl, ph, report: ctrl.report(sim), anchorLift }
}

const expectFinite = (pos: Float32Array): void => {
  for (let i = 0; i < pos.length; i++) {
    expect(Number.isFinite(pos[i]), `pos[${i}] finite`).toBe(true)
  }
}

// 裆四尖两两最大距（drape.test 同手法）
const tipWorstDist = (sim: DrapeSim): number => {
  const tips: number[] = []
  for (const g of sim.seamGroups) {
    if (g.name !== 'tipL' && g.name !== 'tipR') continue
    for (let p = 0; p < g.pairCount; p++) {
      tips.push(sim.seamIdx[2 * (g.pairOffset + p)],
        sim.seamIdx[2 * (g.pairOffset + p) + 1])
    }
  }
  expect(tips.length).toBe(4)
  let worst = 0
  for (let a = 0; a < 4; a++) {
    for (let b = a + 1; b < 4; b++) {
      worst = Math.max(worst, Math.hypot(
        sim.pos[3 * tips[a]] - sim.pos[3 * tips[b]],
        sim.pos[3 * tips[a] + 1] - sim.pos[3 * tips[b] + 1],
        sim.pos[3 * tips[a] + 2] - sim.pos[3 * tips[b] + 2]))
    }
  }
  return worst
}

describe('穿台集成（真 base.bin + fixture 基础款）', () => {
  it('锚定/摆位 canary + 落位收敛 + 双跑确定性', () => {
    const a = loadBodyFromDisk()
    const data = JSON.parse(
      readFileSync(`${HERE}/fixture_fitting.json`, 'utf8')) as FittingResult
    // ---- 锚定 canary：人台腰地标 vendor 契约 + anchorLift 量级 ----
    expect(a.landmarks.waist).toBeCloseTo(105.644, 1)
    const out1 = runDress(a, data, {})
    // 纸样腰站 98 → anchorLift = 105.644 − 98 ≈ +7.644（θ/坐标系错位会
    // 差出几十 cm，量级即把门）
    expect(out1.anchorLift).toBeGreaterThan(7.0)
    expect(out1.anchorLift).toBeLessThan(8.3)
    // ---- θ 对齐 canary：前中腰角 z>0（+Z=前）、后中腰角 z<0 ----
    const fL = out1.pair.parts[0]   // front L（buildFullPair 固定序）
    const bL = out1.pair.parts[2]   // back L
    const rise = fL.mesh.runs.find((r) => r.name === 'rise')
    const cb = bL.mesh.runs.find((r) => r.name === 'cb')
    expect(rise).toBeDefined()
    expect(cb).toBeDefined()
    const fTop = out1.pair.pos[3 * (fL.offset + rise!.indices[rise!.indices.length - 1]) + 2]
    const bTop = out1.pair.pos[3 * (bL.offset + cb!.indices[cb!.indices.length - 1]) + 2]
    expect(fTop).toBeGreaterThan(0)
    expect(bTop).toBeLessThan(0)
    // ---- 初摆位零穿透（腿区绕管半径 = rAt+skin+gap 按构造体外）----
    let inside = 0
    for (let i3 = 0; i3 < out1.pair.pos.length; i3 += 3) {
      const rings = (out1.sim.field as NonNullable<DrapeSim['field']>)
        .loopsAt(out1.pair.pos[i3 + 1] - out1.sim.yLift)
      if (rings.length > 0
        && pointInRings(out1.pair.pos[i3], out1.pair.pos[i3 + 2], rings)) {
        inside++
      }
    }
    expect(inside).toBe(0)
    // ---- 落位收敛 ----
    expect(out1.ph).toBe('done')
    expectFinite(out1.sim.pos)
    expect(tipWorstDist(out1.sim)).toBeLessThan(1.0)
    // 掉裆：前裆锚腰后顶入 ~7cm → 预期掉 ~7 量级；域 [0, maxDrop]
    expect(out1.report.dropF).toBeGreaterThanOrEqual(2.0)
    expect(out1.report.dropF).toBeLessThanOrEqual(DRESSING_PRIOR.maxDrop + 1e-6)
    expect(out1.report.dropB).toBeGreaterThanOrEqual(-1e-6)
    expect(out1.report.dropB).toBeLessThanOrEqual(DRESSING_PRIOR.maxDrop + 1e-6)
    // 下摆：掉裆 ~7cm 后裤脚可及地（腰锚 7.64 − 前掉 ≈7 → 地面网钳 0——
    // 真人掉裆裤脚拖地的对应；旁挂 hangLift 12 才有离地余量），只把门
    // 地面网不破（无穿透到地下）
    let minY = Infinity
    for (let i = 1; i < out1.sim.pos.length; i += 3) {
      minY = Math.min(minY, out1.sim.pos[i])
    }
    expect(minY).toBeGreaterThanOrEqual(-1e-6)
    // ---- 同输入双跑 DressReport 逐字段相等（确定性红线）----
    const out2 = runDress(a, data, {})
    const r1 = out1.report, r2 = out2.report
    for (const key of ['dropF', 'dropB', 'worstPen', 'worstPenY', 'frames'] as const) {
      expect(r2[key], key).toBe(r1[key])
    }
    expect(r2.contactF).toEqual(r1.contactF)
    expect(r2.contactB).toEqual(r1.contactB)
    expect(r2.tooSmall).toBe(r1.tooSmall)
    expect(r2.capped).toBe(r1.capped)
    expect(Array.from(out2.sim.pos)).toEqual(Array.from(out1.sim.pos))
    // 单跑 ~230s；全量并行负载下实测 286s——超时裕度给到 480s（双跑含
    // 两遍 maxTotalFrames 全解算，是全仓最重用例）
  }, 480_000)

  it('hips+ 负松量探索例：不炸、收敛、读数在值域（宽松）', () => {
    const a = loadBodyFromDisk()
    const data = JSON.parse(
      readFileSync(`${HERE}/fixture_fitting.json`, 'utf8')) as FittingResult
    const out = runDress(a, data, { 'hips+': 1 })
    expect(out.ph).toBe('done')
    expectFinite(out.sim.pos)
    expect(out.report.dropF).toBeLessThanOrEqual(DRESSING_PRIOR.maxDrop + 1e-6)
    expect(out.report.dropB).toBeLessThanOrEqual(DRESSING_PRIOR.maxDrop + 1e-6)
    // 偏小（穿透未解/fault）是读数不是错误——本例只验不炸不飞
  }, 300_000)
})
