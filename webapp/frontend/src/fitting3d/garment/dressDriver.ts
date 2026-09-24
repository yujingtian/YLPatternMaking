// 穿台解算驱动（2026-09-23 Worker 化）：把原 Fitting3DView rAF tick 的
// 「stepDrape + ctrl.step + 热力图节拍 + 双停判据」逐字收口为一个可在
// 任意宿主跑的步进器——主线程（node 金标）与 worker（生产）共用同一份
// 语义，宿主只管调度（worker = MessageChannel 每宏任务一步）与消费
// （sink 回调）。终态判据与视图现行完全一致：st!=='running' 且
// ctrl.phase==='done'（settle/capped/frozen 自然停）。
// 热力图节拍按仿真帧（frames 在步内自增，与解算进度同步）——HEAT_PRIOR.
// every 6 帧一次；终态帧恒带末帧 heat（heatOn 时）。pos/heat 所有权归
// sink：worker 宿主 slice+transfer，主线程宿主直读。
import { stepDrape, type DrapeSim } from './drape'
import { buildSettle, type DressReport, type SettleOptions } from './settle'
import { computeHeat } from './heatmap'
import { HEAT_PRIOR } from './priors'
import type { CrotchProbeIdx } from './solvestate'

export interface DressSink {
  /** 每仿真步一次（帧号自 0 起；pos = sim.pos 引用，heat 可空） */
  onFrame(frame: number, pos: Float32Array, heat: Float32Array | null): void
  /** 终态（report 一次性；末帧 pos + heatOn 时末帧 heat） */
  onDone(report: DressReport, pos: Float32Array, heat: Float32Array | null): void
  onError(err: unknown): void
}

export interface DressRun {
  /** 推一步；false = 终态（此后恒 false，安全重复调） */
  stepOnce(): boolean
  /** 热力图开关（解算中/终态皆可；开 = 后续节拍帧带 heat） */
  setHeat(on: boolean): void
}

export function createDressRun(
  sim: DrapeSim, probeIdx: CrotchProbeIdx,
  jam: NonNullable<SettleOptions['jam']>, heatOn: boolean,
  sink: DressSink,
  pinned = false,
): DressRun {
  // ctrl 宿主侧重建（闭包快照 fArr/baseY 读 sim.pinIdx/pinTarget，构造后
  // 即自洽——序列化不携 ctrl 的原因，见 solvestate.ts 头注）；pinned 随
  // init 透传（指定穿位：摆位层整组下移、钉初始即终位，lowering 旁路
  // 直通 settle）
  const ctrl = buildSettle(sim, probeIdx, { jam, pinned })
  let on = heatOn
  let frames = 0
  let finished = false
  return {
    stepOnce(): boolean {
      if (finished) return false
      let st: ReturnType<typeof stepDrape>
      let ph: ReturnType<typeof ctrl.step>
      try {
        st = stepDrape(sim)
        ph = ctrl.step(sim)
      } catch (err) {
        finished = true
        sink.onError(err)
        return false
      }
      const heat = on && frames % HEAT_PRIOR.every === 0
        ? computeHeat(sim, 'gap') : null
      frames++
      // 双停（视图现行判据逐字）：sim 停 + 控制器 done（hold/lowering 中
      // wake 反复续命 settled；停走只认 settle 相位真实静止）
      finished = st !== 'running' && ph === 'done'
      if (finished) {
        const h = on && heat === null ? computeHeat(sim, 'gap') : heat
        sink.onDone(ctrl.report(sim), sim.pos, h)
        return false
      }
      sink.onFrame(frames - 1, sim.pos, heat)
      return true
    },
    setHeat(v: boolean): void {
      on = v
    },
  }
}
