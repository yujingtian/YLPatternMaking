// 穿台集成金标（2026-09-18）：真 base.bin 人台 + fixture 整裤全链
// （锚定 → 人台环场 → 腿轴 → 摆位 → settle 落位 → 读数）。与 Fitting3DView
// dress 分支同源管线（本文件是它的无渲染镜像）。验收口径：
// · anchorLift canary ≈ +7.6（人台腰地标 105.644 − 纸样腰站 98——量级
//   把门：θ/坐标系错位会差出几十 cm）
// · θ 对齐 canary：前中腰角 z>0 / 后中腰角 z<0（纸样系与人台 +Z=前同构）
// · 裆地标下方 forkSearch 窗内存在双腿分离行（腿轴成立前提）
// · 初摆位 pointInRings 计数 = 0（摆位按构造体外——穿模把门）
// · 腰圈钉环（2026-09-19 形随体长随衣；2026-09-20 间隙均匀）：环长 =
//   成衣腰长；身片顶链/腰头两缘 3D 弦和 ≈ 成衣腰长（钉间距 = 纸样边长、
//   零应变摆位）；钉集带符号间隙均匀（等距外偏：每点 ≈ 所在行 δ，底环
//   行 ~0.17、带顶行 ~0.49；旧绕原点缩放前 2.0/后 0.36 悬殊分布已废）
// · 跑至 done：无 NaN、裆四尖两两 <1.0、dropF/dropB ∈ [0, maxDrop]、
//   下摆离地；**同输入双跑 DressReport 逐字段相等**（确定性——单跑
//   比较无意义红线）
// · 挂胯卡停（2026-09-23 P1）：掉裆从穿透驱动 7.8/8.3 塌到 jam 卡停
//   ~1.7——钉环恰停行周长 < C×1.02 的最深可容档（jamF/jamB=true、
//   contact 留 pen、tooSmall——差的布长 = 裆部绷紧，偏小是读数不是错误）
// · 钉环随行重投影（2026-09-23 P2）：钉弧位三源登记全覆盖（缺项 = 该钉
//   退冻结旧口径）；下放后钉 XZ 沿参考环随行（参考行钳腰站行——裸逐钉
//   行把前中钉挤进 P(y_pat)−C 达 0.67 的截面已证伪），正面腰口 gap med
//   −0.07 贴身（冻结口径 +0.53 = 正面腰头悬空主诉）
// · 脚口前缘挂扣（2026-09-19（二））：脚口环带刚度（priors
//   hemBandStiffness，真实双折卷边硬圈）保持前缘挂在脚背上——脚口
//   前向 z ≥7（挂扣态 ~7.9，脱扣态 ~3 = 前缘滑过脚背冠到脚后）；根因
//   曾误判脚碰撞缺陷，实为钉环贴体→掉裆加深拖脱，见决策日志当日条
// · hips+ 负松量探索例：不炸、收敛、读数在值域（宽松断言——偏小是
//   读数不是错误）
// · 偏小款快检（只摆位不解算）：成衣腰长 −4 → 钉环 δ<0 整圈均匀嵌体 +
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
  pointInRings, shiftPositionsY, type BodyField, type WaistRing,
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
  field: BodyField
  effDrop: number
}

