// M2 松量读数金标（方案 .claude/plans/3d试穿二期-复活.md）：
// 1) garmentLoops 容差闭环——缝合对是物理约束**不是共享顶点**，跨缝围度
//    全靠端点距离容差 greedy 链；缝隙 0.4（实测缝合残差 <0.5cm）必闭环、
//    缝隙 5（腿间净距 ≥2cm）绝不误链。
// 2) easeRows 挑环口径与 readGirth 一致（body=最大环 / leg=最右大环）、
//    crotch 分叉站跳过、真空高度 null 传染、ease=成衣−人台。
// 3) markDenimBend 增硬窗（裆/膝 ±denimRegionSpan 含边界）。
// 夹具 = 合成方筒（轴 Y、每面 2 三角形）——独立顶点模拟缝合对（位置
// 近重合不共享索引）；共享顶点方筒模拟人台水密网格（readGirth 精确链）。
import { describe, expect, it } from 'vitest'
import { easeRows, garmentLoops } from './ease'
import { markDenimBend } from './seams'
import type { Garment } from './seams'
import type { ClothMesh } from './mesh'
import { SOLVER_PRIOR } from './priors'
import type { FittingStation } from '../../types'

// 方筒（y∈[0,10]、半宽 r、面间缝隙 g、中心 cx）：4 竖面各 2 三角形，
// 每面两端各缩 g/2 —— 相邻面切片端点距离 = g/√2（缝合残差模拟）。
// 顶点全部独立（缝合对口径：近重合不共享索引）
function squareTube(
  r: number, g: number, cx = 0,
): { pos: Float32Array; tri: Uint32Array } {
  const pos: number[] = [], tri: number[] = []
  const quad = (a: number[], b: number[], c: number[], d: number[]) => {
    const i = pos.length / 3
    pos.push(...a, ...b, ...c, ...d)
    tri.push(i, i + 1, i + 2, i, i + 2, i + 3)
  }
  const e = g / 2
  quad([cx - r + e, 0, r], [cx + r - e, 0, r], [cx + r - e, 10, r], [cx - r + e, 10, r])
  quad([cx + r, 0, r - e], [cx + r, 0, -r + e], [cx + r, 10, -r + e], [cx + r, 10, r - e])
  quad([cx + r - e, 0, -r], [cx - r + e, 0, -r], [cx - r + e, 10, -r], [cx + r - e, 10, -r])
  quad([cx - r, 0, -r + e], [cx - r, 0, r - e], [cx - r, 10, r - e], [cx - r, 10, -r + e])
  return { pos: new Float32Array(pos), tri: new Uint32Array(tri) }
}

// 共享顶点方筒（人台口径：8 顶点水密盒，角竖边由相邻面共享，
// readGirth 共享端点链精确闭环）；y=5 切片围度 = 8r 精确
function sharedTube(r: number, cx = 0): { pos: Float32Array; tri: Uint32Array } {
  const pos = new Float32Array([
    cx - r, 0, -r, cx + r, 0, -r, cx + r, 0, r, cx - r, 0, r,
    cx - r, 10, -r, cx + r, 10, -r, cx + r, 10, r, cx - r, 10, r,
  ])
  const tri = new Uint32Array([
    0, 1, 5, 0, 5, 4,   // back（z=−r）
    1, 2, 6, 1, 6, 5,   // right
    2, 3, 7, 2, 7, 6,   // front
    3, 0, 4, 3, 4, 7,   // left
  ])
  return { pos, tri }
}

describe('garmentLoops：容差链跨缝闭环', () => {
  it('面缝隙 0.4（缝合残差量级）：链成单环，围度≈真周长', () => {
    const r = 10, g = 0.4
    const { pos, tri } = squareTube(r, g)
    const loops = garmentLoops(pos, tri, 5, 1.5)
    expect(loops.length).toBe(1)
    // 真周长 = 4×(2r−g) + 4×(g/√2)（四面 + 四角跨缝对角跳）；
    // 链上角点连线抄近路，偏差 <0.6cm（每面仅 2 段的真夹具下限）
    const trueG = 4 * (2 * r - g) + (4 * g) / Math.SQRT2
    expect(Math.abs(loops[0].girth - trueG)).toBeLessThan(0.6)
    // cx = 链点均值：每角只收一侧端点（另一侧是被跳过的近重合点），
    // 天然偏 ~1.2cm——挑环判据用途（环间距 ≥30cm）无碍
    expect(Math.abs(loops[0].cx)).toBeLessThan(2)
  })

  it('面缝隙 5（腿间净距量级）：不误链，无闭环', () => {
    const { pos, tri } = squareTube(10, 5)
    expect(garmentLoops(pos, tri, 5, 1.5)).toEqual([])
  })

  it('小环过滤：围度 ≤25 不计（碎片防御，口径同 readGirth BIG）', () => {
    const { pos, tri } = squareTube(3, 0.4)   // 周长 ~24 < 25
    expect(garmentLoops(pos, tri, 5, 1.5)).toEqual([])
  })
})

