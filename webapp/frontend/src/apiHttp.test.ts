// apiHttp MS 段金标（vitest node env，fetch 全程 stub 不触网）：七函数
// URL/方法/载荷口径 + normalizeMsError 两形态归一 + 双通道跟随（US-002）+
// 显式通道任务级绑定（US-003：零探测零降级直发）+ archiveNest 回传存档
// （US-005）。ms* 函数无显式通道时每请求先 resolveMsChannel——每用例首轮
// 10 个 ping 探测调用混入 fetchMock，端点断言经 endpointCalls() 滤掉；
// 缺省用例走 proxy 形态（ping 全 miss → '/ms'，现状断言口径），direct
// 形态（ping 命中发现 base）与直连网络级失败降级（TypeError → demote +
// '/ms' 重试）各有专述 describe。vitest 无 VITE_MS_BASE 构建变量（探测必发）。
// 另含 postTomlParse（导入配置）：/api/toml/parse 的 URL/载荷与 422 归一。

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  archiveNest, msDeleteTask, msExport, msResult, msSolveStart, msStateFile,
  msStatus, msStop, normalizeMsError, postTomlParse,
} from './apiHttp'
import { resetMsChannelCache } from './msBase'
import type { NestArchiveMeta } from './nestArchive'
import type { MsMachineConfig, MsStatus } from './types'

const fetchMock = vi.fn()

beforeEach(() => {
  resetMsChannelCache()   // 会话通道缓存跨用例串台防线（msBase 先例）
})

afterEach(() => {
  fetchMock.mockReset()
  vi.unstubAllGlobals()
})

function stubFetch(impl: (url: string, init?: RequestInit) => unknown) {
  fetchMock.mockImplementation(impl)
  vi.stubGlobal('fetch', fetchMock)
}

// ---- 通道探测与端点请求的 stub 分流（US-002 起 ms* 先取通道再发请求）----

const isPing = (url: unknown): boolean =>
  typeof url === 'string' && url.endsWith('/api/machine/ping')

// 探测 ping 之外的端点请求（每用例恰一轮 10 ping，demote 后零新探测）
const endpointCalls = () =>
  fetchMock.mock.calls.filter(([url]) => !isPing(url))

// proxy 通道形态：ping 全 miss（连接拒绝）→ 通道回退 '/ms'（现状断言口径）
function stubProxy(impl: (url: string, init?: RequestInit) => unknown) {
  stubFetch((url, init) => (isPing(url)
    ? Promise.reject(new TypeError('Failed to fetch'))
    : impl(url, init)))
}

// direct 通道形态：仅 <base> 端口 ping 命中（端口序低口优先的发现语义
// 由 msBase.test 覆盖，此处钉单一命中口），端点请求交 impl
function stubDirect(
  base: string,
  impl: (url: string, init?: RequestInit) => unknown,
) {
  stubFetch((url, init) => {
    if (isPing(url)) {
      return url === `${base}/api/machine/ping`
        ? { ok: true, status: 200 }
        : Promise.reject(new TypeError('Failed to fetch'))
    }
    return impl(url, init)
  })
}

// 够用形状的成功/失败响应壳（本模块只消费 ok/status/json/blob/headers.get）
function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body }
}

function fail(status: number, body: unknown) {
  return { ok: false, status, json: async () => body }
}

const CONFIG: MsMachineConfig = {
  gate_mm: 1750,
  run_mode: 'normal',
  sizes: [29, 30],
  per_type: { g01: { d: 0, tol: 0 } },
  quantities: { g01: { 29: 2, 30: 2 } },
}

// 二进制附件响应壳（msExport PLT / msStateFile .msn 共用形状）：gzip 魔数
// 1f 8b 起头钉死「blob 零解析透传」口径（.msn 对前端不透明，严禁 text()
// 字符串通道在别处复活）；headers.get 仅服务 content-disposition
function okAttachment(cd: string | null, bytes = [0x1f, 0x8b, 0x08, 0x00]) {
  return {
    ok: true, status: 200,
    json: async () => ({}),
    blob: async () => new Blob([new Uint8Array(bytes)]),
    headers: { get: (k: string) => (k === 'content-disposition' ? cd : null) },
  }
}

