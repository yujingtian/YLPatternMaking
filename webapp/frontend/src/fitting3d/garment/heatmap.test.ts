// 穿台热力图金标（2026-09-18）：computeHeat 双通道 + heatColor 色带的
// 合成场单元验证（与 dressfield.test.ts 同款手搓几何——正多边形环构造
// 即知）。手工演算：
// · gap **带符号**（2026-09-19「穿不进需要在热力图中体现」：旧无符号
//   d−skin 把体内深点误读成正=松）：gap = (p−最近边界点)·外法线 − CORE_SKIN
//   ——环心粒子在体内：投影 = −5·cos(π/16) ≈ −4.904，gap ≈ −5.884 读红端；
//   边中点法线外 6cm 点：raw = 6−4.904 = 1.096，gap ≈ 0.116
// · strain：p0-p1 len 2 rest 1 → s=+1（+100%）；p1-p2 len 3 rest 4 →
//   s=−0.25；顶点取参与约束的 signed 最大值
// · 色带（修复反向后）：gap 0→红/2→绿/4→蓝；strain +6%→红/0→绿/−6%→蓝
//   （两通道同为红紧/绿适中/蓝松——首版 (s+max)/2max 把拉伸映到蓝端是
//   反的，已修，本文件钉死方向）
import { describe, expect, it } from 'vitest'
import type { DrapeSim } from './drape'
import { CORE_SKIN } from './core'
import { BodyField, type SliceRing } from './placement'
import { HEAT_PRIOR } from './priors'
import { computeHeat, heatColor, type HeatMode } from './heatmap'

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

// 合成 sim（computeHeat 只读 pos/field/yLift/parts[].{offset,mesh.dist}）
const mkSim = (pos: number[], opts: {
  field?: BodyField | null, yLift?: number, dist?: number[], offset?: number,
} = {}): DrapeSim => ({
  pos: new Float32Array(pos),
  field: opts.field ?? null,
  yLift: opts.yLift ?? 0,
  parts: opts.dist
    ? [{ offset: opts.offset ?? 0, mesh: { dist: new Float32Array(opts.dist) } }]
    : [],
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

  it('field 为 null（旁挂自由垂）：全 0 中性', () => {
    const v = computeHeat(mkSim([0, 0, 0, 1, 1, 1]), 'gap')
    expect(Array.from(v)).toEqual([0, 0])
  })
})

describe('computeHeat 应变通道', () => {
  it('逐顶点 = 参与 dist 约束 (len−rest)/rest 的 signed 最大值', () => {
    // p0(0,0,0)-p1(2,0,0) len 2 rest 1 → +1；p1-p2(2,3,0) len 3 rest 4 → −0.25
    const sim = mkSim([0, 0, 0, 2, 0, 0, 2, 3, 0], { dist: [0, 1, 1, 1, 2, 4] })
    const v = computeHeat(sim, 'strain')
    expect(v[0]).toBeCloseTo(1, 10)
    expect(v[1]).toBeCloseTo(1, 10)   // max(+1, −0.25)
    expect(v[2]).toBeCloseTo(-0.25, 10)
  })

  it('rest=0 守卫 s=0；无约束顶点 NaN 哨兵 → 0', () => {
    // p0-p1 同位 rest 0 → 0；p2 不参与任何约束 → 0
    const sim = mkSim([1, 1, 1, 1, 1, 1, 5, 5, 5], { dist: [0, 1, 0] })
    const v = computeHeat(sim, 'strain')
    expect(Array.from(v)).toEqual([0, 0, 0])
  })

  it('offset 平移：dist 存 part 局部号、消费方加偏移（与 drape 同口径）', () => {
    // 第二 part offset=2：约束局部 (0,1) rest 4 → 全局 (2,3) len 2 → −0.5
    const sim = mkSim([0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0],
      { dist: [0, 1, 4], offset: 2 })
    const v = computeHeat(sim, 'strain')
    expect(v[0]).toBe(0)               // 未参与 → 0
    expect(v[2]).toBeCloseTo(-0.5, 10)
    expect(v[3]).toBeCloseTo(-0.5, 10)
  })
})

describe('heatColor 色带（红紧 / 绿适中 / 蓝松，两通道同向）', () => {
  const RED: [number, number, number] = [1.0, 0.25, 0.2]
  const GREEN: [number, number, number] = [0.3, 0.8, 0.35]
  const BLUE: [number, number, number] = [0.25, 0.45, 0.95]

  const eq = (a: [number, number, number], b: [number, number, number]) => {
    expect(a[0]).toBeCloseTo(b[0], 10)
    expect(a[1]).toBeCloseTo(b[1], 10)
    expect(a[2]).toBeCloseTo(b[2], 10)
  }

  it('gap：0 红（贴身/穿透同端）/ 半值绿 / 满值蓝，越界钳端', () => {
    const mode: HeatMode = 'gap'
    eq(heatColor(-1, mode), RED)   // 穿透 → 红
    eq(heatColor(0, mode), RED)
    eq(heatColor(HEAT_PRIOR.gapMax / 2, mode), GREEN)
    eq(heatColor(HEAT_PRIOR.gapMax, mode), BLUE)
    eq(heatColor(99, mode), BLUE)  // 越界钳
  })

  it('strain：+max 拉伸绷紧红 / 0 自然绿 / −max 压缩堆布蓝（方向钉死）', () => {
    const mode: HeatMode = 'strain'
    eq(heatColor(HEAT_PRIOR.strainMax, mode), RED)
    eq(heatColor(0.2, mode), RED)   // 越界钳
    eq(heatColor(0, mode), GREEN)
    eq(heatColor(-HEAT_PRIOR.strainMax, mode), BLUE)
    eq(heatColor(-0.2, mode), BLUE)
    // +3% = t 0.25 → 红↔绿中点（精确演算）
    eq(heatColor(0.03, mode),
      [(RED[0] + GREEN[0]) / 2, (RED[1] + GREEN[1]) / 2, (RED[2] + GREEN[2]) / 2])
  })
})
