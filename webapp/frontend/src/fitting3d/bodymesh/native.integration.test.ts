// 全身原生链真数据冒烟（2026-09-12）：对 public/bodymesh/raw.obj（sha256
// 与 vendor PROVENANCE 一致）+ 官方 measure target 跑 detectStations/
// readGirth/parseTargetText，把守三件 heuristic 不被网格/数据演进静默
// 打破：① g body 面可解析且引用顶点在位；② 站高探测出 4 站且高度在
// 解剖合理区间；③ target 索引域不越全身顶点数（错位即炸）。
// doLoad 用 fetch（浏览器），此处等价复刻其文件解析段从盘上读。
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { detectStations, parseTargetText, readGirth } from './native'

const HERE = import.meta.dirname   // src/fitting3d/bodymesh

function loadRaw(): { positions: Float32Array; indices: Uint32Array; height: number } {
  const text = readFileSync(`${HERE}/../../../public/bodymesh/raw.obj`, 'utf8')
  const pos: number[] = []
  const tris: number[] = []
  let cur = ''
  for (const ln of text.split('\n')) {
    if (ln.startsWith('g ')) cur = ln.slice(2).trim()
    else if (ln.startsWith('v ')) {
      const p = ln.trim().split(/\s+/)
      pos.push(+p[1] * 10, +p[2] * 10, +p[3] * 10)
    } else if (ln.startsWith('f ') && cur === 'body') {
      const p = ln.trim().split(/\s+/).slice(1).map((t) => +t.split('/')[0])
      for (let k = 1; k < p.length - 1; k++) tris.push(p[0] - 1, p[k] - 1, p[k + 1] - 1)
    }
  }
  const positions = new Float32Array(pos)
  const indices = new Uint32Array(tris)
  let yMin = Infinity, yMax = -Infinity
  for (let i = 0; i < indices.length; i++) {
    const y = positions[3 * indices[i] + 1]
    if (y < yMin) yMin = y
    if (y > yMax) yMax = y
  }
  for (let i = 1; i < positions.length; i += 3) positions[i] -= yMin
  return { positions, indices, height: yMax - yMin }
}

const range = (v: number | null, lo: number, hi: number) =>
  v !== null && v > lo && v < hi

describe('native 全身链真数据冒烟', () => {
  const { positions, indices, height } = loadRaw()
  const stations = detectStations(positions, indices)
  const V = positions.length / 3

  it('g body 面可解析、身高量级合理（成年女性 150~200cm）', () => {
    expect(indices.length).toBeGreaterThan(3 * 10000)   // body 组数万面级
    let iMax = 0
    for (let i = 0; i < indices.length; i++) iMax = Math.max(iMax, indices[i])
    expect(iMax).toBeLessThan(V)
    expect(height).toBeGreaterThan(150)
    expect(height).toBeLessThan(200)
  })

  it('站高探测：4 站齐全且序为 膝 < 大腿 < 臀 < 腰', () => {
    expect(Object.keys(stations).sort()).toEqual(['hips', 'knee', 'thigh', 'waist'])
    const y = (k: keyof typeof stations) => stations[k]!.y
    expect(y('knee')).toBeGreaterThan(30)
    expect(y('knee')).toBeLessThan(y('thigh')!)
    expect(y('thigh')).toBeLessThan(y('hips')!)
    expect(y('hips')).toBeLessThan(y('waist')!)
    expect(y('waist')).toBeLessThan(height * 0.7)   // 腰在躯干、非头顶区
  })

  it('基网格四站围度在解剖合理区间（cm）', () => {
    const g = (k: keyof typeof stations) =>
      readGirth(positions, indices, stations[k]!.y, stations[k]!.per)
    expect(range(g('waist'), 55, 110)).toBe(true)
    expect(range(g('hips'), 75, 130)).toBe(true)
    expect(range(g('thigh'), 35, 80)).toBe(true)
    expect(range(g('knee'), 25, 55)).toBe(true)
  })

  it('官方 target 索引域不越全身顶点数、增量非零', () => {
    const t = parseTargetText(readFileSync(
      `${HERE}/../../../public/bodymesh/targets/measure/measure-waist-circ-incr.target`, 'utf8'))
    expect(t.idx.length).toBeGreaterThan(100)          // 稀疏但成规模
    expect(Math.max(...t.idx)).toBeLessThan(V)
    expect(Math.hypot(...t.d)).toBeGreaterThan(0)
  })
})
