// 全裁片装配金标（重建 2026-09-15；2026-09-17 八期整裤缝合换代）：
// 平铺验证（三期回落，现行接线）+ buildFullPair 整裤四 part 摆位（八期，
// 取代六期双筒 buildHangPair——随整裤合并退役）。平铺验收：payload 每
// 片一行（成对片 L 原样 / R 前中镜像逐点等距变换、腰头单片）、全片贴
// 地 y=0、全组 z 居中、行序 = payload 片序、行距 ≥ rowGap、无 NaN。
// 整裤摆位验收见 buildFullPair describe（结构/腰圆/内缝/腿区/穿透）。
// 夹具 = fixture_fitting.json（引擎 build_fitting_payload 直出，默认
// 直腰头 3 片：front_piece / back_piece / waistband）。
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../types'
import { buildFlatLayout, buildFullPair } from './assemble'
import { buildSeamSet } from './seams'
import { bandBottomChain, bandTargets, buildWaistbandMesh, ringWalk } from './band'
import { buildBackPanel, buildFrontPanel } from './panel'
import { buildCore, buildLegAxis, CORE_SKIN } from './core'
import { buildClothMesh } from './mesh'
import {
  BodyField, buildBodyField, buildWaistRing, pointInRings, ringPointAt,
  type SliceRing, type WaistRing,
} from './placement'
import { FLAT_PRIOR, HANG_PRIOR } from './priors'

const HERE = import.meta.dirname   // src/fitting3d/garment

const result: FittingResult = JSON.parse(
  readFileSync(`${HERE}/fixture_fitting.json`, 'utf8'))

describe('assemble：全裁片平铺装配（重建三期回落，现行）', () => {
  const garment = buildFlatLayout(result)
  // fixture 直腰头 3 片：front×2 + back×2 + waistband×1（腰头单片）
  const frontMesh = buildClothMesh(result.pieces[0])
  const backMesh = buildClothMesh(result.pieces[1])
  const wbMesh = buildClothMesh(result.pieces[2])
  const partZ = (pi: number): { z0: number; z1: number; x1: number } => {
    const p = garment.parts[pi]
    const n = p.mesh.xy.length / 2
    let z0 = Infinity, z1 = -Infinity, x1 = 0
    for (let i = 0; i < n; i++) {
      z0 = Math.min(z0, garment.pos[3 * (p.offset + i) + 2])
      z1 = Math.max(z1, garment.pos[3 * (p.offset + i) + 2])
      x1 = Math.max(x1, garment.pos[3 * (p.offset + i)])
    }
    return { z0, z1, x1 }
  }

  it('parts 序 = payload 片序展开（成对片 L+R、腰头单片）、共享网格 offset 顺排', () => {
    expect(garment.parts.map((p) => `${p.key}_${p.side}`))
      .toEqual(['front_piece_L', 'front_piece_R',
        'back_piece_L', 'back_piece_R', 'waistband_L'])
    expect(result.pieces.map((p) => p.key))
      .toEqual(['front_piece', 'back_piece', 'waistband'])
    expect(garment.parts[0].mesh).toBe(garment.parts[1].mesh)
    expect(garment.parts[2].mesh).toBe(garment.parts[3].mesh)
    let off = 0
    for (const p of garment.parts) {
      expect(p.offset).toBe(off)
      off += p.mesh.xy.length / 2
    }
    expect(garment.total).toBe(off)
    expect(garment.pos.length).toBe(3 * off)
    // 网格 = 逐片 buildClothMesh 原样（layout 内自建，引用不同内容同——
    // 内容一致性由下方逐点等距变换用例钉死，这里对账顶点数）
    expect(garment.parts[0].mesh.xy.length).toBe(frontMesh.xy.length)
    expect(garment.parts[4].mesh.xy.length).toBe(wbMesh.xy.length)
  })

  it('全片贴地 y≡0、无 NaN、全组 z 居中于 0', () => {
    let zMin = Infinity, zMax = -Infinity
    for (let i = 0; i < garment.total; i++) {
      const px = garment.pos[3 * i], py = garment.pos[3 * i + 1]
      const pz = garment.pos[3 * i + 2]
      expect(Number.isFinite(px)).toBe(true)
      expect(Number.isFinite(pz)).toBe(true)
      expect(py).toBe(0)                 // 平铺：高度恒 0（离地在显示层）
      zMin = Math.min(zMin, pz)
      zMax = Math.max(zMax, pz)
    }
    // 手工演算：depth = Σ行高 + (片数−1)·rowGap，组 z 域 [-depth/2, +depth/2]
    const depth = (partZ(0).z1 - partZ(0).z0) + (partZ(2).z1 - partZ(2).z0)
      + (partZ(4).z1 - partZ(4).z0) + 2 * FLAT_PRIOR.rowGap
    expect(zMax - zMin).toBeCloseTo(depth, 5)
    expect(Math.abs(zMin + zMax)).toBeLessThan(1e-4)   // 居中：中点 ≈ 0
  })

  it('行序 = payload 片序（前片最近）、相邻行距 ≥ rowGap', () => {
    const f = partZ(0), b = partZ(2), w = partZ(4)
    expect(f.z1).toBeLessThan(b.z0)          // front 行整体在 back 行前
    expect(b.z1).toBeLessThan(w.z0)
    // 摆位构造行距恰 rowGap（pos Float32 对照有 ~1e-6 量化伪差，放 4 位）
    expect(b.z0 - f.z1).toBeCloseTo(FLAT_PRIOR.rowGap, 4)
    expect(w.z0 - b.z1).toBeCloseTo(FLAT_PRIOR.rowGap, 4)
  })

  it('成对片逐点等距变换：L 原样、R 前中镜像（与 2D 裁片 SVG 一比一）', () => {
    for (const [li, ri, mesh] of [
      [0, 1, frontMesh], [2, 3, backMesh],
    ] as const) {
      const n = mesh.xy.length / 2
      let xMin = Infinity, xMax = -Infinity
      let yMin = Infinity
      for (let i = 0; i < mesh.xy.length; i += 2) {
        xMin = Math.min(xMin, mesh.xy[i])
        xMax = Math.max(xMax, mesh.xy[i])
        yMin = Math.min(yMin, mesh.xy[i + 1])
      }
      const W = xMax - xMin
      const zBase = partZ(li).z0
      for (let i = 0; i < n; i++) {
        const u = mesh.xy[2 * i] - xMin
        const v = mesh.xy[2 * i + 1] - yMin
        const l = 3 * (garment.parts[li].offset + i)
        const r = 3 * (garment.parts[ri].offset + i)
        // L：片内归一原样落 (u, 0, zBase+v)
        expect(garment.pos[l]).toBeCloseTo(u, 5)
        expect(garment.pos[l + 2]).toBeCloseTo(zBase + v, 4)
        // R：u→W−u 镜像 + 平移 W+gap；z 同 L（腰口同向）
        expect(garment.pos[r])
          .toBeCloseTo(W + FLAT_PRIOR.gap + (W - u), 5)
        expect(garment.pos[r + 2]).toBeCloseTo(garment.pos[l + 2], 4)
      }
    }
  })

  it('腰头单片原样（无镜像副本）、x∈[0,W]', () => {
    const p = garment.parts[4]
    const n = p.mesh.xy.length / 2
    let xMin = Infinity, xMax = -Infinity
    for (let i = 0; i < wbMesh.xy.length; i += 2) {
      xMin = Math.min(xMin, wbMesh.xy[i])
      xMax = Math.max(xMax, wbMesh.xy[i])
    }
    const W = xMax - xMin
    for (let i = 0; i < n; i++) {
      const u = wbMesh.xy[2 * i] - xMin
      const idx = 3 * (p.offset + i)
      expect(garment.pos[idx]).toBeCloseTo(u, 5)
      expect(garment.pos[idx]).toBeGreaterThanOrEqual(0)
    }
    expect(partZ(4).x1).toBeCloseTo(W, 5)
  })
})

