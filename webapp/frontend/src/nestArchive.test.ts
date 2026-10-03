// nestArchive 纯逻辑金标（vitest node env，风格对齐 useNestSolve.test.ts）：
// US-005 done 终态自动回传存档的三件口径——meta 字段集（PRD 钉死：
// task_id/通道标记/density/width_mm/码套/seed/run_mode/时间）、自动触发判定
//（done 限定 + attemptedTaskId 去重）、状态小字文案（fail 附「不阻塞下载 +
// 可重试」引导）。网络函数 archiveNest 的 multipart 口径在 apiHttp.test.ts；
// 弹窗三态接线（自动触发时机/重试按钮/下载不锁）由 US-005 Playwright 活体
// 验证覆盖（out/us005_verify.mjs）。

import { describe, expect, it } from 'vitest'
import {
  archiveNote, buildArchiveMeta, shouldAutoArchive,
} from './nestArchive'
import type { NestSolvePhase } from './hooks/useNestSolve'
import type {
  MsMachineConfig, MsResult, MsStatus,
} from './types'

function mkConfig(over: Partial<MsMachineConfig> = {}): MsMachineConfig {
  return {
    gate_mm: 1750,
    run_mode: 'advanced',
    sizes: [29, 30],
    per_type: { g01: { d: 0, tol: 0 } },
    quantities: { g01: { 29: 2, 30: 1.5 } },
    ...over,
  }
}

function mkResult(over: Partial<MsResult> = {}): MsResult {
  return {
    state: 'done',
    mode: 'machine',
    run_dir: 'mock',
    manifest: { gate_mm: 1750, total_area_mm2: 2_000_000, n_eroded: 0,
      pieces: [] },
    best: {
      seed: 3, frame_index: 7, elapsed: 42, density: 0.8157,
      density_sparrow: null, width_mm: 1710, placed_items: [],
    },
    summary: { per_seed: [] },
    ...over,
  }
}

function mkStatus(over: Partial<MsStatus> = {}): MsStatus {
  return {
    state: 'done', mode: 'machine', run_mode: 'normal',
    total_budget_sec: 180, elapsed_sec: 42, incumbent: null, current: null,
    per_seed: [], error: null, exit_code: 0,
    ...over,
  }
}

describe('buildArchiveMeta（meta 字段集，PRD 前端口径）', () => {
  it('全字段：通道标记/density 双口径/width_mm/gate_mm/seed/码套/时间', () => {
    const meta = buildArchiveMeta({
      taskId: 'us005-m1',
      channel: { kind: 'direct', base: 'http://127.0.0.1:8011' },
      result: mkResult(),
      status: mkStatus(),
      config: mkConfig(),
      startedAt: '2026-10-02T08:00:00+00:00',
      now: new Date('2026-10-02T08:01:00Z'),
    })
    expect(meta).toEqual({
      task_id: 'us005-m1',
      channel: { kind: 'direct', base: 'http://127.0.0.1:8011' },
      density: 0.8157,           // MS 原生分数口径（与 best.density 同源）
      density_pct: 81.57,        // 人类可读百分数（×100 两位小数）
      width_mm: 1710,
      gate_mm: 1750,
      seed: 3,
      run_mode: 'normal',        // status 权威值优先于 config
      quantities: { g01: { 29: 2, 30: 1.5 } },
      started_at: '2026-10-02T08:00:00+00:00',
      uploaded_at: '2026-10-02T08:01:00.000Z',
    })
  })

  it('run_mode：status 缺席回落提交 config（attach 重连防御位）', () => {
    const meta = buildArchiveMeta({
      taskId: 'm2', channel: { kind: 'proxy' }, result: mkResult(),
      status: null, config: mkConfig(), startedAt: null,
    })
    expect(meta.run_mode).toBe('advanced')
    expect(meta.channel).toEqual({ kind: 'proxy' })
    expect(meta.started_at).toBeNull()   // attach 恢复无 started_at，不臆造
  })

  it('attach 重连场景：config 无快照 → quantities null；channel null → proxy', () => {
    const meta = buildArchiveMeta({
      taskId: 'm3', channel: null, result: mkResult(), status: mkStatus(),
      config: null, startedAt: null,
    })
    expect(meta.quantities).toBeNull()
    expect(meta.channel).toEqual({ kind: 'proxy' })
    expect(meta.run_mode).toBe('normal')
  })
})

describe('shouldAutoArchive（done 自动触发判定）', () => {
  const result = mkResult()

  it('done + 任务/结果在手 → 触发（两通道同口径，通道不是判定输入）', () => {
    expect(shouldAutoArchive('done', 'm1', result, null)).toBe(true)
  })

  it('stopped/error/running/idle 不自动存档（PRD 只钉 done）', () => {
    const phases: NestSolvePhase[] =
      ['stopped', 'error', 'running', 'submitting', 'idle']
    for (const p of phases)
      expect(shouldAutoArchive(p, 'm1', result, null)).toBe(false)
  })

  it('attemptedTaskId 去重：同任务不重发（重渲染/StrictMode/重开窗），新任务放行', () => {
    expect(shouldAutoArchive('done', 'm1', result, 'm1')).toBe(false)
    expect(shouldAutoArchive('done', 'm2', result, 'm1')).toBe(true)
  })

  it('无 taskId / 无 result / result.best 运行时缺失 → 不触发', () => {
    expect(shouldAutoArchive('done', null, result, null)).toBe(false)
    expect(shouldAutoArchive('done', 'm1', null, null)).toBe(false)
    // best 运行时缺失（类型不约束运行时形态，同弹窗渲染侧防御口径）
    const noBest = { ...result, best: null } as unknown as MsResult
    expect(shouldAutoArchive('done', 'm1', noBest, null)).toBe(false)
  })
})

describe('archiveNote（状态小字文案）', () => {
  it('busy/ok 指示文案', () => {
    expect(archiveNote('busy', null)).toBe('正在回传存档…')
    expect(archiveNote('ok', null))
      .toBe('结果已回传存档（PLT / 状态文件 / 元数据）')
  })

  it('fail：消息透传 + 「不影响结果展示与下载，可重试」引导（AC 口径）', () => {
    const note = archiveNote('fail', '回传文件超限')
    expect(note).toContain('回传存档失败：回传文件超限')
    expect(note).toContain('不影响结果展示与下载')
    expect(note).toContain('重试')
    // 消息缺席防御（网络 TypeError 归一前的空态不出现裸「:」）
    expect(archiveNote('fail', null))
      .toBe('回传存档失败：未知错误。不影响结果展示与下载，可点击重试')
  })

  it('idle 无事发生（stopped/取果失败期不渲染指示）', () => {
    expect(archiveNote('idle', null)).toBe('')
  })
})
