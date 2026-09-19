// 穿台热力图金标（2026-09-18；2026-09-19 应变通道移除后恒间隙通道）：
// computeHeat + heatColor 色带的合成场单元验证（与 dressfield.test.ts
// 同款手搓几何——正多边形环构造即知）。手工演算：
// · gap **带符号**（2026-09-19「穿不进需要在热力图中体现」：旧无符号
//   d−skin 把体内深点误读成正=松）：gap = (p−最近边界点)·外法线 − CORE_SKIN
//   ——环心粒子在体内：投影 = −5·cos(π/16) ≈ −4.904，gap ≈ −5.884 读红端；
//   边中点法线外 6cm 点：raw = 6−4.904 = 1.096，gap ≈ 0.116
// · 色带：gap 0→红/2→绿/4→蓝（红紧/绿适中/蓝松）
// · （strain 通道用例随通道移除删除，2026-09-19；恢复见 git 史）
import { describe, expect, it } from 'vitest'
import type { DrapeSim } from './drape'
import { CORE_SKIN } from './core'
import { BodyField, type SliceRing } from './placement'
import { HEAT_PRIOR } from './priors'
import { computeHeat, heatColor } from './heatmap'

// 正 n 边形环（质心=圆心、包围半径=r；同 dressfield.test.ts 构造）
const ring = (cx: number, cz: number, r: number, n = 16): SliceRing => {
  const pts = new Float64Array(2 * n)
  for (let k = 0; k < n; k++) {
    const th = (k / n) * 2 * Math.PI
    pts[2 * k] = cx + r * Math.cos(th)
    pts[2 * k + 1] = cz + r * Math.sin(th)
  }
  return { pts, cx, cz, r }
}

const mkField = (slices: SliceRing[][]): BodyField =>
  new BodyField(new Float32Array(slices.length * 8), slices.length, 0.5, 8, slices, 0)

// 合成 sim（computeHeat 只读 pos/field/yLift）
const mkSim = (pos: number[], opts: {
  field?: BodyField | null, yLift?: number,
} = {}): DrapeSim => ({
  pos: new Float32Array(pos),
  field: opts.field ?? null,
  yLift: opts.yLift ?? 0,
  parts: [],
} as unknown as DrapeSim)

describe('computeHeat 间隙通道', () => {
  // 单行环场：row 0（y=0）一枚 r=5 环；row 1 空（无环行 → 松端）
  const field = mkField([[ring(0, 0, 5)], []])

  it('环心粒子（体内深点）：gap 带符号读负 = 穿透红端', () => {
    const v = computeHeat(mkSim([0, 0, 0], { field }), 'gap')
    expect(v.length).toBe(1)
    expect(v[0]).toBeCloseTo(-5 * Math.cos(Math.PI / 16) - CORE_SKIN, 6)
  })

  it('边中点法线外近点：gap = 径向距 − 到边投影 − 接触壳（体外正）', () => {
    // 边 0-1 中点方向 11.25°、半径 6 的点：垂足 = 边中点（正多边形对称），
    // 外法线 = 该径向 → raw = 6 − 5·cos(π/16)
    const th = Math.PI / 16
    const v = computeHeat(
      mkSim([6 * Math.cos(th), 0, 6 * Math.sin(th)], { field }), 'gap')
    expect(v[0]).toBeCloseTo(6 - 5 * Math.cos(Math.PI / 16) - CORE_SKIN, 6)
  })

  it('环外超 margin / 无环行：钳 gapMax 松端；yLift 换算回纸样系查行', () => {
    // 环外远点（d=15 > margin 0.98+4）：quick reject → 松端
    const far = computeHeat(mkSim([20, 0, 0], { field }), 'gap')
    expect(far[0]).toBe(HEAT_PRIOR.gapMax)
    // y=0.5 → 行 1 空环 → 松端
    const empty = computeHeat(mkSim([0, 0.5, 0], { field }), 'gap')
    expect(empty[0]).toBe(HEAT_PRIOR.gapMax)
    // 世界系 y 扣 yLift 查同一行：环心 gap 与首例逐位相等
    const lifted = computeHeat(mkSim([0, 7.6, 0], { field, yLift: 7.6 }), 'gap')
    expect(lifted[0]).toBeCloseTo(-5 * Math.cos(Math.PI / 16) - CORE_SKIN, 6)
  })

  it('field 为 null：全 0 中性', () => {
    const v = computeHeat(mkSim([0, 0, 0, 1, 1, 1]), 'gap')
    expect(Array.from(v)).toEqual([0, 0])
  })
})

describe('heatColor 色带（红紧 / 绿适中 / 蓝松）', () => {
  const RED: [number, number, number] = [1.0, 0.25, 0.2]
  const GREEN: [number, number, number] = [0.3, 0.8, 0.35]
  const BLUE: [number, number, number] = [0.25, 0.45, 0.95]

  const eq = (a: [number, number, number], b: [number, number, number]) => {
    expect(a[0]).toBeCloseTo(b[0], 10)
    expect(a[1]).toBeCloseTo(b[1], 10)
    expect(a[2]).toBeCloseTo(b[2], 10)
  }

  it('gap：0 红（贴身/穿透同端）/ 半值绿 / 满值蓝，越界钳端', () => {
    eq(heatColor(-1, 'gap'), RED)   // 穿透 → 红
    eq(heatColor(0, 'gap'), RED)
    eq(heatColor(HEAT_PRIOR.gapMax / 2, 'gap'), GREEN)
    eq(heatColor(HEAT_PRIOR.gapMax, 'gap'), BLUE)
    eq(heatColor(99, 'gap'), BLUE)  // 越界钳
  })
})
