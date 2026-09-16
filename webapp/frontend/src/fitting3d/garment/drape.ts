// 引力下垂解算（2026-09-15 重建二期「下垂要符合地球引力」；2026-09-16
// 五期前身自由垂）：主线程轻量 verlet——距离/弯曲约束（mesh.ts 预留的
// dist/bend 数组）+ **前中缝合对**（L/R rise 链镜像配对 rest=0——两片
// 共享同一网格，顶点号天然一一对齐）+ 腰口 pinY 悬挂 + 地面碰撞。
// **自由垂口径（2026-09-16 用户口径「如果拿着前片上部不可能是这个
// 造型」+「裆尖缝合交点要往内拉、在裆下」）**：前身悬挂不再用撑型芯
// 撑开（field 传 null）——芯撑出的前凸筒不是真实提着前片的形态；无撑
// 自由垂下前中缝竖直下垂、前浪凹弧（布不可拉伸）自然把裆尖内收到
// 裆下，布沿缝两侧垂落、下摆过长得地铺地（地面 y≥0 推回 + 摩擦）。
// 旧口径「勿去碰撞（腿间塌片）」是整裤包腿成形的要求（决策日志
// 2026-09-14），前身半身布垂成对折门帘正是预期形态，勿混。芯/场仍
// 用于初摆位半径与取景包络（buildFrontPair / Fitting3DView），只是
// 不进碰撞。摩擦防地面切向滑转；发散兜底恢复好帧。
import type { Garment } from './assemble'
import { CORE_SKIN } from './core'
import type { BodyField } from './placement'
import { DRAPE_PRIOR } from './priors'

export interface DrapeSim {
  pos: Float32Array       // 全粒子当前位置（解算本体；garment.pos 是初摆位）
  prev: Float32Array      // 上一子步位置（verlet）
  vel: Float32Array
  pinIdx: Uint32Array     // 腰口粒子（top_chain 边 + 两端非缝合角点）
  pinTarget: Float32Array // 3×pin 目标位（初始摆位处，全向硬钉 = 悬挂支点）
  pinYIdx: Uint32Array    // 只钉 Y 的角点（缝合链端点——全向钉会与缝合对拔河）
  pinYTarget: Float32Array // 与 pinYIdx 对齐（仅 y 分量）
  seamIdx: Uint32Array    // 2S 中缝粒子对（L/R rise|cb 链同号顶点，rest=0）
  parts: { offset: number; mesh: Garment['parts'][number]['mesh'] }[]
  field: BodyField | null   // null = 自由垂（无撑型芯径向碰撞，仅地面）
  stepCount: number
  settledFrames: number
  settled: boolean
  capped: boolean         // maxFrames 封顶出的 settled（非真静止）
  frozen: boolean         // 发散兜底冻结（显示保终态）
  avgSpeed: number
  failStreak: number
  lastGood: Float32Array
}

