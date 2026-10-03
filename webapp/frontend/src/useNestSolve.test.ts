// useNestSolve 纯函数金标（状态归并/密度投影/预算回落/任务锚存取；轮询
// 状态机行为由 US-007 Playwright 冒烟端到端覆盖）。localStorage 以内存
// stub 注入（node env 无实现）。

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  MS_TASK_STORAGE_KEY, POLL_FAIL_LIMIT, POLL_FAST_MS, POLL_SLOW_MS,
  densityPctOf, msStateToPhase, pollFailMessage, readStoredMsTask,
  solveCloseBehavior, totalSecOf,
} from './hooks/useNestSolve'
import type { MsRunMode, MsStatus } from './types'

function mkStatus(partial: Partial<MsStatus>): MsStatus {
  return {
    state: 'running', mode: 'machine', run_mode: 'normal',
    total_budget_sec: 180, elapsed_sec: 0, incumbent: null, current: null,
    per_seed: [], error: null, exit_code: null, ...partial,
  }
}

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

describe('轮询档位契约（PRD 钉死）', () => {
  it('在视 2s / 关窗 15s / 连续失败容限 3', () => {
    expect(POLL_FAST_MS).toBe(2_000)
    expect(POLL_SLOW_MS).toBe(15_000)
    expect(POLL_FAIL_LIMIT).toBe(3)
  })
})

describe('msStateToPhase（MS 状态归并）', () => {
  it('submitted/starting/running/orphan → running 家族', () => {
    for (const s of ['submitted', 'starting', 'running', 'orphan'] as const)
      expect(msStateToPhase(s)).toBe('running')
  })

  it('done/stopped/error 原样透传（终端态停表依据）', () => {
    expect(msStateToPhase('done')).toBe('done')
    expect(msStateToPhase('stopped')).toBe('stopped')
    expect(msStateToPhase('error')).toBe('error')
  })
})

describe('densityPctOf（物理口径 ×100 两位小数）', () => {
  it('incumbent（best-so-far）优先', () => {
    expect(densityPctOf(mkStatus({
      incumbent: {
        density: 0.876543, width_mm: 9000, seed: 0, frame_index: 2, elapsed: 9,
      },
      current: { seed: 0, density: 0.5, density_sparrow: null, ext: false },
    }))).toBe(87.65)
  })

  it('incumbent 缺失/无 density → 回落 current；双缺 → null', () => {
    expect(densityPctOf(mkStatus({
      incumbent: null,
      current: { seed: 1, density: 0.5, density_sparrow: null, ext: true },
    }))).toBe(50)
    expect(densityPctOf(mkStatus({
      incumbent: {
        density: null, width_mm: null, seed: null, frame_index: null,
        elapsed: null,
      },
      current: null,
    }))).toBeNull()
  })
})

describe('totalSecOf（进度条总时长口径）', () => {
  it('MS total_budget_sec 优先（运行模式烘焙值）', () => {
    expect(totalSecOf(mkStatus({ total_budget_sec: 7200 }))).toBe(7200)
  })

  it('缺失回落 RUN_MODE_OPTIONS 同源预算', () => {
    expect(totalSecOf(mkStatus(
      { run_mode: 'advanced', total_budget_sec: null }))).toBe(1200)
    expect(totalSecOf(mkStatus(
      { run_mode: 'extreme', total_budget_sec: null }))).toBe(7200)
    expect(totalSecOf(mkStatus(
      { run_mode: 'normal', total_budget_sec: null }))).toBe(180)
  })

  it('模式未知且无预算 → null（防御：不臆造总时长）', () => {
    expect(totalSecOf(mkStatus({
      run_mode: 'x' as unknown as MsRunMode, total_budget_sec: null,
    }))).toBeNull()
  })
})

describe('solveCloseBehavior（弹窗显式关闭语义，US-004）', () => {
  it('进度期家族（submitting/running）→ 后台守望，不回收任务', () => {
    expect(solveCloseBehavior('submitting'))
      .toEqual({ background: true, deleteTask: false })
    expect(solveCloseBehavior('running'))
      .toEqual({ background: true, deleteTask: false })
  })

  it('结果期（done/stopped）→ 终结 + best-effort DELETE 回收名额', () => {
    expect(solveCloseBehavior('done'))
      .toEqual({ background: false, deleteTask: true })
    expect(solveCloseBehavior('stopped'))
      .toEqual({ background: false, deleteTask: true })
  })

  it('idle/error → 纯重置关窗（无任务可回收）', () => {
    expect(solveCloseBehavior('idle'))
      .toEqual({ background: false, deleteTask: false })
    expect(solveCloseBehavior('error'))
      .toEqual({ background: false, deleteTask: false })
  })
})

