// 机器排料求解轮询 hook（二期对接 §10.3.2 US-003）：submit → 双档轮询 →
// 终态自动取果。状态机 idle→submitting→running→done|stopped|error；MS 的
// submitted/starting/orphan 归 running 家族（orphan = MS 重启遗留诊断态，
// 30s 宽限窗内继续轮询会自然落 error，pid 存活期可 stop）。轮询双档：弹窗
// 在视 2s / 关窗降频 15s（task_id 存 localStorage 供「继续查看」attach 重
// 连，刷新/误关后恢复）；任一终端态停表；组件卸载清计时器。网络容错：单次
// 失败继续轮询，连续 3 次才转 error（MS 闪断不误杀长跑任务）；404/400
//（任务不存在/task_id 非法）立即终态不重试。
// client_ref（MS 幂等引用）由本层追加，不进 buildMachineConfig 产物（US-002
// 口径）。reset 只停表清锚、不删 MS 任务——结果期清理（best-effort DELETE，
// MS 侧 TTL+7 天兜底）是弹窗显式关闭动作（US-004）的职责。
import { useCallback, useEffect, useRef, useState } from 'react'
import type { MsError } from '../api'
import { msResult, msSolveStart, msStatus, msStop } from '../api'
import type { MsMachineConfig, MsPerSeed, MsResult, MsStatus } from '../types'
import { RUN_MODE_OPTIONS } from '../msConfig'

export type NestSolvePhase =
  | 'idle' | 'submitting' | 'running' | 'done' | 'stopped' | 'error'

// 双档轮询间隔（ms）：在视 2s（进度顺滑）/ 关窗 15s（后台守望）
export const POLL_FAST_MS = 2_000
export const POLL_SLOW_MS = 15_000
// 连续网络失败容限（达到即转 error；单次失败不炸）
export const POLL_FAIL_LIMIT = 3

// localStorage 任务锚（进度期关窗后「继续查看」重连的依据）
export const MS_TASK_STORAGE_KEY = 'ylpattern.msNestTask.v1'

export interface StoredMsTask {
  taskId: string
  runMode: MsMachineConfig['run_mode']
  at?: string
}

