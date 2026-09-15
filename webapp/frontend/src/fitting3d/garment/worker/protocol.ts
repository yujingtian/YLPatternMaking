// sim worker 协议：主线程发 init（payload），worker 自建撑型芯/mesh/场/BVH/
// 整裤并自驱 60Hz 解算，每帧位置转移回传；settled/frozen 停走。
// 2026-09-14 解耦定型：解算空间 = 纸样系（y=纸样高），碰撞体 = 纸样围度
// 撑型芯（core.ts），**不再消费人台几何**——init 不带 bodyPos/bodyIdx/
// landmarks，人台只是视图层旁侧参照（独立原则贯彻到解算）。
import type { FittingResult } from '../../../types'

export type SimStatus = 'running' | 'settled' | 'frozen'

export interface WorkerInit {
  type: 'init'
  payload: FittingResult
  cold: boolean              // true = 放弃热启动（「重新悬挂」）
  hang?: boolean             // true = 悬挂展示（现行唯一模式）：帧数封顶
                             // HANG_PRIOR.maxFrames 兜底
}

export type ToWorker = WorkerInit

export type FromWorker =
  | { type: 'ready'; total: number }
  | { type: 'frame'; pos: Float32Array; status: SimStatus; step: number;
      capped: boolean; seamErrAvg: number; seamErrP95: number }
  | { type: 'error'; message: string }
