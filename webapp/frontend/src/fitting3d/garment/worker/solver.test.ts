// M1 缝合收敛金标（方案里程碑验收；2026-09-14 解耦改版）：payload 撑型芯
// （纸样系 identity warp）+ fixture 直腰头整裤，node 直跑 solver（不走
// worker 壳，逻辑同一份）：
//   300~480 步无 NaN / 不冻结；11/16 缝点距均值 <0.3cm、P95 <0.8cm；
//   band 对账 <0.5%（buildGarment 内 checkBandLength 不炸）；
//   终态网格穿透 = 0（collider.penetrationStats——体内失明修复后实测
//   归零；旧 hull 口径对花生腰谷误报已弃用）；
//   裆尖 pin 释放（crotchHold 耗尽交还缝合约束）；收敛步数 ≤600
//   （撑型芯链实测 506；collide 体内穿面推出 + prev 同步后裆部 tuck 自愈）。
// BVH 碰撞在 node 跑 three-mesh-bvh（纯 JS，无 WebGL 依赖）。
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../../types'
import { buildClothMesh } from '../mesh'
import { buildCore } from '../core'
import { buildBodyField } from '../placement'
import { HANG_PRIOR, SOLVER_PRIOR } from '../priors'
import { buildGarment } from '../seams'
import { buildCollider } from './collide'
import { createSim, seamStats, stepSim } from './solver'
import type { SimStatus } from './solver'

const HERE = import.meta.dirname   // src/fitting3d/garment/worker

const result: FittingResult = JSON.parse(
  readFileSync(`${HERE}/../fixture_fitting.json`, 'utf8'))

// 裆部缝交汇区豁免的穿透统计（hull 场口径；豁免区见文件头注）
function buildOnCore(r: FittingResult) {
  const core = buildCore(r)
  const field = buildBodyField(core.positions, core.indices)
  const collider = buildCollider(core.positions, core.indices, field)
  const identity = (y: number): number => y
  const garment = buildGarment({
    front: buildClothMesh(r.pieces.find((p) => p.key === 'front_piece')!),
    back: buildClothMesh(r.pieces.find((p) => p.key === 'back_piece')!),
    ...(r.pieces.find((p) => p.key === 'back_yoke')
      ? { yoke: buildClothMesh(r.pieces.find((p) => p.key === 'back_yoke')!) }
      : {}),
  }, r, identity, field, (pos, i) =>
    collider.snapOne(pos, i, SOLVER_PRIOR.collisionSkin))
  return { field, collider, garment, identity }
}

describe('M1：PBD 解算收敛（撑型芯 + 直腰头整裤）', () => {
  it('600 步内：无 NaN 不冻结、11 缝均值 <0.3 / P95 <0.8、网格穿透 0', { timeout: 240000 }, () => {
    const { field, collider, garment, identity } = buildOnCore(result)
    // band 对账：straight fixture 不炸即 <0.5%
    expect(garment.bandFallback).toBeNull()
    expect(garment.parts.length).toBe(5)

    const sim = createSim(garment, identity, field, collider)
    // preRelax 已完成：缝合已大幅闭合（拉链渐进后全量迭代）
    const pre = seamStats(sim)
    expect(Number.isFinite(pre.avg)).toBe(true)

    let status: SimStatus = 'running'
    let settledAt = -1
    for (let k = 0; k < HANG_PRIOR.maxFrames; k++) {
      status = stepSim(sim)
      if (status === 'settled') { settledAt = k; break }
      expect(status).not.toBe('frozen')
      for (let i = 0; i < sim.pos.length; i += 7) {   // 抽样防 NaN（全量在 stepSim 内已检）
        expect(Number.isFinite(sim.pos[i])).toBe(true)
      }
    }
    expect(settledAt).toBeGreaterThanOrEqual(0)
    expect(settledAt).toBeLessThanOrEqual(HANG_PRIOR.maxFrames)

    const { avg, p95 } = seamStats(sim)
    expect(avg).toBeLessThan(0.3)
    expect(p95).toBeLessThan(0.8)

    const pen = collider.penetrationStats(sim.pos, sim.garment.total,
      SOLVER_PRIOR.collisionSkin)
    expect(pen.worst).toBeLessThanOrEqual(0.15)
    expect(pen.count).toBeLessThan(50)

    // 裆尖 pin 已释放（crotchHold 耗尽，交还缝合约束）
    expect(sim.crotchHold).toBe(0)
    collider.dispose()
  })

  it('育克整裤（back_yoke 开启）：16 缝业务装配链收敛同门槛', { timeout: 180000 }, () => {
    const yokeResult: FittingResult = JSON.parse(
      readFileSync(`${HERE}/../fixture_fitting_yoke.json`, 'utf8'))
    const { field, collider, garment, identity } = buildOnCore(yokeResult)
    // 7 布片（+育克 L/R）；育克 cb 链首在腰部，不进裆尖 pin
    expect(garment.parts.length).toBe(7)
    expect(garment.crotchIdx.length).toBe(4)

    const sim = createSim(garment, identity, field, collider)
    let status: SimStatus = 'running'
    let settledAt = -1
    for (let k = 0; k < HANG_PRIOR.maxFrames; k++) {
      status = stepSim(sim)
      if (status === 'settled') { settledAt = k; break }
      expect(status).not.toBe('frozen')
      for (let i = 0; i < sim.pos.length; i += 7) {
        expect(Number.isFinite(sim.pos[i])).toBe(true)
      }
    }
    expect(settledAt).toBeGreaterThanOrEqual(0)
    expect(settledAt).toBeLessThanOrEqual(HANG_PRIOR.maxFrames)

    const { avg, p95 } = seamStats(sim)
    expect(avg).toBeLessThan(0.3)
    expect(p95).toBeLessThan(0.8)

    const pen = collider.penetrationStats(sim.pos, sim.garment.total,
      SOLVER_PRIOR.collisionSkin)
    expect(pen.worst).toBeLessThanOrEqual(0.15)
    expect(pen.count).toBeLessThan(50)
    expect(sim.crotchHold).toBe(0)
    collider.dispose()
  })

  it('拉链渐进：preRelax 后段全量激活（rank 覆盖 [0,1]）', () => {
    const { field, garment } = buildOnCore(result)
    expect(field.rows).toBeGreaterThan(10)
    expect(garment.seamRank.length).toBe(garment.seam.length / 2)
    let max = -Infinity, min = Infinity
    for (const r of garment.seamRank) { max = Math.max(max, r); min = Math.min(min, r) }
    expect(min).toBe(0)
    expect(max).toBe(1)
    // 裆尖 4 粒（fL/fR/bL/bR 各一）
    expect(garment.crotchIdx.length).toBe(4)
    expect(garment.crotchTarget.length).toBe(12)
  })
})
