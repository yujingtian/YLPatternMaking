// 穿台几何原语金标（2026-09-18）：placement 穿台三原语（shiftPositionsY /
// nearestRingBoundary / buildLegAxisFromRings）的合成场单元验证——真产物
// 集成（dress.test.ts）前的层间把门。全部手搓可精确断言的几何：
// 正多边形环（质心=圆心）、合成 BodyField（只喂 slices——腿轴/边界查询
// 不读场表）。演进口径见 settle.ts 头注与 .doc/python工程设计.md §10.11。
import { describe, expect, it } from 'vitest'
import {
  BodyField, buildFootCurtain, buildLegAxisFromRings, curtainAt,
  nearestRingBoundary, pointInRings, shiftPositionsY, topSupportY,
  type SliceRing,
} from './placement'
import { CORE_SKIN, type LegAxis } from './core'
import { HANG_PRIOR } from './priors'

// 正 n 边形环（顶点在半径 r 的圆上；质心≈圆心、包围半径=r，构造即知）
const ring = (cx: number, cz: number, r: number, n = 16): SliceRing => {
  const pts = new Float64Array(2 * n)
  for (let k = 0; k < n; k++) {
    const th = (k / n) * 2 * Math.PI
    pts[2 * k] = cx + r * Math.cos(th)
    pts[2 * k + 1] = cz + r * Math.sin(th)
  }
  return { pts, cx, cz, r }
}

describe('shiftPositionsY（世界→纸样系 frame 锚定）', () => {
  it('只动 Y、原数组不改写、1:1 cm 无缩放', () => {
    const src = new Float32Array([1, 2, 3, 4, 5, 6])
    const out = shiftPositionsY(src, -7.5)
    expect(Array.from(out)).toEqual([1, -5.5, 3, 4, -2.5, 6])
    expect(out).not.toBe(src)
    expect(src[1]).toBe(2)   // 原数组不被改写（morph 输出同契约）
  })
})

describe('nearestRingBoundary（最近边界+外法线，collide/探针共口径）', () => {
  it('环内点：d=到边界距离、法线朝外（沿 +法线出界、−法线入内）', () => {
    const R = ring(0, 0, 5)
    const hit = nearestRingBoundary([R], 0, 0, 0.98)
    expect(hit).not.toBeNull()
    // 圆心到 16 边形边距离 = r·cos(π/16) ≈ 4.952
    expect(hit!.d).toBeGreaterThan(4.9)
    expect(hit!.d).toBeLessThan(5.0)
    expect(pointInRings(hit!.px + hit!.nx * 0.05, hit!.pz + hit!.nz * 0.05, [R]))
      .toBe(false)   // 边界沿外法线跨出 = 环外
    expect(pointInRings(hit!.px - hit!.nx * 0.05, hit!.pz - hit!.nz * 0.05, [R]))
      .toBe(true)    // 反向跨回 = 环内
  })

  it('环外近壳点：d=到边界距离；超出 margin quick reject 返回 null', () => {
    const R = ring(0, 0, 5)
    const near = nearestRingBoundary([R], 6, 0, 2.98)
    expect(near).not.toBeNull()
    // 16 边形顶点恰在 +x 向（k=0, θ=0）→ 最近边界 = 顶点 (5,0)，d = 1 精确
    expect(near!.d).toBeCloseTo(1.0, 6)
    expect(nearestRingBoundary([R], 20, 0, 2.98)).toBeNull()   // 远超余量
  })

  it('双环（两腿）：腿间点归最近环、法线背离所属环质心', () => {
    const L = ring(-3, 0, 2), Rt = ring(3, 0, 2)
    const rings = [L, Rt]
    // +0.6 侧点：最近 = 右腿环左缘（x≈1.04），外法线朝 −x（背离右腿质心）
    const hr = nearestRingBoundary(rings, 0.6, 0, 2)
    expect(hr).not.toBeNull()
    expect(hr!.px).toBeGreaterThan(0.9)
    expect(hr!.nx).toBeLessThan(0)
    // −0.6 侧点镜像：最近 = 左腿环右缘，外法线朝 +x
    const hl = nearestRingBoundary(rings, -0.6, 0, 2)
    expect(hl).not.toBeNull()
    expect(hl!.px).toBeLessThan(-0.9)
    expect(hl!.nx).toBeGreaterThan(0)
  })
})