// 悬挂支点 = 腰口整圈**只钉 Y**（高度恒守、环向/径向可滑）+ **双角全向
// 锚**（L/R 侧角各一）。演进（2026-09-15 顶部折角两轮）：
// 一轮全向钉把腰口锁成刚性折线——角点急坠（侧角 −2.1cm）补钉后顶缘
// 仍是「图案角 + 侧缘陡落」的尖状凸起（用户截图复验）、前中角被锁在
// 均匀映射偏心位与前中缝合拔河出顶中缺口；二轮改 Y-only：布自重自然
// 圆化顶缘、前中缝合把顶缘滑到正中闭合。**单锚不收敛实测**（600 帧封
// 顶：单点锚不住环向滑移模态、无锚半边持续蠕动）——双角锚各定住半边
// 的刚体滑移，顶缘中段仍可滑可曲。角点口径（边界环重采样：每边含起
// 点采样、不含终点，共享角点 = 下一条边的首采样）：终点角须并入 Y 钉
// 集（不钉则急坠）。
// 前中缝合对 = rise 链（前裆弯，腰口端→裆点）L/R 同号顶点配对——真裤
// 前中缝只到裆点（inseam 是前后片缝，留给后续加后片），fly 连裁款 rise
// 链缺失则跳过缝合（前中敞口属连裁门襟固有形态）；后身（2026-09-16
// 六期）同款 = cb 链（后浪，裆尖→腰口，育克拼入时经 panel.ts 聚合贯通
// 到腰）L/R 同号配对
export function buildDrape(garment: Garment, field: BodyField | null): DrapeSim {
  const pinIdx: number[] = []
  const pinYIdx: number[] = []
  for (const part of garment.parts) {
    const top = part.mesh.runs.find((r) => r.role === 'top_chain')
    if (!top) throw new Error('裁片缺 top_chain（腰口）边——下垂 pin 无支点')
    const loopLen = part.mesh.loop.length
    const last = top.indices[top.indices.length - 1]
    for (const i of top.indices) pinYIdx.push(part.offset + i)
    // 终点角（下一条边首采样）：全向锚（防半边环向蠕动）+ 并入 Y 集
    const nextNb = (last + 1) % loopLen
    if (!top.indices.includes(nextNb)) {
      pinYIdx.push(part.offset + nextNb)
      pinIdx.push(part.offset + nextNb)
    }
  }
  const pinTarget = new Float32Array(3 * pinIdx.length)
  for (let k = 0; k < pinIdx.length; k++) {
    pinTarget[3 * k] = garment.pos[3 * pinIdx[k]]
    pinTarget[3 * k + 1] = garment.pos[3 * pinIdx[k] + 1]
    pinTarget[3 * k + 2] = garment.pos[3 * pinIdx[k] + 2]
  }
  const pinYTarget = new Float32Array(pinYIdx.length)
  for (let k = 0; k < pinYIdx.length; k++) {
    pinYTarget[k] = garment.pos[3 * pinYIdx[k] + 1]
  }
  // 中缝对（前中 rise / 后中 cb）：L/R 共享网格，同号顶点 (0+i, n+i) 镜像对
  const seamIdx: number[] = []
  if (garment.parts.length >= 2) {
    const seamRun = garment.parts[0].mesh.runs.find(
      (r) => r.name === 'rise' || r.name === 'cb')
    if (seamRun) {
      const [pl, pr] = garment.parts
      for (const i of seamRun.indices) {
        seamIdx.push(pl.offset + i, pr.offset + i)
      }
    }
  }
  const pos = new Float32Array(garment.pos)
  return {
    pos,
    prev: new Float32Array(pos),
    vel: new Float32Array(pos.length),
    pinIdx: new Uint32Array(pinIdx),
    pinTarget,
    pinYIdx: new Uint32Array(pinYIdx),
    pinYTarget,
    seamIdx: new Uint32Array(seamIdx),
    parts: garment.parts.map((p) => ({ offset: p.offset, mesh: p.mesh })),
    field,
    stepCount: 0, settledFrames: 0, settled: false, capped: false,
    frozen: false, avgSpeed: 0, failStreak: 0,
    lastGood: new Float32Array(pos),
  }
}

function projectPins(sim: DrapeSim): void {
  const { pos, pinIdx, pinTarget, pinYIdx, pinYTarget } = sim
  for (let k = 0; k < pinIdx.length; k++) {
    const i3 = 3 * pinIdx[k]
    pos[i3] = pinTarget[3 * k]
    pos[i3 + 1] = pinTarget[3 * k + 1]
    pos[i3 + 2] = pinTarget[3 * k + 2]
  }
  // Y-only 钉（前中角）：只锁高度
  for (let k = 0; k < pinYIdx.length; k++) {
    pos[3 * pinYIdx[k] + 1] = pinYTarget[k]
  }
}

