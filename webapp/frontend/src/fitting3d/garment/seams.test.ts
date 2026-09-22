// 整裤缝合拓扑金标（2026-09-17 八期）：buildSeamSet 四族 + tip 补焊的
// 配对正确性——纯拓扑/弧长断言（不跑解算）。手工演算依据（夹具实测）：
// · yoke 夹具 back 宿主 side = 两条 run（后片侧缝 96.6 + 育克侧段 3.0，
//   合链 99.6；数组序育克段在末尾——mergeRuns 按首采样 y 降序纠正）
// · side 前后链弧长 99.1 vs 99.6（吃势 0.5 均匀吸收）、inseam 78.2 vs
//   78.0——配对数 = 驱动链（front）顶点数
// · tip 本体 = rise/cb 链首采样（角点共享规则）；fly 连裁 rise 缺失时
//   镜像族跳过、tip 走 inseam 环下一点兜底
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../types'
import type { Garment } from './assemble'
import { buildSeamSet } from './seams'
import { buildBackPanel } from './panel'
import { buildClothMesh, mergeRuns, type ClothMesh } from './mesh'

const HERE = import.meta.dirname   // src/fitting3d/garment

// 四 part 合并 Garment（最小构造：seams 只读 parts/mesh，pos 置零即可）；
// yoke 在 = seam 模式六 part（back_yoke L/R 续在四基础 part 后）+ yokeSeam
const mkFull = (front: ClothMesh, back: ClothMesh, yoke?: {
  host: ClothMesh; sCin: number
}): Garment => {
  const nF = front.xy.length / 2, nB = back.xy.length / 2
  const nY = yoke ? yoke.host.xy.length / 2 : 0
  const parts: Garment['parts'] = [
    { key: 'front', side: 'L', mesh: front, offset: 0 },
    { key: 'front', side: 'R', mesh: front, offset: nF },
    { key: 'back', side: 'L', mesh: back, offset: 2 * nF },
    { key: 'back', side: 'R', mesh: back, offset: 2 * nF + nB },
  ]
  if (yoke) {
    parts.push(
      { key: 'back_yoke', side: 'L', mesh: yoke.host, offset: 2 * nF + 2 * nB },
      { key: 'back_yoke', side: 'R', mesh: yoke.host, offset: 2 * nF + 2 * nB + nY },
    )
  }
  return {
    parts,
    pos: new Float32Array(3 * (2 * nF + 2 * nB + 2 * nY)),
    total: 2 * nF + 2 * nB + 2 * nY,
    ...(yoke ? { yokeSeam: { sCin: yoke.sCin } } : {}),
  }
}

describe('seams：mergeRuns 合链（back 宿主 side 两条 run）', () => {
  const yokeFix: FittingResult = JSON.parse(
    readFileSync(`${HERE}/fixture_fitting_yoke.json`, 'utf8'))
  const host = buildBackPanel(yokeFix).host

  it('yoke 款 back side 恰两条 run、合链长度 = 两段和（≈99.6）、arc 单调', () => {
    const sides = host.runs.filter((r) => r.name === 'side')
    expect(sides.length).toBe(2)
    const merged = mergeRuns(sides, host.xy)
    expect(merged).not.toBeNull()
    // 手工演算：后片侧缝 96.6 + 育克侧段 3.0 = 99.6（引擎 fixture 实测）
    expect(merged!.length).toBeCloseTo(99.6, 1)
    expect(merged!.indices.length)
      .toBe(sides[0].indices.length + sides[1].indices.length)
    for (let k = 1; k < merged!.arc.length; k++) {
      expect(merged!.arc[k]).toBeGreaterThan(merged!.arc[k - 1])
    }
  })

  it('合链首采样 = 育克腰角（首采样 y 降序 = 腰口端优先，链方向腰口→脚口）', () => {
    const sides = host.runs.filter((r) => r.name === 'side')
    const merged = mergeRuns(sides, host.xy)!
    const y0 = host.xy[2 * merged.indices[0] + 1]
    for (const run of sides) {
      expect(y0).toBeGreaterThanOrEqual(
        host.xy[2 * run.indices[0] + 1] - 1e-9)
    }
    expect(y0).toBeGreaterThan(95)   // 育克腰角高 ~100，非后片段 PN 角 ~96
  })

  it('单条 run 原样返回、零条返回 null', () => {
    const plain = buildClothMesh(
      JSON.parse(readFileSync(`${HERE}/fixture_fitting.json`, 'utf8'))
        .pieces.find((p: { key: string }) => p.key === 'front_piece'))
    expect(mergeRuns(plain.runs.filter((r) => r.name === 'side'), plain.xy))
      .toBe(plain.runs.find((r) => r.name === 'side'))
    expect(mergeRuns([], plain.xy)).toBeNull()
  })
})