describe('buildLegAxisFromRings（人台切片环 → 腿轴）', () => {
  const mkField = (slices: SliceRing[][], yMin = 0): BodyField =>
    new BodyField(new Float32Array(slices.length * 8), slices.length, 0.5, 8, slices, yMin)

  // 下半身合成场：row 0..12（y 0..6）双腿分离（cx=±(3+0.02r)、r=2+0.01r），
  // row 13..24（y 6.5..12）躯干单环
  const bodyField = (): SliceRing[][] => {
    const slices: SliceRing[][] = []
    for (let r = 0; r <= 24; r++) {
      if (r <= 12) {
        const c = 3 + 0.02 * r, rad = 2 + 0.01 * r
        slices.push([ring(-c, 0, rad), ring(c, 0, rad)])
      } else {
        slices.push([ring(0, 0, 6)])
      }
    }
    return slices
  }

  it('自裆地标向下搜首个双腿分离行；rAt/cAt 沿行线性插值 + 域外钳端', () => {
    const field = mkField(bodyField())
    // forkY=7.0 在单环区 → 向下（r0=14 → rMin=2）首个 2 环行 = r12（y=6.0）
    const axis = buildLegAxisFromRings(field, 7.0)
    expect(axis.forkY).toBeCloseTo(6.0, 10)
    // rProf：(0, 2.0) .. (6, 2.12) 线性
    expect(axis.rAt(0)).toBeCloseTo(2.0, 10)
    expect(axis.rAt(3)).toBeCloseTo(2.06, 10)
    expect(axis.rAt(6)).toBeCloseTo(2.12, 10)
    expect(axis.rAt(-5)).toBeCloseTo(2.0, 10)    // 下方域外钳端值
    expect(axis.rAt(10)).toBeCloseTo(2.12, 10)   // 上方域外钳端值
    // cProf：(0, 3.0) .. (6, 3.24)
    expect(axis.cAt(3)).toBeCloseTo(3.12, 10)
  })

  it('forkY 已在双腿分离区：该行即叉口', () => {
    const axis = buildLegAxisFromRings(mkField(bodyField()), 5.0)
    expect(axis.forkY).toBeCloseTo(5.0, 10)
  })

  it('窗内无双腿分离行必须炸（人台切片未分开 = 摆位无从谈起）', () => {
    const all: SliceRing[][] = []
    for (let r = 0; r <= 24; r++) all.push([ring(0, 0, 6)])
    expect(() => buildLegAxisFromRings(mkField(all), 7.0)).toThrow(/无双腿分离行/)
  })

  it('双腿分离行不足 2 行必须炸（无法插值）', () => {
    const one: SliceRing[][] = []
    for (let r = 0; r <= 24; r++) {
      one.push(r === 10 ? [ring(-3, 0, 2), ring(3, 0, 2)] : [ring(0, 0, 6)])
    }
    expect(() => buildLegAxisFromRings(mkField(one), 7.0)).toThrow(/不足 2 行/)
  })

  // ---- 脚碰撞修复（2026-09-18）：yMin 场域下探 + 腿轴止踝 ----

  it('yMin 场：负 y 域有环（盲区消除）、行号/forkY 按 yMin 换算', () => {
    // 行 r 高 = yMin + r·0.5；行 0..12 双腿。yMin=−8 → 纸样 −8..4.5 是腿区
    const field = mkField(bodyField(), -8)
    expect(field.yMin).toBe(-8)
    // 旧口径盲区（负 y 一律夹行 0）不复存在：−7.5 → round((−7.5+8)/0.5)=1
    expect(field.loopsAt(-7.5).length).toBe(2)
    // 表底之下仍夹行 0（不越界）
    expect(field.loopsAt(-8.4).length).toBe(2)
    // 表域上方单环躯干：y = −8 + 13×0.5 = −1.5
    expect(field.loopsAt(-1.5).length).toBe(1)
    // forkY 传入是场系（yMin 下移后腿区 y∈[−8,−2]、躯干 y≥−1.5，裆上方
    // 纸样 y=1.0 在躯干区）→ 叉口行 12；forkY = yMin + forkRow·step = −8+6.0
    const axis = buildLegAxisFromRings(field, 1.0)
    expect(axis.forkY).toBeCloseTo(-2.0, 10)
    // rProf 横轴是纸样 y：rAt(−8) = 首行 2.0、rAt(−5) = 行 6 值 2.06
    expect(axis.rAt(-8)).toBeCloseTo(2.0, 10)
    expect(axis.rAt(-5)).toBeCloseTo(2.06, 10)
  })

  it('ankleY 止踝：脚环（大包围半径）不进 rProf，摆位半径不被脚撑开', () => {
    // 行 0..3 = 双脚环（r 18 模拟脚全长前伸），行 4..12 = 双腿，13..24 躯干
    const footField: SliceRing[][] = []
    for (let r = 0; r <= 24; r++) {
      if (r <= 3) footField.push([ring(-11, 13, 18), ring(11, 13, 18)])
      else if (r <= 12) {
        const c = 3 + 0.02 * r, rad = 2 + 0.01 * r
        footField.push([ring(-c, 0, rad), ring(c, 0, rad)])
      } else footField.push([ring(0, 0, 6)])
    }
    // 不传 ankleY（老口径）：脚环进 rProf → rAt(0) = r+|cz| = 18+13 = 31
    // （包围圆按 (cx,0) 圆心放大 |cz| 口径——喇叭张开）
    const blind = buildLegAxisFromRings(mkField(footField), 7.0)
    expect(blind.rAt(0)).toBeCloseTo(31, 10)
    // 传踝地标 y=2.0（= 行 4）：扫描止于踝，rProf 首行 = 行 4 → rAt(0) 钳踝值
    const axis = buildLegAxisFromRings(mkField(footField), 7.0, 2.0)
    expect(axis.rAt(0)).toBeCloseTo(2.04, 10)   // 行 4：rad = 2+0.01×4
    expect(axis.rAt(2.0)).toBeCloseTo(2.04, 10)
    expect(axis.forkY).toBeCloseTo(6.0, 10)     // 叉口不受踝下限影响
  })
})