describe('readStoredMsTask（「继续查看」重连锚）', () => {
  it('合法锚透传（含通道标记，US-003）', () => {
    const store = stubLocalStorage()
    store.set(MS_TASK_STORAGE_KEY, JSON.stringify({
      taskId: 'm1', runMode: 'advanced', at: 't0',
      channel: { kind: 'direct', base: 'http://127.0.0.1:8013' },
    }))
    expect(readStoredMsTask()).toEqual({
      taskId: 'm1', runMode: 'advanced', at: 't0',
      channel: { kind: 'direct', base: 'http://127.0.0.1:8013' },
    })
    store.set(MS_TASK_STORAGE_KEY, JSON.stringify({
      taskId: 'm2', runMode: 'normal', at: 't0', channel: { kind: 'proxy' },
    }))
    expect(readStoredMsTask()?.channel).toEqual({ kind: 'proxy' })
  })

  it('锚通道标记归一（US-003）：缺失=旧锚代理时代 / 坏标记 → proxy 防御', () => {
    const store = stubLocalStorage()
    // US-003 前旧锚（无 channel 字段）：任务全落在「/ms 代理唯一通道」
    // 时代，按 proxy 绑定恢复轮询才不串台
    store.set(MS_TASK_STORAGE_KEY,
      JSON.stringify({ taskId: 'm1', runMode: 'normal', at: 't0' }))
    expect(readStoredMsTask()?.channel).toEqual({ kind: 'proxy' })
    // direct 缺 base / base 非 string / 未知 kind → proxy
    for (const bad of [
      { kind: 'direct' }, { kind: 'direct', base: '' },
      { kind: 'direct', base: 8010 }, { kind: 'mystery' }, 'proxy',
    ]) {
      store.set(MS_TASK_STORAGE_KEY, JSON.stringify({
        taskId: 'm1', runMode: 'normal', at: 't0', channel: bad,
      }))
      expect(readStoredMsTask()?.channel).toEqual({ kind: 'proxy' })
    }
  })

  it('坏 JSON / 缺 taskId / 无键 → null', () => {
    const store = stubLocalStorage()
    store.set(MS_TASK_STORAGE_KEY, '{bad json')
    expect(readStoredMsTask()).toBeNull()
    store.set(MS_TASK_STORAGE_KEY, JSON.stringify({ runMode: 'normal' }))
    expect(readStoredMsTask()).toBeNull()
    store.delete(MS_TASK_STORAGE_KEY)
    expect(readStoredMsTask()).toBeNull()
  })

  it('锚 TTL 24h（2026-09-29：进工作台空挂「排料中」成因之一）', () => {
    const store = stubLocalStorage()
    // 新鲜锚（1h 前）：透传
    const fresh = new Date(Date.now() - 60 * 60 * 1000).toISOString()
    store.set(MS_TASK_STORAGE_KEY,
      JSON.stringify({ taskId: 'm1', runMode: 'normal', at: fresh }))
    expect(readStoredMsTask()?.taskId).toBe('m1')
    // 陈锚（25h 前）：null 并清锚（下次不再对账）
    const stale = new Date(Date.now() - 25 * 60 * 60 * 1000).toISOString()
    store.set(MS_TASK_STORAGE_KEY,
      JSON.stringify({ taskId: 'm2', runMode: 'normal', at: stale }))
    expect(readStoredMsTask()).toBeNull()
    expect(store.has(MS_TASK_STORAGE_KEY)).toBe(false)
    // 非法时间串（Date.parse NaN）：兼容保留旧锚
    store.set(MS_TASK_STORAGE_KEY,
      JSON.stringify({ taskId: 'm3', runMode: 'normal', at: 't0' }))
    expect(readStoredMsTask()?.taskId).toBe('m3')
  })
})

describe('pollFailMessage（连续失败引导文案，US-003 AC#2）', () => {
  it('direct：本地 MS 中断 → 两条出路（重启恢复 / 转服务器重跑），明示不自动切换不自动重跑', () => {
    const msg =
      pollFailMessage({ kind: 'direct', base: 'http://127.0.0.1:8010' })
    expect(msg).toContain('本地排料服务连续 3 次无响应')
    // 出路一：重启本地 MS 后凭锚点恢复（marker 在 → orphan 恢复判定）
    expect(msg).toContain('重启本地 VB超排')
    expect(msg).toContain('锚点仍在')
    // 出路二：转服务器排料重跑
    expect(msg).toContain('服务器排料重跑')
    // 不自动切换、不自动重跑（PRD FR-3：转服务器是用户显式动作）
    expect(msg).toContain('不会自动切换通道')
    expect(msg).toContain('不会自动重跑')
  })

  it('proxy：现状通用文案零改动（服务器 MS 视角）', () => {
    expect(pollFailMessage({ kind: 'proxy' }))
      .toBe('MS 排料服务连续 3 次无响应（服务可能未启动；'
        + '任务在 MS 侧可能仍在运行，可稍后「继续查看」重连）')
  })
})

