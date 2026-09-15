// PBD 解算器（f0ce40d 原样移植 + 二期三处适配）：
//   ① Mannequin 三管解析碰撞 → Collider（BVH+场宽相，collide.ts）
//   ② 缝合拉链式渐进激活：preRelax 前 zipperIters 迭代内按 seamRank
//     （锚点→末端）逐对放开，防全边同收的冲量
//   ③ 裆底防下垂：crotchIdx 钉初始位（preRelax 全程 + 动力学前
//     crotchHoldFrames 帧），之后释放交还缝合约束
// 帧结构/热启动/发散兜底阶梯（NaN→恢复好帧降阻尼增迭代→连败 3 冻结）
// 均为旧链原值。
import type { BodyField } from '../placement'
import { bandWarp, placePoint } from '../placement'
import { SOLVER_PRIOR } from '../priors'
import type { Garment, GarmentPart } from '../seams'
import type { Collider } from './collide'
import { projectDistance, projectPin, projectPinY } from '../pbd/constraints'

export interface SimState {
  garment: Garment
  warp: (y: number) => number
  field: BodyField
  collider: Collider
  pos: Float32Array
  prev: Float32Array
  vel: Float32Array
  damping: number
  iterations: number
  substeps: number
  stepCount: number
  settledFrames: number
  settled: boolean
  frozen: boolean
  avgSpeed: number
  failStreak: number
  lastGood: Float32Array
  crotchHold: number       // 裆尖钉住剩余帧（<0 = 已释放）
}

export type SimStatus = 'running' | 'settled' | 'frozen'

// seamGate：当前已激活的 seamRank 阈值（preRelax 拉链渐进；动力学传
// Infinity 全量激活）。crotchPin 由 sim.crotchHold 驱动。
function projectConstraints(sim: SimState, seamGate: number): void {
  const { garment, pos, iterations } = sim
  const p = SOLVER_PRIOR
  for (let it = 0; it < iterations; it++) {
    for (const part of garment.parts) {
      const { dist, bend, bendK, bendKArr } = part.mesh
      const { offset } = part
      const bK = bendK ?? p.bendStiffness
      for (let c = 0; c < dist.length; c += 3) {
        projectDistance(pos, offset + dist[c], offset + dist[c + 1],
          dist[c + 2], p.stretchStiffness)
      }
      if (bendKArr) {
        for (let c = 0, k = 0; c < bend.length; c += 3, k++) {
          projectDistance(pos, offset + bend[c], offset + bend[c + 1],
            bend[c + 2], bendKArr[k])
        }
      } else {
        for (let c = 0; c < bend.length; c += 3) {
          projectDistance(pos, offset + bend[c], offset + bend[c + 1],
            bend[c + 2], bK)
        }
      }
    }
    for (let c = 0; c < garment.seam.length; c += 2) {
      if (garment.seamRank[c / 2] > seamGate) continue
      projectDistance(pos, garment.seam[c], garment.seam[c + 1], 0,
        p.seamStiffness)
    }
    if (garment.pinYOnly) {
      // 腰头 Y-only：高度挂住，环向/径向自由（滑移自对齐）
      for (let k = 0; k < garment.pinIdx.length; k++) {
        projectPinY(pos, garment.pinIdx[k], garment.pinTarget[3 * k + 1],
          p.pinWeight)
      }
    } else {
      for (let k = 0; k < garment.pinIdx.length; k++) {
        const i = garment.pinIdx[k]
        projectPin(pos, i, garment.pinTarget[3 * k],
          garment.pinTarget[3 * k + 1], garment.pinTarget[3 * k + 2],
          p.pinWeight)
      }
    }
    if (sim.crotchHold !== 0) {
      for (let k = 0; k < garment.crotchIdx.length; k++) {
        const i = garment.crotchIdx[k]
        projectPin(pos, i, garment.crotchTarget[3 * k],
          garment.crotchTarget[3 * k + 1], garment.crotchTarget[3 * k + 2],
          p.pinWeight)
      }
    }
  }
}

function collideAll(sim: SimState): void {
  const { collisionSkin, friction } = SOLVER_PRIOR
  sim.collider.resolveAll(sim.pos, sim.prev, sim.garment.total,
    collisionSkin, friction)
}

