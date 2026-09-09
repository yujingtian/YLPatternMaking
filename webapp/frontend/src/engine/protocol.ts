// 主线程 <-> 引擎 worker 的 RPC 协议（2026-08 Pyodide 本地引擎）。
// 请求带 id 配对响应；计算命令与 HTTP 端点一一对应：
//   sheet   <-> POST /api/draft/sheet    pieces  <-> POST /api/draft/pieces
//   adjust  <-> POST /api/adjust         seed    <-> POST /api/seed
//   fitting <-> POST /api/draft/fitting（3D 试穿 payload，§10.11）
// 结果类型与 apiHttp 各函数返回值完全同构（worker 胶水逐字段复刻 app.py），
// 上层（useDraft/SheetView）对两条通道零感知。
import type { DraftPayload, IssueDetail, SeedPayload } from '../types'

export type EngineCmd = 'sheet' | 'pieces' | 'adjust' | 'fitting' | 'seed'

export type AdjustPayload = DraftPayload & {
  element: string
  param: string
  axis: string
  target: number
}

export type EngineRequest =
  | { id: number; cmd: 'sheet'; payload: DraftPayload }
  | { id: number; cmd: 'pieces'; payload: DraftPayload }
  | { id: number; cmd: 'adjust'; payload: AdjustPayload }
  | { id: number; cmd: 'fitting'; payload: DraftPayload }
  | { id: number; cmd: 'seed'; payload: SeedPayload }

// 错误两分法（路由层据此决定回退与否）：
//   validation —— 与 HTTP 422 同构（IssueDetail[]），是参数问题，
//                换 HTTP 通道跑结果也一样，直接抛给上层显示；
//   engine     —— worker/引擎侧异常或超时，回落 HTTP 再试一次
export interface EngineError {
  kind: 'validation' | 'engine'
  message: string
  detail?: IssueDetail[]
}

// type 判别字段：worker -> 主线程两类消息（response/progress）共用判别式
export type EngineResponse =
  | { type: 'response'; id: number; ok: true; result: unknown }
  | { type: 'response'; id: number; ok: false; error: EngineError }

// worker init 各阶段上报（ready 前主线程显示加载进度/角标）
export interface EngineProgress {
  type: 'progress'
  phase: 'pyodide' | 'engine' | 'ready' | 'failed'
  message?: string
  rev?: string
}

export type EngineMessage = EngineResponse | EngineProgress
