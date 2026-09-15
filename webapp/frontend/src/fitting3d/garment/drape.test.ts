// 引力下垂金标（重建二期 2026-09-15；同日补前中缝合）：前片 L+R 从初始
// 摆位解算至静止，前中缝合对（L/R rise 链镜像配对 rest=0）把前中闭合。
// 验收：600 帧内真 settle（非封顶）、无 NaN、腰口 pin 恒守初始位、
// 前中缝 avg<0.3/P95<0.8（旧整裤缝合金标口径）、settle 后对撑型芯场
// 穿透 0（径向碰撞按构造归零）、质心相对初始摆位下降 >2cm（引力生效
// ——布从 garmentGap 摆位沉降贴芯 + 裆下布坠入腰谷）。
// 夹具 = fixture_fitting.json（引擎 build_fitting_payload 直出）。
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../types'
import { buildFrontPair } from './assemble'
import { buildCore, CORE_SKIN } from './core'
import { buildClothMesh } from './mesh'
import { buildBodyField, penetrationStats } from './placement'
import { buildDrape, seamStats, stepDrape } from './drape'
import { DRAPE_PRIOR } from './priors'

const HERE = import.meta.dirname   // src/fitting3d/garment

const result: FittingResult = JSON.parse(
  readFileSync(`${HERE}/fixture_fitting.json`, 'utf8'))

const front = buildClothMesh(result.pieces.find((p) => p.key === 'front_piece')!)
const core = buildCore(result)
const field = buildBodyField(core.positions, core.indices)
const garment = buildFrontPair(front, field)

const centroidY = (pos: Float32Array): number => {
  let s = 0
  for (let i = 1; i < pos.length; i += 3) s += pos[i]
  return s / (pos.length / 3)
}

describe('drape：前片 L+R 引力下垂 + 前中缝合（重建二期）', () => {
  it('600 帧内真收敛、钉恒守、前中缝达标、穿透 0、质心下降 >2cm',
    { timeout: 180000 }, () => {
      const sim = buildDrape(garment, field)
      const cy0 = centroidY(garment.pos)
      let st: ReturnType<typeof stepDrape> = 'running'
      for (let k = 0; k < DRAPE_PRIOR.maxFrames && st === 'running'; k++) {
        st = stepDrape(sim)
      }
      expect(st).toBe('settled')
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
      // 前中角 Y 钉恒守高度（全向钉会锁在 θ≈−20° 摆位与缝合拔河出顶中缺口）
      for (let k = 0; k < sim.pinYIdx.length; k++) {
        expect(sim.pos[3 * sim.pinYIdx[k] + 1])
          .toBeCloseTo(sim.pinYTarget[k], 6)
      }
      // 前中缝合对存在且达标（旧整裤缝合金标口径）
      expect(sim.seamIdx.length).toBeGreaterThan(0)
      const { avg, p95 } = seamStats(sim)
      expect(avg).toBeLessThan(0.3)
      expect(p95).toBeLessThan(0.8)
      // 撑型芯场穿透按构造归零（径向碰撞终点即 skin 壳）
      const pen = penetrationStats(sim.pos, field, CORE_SKIN)
      expect(pen.count).toBe(0)
      expect(pen.worst).toBe(0)
      // 引力生效：质心下降
      expect(centroidY(sim.pos) - cy0).toBeLessThan(-2)
    })
})