// 穿台全管线（Fitting3DView dress 分支同源；heightW=0 地标因子 1）。
// opts：waistDelta 压制成衣腰长（偏小款快检）；maxFrames 0 = 只摆位不解算；
// pinnedDrop 指定穿位（视图分支同源：几何交规钳位 effDrop = min(申请,
// maxFeasibleDrop)、钉环建所选行、整裤刚性下移、lowering 旁路；并开
// pinXZFree 钉体表滑轨——弯腰头斜切嵌体修复，见下方 curved_seam 例）；
// heightW 身高地标因子（非零身高 morph 时锚定随缩放，同视图口径）
function runDress(
  a: BodyMeshAsset, data: FittingResult, w: MeshWeights,
  opts?: {
    waistDelta?: number; maxFrames?: number; pinnedDrop?: number
    heightW?: number
  },
): RunOut {
  const lmWaist = a.landmarks.waist!
  const lmCrotch = a.landmarks.crotch!
  const lmAnkle = a.landmarks.ankle!
  const sf = stationFactor(a.heightInfo, opts?.heightW ?? 0)
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
  // 腰圈钉环（2026-09-19 形随体长随衣；2026-09-20 间隙均匀）：尺寸 =
  // 成衣腰长（优先腰头带底净长——收省后口径；回退腰站 girth_finished），
  // 视图 dress 分支同源
  const waistLen0 = (bandMesh && bandBottomChain(bandMesh)?.runLength)
    ?? waistSt.girth_finished
  if (waistLen0 == null) {
    throw new Error('缺成衣腰长（腰头带底净长/腰站 girth_finished 均缺）——穿台无法定腰圈钉环')
  }
  const waistLen = waistLen0 - (opts?.waistDelta ?? 0)
  // 指定穿位几何交规（2026-09-27，视图分支同源）：所选行体围套不进（≥
  // 腰长×(1+jamMargin))时实际停位钳到最深可穿档——判据复用 P1 挂胯
  const effDrop = (opts?.pinnedDrop ?? 0) > 0
    ? Math.min(opts!.pinnedDrop!, fieldM.maxFeasibleDrop(waistSt.y, waistLen, 12))
    : 0
  const waistRing = buildWaistRing(fieldM, waistSt.y - effDrop, waistLen)
  // seam 模式（有省款）第 9 参 yoke 必传——育克升格 sim 参与片的宿主/
  // 闭式收敛映射（视图分支同款条件；漏传 = 腰环行走缺 top_chain 误报）
  const pair = buildFullPair(panel.host, backPanel.host, fieldM, {
    front: legAxisM.forkY, back: legAxisM.forkY,
  }, legAxisM, bandMesh, anchorLift, waistRing,
    backPanel.mode === 'seam' && backPanel.yokeHost && backPanel.seamInfo
      ? { host: backPanel.yokeHost, sCin: backPanel.seamInfo.sCin }
      : null)
  if (effDrop > 0) {
    for (let i = 1; i < pair.pos.length; i += 3) pair.pos[i] -= effDrop
  }
  // 指定穿位钉 XZ 自由（2026-09-27，视图分支同源）：pinned 下钉只锁 Y，
  // XZ 走 collide 体表滑轨——见下方 curved_seam 金标例注释
  const sim = buildDrape(pair, fieldM, anchorLift, undefined, undefined,
    { pinXZFree: opts?.pinnedDrop !== undefined })
  // 挂胯判据（2026-09-23 P1，与视图 dress 分支同源）：钉环套不进候选行
  // 截面即卡停；pinned = 指定穿位 lowering 旁路
  const ctrl = buildSettle(sim, buildCrotchProbeIdx(pair), {
    jam: { ringTotal: waistRing.total, rowY: waistRing.y },
    pinned: opts?.pinnedDrop !== undefined,
  })
  let ph: SettlePhase = ctrl.phase
  const frames = opts?.maxFrames ?? DRESSING_PRIOR.maxTotalFrames + 10
  for (let k = 0; k < frames && ph !== 'done'; k++) {
    stepDrape(sim)
    ph = ctrl.step(sim)
  }
  return {
    sim, pair, ctrl, ph, report: ctrl.report(sim), anchorLift, waistLen,
    waistRing, field: fieldM, effDrop,
  }
}

const expectFinite = (pos: Float32Array): void => {
  for (let i = 0; i < pos.length; i++) {
    expect(Number.isFinite(pos[i]), `pos[${i}] finite`).toBe(true)
  }
}

