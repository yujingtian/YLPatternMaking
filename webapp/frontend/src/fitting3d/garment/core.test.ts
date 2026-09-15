// 撑型芯金标（2026-09-14 解耦定型，v2 单一水密花生网格）：
//   腰臀段圆环 / 裆下花生整环（双瓣 + 腰谷，单一闭环非两管并置——
//   管并置的相切刀口/交叠符号陷阱/留槽捷径三条死路见 core.ts 头注）；
//   芯周长逐站锁定 girth_finished（圆 2πR−2π·skin / 花生整环 2g−2×2π·skin，
//   布接触壳 core+skin 恰落纸样围度 = 「圆筒按构造成立」的数值口径）；
//   瓣沿 ±x、腰谷在 ±z（前后中线）；支撑场裆上处处等值。
// 夹具 = 引擎 payload 双 fixture（M1 默认 / yoke 整裤）。
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../types'
import { buildCore } from './core'
import { SOLVER_PRIOR } from './priors'
import { buildBodyField } from './placement'
import { sliceLoops } from '../bodymesh/slice'

const HERE = import.meta.dirname   // src/fitting3d/garment

const M1: FittingResult = JSON.parse(
  readFileSync(`${HERE}/fixture_fitting.json`, 'utf8'))
const YOKE: FittingResult = JSON.parse(
  readFileSync(`${HERE}/fixture_fitting_yoke.json`, 'utf8'))
// 弯腰头+口袋挖削+袋贴（用户实测形态 2026-09-15，hip 100 / thigh 63.5）
const POCKET: FittingResult = JSON.parse(
  readFileSync(`${HERE}/fixture_fitting_curved_pocket.json`, 'utf8'))

const st = (r: FittingResult, key: string) =>
  r.body.stations.find((s) => s.key === key)!
const coreR = (g: number) => g / (2 * Math.PI) - SOLVER_PRIOR.collisionSkin
const TWO_SKIN = 2 * Math.PI * SOLVER_PRIOR.collisionSkin

// 站高切片环（水密单面网格点度恒 2，闭合稳定）
const loopsAt = (r: FittingResult, y: number) => {
  const core = buildCore(r)
  return sliceLoops(core.positions, core.indices, y).filter((l) => l.closed)
}

describe('撑型芯：纸样围度逐站成芯（腰臀圆环 + 裆下花生整环）', () => {
  it('双 fixture 可建；各站高恰一个闭环（花生也是单环拓扑）', () => {
    for (const r of [M1, YOKE]) {
      const core = buildCore(r)
      expect(core.positions.length).toBeGreaterThan(0)
      expect(core.indices.length % 3).toBe(0)
      for (const key of ['waist', 'hip', 'knee', 'hem'] as const) {
        expect(loopsAt(r, st(r, key).y)).toHaveLength(1)
      }
    }
  })

  it('站高芯周 ≈ 纸样围度 − skin 壳（圆 2π·skin / 花生 2×2π·skin）', () => {
    // M1 手工演算（skin 0.98）：hip 96 → 芯围 96−6.16=89.8；
    // knee 46 → 花生整环 2×46−12.3=79.7（多边形周长比真值低 ~0.3%）
    const hip = loopsAt(M1, st(M1, 'hip').y)[0]
    expect(Math.abs(hip.girth
      - (st(M1, 'hip').girth_finished! - TWO_SKIN))).toBeLessThan(0.8)
    const knee = loopsAt(M1, st(M1, 'knee').y)[0]
    expect(Math.abs(knee.girth
      - (2 * st(M1, 'knee').girth_finished! - 2 * TWO_SKIN)))
      .toBeLessThan(0.8)
  })

  it('花生瓣沿 ±x、腰谷在 ±z：膝站宽 ≈ 双瓣并排、深 ≈ 单瓣直径', () => {
    const y = st(M1, 'knee').y
    const core = buildCore(M1)
    const xs: number[] = [], zs: number[] = []
    for (let i = 1; i < core.positions.length; i += 3) {
      if (Math.abs(core.positions[i] - y) < 1.05) {
        xs.push(core.positions[i - 1]); zs.push(core.positions[i + 1])
      }
    }
    const w = Math.max(...xs) - Math.min(...xs)
    const d = Math.max(...zs) - Math.min(...zs)
    // 双圆腿并排：宽 ≈ 2×腿直径、深 ≈ 1×腿直径（腰谷只浅于瓣顶、不塌到轴）
    expect(w).toBeGreaterThan(2 * coreR(st(M1, 'knee').girth_finished!) - 0.6)
    expect(Math.abs(d - w / 2)).toBeLessThan(2)
    // 腰谷不塌到轴：x≈0 处（腰谷点）的 |z| > 1cm（两腿间实心连接）
    const waistZ = zs.filter((_, k) => Math.abs(xs[k]) < 1).map(Math.abs)
    expect(waistZ.length).toBeGreaterThan(0)
    expect(Math.min(...waistZ)).toBeGreaterThan(1)
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

  it('裆站不掐腰（v2.1）：臀→裆带芯周长 ≥ 臀周 −4，无蜂腰', () => {
    // 用户实测（hip 100 / thigh 63.5）：旧值躯干圆在裆站取单腿半径，
    // 周长 95.4(臀) → 69.2(裆+3) 掐腰后再弹回 111.4(花生) ——「大腿比
    // 臀大」的结构放大器；v2.1 裆站躯干取 max(臀, 2×腿) 后单调过渡
    const hip = st(POCKET, 'hip'), crotch = st(POCKET, 'crotch')
    const hipG = loopsAt(POCKET, hip.y)[0].girth
    for (let y = crotch.y + 4; y <= hip.y; y += 2) {
      const g = loopsAt(POCKET, y)[0].girth
      expect(g).toBeGreaterThan(hipG - 4)
    }
  })
})