describe('normalizeMsError（两形态归一 + status 兜底）', () => {
  it("MS 体 {'error'} 优先透传，status/taskId 挂载", () => {
    const err = normalizeMsError(409, {
      error: "client_ref 'yl-1' 已有在飞任务（task_id=m123）", task_id: 'm123',
    })
    expect(err.message).toBe("client_ref 'yl-1' 已有在飞任务（task_id=m123）")
    expect(err.status).toBe(409)
    expect(err.taskId).toBe('m123')
  })

  it("YL /ms 代理 502 体 {'detail'} 透传（无 task_id）", () => {
    const err = normalizeMsError(502, { detail: 'MS 排料服务未启动或不可达' })
    expect(err.message).toBe('MS 排料服务未启动或不可达')
    expect(err.status).toBe(502)
    expect(err.taskId).toBeUndefined()
  })

  it('体缺失/空串/非对象 → status 兜底中文', () => {
    expect(normalizeMsError(404, null).message)
      .toBe('任务不存在或已被清理（可能已删除或 MS 服务重启）')
    expect(normalizeMsError(404, {}).message).toContain('任务不存在')
    expect(normalizeMsError(409, { error: '' }).message).toContain('任务冲突')
    expect(normalizeMsError(502, 'plain-text').message)
      .toBe('MS 排料服务未启动或不可达')
  })

  it('未知 status → 通用兜底', () => {
    expect(normalizeMsError(418, null).message).toBe('MS 请求失败（HTTP 418）')
  })
})

describe('msSolveStart（multipart 口径）', () => {
  it('file + config 两字段；config JSON 含 client_ref；不手设 Content-Type', async () => {
    stubProxy(() => ok({ task_id: 'm1', run_name: 'machine_x', started_at: 't' }))
    const res = await msSolveStart(new Blob(['dxf']), 'nest_size_run.dxf',
      { ...CONFIG, client_ref: 'yl-ref-1' })
    expect(res.task_id).toBe('m1')
    const [url, init] = endpointCalls()[0]
    expect(url).toBe('/ms/api/machine/solve')
    expect(init.method).toBe('POST')
    expect(init.headers).toBeUndefined()   // multipart boundary 交给浏览器
    const form = init.body as FormData
    expect(form.get('config')).toBe(
      JSON.stringify({ ...CONFIG, client_ref: 'yl-ref-1' }))
    expect((form.get('file') as File).name).toBe('nest_size_run.dxf')
  })

  it('409 重复提交 → MsError 透传中文 + taskId', async () => {
    stubProxy(() => fail(409, {
      error: "client_ref 'x' 已有在飞任务（task_id=m9）", task_id: 'm9',
    }))
    await expect(msSolveStart(new Blob(['d']), 'n.dxf', CONFIG))
      .rejects.toMatchObject({
        status: 409,
        taskId: 'm9',
        message: expect.stringContaining('在飞任务'),
      })
  })

  it('MS 未启动（代理 502）→ detail 透传', async () => {
    stubProxy(() => fail(502, {
      detail: 'MS 排料服务未启动或不可达（默认 http://127.0.0.1:8010）',
    }))
    await expect(msSolveStart(new Blob(['d']), 'n.dxf', CONFIG))
      .rejects.toMatchObject({
        status: 502,
        message: 'MS 排料服务未启动或不可达（默认 http://127.0.0.1:8010）',
      })
  })
})

