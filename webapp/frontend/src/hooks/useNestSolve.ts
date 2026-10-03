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
// 四期双通道 US-003（tasks/prd-machine-direct-channel.md）：任务生命周期
// 绑定通道——submit 前置 resolveMsChannel 探测，直连提交网络级失败在提交
// 层降级回退 proxy 重试一次（要拿到任务实际落点才能绑定）；锚/状态/取果/
// 终止全走绑定通道（零探测零自动切换——本地 MS 中途死 → 连续失败计数落
// error 引导两条出路，详见 pollFailMessage）。
import { useCallback, useEffect, useRef, useState } from 'react'
import type { MsError } from '../api'
import { msResult, msSolveStart, msStatus, msStop } from '../api'
import type { MsChannel } from '../msBase'
import { demoteMsChannel, resolveMsChannel } from '../msBase'
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
  // 任务绑定的通道标记（US-003：direct 含发现 base / proxy）；readStoredMsTask
  // 归一后恒在场——US-003 前的旧锚缺失/坏标记一律归 proxy（旧锚任务全落
  // 在「/ms 代理唯一通道」时代，按 proxy 绑定恢复轮询才不串台）
  channel: MsChannel
  at?: string
}

// 锚通道标记归一（读侧防御）：direct 须带非空 string base，proxy 无参；
// 其余形态（缺标记/坏 JSON 字段/未知 kind）→ proxy（见 StoredMsTask 注）
function normalizeStoredChannel(raw: unknown): MsChannel {
  if (typeof raw === 'object' && raw !== null) {
    const c = raw as { kind?: unknown; base?: unknown }
    if (c.kind === 'direct' && typeof c.base === 'string' && c.base)
      return { kind: 'direct', base: c.base }
    if (c.kind === 'proxy') return { kind: 'proxy' }
  }
  return { kind: 'proxy' }
}

