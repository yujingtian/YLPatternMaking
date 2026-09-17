// 引力下垂金标（2026-09-15 重建二期 + 同日前中缝合；2026-09-16 五期
// 前身自由垂、六期后身接入 + 同日「拉直」整圈钉直挂；2026-09-17 悬挂
// 抬升 + 侧缝边顶部刚度带）：前片/后片 L+R 从初始摆位解算至静止，中缝
// 对（L/R rise|cb 链镜像配对 rest=0）闭合。
// 验收：600 帧内真 settle（非封顶）、无 NaN、腰口整圈钉恒守初始位、
// 中缝 avg<0.3/P95<0.8、不拖地（minY>1：hangLift 抬升后零地面接触，
// 地面碰撞降级安全网）+ 侧缝边顶部 sideHold 带恒守 θ=±90°（腰头刚度
// 带，顶部圆弧不折）。
// **拉直形态金标（六期用户口径「前中和后中往里折、要拉直」的量化）**：
// ①中缝腰角居中——终态 |x| < 0.1cm（弧长重参数化摆位 + 镜像钉位，
// 「钉与缝同意」的直接验收）；②中缝不塌轴——终态中缝链缝向平均外伸
// ≥ 摆位的 55%（Y-only 口径下前中缝曾塌到均值 ~5.7cm 对折门帘，实测
// 现 front 87% / back 65%）；③缝不外凸——终态缝向最大外伸 ≤ 摆位
// +0.5cm。前身/后身镜像同构（seamDir +1 前中取 z / −1 后中取 −z）。
// 夹具 = fixture_fitting.json / fixture_fitting_pocket.json /
// fixture_fitting_yoke.json（引擎 build_fitting_payload 直出）。
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../types'
import { buildHangPair } from './assemble'
import type { Garment } from './assemble'
import { buildCore } from './core'
import { buildClothMesh } from './mesh'
import { buildBodyField } from './placement'
import { buildDrape, seamStats, stepDrape, type DrapeSim } from './drape'
import { buildBackPanel, buildFrontPanel } from './panel'
import { DRAPE_PRIOR, HANG_PRIOR } from './priors'

const HERE = import.meta.dirname   // src/fitting3d/garment

const result: FittingResult = JSON.parse(
  readFileSync(`${HERE}/fixture_fitting.json`, 'utf8'))

const front = buildClothMesh(result.pieces.find((p) => p.key === 'front_piece')!)
const core = buildCore(result)
const field = buildBodyField(core.positions, core.indices)
const garment = buildHangPair('front', front, field)

const minY = (pos: Float32Array): number => {
  let m = Infinity
  for (let i = 1; i < pos.length; i += 3) m = Math.min(m, pos[i])
  return m
}

const runToSettle = (sim: DrapeSim) => {
  let st: ReturnType<typeof stepDrape> = 'running'
  for (let k = 0; k < DRAPE_PRIOR.maxFrames && st === 'running'; k++) {
    st = stepDrape(sim)
  }
  return st
}

// 直挂通用口径（前身/后身 describe 共用，seamDir = 中缝朝向
// +1 前中 +Z / −1 后中 −Z）：收敛/整圈钉恒守/缝达标/不穿地
// + 六期三条拉直形态金标（腰角居中、中缝不塌轴、缝不外凸）
function assertStraightHang(
  sim: DrapeSim, placed: Garment, seamDir: 1 | -1 = 1,
): void {
  expect(sim.capped).toBe(false)   // 真静止，非封顶兜底
  expect(sim.frozen).toBe(false)
  for (let i = 0; i < sim.pos.length; i++) {
    expect(Number.isFinite(sim.pos[i])).toBe(true)
  }
  // 腰口整圈全向钉恒守初始位（六期直挂支点；重参数化摆位即挂相）
  for (let k = 0; k < sim.pinIdx.length; k++) {
    const i3 = 3 * sim.pinIdx[k]
    expect(sim.pos[i3]).toBeCloseTo(sim.pinTarget[3 * k], 6)
    expect(sim.pos[i3 + 1]).toBeCloseTo(sim.pinTarget[3 * k + 1], 6)
    expect(sim.pos[i3 + 2]).toBeCloseTo(sim.pinTarget[3 * k + 2], 6)
  }
  // 钉集覆盖整圈：钉数 ≥ 2×（顶链顶点 + 终点角）
  const topRun = placed.parts[0].mesh.runs.find((r) => r.role === 'top_chain')!
  expect(sim.pinIdx.length).toBeGreaterThanOrEqual(2 * (topRun.indices.length + 1))
  // 中缝对存在且达标（旧整裤缝合金标口径；重参数化镜像摆位起点即闭）
  expect(sim.seamIdx.length).toBeGreaterThan(0)
  const { avg, p95 } = seamStats(sim)
  expect(avg).toBeLessThan(0.3)
  expect(p95).toBeLessThan(0.8)
  // ---- 六期拉直形态金标 ----
  // 中缝链与腰角：腰角 = 顶链首采样（弧长重参数化 s=0 端 = 中缝侧）
  const seamRun = placed.parts[0].mesh.runs.find(
    (r) => r.name === 'rise' || r.name === 'cb')
  expect(seamRun).toBeDefined()
  // ① 中缝腰角居中（「钉与缝同意」的直接验收）
  const corner = 3 * (placed.parts[0].offset + topRun.indices[0])
  expect(Math.abs(sim.pos[corner])).toBeLessThan(0.1)
  // ② 中缝不塌轴：终态缝向平均外伸 ≥ 摆位 55%（防回退对折门帘——
  //    Y-only 口径实测前中缝均值塌到 ~5.7cm；现 front 87% / back 65%）
  // ③ 缝不外凸：终态缝向最大外伸 ≤ 摆位 + 0.5cm
  const seamMeanExt = (pos: Float32Array): number => {
    let sum = 0
    for (const i of seamRun!.indices) sum += seamDir * pos[3 * i + 2]
    return sum / seamRun!.indices.length
  }
  const seamMaxExt = (pos: Float32Array): number => {
    let m = -Infinity
    for (const i of seamRun!.indices) m = Math.max(m, seamDir * pos[3 * i + 2])
    return m
  }
  expect(seamMeanExt(sim.pos)).toBeGreaterThanOrEqual(0.55 * seamMeanExt(placed.pos))
  expect(seamMaxExt(sim.pos)).toBeLessThanOrEqual(seamMaxExt(placed.pos) + 0.5)
  // 不拖地（2026-09-17 hangLift 整体抬升）：解算本体 minY > 1——零地面
  // 接触（实测三款夹具 3.3~4.4），地面碰撞降级安全网（穿地仍被此拦）
  expect(minY(sim.pos)).toBeGreaterThan(1)
  // ---- 2026-09-17 顶部圆弧金标（用户口径「顶部侧缝边不要折、拼合后
  // 顶部〔腰头缝合线〕是圆弧」的量化）----
  // 侧缝边顶部刚度带：side run 顶部 sideHold cm 内顶点全向钉在 assemble
  // 语义摆位（θ=±90° 竖直）处，终态即钉位——顶部扇区完整、腰口弧不折
  // （L −X / R +X、z≈0；带缘出口偏差 ≤0.7°、往下自由内摆渐增属自然垂，
  // 不在此断言）
  const sideRuns = placed.parts[0].mesh.runs.filter((r) => r.name === 'side')
  expect(sideRuns.length).toBeGreaterThan(0)
  for (const run of sideRuns) {
    for (let k = 0; k < run.indices.length
      && run.arc[k] <= HANG_PRIOR.sideHold; k++) {
      for (const part of placed.parts) {
        const i3 = 3 * (part.offset + run.indices[k])
        const sgn = part.side === 'L' ? -1 : 1
        expect(sim.pos[i3] * sgn).toBeGreaterThan(0)
        expect(Math.abs(sim.pos[i3 + 2])).toBeLessThan(1e-3)
      }
    }
  }
}

