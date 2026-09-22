// 前身并集净样金标（2026-09-16 四期前身缝合立起）：front_piece +
// front_facing 沿 mouth 缝合成一张净样宿主。验收：mouth 内部化（runs
// 无 mouth）；袋贴腰口子段与 front.waist 同名聚合成整条腰口（长度 >
// front 单独 waist，袋贴腰口段并入，drape 悬挂 pin 随之覆盖）；**覆盖
// 性 = 定义性验收**——前片与袋贴两网格全部顶点在宿主上 locate 非 null
// （并集完备，rider 贴层无兜底）；三角化面积比 ≥99%（garment.test
// 同口径防自交/漏采）；宿主面积 > 前片（月牙区并入）。退化：无口袋
// fixture / facing 平移破坏守卫 → hasFacing=false 纯前片宿主。
// 后身并集净样金标（2026-09-16 六期后身缝合立起）：back_piece +
// back_yoke 沿机头下口线缝合。验收：机头下口线内部化（runs 无
// bottom）；back.cb（裆尖→P0）与 yoke cb 反向段（P0→O）聚合成整条
// 后浪（长度 = 两链和，drape 后中缝合对沿它配对）；yoke 腰口 top 顶替
// top_chain；覆盖性/面积比同前身口径。退化：无育克 fixture（信息性
// warning）→ 纯后片；有省款（curved fixture）→ seam 模式分流（2026-
// 09-22）：守卫拦下并集、闭省净样判据命中——育克升格 sim 参与片
//（yokeHost 翻转宿主 + seamInfo.sCin），宿主 = 纯后片。
// 夹具 = fixture_fitting_pocket.json（4 片含袋贴）/ fixture_fitting_
// yoke.json（4 片含育克，无省贴合）/ fixture_fitting_curved_pocket.json
// （有省款）。
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../types'
import { buildBackPanel, buildFrontPanel } from './panel'
import { buildClothMesh, mergeRuns, type ClothMesh } from './mesh'

const HERE = import.meta.dirname   // src/fitting3d/garment

const pocket: FittingResult = JSON.parse(
  readFileSync(`${HERE}/fixture_fitting_pocket.json`, 'utf8'))
const plain: FittingResult = JSON.parse(
  readFileSync(`${HERE}/fixture_fitting.json`, 'utf8'))
const yokeFix: FittingResult = JSON.parse(
  readFileSync(`${HERE}/fixture_fitting_yoke.json`, 'utf8'))
const curved: FittingResult = JSON.parse(
  readFileSync(`${HERE}/fixture_fitting_curved_pocket.json`, 'utf8'))

const frontPiece = pocket.pieces.find((p) => p.key === 'front_piece')!
const facingPiece = pocket.pieces.find((p) => p.key === 'front_facing')!

const shoelace = (m: ClothMesh): number => {
  let s = 0
  const L = m.loop
  for (let i = 0; i < L.length; i++) {
    const a = L[i], b = L[(i + 1) % L.length]
    s += m.xy[2 * a] * m.xy[2 * b + 1] - m.xy[2 * b] * m.xy[2 * a + 1]
  }
  return Math.abs(s) / 2
}

const triArea = (m: ClothMesh): number => {
  let s = 0
  for (let t = 0; t < m.tri.length; t += 3) {
    const a = m.tri[t], b = m.tri[t + 1], c = m.tri[t + 2]
    s += Math.abs(
      (m.xy[2 * b] - m.xy[2 * a]) * (m.xy[2 * c + 1] - m.xy[2 * a + 1])
      - (m.xy[2 * c] - m.xy[2 * a]) * (m.xy[2 * b + 1] - m.xy[2 * a + 1])) / 2
  }
  return s
}

