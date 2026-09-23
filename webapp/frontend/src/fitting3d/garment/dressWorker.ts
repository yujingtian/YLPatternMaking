// 穿台解算 worker 入口（2026-09-23 Worker 化）：主线程构建 sim →
// toSolveState 投影 → init（transfer 零拷贝，**主侧等本模块的 ready 握手
// 再发**——模块 worker 脚本加载完成前投递的消息会被浏览器丢弃，当日实
// 测 new Worker 后立刻 post 的 init 石沉大海：worker 无异常无回帧、重发
// 即正常）→ 再水化 + 逐宏任务一步 stepDrape（MessageChannel 自 post 调
// 度——嵌套 setTimeout 有 4ms 钳 ~10% 开销；兜底方案 setTimeout 每任务
// 2 步留档不启用）。每步回 frame {pos(transfer), heat?}，双停回 done
// {report}。**done 后不 terminate**（setHeat 终态重着色用）；重穿 epoch/
// 组件卸载由主侧 terminate。
// 热力图 worker 侧算：computeHeat 只读 sim.pos/field/yLift（gap-only），
// heat 数组随消息 transfer。先例 engine/worker.ts；vite worker.format
// 'es' 已配（vite.config.ts）。
import type { DrapeSim } from './drape'
import type { DressReport } from './settle'
import { computeHeat } from './heatmap'
import { createDressRun, type DressRun } from './dressDriver'
import { fromSolveState, type CrotchProbeIdx, type SolveState } from './solvestate'
import type { SettleOptions } from './settle'

export type WorkerIn =
  | { type: 'init'; state: SolveState; probeIdx: CrotchProbeIdx;
    jam: NonNullable<SettleOptions['jam']>; heatOn: boolean }
  | { type: 'setHeat'; on: boolean }

export type WorkerOut =
  | { type: 'ready' }
  | { type: 'frame'; frame: number; pos: Float32Array;
    heat: Float32Array | null }
  | { type: 'done'; report: DressReport; pos: Float32Array;
    heat: Float32Array | null }
  | { type: 'heat'; heat: Float32Array }
  | { type: 'error'; message: string }

const ctx = self as unknown as {
  onmessage: ((e: MessageEvent<WorkerIn>) => void) | null
  postMessage: (msg: WorkerOut, transfer?: ArrayBuffer[]) => void
}

let run: DressRun | null = null
let sim: DrapeSim | null = null

const post = (msg: WorkerOut, transfer: ArrayBuffer[] = []): void => {
  ctx.postMessage(msg, transfer)
}

// ---- 调度：MessageChannel 自 post，每宏任务恰好一步（非 setTimeout——
// 定时器 4ms 钳在 ~50ms 步长下白丢 ~8%；port 自 post 零延迟排队）----
const chan = new MessageChannel()
let scheduled = false
chan.port1.onmessage = () => {
  scheduled = false
  if (run === null) return
  if (run.stepOnce()) schedule()
}
const schedule = (): void => {
  if (scheduled) return
  scheduled = true
  chan.port2.postMessage(0)
}

ctx.onmessage = (e: MessageEvent<WorkerIn>) => {
  const msg = e.data
  if (msg.type === 'init') {
    sim = fromSolveState(msg.state)
    run = createDressRun(sim, msg.probeIdx, msg.jam, msg.heatOn, {
      onFrame: (frame, pos, heat) => {
        const p = pos.slice()   // sim.pos 持续复用，副本随消息 transfer
        const transfer = heat ? [p.buffer as ArrayBuffer, heat.buffer as ArrayBuffer]
          : [p.buffer as ArrayBuffer]
        post({ type: 'frame', frame, pos: p, heat }, transfer)
      },
      onDone: (report, pos, heat) => {
        const p = pos.slice()
        const transfer = heat ? [p.buffer as ArrayBuffer, heat.buffer as ArrayBuffer]
          : [p.buffer as ArrayBuffer]
        post({ type: 'done', report, pos: p, heat }, transfer)
      },
      onError: (err) => {
        post({ type: 'error', message: err instanceof Error ? err.message : String(err) })
      },
    })
    schedule()
  } else if (msg.type === 'setHeat') {
    run?.setHeat(msg.on)
    // 开 = 立即按当前帧重算一层回传（开关只重着色不重跑仿真；解算中
    // 后续节拍帧照常带 heat）。关 = 主侧自行清色，无需回包
    if (msg.on && sim) {
      const v = computeHeat(sim, 'gap')
      post({ type: 'heat', heat: v }, [v.buffer as ArrayBuffer])
    }
  }
}

// ready 握手：模块脚本评估完毕的信号（文件末行 = 恰在 onmessage 挂好之后
// 执行）。主线程收到才发 init——见头注「加载完成前投递的消息会被丢弃」。
post({ type: 'ready' })
