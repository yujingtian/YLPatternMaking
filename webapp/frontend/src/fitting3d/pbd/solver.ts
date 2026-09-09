// PBD 解算器：verlet 积分 + Gauss-Seidel 约束投影 + 人台碰撞。
// 帧结构：substeps × [积分 -> iterations×约束 -> 碰撞 -> 速度更新]，
// rAF 每 tick 一帧；碰撞每子步一次（约束迭代内不碰撞，省 pow 开销）。
// 热启动：新网格顶点在旧网格重心插值继承位置与 0.5×速度，跳过冷启动
// 预松弛的大部分。发散兜底阶梯：NaN/飞点 -> 恢复上一好帧（阻尼×0.9、
// 迭代×2 重试）-> 连败 3 次冻结当前帧（frozen=true，视图给「仿真已暂停」）。
import type { Mannequin } from '../mannequin'
import { SOLVER_PRIOR } from '../priors'
import type { Garment, GarmentPart } from '../seams'
import { placePoint } from '../seams'
import { collideOne } from './collide'
import { projectDistance, projectPin } from './constraints'

export interface SimState {
  garment: Garment
  man: Mannequin
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
}

export type SimStatus = 'running' | 'settled' | 'frozen'

function projectConstraints(sim: SimState): void {
  const { garment, pos, iterations } = sim
  const p = SOLVER_PRIOR
  for (let it = 0; it < iterations; it++) {
    for (const part of garment.parts) {
      const { dist, bend } = part.mesh
      const { offset } = part
      for (let c = 0; c < dist.length; c += 3) {
        projectDistance(pos, offset + dist[c], offset + dist[c + 1],
          dist[c + 2], p.stretchStiffness)
      }
      for (let c = 0; c < bend.length; c += 3) {
        projectDistance(pos, offset + bend[c], offset + bend[c + 1],
          bend[c + 2], p.bendStiffness)
      }
    }
    for (let c = 0; c < garment.seam.length; c += 2) {
      projectDistance(pos, garment.seam[c], garment.seam[c + 1], 0,
        p.seamStiffness)
    }
    for (let k = 0; k < garment.pinIdx.length; k++) {
      const i = garment.pinIdx[k]
      projectPin(pos, i, garment.pinTarget[3 * k],
        garment.pinTarget[3 * k + 1], garment.pinTarget[3 * k + 2],
        p.pinWeight)
    }
  }
}

function collideAll(sim: SimState): void {
  const { pos, prev, man } = sim
  const { collisionSkin, friction } = SOLVER_PRIOR
  // 双遍扫描：互嵌后交叠带（y∈(crotch−5, 腿顶) 三管共覆盖）内顺序投影
  // 非幂等——一管的推出可能把粒子推入另一管，单遍残差最坏 14.7cm、
  // 双遍全量归零。未来重构碰撞（并行化/单管早退）不得丢掉 sweep 循环
  for (let sweep = 0; sweep < SOLVER_PRIOR.collideSweeps; sweep++) {
    for (let i = 0; i < sim.garment.total; i++) {
      collideOne(pos, prev, i, man, collisionSkin, friction)
    }
  }
}

// 约束-only 预松弛（无重力无惯性）：冷启动把初始摆位压到缝合闭合
function preRelax(sim: SimState, iters: number): void {
  sim.prev.set(sim.pos)
  const savedIters = sim.iterations
  sim.iterations = 1
  for (let k = 0; k < iters; k++) {
    projectConstraints(sim)
    collideAll(sim)
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
        const [px, py, pz] = placePoint(
          part.key, part.side, xy[2 * i], xy[2 * i + 1], xMin, xMax, sim.man)
        pos[i3] = px; pos[i3 + 1] = py; pos[i3 + 2] = pz
      }
    }
  }
}

export function createSim(
  garment: Garment, man: Mannequin, warmFrom?: SimState,
): SimState {
  const pos = new Float32Array(garment.pos)
  const sim: SimState = {
    garment, man, pos,
    prev: new Float32Array(pos),
    vel: new Float32Array(pos.length),
    damping: SOLVER_PRIOR.damping,
    iterations: SOLVER_PRIOR.iterations,
    substeps: SOLVER_PRIOR.substeps,
    stepCount: 0, settledFrames: 0, settled: false, frozen: false,
    avgSpeed: 0, failStreak: 0,
    lastGood: new Float32Array(pos),
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

// 一帧（rAF 调一次）；返回状态供视图决定停走/角标
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
    projectConstraints(sim)
    collideAll(sim)
    for (let i3 = 0; i3 < pos.length; i3 += 3) {
      vel[i3] = (pos[i3] - prev[i3]) / dtSub
      vel[i3 + 1] = (pos[i3 + 1] - prev[i3 + 1]) / dtSub
      vel[i3 + 2] = (pos[i3 + 2] - prev[i3 + 2]) / dtSub
    }
  }

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

// 视图按帧取位置渲染；settled/frozen 后 pos 不再变，直接复用
export function simPositions(sim: SimState): Float32Array {
  return sim.pos
}
