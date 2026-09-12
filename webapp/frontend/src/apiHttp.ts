import type {
  AdjustResult, DraftPayload, IssueDetail, PiecesResult,
  Schema, SeedPayload, SeedResult, SheetResult, Values,
} from './types'
import type { ExtractResponse } from './types'
import { AGENT_BASE } from './agentConfig'
import { normalizeExtractError } from './extractPayload'

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 422) {
    const body = await res.json()
    const err = new Error('参数校验失败') as Error & { detail: IssueDetail[] }
    err.detail = body.detail
    throw err
  }
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

export async function fetchSchema(): Promise<Schema> {
  return handle(await fetch('/api/schema'))
}

export async function postSheet(payload: DraftPayload): Promise<SheetResult> {
  return handle(await fetch('/api/draft/sheet', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export async function postPieces(payload: DraftPayload): Promise<PiecesResult> {
  return handle(await fetch('/api/draft/pieces', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

// 拖拽反解（二期双向绑定）：目标坐标 cm -> 参数值；stateless，
// 引擎护栏内不抛错（钳制/no_effect 也 200，前端按 reason 显示钳制态）
export async function postAdjust(
  payload: DraftPayload & {
    element: string
    param: string
    axis: string
    target: number
  },
): Promise<AdjustResult> {
  return handle(await fetch('/api/adjust', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

// 从形态导入（贴袋 custom 编辑器）：预设形态 -> custom 初始角点/边；
// 纯函数毫秒级；422 detail 为字符串消息（非法 kind/shape/尺寸）
export async function postSeed(payload: SeedPayload): Promise<SeedResult> {
  return handle(await fetch('/api/seed', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

// DXF/toml 走 blob 下载（同 payload 重新打版，服务端无状态）
export async function download(
  endpoint: string, payload: DraftPayload, filename: string,
): Promise<void> {
  const res = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// 内存内容直存文件（无 HTTP，2026-09-11 导出中心）：整版/裁片 SVG 与
// 打版报表来自内存快照（本地引擎可出、零后端），与 download() 同款
// blob + a[download]
export function downloadBlob(
  content: string, filename: string,
  mime = 'text/plain;charset=utf-8',
): void {
  const url = URL.createObjectURL(new Blob([content], { type: mime }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export interface Template {
  name: string
  file: string
}

export async function fetchTemplates(): Promise<Template[]> {
  return handle(await fetch('/api/templates'))
}

export async function fetchTemplateDetail(
  file: string,
): Promise<{ measurements: Values; options: Values; size_run?: unknown }> {
  return handle(await fetch(`/api/templates/${file}`))
}

// ---- agent 提取服务（/agent 前缀；dev=Vite proxy、prod=backend 转发） ----

// agent /api/extract 的 422 detail 是双形态（字符串=照片非法 |
// [{param,message,level}]=缺必填清单），与 handle<T> 硬编码的
// IssueDetail[] 口径不同，不能复用——错误经 normalizeExtractError 归一
export async function postExtract(form: FormData): Promise<ExtractResponse> {
  const res = await fetch(`${AGENT_BASE}/api/extract`,
    { method: 'POST', body: form })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw normalizeExtractError(res.status, body?.detail)
  }
  return res.json() as Promise<ExtractResponse>
}

// agent 健康预检：网络失败/非 200 返回 null（= 服务未启动），不抛错
// ——调用方据此禁用提交但不禁输入
export async function fetchAgentHealth(): Promise<{
  status: string; vlm_configured: boolean
} | null> {
  try {
    const res = await fetch(`${AGENT_BASE}/healthz`)
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}