describe('assemble：机头+后片缝合拼合（重建三期缝合步，2026-09-15 晚八）', () => {
  const yokeResult: FittingResult = JSON.parse(
    readFileSync(`${HERE}/fixture_fitting_yoke.json`, 'utf8'))
  const garment = buildFlatLayout(yokeResult)
  const partOf = (key: string, side: 'L' | 'R') =>
    garment.parts.find((p) => p.key === key && p.side === side)!
  const px = (part: ReturnType<typeof partOf>, i: number) =>
    garment.pos[3 * (part.offset + i)]

  it('拼合行：back+yoke 同行（L 侧 back,yoke / R 侧镜像）、yoke 不独立成行、腰头单片', () => {
    expect(garment.parts.map((p) => `${p.key}_${p.side}`)).toEqual([
      'front_piece_L', 'front_piece_R',
      'back_piece_L', 'back_yoke_L',
      'back_piece_R', 'back_yoke_R',
      'waistband_L',
    ])
  })

  it('缝合边重合：back top 边与 yoke bottom 边逐点贴合（L/R 两侧）', () => {
    // 依据：两片在整版上共享机头下口线，payload 边链整版全局系坐标
    // 逐点重合（fixture 实测 max 点距 0）+ 拼合组共享变换 → pos 重合；
    // Float32 量化同输入同结果，留 1e-4 余量
    for (const side of ['L', 'R'] as const) {
      const bp = partOf('back_piece', side)
      const yp = partOf('back_yoke', side)
      const top = bp.mesh.runs.find((r) => r.name === 'top')
      const bottom = yp.mesh.runs.find((r) => r.name === 'bottom')
      expect(top).toBeDefined()
      expect(bottom).toBeDefined()
      let worst = 0
      for (const bi of bottom!.indices) {
        const x = px(yp, bi), z = garment.pos[3 * (yp.offset + bi) + 2]
        let dMin = Infinity
        for (const ti of top!.indices) {
          const tx = px(bp, ti), tz = garment.pos[3 * (bp.offset + ti) + 2]
          dMin = Math.min(dMin, Math.hypot(tx - x, tz - z))
        }
        worst = Math.max(worst, dMin)
      }
      expect(worst).toBeLessThan(1e-4)
    }
  })

  it('拼合组整组镜像：R 侧 = L 侧关于组中线镜像（back/yoke 各自逐点）', () => {
    let xMax = 0
    for (const part of [partOf('back_piece', 'L'), partOf('back_yoke', 'L')]) {
      for (let i = 0; i < part.mesh.xy.length / 2; i++) {
        xMax = Math.max(xMax, px(part, i))
      }
    }
    const W = xMax            // L 侧组从 0 归一起，W = L 侧拼合组宽
    const mid = W + FLAT_PRIOR.gap / 2
    for (const key of ['back_piece', 'back_yoke']) {
      const l = partOf(key, 'L'), r = partOf(key, 'R')
      for (let i = 0; i < l.mesh.xy.length / 2; i++) {
        expect(px(r, i) - mid).toBeCloseTo(mid - px(l, i), 5)
      }
    }
  })

  it('拼合行高 = back+yoke 全局 y 并集（缝合成整体后的总高）', () => {
    // fixture 手工演算：back bbox y∈[0, 96.196] + yoke y∈[95.236, 100.141]
    // → 并集高 = 100.141（缝合的后身：脚口到育克上口）
    const bl = partOf('back_piece', 'L')
    let z0 = Infinity, z1 = -Infinity
    for (let i = 0; i < bl.mesh.xy.length / 2; i++) {
      z0 = Math.min(z0, garment.pos[3 * (bl.offset + i) + 2])
      z1 = Math.max(z1, garment.pos[3 * (bl.offset + i) + 2])
    }
    const yl = partOf('back_yoke', 'L')
    for (let i = 0; i < yl.mesh.xy.length / 2; i++) {
      z1 = Math.max(z1, garment.pos[3 * (yl.offset + i) + 2])
    }
    expect(z1 - z0).toBeCloseTo(100.141, 3)
  })
})

