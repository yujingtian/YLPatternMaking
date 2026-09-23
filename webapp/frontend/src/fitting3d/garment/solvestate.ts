// 穿台解算状态序列化/再水化（2026-09-23 Worker 化）：DrapeSim 主线程构建
// → toSolveState 投影为 structuredClone/transfer 可过对象 → worker 侧
// fromSolveState 再水化。两处不可克隆体的处理口径：
// · field: BodyField（class + 惰性缓存 perimCache/分箱 WeakMap）→ 传构造
//   参数六元组（slices 的 SliceRing 本就是 plain {pts,cx,cz,r}），worker 侧
//   new BodyField(...)；缓存惰性重建，确定性同输入同输出（分箱 slack/入箱
//   角只依赖 pts，perim 只依赖 pts）
// · parts[].mesh: ClothMesh 含 locate 闭包 → 收窄 SolverPartMesh
//   {dist,bend,bendKArr?}——求解器只读这三样（drape.ts 消费点核实；bendKArr
//   由主线程 buildDrape 的 stampStiffBands 在构建期盖好章随行）。L/R part
//   共享同一 ClothMesh（drape.test 口径）→ 投影后两 part 引用同一组数组，
//   transfer 清单须去重
// ctrl 不序列化——闭包快照（fArr/baseY/ringCache）读 sim.pinIdx/pinTarget，
// worker 侧 buildSettle 重建即自洽。probeIdx/jam 本就 plain 随 init 透传。
// 确定性红线在序列化层的验证：solvestate.test 双宿主锁步位级相等。
import type { DrapeSim } from './drape'
import { BodyField, type SliceRing } from './placement'
import type { SettleOptions } from './settle'

// 求解器消费的网格子集（drape.ts 唯三读取：dist/bend/bendKArr）
export interface SolverMesh {
  dist: Float32Array
  bend: Float32Array
  bendKArr?: Float32Array
}

// 可克隆场态（BodyField 构造参数）
export interface FieldState {
  table: Float32Array
  rows: number
  rowStep: number
  thetaBins: number
  slices: SliceRing[][]
  yMin: number
}

// 可克隆 sim 态（DrapeSim 逐字段投影；typed array 原引用共享——post 时
// transfer 零拷贝，主线程 post 后不得再碰 sim）
export interface SolveState {
  pos: Float32Array
  prev: Float32Array
  vel: Float32Array
  pinIdx: Uint32Array
  pinTarget: Float32Array
  pinFlag: Uint8Array
  pinArcs?: Float64Array
  seamIdx: Uint32Array
  seamGroups: { name: string; pairOffset: number; pairCount: number }[]
  yLift: number
  holdIdx: Uint32Array
  holdTarget: Float32Array
  parts: { offset: number; mesh: SolverMesh }[]
  field: FieldState | null
  collideAboveY: number
  maxFrames: number
  stepCount: number
  settledFrames: number
  settled: boolean
  capped: boolean
  frozen: boolean
  avgSpeed: number
  failStreak: number
  lastGood: Float32Array
}

export interface CrotchProbeIdx {
  front: number[]
  back: number[]
}

/** worker init 消息体（probeIdx/jam/heatOn 随行）。type 字面量必带——
 * worker 端按 msg.type 分发（dressWorker.ts WorkerIn），漏了 type 消息
 * 会被送达后静默丢弃（2026-09-23 实测「炸开的裤子不会变化」根因；DOM
 * Worker.postMessage 是 any 口径拦不住，契约自守） */
export interface DressInit {
  type: 'init'
  state: SolveState
  probeIdx: CrotchProbeIdx
  jam: NonNullable<SettleOptions['jam']>
  heatOn: boolean
}

/** sim → 可克隆投影（mesh 收窄去 locate；field 展平构造参数） */
export function toSolveState(
  sim: DrapeSim, probeIdx: CrotchProbeIdx,
  jam: NonNullable<SettleOptions['jam']>, heatOn: boolean,
): DressInit {
  const f = sim.field
  const field: FieldState | null = f === null ? null : {
    table: f.table, rows: f.rows, rowStep: f.rowStep,
    thetaBins: f.thetaBins, slices: f.slices, yMin: f.yMin,
  }
  return {
    type: 'init',
    state: {
      pos: sim.pos, prev: sim.prev, vel: sim.vel,
      pinIdx: sim.pinIdx, pinTarget: sim.pinTarget, pinFlag: sim.pinFlag,
      pinArcs: sim.pinArcs,
      seamIdx: sim.seamIdx, seamGroups: sim.seamGroups,
      yLift: sim.yLift, holdIdx: sim.holdIdx, holdTarget: sim.holdTarget,
      parts: sim.parts.map((p) => ({
        offset: p.offset,
        mesh: {
          dist: p.mesh.dist, bend: p.mesh.bend, bendKArr: p.mesh.bendKArr,
        },
      })),
      field,
      collideAboveY: sim.collideAboveY, maxFrames: sim.maxFrames,
      stepCount: sim.stepCount, settledFrames: sim.settledFrames,
      settled: sim.settled, capped: sim.capped, frozen: sim.frozen,
      avgSpeed: sim.avgSpeed, failStreak: sim.failStreak,
      lastGood: sim.lastGood,
    },
    probeIdx, jam, heatOn,
  }
}

/** 可克隆投影 → sim（worker 侧；field 重建 BodyField，缓存惰性再生） */
export function fromSolveState(state: SolveState): DrapeSim {
  const f = state.field
  const field: BodyField | null = f === null ? null
    : new BodyField(f.table, f.rows, f.rowStep, f.thetaBins, f.slices, f.yMin)
  return {
    pos: state.pos, prev: state.prev, vel: state.vel,
    pinIdx: state.pinIdx, pinTarget: state.pinTarget, pinFlag: state.pinFlag,
    pinArcs: state.pinArcs,
    seamIdx: state.seamIdx, seamGroups: state.seamGroups,
    yLift: state.yLift, holdIdx: state.holdIdx, holdTarget: state.holdTarget,
    parts: state.parts,
    field,
    collideAboveY: state.collideAboveY, maxFrames: state.maxFrames,
    stepCount: state.stepCount, settledFrames: state.settledFrames,
    settled: state.settled, capped: state.capped, frozen: state.frozen,
    avgSpeed: state.avgSpeed, failStreak: state.failStreak,
    lastGood: state.lastGood,
  }
}

/** post init 的 transfer 清单（零拷贝；L/R 共享 mesh 数组 → Set 去重防
 * DataCloneError；漏登的 buffer 走克隆不炸、只是多一次拷贝） */
export function transferBuffers(init: DressInit): ArrayBuffer[] {
  const seen = new Set<ArrayBuffer>()
  const add = (a: ArrayBufferView | undefined): void => {
    if (a) seen.add(a.buffer as ArrayBuffer)
  }
  const s = init.state
  add(s.pos); add(s.prev); add(s.vel)
  add(s.pinIdx); add(s.pinTarget); add(s.pinFlag); add(s.pinArcs)
  add(s.seamIdx); add(s.holdIdx); add(s.holdTarget); add(s.lastGood)
  for (const p of s.parts) {
    add(p.mesh.dist); add(p.mesh.bend); add(p.mesh.bendKArr)
  }
  if (s.field) {
    add(s.field.table)
    for (const rings of s.field.slices) {
      for (const ring of rings) add(ring.pts)
    }
  }
  return [...seen]
}
