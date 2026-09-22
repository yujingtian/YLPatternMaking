// 排料 numMap 清单纯逻辑金标（vitest；风格对齐 useNestSolve.test.ts）。
// 口径：后端 /api/nest 返回扁平 numMap {g码: 数量} + labels {g码: 中文名}
// （§10.3.2）；nestRows 排序 = g 码数字升序、labels 缺键回退「裁片」。
// 2026-09-22 入口收口：清单弹窗（NestResultModal）删除，nestRows 迁至
// useDraft 导出、供 startNestFlow 的 console.table 排查打印消费

import { describe, expect, it } from 'vitest'
import { nestRows } from './hooks/useDraft'
import type { NestResult } from './types'

function mk(numMap: Record<string, number>,
           labels: Record<string, string> = {}): NestResult {
  return { ok: true, file: '', filename: 'nest.dxf', numMap, labels }
}

describe('nestRows（排序 / 回退 / 透传）', () => {
  it('g 码数字升序（非字典序：g10 < g11 在 g02 后）', () => {
    const rows = nestRows(mk(
      { g11: 1, g01: 2, g10: 2, g02: 2 },
      { g01: '前片裁片', g02: '后片裁片', g10: '裤耳', g11: '门襟（双排）' },
    ))
    expect(rows.map((r) => r.g)).toEqual(['g01', 'g02', 'g10', 'g11'])
  })

  it('labels 缺键回退「裁片」、数量原样透传', () => {
    const rows = nestRows(mk({ g01: 2, g08: 1 }, { g01: '前片裁片' }))
    expect(rows).toEqual([
      { g: 'g01', label: '前片裁片', qty: 2 },
      { g: 'g08', label: '裁片', qty: 1 },
    ])
  })

  it('空 numMap -> 空行集', () => {
    expect(nestRows(mk({}))).toEqual([])
  })

  it('非规范 g 码（前缀大写可解析/无前缀）不炸、无前缀排末尾', () => {
    const rows = nestRows(mk({ g02: 2, G3: 2, x9: 2 }))
    expect(rows.map((r) => r.g)).toEqual(['g02', 'G3', 'x9'])
  })
})