describe('msStatus / msStop / msResult（路径与方法）', () => {
  it('msStatus GET .../status，载荷透传', async () => {
    const st: MsStatus = {
      state: 'running', mode: 'machine', run_mode: 'normal',
      total_budget_sec: 180, elapsed_sec: 12,
      incumbent: {
        density: 0.8, width_mm: 9000, seed: 0, frame_index: 3, elapsed: 10,
      },
      current: null, per_seed: [], error: null, exit_code: null,
    }
    stubProxy(() => ok(st))
    expect(await msStatus('m1')).toEqual(st)
    const [url, init] = endpointCalls()[0]
    expect(url).toBe('/ms/api/machine/solve/m1/status')
    // 2026-09-29：msJson 恒带 30s 超时 signal（挂死连接兜底，别再裸 fetch）
    expect(init?.method).toBeUndefined()
    expect(init?.signal).toBeInstanceOf(AbortSignal)
    expect((init?.signal as AbortSignal).aborted).toBe(false)
  })

  it('taskId 特殊字符走 encodeURIComponent（路径安全闸）', async () => {
    stubProxy(() => fail(404, { error: '任务不存在' }))
    await expect(msStatus('a/b c')).rejects.toMatchObject({ status: 404 })
    expect(endpointCalls()[0][0])
      .toBe('/ms/api/machine/solve/a%2Fb%20c/status')
  })

  it('msStop POST .../stop，响应透传', async () => {
    stubProxy(() => ok({ stopped: true, pid: 123 }))
    expect(await msStop('m1')).toEqual({ stopped: true, pid: 123 })
    const [url, init] = endpointCalls()[0]
    expect(url).toBe('/ms/api/machine/solve/m1/stop')
    expect(init.method).toBe('POST')
  })

  it('msResult GET .../result；running 409 归一', async () => {
    stubProxy(() => fail(409, { error: '机器排料任务尚未结束' }))
    await expect(msResult('m1')).rejects.toMatchObject({
      status: 409, message: '机器排料任务尚未结束',
    })
    expect(endpointCalls()[0][0]).toBe('/ms/api/machine/solve/m1/result')
  })

  it('msDeleteTask DELETE .../solve/{id}（结果期关窗 best-effort 回收）', async () => {
    stubProxy(() => ok({ deleted: true }))
    await expect(msDeleteTask('m1')).resolves.toBeUndefined()
    const [url, init] = endpointCalls()[0]
    expect(url).toBe('/ms/api/machine/solve/m1')
    expect(init.method).toBe('DELETE')
    // 非 2xx 仍归一 MsError（调用方 catch 静默——MS 侧 TTL+7 天兜底）
    stubFetch(() => fail(404, { error: '任务不存在' }))
    await expect(msDeleteTask('m1')).rejects.toMatchObject({ status: 404 })
  })
})

describe('msExport（{task_id} 最小体 + 文件名解析）', () => {
  it('请求体仅 {task_id}；UTF-8 filename* 优先解码中文真名', async () => {
    stubProxy(() => okAttachment(
      'attachment; filename="nest_m1.plt"; '
      + "filename*=UTF-8''%E6%8E%92%E6%96%99.plt"))
    const res = await msExport('m1')
    expect(res.filename).toBe('排料.plt')
    const [url, init] = endpointCalls()[0]
    expect(url).toBe('/ms/api/machine/export')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ task_id: 'm1' })
  })

  it('仅 ASCII filename="…" 亦可用', async () => {
    stubProxy(() => okAttachment('attachment; filename="nest_m1.plt"'))
    expect((await msExport('m1')).filename).toBe('nest_m1.plt')
  })

  it('缺 Content-Disposition → 本地合成 yl-nest-{taskId}.plt', async () => {
    stubProxy(() => okAttachment(null))
    expect((await msExport('m9')).filename).toBe('yl-nest-m9.plt')
  })

  it('非 2xx → normalizeMsError（404 任务不存在）', async () => {
    stubProxy(() => fail(404, { error: '任务不存在（task_id=m9）' }))
    await expect(msExport('m9')).rejects.toMatchObject({
      status: 404, message: '任务不存在（task_id=m9）',
    })
  })
})

