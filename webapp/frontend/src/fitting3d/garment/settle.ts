// 穿台落位控制器（2026-09-18）：真人穿裤行为模型的仿真翻译——「拉到腰
// （人台腰地标锚定）→ 裆顶住就一点点往下 → 前后裆零穿透即停」。
// 力学口径：向上唯一硬止点是裆（浪长不可伸长）、向下的几何卡点是胯
// （2026-09-23 P1 挂胯判据：不可伸长闭环套不进周长 > 环长的截面——真人
// 裤子滑到胯骨滑不动即停 = 该约束的力平衡形态，钉在卡停行冻结 = 支撑
// 反力的运动学等价）→ 最终穿着高度 = min(锚定腰位, 裆零穿透最高位,
// 挂胯卡停行)，前/后独立先到者即终态；向下没有反向力学信号（掉裆
// 是观感读数）→ 单程搜索。前后裆是两根独立探针（前浪顶耻骨/后浪贴尾
// 骨），hF/hB 独立下放 = 俯仰自然涌现；钉 XZ（2026-09-23 P2 前冻结、
// 现沿参考环重投影——环弧 s 直通保持钉位对应，是「全钉保 XZ 刚度防环向
// 滑移」红线的后继口径：形状随行、弧位不游移；无弧位钉照旧冻结）。
// 单次仿真内准静态缓释钉高（用户拍板口径），非外层搜索重跑。停走判据
// 只认 settle 相位全粒子真实静止（下放瞬态 vs 泵的区分红线：穿透清除后
// 速度仍持续 = 泵）；下放中钉速被全粒子 avgSpeed 均值稀释出的假 settled
// 由 wake() 对治。
import type { DrapeSim } from './drape'
import type { Garment } from './assemble'
import { CORE_SKIN } from './core'
import { DRAPE_PRIOR, DRESSING_PRIOR, FIELD_PRIOR } from './priors'
import {
  buildWaistRing, nearestRingBoundary, pointInRings, ringPointAt,
  type RingHit, type WaistRing,
} from './placement'
import { tipAfterInseam } from './seams'

export type SettlePhase = 'hold' | 'lowering' | 'settle' | 'done'

// 裆接触读数：pen=穿透(value cm) / touch=贴合 / gap=间隙(value cm)
export type ContactKind = 'pen' | 'touch' | 'gap'
export interface CrotchContact { kind: ContactKind; value: number }

export interface DressReport {
  dropF: number; dropB: number   // cm：前/后腰低于人台腰地标的量（正=掉裆）
  contactF: CrotchContact
  contactB: CrotchContact
  worstPen: number               // cm：终态全粒子壳穿透最差（0=无）
  worstPenY: number              // 最差点 y（sim 系 = 世界高度，穿台锚定同源）
  tooSmall: boolean              // 偏小信号（裆穿透未解或全身穿透超阈值）
  jamF: boolean; jamB: boolean   // 挂胯卡停（2026-09-23 P1）：环套不进候选
                                 // 行截面停在下放途中（与 fault=预算尽、capped
                                 // =非真实静止三分，各自独立读数）
  capped: boolean                // 非真实静止收束（预算尽/硬顶）
  frames: number
}

export interface SettleOptions {
  /** 探针注入（测试用；缺省 probeCrotch 实测） */
  probe?: (sim: DrapeSim, side: 'front' | 'back') => { worst: number; best: number }
  /** 挂胯判据（2026-09-23 P1）：ringTotal = 钉环总长 C（成衣腰长）、
   * rowY = 环源截面行（纸样系，同 fieldM 坐标系直接喂 loopsAt）；候选档
   * 行周长 ≥ C×(1+jamMargin) → 该侧卡停不下放。缺省不启用 */
  jam?: { ringTotal: number; rowY: number }
  holdFrames?: number; dropRate?: number; deadZone?: number; maxDrop?: number
  confirmFrames?: number; settleMaxFrames?: number; maxTotalFrames?: number
}

