// 穿台集成金标（2026-09-18）：真 base.bin 人台 + fixture 整裤全链
// （锚定 → 人台环场 → 腿轴 → 摆位 → settle 落位 → 读数）。与 Fitting3DView
// dress 分支同源管线（本文件是它的无渲染镜像）。验收口径：
// · anchorLift canary ≈ +7.6（人台腰地标 105.644 − 纸样腰站 98——量级
//   把门：θ/坐标系错位会差出几十 cm）
// · θ 对齐 canary：前中腰角 z>0 / 后中腰角 z<0（纸样系与人台 +Z=前同构）
// · 裆地标下方 forkSearch 窗内存在双腿分离行（腿轴成立前提）
// · 初摆位 pointInRings 计数 = 0（摆位按构造体外——穿模把门）
// · 腰圈钉环（2026-09-19 形随体长随衣）：环长 = 成衣腰长；身片顶链/
//   腰头两缘 3D 弦和 ≈ 成衣腰长（钉间距 = 纸样边长、零应变摆位）；
//   钉集带符号间隙贴体（后腰 ~0 起）且微隙为截面比例量级（非旧 1.2 垫）
// · 跑至 done：无 NaN、裆四尖两两 <1.0、dropF/dropB ∈ [0, maxDrop]、
//   下摆离地；**同输入双跑 DressReport 逐字段相等**（确定性——单跑
//   比较无意义红线）
// · 脚口前缘挂扣（2026-09-19（二））：脚口环带刚度（priors
//   hemBandStiffness，真实双折卷边硬圈）保持前缘挂在脚背上——脚口
//   前向 z ≥7（挂扣态 ~7.9，脱扣态 ~3 = 前缘滑过脚背冠到脚后）；根因
//   曾误判脚碰撞缺陷，实为钉环贴体→掉裆加深拖脱，见决策日志当日条
// · hips+ 负松量探索例：不炸、收敛、读数在值域（宽松断言——偏小是
//   读数不是错误）
// · 偏小款快检（只摆位不解算）：成衣腰长 −4 → 钉环 s<1 整圈嵌体 +
//   热力图 gap 带符号负值红区（「穿不进需要在热力图中体现」把门）
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
  buildBodyField, buildLegAxisFromRings, buildWaistRing, nearestRingBoundary,
  pointInRings, shiftPositionsY, type WaistRing,
} from './placement'
import { buildDrape, stepDrape, type DrapeSim } from './drape'
import { buildBackPanel, buildFrontPanel } from './panel'
import { bandBottomChain, buildWaistbandMesh, ringWalk } from './band'
import { computeHeat } from './heatmap'
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
  waistLen: number
  waistRing: WaistRing
}

