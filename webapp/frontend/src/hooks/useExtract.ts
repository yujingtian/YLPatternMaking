// 提取向导状态机（一期前端接线 §10.9）：input -> submitting -> confirm。
// 输入内容（describe/photos/thinking）归向导组件所有，本 hook 只管阶段、
// 健康预检、结果与错误；不持 draft（confirmPrefill 返回载荷，由 App 层
// 调 loadValues —— 预填须显式传 d.sizeRun 保留推板配置，决策落 App）。
import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchAgentHealth, postExtract } from '../api'
import { toPrefillPayload, type ExtractError } from '../extractPayload'
import type { ExtractIssue, ExtractResponse, Values } from '../types'

type ExtractStage = 'input' | 'submitting' | 'confirm'

interface AgentHealth {
  status: string
  vlm_configured: boolean
}

interface ExtractErrorState {
  message: string
  issues?: ExtractIssue[]   // 422 缺必填清单（逐条展示白话名）
}

export interface ExtractState {
  stage: ExtractStage
  health: AgentHealth | null   // null = agent 未启动/未知
  healthLoading: boolean
  result: ExtractResponse | null
  error: ExtractErrorState | null
  elapsed: number              // 提交已耗时（秒，等待态展示）
  submit: (describe: string, photos: File[], thinking?: string) => Promise<void>
  backToInput: () => void      // 确认屏「返回修改」（输入由组件保留）
  confirmPrefill: () => { measurements: Values; options: Values } | null
  reset: () => void            // 关弹层清状态
}

export function useExtract(): ExtractState {
  const [stage, setStage] = useState<ExtractStage>('input')
  const [health, setHealth] = useState<AgentHealth | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [result, setResult] = useState<ExtractResponse | null>(null)
  const [error, setError] = useState<ExtractErrorState | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  // 卸载兜底（submitting 中关页面等场景）
  useEffect(() => stopTimer, [stopTimer])

  const checkHealth = useCallback(async () => {
    setHealthLoading(true)
    setHealth(await fetchAgentHealth())
    setHealthLoading(false)
  }, [])

  const reset = useCallback(() => {
    stopTimer()
    setStage('input')
    setResult(null)
    setError(null)
    setElapsed(0)
    void checkHealth()
  }, [checkHealth, stopTimer])

  const submit = useCallback(async (
    describe: string, photos: File[], thinking?: string,
  ) => {
    if (stage === 'submitting') return   // 阶段门控天然互斥
    const form = new FormData()
    form.append('describe', describe)
    for (const p of photos) form.append('photos', p)
    if (thinking && thinking.trim()) form.append('thinking', thinking.trim())
    setStage('submitting')
    setError(null)
    setElapsed(0)
    stopTimer()
    timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000)
    try {
      const res = await postExtract(form)
      stopTimer()
      setResult(res)
      setStage('confirm')
    } catch (e) {
      stopTimer()
      setStage('input')
      // postExtract 抛的是 normalizeExtractError 结果（ExtractError 对象）
      const err = e as ExtractError & Error
      if (err && typeof err === 'object' && err.kind) {
        setError({ message: err.message, issues: err.issues })
      } else {
        setError({ message: String(e) })
      }
    }
  }, [stage, stopTimer])

  const backToInput = useCallback(() => setStage('input'), [])

  const confirmPrefill = useCallback(
    () => (result === null ? null : toPrefillPayload(result)), [result])

  return {
    stage, health, healthLoading, result, error, elapsed,
    submit, backToInput, confirmPrefill, reset,
  }
}
