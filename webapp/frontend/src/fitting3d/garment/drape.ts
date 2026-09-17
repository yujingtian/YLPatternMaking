// 引力下垂解算（2026-09-15 重建二期「下垂要符合地球引力」；2026-09-16
// 五期前身自由垂；同日六期「拉直」整圈钉直挂；2026-09-17 八期整裤缝合
// 现行）：主线程轻量 verlet——距离/弯曲约束（mesh.ts 的 dist/bend 数组）
// + **全族缝合对**（seams.ts buildSeamSet：前中 rise/后中 cb 镜像族 +
// 侧缝/内缝跨宿主弧长族 + 四裆尖 tip 补焊，全 rest=0 同一求解）+ 腰口
// 整圈全向钉直挂（四 part 360° 腰圆支点）+ **撑型芯径向碰撞（八期开）**
// + 地面碰撞（y≥0 推回 + 摩擦，安全网）。
// 八期口径（用户拍板）：①整裤包腿必须有碰撞体（2026-09-14 教训的正名
// ——无碰撞裤腿对折塌陷、两腿布面互穿），芯锚纸样围度与人台无关（独立
// 原则），布面碰撞壳 = 场 + CORE_SKIN 恰落纸样围度；②本期不含腰头，
// 腰圆由整圈钉挂撑形、sideHold 刚度带暂代腰头撑圆；③摆位先行——
// buildFullPair 让全部缝对初始间隙 ≈0（或 15cm 内缝常量温和闭拢），
// 动力学只做小松弛，不用旧链 preRelax 收拢战争。collide 场查询按
// sim.yLift 回纸样空间（摆位侧场查询用纸样 y，两处一致）。
// 形态沿革：二~五期 Y-only 腰口自由垂下「布塌成对折门帘」曾是预期
// 形态，2026-09-16 用户报障「前中和后中往里折、要拉直」后由整圈全向钉
// （三轮，见 buildDrape 头注）取代——中缝保持在前中/后中竖直、顶缘按
// 摆位弧全撑。五期「自由垂不用芯碰撞」是单筒口径，随八期整裤退役。
import type { Garment } from './assemble'
import { CORE_SKIN } from './core'
import type { BodyField } from './placement'
import { pointInRings } from './placement'
import { DRAPE_PRIOR, HANG_PRIOR } from './priors'
import { buildSeamSet, type SeamGroup } from './seams'
import { bandBottomChain } from './band'

