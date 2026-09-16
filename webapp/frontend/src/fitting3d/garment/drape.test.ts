// 引力下垂金标（2026-09-15 重建二期 + 同日前中缝合；2026-09-16 五期改
// **前身自由垂**口径、六期后身同款接入）：前片 L+R 从初始摆位解算至
// 静止，前中缝合对
//（L/R rise 链镜像配对 rest=0）把前中闭合。验收：600 帧内真 settle
//（非封顶）、无 NaN、腰口 pin 恒守初始位、前中缝 avg<0.3/P95<0.8
//（旧整裤缝合金标口径）、不穿地（y ≥ 0，地面碰撞终点）、质心相对
// 初始摆位下降 >2cm（引力生效）。
// **自由垂形态金标（五期用户口径的量化）**：①「裆尖缝合交点要往内
// 拉、在裆下」——front_crotch_vertex（rise 链首点）终态轴心半径比
// 摆位初态内收 ≥2cm 且下沉；②「前片不该往前凸」——全体粒子前向
// 最大 z 终态比初态（扇区摆位圆弧最前点）收缩 ≥2cm（对折门帘的前缘
// 是缝不是凸面）。夹具 = fixture_fitting.json / fixture_fitting_pocket.json
//（引擎 build_fitting_payload 直出）。
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
import { DRAPE_PRIOR } from './priors'

const HERE = import.meta.dirname   // src/fitting3d/garment

const result: FittingResult = JSON.parse(
  readFileSync(`${HERE}/fixture_fitting.json`, 'utf8'))

const front = buildClothMesh(result.pieces.find((p) => p.key === 'front_piece')!)
const core = buildCore(result)
const field = buildBodyField(core.positions, core.indices)
const garment = buildHangPair('front', front, field)

const centroidY = (pos: Float32Array): number => {
  let s = 0
  for (let i = 1; i < pos.length; i += 3) s += pos[i]
  return s / (pos.length / 3)
}

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

// 自由垂通用口径（前身/后身 describe 共用，seamDir = 中缝朝向
// +1 前中 +Z / −1 后中 −Z）：收敛/pin 恒守/缝达标/不穿地/质心下降
// + 五期两条形态金标（裆尖内收、缝向不凸）
function assertFreeHang(
  sim: DrapeSim, placed: Garment, cy0: number, seamDir: 1 | -1 = 1,
): void {
  expect(sim.capped).toBe(false)   // 真静止，非封顶兜底
  expect(sim.frozen).toBe(false)
  for (let i = 0; i < sim.pos.length; i++) {
    expect(Number.isFinite(sim.pos[i])).toBe(true)
  }
  // 腰口悬挂支点恒守初始位（含终点角全向钉——不补钉会下垂出顶部折角，
  // 实测侧角 −2.1cm 急坠）
  for (let k = 0; k < sim.pinIdx.length; k++) {
    const i3 = 3 * sim.pinIdx[k]
    expect(sim.pos[i3]).toBeCloseTo(sim.pinTarget[3 * k], 6)
    expect(sim.pos[i3 + 1]).toBeCloseTo(sim.pinTarget[3 * k + 1], 6)
    expect(sim.pos[i3 + 2]).toBeCloseTo(sim.pinTarget[3 * k + 2], 6)
  }
  // 腰口 Y 钉恒守高度（全向钉会锁成刚性折线/与缝合拔河出顶中缺口）
  for (let k = 0; k < sim.pinYIdx.length; k++) {
    expect(sim.pos[3 * sim.pinYIdx[k] + 1])
      .toBeCloseTo(sim.pinYTarget[k], 6)
  }
  // 前中缝合对存在且达标（旧整裤缝合金标口径）
  expect(sim.seamIdx.length).toBeGreaterThan(0)
  const { avg, p95 } = seamStats(sim)
  expect(avg).toBeLessThan(0.3)
  expect(p95).toBeLessThan(0.8)
  // 地面碰撞终点：不穿地（显示层 hemLift 抬 2cm，解算本体 y≥0）
  expect(minY(sim.pos)).toBeGreaterThanOrEqual(-1e-4)
  // 引力生效：质心下降
  expect(centroidY(sim.pos) - cy0).toBeLessThan(-2)
  // ---- 五期形态金标 ----
  // ① 裆尖内收（「交点在裆下」）：crotch_vertex = 中缝链首点（front
  //    rise / back cb 同构），L 侧（offset 0）终态轴心半径比摆位初态
  //    收缩 ≥2cm
  const rise = placed.parts[0].mesh.runs.find(
    (r) => r.name === 'rise' || r.name === 'cb')
  expect(rise).toBeDefined()
  const ci = 3 * (placed.parts[0].offset + rise!.indices[0])
  const r0 = Math.hypot(placed.pos[ci], placed.pos[ci + 2])
  const r1 = Math.hypot(sim.pos[ci], sim.pos[ci + 2])
  expect(r1).toBeLessThan(r0 - 2)
  // ② 缝线不凸（「拿着前片上部不可能是这个造型」）：中缝链（对折线）
  //    自身的缝向外伸终态比摆位初态收缩 ≥2cm——自由垂后对折线垂挂，
  //    不再被撑到摆位弧半径。钉缝链而非全体粒子：全粒极值被拖地铺展
  //    污染（下摆堆地径向摊开——后片布多堆得宽，实测后身全粒仅缩
  //    0.9cm 假阴），前后中缝镜像同构（+Z 取 z / −Z 取 −z，大者更外）
  const seamExt = (pos: Float32Array): number => {
    let m = -Infinity
    for (const i of rise!.indices) {
      m = Math.max(m, seamDir * pos[3 * i + 2])
    }
    return m
  }
  expect(seamExt(sim.pos)).toBeLessThan(seamExt(placed.pos) - 2)
}

