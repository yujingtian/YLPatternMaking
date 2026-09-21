// MS config 构建器金标（vitest；风格对齐 sizeRun.test.ts / NestResultModal.test.ts）。
// 口径 = PRD US-002 验收金标：gate_mm = cm×10、per_type 全 g 码恒 {d:0,tol:0}
// （键集 = numMap ∪ labels）、quantities 按 numMap 展开到每码（内层键 =
// 数字字符串、各码同数量）；缺省 175cm / normal；非法输入（空码表/非整数
// 码/坏幅宽/坏模式/空清单）抛可读中文错误。无单码分支：sizes 必填数组、
// 空即抛（单码由调用侧前置拦截，不进本函数——二期仅推板多码）。

import { describe, expect, it } from 'vitest'
import {
  buildMachineConfig, DEFAULT_GATE_CM, DEFAULT_RUN_MODE, RUN_MODE_OPTIONS,
} from './msConfig'
import type { MsRunMode } from './types'

describe('buildMachineConfig（PRD 验收金标映射）', () => {
  it('金标：numMap×码表 -> gate_mm/sizes/run_mode/per_type/quantities', () => {
    expect(buildMachineConfig({
      numMap: { g01: 2, g08: 1 }, sizes: ['29', '30'],
      gateCm: 175, runMode: 'normal',
    })).toEqual({
      gate_mm: 1750,
      sizes: [29, 30],
      run_mode: 'normal',
      per_type: { g01: { d: 0, tol: 0 }, g08: { d: 0, tol: 0 } },
      quantities: { g01: { '29': 2, '30': 2 }, g08: { '29': 1, '30': 1 } },
    })
  })

  it('缺省：gateCm=175 -> 1750、runMode=normal', () => {
    expect(buildMachineConfig(
      { numMap: { g01: 2 }, sizes: ['30'] },
    )).toEqual({
      gate_mm: DEFAULT_GATE_CM * 10,
      sizes: [30],
      run_mode: DEFAULT_RUN_MODE,
      per_type: { g01: { d: 0, tol: 0 } },
      quantities: { g01: { '30': 2 } },
    })
  })

  it('幅宽 cm×10（160.5 -> 1605）；advanced/extreme 透传 run_mode', () => {
    const cfg = buildMachineConfig(
      { numMap: { g02: 2 }, sizes: ['30'], gateCm: 160.5, runMode: 'extreme' })
    expect(cfg.gate_mm).toBe(1605)
    expect(cfg.run_mode).toBe('extreme')
    expect(buildMachineConfig(
      { numMap: { g02: 2 }, sizes: ['30'], runMode: 'advanced' }).run_mode,
    ).toBe('advanced')
  })

  it('per_type 键集 = numMap ∪ labels（labels 独有键数量回退 0）', () => {
    const cfg = buildMachineConfig({
      numMap: { g01: 2, g02: 2 },
      labels: { g01: '前片裁片', g02: '后片裁片', g09: '小表袋' },
      sizes: ['30'],
    })
    expect(Object.keys(cfg.per_type).sort()).toEqual(['g01', 'g02', 'g09'])
    expect(cfg.quantities.g09).toEqual({ '30': 0 })
    expect(cfg.per_type.g09).toEqual({ d: 0, tol: 0 })
  })

  it('多码展开：numMap 数量复制到每个码（内层键 = 数字字符串）', () => {
    const cfg = buildMachineConfig(
      { numMap: { g05: 2 }, sizes: ['27', '28', '29', '30'] })
    expect(cfg.sizes).toEqual([27, 28, 29, 30])
    expect(cfg.quantities).toEqual(
      { g05: { '27': 2, '28': 2, '29': 2, '30': 2 } })
  })
})

describe('非法输入（可读中文错误；无单码分支）', () => {
  it('空码表抛错', () => {
    expect(() => buildMachineConfig({ numMap: { g01: 2 }, sizes: [] }))
      .toThrow('码表为空')
  })

  it('非整数字码抛错（字母尾缀/小数/空串）', () => {
    for (const bad of ['29a', '29.5', '']) {
      expect(() => buildMachineConfig(
        { numMap: { g01: 2 }, sizes: ['29', bad] })).toThrow('不是纯整数字')
    }
  })

  it('幅宽非正/NaN 抛错', () => {
    for (const bad of [0, -175, Number.NaN]) {
      expect(() => buildMachineConfig(
        { numMap: { g01: 2 }, sizes: ['30'], gateCm: bad })).toThrow('幅宽非法')
    }
  })

  it('未知运行模式抛错（运行期防御，类型外的脏值）', () => {
    expect(() => buildMachineConfig({
      numMap: { g01: 2 }, sizes: ['30'],
      runMode: 'fast' as unknown as MsRunMode,
    })).toThrow('未知运行模式')
  })

  it('空数量清单（numMap 与 labels 均空）抛错', () => {
    expect(() => buildMachineConfig({ numMap: {}, sizes: ['30'] }))
      .toThrow('数量清单为空')
    expect(() => buildMachineConfig(
      { numMap: {}, labels: {}, sizes: ['30'] })).toThrow('数量清单为空')
  })
})

describe('RUN_MODE_OPTIONS（三档同源标注）', () => {
  it('normal/advanced/extreme + 文案 + 预算秒（对齐 MS total_budget_sec）', () => {
    expect(RUN_MODE_OPTIONS).toEqual([
      { value: 'normal', label: '普通运行（180s）', budgetSec: 180 },
      { value: 'advanced', label: '高级运行（20min）', budgetSec: 1200 },
      { value: 'extreme', label: '极限运行（2h）', budgetSec: 7200 },
    ])
  })
})
