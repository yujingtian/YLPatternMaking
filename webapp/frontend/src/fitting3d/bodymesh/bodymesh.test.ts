// bodymesh 原生链路最小金标（2026-09-12 全身试验场）：parseTargetText
// 文本格式契约（dm→cm ×10）+ morphPositions 稀疏叠加/恒等。裁切链
// （parseBin/对齐/围度闭环）已随调节链退役，演进史见决策日志 §十一。
import { describe, expect, it } from 'vitest'
import { morphPositions } from './morph'
import { parseTargetText } from './native'
import type { MeshTarget } from './types'

// 手搓最小 asset：V=3（原始顶点号即索引）、两场（waist+ 动 v1；waist- 动 v2）
function tinyAsset(): { positions: Float32Array; targets: MeshTarget[] } {
  return {
    positions: new Float32Array([0, 0, 0, 10, 0, 0, 0, 20, 0]),
    targets: [
      { name: 'waist+', idx: new Uint32Array([1]), d: new Float32Array([1, 2, 3]) },
      { name: 'waist-', idx: new Uint32Array([2]), d: new Float32Array([-1, 0, 0.5]) },
    ],
  }
}

describe('bodymesh 原生链路', () => {
  it('parseTargetText：`idx dx dy dz`（dm）→ cm，跳过注释/空行', () => {
    const text = '# comment line\n\n1 0.1 0.2 0.3\n2 -1.5 0 0.05\nbad line\n'
    const { idx, d } = parseTargetText(text)
    expect(idx).toEqual([1, 2])
    expect(d).toEqual([1, 2, 3, -15, 0, 0.5])   // ×10 dm→cm
  })

  it('morph：w=0 逐位恒等；稀疏叠加精确；未列入顶点不动', () => {
    const a = tinyAsset()
    const out0 = morphPositions(a, {})
    expect(out0).toEqual(a.positions)                 // 逐位恒等
    const out = morphPositions(a, { 'waist+': 0.5 })
    expect(out[3]).toBeCloseTo(10.5, 6)
    expect(out[4]).toBeCloseTo(1, 6)
    expect(out[5]).toBeCloseTo(1.5, 6)
    expect(out[6]).toBe(0)                            // v2 不动
    expect(a.positions[3]).toBe(10)                   // 原数组不被改写
  })
})