describe('drape：前片 L+R 引力自由垂 + 前中缝合（五期）', () => {
  it('600 帧内真收敛、钉恒守、前中缝达标、不穿地、质心下降、裆尖内收不前凸',
    { timeout: 180000 }, () => {
      const sim = buildDrape(garment, null)   // 自由垂：无撑型芯碰撞
      const cy0 = centroidY(garment.pos)
      const st = runToSettle(sim)
      expect(st).toBe('settled')
      assertFreeHang(sim, garment, cy0)
    })
})

describe('drape：前身并集宿主自由垂（前片+袋贴缝合，四期宿主 + 五期口径）', () => {
  // 本方案最大数值风险验证点：袋贴月牙带并入宿主（腰口段 + facing 月牙
  // 边）后，自由垂收敛口径（600 帧真 settle / pin 恒守 / 前中缝 avg<0.3 /
  // 不穿地 / 质心下降 >2cm / 裆尖内收不前凸）不被破坏。夹具 =
  // fixture_fitting_pocket.json（引擎直出，front_facing 拼入，hasFacing
  // =true 前置守卫）。
  const pocket: FittingResult = JSON.parse(
    readFileSync(`${HERE}/fixture_fitting_pocket.json`, 'utf8'))
  const panel = buildFrontPanel(pocket)
  const core = buildCore(pocket)
  const field = buildBodyField(core.positions, core.indices)
  const garment = buildHangPair('front', panel.host, field)

  it('袋贴月牙带并入后自由垂全部口径照旧', { timeout: 180000 }, () => {
    expect(panel.hasFacing).toBe(true)   // 前置：并集成功（否则测退化形态无意义）
    const sim = buildDrape(garment, null)
    const cy0 = centroidY(garment.pos)
    const st = runToSettle(sim)
    expect(st).toBe('settled')
    assertFreeHang(sim, garment, cy0)
  })
})

describe('drape：后身并集宿主自由垂（后片+育克缝合 + 后中 cb 缝合，六期）', () => {
  // 后身 = 机头+后片沿机头下口线缝合的并集宿主（panel.ts buildBackPanel）
  // 后扇区摆位（back θ∈[−180°,−90°]）→ 自由垂 + 后浪（cb 聚合链：裆尖
  // →P0→O 贯通育克到腰）L/R 同号缝合对。验收口径与前身同构：600 帧真
  // settle / pin 恒守 / 后中缝 avg<0.3、P95<0.8 / 不穿地 / 质心下降 /
  // 裆尖内收不前凸。夹具 = fixture_fitting_yoke.json（无省贴合，
  // hasYoke=true 前置守卫）。
  const yokeFix: FittingResult = JSON.parse(
    readFileSync(`${HERE}/fixture_fitting_yoke.json`, 'utf8'))
  const backPanel = buildBackPanel(yokeFix)
  const core = buildCore(yokeFix)
  const field = buildBodyField(core.positions, core.indices)
  const garment = buildHangPair('back', backPanel.host, field)

  it('育克拼入后自由垂全部口径照旧（后中 cb 缝合对）', { timeout: 180000 }, () => {
    expect(backPanel.hasYoke).toBe(true)   // 前置：并集成功（否则测退化形态无意义）
    const sim = buildDrape(garment, null)
    // 后中缝合对存在：seamIdx 覆盖 cb 聚合链（裆尖→腰口，贯通育克）
    expect(sim.seamIdx.length).toBeGreaterThan(0)
    const cy0 = centroidY(garment.pos)
    const st = runToSettle(sim)
    expect(st).toBe('settled')
    assertFreeHang(sim, garment, cy0, -1)   // 后中朝 −Z：缝向不凸取 minZ
  })
})
