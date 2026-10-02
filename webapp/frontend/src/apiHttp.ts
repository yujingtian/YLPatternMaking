import type {
  AdjustResult, DraftPayload, FittingResult, IssueDetail, MsMachineConfig,
  MsResult, MsSolveStart, MsStatus, NestResult,
  PiecesResult, Schema, SeedPayload, SeedResult, SheetResult, Values,
} from './types'
import type { ChatTurnResponse, ExtractResponse } from './types'
import { AGENT_BASE } from './agentConfig'
import { normalizeChatError } from './chatPayload'
import { MS_PROXY_BASE, demoteMsChannel, resolveMsChannel } from './msBase'
import type { MsChannel } from './msBase'
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

// 多轮对话一轮（智能打版二期 §10.9.2）：错误归一走 normalizeChatError
// （422 照片非法/400 会话非法/503 VLM；缺必填不 422 转 card，无 issues
// 形态——独立于 postExtract）。响应 session 是**对象**，调用方负责每轮
// stringify 回传（chatPayload.sessionToJson 单点收口）
export async function postChatTurn(form: FormData): Promise<ChatTurnResponse> {
  const res = await fetch(`${AGENT_BASE}/api/chat/turn`,
    { method: 'POST', body: form })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw normalizeChatError(res.status, body?.detail)
  }
  return res.json() as Promise<ChatTurnResponse>
}

// ---- MS 机器排料六端点（通道感知：direct 发现 base / proxy '/ms' 前缀）----
// 纯 HTTP（求解/轮询/取果/停止/PLT 导出全在 MS 服务侧，Pyodide 不做排料），
// 同 postNest 先例不进 route() 引擎通道。四期双通道 US-002：每请求经
// resolveMsChannel 取通道（会话缓存命中零网络成本）——direct → US-001
// 发现的 base（浏览器直连本地 MS）；proxy → '/ms'（dev=Vite proxy、
// prod=backend httpx 转发，现状路径零变化）。四期 US-003：七函数可选尾参
// channel = 任务级绑定通道（useNestSolve 锚定 task_id 所在通道，生命周期
// 请求/下载随绑定直发，零探测零降级——见 runMsRequest 注）。错误体两形态：
// MS {'error': 中文}（solve 409 重复提交另带 task_id）、YL /ms 代理
// {'detail': 中文}（502）——normalizeMsError 归一成可读中文；网络级失败是
// 原生 TypeError（不归一），由调用方（useNestSolve）按「可重试」处理
//（无绑定请求的直连 TypeError 先经降级兜底）。

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

// 通道分派 + 直连降级兜底（US-002 tasks/prd-machine-direct-channel.md）：
// attempt 收当前通道组请求（直连/代理两形态的 URL 或路径可不同，如
// msStateFile 的双端点分派），direct 的**网络级**失败（fetch TypeError：
// CORS/PNA 预检被拒、拒连、跨源响应被拦——JS 侧不可区分；「MS 版本过旧
// 无 ping」在探测层已天然归 miss 回退）在此归一为「回退 proxy」——先把
// 会话通道钉回 proxy（demoteMsChannel：半新半旧部署的后续请求不再各撞
// 一次死直连），同一请求再按 proxy 形态重发一次（multipart/JSON 体可
// 复用重发；不向用户抛裸网络错误，PRD AC#4）。proxy 形态无二次兜底
//（降级无更下去处）；非 TypeError（30s 超时 TimeoutError 等）不降级——
// 挂死是另一病理，照旧落到调用方连续失败计数。HTTP 非 2xx 不在此吞
//（含降级后 proxy 404 任务不存在）：各端点归一 MsError，由 useNestSolve
// 按 status 裁决。
// 显式 channel（US-003 任务级通道绑定）：任务生命周期请求带锚定的通道
// 直发——**零探测零降级**（降级 = 改判通道，任务绑定语义下「不自动切换」；
// direct 死连的 TypeError 原样上抛，由 useNestSolve 连续失败计数裁决成
// error 引导）。提交层的降级重试在 useNestSolve.submit 自理（要知道任务
// 实际落在哪个通道才能绑定）
async function runMsRequest(
  attempt: (channel: MsChannel) => Promise<Response>,
  channel?: MsChannel,
): Promise<Response> {
  if (channel) return attempt(channel)
  const resolved = await resolveMsChannel()
  if (resolved.kind === 'proxy') return attempt(resolved)
  try {
    return await attempt(resolved)
  } catch (e) {
    if (!(e instanceof TypeError)) throw e
    demoteMsChannel()
    return attempt({ kind: 'proxy' })
  }
}

// 通道化 URL：direct → 通道 base + 路径；proxy → '/ms' 同源代理前缀
function msUrl(channel: MsChannel, path: string): string {
  return channel.kind === 'direct' ? `${channel.base}${path}`
    : `${MS_PROXY_BASE}${path}`
}

