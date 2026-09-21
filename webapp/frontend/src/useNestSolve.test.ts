// useNestSolve 纯函数金标（状态归并/密度投影/预算回落/任务锚存取；轮询
// 状态机行为由 US-007 Playwright 冒烟端到端覆盖）。localStorage 以内存
// stub 注入（node env 无实现）。

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  MS_TASK_STORAGE_KEY, POLL_FAIL_LIMIT, POLL_FAST_MS, POLL_SLOW_MS,
  densityPctOf, msStateToPhase, readStoredMsTask, solveCloseBehavior,
  totalSecOf,
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
  it('合法锚透传', () => {
    const store = stubLocalStorage()
    store.set(MS_TASK_STORAGE_KEY,
      JSON.stringify({ taskId: 'm1', runMode: 'advanced', at: 't0' }))
    expect(readStoredMsTask())
      .toEqual({ taskId: 'm1', runMode: 'advanced', at: 't0' })
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
})