describe('assemble：袋贴+前片缝合拼合（重建三期缝合步，2026-09-15 晚九）', () => {
  const pocketResult: FittingResult = JSON.parse(
    readFileSync(`${HERE}/fixture_fitting_pocket.json`, 'utf8'))
  const garment = buildFlatLayout(pocketResult)
  const partOf = (key: string, side: 'L' | 'R') =>
    garment.parts.find((p) => p.key === key && p.side === side)!
  const px = (part: ReturnType<typeof partOf>, i: number) =>
    garment.pos[3 * (part.offset + i)]

  it('拼合行：front+facing 同行、facing 不独立成行、back/腰头照旧', () => {
    expect(garment.parts.map((p) => `${p.key}_${p.side}`)).toEqual([
      'front_facing_L', 'front_piece_L',
      'front_facing_R', 'front_piece_R',
      'back_piece_L', 'back_piece_R',
      'waistband_L',
    ])
  })

  it('缝合依据（数据前提）：facing 袋口净线 marks 与 front mouth 边逐点重合', () => {
    // payload 层钉死拼合前提（整版坐标即缝后位置）；pos 层对齐由下一
    // 条「组共享变换」断言传导
    const front = pocketResult.pieces.find((p) => p.key === 'front_piece')!
    const facing = pocketResult.pieces.find((p) => p.key === 'front_facing')!
    const mouth = front.edges.filter((e) => e.name === 'mouth')
      .flatMap((e) => e.pts)
    expect(mouth.length).toBeGreaterThan(0)
    const gap = facing.marks.some((mk) => {
      let worst = 0
      for (const p of mk.pts) {
        let dMin = Infinity
        for (const q of mouth) {
          dMin = Math.min(dMin, Math.hypot(p[0] - q[0], p[1] - q[1]))
        }
        worst = Math.max(worst, dMin)
      }
      return worst < 0.5
    })
    expect(gap).toBe(true)
  })

  it('组共享变换：L/R 侧各片 pos 与全局 xy 的变换常数逐点恒定（整版对齐）', () => {
    // L 侧：pos_x = x − Cx、pos_z = y − Cy + 行基；Cx/Cy 对组内两片
    // 相等 = 按整版全局坐标对齐（缝合的本质）。R 侧镜像同理（翻号）
    for (const side of ['L', 'R'] as const) {
      const front = partOf('front_piece', side)
      const facing = partOf('front_facing', side)
      const sgn = side === 'L' ? 1 : -1
      let cx = 0, cy = 0
      for (const [k, part] of [['f', front], ['g', facing]] as const) {
        void k
        const n = part.mesh.xy.length / 2
        for (let i = 0; i < n; i++) {
          const x = part.mesh.xy[2 * i], y = part.mesh.xy[2 * i + 1]
          const ax = sgn * px(part, i), az = garment.pos[3 * (part.offset + i) + 2]
          if (i === 0 && part === front) { cx = x - ax; cy = y - az }
          expect(x - ax).toBeCloseTo(cx, 5)
          expect(y - az).toBeCloseTo(cy, 5)
        }
      }
    }
  })

  it('组内叠层：facing y≡0、front y≡stackStep（前片在上盖住袋贴条带）', () => {
    // 2026-09-16 用户口径「前片在前口袋上面」：facing 片序在前 = 下层，
    // 前片叠上层（外观主体是前片，袋贴衬里侧）
    const front = partOf('front_piece', 'L')
    const facing = partOf('front_facing', 'L')
    for (let i = 0; i < facing.mesh.xy.length / 2; i++) {
      expect(garment.pos[3 * (facing.offset + i) + 1]).toBe(0)
    }
    for (let i = 0; i < front.mesh.xy.length / 2; i++) {
      expect(garment.pos[3 * (front.offset + i) + 1])
        .toBeCloseTo(FLAT_PRIOR.stackStep, 6)
    }
  })
})

describe('assemble：贴合守卫（有省 yoke 退独立行、弯腰头袋贴照常拼合）', () => {
  const curvedResult: FittingResult = JSON.parse(
    readFileSync(`${HERE}/fixture_fitting_curved_pocket.json`, 'utf8'))
  const garment = buildFlatLayout(curvedResult)

  it('有省款 yoke 下边（省闭口净样）与 back top 错位 ~12cm → 守卫拦下退独立行', () => {
    // payload 数据前提：省闭口错位实测（决策日志晚八条目）
    expect(garment.parts.map((p) => `${p.key}_${p.side}`)).toEqual([
      'front_facing_L', 'front_piece_L',
      'front_facing_R', 'front_piece_R',
      'back_piece_L', 'back_piece_R',
      'back_yoke_L', 'back_yoke_R',      // yoke 独立行（不与 back 拼合）
      'waistband_L',
    ])
  })

  it('弯腰头款袋贴照常拼合（marks 袋口净线与 mouth 重合，组共享变换成立）', () => {
    const front = garment.parts.find(
      (p) => p.key === 'front_piece' && p.side === 'L')!
    const facing = garment.parts.find(
      (p) => p.key === 'front_facing' && p.side === 'L')!
    expect(facing).toBeDefined()
    // facing 片序在前 = 下层 y=0、前片叠上层（拼合成功才会同行）
    expect(garment.pos[3 * facing.offset + 1]).toBe(0)
    expect(garment.pos[3 * front.offset + 1])
      .toBeCloseTo(FLAT_PRIOR.stackStep, 6)
  })
})

