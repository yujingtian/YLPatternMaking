// 引力下垂解算（2026-09-15 重建二期「下垂要符合地球引力」；2026-09-16
// 五期前身自由垂；同日六期「拉直」整圈钉直挂）：主线程轻量 verlet——
// 距离/弯曲约束（mesh.ts 预留的 dist/bend 数组）+ **中缝对**（L/R
// rise|cb 链镜像配对 rest=0——两片共享同一网格，顶点号天然一一对齐）
// + 腰口整圈全向钉悬挂 + 地面碰撞。**自由垂口径（无撑型芯）**：悬挂
// 不用撑型芯撑开（field 传 null）——芯撑出的前凸筒不是真实提着前片的
// 形态；布条自腰口顶缘竖直垂下、下摆过长得地铺地（地面 y≥0 推回 +
// 摩擦）。形态沿革：二~五期 Y-only 腰口自由垂下「布塌成对折门帘」曾
// 是预期形态，2026-09-16 用户报障「前中和后中往里折、要拉直」后由
// 整圈全向钉（三轮，见 buildDrape 头注）取代——中缝保持在前中/后中
// 竖直、顶缘按摆位弧全撑。旧口径「勿去碰撞（腿间塌片）」是整裤包腿
// 成形的要求（决策日志 2026-09-14），勿混。芯/场仍用于初摆位半径与
// 取景包络（buildHangPair / Fitting3DView），只是不进碰撞。摩擦防地
// 面切向滑转；发散兜底恢复好帧。
import type { Garment } from './assemble'
import { CORE_SKIN } from './core'
import type { BodyField } from './placement'
import { DRAPE_PRIOR } from './priors'

export interface DrapeSim {
  pos: Float32Array       // 全粒子当前位置（解算本体；garment.pos 是初摆位）
  prev: Float32Array      // 上一子步位置（verlet）
  vel: Float32Array
  pinIdx: Uint32Array     // 腰口整圈粒子（top_chain 边全量 + 终点角，六期直挂口径）
  pinTarget: Float32Array // 3×pin 目标位（初始摆位处，全向硬钉 = 悬挂支点）
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

// 悬挂支点 = 腰口整圈**全向钉**（2026-09-16 六期「拉直」口径：真实
// 「提着整个腰口」——顶缘按摆位弧撑住、布条自顶缘竖直垂下，中缝不再
// 塌向轴心），无例外。演进（三轮）：
// 一轮（2026-09-15 顶部折角）全向钉把腰口锁成刚性折线——角点急坠
// （侧角 −2.1cm）补钉后顶缘仍是「图案角 + 侧缘陡落」的尖状凸起（用户
// 截图复验仍在）、前中角被锁在均匀映射偏心位（实测 −3.9cm ≈ 17°）与
// 前中缝合拔河出顶中缺口；二轮改 Y-only + 双角锚（单锚实测不收敛：锚
// 不住环向滑移模态）——布自重圆化顶缘、前中缝把顶缘滑到正中闭合，但
// **环向可滑 = 布自重把整圈腰口滑向轴心**：中缝跟着荡离前中/后中（前
// 中缝外伸 16.6→5.7cm）、整幅布塌成对折门帘（2026-09-16 用户报障
// 「前中和后中往里折、要拉直」）；三轮（现行）= 整圈全向钉：摆位侧经
// assemble 腰口弧长重参数化中缝腰角精确落中面（L/R 镜像重合）——一轮
// 拔河的根源是映射偏心而非钉本身，重参数化后「钉与缝同意」按构造成立
// （无需二轮的角点例外，实测缝对 avg/p95 = 0），顶缘全撑 = 直挂。
// 角点口径（边界环重采样：每边含起点采样、不含终点，共享角点
// = 下一条边的首采样）：终点角须并入钉集（不钉则急坠）。
// 前中缝合对 = rise 链（前裆弯，腰口端→裆点）L/R 同号顶点配对——真裤
// 前中缝只到裆点（inseam 是前后片缝，留给后续加后片），fly 连裁款 rise
// 链缺失则跳过缝合（前中敞口属连裁门襟固有形态）；后身（2026-09-16
// 六期）同款 = cb 链（后浪，裆尖→腰口，育克拼入时经 panel.ts 聚合贯通
// 到腰）L/R 同号配对
export function buildDrape(garment: Garment, field: BodyField | null): DrapeSim {
  const pinIdx: number[] = []
  for (const part of garment.parts) {
    const top = part.mesh.runs.find((r) => r.role === 'top_chain')
    if (!top) throw new Error('裁片缺 top_chain（腰口）边——下垂 pin 无支点')
    const loopLen = part.mesh.loop.length
    const last = top.indices[top.indices.length - 1]
    // 整圈全向钉（六期直挂）：前提 = buildHangPair 腰口弧长重参数化把
    // 中缝腰角精确摆在镜像位（L/R 重合在中面）——钉与缝天然同意，无需
    // 旧二轮的角点例外；实测缝对 avg/p95 = 0
    for (const i of top.indices) pinIdx.push(part.offset + i)
    // 终点角（下一条边首采样）：全向锚（防侧角急坠，实测 −2.1cm）
    const nextNb = (last + 1) % loopLen
    if (!top.indices.includes(nextNb)) pinIdx.push(part.offset + nextNb)
  }
  const pinTarget = new Float32Array(3 * pinIdx.length)
  for (let k = 0; k < pinIdx.length; k++) {
    pinTarget[3 * k] = garment.pos[3 * pinIdx[k]]
    pinTarget[3 * k + 1] = garment.pos[3 * pinIdx[k] + 1]
    pinTarget[3 * k + 2] = garment.pos[3 * pinIdx[k] + 2]
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
    seamIdx: new Uint32Array(seamIdx),
    parts: garment.parts.map((p) => ({ offset: p.offset, mesh: p.mesh })),
    field,
    stepCount: 0, settledFrames: 0, settled: false, capped: false,
    frozen: false, avgSpeed: 0, failStreak: 0,
    lastGood: new Float32Array(pos),
  }
}

function projectPins(sim: DrapeSim): void {
  const { pos, pinIdx, pinTarget } = sim
  for (let k = 0; k < pinIdx.length; k++) {
    const i3 = 3 * pinIdx[k]
    pos[i3] = pinTarget[3 * k]
    pos[i3 + 1] = pinTarget[3 * k + 1]
    pos[i3 + 2] = pinTarget[3 * k + 2]
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