// ---- 上表面竖直支撑（2026-09-20 长裤穿台「脚背盖布」）----
// 合成锥/柱场：行 r 单环半径 R0 − s·r（s = 每行回缩）。查询点沿边中点
// 方向 θ=π/16（16 边形边垂距 = r·cos(π/16)，精确可手算）。g = 2·s·
// cos(π/16)（rowStep 0.5）：锥 s=1 g≈1.96、缓锥 s=0.5 g≈0.98（趾盒冠
// 量级）均 ≥ 阈 0.6 = 上表面；柱 s=0 g→0 = 垂直墙；更缓 s=0.25
// g≈0.49 < 阈 = 陡坡交水平推出。阈 2026-09-20 自 1（45°）降至 0.6
// （~31°）——趾盒冠实测 g≈0.8 需接管，45° 会漏（脚口前缘在趾盒顶滑脱）
describe('topSupportY（上表面竖直支撑：锥支撑/墙 null/埋点救援）', () => {
  const c = Math.cos(Math.PI / 16)
  const mkCone = (radii: number[]): BodyField => {
    const slices = radii.map((r) => [ring(0, 0, r)])
    return new BodyField(
      new Float32Array(slices.length * 8), slices.length, 0.5, 8, slices, 0)
  }
  // 锥场：行 0..6 半径 6−r（每行回缩 1），行 7..9 空（锥尖上无几何）
  const cone = mkCone([6, 5, 4, 3, 2, 1, 0.5, 0, 0, 0].map((r) => Math.max(r, 0.05)))
  // 查询点 d0=3.2：行 2 环内（apothem 4c≈3.923）、行 3 环外（3c≈2.942）
  // → 交叉带 [2,3]；真交叉高 = (2 + (4c−3.2)/c)·0.5；g = 2c；ny = g/√(1+g²)
  const d0 = 3.2
  const qx = d0 * c, qz = d0 * Math.sin(Math.PI / 16)
  const g = 2 * c
  const expectY = (rd: number, rAtRd: number, rAtUp: number): number => {
    const dA = rAtRd * c - d0, dB = d0 - rAtUp * c
    return (rd + dA / (dA + dB)) * 0.5 + CORE_SKIN * (g / Math.sqrt(1 + g * g))
  }

  it('壳上驻留位（自身行环外）：向下扫回交叉带，值 = 交叉高 + skin·ny', () => {
    // patY 2.0 → 行 4 环外 → 扫下至行 2；目标 2.24 > patY（抬到壳上）
    const y = topSupportY(cone, qx, qz, 2.0)!
    expect(y).toBeCloseTo(expectY(2, 4, 3), 6)
    expect(y).toBeGreaterThan(2.0)
  })

  it('恰在交叉带（下行含上行不含）：rd = 自身行', () => {
    const y = topSupportY(cone, qx, qz, 1.4)!   // 行 2 含、行 3 不含
    expect(y).toBeCloseTo(expectY(2, 4, 3), 6)
  })

  it('埋点救援（自身行环内+上行也内）：向上扫到头顶坡面出口抬回', () => {
    // patY 0.2（行 0 含、行 1 含）→ 上扫行 2 含、行 3 出 → rd=2，
    // 目标 = 同一交叉带高（2.24 > 0.2 = 大幅上抬出坡）
    const y = topSupportY(cone, qx, qz, 0.2)!
    expect(y).toBeCloseTo(expectY(2, 4, 3), 6)
    expect(y).toBeGreaterThan(2.0)
  })

  it('墙（柱面：上行永不含出口）→ null 交水平推出', () => {
    const wall = mkCone(new Array(10).fill(5))
    expect(topSupportY(wall, 3.2 * c, 3.2 * Math.sin(Math.PI / 16), 1.0)).toBeNull()
  })

  it('缓坡接管（g≈0.98 ∈ [0.6,1) 趾盒冠量级）——阈 0.6 的存在意义', () => {
    // 缓锥 s=0.5：行 0..10 半径 6−0.5r；d0=3.2 交叉带 [5,6]（行 5 环内
    // 3.5c≈3.43、行 6 环外 3c≈2.94），g = c ≈ 0.98 ≥ 0.6 → 支撑接管
    const slab = mkCone(Array.from({ length: 11 }, (_, r) => 6 - 0.5 * r))
    const gs = c
    const dA = 3.5 * c - d0, dB = d0 - 3 * c
    const y = topSupportY(slab, qx, qz, 3.0)!
    expect(y).toBeCloseTo(
      (5 + dA / (dA + dB)) * 0.5 + CORE_SKIN * (gs / Math.sqrt(1 + gs * gs)), 6)
  })

  it('陡坡（g≈0.49 < 阈 0.6）→ null 交水平推出，墙面行为零改动', () => {
    // 更缓锥 s=0.25：行 0..14 半径 6−0.25r；g = 0.5c ≈ 0.49
    const slab = mkCone(Array.from({ length: 15 }, (_, r) => 6 - 0.25 * r))
    expect(topSupportY(slab, qx, qz, 6.0)).toBeNull()
  })

  it('环外无含行 → null；表顶行界外 → null', () => {
    expect(topSupportY(cone, 8, 0, 1.0)).toBeNull()   // 远离锥体
    expect(topSupportY(cone, qx, qz, 9.6)).toBeNull() // fl = rows−1 上界
    expect(topSupportY(cone, qx, qz, -0.1)).toBeNull() // 表底下界
  })
})


