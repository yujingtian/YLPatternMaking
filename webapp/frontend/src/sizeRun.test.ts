// 推板档差表 <-> canonical 转换金标（vitest；头注释为手工演算，风格对齐
// 后端 tests/ 金标）。语义依据引擎 params/sizerun.py：步进归属 = 行间差
// gapAt(i)=band_of(行 i+1)、孤儿校验、thigh=0 特例；表格口径 = 基码锚定
// （d[k]：k>base 取 gapAt(k-1)、k<base 取 gapAt(k)、k=base 恒 0）——
// 详见 src/sizeRun.ts 头注释。

import { describe, expect, it } from 'vitest'
import {
  absoluteValues, emptySteps, fromGradeTable, normalizeSizeRun, rebaseTable,
  toGradeTable, validateTable, type GradeTable,
} from './sizeRun'
import type { MeasureKey, SizeRunSpec } from './types'

const STEP = { waist: 2.5, hip: 2.5, knee: 1.3, hem: 1.0, front_rise: 0.3,
               back_rise: 0.5, outseam: 1.2, thigh: 1.3 }
// examples/size_female_zhitong.toml 同源：6 码 27-32 单段、基码 30
const SPEC: SizeRunSpec = {
  enabled: true, base: '30', style: 'YL-A2708-F',
  order: ['27', '28', '29', '30', '31', '32'],
  band: [{ sizes: ['27', '28', '29', '30', '31', '32'], ...STEP }],
}

function steps(over: Partial<Record<MeasureKey, number>> = {}) {
  return { ...emptySteps(), ...over }
}

function table(rows: [string, ReturnType<typeof steps>][], baseIndex: number,
               style = 'TEST'): GradeTable {
  return { rows: rows.map(([label, s]) => ({ label, steps: s })), baseIndex,
           style }
}

describe('toGradeTable / fromGradeTable', () => {
  it('单段 27-32 canonical -> 表 -> canonical 恒等', () => {
    const t = toGradeTable(SPEC, '30')
    expect(t.rows.map((r) => r.label)).toEqual(SPEC.order)
    expect(t.baseIndex).toBe(3)
    // 基码锚定：锚位（行 3=30）恒 0；首码 27 在锚上方 = 与更大相邻码 28 之差
    expect(t.rows[3].steps.waist).toBe(0)
    expect(t.rows[0].steps.waist).toBe(2.5)
    expect(t.rows[4].steps.waist).toBe(2.5)   // 锚下方 = 与上一码差
    expect(fromGradeTable(t)).toEqual(SPEC)   // 往返恒等
  })

  it('金标：基码居中两段档差的 d 投影（用户场景 28-31、基码 30）', () => {
    // 手工演算：行间差 28->29 = 2.5、29->30 = 2.5、30->31 = 3.0
    //   （band_of(29)=band_of(30)=首段、band_of(31)=次段）
    //   锚 30 投影 -> d = [2.5, 2.5, 0, 3]
    const spec: SizeRunSpec = {
      enabled: true, base: '30', style: 'T', order: ['28', '29', '30', '31'],
      band: [{ sizes: ['28', '29', '30'], ...steps({ waist: 2.5 }) },
             { sizes: ['31'], ...steps({ waist: 3 }) }],
    }
    const t = toGradeTable(spec, '30')
    expect(t.rows.map((r) => r.steps.waist)).toEqual([2.5, 2.5, 0, 3])
    expect(fromGradeTable(t)).toEqual(spec)
  })

  it('spec=null 给单行基码空表', () => {
    const t = toGradeTable(null, '30')
    expect(t.rows).toHaveLength(1)
    expect(t.rows[0].label).toBe('30')
    expect(t.baseIndex).toBe(0)
  })

  it('档差 [2.5,2.5,3.0] -> 两 band，首码并入首段（孤儿免疫）', () => {
    // 手工演算：28/29/30 之间档差 2.5、30->31 档差 3.0 ->
    //   band1 sizes=[28,29,30]（首码 28 并入）waist=2.5
    //   band2 sizes=[31] waist=3.0
    const t = table([['28', steps()], ['29', steps({ waist: 2.5 })],
                     ['30', steps({ waist: 2.5 })],
                     ['31', steps({ waist: 3.0 })]], 0)
    const spec = fromGradeTable(t)
    expect(spec.base).toBe('28')
    expect(spec.band).toEqual([
      { sizes: ['28', '29', '30'], ...steps({ waist: 2.5 }) },
      { sizes: ['31'], ...steps({ waist: 3.0 }) },
    ])
  })

  it('非相邻等值档差不合并', () => {
    // gaps [2.5, 3.0, 2.5] -> 三个 band（等值连段才合并）
    const t = table([['28', steps()], ['29', steps({ waist: 2.5 })],
                     ['30', steps({ waist: 3.0 })],
                     ['31', steps({ waist: 2.5 })]], 0)
    expect(fromGradeTable(t).band).toHaveLength(3)
  })

  it('换基码重投影：放码关系不变（rebaseTable）', () => {
    // 手工演算：27-32 全段 2.5，锚 30 -> 28 后 d 仍全 2.5（锚位 0），
    // 解回行间差不变 -> band 与 SPEC 全等
    const t = rebaseTable(toGradeTable(SPEC, '30'), 1)
    expect(t.baseIndex).toBe(1)
    expect(t.rows[1].steps.waist).toBe(0)   // 新锚位恒 0
    expect(t.rows[3].steps.waist).toBe(2.5) // 原 30 行（现锚下方）可正常录差
    const spec = fromGradeTable(t)
    expect(spec.base).toBe('28')
    expect(spec.band).toEqual(SPEC.band)
  })

  it('单码表：band 空数组、style 空默认 noname', () => {
    const spec = fromGradeTable(table([['30', steps()]], 0, ''))
    expect(spec).toEqual({ enabled: true, base: '30', style: 'noname',
                           order: ['30'], band: [] })
  })

  it('档差 round(2)', () => {
    const spec = fromGradeTable(table(
      [['28', steps()], ['29', steps({ waist: 2.549999 })]], 0))
    expect(spec.band[0].waist).toBe(2.55)
  })
})