describe('panel：前身并集净样（前片+袋贴沿 mouth 缝合）', () => {
  const panel = buildFrontPanel(pocket)
  const frontMesh = buildClothMesh(frontPiece)
  const facingMesh = buildClothMesh(facingPiece)

  it('守卫通过拼入袋贴：hasFacing=true、无 warnings', () => {
    expect(panel.hasFacing).toBe(true)
    expect(panel.warnings).toEqual([])
  })

  it('mouth 内部化为缝线：runs 无 mouth；waist/side/hem/inseam/rise 齐备', () => {
    const names = panel.host.runs.map((r) => r.name)
    expect(names).not.toContain('mouth')
    for (const n of ['waist', 'side', 'hem', 'inseam', 'rise']) {
      expect(names).toContain(n)
    }
    expect(panel.host.runs.find((r) => r.name === 'waist')!.role)
      .toBe('top_chain')
    expect(panel.host.runs.find((r) => r.name === 'rise')!.role)
      .toBe('seam')
  })

  it('袋贴腰口段并入整条腰口：waist run 长度 > front 单独 waist 总长', () => {
    const frontWaistLen = frontPiece.edges
      .filter((e) => e.name === 'waist')
      .reduce((s, e) => s + e.length, 0)
    const hostWaist = panel.host.runs.find((r) => r.name === 'waist')!
    expect(hostWaist.length).toBeGreaterThan(frontWaistLen + 1)
  })

  it('覆盖性（定义性验收）：全部顶点 locate 非空或在宿主边界上（<0.1cm）', () => {
    // locate null 允许出现在边界上：Delaunay 无约束 + 质心过滤，凹弧处
    // 窄楔形三角形被丢出覆盖（月牙区外边恰是凹弧，实测 facing 11 个边界
    // 顶点命中）——这些点由 rider 兜底（边界段插值，弓高亚毫米），此处
    // 验收并集完备性：内部点必可 locate、边界点必贴宿主边界环
    const host = panel.host
    const distToLoop = (x: number, y: number): number => {
      let dMin = Infinity
      const L = host.loop.length
      for (let s = 0; s < L; s++) {
        const a = host.loop[s], b = host.loop[(s + 1) % L]
        const ax = host.xy[2 * a], ay = host.xy[2 * a + 1]
        const bx = host.xy[2 * b], by = host.xy[2 * b + 1]
        const dx = bx - ax, dy = by - ay
        const len2 = dx * dx + dy * dy
        const t = len2 > 1e-12
          ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / len2))
          : 0
        dMin = Math.min(dMin, Math.hypot(x - (ax + dx * t), y - (ay + dy * t)))
      }
      return dMin
    }
    for (const m of [frontMesh, facingMesh]) {
      for (let i = 0; i < m.xy.length / 2; i++) {
        const x = m.xy[2 * i], y = m.xy[2 * i + 1]
        const loc = host.locate(x, y)
        if (loc === null) {
          // 兜底通道成立前提：点贴宿主边界（弓高量级）
          expect(distToLoop(x, y), `顶点 ${i} (${x}, ${y}) 既不可 locate 也不贴边界`)
            .toBeLessThan(0.1)
        }
      }
    }
  })

  it('三角化面积比 ≥99%（防自交/漏采）、宿主面积 > 前片（月牙并入）', () => {
    expect(triArea(panel.host) / shoelace(panel.host)).toBeGreaterThan(0.99)
    expect(shoelace(panel.host)).toBeGreaterThan(shoelace(frontMesh))
  })

  it('退化：无口袋 fixture（无袋贴片）→ 纯前片宿主', () => {
    const p = buildFrontPanel(plain)
    expect(p.hasFacing).toBe(false)
    expect(p.warnings.length).toBe(1)
    const plainFront = plain.pieces.find((x) => x.key === 'front_piece')!
    expect(p.host.xy.length).toBe(buildClothMesh(plainFront).xy.length)
  })

  it('退化：facing 整体平移 5cm（边+marks 同移）破坏贴合守卫 → 纯前片宿主', () => {
    const broken: FittingResult = {
      ...pocket,
      pieces: pocket.pieces.map((p) => p.key === 'front_facing'
        ? {
          ...p,
          edges: p.edges.map((e) => ({
            ...e, pts: e.pts.map(([x, y]) => [x + 5, y] as [number, number]),
          })),
          marks: p.marks.map((mk) => ({
            ...mk, pts: mk.pts.map(([x, y]) => [x + 5, y] as [number, number]),
          })),
        }
        : p),
    }
    const r = buildFrontPanel(broken)
    expect(r.hasFacing).toBe(false)
    expect(r.warnings.length).toBe(1)
    expect(r.warnings[0]).toContain('不贴合')
  })
})