// 约束-only 预松弛（无重力无惯性）：冷启动把初始摆位压到缝合闭合。
// 拉链激活：前 zipperIters 迭代按 rank 渐进（iter k 激活 rank ≤ k/N）；
// 裆尖钉全程；碰撞每 preRelaxCollideEvery 迭代扫一次（初摆位本就不穿体，
// BVH 查询贵——旧三管解析每迭代都碰的口径不搬）。
function preRelax(sim: SimState, iters: number): void {
  sim.prev.set(sim.pos)
  const savedIters = sim.iterations
  sim.iterations = 1
  const zIters = Math.min(SOLVER_PRIOR.zipperIters, iters)
  for (let k = 0; k < iters; k++) {
    projectConstraints(sim, k >= zIters ? Infinity : k / zIters)
    if (k % SOLVER_PRIOR.preRelaxCollideEvery === 0) collideAll(sim)
  }
  sim.iterations = savedIters
  sim.prev.set(sim.pos)
}

// 新粒子在旧部件网格上的重心插值热启动；新区域（locate 落空）冷摆位
function inheritFrom(sim: SimState, old: SimState): void {
  const { pos, vel } = sim
  for (const part of sim.garment.parts) {
    const oldPart = old.garment.parts.find(
      (q: GarmentPart) => q.key === part.key && q.side === part.side)
    const { xy } = part.mesh
    const off = part.offset
    let xMin = Infinity, xMax = -Infinity
    for (let i = 0; i < xy.length; i += 2) {
      xMin = Math.min(xMin, xy[i]); xMax = Math.max(xMax, xy[i])
    }
    for (let i = 0; i < xy.length / 2; i++) {
      const gi = off + i
      const i3 = 3 * gi
      const loc = oldPart ? oldPart.mesh.locate(xy[2 * i], xy[2 * i + 1]) : null
      if (loc && oldPart) {
        const t = loc.tri
        const a = oldPart.offset + oldPart.mesh.tri[3 * t]
        const b = oldPart.offset + oldPart.mesh.tri[3 * t + 1]
        const c = oldPart.offset + oldPart.mesh.tri[3 * t + 2]
        const [w0, w1, w2] = loc.w
        for (let d = 0; d < 3; d++) {
          pos[i3 + d] = w0 * old.pos[3 * a + d] + w1 * old.pos[3 * b + d]
            + w2 * old.pos[3 * c + d]
          vel[i3 + d] = 0.5 * (w0 * old.vel[3 * a + d] + w1 * old.vel[3 * b + d]
            + w2 * old.vel[3 * c + d])
        }
      } else {
        // band 新粒子冷摆位同 seams 口径：腰站锚+真布高（不吃 warp 顶段拉伸）
        const w = part.key === 'band' && sim.garment.bandY0 !== null
          ? bandWarp(sim.warp, sim.garment.bandY0) : sim.warp
        const [px, py, pz] = placePoint(
          part.key, part.side, xy[2 * i], xy[2 * i + 1], xMin, xMax, w,
          sim.field)
        pos[i3] = px; pos[i3 + 1] = py; pos[i3 + 2] = pz
      }
    }
  }
}

export function createSim(
  garment: Garment,
  warp: (y: number) => number,
  field: BodyField,
  collider: Collider,
  warmFrom?: SimState,
): SimState {
  const pos = new Float32Array(garment.pos)
  const sim: SimState = {
    garment, warp, field, collider, pos,
    prev: new Float32Array(pos),
    vel: new Float32Array(pos.length),
    damping: SOLVER_PRIOR.damping,
    iterations: SOLVER_PRIOR.iterations,
    substeps: SOLVER_PRIOR.substeps,
    stepCount: 0, settledFrames: 0, settled: false, frozen: false,
    avgSpeed: 0, failStreak: 0,
    lastGood: new Float32Array(pos),
    crotchHold: SOLVER_PRIOR.crotchHoldFrames,
  }
  if (warmFrom) {
    inheritFrom(sim, warmFrom)
    sim.lastGood.set(sim.pos)
    preRelax(sim, Math.round(SOLVER_PRIOR.preRelaxIters * 0.3))
  } else {
    preRelax(sim, SOLVER_PRIOR.preRelaxIters)
  }
  return sim
}