describe('absoluteValues', () => {
  const base = { waist: 77, hip: 99, knee: 47.6, hem: 37.5, front_rise: 29,
                 back_rise: 39, outseam: 106, thigh: 58 }
  it('金标：基码 30 腰 77 档差 2.5 -> 27=69.5 / 32=82', () => {
    const vals = absoluteValues(toGradeTable(SPEC, '30'), base)
    expect(vals['27'].waist).toBeCloseTo(77 - 3 * 2.5)
    expect(vals['30'].waist).toBeCloseTo(77)
    expect(vals['32'].waist).toBeCloseTo(77 + 2 * 2.5)
    expect(vals['27'].thigh).toBeCloseTo(58 - 3 * 1.3)
  })
  it('改基码重锚：28=面板 72 时 30=77、32=82（档差不变）', () => {
    const t = rebaseTable(toGradeTable(SPEC, '30'), 1)
    const vals = absoluteValues(t, { ...base, waist: 72 })
    expect(vals['28'].waist).toBeCloseTo(72)
    expect(vals['30'].waist).toBeCloseTo(77)
    expect(vals['32'].waist).toBeCloseTo(82)
  })
  it('thigh 特例：基码 thigh=0 时全码 0（档差不生效）', () => {
    const vals = absoluteValues(toGradeTable(SPEC, '30'), { ...base, thigh: 0 })
    for (const label of ['27', '30', '32']) expect(vals[label].thigh).toBe(0)
  })
})

describe('normalizeSizeRun', () => {
  it('模板 spec（enabled=false）也预填：enabled 归一 true', () => {
    const raw = { enabled: false, base: '30', style: 'YL-A2708-F',
                  order: ['27', '28'], band: [{ sizes: ['27', '28'],
                                                ...steps({ waist: 2.5 }) }] }
    const { spec, droppedOverrides } = normalizeSizeRun(raw)
    expect(droppedOverrides).toBe(false)
    expect(spec?.enabled).toBe(true)
    expect(spec?.base).toBe('30')
    expect(spec?.band[0].waist).toBe(2.5)
  })
  it('sizes 逐码覆盖：丢弃并返回标记', () => {
    const { spec, droppedOverrides } = normalizeSizeRun(
      { base: '30', order: ['30', '31'], band: [{ sizes: ['30', '31'] }],
        sizes: { '31': { waist: 90 } } })
    expect(droppedOverrides).toBe(true)
    expect(spec && 'sizes' in spec).toBe(false)
  })
  it('坏数据/旧存量（无键）-> null', () => {
    expect(normalizeSizeRun(undefined).spec).toBeNull()
    expect(normalizeSizeRun('junk').spec).toBeNull()
    expect(normalizeSizeRun({}).spec).toBeNull()
  })
})

describe('validateTable', () => {
  it('空标签 / 重复标签报错', () => {
    expect(validateTable(table([['30', steps()], ['  ', steps()]], 0)))
      .toContainEqual(expect.stringContaining('空码标签'))
    expect(validateTable(table([['30', steps()], ['30 ', steps()]], 0)))
      .toContainEqual(expect.stringContaining('重复'))
  })
  it('订单号：非 ASCII 报错、空放行（默认 noname）', () => {
    expect(validateTable(table([['30', steps()]], 0, '订单ABC')))
      .toContainEqual(expect.stringContaining('ASCII'))
    expect(validateTable(table([['30', steps()]], 0, ''))).toEqual([])
  })
})
