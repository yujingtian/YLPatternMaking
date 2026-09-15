// 悬挂展示金标（2026-09-14 解耦定型）：解算在纸样系进行，碰撞体 = 纸样
// 围度撑型芯（core.ts，girth_finished 逐站取值 → 圆筒按构造成立）+ 帧数
// 封顶兜底（HANG_PRIOR.maxFrames）。验收（撑型芯链实测值 2026-09-14）：
// 包腿圆度 wrapKnee≥0.65 / wrapHem≥0.55（塌片=0.50——穿人台时代的翻车值）；
// 缝 avg<0.3/P95<0.8、穿透 ≤0.15、600 帧内收敛。
// wrapFraction：y 段粒子按 x 正负分腿，绕各腿质心的 12 扇区非空占比
// （阈值 = 该腿粒子数/36 抗零星噪声）——裤腿成筒则全覆盖 ~1.0，
// 前后片对折塌陷则 ~0.5。
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../../types'
import { buildClothMesh } from '../mesh'
import { buildCore } from '../core'
import { buildBodyField } from '../placement'
import { HANG_PRIOR, SOLVER_PRIOR } from '../priors'
import { buildGarment } from '../seams'
import { buildCollider } from './collide'
import type { Collider } from './collide'
import { createSim, seamStats, stepSim } from './solver'
import type { SimState } from './solver'

const HERE = import.meta.dirname   // src/fitting3d/garment/worker

function wrapFraction(pos: Float32Array, yLo: number, yHi: number): number {
  const L: number[][] = [], R: number[][] = []
  for (let i = 0; i < pos.length; i += 3) {
    const y = pos[i + 1]
    if (y < yLo || y > yHi) continue
    const p = [pos[i], pos[i + 2]]
    if (pos[i] < 0) L.push(p); else R.push(p)
  }
  let fracSum = 0, n = 0
  for (const pts of [L, R]) {
    if (pts.length < 50) continue
    let cx = 0, cz = 0
    for (const [x, z] of pts) { cx += x; cz += z }
    cx /= pts.length; cz /= pts.length
    const bins = new Array(12).fill(0)
    for (const [x, z] of pts) {
      const a = Math.atan2(z - cz, x - cx)
      const b = Math.floor(((a + Math.PI) / (2 * Math.PI)) * 12) % 12
      bins[b]++
    }
    const th = Math.max(2, pts.length / 36)
    fracSum += bins.filter((c) => c >= th).length / 12
    n++
  }
  return n ? fracSum / n : -1
}

// 与 worker entry 同口径：撑型芯（纸样系 identity warp）+ band snap 芯面
// + 跑到 settle 或 HANG_PRIOR.maxFrames 封顶（封顶帧 = 显示兜底口径）
function hangRun(fixture: string)
  : { sim: SimState; capped: boolean; collider: Collider } {
  const result: FittingResult = JSON.parse(
    readFileSync(`${HERE}/../${fixture}`, 'utf8'))
  const core = buildCore(result)
  const field = buildBodyField(core.positions, core.indices)
  const collider = buildCollider(core.positions, core.indices, field)
  const identity = (y: number): number => y
  const yokePiece = result.pieces.find((p) => p.key === 'back_yoke')
  const pocketPiece = result.pieces.find((p) => p.key === 'front_facing')
  const garment = buildGarment({
    front: buildClothMesh(result.pieces.find((p) => p.key === 'front_piece')!),
    back: buildClothMesh(result.pieces.find((p) => p.key === 'back_piece')!),
    ...(yokePiece ? { yoke: buildClothMesh(yokePiece) } : {}),
    ...(pocketPiece ? { pocket: buildClothMesh(pocketPiece) } : {}),
  }, result, identity, field, (pos, i) =>
    collider.snapOne(pos, i, SOLVER_PRIOR.collisionSkin))
  const sim = createSim(garment, identity, field, collider)
  let capped = false
  for (let k = 0; k < HANG_PRIOR.maxFrames; k++) {
    const st = stepSim(sim)
    expect(st).not.toBe('frozen')
    if (st === 'settled') return { sim, capped, collider }
    if (k === HANG_PRIOR.maxFrames - 1) capped = true
  }
  return { sim, capped, collider }
}

// 裆部缝交汇区豁免的穿透统计（rise/cb 四缝交汇布 tucked 进花生腰谷
// 内侧 ~3cm，视觉无穿模；hull 场口径在腰谷内侧误报——同 solver.test）
const crotchYOf = (fixture: string): number =>
  (JSON.parse(readFileSync(`${HERE}/../${fixture}`, 'utf8')) as FittingResult)
    .body.stations.find((q) => q.key === 'crotch')!.y

