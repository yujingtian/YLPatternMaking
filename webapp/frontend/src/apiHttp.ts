import type {
  AdjustResult, DraftPayload, FittingResult, IssueDetail, MsMachineConfig,
  MsResult, MsSolveStart, MsStatus, NestResult,
  PiecesResult, Schema, SeedPayload, SeedResult, SheetResult, Values,
} from './types'
import type { ExtractResponse } from './types'
import { AGENT_BASE } from './agentConfig'
import { MS_BASE } from './msBase'
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

// 3D 试穿 payload（§10.11）：前后片净样边链（整版全局坐标）+ 站点 +
// 腰头标量；2026-09-13 二期复活（前端消费恢复，引擎端点原样闲置）
export async function postFitting(payload: DraftPayload): Promise<FittingResult> {
  return handle(await fetch('/api/draft/fitting', {
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

// 二进制内存直存（排料 DXF：/api/nest JSON 里的 base64 解码成字节后落盘），
// 与 downloadBlob 同款 blob + a[download]。形参收窄 Uint8Array<ArrayBuffer>：
// TS 5.7 起 BlobPart 不再接受 ArrayBufferLike（atob/Uint8Array.from 均产此型）
export function downloadBlobBytes(
  data: Uint8Array<ArrayBuffer>, filename: string,
  mime = 'application/dxf',
): void {
  const url = URL.createObjectURL(new Blob([data], { type: mime }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// 排料对接（POST /api/nest，§10.3.2）：带 g 码编号 DXF（file=base64）+
// numMap 数量契约。422 detail 双形态（字符串=推板码号非纯数字等 |
// IssueDetail[]=参数校验），归一成可读消息——排料侧码号错误用户要能看懂
export async function postNest(payload: DraftPayload): Promise<NestResult> {
  const res = await fetch('/api/nest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    if (res.status === 422 && body) {
      const detail: unknown = body.detail
      throw new Error(typeof detail === 'string' ? detail
        : Array.isArray(detail)
          ? detail.map((d: IssueDetail) =>
            `${d.param ? `${d.param}: ` : ''}${d.message}`).join('；')
          : '参数校验失败')
    }
    throw new Error(`${res.status} ${await res.text()}`)
  }
  return res.json() as Promise<NestResult>
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

// ---- MS 机器排料六端点（/ms 前缀；dev=Vite proxy、prod=backend httpx 转发） ----
// 纯 HTTP（求解/轮询/取果/停止/PLT 导出全在 MS 服务侧，Pyodide 不做排料），
// 同 postNest 先例不进 route() 引擎通道。错误体两形态：MS {'error': 中文}
//（solve 409 重复提交另带 task_id）、YL /ms 代理 {'detail': 中文}（502）——
// normalizeMsError 归一成可读中文；网络级失败是原生 TypeError（不归一），
// 由调用方（useNestSolve）按「可重试」处理。

// MS 错误归一产物：带 HTTP status（404/400 等不可重试判定用）与 409 带回的
// 既有 task_id（幂等冲突提示用）
export interface MsError extends Error {
  status: number
  taskId?: string
}

// status 兜底文案：仅在错误体缺失/非字符串时启用（MS 侧消息本就是可读
// 中文，优先透传）
const MS_ERROR_FALLBACK: Record<number, string> = {
  400: '请求无效（载荷或参数不合法）',
  401: 'MS 认证失败（服务端已启用 X-Machine-Token 认证）',
  404: '任务不存在或已被清理（可能已删除或 MS 服务重启）',
  409: '任务冲突（重复提交或运行尚未结束）',
  413: '母版 DXF 超过大小上限（20MB）',
  422: '母版 DXF 解析失败',
  502: 'MS 排料服务未启动或不可达',
}

export function normalizeMsError(status: number, body: unknown): MsError {
  const b = typeof body === 'object' && body !== null
    ? body as Record<string, unknown> : {}
  const raw = typeof b.error === 'string' && b.error ? b.error
    : typeof b.detail === 'string' && b.detail ? b.detail : null
  const err = new Error(raw ?? MS_ERROR_FALLBACK[status]
    ?? `MS 请求失败（HTTP ${status}）`) as MsError
  err.status = status
  if (typeof b.task_id === 'string' && b.task_id) err.taskId = b.task_id
  return err
}

// 五端点公共壳：非 2xx → 错误体归一抛 MsError
async function msJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${MS_BASE}${path}`, init)
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw normalizeMsError(res.status, body)
  }
  return res.json() as Promise<T>
}

// 提交求解（POST /api/machine/solve → 202 {task_id, run_name, started_at}）：
// multipart file（母版 DXF 字节，filename 保留 .dxf 后缀——MS 侧校验）+
// config（JSON 字符串，client_ref 由提交层 useNestSolve 追加）。勿手设
// Content-Type（浏览器补 multipart boundary，代理透传依赖它）
export async function msSolveStart(
  file: Blob, filename: string,
  config: MsMachineConfig & { client_ref?: string },
): Promise<MsSolveStart> {
  const form = new FormData()
  form.append('file', file, filename)
  form.append('config', JSON.stringify(config))
  return msJson<MsSolveStart>('/api/machine/solve', { method: 'POST', body: form })
}

// 状态轮询（GET .../status：控载荷 {state, incumbent, current, per_seed, …}）
export async function msStatus(taskId: string): Promise<MsStatus> {
  return msJson<MsStatus>(
    `/api/machine/solve/${encodeURIComponent(taskId)}/status`)
}

// 终态取果（GET .../result：{manifest, best, summary}；running → 409）
export async function msResult(taskId: string): Promise<MsResult> {
  return msJson<MsResult>(
    `/api/machine/solve/${encodeURIComponent(taskId)}/result`)
}

// 终止（POST .../stop：在飞树杀 → {'stopped': true, pid}；orphan marker
// 清理带 orphan: true；已终态 400）
export async function msStop(
  taskId: string,
): Promise<{ stopped: boolean; pid: number | null; orphan?: boolean }> {
  return msJson(`/api/machine/solve/${encodeURIComponent(taskId)}/stop`,
    { method: 'POST' })
}

// 任务清理（DELETE .../solve/{task_id}）：结果期显式关闭时 best-effort
// 回收 MS 会话名额（并发任务上限）——失败由调用方静默，MS 侧 TTL+7 天
// 兜底；非 2xx 仍走 normalizeMsError 抛 MsError（调用方 catch 吞掉）
export async function msDeleteTask(taskId: string): Promise<void> {
  const res = await fetch(
    `${MS_BASE}/api/machine/solve/${encodeURIComponent(taskId)}`,
    { method: 'DELETE' })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw normalizeMsError(res.status, body)
  }
}

// PLT 导出（POST /api/machine/export）：请求体仅 {task_id}——fmt 缺省
// plt-clean、表格缺省服务端全算（零格式/表格参数，全在 MS 侧烘焙）；返回
// blob + 文件名（Content-Disposition 优先，ASCII/UTF-8 双形态；缺头本地
// 合成）。落盘时机由调用方（结果区「下载 PLT」按钮）决定
export async function msExport(
  taskId: string,
): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(`${MS_BASE}/api/machine/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_id: taskId }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw normalizeMsError(res.status, body)
  }
  return { blob: await res.blob(), filename: exportFilename(res, taskId) }
}

// Content-Disposition 文件名解析：RFC 5987 filename*=UTF-8''<pct-encoded>
// 优先（中文真名）、退 filename="..."（ASCII）——MS 侧中文/ASCII 双写同款
function exportFilename(res: Response, taskId: string): string {
  const cd = res.headers.get('content-disposition')
  if (cd) {
    const star = /filename\*=(?:UTF-8|utf-8)''([^;\s]+)/.exec(cd)
    if (star) {
      try { return decodeURIComponent(star[1]) } catch { /* 坏编码走回落 */ }
    }
    const plain = /filename="([^"]+)"/.exec(cd)
    if (plain) return plain[1]
  }
  return `yl-nest-${taskId}.plt`
}
