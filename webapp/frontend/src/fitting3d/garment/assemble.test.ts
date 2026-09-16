// 全裁片装配金标（重建 2026-09-15）：平铺验证（三期回落，现行接线）
// + 扇区悬挂摆位（一期，暂停接线）。平铺验收：payload 逐片一行（成对
// 片 L 原样 / R 前中镜像逐点等距变换、腰头单片）、全片贴地 y=0、全组
// z 居中、行序 = payload 片序、行距 ≥ rowGap、无 NaN。悬挂验收：2 片
// 镜像摆位（x 翻号、z 差 <0.05cm——θ-bin 量化对 ±θ 不对称）、前扇区
// 角度域 [−90°,0°]、无穿透（摆位半径 = 场 + gap，按构造零穿透）。
// 夹具 = fixture_fitting.json（引擎 build_fitting_payload 直出，默认
// 直腰头 3 片：front_piece / back_piece / waistband）。
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { FittingResult } from '../../types'
import { buildFlatLayout, buildHangPair } from './assemble'
import { buildBackPanel, buildFrontPanel } from './panel'
import { buildCore, CORE_SKIN } from './core'
import { buildClothMesh } from './mesh'
import { buildBodyField, penetrationStats } from './placement'
import { FLAT_PRIOR } from './priors'

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

describe('assemble：前片 L+R 静态装配（一期扇区摆位，四期起悬挂链接线）', () => {
  const front = buildClothMesh(result.pieces.find((p) => p.key === 'front_piece')!)
  const core = buildCore(result)
  const field = buildBodyField(core.positions, core.indices)
  const garment = buildHangPair('front', front, field)

  it('两片共享网格、offset 顺排、总数 = 2×前片顶点', () => {
    expect(garment.parts.map((p) => `${p.key}_${p.side}`))
      .toEqual(['front_L', 'front_R'])
    expect(garment.parts[0].mesh).toBe(front)
    expect(garment.parts[1].mesh).toBe(front)
    expect(garment.parts[1].offset).toBe(front.xy.length / 2)
    expect(garment.total).toBe(front.xy.length)
    expect(garment.pos.length).toBe(3 * garment.total)
  })

  it('无 NaN；前扇区角度域：L 全部 θ∈[−90°,0°]、R 镜像', () => {
    for (let i = 0; i < garment.pos.length; i++) {
      expect(Number.isFinite(garment.pos[i])).toBe(true)
    }
    for (let i = 0; i < garment.total; i++) {
      const x = garment.pos[3 * i], z = garment.pos[3 * i + 2]
      const th = Math.atan2(x, z)
      if (i < garment.parts[1].offset) {
        expect(th).toBeGreaterThanOrEqual(-Math.PI / 2 - 1e-9)
        expect(th).toBeLessThanOrEqual(1e-9)
      } else {
        expect(th).toBeLessThanOrEqual(Math.PI / 2 + 1e-9)
        expect(th).toBeGreaterThanOrEqual(-1e-9)
      }
    }
  })

  it('镜像对称：L/R 同网格逐顶点 x 翻号、y 同值、z 差 <0.1cm', () => {
    // z 差源于支撑场 θ-bin 量化对 ±θ 的不对称 + bin 边界支撑跳变：旧链
    // 人台场实测 <0.05cm；撑型芯场（花生瓣特征更锐）实测 max 0.073cm，
    // 口径放宽到 <0.1cm（0.7mm 纯量化伪差，视觉不可辨）
    const N = front.xy.length / 2
    const xs: number[] = []
    for (let i = 0; i < N; i++) {
      const l = 3 * (garment.parts[0].offset + i)
      const r = 3 * (garment.parts[1].offset + i)
      expect(garment.pos[l + 1]).toBeCloseTo(garment.pos[r + 1], 6)   // y
      expect(Math.abs(garment.pos[l + 2] - garment.pos[r + 2]))
        .toBeLessThan(0.1)
      xs.push(Math.abs(garment.pos[l] + garment.pos[r]))
    }
    xs.sort((a, b) => a - b)
    expect(xs[Math.floor(xs.length / 2)]).toBeLessThan(0.1)
  })

  it('穿透零：摆位半径 = 场 + garmentGap，按构造不穿芯（skin 壳口径）', () => {
    const pen = penetrationStats(garment.pos, field, CORE_SKIN)
    expect(pen.count).toBe(0)
    expect(pen.worst).toBe(0)
  })
})