export function readStoredMsTask(): StoredMsTask | null {
  try {
    const raw = localStorage.getItem(MS_TASK_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (typeof parsed?.taskId !== 'string' || !parsed.taskId) return null
    // 锚过期（>24h）视同无会话并清锚：任务早被 MS 侧 TTL 回收，attach
    // 只会得到 error 噪音、按钮白挂「排料中」一轮（2026-09-29 用户报障
    // 「一进工作台就排料中」成因之一；缺 at 的旧锚兼容保留）
    if (typeof parsed.at === 'string') {
      const t = Date.parse(parsed.at)
      if (Number.isFinite(t)
          && Date.now() - t > MS_TASK_ANCHOR_TTL_MS) {
        localStorage.removeItem(MS_TASK_STORAGE_KEY)
        return null
      }
    }
    return {
      taskId: parsed.taskId,
      runMode: parsed.runMode,
      channel: normalizeStoredChannel(parsed.channel),
      at: parsed.at,
    }
  } catch {
    return null
  }
}

// 任务锚 TTL：MS 侧任务 TTL+7 天兜底，但「继续查看」语义是短期重连；
// 超一天的陈锚直接跳过（attach 对账一轮 error 噪音无意义）
export const MS_TASK_ANCHOR_TTL_MS = 24 * 60 * 60 * 1000

// MS 状态 → hook 阶段：submitted/starting/running/orphan 均 running 家族
//（orphan 语义见文件头；原始 state 仍经 status 透出供 UI 细分展示）
export function msStateToPhase(s: MsStatus['state']): NestSolvePhase {
  return s === 'done' || s === 'stopped' || s === 'error' ? s : 'running'
}

// 弹窗显式关闭（唯一出口）的动作语义（US-004 弹窗安全第二则）：
// - 进度期家族（submitting/running）→ background：关窗降频 15s 后台守望，
//   不回收任务（task_id 已存锚，可「继续查看」attach 重连）；
// - done/stopped → deleteTask：会话终结 + best-effort DELETE 回收 MS
//   会话名额（失败静默，MS 侧 TTL+7 天兜底）；
// - idle/error → 纯重置关窗（无任务可回收）
export interface SolveCloseBehavior {
  background: boolean
  deleteTask: boolean
}

export function solveCloseBehavior(
  phase: NestSolvePhase,
): SolveCloseBehavior {
  if (phase === 'submitting' || phase === 'running')
    return { background: true, deleteTask: false }
  if (phase === 'done' || phase === 'stopped')
    return { background: false, deleteTask: true }
  return { background: false, deleteTask: false }
}

// 连续网络失败（POLL_FAIL_LIMIT 达限）的 error 引导文案（US-003 AC#2）：
// - direct：本地 MS 中途死——两条出路（重启本地 MS 后凭锚点恢复，MS 重启
//   后任务 marker 在 → orphan 宽限窗自然判定 / 重新提交转服务器排料重跑），
//   **不自动切换通道、不自动重跑**（PRD FR-3：转服务器是用户显式动作）
// - proxy：现状通用文案（服务器 MS 视角，零改动）
export function pollFailMessage(channel: MsChannel): string {
  if (channel.kind === 'direct')
    return `本地排料服务连续 ${POLL_FAIL_LIMIT} 次无响应（本地 VB超排 可能已退出）。`
      + '出路一：重启本地 VB超排 后点击左栏「排料」继续查看——任务锚点仍在，'
      + 'MS 重启后任务标记会以遗留任务恢复判定；'
      + '出路二：重试/再次排料 改用服务器排料重跑。'
      + '本任务不会自动切换通道，也不会自动重跑'
  return `MS 排料服务连续 ${POLL_FAIL_LIMIT} 次无响应（服务可能未启动；`
    + '任务在 MS 侧可能仍在运行，可稍后「继续查看」重连）'
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
  // 任务绑定的通道（US-003）：submit 成功/attach 时绑定（任务实际落点），
  // 弹窗通道指示与生命周期请求（轮询/取果/终止/下载）随它走；null = 无
  // 任务在手（idle/提交失败期）
  channel: MsChannel | null
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
  // 产物，client_ref 由本层追加。前置 resolveMsChannel 探测，直连网络级
  // 失败降级 proxy 重试一次（绑定落点通道）
  submit: (file: Blob, filename: string, config: MsMachineConfig) =>
    Promise<boolean>
  // 重连既有任务（首拍轮询自会对齐终态）：channel = 锚点绑定通道（恢复
  // 轮询走原通道，US-003 AC#1）
  attach: (taskId: string, channel: MsChannel) => void
  stop: () => void                   // 终止 → stopped（fire-and-forget）
  setVisible: (v: boolean) => void   // 双档切换（即时重排待发的一拍）
  reset: () => void                  // 回 idle：停表 + 清任务锚（不删 MS 任务）
}

export function useNestSolve(): NestSolveState {
  const [phase, setPhase] = useState<NestSolvePhase>('idle')
  const [visible, setVisibleState] = useState(true)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [channel, setChannel] = useState<MsChannel | null>(null)
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
  const channelRef = useRef<MsChannel | null>(null)
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
    // 无条件重排（2026-09-30 撤回 063531e「取更早一拍」守卫）：守卫把定时器
    // fire 后残留的 timerRef 误当「有待发一拍」，首次成功轮询后的重排被吞、
    // 轮询链死在第一拍（进度冻结、终止无回显、按钮恒「排料中」——当日用户
    // 报障）。它想修的「attach 0ms 对账拍被挂载期 15s 降频推迟」属偶现问题，
    // 修法不对整体撤回，待后续遇到再彻查（用户口径 2026-09-30）
    clearTimer()
    timerRef.current = setTimeout(() => { void tickRef.current() }, delayMs)
  }, [clearTimer])

  // 终态取果（done/stopped；stopped 态 MS 由 best_frame 边车 density 最大
  // 回落）——best-effort：失败不改变终态，消息进 error 供 UI 展示
  const fetchResult = useCallback(async (id: string) => {
    const terminal = () =>
      phaseRef.current === 'done' || phaseRef.current === 'stopped'
    try {
      const r = await msResult(id, channelRef.current ?? undefined)
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
      const st = await msStatus(id, channelRef.current ?? undefined)
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
        // 引导随绑定通道分派（US-003 AC#2）：direct 死连给两条出路且明示
        // 不自动切换；proxy 保持现状文案。taskId 在场 ⇒ channel 必已绑定
        //（submit 成功/attach 均先绑），proxy 兜底仅防御
        setError(pollFailMessage(
          channelRef.current ?? { kind: 'proxy' }))
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
    channelRef.current = null
    setChannel(null)
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
      // 前置通道探测（US-003 AC#1）：resolveMsChannel 会话缓存命中零网络
      // 成本，首提交 ~300ms 探测在 submitting Spin 内不拖慢感知
      let ch = await resolveMsChannel()
      const full = { ...config, client_ref: newClientRef() }
      let res
      try {
        res = await msSolveStart(file, filename, full, ch)
      } catch (e) {
        // 直连提交网络级失败（本地 MS 提交中途退出/CORS 拦截）→ 提交层
        // 降级回退 proxy 重试一次（US-002 AC#4「归一为回退」口径上移到此：
        // 任务通道绑定要求提交层拿到任务**实际落点**——请求层内部降级对
        // 外不可见，锚会绑错通道；同 client_ref 跨通道不冲突——两通道是
        // 不同 MS 实例）。非 TypeError（30s 超时等）不降级照旧落 error
        if (ch.kind !== 'direct' || !(e instanceof TypeError)) throw e
        demoteMsChannel()
        ch = { kind: 'proxy' }
        res = await msSolveStart(file, filename, full, ch)
      }
      if (!aliveRef.current) return false
      // 通道随 task_id 绑定（锚附通道标记 kind+base，恢复轮询走原通道）
      channelRef.current = ch
      setChannel(ch)
      taskIdRef.current = res.task_id
      setTaskId(res.task_id)
      setStartedAt(res.started_at)
      try {
        localStorage.setItem(MS_TASK_STORAGE_KEY, JSON.stringify({
          taskId: res.task_id, runMode: config.run_mode, at: res.started_at,
          channel: ch,
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

  // 重连既有任务（「继续查看」）：按 running 起步，首拍**立即对账**（0ms，
  // 非 15s 降频档——挂载/刷新恢复秒级对齐真实终态：done 转会话态、
  // 404/连续失败转 error，按钮不再空挂「排料中」）；submitting/running
  // 中是无效调用，但计时器已死时补一拍（dev StrictMode 双挂载：卸载
  // 清理停表后 attach 早退会让 running 态永久失表——报障成因之二）。
  // channel = 锚点绑定通道（US-003）：恢复轮询走原通道，不重新探测
  const attach = useCallback((id: string, ch: MsChannel) => {
    if (phaseRef.current === 'submitting' || phaseRef.current === 'running') {
      if (timerRef.current === null) schedule(0)   // 死表补拍：立即对账
      return
    }
    clearTimer()
    failRef.current = 0
    taskIdRef.current = id
    setTaskId(id)
    channelRef.current = ch
    setChannel(ch)
    setStartedAt(null)
    setError(null)
    setResult(null)
    setStatus(null)
    setDensityPct(null)
    setElapsedSec(0)
    setTotalSec(null)
    setPerSeed([])
    goPhase('running')
    schedule(0)
  }, [clearTimer, goPhase, schedule])

  // 终止（→ stopped 可返回）：fire-and-forget——已终态 400 等静默，状态由
  // 补发的一拍（0ms）轮询对齐（走绑定通道）
  const stop = useCallback(() => {
    const id = taskIdRef.current
    if (id === null || phaseRef.current !== 'running') return
    void (async () => {
      try { await msStop(id, channelRef.current ?? undefined) }
      catch { /* 静默：轮询对齐 */ }
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
    channelRef.current = null
    try { localStorage.removeItem(MS_TASK_STORAGE_KEY) } catch { /* 同上 */ }
    goPhase('idle')
    setTaskId(null)
    setChannel(null)
    setStartedAt(null)
    setError(null)
    setResult(null)
    setStatus(null)
    setDensityPct(null)
    setElapsedSec(0)
    setTotalSec(null)
    setPerSeed([])
  }, [clearTimer, goPhase])

  // 卸载兜底：清计时器 + 后续 setState 守卫（长跑任务不跨卸载泄漏）；
  // clearTimer 同步置 null——重挂（StrictMode）时 attach 早退分支据
  // timerRef === null 补拍，不再依赖「已清 timer 残留非 null」的巧合
  useEffect(() => {
    aliveRef.current = true
    return () => {
      aliveRef.current = false
      clearTimer()
    }
  }, [clearTimer])

  return {
    phase, visible, taskId, channel, startedAt, error,
    densityPct, elapsedSec, totalSec, perSeed, status, result,
    submit, attach, stop, setVisible, reset,
  }
}