// 穿台全管线（Fitting3DView dress 分支同源；heightW=0 地标因子 1）。
// opts：waistDelta 压制成衣腰长（偏小款快检）；maxFrames 0 = 只摆位不解算
function runDress(
  a: BodyMeshAsset, data: FittingResult, w: MeshWeights,
  opts?: { waistDelta?: number; maxFrames?: number },
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
  // 腰圈钉环（2026-09-19 形随体长随衣）：尺寸 = 成衣腰长（优先腰头带底
  // 净长——收省后口径；回退腰站 girth_finished），视图 dress 分支同源
  const waistLen0 = (bandMesh && bandBottomChain(bandMesh)?.runLength)
    ?? waistSt.girth_finished
  if (waistLen0 == null) {
    throw new Error('缺成衣腰长（腰头带底净长/腰站 girth_finished 均缺）——穿台无法定腰圈钉环')
  }
  const waistLen = waistLen0 - (opts?.waistDelta ?? 0)
  const waistRing = buildWaistRing(fieldM, waistSt.y, waistLen)
  const pair = buildFullPair(panel.host, backPanel.host, fieldM, {
    front: legAxisM.forkY, back: legAxisM.forkY,
  }, legAxisM, bandMesh, anchorLift, waistRing)
  const sim = buildDrape(pair, fieldM, anchorLift)
  const ctrl = buildSettle(sim, buildCrotchProbeIdx(pair))
  let ph: SettlePhase = ctrl.phase
  const frames = opts?.maxFrames ?? DRESSING_PRIOR.maxTotalFrames + 10
  for (let k = 0; k < frames && ph !== 'done'; k++) {
    stepDrape(sim)
    ph = ctrl.step(sim)
  }
  return { sim, pair, ctrl, ph, report: ctrl.report(sim), anchorLift, waistLen, waistRing }
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
    // ---- 腰圈钉环（形随体长随衣）----
    // 环长 = 成衣腰长（等弧长重采样弦差 <0.5%）
    expect(Math.abs(out1.waistRing.total - out1.waistLen) / out1.waistLen)
      .toBeLessThan(0.005)
    // 身片顶链连续环走 3D 弦和 ≈ 成衣腰长（弧长贴环、钉间距 = 纸样边长
    // 零应变）。量法必须沿 ringWalk 连续走：per-part 分段会漏 4 个角点
    // 缺口（各 ~2×boundaryStep，合计 ~8%——角点在 side 链不在 top 采样）；
    // 连续环走只剩弦弧差 + 省口富余压缩，预算 3%
    const walk = ringWalk(out1.pair.parts.filter((p) => p.key !== 'waistband'))
    let topChord = 0
    for (let k = 0; k + 1 < walk.verts.length; k++) {
      const va = walk.verts[k], vb = walk.verts[k + 1]
      const aI = 3 * (out1.pair.parts[va.part].offset + va.idx)
      const bI = 3 * (out1.pair.parts[vb.part].offset + vb.idx)
      topChord += Math.hypot(
        out1.pair.pos[aI] - out1.pair.pos[bI],
        out1.pair.pos[aI + 1] - out1.pair.pos[bI + 1],
        out1.pair.pos[aI + 2] - out1.pair.pos[bI + 2])
    }
    expect(Math.abs(topChord - out1.waistLen) / out1.waistLen)
      .toBeLessThan(0.03)
    // 腰头两缘 3D 弦和 ≈ 成衣腰长（带 = 零应变布：底缘贴钉环、顶缘贴
    // 带顶环，环长各自 = C）
    const bandPart = out1.pair.parts.find((p) => p.key === 'waistband')!
    expect(bandPart).toBeDefined()
    const chordOf = (idx: number[]): number => {
      let s = 0
      for (let k = 0; k + 1 < idx.length; k++) {
        const aI = 3 * (bandPart.offset + idx[k])
        const bI = 3 * (bandPart.offset + idx[k + 1])
        s += Math.hypot(
          out1.pair.pos[aI] - out1.pair.pos[bI],
          out1.pair.pos[aI + 1] - out1.pair.pos[bI + 1],
          out1.pair.pos[aI + 2] - out1.pair.pos[bI + 2])
      }
      return s
    }
    const bandTop = bandPart.mesh.runs.find((r) => r.name === 'top')!
    const bandBot = bandBottomChain(bandPart.mesh)!
    const relBandTop = Math.abs(chordOf(bandTop.indices) - out1.waistLen)
      / out1.waistLen
    const relBandBot = Math.abs(chordOf(bandBot.indices) - out1.waistLen)
      / out1.waistLen
    expect(relBandTop).toBeLessThan(0.02)
    expect(relBandBot).toBeLessThan(0.02)
    // 钉集带符号间隙（到体截面边界，raw）：贴体起于 ~0（后腰最薄处截面
    // 行差/重采样 ≤0.06）且上限为截面比例量级（上方收窄行的真实悬空
    // ~0.7；旧统一 1.2 垫已废）
    const pinnedIdx: number[] = []
    for (const part of out1.pair.parts) {
      if (part.key === 'waistband') {
        pinnedIdx.push(...bandTop.indices.map((i) => part.offset + i))
        pinnedIdx.push(...bandBot.indices.map((i) => part.offset + i))
      } else {
        const top = part.mesh.runs.find((r) => r.role === 'top_chain')!
        pinnedIdx.push(...top.indices.map((i) => part.offset + i))
      }
    }
    let gapMin = Infinity, gapMax = -Infinity
    const gapAll: number[] = []
    for (const gi of pinnedIdx) {
      const x = out1.pair.pos[3 * gi]
      const y = out1.pair.pos[3 * gi + 1] - out1.sim.yLift
      const z = out1.pair.pos[3 * gi + 2]
      const rings = (out1.sim.field as NonNullable<DrapeSim['field']>).loopsAt(y)
      if (rings.length === 0) continue
      const hit = nearestRingBoundary(rings, x, z, 5)
      if (hit === null) continue
      const sd = (x - hit.px) * hit.nx + (z - hit.pz) * hit.nz
      gapMin = Math.min(gapMin, sd)
      gapMax = Math.max(gapMax, sd)
      gapAll.push(sd)
    }
    gapAll.sort((p, q) => p - q)
    // 判别「非旧统一 1.2 垫」的稳健量 = 中位数（旧垫法 min≈max≈1.15；
    // 实测新口径 min −0.009 贴体 / 中位 0.35 / p90 0.73）；上限给到 1.1
    // ——腰上凹背行带列走两环直线割线，真实悬空峰值 ~1（实测 0.99）
    expect(gapMin).toBeGreaterThan(-0.06)
    expect(gapAll[Math.floor(gapAll.length / 2)]).toBeLessThan(0.5)
    expect(gapMax).toBeLessThan(1.1)
    // ---- 初摆位穿透把门（腿区绕管半径 = rAt+skin+gap 按构造体外；腰圈
    // 钉环 = 截面边界放大 s=C/周长，等弧长弦重采样内切伪差 ~0.01cm 级
    // 实测最深 0.009——计数把门改深度把门，预算 0.05（碰撞 deadZone 0.3
    // 量级内，动力学不受扰）----
    let worstIn = 0
    for (let i3 = 0; i3 < out1.pair.pos.length; i3 += 3) {
      const rings = (out1.sim.field as NonNullable<DrapeSim['field']>)
        .loopsAt(out1.pair.pos[i3 + 1] - out1.sim.yLift)
      if (rings.length === 0) continue
      if (!pointInRings(out1.pair.pos[i3], out1.pair.pos[i3 + 2], rings)) continue
      const hit = nearestRingBoundary(
        rings, out1.pair.pos[i3], out1.pair.pos[i3 + 2], 5)
      if (hit === null) continue
      worstIn = Math.max(worstIn, -(
        (out1.pair.pos[i3] - hit.px) * hit.nx
        + (out1.pair.pos[i3 + 2] - hit.pz) * hit.nz))
    }
    expect(worstIn).toBeLessThan(0.05)
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
    // ---- 脚口前缘挂扣（2026-09-19（二）修复金标）：脚口带（纸样 y∈
    // [−1,1]）前向 max z ≥7 = 前缘挂在脚背上（挂扣态实测 7.9，脱扣态
    // ~3——09-19 钉环贴体→掉裆加深 dropF 7.12 把前缘拖过脚背冠；脚
    // 碰撞本身干净，修复 = hem 环带刚度非碰撞壳）----
    let frontRim = -Infinity
    for (const part of out1.pair.parts) {
      if (part.key === 'waistband') continue
      for (let i = 0; i < part.mesh.xy.length / 2; i++) {
        const gi = part.offset + i
        const py = out1.sim.pos[3 * gi + 1] - out1.anchorLift
        if (py < -1 || py > 1) continue
        frontRim = Math.max(frontRim, out1.sim.pos[3 * gi + 2])
      }
    }
    expect(frontRim).toBeGreaterThan(7.0)
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

  it('偏小款穿不进：钉环 s<1 整圈嵌体 + 热力图 gap 红区（只摆位快检）', () => {
    const a = loadBodyFromDisk()
    const data = JSON.parse(
      readFileSync(`${HERE}/fixture_fitting.json`, 'utf8')) as FittingResult
    // 成衣腰长 −4：s = 66.1/69.05 ≈ 0.957——钉环整体缩进截面内（前腹
    // ~0.6、侧 ~0.55），钉 XZ 冻结如实呈现穿不进
    const out = runDress(a, data, {}, { waistDelta: 4, maxFrames: 0 })
    let inside = 0
    for (let i3 = 0; i3 < out.pair.pos.length; i3 += 3) {
      const rings = (out.sim.field as NonNullable<DrapeSim['field']>)
        .loopsAt(out.pair.pos[i3 + 1] - out.sim.yLift)
      if (rings.length > 0
        && pointInRings(out.pair.pos[i3], out.pair.pos[i3 + 2], rings)) {
        inside++
      }
    }
    // 腰口钉环整圈（顶链 + 腰头两缘）嵌体——腿区/躯干摆位照旧体外
    expect(inside).toBeGreaterThan(100)
    // 热力图 gap 带符号：穿体深度读负值红端（前腹 ~0.6 − 接触壳 0.98）
    const heat = computeHeat(out.sim, 'gap')
    let gapMin = 0
    for (const v of heat) gapMin = Math.min(gapMin, v)
    expect(gapMin).toBeLessThan(-1.0)
  }, 60_000)
})