describe('msStateFile（proxy 通道 YL 代理端点 + .msn 文件名解析）', () => {
  it('GET /api/nest/tasks/{id}/state-file（YL 代理非 /ms 直连）；UTF-8 filename* 优先解码中文真名；blob 二进制原样透出', async () => {
    stubProxy(() => okAttachment('attachment; filename="machine_m1.msn"; '
      + "filename*=UTF-8''%E6%8E%92%E6%96%99.msn"))
    const res = await msStateFile('m1')
    expect(res.filename).toBe('排料.msn')
    expect(res.blob.size).toBe(4)
    const [url, init] = endpointCalls()[0]
    expect(url).toBe('/api/nest/tasks/m1/state-file')
    expect(init).toBeUndefined()   // 纯 GET：无方法/载荷/头
  })

  it('仅 ASCII filename="…" 亦可用；缺头 → 本地合成 yl-nest-{id}.msn', async () => {
    stubProxy(() => okAttachment('attachment; filename="machine_m1.msn"'))
    expect((await msStateFile('m1')).filename).toBe('machine_m1.msn')
    stubFetch(() => okAttachment(null))
    expect((await msStateFile('m9')).filename).toBe('yl-nest-m9.msn')
  })

  it('taskId 特殊字符走 encodeURIComponent（路径安全闸，同 msStatus）', async () => {
    stubProxy(() => fail(404, { detail: '任务不存在或已清理' }))
    await expect(msStateFile('a/b c')).rejects.toMatchObject({ status: 404 })
    expect(endpointCalls()[0][0])
      .toBe('/api/nest/tasks/a%2Fb%20c/state-file')
  })

  it('非 2xx → US-001 映射中文文案经 detail 原样透出（不重写）', async () => {
    stubProxy(() => fail(404, { detail: '任务不存在或已清理' }))
    await expect(msStateFile('m9')).rejects.toMatchObject({
      status: 404, message: '任务不存在或已清理',
    })
    stubFetch(() => fail(409, { detail: '任务数据已不可得，请重新提交排料' }))
    await expect(msStateFile('m9')).rejects.toMatchObject({
      status: 409, message: '任务数据已不可得，请重新提交排料',
    })
    stubFetch(() => fail(502, { detail: '排料服务暂不可用，请稍后重试' }))
    await expect(msStateFile('m9')).rejects.toMatchObject({
      status: 502, message: '排料服务暂不可用，请稍后重试',
    })
  })
})

describe('postTomlParse（导入配置 /api/toml/parse）', () => {
  it('POST JSON {text}；成功透传 measurements/options/size_run', async () => {
    stubFetch(() => ok({
      measurements: { waist: 68 }, options: { delta: 1.35 },
      size_run: { base: '30', order: ['30'], band: [] },
    }))
    const text = '[measurements]\nwaist = 68\n'
    const res = await postTomlParse(text)
    expect(res.measurements).toEqual({ waist: 68 })
    expect(res.options).toEqual({ delta: 1.35 })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/toml/parse')
    expect(init.method).toBe('POST')
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
    expect(JSON.parse(init.body as string)).toEqual({ text })
  })

  it('422 字符串 detail 原样透出（语法错/缺段可读）', async () => {
    stubFetch(() => fail(422, { detail: 'TOML 解析失败：坏文本' }))
    await expect(postTomlParse('x')).rejects.toThrow('TOML 解析失败：坏文本')
    stubFetch(() => fail(422, {
      detail: '缺少非空 [measurements] 段（不是有效的尺寸单）',
    }))
    await expect(postTomlParse('[options]'))
      .rejects.toThrow('缺少非空 [measurements] 段')
  })

  it('错误体不可解析 → HTTP 状态兜底中文', async () => {
    stubFetch(() => ({
      ok: false, status: 500,
      json: async () => { throw new Error('bad body') },
    }))
    await expect(postTomlParse('x')).rejects.toThrow('导入失败（HTTP 500）')
  })
})

