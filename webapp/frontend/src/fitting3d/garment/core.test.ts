// 撑型芯金标（v3，2026-09-17 八期整裤缝合：**两腿分离三实体**——躯干管
// + 左右腿管，各实体独立水密）：躯干管（fork→腰+8 圆环）；腿管（hem−1.5
// →fork 圆环，轴 ±(r+gapHalf)，gapHalf 从 fork LEG_GAP_MIN 张开到
// LEG_GAP_TAPER 以下 LEG_GAP_HALF）——**裆下两腿真分离**，腿间空隙给内缝
// 焊线与裆交叉点安身。腿管周长逐站锁定 girth_finished − 2π·skin（摆位壳
// core+skin 恰落纸样围度 = 「圆筒按构造成立」的数值口径）。
// v2 花生整环（裆下双瓣+腰谷单环）2026-09-17 证伪退役：径向碰撞场下
// 腰谷仍是实心桥（星形实心），前/后内缝边隔桥相望焊不上、绕腿瓣外侧
// 闭拢把裤腿拖成侧挂门帘（实测 inseam 终态 θ≈±90°、r≈腿瓣外）——详见
// core.ts 头注与决策日志八期条目。
// 夹具 = 引擎 payload（fixture_fitting.json）。
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../types'
import { buildCore, buildLegAxis, CORE_SKIN, LEG_GAP_HALF, LEG_GAP_MIN } from './core'
import { buildBodyField } from './placement'
import { sliceLoops } from '../bodymesh/slice'

const HERE = import.meta.dirname   // src/fitting3d/garment

const M1: FittingResult = JSON.parse(
  readFileSync(`${HERE}/fixture_fitting.json`, 'utf8'))

const st = (r: FittingResult, key: string) =>
  r.body.stations.find((s) => s.key === key)!
const coreR = (g: number) => g / (2 * Math.PI) - CORE_SKIN
const TWO_SKIN = 2 * Math.PI * CORE_SKIN

// 站高切片环（水密单面网格点度恒 2，闭合稳定）
const loopsAt = (r: FittingResult, y: number) => {
  const core = buildCore(r)
  return sliceLoops(core.positions, core.indices, y).filter((l) => l.closed)
}

