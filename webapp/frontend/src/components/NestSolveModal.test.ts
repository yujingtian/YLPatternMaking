// NestSolveModal 参数记忆与通道指示纯逻辑金标（vitest node env，
// localStorage 内存 stub 注入）：幅宽/运行模式跨会话记忆的读侧防御（写侧
// saveNestSolveParams 由组件提交动作触发，读侧防御保证任何坏锚都不阻塞
// 弹窗）；通道徽标文案/回退提示（US-003 AC#3，PRD 钉死原文）。弹窗三态
// 视图与安全口径（maskClosable/keyboard/关闭语义）由 US-007 Playwright
// 冒烟端到端覆盖。

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  MS_FALLBACK_NOTE, NEST_PARAMS_STORAGE_KEY, channelLabel, channelNote,
  readNestSolveParams,
} from './NestSolveModal'

function stubLocalStorage(): Map<string, string> {
  const store = new Map<string, string>()
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  })
  return store
}

afterEach(() => vi.unstubAllGlobals())

describe('readNestSolveParams（参数记忆锚）', () => {
  it('无锚/存储被禁 → 缺省 175cm + 普通档', () => {
    stubLocalStorage()
    expect(readNestSolveParams())
      .toEqual({ gateCm: 175, runMode: 'normal' })
  })

  it('合法锚透传（上次提交的幅宽/模式）', () => {
    const store = stubLocalStorage()
    store.set(NEST_PARAMS_STORAGE_KEY,
      JSON.stringify({ gateCm: 160.5, runMode: 'extreme' }))
    expect(readNestSolveParams())
      .toEqual({ gateCm: 160.5, runMode: 'extreme' })
  })

  it('坏 JSON → 缺省不炸', () => {
    const store = stubLocalStorage()
    store.set(NEST_PARAMS_STORAGE_KEY, '{bad json')
    expect(readNestSolveParams())
      .toEqual({ gateCm: 175, runMode: 'normal' })
  })

  it('非法值逐项防御：坏幅宽/未知模式 → 缺省（不让 select 打成空值）', () => {
    const store = stubLocalStorage()
    store.set(NEST_PARAMS_STORAGE_KEY,
      JSON.stringify({ gateCm: 0, runMode: 'normal' }))
    expect(readNestSolveParams())
      .toEqual({ gateCm: 175, runMode: 'normal' })
    store.set(NEST_PARAMS_STORAGE_KEY,
      JSON.stringify({ gateCm: 180, runMode: 'turbo' }))
    expect(readNestSolveParams())
      .toEqual({ gateCm: 175, runMode: 'normal' })
  })
})

describe('通道指示与回退提示（US-003 AC#3，PRD 钉死文案）', () => {
  it('channelLabel：direct=本地排料(直连) / proxy=服务器排料(回退)', () => {
    expect(channelLabel({ kind: 'direct', base: 'http://127.0.0.1:8013' }))
      .toBe('本地排料(直连)')
    expect(channelLabel({ kind: 'proxy' })).toBe('服务器排料(回退)')
  })

  it('channelNote：proxy 附回退提示（PRD 原文），direct 无事发生', () => {
    expect(channelNote({ kind: 'proxy' })).toBe(MS_FALLBACK_NOTE)
    expect(MS_FALLBACK_NOTE).toBe(
      '未检测到本地 VB超排,已使用服务器排料(性能受限);'
      + '启动本地 VB超排可获得更快速度')
    expect(channelNote({ kind: 'direct', base: 'http://127.0.0.1:8010' }))
      .toBeNull()
  })
})