describe('seams：buildSeamSet 四族 + tip 补焊（yoke 夹具全款）', () => {
  const yokeFix: FittingResult = JSON.parse(
    readFileSync(`${HERE}/fixture_fitting_yoke.json`, 'utf8'))
  const front = buildClothMesh(yokeFix.pieces.find((p) => p.key === 'front_piece')!)
  const back = buildBackPanel(yokeFix).host
  const garment = mkFull(front, back)
  const seam = buildSeamSet(garment)
  const nF = front.xy.length / 2
  const group = (name: string) => seam.groups.find((g) => g.name === name)
  const pairAt = (g: { pairOffset: number }, k: number): [number, number] => [
    seam.pairs[2 * (g.pairOffset + k)], seam.pairs[2 * (g.pairOffset + k) + 1],
  ]

  it('八族齐备（rise/cb/side×2/inseam×2/tip×2），族切片不重叠拼满 pairs', () => {
    expect(seam.groups.map((g) => g.name)).toEqual([
      'rise', 'cb', 'sideL', 'sideR', 'inseamL', 'inseamR', 'tipL', 'tipR',
    ])
    let covered = 0
    for (const g of seam.groups) {
      expect(g.pairOffset).toBe(covered)
      expect(g.pairCount).toBeGreaterThan(0)
      covered += g.pairCount
    }
    expect(covered * 2).toBe(seam.pairs.length)
  })

  it('镜像族：配对数 = 链顶点数、同号顶点 (offL+i, offR+i)', () => {
    const rise = front.runs.find((r) => r.name === 'rise')!
    const cb = back.runs.find((r) => r.name === 'cb')!
    const gR = group('rise')!
    const gC = group('cb')!
    expect(gR.pairCount).toBe(rise.indices.length)
    expect(gC.pairCount).toBe(cb.indices.length)
    // 手工演算：裆尖→腰口链长 rise ≈? / cb 贯通育克 ≈29.0（决策日志六期）
    expect(cb.length).toBeGreaterThan(28)
    expect(cb.length).toBeLessThan(30)
    for (let k = 0; k < gR.pairCount; k++) {
      const [a, b] = pairAt(gR, k)
      expect(a).toBe(0 + rise.indices[k])
      expect(b).toBe(nF + rise.indices[k])
    }
    const offBL = 2 * nF
    for (let k = 0; k < gC.pairCount; k++) {
      const [a, b] = pairAt(gC, k)
      expect(a).toBe(offBL + cb.indices[k])
      expect(b).toBe(offBL + back.xy.length / 2 + cb.indices[k])
    }
  })

  it('side 弧长族：配对数 = front 合链顶点数、首对锚腰口端（两链 indices[0]）', () => {
    const fSide = mergeRuns(front.runs.filter((r) => r.name === 'side'), front.xy)!
    const bSide = mergeRuns(back.runs.filter((r) => r.name === 'side'), back.xy)!
    // 手工演算：前后侧缝弧长 99.03 vs 99.6（吃势 ~0.57 弧长均匀吸收；
    // yoke 夹具 front 实测 99.030115）
    expect(fSide.length).toBeCloseTo(99.03, 1)
    expect(bSide.length).toBeCloseTo(99.6, 1)
    const offBL = 2 * nF, offBR = offBL + back.xy.length / 2
    for (const [g, offF, offB] of [
      [group('sideL')!, 0, offBL], [group('sideR')!, nF, offBR],
    ] as const) {
      expect(g.pairCount).toBe(fSide.indices.length)
      const [a0, b0] = pairAt(g, 0)
      expect(a0).toBe(offF + fSide.indices[0])
      expect(b0).toBe(offB + bSide.indices[0])   // s=0 -> 对侧链腰口端顶点
      // 驱动链 = front：逐顶点配对，首元素恒为 front 链顶点
      for (let k = 0; k < g.pairCount; k++) {
        expect(pairAt(g, k)[0]).toBe(offF + fSide.indices[k])
      }
    }
  })

  it('inseam 弧长族：首对锚脚口端（arc[0]=0 即 hem 内角）、配对数对账', () => {
    const fIn = front.runs.find((r) => r.name === 'inseam')!
    const bIn = back.runs.find((r) => r.name === 'inseam')!
    // 手工演算：前后内缝弧长 78.2 vs 78.0（几乎等长）
    expect(fIn.length).toBeCloseTo(78.2, 1)
    expect(bIn.length).toBeCloseTo(78.0, 1)
    const offBL = 2 * nF
    const g = group('inseamL')!
    expect(g.pairCount).toBe(fIn.indices.length)
    const [a0, b0] = pairAt(g, 0)
    expect(a0).toBe(fIn.indices[0])
    expect(b0).toBe(offBL + bIn.indices[0])
  })

  it('tip 补焊：顶点号 = rise/cb 链首采样（角点共享规则），L/R 各一对', () => {
    const rise0 = front.runs.find((r) => r.name === 'rise')!.indices[0]
    const cb0 = back.runs.find((r) => r.name === 'cb')!.indices[0]
    const offBL = 2 * nF, offBR = offBL + back.xy.length / 2
    expect(pairAt(group('tipL')!, 0)).toEqual([rise0, offBL + cb0])
    expect(pairAt(group('tipR')!, 0)).toEqual([nF + rise0, offBR + cb0])
  })
})