export interface DrapeSim {
  pos: Float32Array       // 全粒子当前位置（解算本体；garment.pos 是初摆位）
  prev: Float32Array      // 上一子步位置（verlet）
  vel: Float32Array
  pinIdx: Uint32Array     // 腰口整圈粒子（top_chain 边全量 + 终点角，六期直挂口径）
  pinTarget: Float32Array // 3×pin 目标位（初始摆位处，全向硬钉 = 悬挂支点）
  seamIdx: Uint32Array    // 2S 全族缝合对（八期 buildSeamSet：rise/cb 镜像
                          // + side/inseam 弧长 + tip 补焊，全 rest=0 同一求解）
  seamGroups: SeamGroup[] // 分族切片（金标分族统计用）
  yLift: number           // 摆位整体抬升（collide 场查询按此回纸样空间）
  holdIdx: Uint32Array    // 裆尖短时硬钉粒子（crotchHold>0 fallback 旋钮用）
  holdTarget: Float32Array
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
export function buildDrape(
  garment: Garment, field: BodyField | null, yLift = 0,
): DrapeSim {
  const pinIdx: number[] = []
  // 腰头在（九期）：**腰口区全钉**——身片腰口环整圈（「腰部圆形撑开」
  // 全义）+ 带顶/带底两缘（带 = 两缘被持的真实布，中间布自由）；
  // sideHold 退役（带即腰头）。演进：先试只钉带顶（真实「提着腰头上
  // 沿」）——自由垂挂对折趋势把前中/后中往里拖 1.2cm，腰头内倾+布面
  // 内折 = 前后中透光楔形洞（用户报障）；再试加钉带底——缝对与身片
  // 网格 GS 冲突平衡留 ~0.5cm 均匀缝口；全钉后两侧钉位本就重合、缝恒 0。
  // 无腰头 = 旧口径：身片腰口整圈钉 + sideHold 带
  const bandPart = garment.parts.find((p) => p.key === 'waistband')
  for (const part of garment.parts) {
    // 有腰头（九期）：身片腰口环照旧整圈钉（「腰部圆形撑开」的全义
    // ——整个腰口区保持圆；早期只钉带顶时自由垂挂的对折趋势把前中/
    // 后中往里拖 1.2cm、只加钉带底时缝对与身片网格 GS 冲突平衡留
    // ~0.5cm 均匀缝口——两侧钉位本就重合，全钉后缝恒 0）+ 带顶带底
    // 两缘钉（带 = 两缘被持的真实布，中间布自由）；sideHold 退役（带
    // 即腰头）。无腰头 = 旧口径
    const isBand = part === bandPart
    if (isBand) {
      const top = part.mesh.runs.find((r) => r.name === 'top')
      if (top) {
        for (const i of top.indices) pinIdx.push(part.offset + i)
        const loopLen = part.mesh.loop.length
        const last = top.indices[top.indices.length - 1]
        const nextNb = (last + 1) % loopLen
        if (!top.indices.includes(nextNb)) pinIdx.push(part.offset + nextNb)
      }
      const chain = bandBottomChain(part.mesh)
      if (chain) {
        for (const i of chain.indices) {
          if (!pinIdx.includes(part.offset + i)) {
            pinIdx.push(part.offset + i)
          }
        }
      }
      continue
    }
    const top = part.mesh.runs.find((r) => r.role === 'top_chain')
    if (!top) throw new Error('裁片缺 top_chain（腰口）边——下垂 pin 无支点')
    const loopLen = part.mesh.loop.length
    const last = top.indices[top.indices.length - 1]
    // 整圈全向钉（六期直挂）：前提 = buildFullPair 腰口弧长重参数化把
    // 中缝腰角精确摆在镜像位（L/R 重合在中面）——钉与缝天然同意，无需
    // 旧二轮的角点例外；实测缝对 avg/p95 = 0
    for (const i of top.indices) pinIdx.push(part.offset + i)
    // 终点角（下一条边首采样）：全向锚（防侧角急坠，实测 −2.1cm）
    const nextNb = (last + 1) % loopLen
    if (!top.indices.includes(nextNb)) pinIdx.push(part.offset + nextNb)
    // 侧缝边顶部刚度带（无腰头旧口径；有腰头时带即腰头、跳过）：无侧缝
    // 缝合的自由半身筒，侧缝自由边在自由垂中向筒轴心内摆（后身实测最深
    // ~25°）、顶部扇区塌角。顶部 sideHold cm 全向钉 = 腰头缝合线的刚度带
    // （真实成衣此区由腰头撑圆），配 assemble 侧缝边语义摆位（θ=±90°
    // 竖直）后顶部圆弧保持、带缘出口偏差实测 ≤0.7°（往下自由内摆渐增属
    // 自然垂）。run 首采样 = 腰口终点角（已在上方钉集）须去重；后宿主
    // 育克侧段与后片侧缝同为 side 名（可能各自成 run），全部覆盖
    for (const side of bandPart ? [] : part.mesh.runs) {
      if (side.name !== 'side') continue
      for (let k = 0; k < side.indices.length
        && side.arc[k] <= HANG_PRIOR.sideHold; k++) {
        const gi = part.offset + side.indices[k]
        if (!pinIdx.includes(gi)) pinIdx.push(gi)
      }
    }
  }
  const pinTarget = new Float32Array(3 * pinIdx.length)
  for (let k = 0; k < pinIdx.length; k++) {
    pinTarget[3 * k] = garment.pos[3 * pinIdx[k]]
    pinTarget[3 * k + 1] = garment.pos[3 * pinIdx[k] + 1]
    pinTarget[3 * k + 2] = garment.pos[3 * pinIdx[k] + 2]
  }
  // 全族缝合对（八期 buildSeamSet）：六期「parts[0] 单一 rise|cb 链同号
  // 配对」的泛化——rise/cb 镜像族同机制、side/inseam 跨宿主弧长配对、
  // 四裆尖 tip 补焊，全族 rest=0 进同一扁平数组（求解循环零改动）
  const seam = buildSeamSet(garment)
  // 裆尖短时硬钉（crotchHold fallback 旋钮，默认 0 关；先例旧链 60 硬
  // 释放）：tipL/tipR 两对共四顶点钉初始位 crotchHold 帧后硬释放交还缝合
  const holdIdx: number[] = []
  if (DRAPE_PRIOR.crotchHold > 0) {
    for (const g of seam.groups) {
      if (g.name !== 'tipL' && g.name !== 'tipR') continue
      for (let p = 0; p < g.pairCount; p++) {
        holdIdx.push(seam.pairs[2 * (g.pairOffset + p)],
          seam.pairs[2 * (g.pairOffset + p) + 1])
      }
    }
  }
  const holdTarget = new Float32Array(3 * holdIdx.length)
  for (let k = 0; k < holdIdx.length; k++) {
    holdTarget[3 * k] = garment.pos[3 * holdIdx[k]]
    holdTarget[3 * k + 1] = garment.pos[3 * holdIdx[k] + 1]
    holdTarget[3 * k + 2] = garment.pos[3 * holdIdx[k] + 2]
  }
  const pos = new Float32Array(garment.pos)
  return {
    pos,
    prev: new Float32Array(pos),
    vel: new Float32Array(pos.length),
    pinIdx: new Uint32Array(pinIdx),
    pinTarget,
    seamIdx: seam.pairs,
    seamGroups: seam.groups,
    yLift,
    holdIdx: new Uint32Array(holdIdx),
    holdTarget,
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

// 裆尖短时硬钉投影（crotchHold fallback 旋钮，默认 0 不投影）
function projectHold(sim: DrapeSim): void {
  const { pos, holdIdx, holdTarget } = sim
  for (let k = 0; k < holdIdx.length; k++) {
    const i3 = 3 * holdIdx[k]
    pos[i3] = holdTarget[3 * k]
    pos[i3 + 1] = holdTarget[3 * k + 1]
    pos[i3 + 2] = holdTarget[3 * k + 2]
  }
}

// 撑型芯截面碰撞（八期）：y'（pos.y − yLift 回纸样空间）行的截面环内
// 或皮肤壳内（到最近边界 < skin）→ 推到最近边界 + skin·外法线；接触
// 时 prev 向 pos 混合摩擦（无摩擦 = 芯面周向滑转不锚，旧链 0.5 地板
// ~9 永不收敛）。截面多边形口径取代旧径向推——两腿分离芯的腿间空隙
// 径向场表示不了（星形实心），只有截面/表面碰撞能留白（旧链 BVH 同因）；
// 腿管间隙按环独立判内，无 v1「双管交叠符号判陷阱」
function collide(sim: DrapeSim): void {
  const { pos, prev, field } = sim
  if (!field) return
  const fr = DRAPE_PRIOR.friction
  for (let i3 = 0; i3 < pos.length; i3 += 3) {
    const x = pos[i3], z = pos[i3 + 2]
    const rings = field.loopsAt(pos[i3 + 1] - sim.yLift)
    if (rings.length === 0) continue
    // 最近边界（跨全部环，quick reject：质心包围圆 + skin 余量）。
    // 性能口径：Math.hypot 慢一个量级，用 sqrt
    let bd = Infinity, bx = 0, bz = 0, bnx = 0, bnz = 0
    for (const ring of rings) {
      const dxc = x - ring.cx, dzc = z - ring.cz
      const rr = ring.r + CORE_SKIN
      if (dxc * dxc + dzc * dzc > rr * rr) continue
      const n = ring.pts.length / 2
      for (let s = 0; s < n; s++) {
        const a2 = 2 * s, b2 = 2 * ((s + 1) % n)
        const ax = ring.pts[a2], az = ring.pts[a2 + 1]
        const ex = ring.pts[b2] - ax, ez = ring.pts[b2 + 1] - az
        const l2 = ex * ex + ez * ez
        const t = l2 > 1e-12
          ? Math.max(0, Math.min(1, ((x - ax) * ex + (z - az) * ez) / l2)) : 0
        const px = ax + ex * t, pz = az + ez * t
        const dxp = x - px, dzp = z - pz
        const d2 = dxp * dxp + dzp * dzp
        if (d2 < bd * bd) {
          bd = Math.sqrt(d2); bx = px; bz = pz
          // 外法线 = 段垂线，背离环质心
          const len = Math.sqrt(l2) || 1
          let nx = -ez / len, nz = ex / len
          if (nx * (ring.cx - px) + nz * (ring.cz - pz) > 0) {
            nx = -nx; nz = -nz
          }
          bnx = nx; bnz = nz
        }
      }
    }
    if (bd === Infinity) continue
    if (bd >= CORE_SKIN) {
      // 远离边界：只在某环包围圆内（可能深穿）才做射线判内兜底——正常
      // 挂相布在壳外起步，此分支零命中（v1 细龙骨穿膛教训的守门）
      let maybe = false
      for (const ring of rings) {
        const dxc = x - ring.cx, dzc = z - ring.cz
        if (dxc * dxc + dzc * dzc < ring.r * ring.r) { maybe = true; break }
      }
      if (!maybe || !pointInRings(x, z, rings)) continue
    }
    // 统一推出目标 = 最近边界 + skin·外法线：边界外侧近壳粒子与环内
    // 粒子同向处理（内侧粒子若按「边界->粒子」方向推会越推越深自陷）
    const tx = bx + bnx * CORE_SKIN
    const tz = bz + bnz * CORE_SKIN
    pos[i3] = tx
    pos[i3 + 2] = tz
    prev[i3] += (pos[i3] - prev[i3]) * fr
    prev[i3 + 1] += (pos[i3 + 1] - prev[i3 + 1]) * fr
    prev[i3 + 2] += (pos[i3 + 2] - prev[i3 + 2]) * fr
  }
}

// 地面碰撞（hangLift 抬升后的安全网）：y < 0 推回地面；法向速度清零
// （prev.y 同钉）+ 切向摩擦（prev xz 向 pos 混合——无摩擦布在地上持续
// 滑转不锚）。抬升前布全长超挂高、下摆拖地铺地曾是主约束（front 102/
// back 202 粒子贴地实测），抬 12 后正常挂相零接触
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
      // 全族缝合对（八期：rise/cb 镜像 + side/inseam 弧长 + tip 补焊，
      // 跨片 rest=0、刚度 1）：双向各移一半——求解循环对全族一视同仁
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
      // 裆尖短时硬钉（crotchHold 帧后硬释放交还缝合约束；默认 0 关）
      if (sim.stepCount < DRAPE_PRIOR.crotchHold) projectHold(sim)
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

// 全族缝合误差统计（金标用）：全部缝合对点距 avg / P95。读 sim.pos
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

// 分族缝合误差统计（八期金标：rise/cb/sideL/sideR/inseamL/inseamR/tip
// 各族单独 avg/P95——各族几何性质不同，阈值分开钉）
export function seamStatsByGroup(
  sim: DrapeSim,
): Record<string, { avg: number; p95: number }> {
  const out: Record<string, { avg: number; p95: number }> = {}
  for (const g of sim.seamGroups) {
    const ds: number[] = []
    for (let p = 0; p < g.pairCount; p++) {
      const a = 3 * sim.seamIdx[2 * (g.pairOffset + p)]
      const b = 3 * sim.seamIdx[2 * (g.pairOffset + p) + 1]
      ds.push(Math.hypot(sim.pos[b] - sim.pos[a],
        sim.pos[b + 1] - sim.pos[a + 1], sim.pos[b + 2] - sim.pos[a + 2]))
    }
    ds.sort((x, y) => x - y)
    out[g.name] = {
      avg: ds.reduce((s, d) => s + d, 0) / ds.length,
      p95: ds[Math.min(ds.length - 1, Math.floor(ds.length * 0.95))],
    }
  }
  return out
}
