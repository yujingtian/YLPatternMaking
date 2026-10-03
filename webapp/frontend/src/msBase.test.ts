// msBase 双通道路由层金标（vitest node env，fetch 全程 stub 不触网；US-001
// tasks/prd-machine-direct-channel.md）：resolveMsChannel 端口族并发探测
// （8010..8019 × /api/machine/ping、AbortSignal 短超时）/ 端口序低口优先 /
// 全败回退 proxy / VITE_MS_BASE 覆盖零探测 / 会话缓存与在飞去重；msWorkbenchUrl
// 跟随直连发现端口、未发现保持缺省 8010。vitest 无 VITE_* 构建变量，覆盖
// 语义经 vi.stubEnv 注入 import.meta.env（源侧 env 须调用期读取——模块顶层
// 求值的常量在 import 时已冻结，stub 不生效）。

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  demoteMsChannel, msWorkbenchUrl, MS_DIRECT_PORTS, MS_PING_TIMEOUT_MS,
  MS_WORKBENCH_URL, resetMsChannelCache, resolveMsChannel,
} from './msBase'

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  resetMsChannelCache()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

function stubFetch(impl: (url: string, init?: RequestInit) => unknown) {
  fetchMock.mockImplementation(impl)
  vi.stubGlobal('fetch', fetchMock)
}

// ping 命中响应壳（探测只消费 res.ok；MS 侧 200 {ok,service} 恰两键）
const pingOk = () => ({ ok: true, status: 200 })

const PING_URLS = MS_DIRECT_PORTS.map((p) => `http://127.0.0.1:${p}/api/machine/ping`)

describe('resolveMsChannel：本地 MS 命中 → direct', () => {
  it('8010..8019 十候选一次性全发 ping，任一 2xx 命中即 direct', async () => {
    stubFetch((url) => (url === 'http://127.0.0.1:8013/api/machine/ping'
      ? pingOk() : Promise.reject(new Error('ECONNREFUSED'))))
    const ch = await resolveMsChannel()
    expect(ch).toEqual({ kind: 'direct', base: 'http://127.0.0.1:8013' })
    // 并发探测：十请求在任一落定前已全部发出（调用序 = 端口序）
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual(PING_URLS)
    // 每请求带 AbortSignal 短超时（~300ms 档，总墙钟 <1s 发起预算）
    for (const [, init] of fetchMock.mock.calls)
      expect(init?.signal).toBeInstanceOf(AbortSignal)
    expect(MS_PING_TIMEOUT_MS).toBeLessThan(1000)
  })

  it('多口命中取端口序首个（launcher 8010 顺位占端口，低口优先确定性）', async () => {
    stubFetch((url) => (/http:\/\/127\.0\.0\.1:801[2-6]\//.test(url)
      ? pingOk() : Promise.reject(new Error('miss'))))
    expect(await resolveMsChannel())
      .toEqual({ kind: 'direct', base: 'http://127.0.0.1:8012' })
  })
})

describe('resolveMsChannel：全败 → proxy 回退', () => {
  it('全部连接拒绝（本地无 MS）→ {kind:"proxy"}', async () => {
    stubFetch(() => Promise.reject(new TypeError('Failed to fetch')))
    expect(await resolveMsChannel()).toEqual({ kind: 'proxy' })
    expect(fetchMock).toHaveBeenCalledTimes(MS_DIRECT_PORTS.length)
  })

  it('非 2xx（旧版 MS 无 ping 端点 404 / CORS 白名单外 403）同样归 miss', async () => {
    stubFetch(() => ({ ok: false, status: 404 }))
    expect(await resolveMsChannel()).toEqual({ kind: 'proxy' })
  })
})