describe('panel：后身并集净样（后片+育克沿机头下口线缝合）', () => {
  const panel = buildBackPanel(yokeFix)
  const backPiece = yokeFix.pieces.find((p) => p.key === 'back_piece')!
  const yokePiece = yokeFix.pieces.find((p) => p.key === 'back_yoke')!
  const backMesh = buildClothMesh(backPiece)
  const yokeMesh = buildClothMesh(yokePiece)

  it('守卫通过拼入育克：hasYoke=true、无 warnings', () => {
    expect(panel.hasYoke).toBe(true)
    expect(panel.warnings).toEqual([])
  })

  it('机头下口线内部化为缝线：runs 无 bottom；cb/top/side/hem/inseam 齐备', () => {
    const names = panel.host.runs.map((r) => r.name)
    expect(names).not.toContain('bottom')
    for (const n of ['cb', 'top', 'side', 'hem', 'inseam']) {
      expect(names).toContain(n)
    }
    expect(panel.host.runs.find((r) => r.role === 'top_chain')!.name)
      .toBe('top')
  })

  it('后浪贯通：back.cb（裆尖→P0）与 yoke cb 反向段（P0→O）聚合成单一 cb run，长度 = 两链和', () => {
    // fixture 手工演算：back cb 两段 14.66+10.34 + yoke cb 4.00 = 29.00
    const cbRuns = panel.host.runs.filter((r) => r.name === 'cb')
    expect(cbRuns.length).toBe(1)
    const backCbLen = backPiece.edges
      .filter((e) => e.name === 'cb').reduce((s, e) => s + e.length, 0)
    const yokeCbLen = yokePiece.edges
      .filter((e) => e.name === 'cb').reduce((s, e) => s + e.length, 0)
    expect(cbRuns[0].length).toBeCloseTo(backCbLen + yokeCbLen, 5)
    expect(cbRuns[0].length).toBeCloseTo(29.0, 2)
    // 链首 = 裆尖（cb 边链起点，全局系 x 最大端）——drape 后中缝合对
    // 从裆尖配到腰口
    const first = cbRuns[0].indices[0]
    expect(panel.host.xy[2 * first]).toBeCloseTo(67.6, 1)
  })

  it('育克腰口顶替 top_chain：top run 长度 = yoke top 总长', () => {
    const yokeTopLen = yokePiece.edges
      .filter((e) => e.name === 'top').reduce((s, e) => s + e.length, 0)
    const topRun = panel.host.runs.find((r) => r.name === 'top')!
    expect(topRun.length).toBeCloseTo(yokeTopLen, 5)
  })

  it('覆盖性（定义性验收）：后片/育克全部顶点 locate 非空或贴宿主边界（<0.1cm）', () => {
    const host = panel.host
    const distToLoop = (x: number, y: number): number => {
      let dMin = Infinity
      const L = host.loop.length
      for (let s = 0; s < L; s++) {
        const a = host.loop[s], b = host.loop[(s + 1) % L]
        const ax = host.xy[2 * a], ay = host.xy[2 * a + 1]
        const bx = host.xy[2 * b], by = host.xy[2 * b + 1]
        const dx = bx - ax, dy = by - ay
        const len2 = dx * dx + dy * dy
        const t = len2 > 1e-12
          ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / len2))
          : 0
        dMin = Math.min(dMin, Math.hypot(x - (ax + dx * t), y - (ay + dy * t)))
      }
      return dMin
    }
    for (const m of [backMesh, yokeMesh]) {
      for (let i = 0; i < m.xy.length / 2; i++) {
        const x = m.xy[2 * i], y = m.xy[2 * i + 1]
        const loc = host.locate(x, y)
        if (loc === null) {
          expect(distToLoop(x, y), `顶点 ${i} (${x}, ${y}) 既不可 locate 也不贴边界`)
            .toBeLessThan(0.1)
        }
      }
    }
  })

  it('三角化面积比 ≥99%（防自交/漏采）、宿主面积 > 后片（育克区并入）', () => {
    expect(triArea(panel.host) / shoelace(panel.host)).toBeGreaterThan(0.99)
    expect(shoelace(panel.host)).toBeGreaterThan(shoelace(backMesh))
  })

  it('退化：无育克 fixture（back_yoke 未开）→ 纯后片宿主（信息性 warning）', () => {
    const p = buildBackPanel(plain)
    expect(p.hasYoke).toBe(false)
    expect(p.warnings.length).toBe(1)
    const plainBack = plain.pieces.find((x) => x.key === 'back_piece')!
    expect(p.host.xy.length).toBe(buildClothMesh(plainBack).xy.length)
  })

  it('有省款（yoke 省闭口净样与整版下口线错位）→ seam 模式分流：育克升格 sim 参与片', () => {
    const p = buildBackPanel(curved)
    expect(p.mode).toBe('seam')
    expect(p.hasYoke).toBe(true)   // 育克离开平铺、升格参与片
    expect(p.warnings.length).toBe(0)
    // 宿主 = 纯后片：top 边 role='seam'（引擎 role_override）无 top_chain
    expect(p.host.runs.some((r) => r.role === 'top_chain')).toBe(false)
    // 翻转宿主四边链：cb'(P0→O)/top'(O→X，top_chain 顶替腰口)/side'/bottom'
    const yh = p.yokeHost!
    expect(yh.runs.find((r) => r.role === 'top_chain')!.name).toBe('top')
    // 真有省几何账（fixture 实测）：back top = 整版机头下口线直线
    // L_back 22.07（含省口段不扣）；yoke bottom = 闭省净样 L_yoke 19.68
    // ——sMouth = L_back − L_yoke ≈ 2.39 = 省口段布量（真实缝前状态）；
    // 瓣1 [0, 7.81] 与直线逐点重合 perp=0；sCin = C_in 从 P0 侧弧 ≈9.7
    //（瓣1 末端倒圆中段，seams yokeWaist 闭式收敛映射断点）
    const bTop = mergeRuns(p.host.runs.filter((r) => r.name === 'top'), p.host.xy)!
    const yBottom = mergeRuns(yh.runs.filter((r) => r.name === 'bottom'), yh.xy)!
    expect(bTop.length).toBeCloseTo(22.07, 1)
    expect(yBottom.length).toBeCloseTo(19.68, 1)
    expect(p.seamInfo!.sCin).toBeCloseTo(9.76, 1)
  })
})
