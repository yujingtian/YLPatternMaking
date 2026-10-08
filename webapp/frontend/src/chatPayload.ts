// 智能打版对话壳纯逻辑层（二期前端接线 §10.9.2，无 React/DOM 依赖，
// vitest 直测；FormData/File 走 Node ≥20 原生实现）。契约对齐
// agent/converse.py + agent/app.py POST /api/chat/turn：
//   Form session（JSON 串，首轮 '{}'）/text/photos 多值/thinking/run_probe/
//   run_score/max_refeed → {ok, session, card, delivery}；card/delivery 二选一；
//   错误 422=照片非法串 / 400=会话 JSON 非法 / 503=VLM；**缺必填不 422 转
//   求援卡**（无 issues 形态，故不与 normalizeExtractError 共用）。
import type { ChatDelivery, PhotoMetaItem, Values } from './types'

// ---- 会话串往返（最易踩：响应 session 是对象、请求要串） ----

// null/undefined/空对象 → '{}'（首轮）；对象 → JSON.stringify。
// 后端 Session.from_json 收串，单点收口防止散落各处手写
export function sessionToJson(session: unknown): string {
  if (session === null || session === undefined) return '{}'
  return JSON.stringify(session)
}

// ---- 请求组装 ----

export interface ChatFormOpts {
  thinking?: string
  run_probe?: boolean
  run_score?: boolean
  max_refeed?: number
  // D 两段握手轮次 B（2026-09-29）：directive 响应后自动附类别照片续发
  fulfill?: 'recheck'
}

// 字段序 session/text/photos 多值/photo_meta/thinking（空白不附）；opts
// 键缺省不附（吃后端默认 true/true/2）。布尔串化为 'true'/'false'——
// FastAPI Form(bool) 可析（金标钉死，防将来误改成因按钮）。
// photoMeta（C 照片三类，2026-09-29）：[{name, category, note}] JSON 串、
// 与 photos 按序对齐；无照片/未传不附（后端 None -> 旧行为）
export function buildChatForm(
  session: unknown, text: string, photos: File[], opts?: ChatFormOpts,
  photoMeta?: PhotoMetaItem[],
): FormData {
  const form = new FormData()
  form.append('session', sessionToJson(session))
  form.append('text', text)
  for (const p of photos) form.append('photos', p)
  if (photos.length > 0 && photoMeta && photoMeta.length > 0) {
    form.append('photo_meta', JSON.stringify(photoMeta))
  }
  if (opts?.thinking && opts.thinking.trim()) {
    form.append('thinking', opts.thinking.trim())
  }
  if (opts?.run_probe !== undefined) form.append('run_probe', String(opts.run_probe))
  if (opts?.run_score !== undefined) form.append('run_score', String(opts.run_score))
  if (opts?.max_refeed !== undefined) form.append('max_refeed', String(opts.max_refeed))
  if (opts?.fulfill) form.append('fulfill', opts.fulfill)
  return form
}

// ---- 错误归一（postChatTurn 抛出形态；对话错误口径独立于 extract） ----

export interface ChatError {
  kind: 'text'
  message: string
}

export function normalizeChatError(status: number, detail: unknown): ChatError {
  if (typeof detail === 'string' && detail) {
    return { kind: 'text', message: detail }
  }
  if (status === 400) {
    // 会话 JSON 非法（app.py 400）：不吓用户，引导重开
    return { kind: 'text', message: '会话状态异常，请点「重新开始」重开对话' }
  }
  if (status === 503) {
    return { kind: 'text', message: 'VLM 未配置或调用失败（vlm.toml / 上游服务）' }
  }
  return { kind: 'text', message: `对话失败（HTTP ${status}）` }
}

// ---- delivery 适配 ----

// 语义同 extractPayload.toPrefillPayload（浅拷贝，改返回值不污染 delivery）
export function deliveryToPrefill(
  d: ChatDelivery,
): { measurements: Values; options: Values } {
  return { measurements: { ...d.measurements }, options: { ...d.options } }
}

// 交卷摘要行（交卷卡 meta 行 + 历史 delivery 折叠展示）：
// '第 N 轮交卷 · 模型 X · 照片 N 张 · 调版 n 键 · 回退 n 项/低置信 n 项/评分警告 n 项'
// （计数为 0 的段省略）
export function deliverySummaryLine(d: ChatDelivery): string {
  const parts = [
    `第 ${d.summary.turn} 轮交卷`,
    `模型 ${d.summary.model}`,
    `照片 ${d.summary.photo_count} 张`,
  ]
  if (d.adjust && d.adjust.applied.length > 0) {
    parts.push(`调版 ${d.adjust.applied.length} 键`)
  }
  if (d.recheck && d.recheck.diff.length > 0) {
    parts.push(`复查 ${d.recheck.diff.length} 处`)
  }
  const review = d.review
  if (review.reverted.length > 0) parts.push(`回退 ${review.reverted.length} 项`)
  if (review.low_confidence.length > 0) {
    parts.push(`低置信 ${review.low_confidence.length} 项`)
  }
  if (review.score_warnings.length > 0) {
    parts.push(`评分警告 ${review.score_warnings.length} 项`)
  }
  if ((review.balance_guard ?? []).length > 0) {
    parts.push(`侧缝守卫 ${review.balance_guard.length} 项`)
  }
  return parts.join(' · ')
}

// 侧缝守卫披露（2026-09-29 A5）：review.balance_guard 全句拼接
// （waist_balance 自动抬回轨迹 / 调版亲说只量不改）；未触发轮为空串，
// 调用方非空才渲染；?? [] 兼容旧会话缺键
export function balanceNotes(d: ChatDelivery): string {
  return (d.review?.balance_guard ?? []).join('；')
}

// 调版 note（映射节点一句话披露：动了哪些/最佳猜测依据/回退说明）；
// 无调版轮 delivery 无 adjust 键 -> 空串（调用方非空才渲染）
export function adjustNote(d: ChatDelivery): string {
  return d.adjust?.note ?? ''
}

// 复查 diff 披露行（D，2026-09-29）：逐条「key old -> new（evidence）」；
// 旧值 null 显示「（未判断）」；非复查轮空数组（调用方按 length 渲染）
export function recheckDiffLines(d: ChatDelivery): string[] {
  const fmt = (v: unknown): string =>
    v === null || v === undefined ? '（未判断）'
      : typeof v === 'boolean' ? (v ? '开' : '关')
        : String(v)
  return (d.recheck?.diff ?? []).map(
    (r) => `${r.key} ${fmt(r.old)} -> ${fmt(r.new)}（${r.evidence}）`)
}

// 复查结论一句话（映射注语 + diff 摘要）；非复查轮空串
export function recheckNote(d: ChatDelivery): string {
  return d.recheck?.note ?? ''
}

// 思考段文本（2026-10-08 折叠展示用）：复查轮优先（复查时 S2 未跑、
// delivery.reasoning 恒空），常规轮取 S2 草稿；快速模式/旧会话缺键
// 回退空串（调用方非空才渲染折叠块）
export function reasoningText(d: ChatDelivery): string {
  return d.recheck?.reasoning || d.reasoning || ''
}
