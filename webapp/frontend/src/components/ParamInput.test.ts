// 数字参数清空交互纯逻辑金标（vitest node env）：2026-09-29 修「删不掉」
// （清空被 schema 默认值立刻顶回）。DOM 交互（编辑期持空显示、失焦、
// 外部落值解除覆写）由人工/Playwright 覆盖（NestSolveModal.test.ts 同款
// 口径），此处锚定提交与显示的纯决策：
// - 非可空清空提交 undefined（未设置态）：JSON.stringify 丢键 -> 载荷与
//   localStorage 暂存均不含该键，引擎回落自身默认；绝不提交 null——
//   引擎 from_dict 对 None 直通会撞类型校验（旧口径的隐藏雷）
// - 可空清空提交 null（自动）
// - 编辑期空态覆写优先于一切回落（受控 InputNumber 不回弹的机制本体）
import { describe, expect, it } from 'vitest'
import { emptyNumberCommit, numberDisplayValue } from './ParamInput'
import type { ParamSpec } from '../types'

function spec(nullable: boolean): ParamSpec {
  return { key: 'watch_pocket_width', label: '袋口宽', type: 'number',
           default: 7.5, nullable }
}

describe('emptyNumberCommit（清空提交值）', () => {
  it('非可空 -> undefined：JSON 序列化丢键（载荷/暂存不含该键）', () => {
    expect(emptyNumberCommit(spec(false))).toBeUndefined()
    expect(JSON.stringify({ w: emptyNumberCommit(spec(false)) })).toBe('{}')
  })

  it('可空 -> null（自动）', () => {
    expect(emptyNumberCommit(spec(true))).toBeNull()
  })
})

describe('numberDisplayValue（清空显示值）', () => {
  it('编辑期空态覆写优先：清空后显示恒空，不受默认值回落影响', () => {
    expect(numberDisplayValue(spec(false), 8, true)).toBeNull()
    expect(numberDisplayValue(spec(true), null, true)).toBeNull()
  })

  it('非可空 value 缺失回落 schema 默认（未清空时的旧显示口径不变）', () => {
    expect(numberDisplayValue(spec(false), undefined, false)).toBe(7.5)
    expect(numberDisplayValue(spec(false), null, false)).toBe(7.5)
  })

  it('可空 value 缺失 = 空态（placeholder「自动」）', () => {
    expect(numberDisplayValue(spec(true), null, false)).toBeNull()
  })

  it('正常数值直通', () => {
    expect(numberDisplayValue(spec(false), 8.2, false)).toBe(8.2)
  })
})