// 一帧（worker 60Hz 调一次）；返回状态供停走判断
export function stepSim(sim: SimState): SimStatus {
  if (sim.settled || sim.frozen) {
    return sim.frozen ? 'frozen' : 'settled'
  }
  const p = SOLVER_PRIOR
  const dtSub = p.dt / sim.substeps
  const g = p.gravity
  sim.lastGood.set(sim.pos)

  for (let sub = 0; sub < sim.substeps; sub++) {
    const { pos, prev, vel } = sim
    for (let i3 = 0; i3 < pos.length; i3 += 3) {
      vel[i3 + 1] += g * dtSub
      vel[i3] *= sim.damping
      vel[i3 + 1] *= sim.damping
      vel[i3 + 2] *= sim.damping
      prev[i3] = pos[i3]; prev[i3 + 1] = pos[i3 + 1]; prev[i3 + 2] = pos[i3 + 2]
      pos[i3] += vel[i3] * dtSub
      pos[i3 + 1] += vel[i3 + 1] * dtSub
      pos[i3 + 2] += vel[i3 + 2] * dtSub
    }
    projectConstraints(sim, Infinity)
    collideAll(sim)
    for (let i3 = 0; i3 < pos.length; i3 += 3) {
      vel[i3] = (pos[i3] - prev[i3]) / dtSub
      vel[i3 + 1] = (pos[i3 + 1] - prev[i3 + 1]) / dtSub
      vel[i3 + 2] = (pos[i3 + 2] - prev[i3 + 2]) / dtSub
    }
  }
  if (sim.crotchHold > 0) sim.crotchHold -= 1

  // 发散检测（NaN / 飞点）：恢复好帧降阻尼增迭代重试，连败冻结
  let bad = false
  const { pos, vel } = sim
  let speedSum = 0
  for (let i3 = 0; i3 < pos.length; i3 += 3) {
    if (!Number.isFinite(pos[i3]) || Math.abs(pos[i3 + 1]) > 1e4) { bad = true; break }
    speedSum += Math.abs(vel[i3]) + Math.abs(vel[i3 + 1]) + Math.abs(vel[i3 + 2])
  }
  if (bad) {
    sim.pos.set(sim.lastGood)
    sim.vel.fill(0)
    sim.damping *= 0.9
    sim.iterations = Math.min(16, sim.iterations * 2)
    sim.failStreak += 1
    if (sim.failStreak >= 3) sim.frozen = true
    return sim.frozen ? 'frozen' : 'running'
  }
  sim.failStreak = 0
  sim.stepCount += 1
  sim.avgSpeed = speedSum / sim.garment.total
  sim.settledFrames = sim.avgSpeed < p.settleSpeed
    ? sim.settledFrames + 1 : 0
  if (sim.settledFrames >= p.settleFrames) sim.settled = true
  return sim.settled ? 'settled' : 'running'
}

// 缝合误差统计（M1 验收 + 界面读数）：全部缝合对点距 avg / P95。
// 读 sim.pos（当前解算位）——garment.pos 是初始摆位，别解构它
export function seamStats(sim: SimState): { avg: number; p95: number } {
  const { seam } = sim.garment
  const { pos } = sim
  const S = seam.length / 2
  if (S === 0) return { avg: 0, p95: 0 }
  const errs = new Float64Array(S)
  let sum = 0
  for (let c = 0; c < seam.length; c += 2) {
    const i = 3 * seam[c], j = 3 * seam[c + 1]
    const e = Math.hypot(pos[j] - pos[i], pos[j + 1] - pos[i + 1],
      pos[j + 2] - pos[i + 2])
    errs[c / 2] = e
    sum += e
  }
  errs.sort()
  return { avg: sum / S, p95: errs[Math.floor(0.95 * (S - 1))] }
}

// 视图按帧取位置渲染；settled/frozen 后 pos 不再变，直接复用
export function simPositions(sim: SimState): Float32Array {
  return sim.pos
}
