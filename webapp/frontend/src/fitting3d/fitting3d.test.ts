// 3D 人台数据层单测（three 不进测试：视图层另行肉眼验收）。金标风格：
// 手工推演值 + 强断言。
//   1. estimateBody：成衣 − 先验松量 + 0.85 下限
//   2. 体型库：默认估计激活、预设存在、自定义增删、JSON 导入导出
// 人台几何链路金标在 bodymesh/bodymesh.test.ts（合成网格）+
// fitting3d.integration.test.ts（真资产端到端）；2026-09-12 裁撤试穿后
// mannequin 适配层/mesh/seams/pbd/heatmap describe 随试穿链退役
//（演进史见决策日志）。
import { describe, expect, it, vi } from 'vitest'
import { estimateBody, validateGirths } from './bodyProfile'
import {
  BODY_PRESETS, exportProfiles, findProfile, importProfiles, loadStore,
  removeCustom, upsertCustom,
} from './bodyProfileStore'

describe('bodyProfile 体型估计', () => {
  it('成衣 − 先验松量（waist 1.5 / hip 5 / thigh 4 / knee 3）', () => {
    const b = estimateBody({ waist: 70, hip: 96, thigh: 58, knee: 46 })
    expect(b.waist).toBeCloseTo(68.5, 9)
    expect(b.hip).toBeCloseTo(91, 9)
    expect(b.thigh).toBeCloseTo(54, 9)
    expect(b.knee).toBeCloseTo(43, 9)
    expect(b.estimated).toBe(true)
  })
  it('0.85 下限：小成衣防负松量翻车', () => {
    const b = estimateBody({ waist: 1, hip: 1, knee: 1 })
    expect(b.waist).toBeCloseTo(0.85, 9)
    expect(b.thigh).toBeUndefined()
  })
  it('校验范围', () => {
    expect(validateGirths({ waist: 66, hip: 90, knee: 35 })).toBeNull()
    expect(validateGirths({ waist: 140, hip: 90, knee: 35 })).toMatch(/腰围/)
  })
})

describe('bodyProfileStore 体型库', () => {
  it('默认激活估计体型；预设含标准 165/66A', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => null, setItem: () => {}, removeItem: () => {},
    })
    const s = loadStore()
    expect(s.activeId).toBe('estimated')
    expect(BODY_PRESETS.some((p) => p.id === 'std-165-66')).toBe(true)
    vi.unstubAllGlobals()
  })
  it('自定义增删改 + 查找', () => {
    const s0 = { version: 1 as const, activeId: 'estimated', customs: [] }
    const p = { id: 'c1', name: '我的体型', waist: 64, hip: 92, knee: 34 }
    const s1 = upsertCustom(s0, p)
    expect(s1.customs).toHaveLength(1)
    expect(s1.activeId).toBe('c1')
    expect(findProfile(s1, 'c1')?.name).toBe('我的体型')
    const s2 = upsertCustom(s1, { ...p, waist: 65 })
    expect(s2.customs).toHaveLength(1)
    expect(s2.customs[0].waist).toBe(65)
    const s3 = removeCustom(s2, 'c1')
    expect(s3.customs).toHaveLength(0)
    expect(s3.activeId).toBe('estimated')
  })
  it('JSON 导出/导入回环；非法条目跳过计数', () => {
    const text = exportProfiles([
      { id: 'a', name: 'A', waist: 64, hip: 90, knee: 34 },
      { id: 'b', name: 'B', waist: 64, hip: 90, knee: 34 },
    ])
    const rt = importProfiles(text)
    expect(rt.ok).toHaveLength(2)
    expect(rt.skipped).toBe(0)
    const bad = JSON.stringify({
      profiles: [
        { id: 'x', name: 'X', waist: 999, hip: 90, knee: 34 },   // 范围外
        { id: 'y', name: 'Y', waist: 64, hip: 90, knee: 34 },
      ],
    })
    const r2 = importProfiles(bad)
    expect(r2.ok.map((p) => p.id)).toEqual(['y'])
    expect(r2.skipped).toBe(1)
    expect(() => importProfiles('[]')).toThrow()
  })
})