describe('通道跟随（direct 发现 base，US-002）', () => {
  const BASE = 'http://127.0.0.1:8013'

  it('msSolveStart 走 {base}/api/machine/solve；multipart/30s 超时约定不变', async () => {
    stubDirect(BASE, () =>
      ok({ task_id: 'm1', run_name: 'machine_x', started_at: 't' }))
    const res = await msSolveStart(new Blob(['dxf']), 'nest_size_run.dxf', CONFIG)
    expect(res.task_id).toBe('m1')
    const [url, init] = endpointCalls()[0]
    expect(url).toBe(`${BASE}/api/machine/solve`)
    expect(init.method).toBe('POST')
    expect(init.headers).toBeUndefined()   // multipart boundary 交给浏览器
    expect(init.signal).toBeInstanceOf(AbortSignal)
  })

  it('msStatus/msStop/msResult/msDeleteTask/msExport 同款跟随（签名零改动）', async () => {
    stubDirect(BASE, (url) =>
      url.endsWith('/export') ? okAttachment(null) : ok({ stopped: true, pid: 1 }))
    await msStatus('m7')
    expect(endpointCalls()[0][0]).toBe(`${BASE}/api/machine/solve/m7/status`)
    await msStop('m7')
    expect(endpointCalls()[1][0]).toBe(`${BASE}/api/machine/solve/m7/stop`)
    await msResult('m7')
    expect(endpointCalls()[2][0]).toBe(`${BASE}/api/machine/solve/m7/result`)
    await msDeleteTask('m7')
    expect(endpointCalls()[3][0]).toBe(`${BASE}/api/machine/solve/m7`)
    expect((await msExport('m7')).filename).toBe('yl-nest-m7.plt')
    expect(endpointCalls()[4][0]).toBe(`${BASE}/api/machine/export`)
  })

  it('msStateFile direct → MS 原生端点 {base}/api/machine/solve/{id}/state-file（纯 GET 无 token 头）', async () => {
    stubDirect(BASE, () =>
      okAttachment('attachment; filename="machine_m1.msn"'))
    const res = await msStateFile('m1')
    expect(res.filename).toBe('machine_m1.msn')
    const [url, init] = endpointCalls()[0]
    expect(url).toBe(`${BASE}/api/machine/solve/m1/state-file`)
    expect(init).toBeUndefined()
  })
})

describe('直连网络级失败 → 降级 proxy（AC#4：归一为回退，不抛裸网络错误）', () => {
  const BASE = 'http://127.0.0.1:8013'

  // 直连尝试一律 TypeError（CORS/PNA 预检被拒、拒连 JS 侧同形态不可区分），
  // proxy 形态（'/ms' 或 YL 端点）按 impl 落定
  function stubDirectDead(proxyImpl: (url: string) => unknown) {
    stubDirect(BASE, (url) => (url.startsWith(`${BASE}/`)
      ? Promise.reject(new TypeError('Failed to fetch'))
      : proxyImpl(url)))
  }

  it('TypeError → demote + 同请求 /ms 重试成功；会话通道钉回 proxy（后续请求零新探测、直奔 /ms）', async () => {
    stubDirectDead(() => ok({ stopped: true, pid: 5 }))
    expect(await msStop('m1')).toEqual({ stopped: true, pid: 5 })
    expect(endpointCalls().map((c) => c[0])).toEqual([
      `${BASE}/api/machine/solve/m1/stop`,
      '/ms/api/machine/solve/m1/stop',
    ])
    // 降级已钉缓存：第二次请求不再先撞直连、也不再发探测
    expect(await msStop('m1')).toEqual({ stopped: true, pid: 5 })
    expect(endpointCalls().map((c) => c[0])).toEqual([
      `${BASE}/api/machine/solve/m1/stop`,
      '/ms/api/machine/solve/m1/stop',
      '/ms/api/machine/solve/m1/stop',
    ])
    expect(fetchMock.mock.calls.filter(([u]) => isPing(u))).toHaveLength(10)
  })

  it('msSolveStart multipart 体在 proxy 重试中原样重发（FormData 可复用）', async () => {
    stubDirectDead(() => ok({ task_id: 'm2', run_name: 'r', started_at: 't' }))
    const res = await msSolveStart(new Blob(['dxf']), 'nest_size_run.dxf',
      { ...CONFIG, client_ref: 'yl-ref-2' })
    expect(res.task_id).toBe('m2')
    const calls = endpointCalls()
    expect(calls.map((c) => c[0])).toEqual([
      `${BASE}/api/machine/solve`, '/ms/api/machine/solve'])
    const retryForm = calls[1][1].body as FormData
    expect(retryForm.get('config'))
      .toBe(JSON.stringify({ ...CONFIG, client_ref: 'yl-ref-2' }))
    expect((retryForm.get('file') as File).name).toBe('nest_size_run.dxf')
  })

  it('msStateFile 直连失败 → 降级切 YL 代理端点（两形态路径不同，随形态切换）', async () => {
    stubDirectDead(() => okAttachment('attachment; filename="machine_m9.msn"'))
    const res = await msStateFile('m9')
    expect(res.filename).toBe('machine_m9.msn')
    expect(endpointCalls().map((c) => c[0])).toEqual([
      `${BASE}/api/machine/solve/m9/state-file`,
      '/api/nest/tasks/m9/state-file',
    ])
  })

  it('非 TypeError（30s 超时 TimeoutError）不降级——原样抛给调用方计连续失败', async () => {
    stubDirect(BASE, () =>
      Promise.reject(new DOMException('signal timed out', 'TimeoutError')))
    await expect(msStatus('m1')).rejects.toBeInstanceOf(DOMException)
    expect(endpointCalls()).toHaveLength(1)   // 无 proxy 重试
  })

  it('proxy 也网络失败 → TypeError 透出（useNestSolve「可重试」口径不变）', async () => {
    stubDirectDead(() => Promise.reject(new TypeError('Failed to fetch')))
    await expect(msStatus('m1')).rejects.toBeInstanceOf(TypeError)
    expect(endpointCalls().map((c) => c[0])).toEqual([
      `${BASE}/api/machine/solve/m1/status`,
      '/ms/api/machine/solve/m1/status',
    ])
  })
})