describe('resolveMsChannel：VITE_MS_BASE 显式覆盖优先', () => {
  it('配置时直取该绝对地址为 direct 通道，零探测请求', async () => {
    vi.stubEnv('VITE_MS_BASE', 'https://ms-ops.example.com')
    stubFetch(() => { throw new Error('探测不应发出') })
    expect(await resolveMsChannel())
      .toEqual({ kind: 'direct', base: 'https://ms-ops.example.com' })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('resolveMsChannel：会话缓存语义', () => {
  it('direct 命中后缓存——二次调用零新探测、同对象直返', async () => {
    stubFetch((url) => (url.includes(':8011/') ? pingOk()
      : Promise.reject(new Error('miss'))))
    const first = await resolveMsChannel()
    const second = await resolveMsChannel()
    expect(second).toBe(first)
    expect(fetchMock).toHaveBeenCalledTimes(MS_DIRECT_PORTS.length)
  })

  it('proxy 回退同样缓存（会话内不重复探测）', async () => {
    stubFetch(() => Promise.reject(new Error('miss')))
    await resolveMsChannel()
    await resolveMsChannel()
    expect(fetchMock).toHaveBeenCalledTimes(MS_DIRECT_PORTS.length)
  })

  it('并发调用共享同一轮探测（在飞去重）', async () => {
    stubFetch((url) => (url.includes(':8015/') ? pingOk()
      : Promise.reject(new Error('miss'))))
    const [a, b] = await Promise.all([resolveMsChannel(), resolveMsChannel()])
    expect(a).toEqual({ kind: 'direct', base: 'http://127.0.0.1:8015' })
    expect(b).toBe(a)
    expect(fetchMock).toHaveBeenCalledTimes(MS_DIRECT_PORTS.length)
  })

  it('resetMsChannelCache 复位后重新探测（测试钩子）', async () => {
    stubFetch(() => Promise.reject(new Error('miss')))
    expect(await resolveMsChannel()).toEqual({ kind: 'proxy' })
    resetMsChannelCache()
    stubFetch((url) => (url.includes(':8010/') ? pingOk()
      : Promise.reject(new Error('miss'))))
    expect(await resolveMsChannel())
      .toEqual({ kind: 'direct', base: 'http://127.0.0.1:8010' })
    expect(fetchMock).toHaveBeenCalledTimes(MS_DIRECT_PORTS.length * 2)
  })
})

describe('msWorkbenchUrl：三期引导链接跟随通道', () => {
  it('直连发现端口跟随（8013 → http://127.0.0.1:8013/）', () => {
    expect(msWorkbenchUrl({ kind: 'direct', base: 'http://127.0.0.1:8013' }))
      .toBe('http://127.0.0.1:8013/')
  })

  it('proxy / 无通道保持缺省 8010', () => {
    expect(MS_WORKBENCH_URL).toBe('http://127.0.0.1:8010/')
    expect(msWorkbenchUrl({ kind: 'proxy' })).toBe(MS_WORKBENCH_URL)
    expect(msWorkbenchUrl(null)).toBe(MS_WORKBENCH_URL)
    expect(msWorkbenchUrl()).toBe(MS_WORKBENCH_URL)
  })

  it('VITE_MS_WORKBENCH_URL 显式覆盖恒优先（含直连发现端口）', () => {
    vi.stubEnv('VITE_MS_WORKBENCH_URL', 'https://wb.example.com/')
    expect(msWorkbenchUrl({ kind: 'direct', base: 'http://127.0.0.1:8013' }))
      .toBe('https://wb.example.com/')
    expect(msWorkbenchUrl({ kind: 'proxy' })).toBe('https://wb.example.com/')
  })

  it('非 127.0.0.1 直连 base（VITE_MS_BASE 钉远端）不自动跟随，回缺省', () => {
    expect(msWorkbenchUrl({ kind: 'direct', base: 'https://ms.example.com' }))
      .toBe(MS_WORKBENCH_URL)
  })
})

describe('demoteMsChannel：请求层降级钩子（US-002）', () => {
  it('钉缓存 proxy——后续 resolve 零探测直返；在飞探测迟到回填被拒收', async () => {
    stubFetch((url) => (url.includes(':8010/') ? pingOk()
      : Promise.reject(new Error('miss'))))
    expect(await resolveMsChannel())
      .toEqual({ kind: 'direct', base: 'http://127.0.0.1:8010' })
    demoteMsChannel()
    // 钉回 proxy：不发新探测（fetch 计数不增），resolve 直接命中缓存
    expect(await resolveMsChannel()).toEqual({ kind: 'proxy' })
    expect(fetchMock).toHaveBeenCalledTimes(MS_DIRECT_PORTS.length)
  })

  it('demote 后 resetMsChannelCache 可恢复探测（测试复位语义不变）', async () => {
    stubFetch(() => Promise.reject(new Error('miss')))
    expect(await resolveMsChannel()).toEqual({ kind: 'proxy' })
    demoteMsChannel()
    resetMsChannelCache()
    expect(await resolveMsChannel()).toEqual({ kind: 'proxy' })
    expect(fetchMock).toHaveBeenCalledTimes(MS_DIRECT_PORTS.length * 2)
  })
})