// ---- 脚区幕帘摆位（2026-09-20 长裤盖脚，assemble step 4.5 消费）----
// 合成双脚场：行 0..7（y 0..3.5）双脚方环（L x∈[−9,−3]、R x∈[3,9]、
// z∈[0,8]，趾尖前伸 +z），踝上无环。腿轴 rAt≡2、cAt≡6、ankleY=4 →
// rTube = 2+skin+gap ≈ 4.18、cx = ±6、off = skin+gap ≈ 2.18。前方 bin：
// 踝环竖垂 → 触趾面（t = 8/cos(π/96)+off ≈ 10.18）后贴面平走 → 落地
// （本例踝高 4 恰铺满）→ 沿地外摊；后方 bin 无触面 = 筒半径全程竖直垂
// + 落地外摊。数值全部由几何常数现场推导（阈独立于实现）
describe('buildFootCurtain/curtainAt（脚区幕帘行走表）', () => {
  const rect = (x0: number, z0: number, x1: number, z1: number): SliceRing => {
    const pts = new Float64Array([x0, z0, x1, z0, x1, z1, x0, z1])
    return {
      pts,
      cx: (x0 + x1) / 2, cz: (z0 + z1) / 2,
      r: Math.hypot((x1 - x0) / 2, (z1 - z0) / 2),
    }
  }
  const mkFootField = (): BodyField => {
    const slices: SliceRing[][] = []
    for (let r = 0; r < 21; r++) {
      slices.push(r <= 7 ? [rect(-9, 0, -3, 8), rect(3, 0, 9, 8)] : [])
    }
    return new BodyField(new Float32Array(21 * 8), 21, 0.5, 8, slices, 0)
  }
  const axis: LegAxis = { rAt: () => 2, cAt: () => 6, forkY: 8, ankleY: 4 }
  const off = CORE_SKIN + HANG_PRIOR.garmentGap
  const rTube = 2 + off
  const thF = ((0 + 0.5) / 96) * 2 * Math.PI      // 前方 bin 0 中心角
  const thB = ((48 + 0.5) / 96) * 2 * Math.PI     // 后方 bin 48 中心角
  const tToe = 8 / Math.cos(thF) + off            // 趾面前缘径距
  const sBend = Math.hypot(0.5, tToe - rTube)     // 踝行→首触面行弧长
  const [curL, curR] = buildFootCurtain(mkFootField(), axis, 0)

  it('前方 bin：竖垂 → 触趾面折线外推 → 贴面平走（s 逐段插值）', () => {
    expect(curL.cx).toBeCloseTo(-6, 10)
    const at0 = curtainAt(curL, thF, 0)
    expect(at0.h).toBeCloseTo(4, 3)
    expect(at0.t).toBeCloseTo(rTube, 3)
    const f = 3 / sBend
    const mid = curtainAt(curL, thF, 3)
    expect(mid.h).toBeCloseTo(4 - 0.5 * f, 3)
    expect(mid.t).toBeCloseTo(rTube + (tToe - rTube) * f, 3)
    const flat = curtainAt(curL, thF, sBend + 1.2)
    expect(flat.h).toBeCloseTo(3.5 - 1.2, 3)
    expect(flat.t).toBeCloseTo(tToe, 3)
  })

  it('前方 bin：预算超表尾钳末值（落地后沿地外摊段）', () => {
    // 踝高 4 全程竖+贴面恰铺到地（s≈9.5）；外摊 40 行 ×0.5 → 末值
    const end = curtainAt(curL, thF, 100)
    expect(end.h).toBeCloseTo(0, 3)
    expect(end.t).toBeCloseTo(tToe + 20, 3)
  })

  it('后方 bin：无触面 = 筒半径全程竖直垂 + 落地沿地外摊', () => {
    const hang = curtainAt(curL, thB, 2)
    expect(hang.h).toBeCloseTo(2, 3)
    expect(hang.t).toBeCloseTo(rTube, 3)
    // s=4 到地（h 4→0 竖垂）；此后每 +1 弧长沿地外摊 +1
    const floor = curtainAt(curL, thB, 4.7)
    expect(floor.h).toBeCloseTo(0, 3)
    expect(floor.t).toBeCloseTo(rTube + 0.7, 3)
  })

  it('环归属按质心同侧：右幕帘只吃右脚（镜像同数值）、左脚不串台', () => {
    expect(curR.cx).toBeCloseTo(6, 10)
    const mid = curtainAt(curR, thF, 3)
    expect(mid.h).toBeCloseTo(4 - 0.5 * (3 / sBend), 3)
    expect(mid.t).toBeCloseTo(rTube + (tToe - rTube) * (3 / sBend), 3)
    // 后方 bin 照旧无触面竖垂（右脚不前伸到左幕帘 bin）
    const back = curtainAt(curR, thB, 2)
    expect(back.t).toBeCloseTo(rTube, 3)
  })
})