describe('seams：fly 连裁与有省 seam 分支', () => {
  it('fly（删 rise 边合成款）：镜像族跳过、tip 走 inseam 环下一点兜底', () => {
    const plain: FittingResult = JSON.parse(
      readFileSync(`${HERE}/fixture_fitting.json`, 'utf8'))
    const flyFront = buildClothMesh({
      ...plain.pieces.find((p) => p.key === 'front_piece')!,
      edges: plain.pieces.find((p) => p.key === 'front_piece')!
        .edges.filter((e) => e.name !== 'rise'),
    })
    expect(flyFront.runs.some((r) => r.name === 'rise')).toBe(false)
    const back = buildClothMesh(plain.pieces.find((p) => p.key === 'back_piece')!)
    const seam = buildSeamSet(mkFull(flyFront, back))
    const names = seam.groups.map((g) => g.name)
    expect(names).not.toContain('rise')
    // tip 兜底 = inseam 末采样环下一点（tip 本体的角点共享规则口径）
    const inRun = flyFront.runs.find((r) => r.name === 'inseam')!
    const fallback = (inRun.indices[inRun.indices.length - 1] + 1)
      % flyFront.loop.length
    const tipL = seam.groups.find((g) => g.name === 'tipL')!
    expect(seam.pairs[2 * tipL.pairOffset]).toBe(fallback)
    expect(names).toContain('sideL')
    expect(names).toContain('inseamL')
    expect(names).toContain('cb')
  })

  it('有省款 seam 模式（育克升格 sim 参与片）：yokeCb/yokeWaist/yokeWeld 三族齐备', () => {
    const curved: FittingResult = JSON.parse(
      readFileSync(`${HERE}/fixture_fitting_curved_pocket.json`, 'utf8'))
    const panel = buildBackPanel(curved)
    expect(panel.mode).toBe('seam')   // 闭省净样判据命中（非退化）
    const front = buildClothMesh(curved.pieces.find((p) => p.key === 'front_piece')!)
    const seam = buildSeamSet(mkFull(front, panel.host,
      panel.yokeHost && panel.seamInfo
        ? { host: panel.yokeHost, sCin: panel.seamInfo.sCin } : undefined))
    // 手工演算：族序 = push 序（镜像 rise/cb/yokeCb → 弧长 side/inseam →
    // tip → yokeWaist/yokeWeld 按 L/R 交替）
    expect(seam.groups.map((g) => g.name)).toEqual([
      'rise', 'cb', 'yokeCb', 'sideL', 'sideR', 'inseamL', 'inseamR',
      'tipL', 'tipR', 'yokeWaistL', 'yokeWeldL', 'yokeWaistR', 'yokeWeldR',
    ])
    // yokeWaist 配对数 = back top 链顶点数（驱动链逐顶点闭式映射）
    const bTop = mergeRuns(panel.host.runs.filter((r) => r.name === 'top'), panel.host.xy)!
    expect(seam.groups.find((g) => g.name === 'yokeWaistL')!.pairCount)
      .toBe(bTop.indices.length)
    // yokeWeld 每族恰 2 对（P0/PN 角点焊对——弧长族端点只有最近采样级
    // 覆盖，角点须显式焊）
    for (const nm of ['yokeWeldL', 'yokeWeldR']) {
      expect(seam.groups.find((g) => g.name === nm)!.pairCount).toBe(2)
    }
  })
})
