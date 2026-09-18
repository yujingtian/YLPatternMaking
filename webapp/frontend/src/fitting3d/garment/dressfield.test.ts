// 穿台几何原语金标（2026-09-18）：placement 穿台三原语（shiftPositionsY /
// nearestRingBoundary / buildLegAxisFromRings）的合成场单元验证——真产物
// 集成（dress.test.ts）前的层间把门。全部手搓可精确断言的几何：
// 正多边形环（质心=圆心）、合成 BodyField（只喂 slices——腿轴/边界查询
// 不读场表）。演进口径见 settle.ts 头注与 .doc/python工程设计.md §10.11。
import { describe, expect, it } from 'vitest'
import {
  BodyField, buildLegAxisFromRings, nearestRingBoundary, pointInRings,
  shiftPositionsY, type SliceRing,
} from './placement'

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