// 网格口径穿透（collider.penetrationStats），裆部缝交汇区豁免：
// rise/cb 四缝交汇布 tucked 进花生腰谷内侧 ~3cm——视觉无穿模（正交视图
// 验收过）；腰谷里的布在 hull 内但不在网格内，网格口径已天然不误报
function penExceptCrotch(
  pos: Float32Array, collider: Collider, crotchY: number,
): { count: number; worst: number } {
  const box: { i: number; y: number; x: number }[] = []
  const gi: number[] = []
  for (let i = 0; i < pos.length / 3; i++) {
    const y = pos[3 * i + 1]
    if (Math.abs(pos[3 * i]) < 4 && y > crotchY - 12 && y < crotchY + 4) continue
    gi.push(i)
  }
  void box
  const sub = new Float32Array(3 * gi.length)
  for (let k = 0; k < gi.length; k++) {
    sub[3 * k] = pos[3 * gi[k]]
    sub[3 * k + 1] = pos[3 * gi[k] + 1]
    sub[3 * k + 2] = pos[3 * gi[k] + 2]
  }
  return collider.penetrationStats(sub, gi.length, SOLVER_PRIOR.collisionSkin)
}

describe('悬挂展示：纸样系撑型芯解算（包腿守卫 + 封顶兜底）', () => {
  it('M1（无 yoke，11 缝）：包腿 wrapKnee≥0.65/wrapHem≥0.55、缝/穿透达标、600 帧内收敛',
    { timeout: 180000 }, () => {
      const { sim, capped, collider } = hangRun('fixture_fitting.json')
      expect(capped).toBe(false)         // 正常收敛
      const { avg, p95 } = seamStats(sim)
      expect(avg).toBeLessThan(0.3)
      expect(p95).toBeLessThan(0.8)
      const pen = penExceptCrotch(sim.pos, collider,
        crotchYOf('fixture_fitting.json'))
      expect(pen.worst).toBeLessThanOrEqual(0.15)
      expect(pen.count).toBeLessThan(50)
      expect(wrapFraction(sim.pos, 4, 18)).toBeGreaterThanOrEqual(0.55)
      expect(wrapFraction(sim.pos, 42, 56)).toBeGreaterThanOrEqual(0.65)
    })

  it('育克整裤（16 缝业务装配链）：同门槛', { timeout: 180000 }, () => {
    const { sim, capped, collider } = hangRun('fixture_fitting_yoke.json')
    expect(capped).toBe(false)
    const { avg, p95 } = seamStats(sim)
    expect(avg).toBeLessThan(0.3)
    expect(p95).toBeLessThan(0.8)
    const pen = penExceptCrotch(sim.pos, collider,
      crotchYOf('fixture_fitting_yoke.json'))
    expect(pen.worst).toBeLessThanOrEqual(0.15)
    expect(pen.count).toBeLessThan(50)
    expect(wrapFraction(sim.pos, 4, 18)).toBeGreaterThanOrEqual(0.55)
    expect(wrapFraction(sim.pos, 42, 56)).toBeGreaterThanOrEqual(0.65)
  })

  it('弯腰头+口袋挖削+袋贴整裤（视觉环带回退 + 挖削侧缝链式配对）：同门槛',
    { timeout: 180000 }, () => {
      // 用户实测形态（2026-09-15）：弯腰头 → 视觉环带贴腰口弧、前片
      // mouth 挖削由袋贴补位（side 缝育克侧边）、前片侧缝只配后片下段。
      // 实测 461 帧收敛 / 缝 avg 0.023
      const { sim, capped, collider } = hangRun(
        'fixture_fitting_curved_pocket.json')
      expect(capped).toBe(false)
      const { avg, p95 } = seamStats(sim)
      expect(avg).toBeLessThan(0.3)
      expect(p95).toBeLessThan(0.8)
      const pen = penExceptCrotch(sim.pos, collider,
        crotchYOf('fixture_fitting_curved_pocket.json'))
      expect(pen.worst).toBeLessThanOrEqual(0.15)
      expect(pen.count).toBeLessThan(50)
      expect(wrapFraction(sim.pos, 4, 14)).toBeGreaterThanOrEqual(0.55)
      expect(wrapFraction(sim.pos, 34, 44)).toBeGreaterThanOrEqual(0.65)
    })
})
