// 智能打版对话状态机（二期前端接线 §10.9.2）：多轮会话核心。
// 挂 DraftApp 顶层——界面关开状态不丢（中途关掉重开继续、照片/消息/会话
// 全在）；跨启动 localStorage 持久化本期不做（照片本体在 IndexedDB 的
// 口径留后续）。职责：session JSON 串往返（响应对象存 ref，每轮
// stringify）、消息流、照片待提交池（**提交成功即清空**，用户口径
// 2026-09-24：已识别证据在会话 vlm_cache，后续轮零照片安全；会话上限
// 4 张按「池内待提交 + 累计已提交」计）、健康预检、busy 互斥与秒表。
// 输入文本归组件所有（send 成功才由组件清输入框）；确认预填载荷由
// confirmPrefill 返回、App 层调 loadValues（须显式传 d.sizeRun）。
import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchAgentHealth, postChatTurn } from '../api'
import {
  buildChatForm, deliveryToPrefill, type ChatError,
} from '../chatPayload'
import type { ChatCard, ChatDelivery, Values } from '../types'

// 照片池条目（objectURL 生命周期归本 hook：手动 remove/reset/卸载才
// revoke，**提交清池不 revoke**——历史 user 气泡缩略还引用着同一 URL；
// 全量登记进 allUrlsRef，reset/卸载统一回收）
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
  photos: PhotoItem[]            // 待提交池（send 成功即清空）
  sentPhotoCount: number         // 累计已提交照片数（与池共用 4 张会话上限）
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
  const [sentPhotoCount, setSentPhotoCount] = useState(0)
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
  const photosRef = useRef<PhotoItem[]>([])   // send 快照/卸载兜底 revoke 用
  photosRef.current = photos
  // 全量 objectURL 登记（含已提交清池的）：提交清池不 revoke（历史气泡
  // 还引用），reset/卸载统一回收防泄漏
  const allUrlsRef = useRef<Set<string>>(new Set())

  const stopTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  // 卸载兜底：秒表 + objectURL 全量回收（含已提交清池的——allUrls 登记）
  useEffect(() => () => {
    stopTimer()
    for (const u of allUrlsRef.current) URL.revokeObjectURL(u)
    allUrlsRef.current.clear()
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

    // 本轮新增照片快照进 user 气泡（url 字符串；提交清池不 revoke，
    // 历史缩略长期有效——手动 removePhoto 才会裂，删了就是删了）
    const newUrls = photosRef.current
      .filter((p) => newUidsRef.current.has(p.uid))
      .map((p) => p.url)
    appendMsg({
      id: ++idRef.current, role: 'user',
      text, photoUrls: newUrls,
    })
    const turnPhotoCount = photosRef.current.length   // 本轮随发的池全量

    try {
      const res = await postChatTurn(buildChatForm(
        sessionRef.current, text, photosRef.current.map((p) => p.file),
        { thinking },
      ))
      stopTimer()
      sessionRef.current = res.session
      newUidsRef.current.clear()
      // 照片提交成功即清空上传池（用户口径 2026-09-24）：证据已入会话
      // vlm_cache（指纹+观测），后续轮零照片安全；objectURL 不 revoke
      // （历史气泡引用着），reset/卸载统一回收
      setPhotos([])
      setSentPhotoCount((n) => n + turnPhotoCount)
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
    allUrlsRef.current.add(item.url)
    setPhotos((prev) => [...prev, item])
  }, [])

  // 手动移除（仅池内待提交照片可移）：revoke 立即回收，历史气泡缩略
  // 随之失效（删了就是删了）；不撤销后端 vlm_cache 已识别证据
  const removePhoto = useCallback((uid: string) => {
    setPhotos((prev) => {
      const hit = prev.find((p) => p.uid === uid)
      if (hit) {
        URL.revokeObjectURL(hit.url)
        allUrlsRef.current.delete(hit.url)
      }
      newUidsRef.current.delete(uid)
      return prev.filter((p) => p.uid !== uid)
    })
  }, [])

  const confirmPrefill = useCallback((d: ChatDelivery) => deliveryToPrefill(d), [])

  const reset = useCallback(() => {
    stopTimer()
    busyRef.current = false
    setMessages([])
    for (const u of allUrlsRef.current) URL.revokeObjectURL(u)
    allUrlsRef.current.clear()
    setPhotos([])
    setSentPhotoCount(0)
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
    open, setOpen, messages, photos, sentPhotoCount, busy, elapsed,
    health, healthLoading, thinking, setThinking,
    send, addPhoto, removePhoto, confirmPrefill, reset,
  }
}