describe('easeRows：逐站读数与挑环口径', () => {
  const r = 10, g = 0.4
  // 整裤 = 躯干筒（cx=0）+ 右腿筒（cx=30，半宽 6 → 围度 ~46>25 计环）
  const big = squareTube(r, g, 0)
  const leg = squareTube(6, g, 30)
  const pos = new Float32Array(big.pos.length + leg.pos.length)
  pos.set(big.pos)
  pos.set(leg.pos, big.pos.length)
  const tri = new Uint32Array(big.tri.length + leg.tri.length)
  for (let t = 0; t < leg.tri.length; t++) leg.tri[t] += big.pos.length / 3
  tri.set(big.tri)
  tri.set(leg.tri, big.tri.length)
  const garment = { triAll: tri } as unknown as Garment
  const body = sharedTube(9)                  // 人台筒围度 72
  const st = (key: FittingStation['key'], per: 'body' | 'leg',
    y = 5): FittingStation => ({ key, y, per, girth_finished: 100 })

  it('body 站挑最大环、leg 站挑最右环，ease=成衣−人台、纸样直通', () => {
    const rows = easeRows(garment, pos,
      [st('waist', 'body'), st('knee', 'leg')],
      (y) => y, body.pos, body.tri)
    expect(rows.map((x) => x.key)).toEqual(['waist', 'knee'])
    const w = rows[0]
    // body 站：两环里取最大（躯干筒 ~79.5 而非腿筒 ~46）
    const trueG = 4 * (2 * r - g) + (4 * g) / Math.SQRT2
    expect(Math.abs(w.sim! - trueG)).toBeLessThan(0.6)
    expect(w.body).toBeCloseTo(72, 6)         // 人台 4×2×9
    expect(w.ease!).toBeCloseTo(w.sim! - 72, 6)
    expect(w.pattern).toBe(100)
    const k = rows[1]
    // leg 站：取最右（cx=30 腿筒 ~47）而非最大（躯干筒 ~79.5）
    const legTrueG = 4 * (2 * 6 - g) + (4 * g) / Math.SQRT2
    expect(Math.abs(k.sim! - legTrueG)).toBeLessThan(0.6)
    expect(k.body).toBeCloseTo(72, 6)
    expect(k.ease!).toBeCloseTo(k.sim! - 72, 6)
  })

  it('crotch 分叉站跳过；真空高度 sim/body 全 null 且 ease 传染', () => {
    const rows = easeRows(garment, pos,
      [st('crotch', 'body'), st('hem', 'leg', 50)],
      (y) => y, body.pos, body.tri)
    expect(rows.map((x) => x.key)).toEqual(['hem'])   // crotch 不出行
    const hem = rows[0]
    expect(hem.sim).toBeNull()
    expect(hem.body).toBeNull()
    expect(hem.ease).toBeNull()
    expect(hem.pattern).toBe(100)
  })
})

describe('markDenimBend：丹宁裆/膝增硬窗', () => {
  it('窗内 denimBendStiffness、窗外全局值、±span 边界含入（≤）', () => {
    const span = SOLVER_PRIOR.denimRegionSpan
    const crotchY = 100, kneeY = 130
    // 5 条弯曲边（[i,j,rest]），按「边中点 pattern-y」手工布置（顶点 y
    // 反推 = 中点×2−对端）：裆心 / 膝心 / 两窗外 115 / 恰在裆窗上界 / 窗外 1
    const ys = [crotchY, crotchY, kneeY, kneeY, 115, 115,
      crotchY + 2 * span, crotchY, crotchY + 2 * (span + 1), crotchY]
    const xy = new Float64Array(ys.length * 2)
    for (let i = 0; i < ys.length; i++) { xy[2 * i] = i; xy[2 * i + 1] = ys[i] }
    const bend = new Float32Array((ys.length / 2) * 3)   // [i,j,rest] 平铺
    for (let e = 0; e < ys.length / 2; e++) {
      bend[3 * e] = 2 * e; bend[3 * e + 1] = 2 * e + 1; bend[3 * e + 2] = 1
    }
    const mesh = { xy, bend } as unknown as ClothMesh
    markDenimBend(mesh, { crotch: crotchY, knee: kneeY })
    const k = mesh.bendKArr!
    expect(k.length).toBe(ys.length / 2)
    // Float32Array 存储有精度取整，用 toBeCloseTo
    expect(k[0]).toBeCloseTo(SOLVER_PRIOR.denimBendStiffness, 6)   // 裆窗中心
    expect(k[1]).toBeCloseTo(SOLVER_PRIOR.denimBendStiffness, 6)   // 膝窗中心
    expect(k[2]).toBeCloseTo(SOLVER_PRIOR.bendStiffness, 6)        // 两窗外
    expect(k[3]).toBeCloseTo(SOLVER_PRIOR.denimBendStiffness, 6)   // |mid−crotch|=span 含入
    expect(k[4]).toBeCloseTo(SOLVER_PRIOR.bendStiffness, 6)        // span+1 出窗
  })
})