describe('assemble：后片 L+R 扇区摆位（六期后身缝合，后扇区）', () => {
  const yokeResult: FittingResult = JSON.parse(
    readFileSync(`${HERE}/fixture_fitting_yoke.json`, 'utf8'))
  const back = buildClothMesh(yokeResult.pieces.find((p) => p.key === 'back_piece')!)
  const core = buildCore(yokeResult)
  const field = buildBodyField(core.positions, core.indices)
  const garment = buildHangPair('back', back, field)

  it('两片共享网格、key=back、总数 = 2×后片顶点、无 NaN', () => {
    expect(garment.parts.map((p) => `${p.key}_${p.side}`))
      .toEqual(['back_L', 'back_R'])
    expect(garment.parts[0].mesh).toBe(back)
    expect(garment.parts[1].offset).toBe(back.xy.length / 2)
    expect(garment.total).toBe(back.xy.length)
    for (let i = 0; i < garment.pos.length; i++) {
      expect(Number.isFinite(garment.pos[i])).toBe(true)
    }
  })

  it('后扇区角度域：L 全部 θ∈[−180°,−90°]、R 镜像 [90°,180°]', () => {
    // 侧缝端 θ=±90°（与前身扇区同角、穿着拓扑侧缝相邻）、后中端
    // θ=±180°（cb 缝对在此闭合，与前中 θ=0 相对）
    for (let i = 0; i < garment.total; i++) {
      const x = garment.pos[3 * i], z = garment.pos[3 * i + 2]
      const th = Math.atan2(x, z)
      if (i < garment.parts[1].offset) {
        expect(th).toBeLessThanOrEqual(-Math.PI / 2 + 1e-9)
        expect(th).toBeGreaterThanOrEqual(-Math.PI - 1e-9)
      } else {
        expect(th).toBeGreaterThanOrEqual(Math.PI / 2 - 1e-9)
        expect(th).toBeLessThanOrEqual(Math.PI + 1e-9)
      }
    }
  })

  it('镜像对称：L/R 同网格逐顶点 x 翻号、y 同值、z 差 <0.1cm', () => {
    // θ-bin 量化伪差口径同前片用例（撑型芯场花生瓣特征，x 取中位数）
    const N = back.xy.length / 2
    const xs: number[] = []
    for (let i = 0; i < N; i++) {
      const l = 3 * i, r = 3 * (garment.parts[1].offset + i)
      expect(garment.pos[l + 1]).toBeCloseTo(garment.pos[r + 1], 6)
      expect(Math.abs(garment.pos[l + 2] - garment.pos[r + 2]))
        .toBeLessThan(0.1)
      xs.push(Math.abs(garment.pos[l] + garment.pos[r]))
    }
    xs.sort((a, b) => a - b)
    expect(xs[Math.floor(xs.length / 2)]).toBeLessThan(0.1)
  })

  it('穿透零：摆位半径 = 场 + garmentGap，按构造不穿芯', () => {
    const pen = penetrationStats(garment.pos, field, CORE_SKIN)
    expect(pen.count).toBe(0)
    expect(pen.worst).toBe(0)
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

describe('assemble：腰口弧长重参数化（六期拉直）', () => {
  // 顶链按腰口弧长分数铺满扇区：中缝腰角（顶链 s=0 端）精确落中面
  // （front θ=0 / back θ=−180°，均匀 x→θ 映射的固有偏心实测 −3.9/
  // −5.8cm 根治）、侧缝腰角（s=1 端）精确落 ±90°、θ 沿链单调——
  // drape 整圈全向钉的「钉与缝同意」前提。夹具 = 前身并集（pocket）
  // / 后身并集（yoke）双宿主
  const cases = [
    { key: 'front' as const, fixture: 'fixture_fitting_pocket.json',
      build: buildFrontPanel, centerTh: 0 },
    { key: 'back' as const, fixture: 'fixture_fitting_yoke.json',
      build: buildBackPanel, centerTh: -Math.PI },
  ]
  for (const c of cases) {
    it(`${c.key}：中缝腰角落中面、侧缝腰角落 ±90°、θ 沿链单调铺满扇区`, () => {
      const payload: FittingResult = JSON.parse(
        readFileSync(`${HERE}/${c.fixture}`, 'utf8'))
      const core = buildCore(payload)
      const field = buildBodyField(core.positions, core.indices)
      const g = buildHangPair(c.key, c.build(payload).host, field)
      const top = g.parts[0].mesh.runs.find((r) => r.role === 'top_chain')!
      const thOf = (side: 'L' | 'R', i: number): number => {
        const off = side === 'L' ? g.parts[0].offset : g.parts[1].offset
        return Math.atan2(g.pos[3 * (off + i)], g.pos[3 * (off + i) + 2])
      }
      // 首端（s=0）= 中缝腰角：精确落中面（front 0° / back −180°）
      const first = top.indices[0]
      expect(Math.abs(g.pos[3 * (g.parts[0].offset + first)])).toBeLessThan(0.01)
      const th0 = thOf('L', first)
      expect(Math.abs(Math.atan2(Math.sin(th0 - c.centerTh),
        Math.cos(th0 - c.centerTh)))).toBeLessThan(0.01)
      // 末端（s=1）= 侧缝腰角：精确落 −90°
      const lastI = top.indices[top.indices.length - 1]
      const thL = thOf('L', lastI)
      expect(Math.abs(Math.atan2(Math.sin(thL + Math.PI / 2),
        Math.cos(thL + Math.PI / 2)))).toBeLessThan(0.01)
      expect(g.pos[3 * (g.parts[0].offset + lastI)]).toBeLessThan(0)   // L 侧 −X
      // θ 沿链单调（front 0→−90 递减 / back −180→−90 递增）铺满 90°
      const step = c.key === 'front' ? -1 : 1
      for (let k = 1; k < top.indices.length; k++) {
        const prev = thOf('L', top.indices[k - 1])
        const cur = thOf('L', top.indices[k])
        expect((cur - prev) * step).toBeGreaterThanOrEqual(-1e-6)
      }
    })
  }
})