describe('撑型芯：v3 两腿分离三实体（躯干管 + 左右腿管）', () => {
  it('可建；waist/hip 行恰 1 环（躯干）、knee/hem 行恰 2 环（左右腿管）', () => {
    const core = buildCore(M1)
    expect(core.positions.length).toBeGreaterThan(0)
    expect(core.indices.length % 3).toBe(0)
    for (const key of ['waist', 'hip'] as const) {
      expect(loopsAt(M1, st(M1, key).y)).toHaveLength(1)
    }
    for (const key of ['knee', 'hem'] as const) {
      expect(loopsAt(M1, st(M1, key).y)).toHaveLength(2)
    }
    // fork 行（= front 裆尖 y 78）也恰 2 环：腿管上延过 fork，裆交叉
    // 口袋留给分离腿管（躯干环不出现在 fork 带）
    expect(loopsAt(M1, st(M1, 'crotch').y)).toHaveLength(2)
  })

  it('腿管周长逐站锁定：每环 ≈ girth_finished − 2π·skin（左右对称）', () => {
    // M1 手工演算（skin 0.98）：knee 46 → 每腿 46−6.16=39.8；hem 34 →
    // 27.8（多边形周长比真值低 ~0.15%）
    for (const key of ['knee', 'hem'] as const) {
      const loops = loopsAt(M1, st(M1, key).y)
      const [l, r] = [...loops].sort((a, b) => a.cx - b.cx)
      expect(Math.abs(l.cx + r.cx)).toBeLessThan(1e-6)   // 左右镜像
      for (const loop of [l, r]) {
        expect(Math.abs(loop.girth
          - (st(M1, key).girth_finished! - TWO_SKIN))).toBeLessThan(0.4)
      }
    }
  })

  it('腿间隙：fork 处 ≈ 2×LEG_GAP_MIN、张开后 ≈ 2×LEG_GAP_HALF（腿内侧留白）', () => {
    const axis = buildLegAxis(M1)
    const fork = st(M1, 'crotch').y
    // fork−1（锥形刚起）：间隙 = 2×(GAP_MIN + (GAP_HALF−GAP_MIN)/12)
    const gapNear = 2 * (axis.cAt(fork - 1) - axis.rAt(fork - 1))
    expect(gapNear).toBeGreaterThan(2 * LEG_GAP_MIN - 0.05)
    expect(gapNear).toBeLessThan(2 * LEG_GAP_MIN + 0.35)
    // knee（锥形完成区）：间隙 = 2×GAP_HALF
    const yK = st(M1, 'knee').y
    const gapFar = 2 * (axis.cAt(yK) - axis.rAt(yK))
    expect(Math.abs(gapFar - 2 * LEG_GAP_HALF)).toBeLessThan(1e-9)
    // 芯网格实测：knee 行两环内沿距 ≈ gapFar（多边形离散 ±0.1）
    const loops = loopsAt(M1, yK)
    const [l, r] = [...loops].sort((a, b) => a.cx - b.cx)
    let inner = Infinity
    for (const p of l.pts) for (const q of r.pts) {
      inner = Math.min(inner, Math.hypot(p.x - q.x, p.z - q.z))
    }
    expect(Math.abs(inner - gapFar)).toBeLessThan(0.15)
  })

  it('支撑场：裆上圆环处处等值（±0.15cm），臀站 ≈ coreR(hip)', () => {
    const core = buildCore(M1)
    const field = buildBodyField(core.positions, core.indices)
    const hip = st(M1, 'hip')
    const target = coreR(hip.girth_finished!)
    for (let k = 0; k < 8; k++) {
      const th = (k / 8) * 2 * Math.PI
      expect(Math.abs(field.radiusAt(hip.y, th) - target)).toBeLessThan(0.15)
    }
  })

  it('裆圆角带：底行前后收拢成扁椭圆、左右保持髋宽；臀站恢复全圆', () => {
    // 用户报障「裆部前后片生硬凸起」的芯侧根因 = 平底全半径圆柱，圆角
    // 带前后（z）收拢（真身形耻骨/会阴区 z 小、左右髋仍宽）。用切片环
    // 取最大环（躯干环——该行腿管上延段也在，不能裸采顶点）
    const crotch = st(M1, 'crotch')
    const ringAt = (y: number) => {
      const loops = loopsAt(M1, y)
      return loops.reduce((m, l) => (l.girth > m.girth ? l : m))
    }
    const bot = ringAt(crotch.y + 2.5)
    const zHalf = (Math.max(...bot.pts.map((p) => p.z))
      - Math.min(...bot.pts.map((p) => p.z))) / 2
    const xHalf = (Math.max(...bot.pts.map((p) => p.x))
      - Math.min(...bot.pts.map((p) => p.x))) / 2
    expect(zHalf).toBeLessThan(0.4 * xHalf)        // 前后收拢（扁椭圆）
    expect(xHalf).toBeGreaterThan(coreR(96) - 1)   // 左右不掐（髋宽保留）
    // 臀站恢复全圆（圆角带到臀为止）：x/z 半宽比 ≈ 1
    const hipRing = ringAt(st(M1, 'hip').y)
    const hz = (Math.max(...hipRing.pts.map((p) => p.z))
      - Math.min(...hipRing.pts.map((p) => p.z))) / 2
    const hx = (Math.max(...hipRing.pts.map((p) => p.x))
      - Math.min(...hipRing.pts.map((p) => p.x))) / 2
    expect(Math.abs(hz / hx - 1)).toBeLessThan(0.02)
  })

  it('裆站左右不掐腰（v2.1 口径的圆角带版）：臀→裆带侧向宽度 ≥ 臀宽 −4', () => {
    // 装站躯干圆取 max(臀, 2×腿)（M1：max(96, 2×58)=116）——侧向（x）
    // 不掐；前后（z）在圆角带收拢属设计（上用例）
    const hip = st(M1, 'hip'), crotch = st(M1, 'crotch')
    const core = buildCore(M1)
    const halfWAt = (yq: number): number => {
      let m = 0
      for (let i = 1; i < core.positions.length; i += 3) {
        if (Math.abs(core.positions[i] - yq) > 0.6) continue
        m = Math.max(m, Math.abs(core.positions[i - 1]))
      }
      return m
    }
    const hipW = halfWAt(hip.y)
    for (let y = crotch.y + 4; y <= hip.y; y += 2) {
      expect(halfWAt(y)).toBeGreaterThan(hipW - 4)
    }
  })
})