describe('显式通道（任务级绑定，US-003）：零探测零降级直发', () => {
  const BASE = 'http://127.0.0.1:8013'

  it('显式 direct 通道：不发 ping 探测、直奔 {base} 端点（锚点恢复轮询走原通道）', async () => {
    stubFetch((url) => {
      if (isPing(url)) throw new Error('任务级绑定不应触发通道探测')
      return ok({ state: 'done', mode: 'machine', run_mode: 'normal',
        total_budget_sec: 180, elapsed_sec: 5, incumbent: null, current: null,
        per_seed: [], error: null, exit_code: null })
    })
    const st = await msStatus('m1', { kind: 'direct', base: BASE })
    expect(st.state).toBe('done')
    expect(fetchMock.mock.calls).toHaveLength(1)   // 全程恰一次端点请求
    expect(fetchMock.mock.calls[0][0])
      .toBe(`${BASE}/api/machine/solve/m1/status`)
  })

  it('显式 direct 网络级失败 → TypeError 原样上抛，不降级不切 proxy、会话缓存不动', async () => {
    stubFetch(() => Promise.reject(new TypeError('Failed to fetch')))
    await expect(msStatus('m1', { kind: 'direct', base: BASE }))
      .rejects.toBeInstanceOf(TypeError)
    // 无 '/ms' 重试（「不自动切换」交 useNestSolve 连续失败计数裁决）
    expect(endpointCalls().map((c) => c[0]))
      .toEqual([`${BASE}/api/machine/solve/m1/status`])
  })

  it('显式 proxy 通道 → /ms 前缀；msStateFile 显式通道随形态分派端点', async () => {
    stubFetch((url) => (isPing(url)
      ? Promise.reject(new TypeError('Failed to fetch'))
      : okAttachment('attachment; filename="machine_m9.msn"')))
    await msStateFile('m9', { kind: 'proxy' })
    expect(endpointCalls().map((c) => c[0]))
      .toEqual(['/api/nest/tasks/m9/state-file'])
    fetchMock.mockClear()
    await msStateFile('m9', { kind: 'direct', base: BASE })
    expect(endpointCalls().map((c) => c[0]))
      .toEqual([`${BASE}/api/machine/solve/m9/state-file`])
  })
})

