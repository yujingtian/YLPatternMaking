// 智能打版对话状态机（二期前端接线 §10.9.2）：多轮会话核心。
// 挂 DraftApp 顶层——弹层关开状态不丢（中途关掉重开继续、照片/消息/会话
// 全在）；跨启动 localStorage 持久化本期不做（照片本体在 IndexedDB 的
// 口径留后续）。职责：session JSON 串往返（响应对象存 ref，每轮
// stringify）、消息流、照片全量池（每轮全量重发，后端 sha256 指纹去重
// 只送新照片进 VLM）、健康预检、busy 互斥与秒表。
// 输入文本归组件所有（send 成功才由组件清输入框）；确认预填载荷由
// confirmPrefill 返回、App 层调 loadValues（须显式传 d.sizeRun）。
import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchAgentHealth, postChatTurn } from '../api'
import {
  buildChatForm, deliveryToPrefill, type ChatError,
} from '../chatPayload'
import type { ChatCard, ChatDelivery, Values } from '../types'

// 照片池条目（objectURL 生命周期归本 hook：remove/reset 才 revoke，
// 弹层关开不释放；卸载兜底全池回收）
export interface PhotoItem {
  uid: string
  name: string
  url: string
  file: File
}

// 对话消息（UI 层结构，不进 types.ts）
export type ChatMsg =
  | { id: number; role: 'user'; text: string; photoUrls: string[] }
  | { id: number; role: 'agent'; kind: 'card'; turn: number; card: ChatCard }
  | { id: number; role: 'agent'; kind: 'deliver'; turn: number; delivery: ChatDelivery }
  | { id: number; role: 'agent'; kind: 'error'; message: string }

interface AgentHealth {
  status: string
  vlm_configured: boolean
}

export interface SmartDraftState {
  open: boolean
  setOpen: (v: boolean) => void
  messages: ChatMsg[]
  photos: PhotoItem[]            // 会话全量池（跨轮持有、每轮全量重发）
  busy: boolean                  // 一轮进行中（锁发送/加照片/关层）
  elapsed: number                // 本轮已耗时（秒）
  health: AgentHealth | null     // null = agent 未启动/未知
  healthLoading: boolean
  thinking: string
  setThinking: (v: string) => void
  // 成功才 true（组件据此清输入框）；失败消息内联、输入未清可重发
  send: (text: string) => Promise<boolean>
  addPhoto: (item: PhotoItem) => void   // 满 MAX_PHOTOS 由组件拦
  removePhoto: (uid: string) => void
  confirmPrefill: (d: ChatDelivery) => { measurements: Values; options: Values }
  reset: () => void              // 「重新开始」：清消息/会话/照片 + 重检健康
}

export function useSmartDraft(): SmartDraftState {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [photos, setPhotos] = useState<PhotoItem[]>([])
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [health, setHealth] = useState<AgentHealth | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [thinking, setThinking] = useState('')

  // 响应 session 对象（大 JSON 不进 state，避免每轮整串触发渲染）；
  // 首轮 null -> sessionToJson 出 '{}'
  const sessionRef = useRef<unknown>(null)
  // 待随下一轮「发出」的照片 uid（addPhoto 记入；send 成功快照进 user
  // 消息后清空——气泡只显本轮新增，全量池在输入区 Upload 展示；
  // **失败不清**：照片仍算未发出，下轮带上）
  const newUidsRef = useRef<Set<string>>(new Set())
  const idRef = useRef(0)
  const busyRef = useRef(false)   // send 闭包互斥（state 异步不可靠）
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const photosRef = useRef<PhotoItem[]>([])   // 卸载兜底 revoke 用
  photosRef.current = photos

  const stopTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  // 卸载兜底：秒表 + objectURL 全池回收
  useEffect(() => () => {
    stopTimer()
    for (const p of photosRef.current) URL.revokeObjectURL(p.url)
  }, [stopTimer])

  // 弹层每次打开重检健康（服务可能中途启停）
  useEffect(() => {
    if (!open) return
    let alive = true
    setHealthLoading(true)
    fetchAgentHealth().then((h) => {
      if (alive) {
        setHealth(h)
        setHealthLoading(false)
      }
    })
    return () => { alive = false }
  }, [open])

  const appendMsg = useCallback((m: ChatMsg) => {
    setMessages((prev) => [...prev, m])
  }, [])

  const send = useCallback(async (text: string) => {
    if (busyRef.current) return false   // 轮次门控互斥
    busyRef.current = true
    setBusy(true)
    setElapsed(0)
    stopTimer()
    timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000)

    // 本轮新增照片快照进 user 气泡（url 字符串；removePhoto revoke 后
    // 历史缩略会裂——池在输入区可见，删了就是删了，保历史图留位不做）
    const newUrls = photosRef.current
      .filter((p) => newUidsRef.current.has(p.uid))
      .map((p) => p.url)
    appendMsg({
      id: ++idRef.current, role: 'user',
      text, photoUrls: newUrls,
    })

    try {
      const res = await postChatTurn(buildChatForm(
        sessionRef.current, text, photosRef.current.map((p) => p.file),
        { thinking },
      ))
      stopTimer()
      sessionRef.current = res.session
      newUidsRef.current.clear()
      if (res.card) {
        appendMsg({
          id: ++idRef.current, role: 'agent', kind: 'card',
          turn: -1, card: res.card,
        })
      } else if (res.delivery) {
        appendMsg({
          id: ++idRef.current, role: 'agent', kind: 'deliver',
          turn: res.delivery.summary.turn, delivery: res.delivery,
        })
      }
      busyRef.current = false
      setBusy(false)
      return true
    } catch (e) {
      stopTimer()
      // postChatTurn 抛的是 normalizeChatError 结果（含 400 引导重开文案）
      const err = e as ChatError & Error
      appendMsg({
        id: ++idRef.current, role: 'agent', kind: 'error',
        message: err && typeof err === 'object' && err.kind
          ? err.message : String(e),
      })
      busyRef.current = false
      setBusy(false)
      return false   // 输入不清、照片未发出标记不动、session 不动
    }
  }, [appendMsg, stopTimer, thinking])

  const addPhoto = useCallback((item: PhotoItem) => {
    newUidsRef.current.add(item.uid)
    setPhotos((prev) => [...prev, item])
  }, [])

  const removePhoto = useCallback((uid: string) => {
    setPhotos((prev) => {
      const hit = prev.find((p) => p.uid === uid)
      if (hit) URL.revokeObjectURL(hit.url)
      newUidsRef.current.delete(uid)
      return prev.filter((p) => p.uid !== uid)
    })
  }, [])

  const confirmPrefill = useCallback((d: ChatDelivery) => deliveryToPrefill(d), [])

  const reset = useCallback(() => {
    stopTimer()
    busyRef.current = false
    setMessages([])
    for (const p of photosRef.current) URL.revokeObjectURL(p.url)
    setPhotos([])
    newUidsRef.current.clear()
    sessionRef.current = null
    setBusy(false)
    setElapsed(0)
    setHealthLoading(true)
    void fetchAgentHealth().then((h) => {
      setHealth(h)
      setHealthLoading(false)
    })
  }, [stopTimer])

  return {
    open, setOpen, messages, photos, busy, elapsed,
    health, healthLoading, thinking, setThinking,
    send, addPhoto, removePhoto, confirmPrefill, reset,
  }
}
