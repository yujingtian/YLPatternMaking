// 引擎 worker 的主线程客户端：模块级单例（React StrictMode 双挂载也只建
// 一个 worker、只加载一次引擎资产），供 api.ts 路由层优先调用。
//
// 回退策略（与 HTTP 通道共存，最坏退化为现状体验）：
//   - ?engine=off / sessionStorage 降级标记 -> 不建 worker，全走 HTTP；
//   - init 超时 60s / 初始化失败 -> 会话降级（写 sessionStorage 防抖动重试）；
//   - 单次调用超时或引擎侧异常 -> 本次回落 HTTP 并计数，连续 3 次会话降级；
//   - worker 崩溃 -> 自动重建一次，再败降级。
//   validation 错误（与 HTTP 422 同构）不触发回退：参数问题换通道结果一样。
import type {
  AdjustPayload, EngineCmd, EngineMessage, EngineProgress, EngineRequest,
} from './protocol'
import type { DraftPayload, IssueDetail, SeedPayload } from '../types'

export type EngineState = 'loading' | 'ready' | 'unavailable'

/** worker/引擎侧失败（超时、内部异常）：路由层回落 HTTP */
export class EngineFailure extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'EngineFailure'
  }
}

/** 参数校验失败：与 HTTP 422 同构，直接抛给上层（与 apiHttp 相同口径） */
export class EngineValidationError extends Error {
  detail?: IssueDetail[]
  constructor(message: string, detail?: IssueDetail[]) {
    super(message)
    this.name = 'EngineValidationError'
    this.detail = detail
  }
}

export function isEngineFailure(e: unknown): boolean {
  return e instanceof EngineFailure
}

const DEGRADED_KEY = 'yl-engine-degraded'
const INIT_TIMEOUT_MS = 60_000
const MAX_CONSECUTIVE_FAILURES = 3

class EngineClient {
  state: EngineState = 'loading'

  private worker: Worker
  private seq = 0
  private crashed = false
  private failures = 0
  private initTimer: ReturnType<typeof setTimeout> | null = null
  private readonly pending = new Map<number, {
    resolve: (v: unknown) => void
    reject: (e: unknown) => void
    timer: ReturnType<typeof setTimeout>
  }>()
  private readonly progressCbs = new Set<(p: EngineProgress) => void>()

  constructor() {
    this.worker = this.spawn()
    this.initTimer = setTimeout(
      () => this.degrade('本地引擎初始化超时'), INIT_TIMEOUT_MS)
  }

  private spawn(): Worker {
    const w = new Worker(new URL('./worker.ts', import.meta.url),
                         { type: 'module' })
    w.onmessage = (ev: MessageEvent<EngineMessage>) => this.onMessage(ev.data)
    w.onerror = () => this.onCrash()
    return w
  }

  private emit(p: EngineProgress): void {
    for (const cb of this.progressCbs) cb(p)
  }

  private onMessage(msg: EngineMessage): void {
    if (msg.type === 'progress') {
      if (msg.phase === 'ready') {
        if (this.initTimer !== null) clearTimeout(this.initTimer)
        this.initTimer = null
        this.state = 'ready'
      } else if (msg.phase === 'failed') {
        this.degrade(msg.message ?? '本地引擎初始化失败')
        return
      }
      this.emit(msg)
      return
    }
    const p = this.pending.get(msg.id)
    if (p === undefined) return
    this.pending.delete(msg.id)
    clearTimeout(p.timer)
    if (msg.ok) {
      this.failures = 0
      p.resolve(msg.result)
    } else if (msg.error.kind === 'validation') {
      p.reject(new EngineValidationError(msg.error.message, msg.error.detail))
    } else {
      this.noteFailure()
      p.reject(new EngineFailure(msg.error.message))
    }
  }

  private onCrash(): void {
    // 未就绪时崩溃 -> 直接降级；就绪后崩溃 -> 重建一次（清空挂起请求）
    if (this.state !== 'ready') {
      this.degrade('本地引擎 worker 崩溃')
      return
    }
    this.rejectAllPending(new EngineFailure('引擎 worker 崩溃'))
    if (this.crashed) {
      this.degrade('引擎 worker 反复崩溃')
      return
    }
    this.crashed = true
    this.state = 'loading'
    this.worker.terminate()
    this.worker = this.spawn()
    this.initTimer = setTimeout(
      () => this.degrade('本地引擎重建超时'), INIT_TIMEOUT_MS)
  }

  private rejectAllPending(e: EngineFailure): void {
    for (const [, p] of this.pending) {
      clearTimeout(p.timer)
      p.reject(e)
    }
    this.pending.clear()
  }

  private degrade(reason: string): void {
    if (this.initTimer !== null) clearTimeout(this.initTimer)
    this.initTimer = null
    this.state = 'unavailable'
    this.rejectAllPending(new EngineFailure(reason))
    try { this.worker.terminate() } catch { /* 已终止 */ }
    try { sessionStorage.setItem(DEGRADED_KEY, reason) } catch { /* 隐私模式 */ }
    this.emit({ type: 'progress', phase: 'failed', message: reason })
  }

  private noteFailure(): void {
    this.failures += 1
    if (this.failures >= MAX_CONSECUTIVE_FAILURES) {
      this.degrade(`本地引擎连续失败 ${this.failures} 次`)
    }
  }

  onProgress(cb: (p: EngineProgress) => void): () => void {
    this.progressCbs.add(cb)
    // 订阅时若已就绪/降级，补发一次当前态（防错过 ready 事件）
    if (this.state === 'ready') cb({ type: 'progress', phase: 'ready' })
    if (this.state === 'unavailable') {
      cb({ type: 'progress', phase: 'failed' })
    }
    return () => this.progressCbs.delete(cb)
  }

  call<T>(cmd: EngineCmd, payload: DraftPayload | AdjustPayload | SeedPayload,
          timeoutMs: number): Promise<T> {
    if (this.state === 'unavailable') {
      return Promise.reject(new EngineFailure('本地引擎不可用'))
    }
    const id = ++this.seq
    const req: EngineRequest = { id, cmd, payload } as EngineRequest
    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id)
        this.noteFailure()
        reject(new EngineFailure(`本地引擎计算超时（${timeoutMs}ms）`))
      }, timeoutMs)
      this.pending.set(id, {
        resolve: resolve as (v: unknown) => void, reject, timer })
      this.worker.postMessage(req)
    })
  }
}

let instance: EngineClient | null = null

/** 取引擎客户端单例；返回 null = 本会话不用本地引擎（?engine=off/已降级） */
export function getEngine(): EngineClient | null {
  if (typeof window === 'undefined') return null
  if (instance !== null) return instance
  try {
    const q = new URLSearchParams(window.location.search)
    if (q.get('engine') === 'off') return null      // 验收/对比用强制 HTTP
    if (sessionStorage.getItem(DEGRADED_KEY) !== null) return null
  } catch { /* 隐私模式下 sessionStorage 不可用：照常启用 */ }
  instance = new EngineClient()
  return instance
}