// 中位数
const med = (xs: number[]): number => {
  expect(xs.length).toBeGreaterThan(0)
  const s = [...xs].sort((p, q) => p - q)
  const m = s.length >> 1
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

// 腰口开口钉索引集（结构判据）：身片 top_chain + 腰头带底缘——两链贴腰口
// 开洞同一斜切行。不能按 Y 滤：带顶缘随斜切 Y 100~104 与后侧开口钉
//（Y 至 ~99.7）域交叠，实测钉 Y 分位数 96→104 连续无空档
const openingPinSet = (pair: ReturnType<typeof buildFullPair>): Set<number> => {
  const s = new Set<number>()
  for (const part of pair.parts) {
    if (part.key === 'waistband') {
      const bot = bandBottomChain(part.mesh)
      if (bot) for (const i of bot.indices) s.add(part.offset + i)
    } else {
      const top = part.mesh.runs.find((r) => r.role === 'top_chain')
      if (top) for (const i of top.indices) s.add(part.offset + i)
    }
  }
  return s
}

// 钉集分扇带符号间隙（P2 pinGapAt 同口径）：sd = (点−最近边界)·外法线
//（正=悬空、负=嵌体——到体截面边界的原始距离，**非 worstPen 壳口径**：
// 壳位停留读 −CORE_SKIN 会把「贴皮肤」误读成深嵌体），frontness f =
// |atan2(x,z)|/π 分扇（<0.25 前 / >0.75 后）——pinned 钉全程不动，pos 即
// 建环位；margin 5 同 P2 量法（带顶钉行形浮空不被 quick reject 落掉）。
// only：钉子集（腰口开口钉——带顶缘随自身行 δ_top 另是一套读数，混进
// 中位会拉偏）
const pinSectorGaps = (
  sim: DrapeSim, field: BodyField, only?: Set<number>,
): { front: number[]; back: number[] } => {
  const out = { front: [] as number[], back: [] as number[] }
  for (const gi of sim.pinIdx) {
    if (only !== undefined && !only.has(gi)) continue
    const x = sim.pos[3 * gi], y = sim.pos[3 * gi + 1], z = sim.pos[3 * gi + 2]
    const rings = field.loopsAt(y - sim.yLift)
    if (rings.length === 0) continue
    const hit = nearestRingBoundary(rings, x, z, 5)
    if (hit === null) continue
    const sd = (x - hit.px) * hit.nx + (z - hit.pz) * hit.nz
    const f = Math.abs(Math.atan2(x, z)) / Math.PI
    if (f < 0.25) out.front.push(sd)
    else if (f > 0.75) out.back.push(sd)
  }
  return out
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
    // 环长 = 成衣腰长（定点迭代收敛：实测残差 ~1e-8 量级，预算 1e-4）
    expect(Math.abs(out1.waistRing.total - out1.waistLen) / out1.waistLen)
      .toBeLessThan(1e-4)
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
    // 钉集带符号间隙（到体截面边界，raw）：等距外偏口径——每点 ≈ 所在
    // 行的 δ（底环行 ~0.17、带顶行 ~0.49；上方收窄/前腹外凸的行形差是
    // ±0.15 内真实浮动）。旧绕原点缩放 gap ∝ |p|（前 2.0/后 0.36 悬殊
    // ——环整体前骑）已废
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
    // 判别「间隙均匀」：下限起于底环行 δ（实测 min 0.14 ≈ δ_底 0.17 −
    // 行形差；旧缩放口径前 2.0/后 0.36 悬殊时 max 会破 1.6）；中位混两
    // 行（底 0.17 + 顶 0.49）实测 0.38；上限 = 带顶行凹背真实悬空实测
    // 0.76，预算 0.9
    expect(gapMin).toBeGreaterThan(0.05)
    expect(gapAll[Math.floor(gapAll.length / 2)]).toBeLessThan(0.5)
    expect(gapMax).toBeLessThan(0.9)
    // ---- 初摆位穿透把门（腿区绕管半径 = rAt+skin+gap 按构造体外；腰圈
    // 钉环 = 截面边界沿外法线等距偏移 δ>0 按构造体外，残余仅角平分法线/
    // 重采样伪差 0.01 量级——深度把门预算 0.05（碰撞 deadZone 0.3 量级
    // 内，动力学不受扰）----
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
    // 掉裆（挂胯卡停 P1 2026-09-23）：旧口径穿透驱动掉到 7.8/8.3——刚性
    // 钉环被拽进体围大得多的下行行（嵌体/深褶/波浪根因）；jam 判据后掉裆
    // 塌到 ~1.7——钉环（总长 70.10）恰停行 y=96.5（P=71.07 < 71.50 =
    // C×1.02 最深可容档）、候选行 y=96.0（P=71.98）套不进即卡停。
    // contactF/B 留 pen（差的布长 = 裆部绷紧勒住，tooSmall 偏小读数）
    expect(out1.report.jamF).toBe(true)
    expect(out1.report.jamB).toBe(true)
    expect(out1.report.dropF).toBeGreaterThanOrEqual(1.0)
    expect(out1.report.dropF).toBeLessThanOrEqual(3.0)
    expect(out1.report.dropB).toBeGreaterThanOrEqual(1.0)
    expect(out1.report.dropB).toBeLessThanOrEqual(3.0)
    expect(out1.report.dropF).toBeLessThanOrEqual(DRESSING_PRIOR.maxDrop + 1e-6)
    expect(out1.report.dropB).toBeLessThanOrEqual(DRESSING_PRIOR.maxDrop + 1e-6)
    // 下摆：掉裆收窄到 ~1.7（旧 7.8 时裤脚及地、地面网钳 0）→ 下摆离地
    // 实测 ~2.4；把门地面网不破（无穿透到地下）
    let minY = Infinity
    for (let i = 1; i < out1.sim.pos.length; i += 3) {
      minY = Math.min(minY, out1.sim.pos[i])
    }
    expect(minY).toBeGreaterThanOrEqual(-1e-6)
    // ---- 脚口前缘位置（2026-09-19（三）strain limiting 重定标 → 2026-09-20
    // 等距外偏再定标 → 2026-09-23 P1 挂胯再定标）：掉裆从 7.8 收窄到 ~1.7
    // 后整裤高挂，脚口带（纸样 y∈[−1,1]）前缘实测 8.14（旧 3.25）——
    // 挂扣余量转厚；把门 ≥6（滑脱到脚后的脱扣态 ~3 仍可分）----
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
    expect(frontRim).toBeGreaterThan(6.0)
    // ---- P2 钉环随行重投影（2026-09-23）：钉弧位全覆盖 + 正面腰口贴身 ----
    // 弧位覆盖：穿台分支三源登记（身片顶链走样 + 终点角 + 腰头带列全顶点）
    // 应覆盖全部钉——缺项 = 该钉 XZ 冻结退旧口径，静默缺 = 回归。注意
    // pinArcs 是钉集超集（带列非钉顶点也登记，源③整列循环不筛），size
    // 不能与 pinIdx.length 判等，覆盖性以 has 逐钉为准（实测 146 钉全中）
    expect(out1.pair.pinArcs).toBeDefined()
    expect(out1.pair.pinArcs!.size).toBeGreaterThanOrEqual(out1.sim.pinIdx.length)
    for (const gi of out1.sim.pinIdx) {
      expect(out1.pair.pinArcs!.has(gi), `pin ${gi} 弧位缺失`).toBe(true)
    }
    // 终态钉 gap 扇区读数：正面（f<0.25）腰口贴身——冻结口径 med +0.53
    //（正面腰头悬空主诉）、裸逐钉行 −0.47（前中过挤）先后证伪；参考行
    // 钳腰站行口径实测 med −0.07、嵌体下探 −0.19。后扇区 med +0.27 主体
    // 是带顶钉随自身行的诚实浮空（上段体围 < 环长 → δ_top ~+0.3..0.45）
    // ——腰口闭合差已消除，扇区差不作把门
    const pinGapAt = (gi: number): number => {
      const field = out1.sim.field as NonNullable<DrapeSim['field']>
      const x = out1.sim.pos[3 * gi]
      const y = out1.sim.pos[3 * gi + 1] - out1.sim.yLift
      const z = out1.sim.pos[3 * gi + 2]
      const rings = field.loopsAt(y)
      if (rings.length === 0) return NaN
      const hit = nearestRingBoundary(rings, x, z, 5)
      if (hit === null) return NaN
      return (x - hit.px) * hit.nx + (z - hit.pz) * hit.nz
    }
    const fSd: number[] = []
    for (const gi of out1.sim.pinIdx) {
      const f = Math.abs(
        Math.atan2(out1.sim.pos[3 * gi], out1.sim.pos[3 * gi + 2])) / Math.PI
      if (f >= 0.25) continue
      const sd = pinGapAt(gi)
      if (Number.isFinite(sd)) fSd.push(sd)
    }
    fSd.sort((p, q) => p - q)
    const fMed = fSd[Math.floor(fSd.length / 2)]
    expect(fMed).toBeGreaterThanOrEqual(-0.25)
    expect(fMed).toBeLessThanOrEqual(0.15)
    expect(Math.min(...fSd)).toBeGreaterThan(-0.30)
    // ---- 同输入双跑 DressReport 逐字段相等（确定性红线）----
    const out2 = runDress(a, data, {})
    const r1 = out1.report, r2 = out2.report
    for (const key of ['dropF', 'dropB', 'worstPen', 'worstPenY', 'frames',
      'jamF', 'jamB'] as const) {
      expect(r2[key], key).toBe(r1[key])
    }
    expect(r2.contactF).toEqual(r1.contactF)
    expect(r2.contactB).toEqual(r1.contactB)
    expect(r2.tooSmall).toBe(r1.tooSmall)
    expect(r2.capped).toBe(r1.capped)
    expect(Array.from(out2.sim.pos)).toEqual(Array.from(out1.sim.pos))
    // 2026-09-23 提速（1a sqrt + 1b 分箱 + 1c 帧数压缩）后实测 58s（含
    // 双跑全解算；提速前 ~230s 单跑/286s 并行）。超时裕度 3× 给到 180s
    //（双跑两遍全解算，仍是全仓最重用例）
  }, 180_000)

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
  }, 120_000)

  it('偏小款穿不进：钉环 δ<0 整圈均匀嵌体 + 热力图 gap 红区（只摆位快检）', () => {
    const a = loadBodyFromDisk()
    const data = JSON.parse(
      readFileSync(`${HERE}/fixture_fitting.json`, 'utf8')) as FittingResult
    // 成衣腰长 −4：δ = (66.1−69.05)/2π ≈ −0.47——钉环沿外法线均匀内嵌
    // 截面内 ~0.47（每点同一深度），钉 XZ 冻结如实呈现穿不进
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
    // 热力图 gap 带符号：穿体深度读负值红端（均匀嵌体 ~0.47 − 接触壳 0.98）
    const heat = computeHeat(out.sim, 'gap')
    let gapMin = 0
    for (const v of heat) gapMin = Math.min(gapMin, v)
    expect(gapMin).toBeLessThan(-1.0)
  }, 60_000)

  // ---- 指定穿位几何交规（2026-09-27 用户报障：腰下滑杆加深 → 后腰头/
  // 机头嵌体 + 前腰头悬空。根因 = pinned 缺 P1 同款交规：所选行体围 ≥
  // 成衣腰长×(1+jamMargin) 时钉环 δ<0 无下限均匀嵌体（钉豁免碰撞）、
  // 机头自由布贴体表 → 埋体钉到贴体布的手风琴深褶。修复 = effDrop 钳到
  // maxFeasibleDrop 最深可穿档、周身 δ ≥ −jamMargin×C/2π ≈ −0.22 均匀贴身）----
  it('指定穿位超深卡停：effDrop 钳到最深可穿档、钉环周身均匀不嵌体 + 双跑确定性', () => {
    const a = loadBodyFromDisk()
    const data = JSON.parse(
      readFileSync(`${HERE}/fixture_fitting.json`, 'utf8')) as FittingResult
    const waistY = data.body.stations.find((s) => s.key === 'waist')!.y
    const probe = runDress(a, data, {}, { pinnedDrop: 8, maxFrames: 0 })
    // 钳位语义独立复算：与方法实现同判据的手推行周长扫描（P1 口径）
    const limit = probe.waistLen * (1 + DRESSING_PRIOR.jamMargin)
    let expected = 0
    for (let d = FIELD_PRIOR.rowStep; d <= 12; d += FIELD_PRIOR.rowStep) {
      if (probe.field.rowPerimeter(waistY - d) >= limit) break
      expected = d
    }
    expect(probe.effDrop).toBeCloseTo(expected, 10)
    expect(probe.effDrop).toBeGreaterThan(0)
    expect(probe.effDrop).toBeLessThan(8)   // 申请 8 被钳位（fixture 体围腰下即超）
    // 摆位期腰口开口钉分扇带符号间隙（只量开口钉——带顶随自身行 δ_top
    // 混中位拉偏，见 pinSectorGaps 注）：周身不嵌体 + 前后差不悬殊。实测
    // medF −0.03（贴身）/ medB +0.31（弯腰头开口斜切、后侧钉站更瘦行 →
    // 诚实浮空）；未钳位现状 = 申请行裸嵌体 δ ≈ −2.45（P(y−8)=85.5 vs
    // C=70.1）——窗按 jamMargin δ 界 −0.22 + 余量取 −0.25
    const g0 = pinSectorGaps(probe.sim, probe.field, openingPinSet(probe.pair))
    expect(med(g0.front)).toBeGreaterThanOrEqual(-0.25)
    expect(med(g0.front)).toBeLessThanOrEqual(0.6)
    expect(med(g0.back)).toBeGreaterThanOrEqual(-0.25)
    expect(med(g0.back)).toBeLessThanOrEqual(0.6)
    expect(Math.abs(med(g0.front) - med(g0.back))).toBeLessThan(0.5)
    // 解算终态：钉全程不动（分扇窗不漂移）+ worstPen 回 auto jam 档量级
    //（实测 1.96 @78.4，与 auto 卡停读数同级 = 接触带残余的偏小诚实读数）
    const out = runDress(a, data, {}, { pinnedDrop: 8 })
    expect(out.ph).toBe('done')
    expectFinite(out.sim.pos)
    expect(out.report.dropF).toBeCloseTo(0, 10)   // 掉裆读数退场（−0 陷阱）
    expect(out.report.dropB).toBeCloseTo(0, 10)
    const g = pinSectorGaps(out.sim, out.field, openingPinSet(out.pair))
    expect(med(g.front)).toBeGreaterThanOrEqual(-0.25)
    expect(med(g.back)).toBeGreaterThanOrEqual(-0.25)
    expect(Math.abs(med(g.front) - med(g.back))).toBeLessThan(0.5)
    expect(out.report.worstPen).toBeLessThan(2.2)
    // 同输入双跑 DressReport 逐字段相等（确定性红线）
    const out2 = runDress(a, data, {}, { pinnedDrop: 8 })
    expect(out2.report).toEqual(out.report)
  }, 300_000)

  it('指定穿位偏小款：effDrop=0 合法终态 + δ<0 均匀嵌体读数保留（只摆位快检）', () => {
    const a = loadBodyFromDisk()
    const data = JSON.parse(
      readFileSync(`${HERE}/fixture_fitting.json`, 'utf8')) as FittingResult
    const waistY = data.body.stations.find((s) => s.key === 'waist')!.y
    // 成衣腰长 −4：第一档即套不进 → effDrop=0（对齐 P1「h′=0 即 jam」）
    const out = runDress(a, data, {}, { waistDelta: 4, pinnedDrop: 8, maxFrames: 0 })
    expect(out.effDrop).toBe(0)
    expect(out.field.rowPerimeter(waistY - FIELD_PRIOR.rowStep))
      .toBeGreaterThanOrEqual(out.waistLen * (1 + DRESSING_PRIOR.jamMargin))
    // 钉环整圈均匀嵌体（等距外偏口径）：环点 vs 环行截面边界每点 ≈ δ* =
    // (C−P)/2π ≈ −0.47——开口钉按「各自行」读数与弯腰头斜切行差纠缠
    //（前扇 −0.32 / 后扇 −0.05），均匀性断言落在环本体层：逐点全在
    // δ*±0.1 窗内 + 全在截面内（穿不进如实呈现；旧绕原点缩放口径前:后
    // 2.0/0.36 悬殊在此必破窗）
    const rings = out.field.loopsAt(out.waistRing.y)
    expect(rings.length).toBeGreaterThan(0)
    const dStar = (out.waistLen - out.field.rowPerimeter(out.waistRing.y))
      / (2 * Math.PI)
    expect(dStar).toBeLessThan(-0.4)
    let gMin = Infinity, gMax = -Infinity
    for (let k = 0; k < out.waistRing.pts.length / 2; k++) {
      const x = out.waistRing.pts[2 * k], z = out.waistRing.pts[2 * k + 1]
      const hit = nearestRingBoundary(rings, x, z, 5)
      expect(hit, `ring pt ${k} 边界查询落空`).not.toBeNull()
      const sd = (x - hit!.px) * hit!.nx + (z - hit!.pz) * hit!.nz
      gMin = Math.min(gMin, sd)
      gMax = Math.max(gMax, sd)
    }
    expect(gMax - gMin).toBeLessThan(0.1)          // 均匀（等距外偏）
    expect(gMin).toBeGreaterThan(dStar - 0.1)
    expect(gMax).toBeLessThan(dStar + 0.1)
    expect(pointInRings(
      out.waistRing.pts[0], out.waistRing.pts[1], rings)).toBe(true)
  }, 60_000)

  // ---- 指定穿位钉体表滑轨（2026-09-27 用户报障「裤子和腰头的缝合处，
  // 部分布进入人台——前中一点、侧缝比较明显」）----
  // 样本 = fixture_fitting_curved_seam（size_draft.toml 有省弯腰头款）：
  // 腰口斜切极差 8.6cm（侧缝点下垂站下 ~2.2、后中抬到站上 ~4.8），远超
  // 其余 fixture（≤4.9）。根因链（残差分解实测，ringDev 全体 0.00 = 摆位
  // 精确在等距外偏环上、嵌体全来自行差）：pinned 钉 XZ 锁在建环行（站−
  // drop）单行环、钉 Y 是纸样斜切位——侧缝段钉站腰下 6.5~8.2 的粗行
  //（体围 74~76.6 vs C 69.4）→ 局部深嵌尖刺 sd −0.76（band bottom /
  // front waist / yoke top 三片同点三份），钉缘嵌体 vs 带中自由布贴壳
  //（+0.98）的折痕对比 = 缝合口「布进人台」观感。物理真相：布真实 3D
  // 链长（含斜切竖向分量）73.3 ≥ 体表斜切线 ~72.5——贴体可行、不缺布；
  // 锁单行环才是人为约束。修复 = pinXZFree 钉滑轨（drape.ts）：钉只锁
  // Y（穿位高度），XZ 径向双向钳到体表边界 + PIN_SKIN（体内推出 + 体外
  // 拉回——单向推对初值浮空的 yoke 后中高段无回贴力）、环向由布网 side
  // 弧长配对锚；钉端 dist/bend/seam/strainLimit 全程逆质量 0 + prev 同步
  // 零速度注入。呈现 = 缝合口整圈贴体微皱（真实低腰弯腰头观感），布长
  // 守恒把门。体型 160/61/84 = 用户实报场景（hips− 拉满 + waist− 解出）
  it('curved_seam 指定穿位滑轨：缝合口整圈贴体（嵌体消除 + 布长守恒）+ 双跑确定性', () => {
    const a = loadBodyFromDisk()
    const data = JSON.parse(
      readFileSync(`${HERE}/fixture_fitting_curved_seam.json`, 'utf8')) as FittingResult
    // 160/61/84 权重（ hips 域下沿钳端点 84.20；身高 160 → height− 负分支）
    const w: MeshWeights = {
      'waist-': 0.5330811949488634, 'hips-': 1, 'height-': 0.20059961842463925,
    }
    const out = runDress(a, data, w, {
      pinnedDrop: 5, heightW: -0.20059961842463925,
    })
    // effDrop = 5 全额可行（160 体型 maxFeasibleDrop ≈ 5.5）
    expect(out.effDrop).toBeCloseTo(5, 10)
    expect(out.ph).toBe('done')
    expectFinite(out.sim.pos)
    // 滑轨贴体：开口钉（带底缘+身片顶链）全体 sd ≈ PIN_SKIN 0.05——
    // 冻结口径同场景深嵌 min −0.76/浮空 med +0.80（三片同点）全消
    const open = openingPinSet(out.pair)
    const sds: number[] = []
    for (const gi of out.sim.pinIdx) {
      if (!open.has(gi)) continue
      const x = out.sim.pos[3 * gi]
      const y = out.sim.pos[3 * gi + 1] - out.sim.yLift
      const z = out.sim.pos[3 * gi + 2]
      const rings = out.field.loopsAt(y)
      if (rings.length === 0) continue
      const hit = nearestRingBoundary(rings, x, z, 5)
      if (hit === null) continue
      sds.push((x - hit.px) * hit.nx + (z - hit.pz) * hit.nz)
    }
    expect(sds.length).toBeGreaterThan(80)
    sds.sort((p, q) => p - q)
    expect(sds[0]).toBeGreaterThan(-0.1)                       // 嵌体消除
    expect(sds[Math.floor(sds.length * 0.99)]).toBeLessThan(0.35)   // 贴体均匀
    // 布长守恒（布不可伸长红线）：顶链连续环走 3D 弦和 / C——斜切款
    // 竖向分量使比值天然 >1（冻结口径 1.056），滑轨拉直钉距到体表线后
    // 实测 1.065；>1.10 = 钉把布拉出体表线 = 拉伸违规红旗
    const walk = ringWalk(out.pair.parts.filter((p) => p.key !== 'waistband'))
    let topChord = 0
    for (let k = 0; k + 1 < walk.verts.length; k++) {
      const va = walk.verts[k], vb = walk.verts[k + 1]
      const aI = 3 * (out.pair.parts[va.part].offset + va.idx)
      const bI = 3 * (out.pair.parts[vb.part].offset + vb.idx)
      topChord += Math.hypot(
        out.sim.pos[aI] - out.sim.pos[bI],
        out.sim.pos[aI + 1] - out.sim.pos[bI + 1],
        out.sim.pos[aI + 2] - out.sim.pos[bI + 2])
    }
    const rel = topChord / out.waistLen
    expect(rel).toBeGreaterThanOrEqual(1.0)
    expect(rel).toBeLessThanOrEqual(1.10)
    // 同输入双跑 DressReport 逐字段相等（确定性红线）
    const out2 = runDress(a, data, w, {
      pinnedDrop: 5, heightW: -0.20059961842463925,
    })
    expect(out2.report).toEqual(out.report)
    expect(Array.from(out2.sim.pos)).toEqual(Array.from(out.sim.pos))
  }, 180_000)

  // ---- 长裤盖脚（2026-09-20 用户报障「裤腿不盖在脚上、脚慢慢穿透布」）----
  // zhitong 直筒 outseam 106 ≈ 身高：脚全在裤筒内、hem 37.5 < 脚底切片
  // 周长 75~86（脚口环抱脚截面不可能——真实长裤脚口本就搭在脚背上）。
  // 修复三层：脚区幕帘摆位（placement.buildFootCurtain，踝下布沿脚面
  // 弧长走线、初值直落正确 drape 盆地）+ collide 上表面竖直支撑
  // （topSupportY 阈 0.6 盖趾盒冠 g≈0.8）+ 埋点救援。金标把门：
  // · 踝下（幕帘域）全粒子穿脚环深度 ≤0.3（deadZone 口径；修复前布绕
  //   脚沉地、脚渐次穿出裤筒 = 脚环内大量布点 + 永动 churn）
  // · hem 前缘（脚区 z>1 采样）盖在脚背上：中位离地 >2cm、z>2 覆盖
  //   采样 >10（修复前 hem 中位 0 = 全体贴地）
  // · 裆读数照旧（contact gap ≈1.1-1.2 → lowering 不触发属正确——
  //   长裤问题全在脚区，掉裆机制零改动）
  it('zhitong 长裤：脚区幕帘盖脚（踝下零穿透 + hem 前缘挂脚背）', () => {
    const a = loadBodyFromDisk()
    const data = JSON.parse(
      readFileSync(`${HERE}/fixture_zhitong.json`, 'utf8')) as FittingResult
    const out = runDress(a, data, {})
    // 锚定 canary：zhitong 纸样腰站 ≈ 人台腰地标 → 负小量 lift（量级把门）
    expect(out.anchorLift).toBeGreaterThan(-1.0)
    expect(out.anchorLift).toBeLessThan(0.0)
    expect(out.ph).toBe('done')
    expectFinite(out.sim.pos)
    expect(out.report.dropF).toBeGreaterThanOrEqual(-1e-6)
    expect(out.report.dropF).toBeLessThanOrEqual(DRESSING_PRIOR.maxDrop + 1e-6)
    expect(out.report.dropB).toBeGreaterThanOrEqual(-1e-6)
    expect(out.report.dropB).toBeLessThanOrEqual(DRESSING_PRIOR.maxDrop + 1e-6)
    // P1 挂胯零变化回归：contact gap → 无 pen 不评估下放，jam 不触发
    //（由构造保证——长裤问题全在脚区，掉裆机制零改动）
    expect(out.report.jamF).toBe(false)
    expect(out.report.jamB).toBe(false)
    // 踝下（幕帘域，踝上 1cm 缓冲）全粒子穿脚环深度 >0.3 计数 = 0
    const field = out.sim.field as NonNullable<DrapeSim['field']>
    const anklePat = a.landmarks.ankle! * stationFactor(a.heightInfo, 0)
      - out.anchorLift
    let footPen = 0
    for (const part of out.pair.parts) {
      if (part.key === 'waistband') continue
      for (let i = 0; i < part.mesh.xy.length / 2; i++) {
        const gi = part.offset + i
        const patY = out.sim.pos[3 * gi + 1] - out.sim.yLift
        if (patY >= anklePat - 1) continue
        const rings = field.loopsAt(patY)
        if (rings.length === 0) continue
        const x = out.sim.pos[3 * gi], z = out.sim.pos[3 * gi + 2]
        const hit = nearestRingBoundary(rings, x, z, 1)
        if (hit === null) continue
        const sd = (x - hit.px) * hit.nx + (z - hit.pz) * hit.nz
        if (-sd > 0.3) footPen++
      }
    }
    expect(footPen).toBe(0)
    // hem 前缘挂脚背：脚区 z>1 的 hem 采样 world y 中位 >2（实测 ~6，
    // 盖在脚背/趾盒上）；z>2 覆盖采样 >10（实测 ~28，双脚）
    const hemFront: number[] = []
    let hemOverToe = 0
    for (const part of out.pair.parts) {
      for (const run of part.mesh.runs) {
        if (run.name !== 'hem') continue
        for (const i of run.indices) {
          const gi = part.offset + i
          const z = out.sim.pos[3 * gi + 2]
          if (z <= 1) continue
          hemFront.push(out.sim.pos[3 * gi + 1])
          if (z > 2) hemOverToe++
        }
      }
    }
    hemFront.sort((p, q) => p - q)
    expect(hemFront.length).toBeGreaterThan(20)
    expect(hemFront[Math.floor(hemFront.length / 2)]).toBeGreaterThan(2.0)
    expect(hemOverToe).toBeGreaterThan(10)
  }, 120_000)
})
