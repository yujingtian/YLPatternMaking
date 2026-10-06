// sheetMeasure 纯逻辑金标（vitest node env，风格对齐 NestPreview.test.ts）：
// 仿射逆换算（Y 翻转符号最易错）/ 吸附半径语义 / 一次一条状态机 / 距离读数。
// overlay 视图（吸附环/橡皮筋/气泡观感）由手工 + Playwright 冒烟覆盖。
//
// fixture 手工演算（镜像 svg.py 口径：SCALE=10、MARGIN=30）：
//   版面含两点 (0,0)cm、(20,10)cm → transform = { scale: 10, ox: 30, top: 130 }
//   （ox = 30 − 0×10 = 30；top = 30 + 10×10 = 130）
//   circle 坐标：(0,0)cm → (30, 130)；(20,10)cm → (230, 130−100=30)

import { describe, expect, it } from 'vitest'
import {
  CLICK_SLOP_PX, SNAP_PX, cmToUser, distCm, fmtCm, nextMeasureState,
  pickNearest, userToCm,
} from './sheetMeasure'
import type { MeasureEnd, MeasurePoint } from './sheetMeasure'
import type { Transform } from '../types'

const T: Transform = { scale: 10, ox: 30, top: 130 }

const P0: MeasurePoint = { name: 'front.o', label: '原点', ux: 30, uy: 130 }
const P1: MeasurePoint = { name: 'front.p', label: '靶点', ux: 230, uy: 30 }

function end(p: MeasurePoint | null, x: number, y: number): MeasureEnd {
  return { point: p, cm: { x, y } }
}

describe('userToCm / cmToUser（Y 翻转逆仿射）', () => {
  it('cm→user：sx=x*10+30、sy=top−y*10', () => {
    expect(cmToUser(T, 20, 10)).toEqual({ x: 230, y: 30 })
    expect(cmToUser(T, 0, 0)).toEqual({ x: 30, y: 130 })
  })

  it('user→cm：(ux−30)/10、(top−uy)/10（翻转符号锚死）', () => {
    expect(userToCm(T, 230, 30)).toEqual({ x: 20, y: 10 })
    expect(userToCm(T, 30, 130)).toEqual({ x: 0, y: 0 })
  })

  it('互逆：cmToUser ∘ userToCm = 恒等', () => {
    const u = userToCm(T, 230, 30)
    expect(cmToUser(T, u.x, u.y)).toEqual({ x: 230, y: 30 })
  })
})

describe('distCm / fmtCm', () => {
  it('(0,0)~(20,10)cm 距离 = √500 ≈ 22.360679…', () => {
    expect(distCm(end(null, 0, 0), end(null, 20, 10))).toBe(Math.sqrt(500))
  })

  it('user 空间 hypot/scale 与 cm 空间 hypot 互证（双口径同源）', () => {
    const byUser = Math.hypot(230 - 30, 30 - 130) / T.scale
    expect(byUser).toBe(distCm(end(null, 0, 0), end(null, 20, 10)))
  })

  it('fmtCm 两位小数 + cm 后缀（与拖拽气泡同口径）', () => {
    expect(fmtCm(Math.sqrt(500))).toBe('22.36 cm')
    expect(fmtCm(0)).toBe('0.00 cm')
    expect(fmtCm(27)).toBe('27.00 cm')
  })
})

describe('pickNearest（user 空间吸附）', () => {
  it('半径内取最近：探针 (232,31) 距 P1=√5≈2.24 < 5', () => {
    expect(pickNearest([P0, P1], 232, 31, 5)).toBe(P1)
  })

  it('半径外返回 null：探针 (229,31) 距 P1=√2≈1.41 ≥ 1', () => {
    expect(pickNearest([P0, P1], 229, 31, 1)).toBeNull()
  })

  it('半径放大到覆盖两倍距离仍取最近者', () => {
    expect(pickNearest([P0, P1], 229, 31, 2)).toBe(P1)
  })

  it('空点集返回 null（show_labels 无关，circle 恒在——防御分支）', () => {
    expect(pickNearest([], 0, 0, 100)).toBeNull()
  })
})

describe('nextMeasureState（一次一条、自动替换）', () => {
  const e1 = end(P0, 0, 0)
  const e2 = end(P1, 20, 10)
  const e3 = end(null, 5, 5)

  it('空 → 记 first', () => {
    expect(nextMeasureState({ first: null, done: null }, e1))
      .toEqual({ first: e1, done: null })
  })

  it('first → done {a,b}', () => {
    expect(nextMeasureState({ first: e1, done: null }, e2))
      .toEqual({ first: null, done: { a: e1, b: e2 } })
  })

  it('done → 清旧成线、新点作 first（第三点开启下一组）', () => {
    expect(nextMeasureState({ first: null, done: { a: e1, b: e2 } }, e3))
      .toEqual({ first: e3, done: null })
  })
})

describe('常量（吸附/死区半径口径）', () => {
  it('SNAP_PX=12、CLICK_SLOP_PX=4（屏幕像素恒定，user 半径 = SNAP_PX/k）', () => {
    expect(SNAP_PX).toBe(12)
    expect(CLICK_SLOP_PX).toBe(4)
  })
})