describe('assemble：buildFlatLayout exclude（四期前身缝合立起）', () => {
  const pocketResult: FittingResult = JSON.parse(
    readFileSync(`${HERE}/fixture_fitting_pocket.json`, 'utf8'))

  it('exclude 前身组（锚+组员）→ 整组离开平铺，余片照旧', () => {
    const g = buildFlatLayout(pocketResult,
      new Set(['front_piece', 'front_facing']))
    expect(g.parts.map((p) => `${p.key}_${p.side}`)).toEqual([
      'back_piece_L', 'back_piece_R', 'waistband_L',
    ])
  })

  it('只 exclude 锚、守卫通过 → 组员随锚整组离开（缝合整体口径）', () => {
    const g = buildFlatLayout(pocketResult, new Set(['front_piece']))
    expect(g.parts.map((p) => `${p.key}_${p.side}`)).toEqual([
      'back_piece_L', 'back_piece_R', 'waistband_L',
    ])
  })

  it('无袋贴款 exclude 前片 → 前片独立离开、无组员可带走', () => {
    const g = buildFlatLayout(result, new Set(['front_piece']))
    expect(g.parts.map((p) => `${p.key}_${p.side}`)).toEqual([
      'back_piece_L', 'back_piece_R', 'waistband_L',
    ])
  })

  it('守卫破坏 + exclude 锚 → 组员照旧独立行平铺（panel 退化兜底）', () => {
    const broken: FittingResult = {
      ...pocketResult,
      pieces: pocketResult.pieces.map((p) => p.key === 'front_facing'
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
    const g = buildFlatLayout(broken, new Set(['front_piece']))
    // 行序 = payload 片序（front_facing 片序在 back 之后）
    expect(g.parts.map((p) => `${p.key}_${p.side}`)).toEqual([
      'back_piece_L', 'back_piece_R',
      'front_facing_L', 'front_facing_R', 'waistband_L',
    ])
  })
})

describe('assemble：buildFlatLayout exclude 后身组（六期后身缝合立起）', () => {
  const yokeResult: FittingResult = JSON.parse(
    readFileSync(`${HERE}/fixture_fitting_yoke.json`, 'utf8'))

  it('exclude 后身组（锚+组员）→ 整组离开平铺，余片照旧', () => {
    const g = buildFlatLayout(yokeResult,
      new Set(['front_piece', 'back_piece', 'back_yoke']))
    expect(g.parts.map((p) => `${p.key}_${p.side}`)).toEqual([
      'waistband_L',
    ])
  })

  it('只 exclude 锚 back_piece、守卫通过（无省贴合）→ 育克随锚整组离开', () => {
    const g = buildFlatLayout(yokeResult, new Set(['back_piece']))
    expect(g.parts.map((p) => `${p.key}_${p.side}`)).toEqual([
      'front_piece_L', 'front_piece_R', 'waistband_L',
    ])
  })

  it('守卫破坏 + exclude 锚 → 育克照旧独立行平铺（panel 退化兜底）', () => {
    const broken: FittingResult = {
      ...yokeResult,
      pieces: yokeResult.pieces.map((p) => p.key === 'back_yoke'
        ? {
          ...p,
          edges: p.edges.map((e) => ({
            ...e, pts: e.pts.map(([x, y]) => [x + 5, y] as [number, number]),
          })),
        }
        : p),
    }
    const g = buildFlatLayout(broken, new Set(['back_piece']))
    expect(g.parts.map((p) => `${p.key}_${p.side}`)).toEqual([
      'front_piece_L', 'front_piece_R',
      'back_yoke_L', 'back_yoke_R',      // 育克独立行（不与 back 拼合）
      'waistband_L',
    ])
  })
})

describe('assemble：buildFullPair 整裤四 part 摆位（八期整裤缝合）', () => {
  // 摆位先行验收：合并四 part（fL/fR/bL/bR）、腰圆 360° 整圈初始已闭
  // （侧腰角前后宿主共点 ±90°）、内缝语义摆位 pinch 线、腿区逐高度
  // 局部归一角度域、side 语义摆位 + 镜像对称 + 纸样空间穿透零。夹具 =
  // pocket（前并集含袋贴 / 后纯片）+ yoke（后并集含育克 / 前纯片）双款
  // 覆盖；forkY 取 payload body.points 裡尖 y。
  const cases = [
    { name: 'pocket', fixture: 'fixture_fitting_pocket.json' },
    { name: 'yoke', fixture: 'fixture_fitting_yoke.json' },
  ]
  for (const c of cases) {
    const payload: FittingResult = JSON.parse(
      readFileSync(`${HERE}/${c.fixture}`, 'utf8'))
    const frontPanel = buildFrontPanel(payload)
    const backPanel = buildBackPanel(payload)
    const core = buildCore(payload)
    const field = buildBodyField(core.positions, core.indices)
    const axis = buildLegAxis(payload)
    const g = buildFullPair(frontPanel.host, backPanel.host, field, {
      front: payload.body.points.front_crotch_vertex[1],
      back: payload.body.points.back_crotch_vertex[1],
    }, axis)
    const nF = frontPanel.host.xy.length / 2
    const nB = backPanel.host.xy.length / 2
    const part = (key: 'front' | 'back', side: 'L' | 'R') =>
      g.parts.find((p) => p.key === key && p.side === side)!
    const at = (p: ReturnType<typeof part>, i: number) => 3 * (p.offset + i)
    const thOf = (p: ReturnType<typeof part>, i: number) =>
      Math.atan2(g.pos[at(p, i)], g.pos[at(p, i) + 2])

    it(`${c.name}：四 part 结构 [fL,fR,bL,bR]、offset 顺排、总数对账、无 NaN`, () => {
      expect(g.parts.map((p) => `${p.key}_${p.side}`))
        .toEqual(['front_L', 'front_R', 'back_L', 'back_R'])
      expect(part('front', 'L').offset).toBe(0)
      expect(part('front', 'R').offset).toBe(nF)
      expect(part('back', 'L').offset).toBe(2 * nF)
      expect(part('back', 'R').offset).toBe(2 * nF + nB)
      expect(g.total).toBe(2 * nF + 2 * nB)
      expect(g.pos.length).toBe(3 * g.total)
      for (let i = 0; i < g.pos.length; i++) {
        expect(Number.isFinite(g.pos[i])).toBe(true)
      }
    })

    it(`${c.name}：腰圆整圈——四段顶链中缝腰角精确落中面、侧缝腰角落 ±90° 且前后宿主共点`, () => {
      // 「钉与缝同意」整裤版：fL/bL 侧腰角三维共点（front/back top 链
      // 的 side 腰角端；θ=±90°、r=场+gap、前后腰口线等高——五条水平线
      // 等高的整版口径在 3D 摆位的直接验收）
      const topOf = (p: ReturnType<typeof part>) =>
        p.mesh.runs.find((r) => r.role === 'top_chain')!
      const seamRunOf = (p: ReturnType<typeof part>) =>
        p.mesh.runs.find((r) => r.name === 'rise' || r.name === 'cb')
      // order[0] = 中缝腰角（与 buildFullPair Step2 同判定：seamTop ==
      // top 末采样则 order 反转、否则原序），另一端 = 侧缝腰角
      const centerIdx = (p: ReturnType<typeof part>): number => {
        const top = topOf(p)
        const seam = seamRunOf(p)
        const seamTop = seam ? seam.indices[seam.indices.length - 1] : null
        return seamTop === top.indices[top.indices.length - 1]
          ? top.indices[top.indices.length - 1] : top.indices[0]
      }
      for (const [key, midTh] of [['front', 0], ['back', -Math.PI]] as const) {
        for (const side of ['L', 'R'] as const) {
          const p = part(key, side)
          const i = centerIdx(p)
          expect(Math.abs(g.pos[at(p, i)])).toBeLessThan(1e-3)
          const th = thOf(p, i)
          expect(Math.abs(Math.atan2(Math.sin(th - midTh),
            Math.cos(th - midTh)))).toBeLessThan(0.01)
          expect(g.pos[at(p, i) + 2] * (key === 'front' ? 1 : -1))
            .toBeGreaterThan(0)
        }
      }
      // 侧腰角本体 = side 合链首采样（与 buildFullPair snap/mergeRuns 同
      // 口径：首采样 y 最高的 run 的首点；top run 末端只是角点前一步）
      const sideCorner = (p: ReturnType<typeof part>): number => {
        const runs = p.mesh.runs.filter((r) => r.name === 'side')
        const top = runs.reduce((a, b) =>
          p.mesh.xy[2 * b.indices[0] + 1] > p.mesh.xy[2 * a.indices[0] + 1] ? b : a)
        return top.indices[0]
      }
      // θ 沿链单调铺满 90°（front 0→−90 递减 / back −180→−90 递增；
      // 六期拉直口径移植——整圈全向钉的前提）
      for (const p of [part('front', 'L'), part('back', 'L')]) {
        const top = topOf(p)
        const seam = seamRunOf(p)
        const seamTop = seam ? seam.indices[seam.indices.length - 1] : null
        const order = seamTop === top.indices[top.indices.length - 1]
          ? [...top.indices].reverse() : [...top.indices]
        const step = p.key === 'front' ? -1 : 1
        for (let k = 1; k < order.length; k++) {
          const prev = thOf(p, order[k - 1])
          const cur = thOf(p, order[k])
          expect((cur - prev) * step).toBeGreaterThanOrEqual(-1e-6)
        }
      }
      const fC = at(part('front', 'L'), sideCorner(part('front', 'L')))
      const bC = at(part('back', 'L'), sideCorner(part('back', 'L')))
      expect(Math.hypot(
        g.pos[fC] - g.pos[bC],
        g.pos[fC + 1] - g.pos[bC + 1],
        g.pos[fC + 2] - g.pos[bC + 2])).toBeLessThan(1e-3)
      expect(Math.abs(g.pos[fC + 2])).toBeLessThan(1e-3)   // ±90°：z≈0
      expect(g.pos[fC]).toBeLessThan(0)                    // L 侧 −X
    })

    it(`${c.name}：内缝语义摆位 = 腿内侧线——z=0 中面上、|x|=腿内侧距（≥0.3 不越中线）、y=纸样高+lift`, () => {
      for (const p of g.parts) {
        const run = p.mesh.runs.find((r) => r.name === 'inseam')!
        expect(run.indices.length).toBeGreaterThan(0)
        const sgn = p.side === 'L' ? -1 : 1
        for (const i of run.indices) {
          const i3 = at(p, i)
          const yPat = p.mesh.xy[2 * i + 1]
          const medial = Math.max(
            axis.cAt(yPat) - (axis.rAt(yPat) + CORE_SKIN + HANG_PRIOR.garmentGap), 0.3)
          expect(Math.abs(g.pos[i3 + 2])).toBeLessThan(1e-3)   // 腿内侧线在中面
          expect(g.pos[i3] * sgn).toBeGreaterThanOrEqual(0.3 - 1e-6)
          expect(Math.abs(Math.abs(g.pos[i3]) - medial)).toBeLessThan(1e-3)
          expect(g.pos[i3 + 1])
            .toBeCloseTo(yPat + HANG_PRIOR.hangLift, 4)
        }
      }
    })

    it(`${c.name}：腿区腿局部圆环——fork 以下顶点距腿轴 ≈ rAt+skin+gap；hem 内角落腿内侧线`, () => {
      const forks = {
        front: payload.body.points.front_crotch_vertex[1],
        back: payload.body.points.back_crotch_vertex[1],
      }
      let checked = 0
      for (const p of g.parts) {
        const mesh = p.mesh
        const fork = forks[p.key as 'front' | 'back']
        const sgn = p.side === 'L' ? -1 : 1
        for (let i = 0; i < mesh.xy.length / 2; i++) {
          const yPat = mesh.xy[2 * i + 1]
          if (yPat >= fork) continue
          const i3 = at(p, i)
          const x = g.pos[i3] - 0, z = g.pos[i3 + 2]
          // 近裆钳位带（x·sgn = 0.3）不在此断言（内侧线收敛区）
          if (x * sgn <= 0.31) continue
          const d = Math.hypot(x - sgn * axis.cAt(yPat), z)
          expect(Math.abs(d - (axis.rAt(yPat) + CORE_SKIN + HANG_PRIOR.garmentGap)))
            .toBeLessThan(0.05)
          checked++
        }
      }
      expect(checked).toBeGreaterThan(200)   // 真跑了腿区（非全被钳位跳过）
      // hem 内角（inseam 端）落腿内侧线：末采样是内角（φ=0 精确、由
      // 内缝语义摆位覆盖）沿 hem 一个边界步长的邻点（φ≈0.25 → |x| 偏
      // ~0.4、z=r·sinφ≈1.8），只断言 x 侧、容差 2cm
      const hemF = part('front', 'R').mesh.runs.find((r) => r.name === 'hem')!
      const last = hemF.indices[hemF.indices.length - 1]
      const i3 = at(part('front', 'R'), last)
      const yHem = part('front', 'R').mesh.xy[2 * last + 1]
      const medial = Math.max(
        axis.cAt(yHem) - (axis.rAt(yHem) + CORE_SKIN + HANG_PRIOR.garmentGap), 0.3)
      expect(Math.abs(Math.abs(g.pos[i3]) - medial)).toBeLessThan(2.0)
    })

    it(`${c.name}：side 语义摆位 + 镜像对称 + 纸样空间穿透零`, () => {
      for (const p of g.parts) {
        for (const run of p.mesh.runs) {
          if (run.name !== 'side') continue
          for (const i of run.indices) {
            const i3 = at(p, i)
            expect(Math.abs(g.pos[i3 + 2])).toBeLessThan(1e-3)
            expect(g.pos[i3] * (p.side === 'L' ? -1 : 1)).toBeGreaterThan(0)
          }
        }
      }
      for (const key of ['front', 'back'] as const) {
        const mesh = part(key, 'L').mesh
        const xs: number[] = []
        for (let i = 0; i < mesh.xy.length / 2; i++) {
          const l = at(part(key, 'L'), i), r = at(part(key, 'R'), i)
          expect(g.pos[l + 1]).toBeCloseTo(g.pos[r + 1], 6)
          xs.push(Math.abs(g.pos[l] + g.pos[r]))
        }
        xs.sort((a, b) => a - b)
        expect(xs[Math.floor(xs.length / 2)]).toBeLessThan(0.1)
      }
      // 穿透零（截面环口径：腿内侧线在腿间隙里是合法布位，径向口径
      // 会误判——两腿分离芯只有截面/表面碰撞能表达腿间空隙）
      let penCount = 0
      for (let i3 = 0; i3 < g.pos.length; i3 += 3) {
        if (pointInRings(g.pos[i3], g.pos[i3 + 2],
          field.loopsAt(g.pos[i3 + 1] - HANG_PRIOR.hangLift))) penCount++
      }
      expect(penCount).toBe(0)
    })
  }
})

describe('assemble：腰头立体缝合（九期，用户口径「腰头两边是前中线、腰头中点是后中线」）', () => {
  const payload: FittingResult = JSON.parse(
    readFileSync(`${HERE}/fixture_fitting.json`, 'utf8'))
  const frontPanel = buildFrontPanel(payload)
  const backPanel = buildBackPanel(payload)
  const core = buildCore(payload)
  const field = buildBodyField(core.positions, core.indices)
  const band = buildWaistbandMesh(payload)!
  expect(band).toBeTruthy()
  const g = buildFullPair(frontPanel.host, backPanel.host, field, {
    front: payload.body.points.front_crotch_vertex[1],
    back: payload.body.points.back_crotch_vertex[1],
  }, buildLegAxis(payload), band)
  const seam = buildSeamSet(g)
  const bandPart = g.parts.find((p) => p.key === 'waistband')!
  const walk = ringWalk(g.parts)
  const chain = bandBottomChain(band)!
  const targets = bandTargets(band, walk)!

  it('第 5 part 结构 + 对账：带底弧长 ≈ 四段腰弧和（腰长不变量，直款 <0.5%）', () => {
    expect(g.parts).toHaveLength(5)
    expect(bandPart.offset).toBe(g.total - band.xy.length / 2)
    expect(Math.abs(chain.runLength - walk.total) / walk.total).toBeLessThan(0.005)
  })

  it('两端在前中、中点在后中（用户口径的量化）：u=0/1 环伙伴 θ≈0(+Z)、u=0.5 伙伴 θ≈−180(−Z)', () => {
    const ringPos = (ringK: number): [number, number, number] => {
      const r = walk.verts[ringK]
      const v = g.parts[r.part]
      const i3 = 3 * (v.offset + r.idx)
      return [g.pos[i3], g.pos[i3 + 1], g.pos[i3 + 2]]
    }
    const ends: [number, number][] = [
      [0, chain.indices[0]],
      [1, chain.indices[chain.indices.length - 1]],
    ]
    for (const [, vi] of ends) {
      const [x, , z] = ringPos(targets[vi].ringK)
      expect(Math.abs(x)).toBeLessThan(0.05)   // 前中面
      expect(z).toBeGreaterThan(10)            // +Z 前中
    }
    const mid = chain.indices[Math.floor(chain.indices.length / 2)]
    const [mx, , mz] = ringPos(targets[mid].ringK)
    expect(Math.abs(mx)).toBeLessThan(0.05)    // 后中面
    expect(mz).toBeLessThan(-10)               // −Z 后中
  })

  it('bandWaist 摆位即闭：全部底边焊对初始距离 = 0（带底=环顶点原位）', () => {
    const gw = seam.groups.find((s) => s.name === 'bandWaist')!
    // ≥ 底边链顶点数：接缝孪生角（前中/后中镜像角）追加配对
    expect(gw.pairCount).toBeGreaterThanOrEqual(chain.indices.length)
    for (let p = 0; p < gw.pairCount; p++) {
      const a = 3 * seam.pairs[2 * (gw.pairOffset + p)]
      const b = 3 * seam.pairs[2 * (gw.pairOffset + p) + 1]
      expect(Math.hypot(g.pos[a] - g.pos[b], g.pos[a + 1] - g.pos[b + 1],
        g.pos[a + 2] - g.pos[b + 2])).toBeLessThan(1e-6)
    }
  })

  it('带高 = width：全部带顶点 v ∈ [0, width]（带法向距离，弯款曲线底边口径）', () => {
    const width = payload.pieces.find((p) => p.key === 'waistband')!.scalars!.width
    for (const t of targets) {
      expect(t.v).toBeGreaterThanOrEqual(-0.01)
      expect(t.v).toBeLessThanOrEqual(width + 0.01)
    }
  })

  it('bandEnds 前中 weld 两端共位（扣好闭合环）', () => {
    const ge = seam.groups.find((s) => s.name === 'bandEnds')!
    expect(ge.pairCount).toBeGreaterThan(0)
    for (let p = 0; p < ge.pairCount; p++) {
      const a = 3 * seam.pairs[2 * (ge.pairOffset + p)]
      const b = 3 * seam.pairs[2 * (ge.pairOffset + p) + 1]
      expect(Math.hypot(g.pos[a] - g.pos[b], g.pos[a + 1] - g.pos[b + 1],
        g.pos[a + 2] - g.pos[b + 2])).toBeLessThan(0.5)
    }
  })
})

// ---- 穿台腰圈摆位（2026-09-19 形随体长随衣；2026-09-20 间隙均匀）----
// 合成椭圆截面场（腰行 a=12/b=10、向上逐行收窄——模拟腰上方围收窄），
// 验 buildWaistRing + buildFullPair 环分支：形状来自截面、长度 = 成衣
// 腰长 C（带底净长）、间隙均匀（等距外偏 |δ| 恒定）；顶链/带底贴环、
// 侧缝腰角随弧位前移（≠±90° 硬切）、带顶贴带顶环（收窄行 → 顶环更拢）；
// 旁挂既有断言不受影响（上方双款未传 waistRing = 字节等价回归）
describe('assemble：穿台腰圈摆位（形随体长随衣+间隙均匀，合成椭圆场）', () => {
  const payload: FittingResult = JSON.parse(
    readFileSync(`${HERE}/fixture_fitting.json`, 'utf8'))
  const frontPanel = buildFrontPanel(payload)
  const backPanel = buildBackPanel(payload)
  const band = buildWaistbandMesh(payload)!
  const C = bandBottomChain(band)!.runLength
  // 行表 yMin=0 / rowStep=0.5，行 192~208（y 96~104）放椭圆环：向上收窄
  // 只收 a（X 侧向）——均匀缩放行偏移到同一 C 时 δ 顶抬升回补半径（maxR
  // 对比弱），非均匀收窄才出「带顶环更拢」；其余行空（摆位只消费腰口
  // 附近行）
  const ellipse = (a: number, b: number): SliceRing => {
    const n = 48
    const pts = new Float64Array(2 * n)
    let cx = 0, cz = 0
    for (let k = 0; k < n; k++) {
      const t = (k / n) * 2 * Math.PI
      pts[2 * k] = a * Math.cos(t)
      pts[2 * k + 1] = b * Math.sin(t)
      cx += pts[2 * k]; cz += pts[2 * k + 1]
    }
    return { pts, cx: cx / n, cz: cz / n, r: Math.max(a, b) }
  }
  const slices: SliceRing[][] = []
  const rows = 221
  for (let r = 0; r < rows; r++) {
    const y = r * 0.5
    slices.push(y >= 96 && y <= 104
      ? [ellipse(12 - 0.15 * (y - 98), 10 - 0.02 * (y - 98))] : [])
  }
  const field = new BodyField(
    new Float32Array(rows * 8), rows, 0.5, 8, slices, 0)
  const ring = buildWaistRing(field, 98, C)
  const g = buildFullPair(frontPanel.host, backPanel.host, field, {
    front: payload.body.points.front_crotch_vertex[1],
    back: payload.body.points.back_crotch_vertex[1],
  }, buildLegAxis(payload), band, 0, ring)
  const walk = ringWalk(g.parts.filter((p) => p.key !== 'waistband'))
  const bandPart = g.parts.find((p) => p.key === 'waistband')!
  const bandTop = bandPart.mesh.runs.find((r) => r.name === 'top')!
  const bandBot = bandBottomChain(bandPart.mesh)!
  // 点到环折线最小距（顶链贴环断言）
  const distToRing = (rg: WaistRing, x: number, z: number): number => {
    const n = rg.pts.length / 2
    let dMin = Infinity
    for (let k = 0; k < n; k++) {
      const k2 = (k + 1) % n
      const ax = rg.pts[2 * k], az = rg.pts[2 * k + 1]
      const ex = rg.pts[2 * k2] - ax, ez = rg.pts[2 * k2 + 1] - az
      const l2 = ex * ex + ez * ez
      const t = l2 > 1e-12
        ? Math.max(0, Math.min(1, ((x - ax) * ex + (z - az) * ez) / l2)) : 0
      dMin = Math.min(dMin, Math.hypot(x - (ax + ex * t), z - (az + ez * t)))
    }
    return dMin
  }

  it('环长 = 成衣腰长（定点迭代收敛 <1e-4）；顶链逐点贴环（Float32 量化 1e-4）', () => {
    expect(Math.abs(ring.total - C) / C).toBeLessThan(1e-4)
    for (const v of walk.verts) {
      const part = g.parts[v.part]
      const i3 = 3 * (part.offset + v.idx)
      expect(distToRing(ring, g.pos[i3], g.pos[i3 + 2])).toBeLessThan(1e-4)
    }
  })

  it('环点到体截面边界等距（间隙均匀——每点 ≈ 同一 δ，spread <0.05）', () => {
    // 等距外偏的直接判据：钉环每点到源截面边界折线的最短距 ≈ 同一 δ
    // （重采样 + 顶点角平分法线偏移的理论误差 <0.01）。旧「绕原点放大」
    // 口径此量 ∝ 点到原点距离（真人截面实测前后差 5.5:1——环整体前骑），
    // 本断言即钉死该回归
    const loops = field.loopsAt(98)
    const dists: number[] = []
    for (let k = 0; k < ring.pts.length / 2; k++) {
      let dMin = Infinity
      for (const lp of loops) {
        const m = lp.pts.length / 2
        for (let s = 0; s < m; s++) {
          const s2 = (s + 1) % m
          const ax = lp.pts[2 * s], az = lp.pts[2 * s + 1]
          const ex = lp.pts[2 * s2] - ax, ez = lp.pts[2 * s2 + 1] - az
          const l2 = ex * ex + ez * ez
          const t = l2 > 1e-12
            ? Math.max(0, Math.min(1, ((ring.pts[2 * k] - ax) * ex
              + (ring.pts[2 * k + 1] - az) * ez) / l2)) : 0
          dMin = Math.min(dMin, Math.hypot(
            ring.pts[2 * k] - (ax + ex * t), ring.pts[2 * k + 1] - (az + ez * t)))
        }
      }
      dists.push(dMin)
    }
    expect(Math.max(...dists) - Math.min(...dists)).toBeLessThan(0.05)
  })

  it('侧缝腰角沿钉环弧位落位（≠±90° 硬切）且前后宿主共点（腰圆闭合）', () => {
    for (const [key, side, sgn] of [
      ['front', 'L', -1], ['back', 'L', -1],
    ] as const) {
      const p = g.parts.find(
        (q) => q.key === key && q.side === side)!
      const runs = p.mesh.runs.filter((r) => r.name === 'side')
      const top = runs.reduce((a, b) =>
        p.mesh.xy[2 * b.indices[0] + 1] > p.mesh.xy[2 * a.indices[0] + 1] ? b : a)
      const i3 = 3 * (p.offset + top.indices[0])
      // 角点弧位 = 布弧分数 × 环弧速，漂移方向/幅度随截面形状与布量分布
      // （真人截面前移 ~73°、对称椭圆恰落截面 1/4 弧 z≈0），非不变量、
      // 不定向断言。判别「≠±90° 硬切」= 角点在钉环上 + 落侧区真实半径
      // （本合成场 θ 表全 0，径向场路径只会给 r≈gap=1.2——x>5 即证走钉环）
      expect(distToRing(ring, g.pos[i3], g.pos[i3 + 2])).toBeLessThan(1e-3)
      expect(g.pos[i3] * sgn, `${key} 角在侧`).toBeGreaterThan(5)
    }
    const fRuns = g.parts[0].mesh.runs.filter((r) => r.name === 'side')
    const bRuns = g.parts[2].mesh.runs.filter((r) => r.name === 'side')
    const fTop = fRuns.reduce((a, b) =>
      g.parts[0].mesh.xy[2 * b.indices[0] + 1]
        > g.parts[0].mesh.xy[2 * a.indices[0] + 1] ? b : a)
    const bTop = bRuns.reduce((a, b) =>
      g.parts[2].mesh.xy[2 * b.indices[0] + 1]
        > g.parts[2].mesh.xy[2 * a.indices[0] + 1] ? b : a)
    const fI = 3 * (g.parts[0].offset + fTop.indices[0])
    const bI = 3 * (g.parts[2].offset + bTop.indices[0])
    expect(Math.hypot(g.pos[fI] - g.pos[bI], g.pos[fI + 1] - g.pos[bI + 1],
      g.pos[fI + 2] - g.pos[bI + 2])).toBeLessThan(1e-3)
  })

  it('带底贴腰环、带顶贴带顶环（收窄行 → 顶环同向更拢）、两缘弦和 ≈ C', () => {
    // 带底 = f0 贴环；带顶：行截面非均匀收窄（a 收 b 持平）→ 顶环径向
    // 比腰环更拢（同向对比 max 对 max——椭圆各向半径不同，min/max 交叉
    // 无意义）
    let topMaxR = 0, botMaxR = 0
    for (const i of bandTop.indices) {
      const i3 = 3 * (bandPart.offset + i)
      topMaxR = Math.max(topMaxR, Math.hypot(g.pos[i3], g.pos[i3 + 2]))
    }
    for (const i of bandBot.indices) {
      const i3 = 3 * (bandPart.offset + i)
      botMaxR = Math.max(botMaxR, Math.hypot(g.pos[i3], g.pos[i3 + 2]))
    }
    expect(topMaxR).toBeLessThan(botMaxR - 0.1)
    const chordOf = (idx: number[]): number => {
      let s = 0
      for (let k = 0; k + 1 < idx.length; k++) {
        const aI = 3 * (bandPart.offset + idx[k])
        const bI = 3 * (bandPart.offset + idx[k + 1])
        s += Math.hypot(g.pos[aI] - g.pos[bI], g.pos[aI + 1] - g.pos[bI + 1],
          g.pos[aI + 2] - g.pos[bI + 2])
      }
      return s
    }
    // 带顶容差略宽（2.5%）：端帽列 v<带宽，XZ 沿底→顶环直线插值走割线
    // （合成直款实测 +1.6%），缝焊吸收量级；带底钉环原位 1.5%
    expect(Math.abs(chordOf(bandTop.indices) - C) / C).toBeLessThan(0.025)
    expect(Math.abs(chordOf(bandBot.indices) - C) / C).toBeLessThan(0.015)
  })

  it('L/R 镜像对称（对称椭圆场下左右半环逐点镜像）', () => {
    for (const key of ['front', 'back'] as const) {
      const xs: number[] = []
      const mesh = g.parts.find((p) => p.key === key && p.side === 'L')!.mesh
      for (let i = 0; i < mesh.xy.length / 2; i++) {
        const l = g.parts.find((p) => p.key === key && p.side === 'L')!
        const r = g.parts.find((p) => p.key === key && p.side === 'R')!
        const li = 3 * (l.offset + i), ri = 3 * (r.offset + i)
        expect(g.pos[li + 1]).toBeCloseTo(g.pos[ri + 1], 6)
        xs.push(Math.abs(g.pos[li] + g.pos[ri]))
      }
      xs.sort((a, b) => a - b)
      expect(xs[Math.floor(xs.length / 2)]).toBeLessThan(0.1)
    }
  })

  it('偏小环（C−4）δ<0：钉位均匀内嵌截面内（穿不进摆位侧把门）', () => {
    const small = buildWaistRing(field, 98, C - 4)
    const p = ringPointAt(small, small.total * 0.25)
    expect(pointInRings(p.x, p.z, field.loopsAt(98))).toBe(true)
    const p2 = ringPointAt(small, 0)
    expect(pointInRings(p2.x, p2.z, field.loopsAt(98))).toBe(true)
  })
})
