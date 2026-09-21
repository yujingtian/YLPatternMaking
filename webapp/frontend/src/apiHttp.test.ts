// apiHttp MS 段金标（vitest node env，fetch 全程 stub 不触网）：五函数
// URL/方法/载荷口径 + normalizeMsError 两形态归一。MS_BASE 取缺省 '/ms'
//（vitest 无 VITE_MS_BASE 构建变量）。

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  msExport, msResult, msSolveStart, msStatus, msStop, normalizeMsError,
} from './apiHttp'
import type { MsMachineConfig, MsStatus } from './types'

const fetchMock = vi.fn()

afterEach(() => {
  fetchMock.mockReset()
  vi.unstubAllGlobals()
})

function stubFetch(impl: (url: string, init?: RequestInit) => unknown) {
  fetchMock.mockImplementation(impl)
  vi.stubGlobal('fetch', fetchMock)
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
    stubFetch(() => ok({ task_id: 'm1', run_name: 'machine_x', started_at: 't' }))
    const res = await msSolveStart(new Blob(['dxf']), 'nest_size_run.dxf',
      { ...CONFIG, client_ref: 'yl-ref-1' })
    expect(res.task_id).toBe('m1')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/ms/api/machine/solve')
    expect(init.method).toBe('POST')
    expect(init.headers).toBeUndefined()   // multipart boundary 交给浏览器
    const form = init.body as FormData
    expect(form.get('config')).toBe(
      JSON.stringify({ ...CONFIG, client_ref: 'yl-ref-1' }))
    expect((form.get('file') as File).name).toBe('nest_size_run.dxf')
  })

  it('409 重复提交 → MsError 透传中文 + taskId', async () => {
    stubFetch(() => fail(409, {
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
    stubFetch(() => fail(502, {
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
    stubFetch(() => ok(st))
    expect(await msStatus('m1')).toEqual(st)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/ms/api/machine/solve/m1/status')
    expect(init).toBeUndefined()
  })

  it('taskId 特殊字符走 encodeURIComponent（路径安全闸）', async () => {
    stubFetch(() => fail(404, { error: '任务不存在' }))
    await expect(msStatus('a/b c')).rejects.toMatchObject({ status: 404 })
    expect(fetchMock.mock.calls[0][0])
      .toBe('/ms/api/machine/solve/a%2Fb%20c/status')
  })

  it('msStop POST .../stop，响应透传', async () => {
    stubFetch(() => ok({ stopped: true, pid: 123 }))
    expect(await msStop('m1')).toEqual({ stopped: true, pid: 123 })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/ms/api/machine/solve/m1/stop')
    expect(init.method).toBe('POST')
  })

  it('msResult GET .../result；running 409 归一', async () => {
    stubFetch(() => fail(409, { error: '机器排料任务尚未结束' }))
    await expect(msResult('m1')).rejects.toMatchObject({
      status: 409, message: '机器排料任务尚未结束',
    })
    expect(fetchMock.mock.calls[0][0]).toBe('/ms/api/machine/solve/m1/result')
  })
})

describe('msExport（{task_id} 最小体 + 文件名解析）', () => {
  function okPlt(cd: string | null) {
    return {
      ok: true, status: 200,
      json: async () => ({}),
      blob: async () => new Blob(['IN;PU']),
      headers: { get: (k: string) => (k === 'content-disposition' ? cd : null) },
    }
  }

  it('请求体仅 {task_id}；UTF-8 filename* 优先解码中文真名', async () => {
    stubFetch(() => okPlt(
      'attachment; filename="nest_m1.plt"; '
      + "filename*=UTF-8''%E6%8E%92%E6%96%99.plt"))
    const res = await msExport('m1')
    expect(res.filename).toBe('排料.plt')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/ms/api/machine/export')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ task_id: 'm1' })
  })

  it('仅 ASCII filename="…" 亦可用', async () => {
    stubFetch(() => okPlt('attachment; filename="nest_m1.plt"'))
    expect((await msExport('m1')).filename).toBe('nest_m1.plt')
  })

  it('缺 Content-Disposition → 本地合成 yl-nest-{taskId}.plt', async () => {
    stubFetch(() => okPlt(null))
    expect((await msExport('m9')).filename).toBe('yl-nest-m9.plt')
  })

  it('非 2xx → normalizeMsError（404 任务不存在）', async () => {
    stubFetch(() => fail(404, { error: '任务不存在（task_id=m9）' }))
    await expect(msExport('m9')).rejects.toMatchObject({
      status: 404, message: '任务不存在（task_id=m9）',
    })
  })
})