export function readStoredMsTask(): StoredMsTask | null {
  try {
    const raw = localStorage.getItem(MS_TASK_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (typeof parsed?.taskId !== 'string' || !parsed.taskId) return null
    return parsed as StoredMsTask
  } catch {
    return null
  }
}

// MS 状态 → hook 阶段：submitted/starting/running/orphan 均 running 家族
//（orphan 语义见文件头；原始 state 仍经 status 透出供 UI 细分展示）
export function msStateToPhase(s: MsStatus['state']): NestSolvePhase {
  return s === 'done' || s === 'stopped' || s === 'error' ? s : 'running'
}

// 利用率%（物理口径，MS NestLabel 同源：density 分数×100 两位小数）；
// incumbent（best-so-far 摘要）优先、回落 current（最新帧）
export function densityPctOf(status: MsStatus): number | null {
  const d = status.incumbent?.density ?? status.current?.density ?? null
  return d === null ? null : Math.round(d * 10_000) / 100
}

// 进度条总时长：MS total_budget_sec 优先（运行模式烘焙值），缺失回落
// RUN_MODE_OPTIONS 同源预算（orphan 恢复场景 MS 侧可降级 null）
export function totalSecOf(status: MsStatus): number | null {
  if (status.total_budget_sec !== null) return status.total_budget_sec
  return RUN_MODE_OPTIONS.find((o) => o.value === status.run_mode)?.budgetSec
    ?? null
}

// client_ref（MS 幂等引用，≤128 字符）：每次提交新生成——同 ref 在飞会
// 409，新引用最简（重试即新任务语义，旧任务交由 MS TTL 兜底）
function newClientRef(): string {
  return `yl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export interface NestSolveState {
  phase: NestSolvePhase
  visible: boolean               // 弹窗在视（双档轮询开关的 UI 镜像）
  taskId: string | null
  startedAt: string | null       // solve 202 的 started_at（attach 重连为 null）
  error: string | null           // 最近一次可读中文错误（phase=error 或取果失败）
  // running 期进度投影（终态后保留最后一拍）
  densityPct: number | null
  elapsedSec: number
  totalSec: number | null
  perSeed: MsPerSeed[]
  status: MsStatus | null        // 最后一次原始状态（orphan/exit_code 等 UI 细节）
  result: MsResult | null        // done/stopped 自动取果（{manifest, best, …}）
  // 提交（互斥：idle/error 之外丢弃）；成功 true。config 为 buildMachineConfig
  // 产物，client_ref 由本层追加
  submit: (file: Blob, filename: string, config: MsMachineConfig) =>
    Promise<boolean>
  attach: (taskId: string) => void   // 重连既有任务（首拍轮询自会对齐终态）
  stop: () => void                   // 终止 → stopped（fire-and-forget）
  setVisible: (v: boolean) => void   // 双档切换（即时重排待发的一拍）
  reset: () => void                  // 回 idle：停表 + 清任务锚（不删 MS 任务）
}

export function useNestSolve(): NestSolveState {
  const [phase, setPhase] = useState<NestSolvePhase>('idle')
  const [visible, setVisibleState] = useState(true)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [startedAt, setStartedAt] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [densityPct, setDensityPct] = useState<number | null>(null)
  const [elapsedSec, setElapsedSec] = useState(0)
  const [totalSec, setTotalSec] = useState<number | null>(null)
  const [perSeed, setPerSeed] = useState<MsPerSeed[]>([])
  const [status, setStatus] = useState<MsStatus | null>(null)
  const [result, setResult] = useState<MsResult | null>(null)

  // 轮询引擎 refs：异步闭包读恒新值（useDraft measRef 先例）+ 卸载守卫
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const tickRef = useRef<() => Promise<void>>(async () => {})
  const phaseRef = useRef<NestSolvePhase>('idle')
  const taskIdRef = useRef<string | null>(null)
  const visibleRef = useRef(true)
  const failRef = useRef(0)
  const aliveRef = useRef(true)

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const goPhase = useCallback((p: NestSolvePhase) => {
    phaseRef.current = p
    setPhase(p)
    if (p !== 'running') clearTimer()   // 终端/非轮询态一律停表
  }, [clearTimer])

  const schedule = useCallback((delayMs: number) => {
    clearTimer()
    timerRef.current = setTimeout(() => { void tickRef.current() }, delayMs)
  }, [clearTimer])

  // 终态取果（done/stopped；stopped 态 MS 由 best_frame 边车 density 最大
  // 回落）——best-effort：失败不改变终态，消息进 error 供 UI 展示
  const fetchResult = useCallback(async (id: string) => {
    const terminal = () =>
      phaseRef.current === 'done' || phaseRef.current === 'stopped'
    try {
      const r = await msResult(id)
      if (!aliveRef.current || !terminal()) return
      setResult(r)
      setError(null)
    } catch (e) {
      if (!aliveRef.current || !terminal()) return
      setError((e as Error).message)
    }
  }, [])

  const tick = useCallback(async () => {
    const id = taskIdRef.current
    if (id === null || phaseRef.current !== 'running') return
    try {
      const st = await msStatus(id)
      if (!aliveRef.current || phaseRef.current !== 'running') return
      failRef.current = 0
      setStatus(st)
      setDensityPct(densityPctOf(st))
      setElapsedSec(st.elapsed_sec)
      setTotalSec(totalSecOf(st))
      setPerSeed(st.per_seed)
      const p = msStateToPhase(st.state)
      if (p === 'running') {
        schedule(visibleRef.current ? POLL_FAST_MS : POLL_SLOW_MS)
        return
      }
      goPhase(p)
      if (p === 'error') setError(st.error ?? '求解异常退出（MS 未提供错误详情）')
      else void fetchResult(id)
    } catch (e) {
      if (!aliveRef.current || phaseRef.current !== 'running') return
      const err = e as MsError
      // 404/400：任务不存在/task_id 非法——重试无意义，立即终态
      if (err.status === 404 || err.status === 400) {
        goPhase('error')
        setError(err.message)
        return
      }
      failRef.current += 1
      if (failRef.current >= POLL_FAIL_LIMIT) {
        goPhase('error')
        setError(`MS 排料服务连续 ${POLL_FAIL_LIMIT} 次无响应（服务可能未启动；`
          + '任务在 MS 侧可能仍在运行，可稍后「继续查看」重连）')
        return
      }
      schedule(visibleRef.current ? POLL_FAST_MS : POLL_SLOW_MS)
    }
  }, [fetchResult, goPhase, schedule])
  // 同步镜像（measRef 先例）：submit/attach 紧随其后调度时 tick 已就位
  tickRef.current = tick

  const submit = useCallback(async (
    file: Blob, filename: string, config: MsMachineConfig,
  ) => {
    if (phaseRef.current !== 'idle' && phaseRef.current !== 'error') return false
    goPhase('submitting')
    // 清上一任务现场（error 重试场景）
    taskIdRef.current = null
    setTaskId(null)
    setStartedAt(null)
    setError(null)
    setResult(null)
    setStatus(null)
    setDensityPct(null)
    setElapsedSec(0)
    setTotalSec(null)
    setPerSeed([])
    failRef.current = 0
    try {
      const res = await msSolveStart(file, filename,
        { ...config, client_ref: newClientRef() })
      if (!aliveRef.current) return false
      taskIdRef.current = res.task_id
      setTaskId(res.task_id)
      setStartedAt(res.started_at)
      try {
        localStorage.setItem(MS_TASK_STORAGE_KEY, JSON.stringify({
          taskId: res.task_id, runMode: config.run_mode, at: res.started_at,
        }))
      } catch { /* 存储被禁等：重连锚丢失不阻塞主流程 */ }
      goPhase('running')
      schedule(visibleRef.current ? POLL_FAST_MS : POLL_SLOW_MS)
      return true
    } catch (e) {
      if (!aliveRef.current) return false
      goPhase('error')
      setError((e as Error).message)
      return false
    }
  }, [goPhase, schedule])

  // 重连既有任务（「继续查看」）：按 running 起步，首拍轮询自会对齐真实
  // 终态（done 也会走自动取果）；submitting/running 中是无效调用
  const attach = useCallback((id: string) => {
    if (phaseRef.current === 'submitting' || phaseRef.current === 'running')
      return
    clearTimer()
    failRef.current = 0
    taskIdRef.current = id
    setTaskId(id)
    setStartedAt(null)
    setError(null)
    setResult(null)
    setStatus(null)
    setDensityPct(null)
    setElapsedSec(0)
    setTotalSec(null)
    setPerSeed([])
    goPhase('running')
    schedule(visibleRef.current ? POLL_FAST_MS : POLL_SLOW_MS)
  }, [clearTimer, goPhase, schedule])

  // 终止（→ stopped 可返回）：fire-and-forget——已终态 400 等静默，状态由
  // 补发的一拍（0ms）轮询对齐
  const stop = useCallback(() => {
    const id = taskIdRef.current
    if (id === null || phaseRef.current !== 'running') return
    void (async () => {
      try { await msStop(id) } catch { /* 静默：轮询对齐 */ }
      if (aliveRef.current && phaseRef.current === 'running') schedule(0)
    })()
  }, [schedule])

  // 双档切换即时生效：关窗降频/开窗提速——在跑则重排待发的一拍
  const setVisible = useCallback((v: boolean) => {
    visibleRef.current = v
    setVisibleState(v)
    if (phaseRef.current === 'running' && timerRef.current !== null)
      schedule(v ? POLL_FAST_MS : POLL_SLOW_MS)
  }, [schedule])

  const reset = useCallback(() => {
    clearTimer()
    failRef.current = 0
    taskIdRef.current = null
    try { localStorage.removeItem(MS_TASK_STORAGE_KEY) } catch { /* 同上 */ }
    goPhase('idle')
    setTaskId(null)
    setStartedAt(null)
    setError(null)
    setResult(null)
    setStatus(null)
    setDensityPct(null)
    setElapsedSec(0)
    setTotalSec(null)
    setPerSeed([])
  }, [clearTimer, goPhase])

  // 卸载兜底：清计时器 + 后续 setState 守卫（长跑任务不跨卸载泄漏）
  useEffect(() => {
    aliveRef.current = true
    return () => {
      aliveRef.current = false
      if (timerRef.current !== null) clearTimeout(timerRef.current)
    }
  }, [])

  return {
    phase, visible, taskId, startedAt, error,
    densityPct, elapsedSec, totalSec, perSeed, status, result,
    submit, attach, stop, setVisible, reset,
  }
}