export interface SettleController {
  phase: SettlePhase
  hF: number; hB: number            // 前/后腰下放量（≤0，相对锚定位）
  step(sim: DrapeSim): SettlePhase  // 每帧 stepDrape 之后调一次
  report(sim: DrapeSim): DressReport
}

// 裆探针索引：前 = rise 链自裆尖 span 内采样（arc[0]=0 在裆尖，方向见
// mesh.ts 头注）+ inseam 链自脚口端回溯 span（末段 = 裆尖端）+ 裆尖本体
// （rise 缺失的 fly 连裁款兜底 tipAfterInseam，与 seams tip 配对同源）；
// 后同（cb 链）。L part 共享网格取 L 侧全局号——探针只测距离不配对。
// 裆接触是一段不是一个点（会阴贴一段弧）
export function buildCrotchProbeIdx(
  garment: Garment, span = DRESSING_PRIOR.probeSpan,
): { front: number[]; back: number[] } {
  const partOf = (key: string): Garment['parts'][number] | undefined =>
    garment.parts.find((p) => p.key === key && p.side === 'L')
  const collect = (
    part: Garment['parts'][number], seam: 'rise' | 'cb',
  ): number[] => {
    const out = new Set<number>()
    const seamRun = part.mesh.runs.find((r) => r.name === seam)
    if (seamRun) {
      for (let k = 0; k < seamRun.indices.length && seamRun.arc[k] <= span; k++) {
        out.add(part.offset + seamRun.indices[k])
      }
    } else {
      const tip = tipAfterInseam(part.mesh)
      if (tip !== null) out.add(part.offset + tip)
    }
    const inseam = part.mesh.runs.find((r) => r.name === 'inseam')
    if (inseam) {
      for (let k = inseam.indices.length - 1; k >= 0
        && inseam.length - inseam.arc[k] <= span; k--) {
        out.add(part.offset + inseam.indices[k])
      }
    }
    return [...out]
  }
  const f = partOf('front'), b = partOf('back')
  if (!f || !b) throw new Error('穿台探针：Garment 缺 front/back L part')
  return { front: collect(f, 'rise'), back: collect(b, 'cb') }
}

// 裆接触探针（实测口径）：逐探针顶点对场行截面环算带符号接触量——
// v = 环内 ? skin + d : skin − d（d = 到最近边界距离；v=0 恰接触、>0 穿透
// 深度、<0 间隙），与 collide 平衡位同口径（推出到边界+skin 处 v=0）。
// quick reject 余量放大 probeMargin（要量间隙）；全落空 = 净空至少
// probeMargin（钳为 −probeMargin，勿误报穿透）。无场/探针空 = 无信息
// （worst −∞ 不触发下放）
export function probeCrotch(
  sim: DrapeSim, idx: number[],
): { worst: number; best: number } {
  let worst = -Infinity, best = Infinity
  const field = sim.field
  if (!field) return { worst, best }
  const margin = CORE_SKIN + DRESSING_PRIOR.probeMargin
  // scratch 出参（1b 提速）：逐探针命中复用（d 立即消费，安全）
  const hit: RingHit = { d: 0, px: 0, pz: 0, nx: 0, nz: 0 }
  for (const gi of idx) {
    const i3 = 3 * gi
    const x = sim.pos[i3], y = sim.pos[i3 + 1], z = sim.pos[i3 + 2]
    const rings = field.loopsAt(y - sim.yLift)
    if (rings.length === 0) continue
    const got = nearestRingBoundary(rings, x, z, margin, hit)
    const v = !got ? -DRESSING_PRIOR.probeMargin
      : pointInRings(x, z, rings) ? CORE_SKIN + hit.d : CORE_SKIN - hit.d
    if (v > worst) worst = v
    if (v < best) best = v
  }
  return { worst, best }
}

