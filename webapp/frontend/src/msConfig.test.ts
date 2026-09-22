// MS config 构建器金标（vitest；风格对齐 sizeRun.test.ts / NestResultModal.test.ts）。
// 口径 = PRD US-002 验收金标：gate_mm = cm×10、per_type 全 g 码恒 {d:0,tol:0}
// （键集 = numMap ∪ labels）、quantities = numMap 默认数量按各码套数
// multiplySets 换算展开（内层键 = 数字字符串；缺省各码 1 套 = 旧口径各码
// 同数量；2026-09-22 套数三分支：整数套直乘/非整数套偶数量直乘/奇数量
// 向上取整）；缺省 175cm / normal；非法输入（空码表/非整数码/坏幅宽/坏
// 模式/空清单/坏套数）抛可读中文错误。无单码分支：sizes 必填数组、
// 空即抛（单码由调用侧前置拦截，不进本函数——二期仅推板多码）。

import { describe, expect, it } from 'vitest'
import {
  buildMachineConfig, DEFAULT_GATE_CM, DEFAULT_RUN_MODE, multiplySets,
  RUN_MODE_OPTIONS,
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

describe('multiplySets 套数换算（2026-09-22 用户口径金标）', () => {
  it('整数套直接相乘：2×2=4、1×2=2、3×4=12', () => {
    expect(multiplySets(2, 2)).toBe(4)
    expect(multiplySets(1, 2)).toBe(2)
    expect(multiplySets(3, 4)).toBe(12)
  })

  it('非整数套 × 偶数量直接相乘：2×0.5=1、2×1.5=3、4×2.5=10', () => {
    expect(multiplySets(2, 0.5)).toBe(1)
    expect(multiplySets(2, 1.5)).toBe(3)
    expect(multiplySets(4, 2.5)).toBe(10)
  })

  it('非整数套 × 奇数量向上取整：1×0.5=1、1×1.5=2、3×0.5=2、1×2.5=3', () => {
    expect(multiplySets(1, 0.5)).toBe(1)
    expect(multiplySets(1, 1.5)).toBe(2)
    expect(multiplySets(3, 0.5)).toBe(2)
    expect(multiplySets(1, 2.5)).toBe(3)
  })
})

describe('buildMachineConfig 套数（sets）展开', () => {
  it('各码异套数：偶/奇数量裁片混合换算（g01=2 前片系 / g08=1 门襟系）', () => {
    const cfg = buildMachineConfig({
      numMap: { g01: 2, g08: 1 }, sizes: ['29', '30', '31'],
      sets: { '29': 2, '30': 0.5, '31': 1.5 },
    })
    expect(cfg.quantities).toEqual({
      // 偶数量直接相乘：2×2 / 2×0.5 / 2×1.5
      g01: { '29': 4, '30': 1, '31': 3 },
      // 奇数量：整数套直乘 1×2；非整数套向上取整 ceil(0.5)/ceil(1.5)
      g08: { '29': 2, '30': 1, '31': 2 },
    })
  })

  it('缺键回 1（未列码号 = 1 套 = 旧口径默认数量）', () => {
    const cfg = buildMachineConfig(
      { numMap: { g01: 2 }, sizes: ['29', '30'], sets: { '29': 3 } })
    expect(cfg.quantities.g01).toEqual({ '29': 6, '30': 2 })
  })

  it('labels 独有键（数量回退 0）× 任意套数 = 0（MS demand=0 跳过）', () => {
    const cfg = buildMachineConfig({
      numMap: { g01: 2 }, labels: { g09: '小表袋' },
      sizes: ['30'], sets: { '30': 1.5 },
    })
    expect(cfg.quantities.g09).toEqual({ '30': 0 })
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

  it('坏套数抛错（非 0.5 倍数/小于 0.5/NaN——输入侧键盘可自由键入）', () => {
    for (const bad of [1.3, 0, -0.5, Number.NaN]) {
      expect(() => buildMachineConfig(
        { numMap: { g01: 2 }, sizes: ['30'], sets: { '30': bad } }))
        .toThrow('套数非法')
    }
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