describe('drape：前片 L+R 整圈钉直挂 + 前中缝合（六期口径）', () => {
  it('600 帧内真收敛、整圈钉恒守、前中缝达标、不穿地、腰角居中不塌轴不外凸',
    { timeout: 180000 }, () => {
      const sim = buildDrape(garment, null)   // 自由垂：无撑型芯碰撞
      const st = runToSettle(sim)
      expect(st).toBe('settled')
      assertStraightHang(sim, garment)
    })
})

describe('drape：前身并集宿主自由垂（前片+袋贴缝合，四期宿主 + 五期口径）', () => {
  // 本方案最大数值风险验证点：袋贴月牙带并入宿主（腰口段 + facing 月牙
  // 边）后，自由垂收敛口径（600 帧真 settle / pin 恒守 / 前中缝 avg<0.3 /
  // 不拖地 / 侧缝顶部刚度带）不被破坏。夹具 =
  // fixture_fitting_pocket.json（引擎直出，front_facing 拼入，hasFacing
  // =true 前置守卫）。
  const pocket: FittingResult = JSON.parse(
    readFileSync(`${HERE}/fixture_fitting_pocket.json`, 'utf8'))
  const panel = buildFrontPanel(pocket)
  const core = buildCore(pocket)
  const field = buildBodyField(core.positions, core.indices)
  const garment = buildHangPair('front', panel.host, field)

  it('袋贴月牙带并入后直挂全部口径照旧', { timeout: 180000 }, () => {
    expect(panel.hasFacing).toBe(true)   // 前置：并集成功（否则测退化形态无意义）
    const sim = buildDrape(garment, null)
    const st = runToSettle(sim)
    expect(st).toBe('settled')
    assertStraightHang(sim, garment)
  })
})

describe('drape：后身并集宿主自由垂（后片+育克缝合 + 后中 cb 缝合，六期）', () => {
  // 后身 = 机头+后片沿机头下口线缝合的并集宿主（panel.ts buildBackPanel）
  // 后扇区摆位（back θ∈[−180°,−90°]）→ 自由垂 + 后浪（cb 聚合链：裆尖
  // →P0→O 贯通育克到腰）L/R 同号缝合对。验收口径与前身同构：600 帧真
  // settle / pin 恒守 / 后中缝 avg<0.3、P95<0.8 / 不拖地 / 侧缝顶部
  // 刚度带。夹具 = fixture_fitting_yoke.json（无省贴合，
  // hasYoke=true 前置守卫）。
  const yokeFix: FittingResult = JSON.parse(
    readFileSync(`${HERE}/fixture_fitting_yoke.json`, 'utf8'))
  const backPanel = buildBackPanel(yokeFix)
  const core = buildCore(yokeFix)
  const field = buildBodyField(core.positions, core.indices)
  const garment = buildHangPair('back', backPanel.host, field)

  it('育克拼入后直挂全部口径照旧（后中 cb 缝合对）', { timeout: 180000 }, () => {
    expect(backPanel.hasYoke).toBe(true)   // 前置：并集成功（否则测退化形态无意义）
    const sim = buildDrape(garment, null)
    // 后中缝合对存在：seamIdx 覆盖 cb 聚合链（裆尖→腰口，贯通育克）
    expect(sim.seamIdx.length).toBeGreaterThan(0)
    const st = runToSettle(sim)
    expect(st).toBe('settled')
    assertStraightHang(sim, garment, -1)   // 后中朝 −Z：缝向外伸取 −z
  })
})