// 撑型芯径向场碰撞（自由垂口径下不调用——field null）：r < 场(y,θ)+skin
// 则径向推出；接触时 prev 向 pos 混合摩擦（无摩擦 = 芯面周向滑转不锚，
// 旧链 0.5 地板 ~9 永不收敛）
function collide(sim: DrapeSim): void {
  const { pos, prev, field } = sim
  if (!field) return
  const fr = DRAPE_PRIOR.friction
  for (let i3 = 0; i3 < pos.length; i3 += 3) {
    const x = pos[i3], y = pos[i3 + 1], z = pos[i3 + 2]
    const r = Math.hypot(x, z)
    if (r < 1e-9) continue
    const s = field.radiusAt(y, Math.atan2(x, z)) + CORE_SKIN
    if (r < s) {
      const k = s / r
      pos[i3] = x * k
      pos[i3 + 2] = z * k
      prev[i3] += (pos[i3] - prev[i3]) * fr
      prev[i3 + 1] += (pos[i3 + 1] - prev[i3 + 1]) * fr
      prev[i3 + 2] += (pos[i3 + 2] - prev[i3 + 2]) * fr
    }
  }
}

// 地面碰撞（自由垂主约束）：y < 0 推回地面；法向速度清零（prev.y 同钉）
// + 切向摩擦（prev xz 向 pos 混合——无摩擦布在地上持续滑转不锚）。
// 悬挂高 = 纸样腰高，布全长超过它则下摆拖地铺地（真实提着前片的形态）
function collideGround(sim: DrapeSim): void {
  const { pos, prev } = sim
  const fr = DRAPE_PRIOR.friction
  for (let i3 = 0; i3 < pos.length; i3 += 3) {
    if (pos[i3 + 1] < 0) {
      pos[i3 + 1] = 0
      prev[i3 + 1] = 0
      prev[i3] += (pos[i3] - prev[i3]) * fr
      prev[i3 + 2] += (pos[i3 + 2] - prev[i3 + 2]) * fr
    }
  }
}