// 五端点公共壳：非 2xx → 错误体归一抛 MsError；30s 超时兜底——裸 fetch
// 在连接建立但不响应（MS/代理挂死）时永不落定，轮询 failRef 不累计、
// 按钮永久卡「排料中」（2026-09-29 报障成因之三）；到点 abort 计一次
// 网络失败，连续 3 次自然转 error（与后端代理 status 30s 档对齐）。超时
// signal 在 attempt 回调内构造：降级重试各起各的 30s 窗
async function msJson<T>(
  path: string, init?: RequestInit, channel?: MsChannel,
): Promise<T> {
  const res = await runMsRequest((ch) =>
    fetch(msUrl(ch, path), { ...init, signal: AbortSignal.timeout(30_000) }),
    channel)
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
  channel?: MsChannel,
): Promise<MsSolveStart> {
  const form = new FormData()
  form.append('file', file, filename)
  form.append('config', JSON.stringify(config))
  return msJson<MsSolveStart>(
    '/api/machine/solve', { method: 'POST', body: form }, channel)
}

// 状态轮询（GET .../status：控载荷 {state, incumbent, current, per_seed, …}）
export async function msStatus(
  taskId: string, channel?: MsChannel,
): Promise<MsStatus> {
  return msJson<MsStatus>(
    `/api/machine/solve/${encodeURIComponent(taskId)}/status`, undefined,
    channel)
}

// 终态取果（GET .../result：{manifest, best, summary}；running → 409）
export async function msResult(
  taskId: string, channel?: MsChannel,
): Promise<MsResult> {
  return msJson<MsResult>(
    `/api/machine/solve/${encodeURIComponent(taskId)}/result`, undefined,
    channel)
}

// 终止（POST .../stop：在飞树杀 → {'stopped': true, pid}；orphan marker
// 清理带 orphan: true；已终态 400）
export async function msStop(
  taskId: string, channel?: MsChannel,
): Promise<{ stopped: boolean; pid: number | null; orphan?: boolean }> {
  return msJson(`/api/machine/solve/${encodeURIComponent(taskId)}/stop`,
    { method: 'POST' }, channel)
}

// 任务清理（DELETE .../solve/{task_id}）：结果期显式关闭时 best-effort
// 回收 MS 会话名额（并发任务上限）——失败由调用方静默，MS 侧 TTL+7 天
// 兜底；非 2xx 仍走 normalizeMsError 抛 MsError（调用方 catch 吞掉）
export async function msDeleteTask(
  taskId: string, channel?: MsChannel,
): Promise<void> {
  const res = await runMsRequest((ch) =>
    fetch(msUrl(ch, `/api/machine/solve/${encodeURIComponent(taskId)}`),
      { method: 'DELETE' }), channel)
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
  taskId: string, channel?: MsChannel,
): Promise<{ blob: Blob; filename: string }> {
  const res = await runMsRequest((ch) =>
    fetch(msUrl(ch, '/api/machine/export'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId }),
    }), channel)
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw normalizeMsError(res.status, body)
  }
  return {
    blob: await res.blob(),
    filename: cdFilename(res, `yl-nest-${taskId}.plt`),
  }
}

// .msn 状态文件下载（三期机器对接 US-002，tasks/prd-machine-state-file-yl.md；
// 四期双通道 US-002 起双通道分派——两形态端点不同，走 runMsRequest 通道化
// attempt 而非 msUrl）：
//   direct → MS 原生端点 GET {base}/api/machine/solve/{id}/state-file
//     （浏览器直连模式 MS 侧不设 token——CORS 白名单即访问边界）
//   proxy → YL 后端专用代理 GET /api/nest/tasks/{id}/state-file（现状零
//     改动；服务端注入 MS token，token 永不下发前端，三期 US-001 先例）
// 直连网络级失败同款降级（proxy 形态 = YL 端点重试）。blob 零解析（.msn
// 对前端是不透明字节流，不感知 MS schema 升级）；文件名与 msExport 共用
// cdFilename 解析器（Content-Disposition 优先，缺头本地合成
// yl-nest-{taskId}.msn）。错误体 {'detail': 中文}（US-001 映射文案）经
// normalizeMsError 原样透出不重写
export async function msStateFile(
  taskId: string, channel?: MsChannel,
): Promise<{ blob: Blob; filename: string }> {
  const id = encodeURIComponent(taskId)
  const res = await runMsRequest((ch) => fetch(
    ch.kind === 'direct'
      ? `${ch.base}/api/machine/solve/${id}/state-file`
      : `/api/nest/tasks/${id}/state-file`), channel)
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw normalizeMsError(res.status, body)
  }
  return {
    blob: await res.blob(),
    filename: cdFilename(res, `yl-nest-${taskId}.msn`),
  }
}

// Content-Disposition 文件名解析：RFC 5987 filename*=UTF-8''<pct-encoded>
// 优先（中文真名）、退 filename="..."（ASCII）——MS 侧中文/ASCII 双写同款；
// 缺头/坏编码回落调用方给的本地合成名（.plt/.msn 后缀随通道）
function cdFilename(res: Response, fallback: string): string {
  const cd = res.headers.get('content-disposition')
  if (cd) {
    const star = /filename\*=(?:UTF-8|utf-8)''([^;\s]+)/.exec(cd)
    if (star) {
      try { return decodeURIComponent(star[1]) } catch { /* 坏编码走回落 */ }
    }
    const plain = /filename="([^"]+)"/.exec(cd)
    if (plain) return plain[1]
  }
  return fallback
}
