// M1 解算生命周期 hook：fitting 快照 -> worker init，每帧位置流回
// （onFrame 回调，不走 state——60Hz 不许触发 React 渲染）；settled/frozen
// 停走；「重新悬挂」= 冷启动重放当前形态。2026-09-14 解耦后 init 只带
// payload（撑型芯在 worker 内自建），不再消费人台几何/地标。
import { useCallback, useEffect, useRef, useState } from 'react'
import type { FittingResult, Snapshot } from '../../types'
import type { FromWorker, ToWorker } from './worker/protocol'

export type SolverStatus = 'idle' | 'building' | 'running' | 'settled' | 'frozen'

export interface SolverHandles {
  status: SolverStatus
  simError: string | null
  /** 最近一次缝合误差读数（worker 每 10 帧/停走时上报；-1 = 本帧未算） */
  seamErr: { avg: number; p95: number } | null
  /** settled 是否为封顶兜底帧（非真静止；UI 提示用） */
  capped: boolean
  /** 注册每帧回调（worker 帧到达时调用；视图渲染挂这里） */
  onFrame: (cb: (pos: Float32Array) => void) => () => void
  /** 冷启动重解算（「重新悬挂」；后续参数变化恢复热启） */
  restart: () => void
}

export function useGarment(
  fitting: Snapshot<FittingResult> | null,
): SolverHandles {
  const [status, setStatus] = useState<SolverStatus>('idle')
  const [simError, setSimError] = useState<string | null>(null)
  const [seamErr, setSeamErr] = useState<{ avg: number; p95: number } | null>(null)
  const [capped, setCapped] = useState(false)
  const [restartTick, setRestartTick] = useState(0)
  const forceCold = useRef(false)
  const listeners = useRef(new Set<(pos: Float32Array) => void>())

  useEffect(() => {
    if (!fitting) {
      setStatus('idle')
      return
    }
    setStatus('building')
    setSimError(null)
    setCapped(false)
    let stale = false
    const w = new Worker(
      new URL('./worker/entry.ts', import.meta.url), { type: 'module' })
    w.onmessage = (ev: MessageEvent<FromWorker>) => {
      if (stale) return
      const m = ev.data
      if (m.type === 'ready') {
        setStatus('running')
      } else if (m.type === 'frame') {
        for (const cb of listeners.current) cb(m.pos)
        if (m.seamErrAvg >= 0) setSeamErr({ avg: m.seamErrAvg, p95: m.seamErrP95 })
        if (m.status !== 'running') {
          setStatus(m.status)
          setCapped(m.capped)
        }
      } else {
        setSimError(m.message)
        setStatus('idle')
      }
    }
    w.onerror = (e) => {
      if (stale) return
      setSimError(String(e.message ?? 'sim worker 加载失败'))
      setStatus('idle')
    }
    const msg: ToWorker = {
      type: 'init',
      payload: fitting.data,
      cold: forceCold.current,
      // 悬挂展示 2026-09-14 起唯一模式（穿台模拟退役，代码留档不触发）
      hang: true,
    }
    forceCold.current = false
    w.postMessage(msg)
    return () => {
      stale = true
      w.terminate()
    }
  }, [fitting, restartTick])

  const onFrame = useCallback((cb: (pos: Float32Array) => void) => {
    listeners.current.add(cb)
    return () => { listeners.current.delete(cb) }
  }, [])

  const restart = useCallback(() => {
    forceCold.current = true
    setRestartTick((t) => t + 1)
  }, [])

  return { status, simError, seamErr, capped, onFrame, restart }
}