// 一帧（60Hz 调一次）；返回状态供停走判断
export function stepDrape(sim: DrapeSim): 'running' | 'settled' | 'frozen' {
  if (sim.settled || sim.frozen) {
    return sim.frozen ? 'frozen' : 'settled'
  }
  const p = DRAPE_PRIOR
  const dtSub = p.dt / p.substeps
  sim.lastGood.set(sim.pos)
  for (let sub = 0; sub < p.substeps; sub++) {
    const { pos, prev, vel } = sim
    for (let i3 = 0; i3 < pos.length; i3 += 3) {
      vel[i3] *= p.damping
      vel[i3 + 1] = vel[i3 + 1] * p.damping + p.gravity * dtSub
      vel[i3 + 2] *= p.damping
      prev[i3] = pos[i3]; prev[i3 + 1] = pos[i3 + 1]; prev[i3 + 2] = pos[i3 + 2]
      pos[i3] += vel[i3] * dtSub
      pos[i3 + 1] += vel[i3 + 1] * dtSub
      pos[i3 + 2] += vel[i3 + 2] * dtSub
    }
    for (let it = 0; it < p.iterations; it++) {
      for (const part of sim.parts) {
        const { dist, bend } = part.mesh
        const off = part.offset
        // 距离约束（拉伸+剪切，刚度 1）：双向各移一半
        for (let c = 0; c < dist.length; c += 3) {
          const a = 3 * (off + dist[c]), b = 3 * (off + dist[c + 1])
          const dx = pos[b] - pos[a], dy = pos[b + 1] - pos[a + 1]
          const dz = pos[b + 2] - pos[a + 2]
          const d = Math.hypot(dx, dy, dz)
          if (d < 1e-9) continue
          const k = ((d - dist[c + 2]) / d) * 0.5
          pos[a] += dx * k; pos[a + 1] += dy * k; pos[a + 2] += dz * k
          pos[b] -= dx * k; pos[b + 1] -= dy * k; pos[b + 2] -= dz * k
        }
        // 弯曲约束（内边对点，刚度 0.3）
        for (let c = 0; c < bend.length; c += 3) {
          const a = 3 * (off + bend[c]), b = 3 * (off + bend[c + 1])
          const dx = pos[b] - pos[a], dy = pos[b + 1] - pos[a + 1]
          const dz = pos[b + 2] - pos[a + 2]
          const d = Math.hypot(dx, dy, dz)
          if (d < 1e-9) continue
          const k = ((d - bend[c + 2]) / d) * 0.5 * p.bendStiffness
          pos[a] += dx * k; pos[a + 1] += dy * k; pos[a + 2] += dz * k
          pos[b] -= dx * k; pos[b + 1] -= dy * k; pos[b + 2] -= dz * k
        }
      }
      // 中缝对（前中 rise/后中 cb，跨片，rest=0、刚度 1）：双向各移一半
      const { seamIdx } = sim
      for (let c = 0; c < seamIdx.length; c += 2) {
        const a = 3 * seamIdx[c], b = 3 * seamIdx[c + 1]
        const dx = pos[b] - pos[a], dy = pos[b + 1] - pos[a + 1]
        const dz = pos[b + 2] - pos[a + 2]
        const d = Math.hypot(dx, dy, dz)
        if (d < 1e-9) continue
        // rest = 0：k = ((d − 0)/d) × 0.5 × 刚度 = 0.5 × 刚度
        const k = 0.5 * p.seamStiffness
        pos[a] += dx * k; pos[a + 1] += dy * k; pos[a + 2] += dz * k
        pos[b] -= dx * k; pos[b + 1] -= dy * k; pos[b + 2] -= dz * k
      }
      projectPins(sim)
    }
    collide(sim)
    collideGround(sim)
    for (let i3 = 0; i3 < pos.length; i3 += 3) {
      vel[i3] = (pos[i3] - prev[i3]) / dtSub
      vel[i3 + 1] = (pos[i3 + 1] - prev[i3 + 1]) / dtSub
      vel[i3 + 2] = (pos[i3 + 2] - prev[i3 + 2]) / dtSub
    }
  }

  // 发散检测（NaN/飞点）：恢复好帧、清速度重试，连败冻结保终态
  let bad = false
  let speedSum = 0
  const { pos, vel } = sim
  for (let i3 = 0; i3 < pos.length; i3 += 3) {
    if (!Number.isFinite(pos[i3]) || Math.abs(pos[i3 + 1]) > 1e4) {
      bad = true; break
    }
    speedSum += Math.abs(vel[i3]) + Math.abs(vel[i3 + 1]) + Math.abs(vel[i3 + 2])
  }
  if (bad) {
    sim.pos.set(sim.lastGood)
    sim.vel.fill(0)
    sim.prev.set(sim.pos)
    sim.failStreak += 1
    if (sim.failStreak >= 3) sim.frozen = true
    return sim.frozen ? 'frozen' : 'running'
  }
  sim.failStreak = 0
  sim.stepCount += 1
  sim.avgSpeed = speedSum / (sim.pos.length / 3)
  sim.settledFrames = sim.avgSpeed < p.settleSpeed
    ? sim.settledFrames + 1 : 0
  // 帧数封顶兜底：超限取当前帧出 settled（防极限环卡死显示）
  if (sim.stepCount >= p.maxFrames) {
    sim.settled = true
    sim.capped = true
  } else if (sim.settledFrames >= p.settleFrames) {
    sim.settled = true
  }
  return sim.settled ? 'settled' : 'running'
}

// 中缝（前中 rise/后中 cb）缝合误差统计（金标用）：全部缝合对点距 avg / P95。读 sim.pos
// 当前解算位——garment.pos 是初始摆位，别解构它
export function seamStats(sim: DrapeSim): { avg: number; p95: number } {
  const { pos, seamIdx } = sim
  const ds: number[] = []
  for (let c = 0; c < seamIdx.length; c += 2) {
    const a = 3 * seamIdx[c], b = 3 * seamIdx[c + 1]
    ds.push(Math.hypot(pos[b] - pos[a], pos[b + 1] - pos[a + 1],
      pos[b + 2] - pos[a + 2]))
  }
  if (ds.length === 0) return { avg: -1, p95: -1 }
  ds.sort((x, y) => x - y)
  const avg = ds.reduce((s, d) => s + d, 0) / ds.length
  const p95 = ds[Math.min(ds.length - 1, Math.floor(ds.length * 0.95))]
  return { avg, p95 }
}