export function buildSettle(
  sim: DrapeSim, probeIdx: { front: number[]; back: number[] },
  opts: SettleOptions = {},
): SettleController {
  const {
    probe, jam,
    holdFrames = DRESSING_PRIOR.holdFrames,
    dropRate = DRESSING_PRIOR.dropRate,
    deadZone = DRESSING_PRIOR.deadZone,
    maxDrop = DRESSING_PRIOR.maxDrop,
    confirmFrames = DRESSING_PRIOR.confirmFrames,
    settleMaxFrames = DRESSING_PRIOR.settleMaxFrames,
    maxTotalFrames = DRESSING_PRIOR.maxTotalFrames,
  } = opts
  // frontness + 钉基线（build 时一次性快照）：f = |atan2(x,z)|/π——
  // 0=前中(θ=0,+Z) → 0.5=侧(±90°) → 1=后中(±180°)；身片腰环/带顶带底
  // 环/终点角全部在同一腰圆上，位置即方位，统一成立
  const nPin = sim.pinIdx.length
  const fArr = new Float32Array(nPin)
  const baseY = new Float32Array(nPin)
  for (let k = 0; k < nPin; k++) {
    fArr[k] = Math.abs(
      Math.atan2(sim.pinTarget[3 * k], sim.pinTarget[3 * k + 2])) / Math.PI
    baseY[k] = sim.pinTarget[3 * k + 1]
  }
  const state = {
    phase: 'hold' as SettlePhase,
    hF: 0, hB: 0,
    frames: 0,
    confirm: 0,
    faultF: false, faultB: false,
    jamF: false, jamB: false,
    settleStart: 0,
    capped: false,
  }
  // 挂胯判据（P1）：候选档行周长 ≥ 环长×(1+jamMargin) → 卡停。未配 jam /
  // 无场 / 空行（周长 0）恒 false 不拦（安全缺省——无 pen 侧本就不评估）
  const jammed = (h2: number): boolean => !!jam && !!sim.field
    && sim.field.rowPerimeter(jam.rowY + h2)
      >= jam.ringTotal * (1 + DRESSING_PRIOR.jamMargin)
  // 假 settled 对策（红线：下放瞬态 vs 泵——停走只认 settle 相位真实
  // 静止）：动钉/进 settle 时清 settled 并续帧预算
  const wake = (s: DrapeSim): void => {
    s.settled = false
    s.settledFrames = 0
    s.capped = false
    s.maxFrames = Math.max(s.maxFrames, s.stepCount + settleMaxFrames)
  }
  // 钉目标下放写回（2026-09-23 P2 钉环随行重投影）：Y 照旧
  // y = baseY + lerp(hF, hB, f)；XZ 不再冻结——有弧位的钉沿参考环重投影：
  // 参考环 = buildWaistRing(field, 该钉参考行, C)（C = jam.ringTotal 恒定
  // → s 直通 ringPointAt(ref, s)，弧位对应稳定防钉游移）。参考行 = 钉自身
  // 当前目标行（纸样系 yPat = yT − yLift），**下钳到腰站行 + 同 lerp 下放量**
  // （对照数字证伪裸逐钉行：腰口是斜切身体的整圈闭曲线——前中下垂 ~1.1cm，
  // 逐钉水平行环在前中把钉挤进 P(y_pat)−C 达 0.67cm 的截面，斜切真量只
  // ~0.15；钳下限 = 腰口整圈按腰站环走 XZ、高于腰站行的钉〔带顶〕随自身
  // 行 = 形随体长随衣。连续性：钳位边界 max() 连续）。按 rowStep 档缓存 +
  // 档间线性插值（dropRate 0.08 → 每 ~6 帧换档，准静态无下放瞬态）。
  // 重投影语义：环长恒 C、形状随行——浅掉裆贴身；行周长 > C 的深行
  // δ<0 均匀嵌体 = 诚实读数（偏小不顶开红线不动）。多环/空行档
  // （loopsAt length !== 1）不重建 → 双档皆无环的钉保持当前 XZ（防御性
  // 兜底；P1 封顶后深行到不了）。激活门槛 sim.pinArcs && jam（旁挂/旧
  // 用例零改动）
  const arcs = sim.pinArcs ?? null
  const C = jam ? jam.ringTotal : 0
  const ringCache = new Map<number, WaistRing | null>()
  const ringAt = (notch: number): WaistRing | null => {
    const hit = ringCache.get(notch)
    if (hit !== undefined) return hit
    let ring: WaistRing | null = null
    if (sim.field) {
      const y = sim.field.yMin + notch * FIELD_PRIOR.rowStep
      if (sim.field.loopsAt(y).length === 1) {
        try { ring = buildWaistRing(sim.field, y, C) } catch { ring = null }
      }
    }
    ringCache.set(notch, ring)
    return ring
  }
  const ringPointAt0 = (
    ring: WaistRing | null, s: number,
  ): { x: number; z: number } | null =>
    ring !== null ? ringPointAt(ring, s) : null
  const applyDrop = (): void => {
    for (let k = 0; k < nPin; k++) {
      const yDrop = state.hF * (1 - fArr[k]) + state.hB * fArr[k]
      const yT = baseY[k] + yDrop
      sim.pinTarget[3 * k + 1] = yT
      if (arcs === null || jam === undefined || Number.isNaN(arcs[k])) continue
      // 参考行下钳：腰口整圈按腰站环走 XZ（斜切闭曲线的正确几何），
      // 高于腰站行的钉（带顶）随自身行（形随体长随衣）
      const yRef = Math.max(
        yT - sim.yLift,
        jam.rowY + yDrop,
      )
      const t = (yRef - (sim.field?.yMin ?? 0)) / FIELD_PRIOR.rowStep
      const n0 = Math.floor(t), fr = t - n0
      const p0 = ringPointAt0(ringAt(n0), arcs[k])
      const p1 = fr > 0 ? ringPointAt0(ringAt(n0 + 1), arcs[k]) : null
      if (p0 !== null && p1 !== null) {
        sim.pinTarget[3 * k] = p0.x + (p1.x - p0.x) * fr
        sim.pinTarget[3 * k + 2] = p0.z + (p1.z - p0.z) * fr
      } else if (p0 !== null) {
        sim.pinTarget[3 * k] = p0.x
        sim.pinTarget[3 * k + 2] = p0.z
      } else if (p1 !== null) {
        sim.pinTarget[3 * k] = p1.x
        sim.pinTarget[3 * k + 2] = p1.z
      }
    }
  }
  const measure = (side: 'front' | 'back'): { worst: number; best: number } =>
    probe ? probe(sim, side) : probeCrotch(sim, probeIdx[side])
  return {
    get phase() { return state.phase },
    get hF() { return state.hF },
    get hB() { return state.hB },
    step(s: DrapeSim): SettlePhase {
      if (state.phase === 'done') return state.phase
      state.frames++
      if (s.frozen) {           // 发散冻结：保终态直接出报告
        state.phase = 'done'; state.capped = true
        return state.phase
      }
      if (state.frames >= maxTotalFrames) {   // 控制器硬顶兜底
        state.phase = 'done'; state.capped = true
        return state.phase
      }
      if (state.phase === 'hold') {
        // 不动钉持锚松弛（启动序列红线：先让布静止再动钉）。提前转
        // （2026-09-23 提速 1c）：布已达全局唯一静止判据（settledFrames 与
        // settle 相位同源——settleSpeed/settleFrames 一套常数零新常数）即转
        // lowering，holdFrames 退居上限；「静止」定义三相位一致
        if (state.frames >= holdFrames
          || s.settledFrames >= DRAPE_PRIOR.settleFrames) state.phase = 'lowering'
        return state.phase
      }
      if (state.phase === 'lowering') {
        const pF = measure('front'), pB = measure('back')
        let changed = false
        // 单侧下放：穿透超死区且未到底 → 降 dropRate；候选档挂胯（环套不
        // 进该行截面）→ jam 卡停不下放（不动钉无需 wake）；到底仍穿 =
        // fault 停放（偏小读数路径，不与碰撞无限拔河——jam 未拦 = 行周长
        // 可容，fault 路径不受 jam 影响）；入区 → 待确认。h′=0 即 jam
        // （腰围偏小款 pen 驱动第一档就拦）= 合法终态 drop=0
        const penF = pF.worst > deadZone, penB = pB.worst > deadZone
        if (penF && !state.faultF) {
          if (state.hF > -maxDrop) {
            const h2 = Math.max(-maxDrop, state.hF - dropRate)
            if (jammed(h2)) state.jamF = true
            else { state.hF = h2; changed = true }
          } else state.faultF = true
        }
        if (penB && !state.faultB) {
          if (state.hB > -maxDrop) {
            const h2 = Math.max(-maxDrop, state.hB - dropRate)
            if (jammed(h2)) state.jamB = true
            else { state.hB = h2; changed = true }
          } else state.faultB = true
        }
        // 双侧完成（入区、fault 或 jam）连续 confirmFrames → settle（钉冻结）
        const doneF = !penF || state.faultF || state.jamF
        const doneB = !penB || state.faultB || state.jamB
        state.confirm = doneF && doneB ? state.confirm + 1 : 0
        if (changed) { applyDrop(); wake(s) }
        if (state.confirm >= confirmFrames) {
          state.phase = 'settle'
          state.settleStart = state.frames
          wake(s)   // 强制重测真实静止（含预算续期）
        }
        return state.phase
      }
      // settle：钉冻结纯跑；真实静止或相位预算尽 → done
      if (s.settled) {
        state.phase = 'done'
        state.capped = s.capped
        return state.phase
      }
      if (state.frames - state.settleStart >= settleMaxFrames) {
        state.phase = 'done'; state.capped = true
      }
      return state.phase
    },
    report(s: DrapeSim): DressReport {
      const pF = measure('front'), pB = measure('back')
      const contactOf = (p: { worst: number; best: number }): CrotchContact => {
        if (p.worst > deadZone) return { kind: 'pen', value: p.worst }
        if (p.best < -deadZone) {
          // 间隙（无信息的 −∞ 钳到 margin 上限）
          const gap = Number.isFinite(p.best) ? -p.best : DRESSING_PRIOR.probeMargin
          return { kind: 'gap', value: gap }
        }
        return { kind: 'touch', value: Math.abs(p.worst) }
      }
      // 终态全粒子壳穿透扫（report 期一次性，成本同 seamStats 量级）
      let worst = 0, worstY = 0
      if (s.field) {
        // scratch 出参（1b 提速）：d 即读即用
        const hit: RingHit = { d: 0, px: 0, pz: 0, nx: 0, nz: 0 }
        for (let i3 = 0; i3 < s.pos.length; i3 += 3) {
          const x = s.pos[i3], y = s.pos[i3 + 1], z = s.pos[i3 + 2]
          const rings = s.field.loopsAt(y - s.yLift)
          if (rings.length === 0) continue
          if (!nearestRingBoundary(rings, x, z, CORE_SKIN, hit)) continue
          const v = pointInRings(x, z, rings)
            ? CORE_SKIN + hit.d : CORE_SKIN - hit.d
          if (v > worst) { worst = v; worstY = y }
        }
      }
      const contactF = contactOf(pF), contactB = contactOf(pB)
      return {
        dropF: -state.hF, dropB: -state.hB,
        contactF, contactB,
        worstPen: worst, worstPenY: worstY,
        tooSmall: contactF.kind === 'pen' || contactB.kind === 'pen'
          || worst > DRESSING_PRIOR.tooSmallPen,
        jamF: state.jamF, jamB: state.jamB,
        capped: state.capped,
        frames: state.frames,
      }
    },
  }
}