describe('archiveNest（US-005 回传存档：YL 端点 multipart 三件）', () => {
  // archiveNest 走 YL 后端 /api/nest/…（非 MS，不经 resolveMsChannel——
  // 零 ping 探测）；stubProxy 语义同样适用（ping 全 miss 不影响本端点）
  const META: NestArchiveMeta = {
    task_id: 'us005-m1',
    channel: { kind: 'direct', base: 'http://127.0.0.1:8011' },
    density: 0.8157, density_pct: 81.57, width_mm: 1710, gate_mm: 1750,
    seed: 3, run_mode: 'normal', quantities: { g01: { 29: 2 } },
    started_at: '2026-10-02T08:00:00Z', uploaded_at: '2026-10-02T08:01:00Z',
  }
  const PLT = { blob: new Blob(['IN;PU10,10;PD250,250;PU;']),
    filename: 'yl-nest-us005-m1.plt' }
  const MSN = { blob: new Blob([new Uint8Array([0x1f, 0x8b, 0x08, 0x00])]),
    filename: 'yl-nest-us005-m1.msn' }

  it('POST /api/nest/tasks/{id}/archive：file_plt/file_msn/meta 三字段 + 响应透传', async () => {
    stubProxy(() => ok({ ok: true, task_id: 'us005-m1',
      dir: 'out/nest_archive/us005-m1',
      files: { plt: 'result.plt', msn: 'state.msn', meta: 'meta.json' },
      sizes: { plt: 22, msn: 4, meta: 300 } }))
    const res = await archiveNest('us005-m1', PLT, MSN, META)
    expect(res.dir).toBe('out/nest_archive/us005-m1')
    // 恰一次端点请求（无通道探测混入——非 MS 端点不经 resolveMsChannel）
    expect(endpointCalls()).toHaveLength(1)
    const [url, init] = endpointCalls()[0]
    expect(url).toBe('/api/nest/tasks/us005-m1/archive')
    expect(init?.method).toBe('POST')
    expect(init?.headers).toBeUndefined()   // 不手设 Content-Type（boundary 浏览器补）
    const form = init?.body as FormData
    expect(form.get('meta')).toBe(JSON.stringify(META))
    const plt = form.get('file_plt') as File
    const msn = form.get('file_msn') as File
    expect(plt).toBeInstanceOf(Blob)
    expect(plt.name).toBe('yl-nest-us005-m1.plt')
    expect(await plt.text()).toBe('IN;PU10,10;PD250,250;PU;')
    expect(msn.name).toBe('yl-nest-us005-m1.msn')
    expect([...new Uint8Array(await msn.arrayBuffer())])
      .toEqual([0x1f, 0x8b, 0x08, 0x00])    // gzip 字节原样（.msn 不透明）
    // 30s 超时兜底同 msJson 口径
    expect((init?.signal as AbortSignal).aborted).toBe(false)
  })

  it('taskId 特殊字符走 encodeURIComponent（同 msStatus 路径安全闸）', async () => {
    stubProxy(() => ok({ ok: true }))
    await archiveNest('a b/c', PLT, MSN, META)
    expect(endpointCalls()[0][0])
      .toBe('/api/nest/tasks/a%20b%2Fc/archive')
  })

  it("FastAPI {'detail'} 透传（400 meta 不一致 / 413 超限）", async () => {
    stubProxy(() => fail(400,
      { detail: "meta.task_id 与路径不一致（'m2' != 'm1'）" }))
    await expect(archiveNest('m1', PLT, MSN, META))
      .rejects.toThrow("meta.task_id 与路径不一致（'m2' != 'm1'）")
  })

  it('非 JSON 体（代理 502 HTML）→ HTTP 状态码兜底文案；detail 非串不理会', async () => {
    stubProxy(() => ({
      ok: false, status: 502,
      json: async () => Promise.reject(new SyntaxError('Unexpected token')),
    }))
    await expect(archiveNest('m1', PLT, MSN, META))
      .rejects.toThrow('回传存档失败（HTTP 502）')
    stubProxy(() => fail(422, { detail: [{ param: 'file_plt' }] }))
    await expect(archiveNest('m1', PLT, MSN, META))
      .rejects.toThrow('回传存档失败（HTTP 422）')
  })
})
