// bodymesh base.bin 链路最小金标（2026-09-13 下半身切割人台 + 身高 macro 场）：
// parseBaseBin 布局契约（含尾部残留/索引越界防爆）+ morphPositions 稀疏
// 叠加/恒等 + height.ts 预设换算纯函数 + 真产物冒烟（public/bodymesh 现货
// base.bin+targets.json）。布局与 scripts/vendor_makehuman.py 头注、
// tests/test_vendor_bodymesh.py ::read_bin 三处同步；raw.obj 全身原生链
// （native.ts）同日退役，演进史见决策日志 §十一。
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { loadBodyMesh, parseBaseBin } from './bin'
import { morphPositions } from './morph'
import { readGirth } from './slice'
import { heightCm, stationFactor, weightFor } from './height'
import type { HeightInfo } from './height'
import type { MeshTarget } from './types'

const HERE = import.meta.dirname   // src/fitting3d/bodymesh

// 手搓最小 bin：V=3（脚底 y=0 顶点在内）、F=1、T=2（waist+ 动 v1；waist- 动 v2）
function tinyBin(tail = 0): ArrayBuffer {
  const V = 3, F = 1, T = 2
  const bytes: number[] = []
  const u32 = (x: number) => {
    bytes.push(x & 0xff, (x >>> 8) & 0xff, (x >>> 16) & 0xff, x >>> 24)
  }
  const f32 = (x: number) => {
    bytes.push(...new Uint8Array(new Float32Array([x]).buffer))
  }
  u32(V); u32(F); u32(T)
  for (const p of [0, 0, 0, 10, 0, 0, 0, 20, 0]) f32(p)     // 顶点
  u32(0); u32(1); u32(2)                                     // 一个三角形
  u32(1); u32(1); f32(1); f32(2); f32(3)                     // 场A：v1 +(1,2,3)
  u32(1); u32(2); f32(-1); f32(0); f32(0.5)                  // 场B：v2 +(-1,0,.5)
  for (let i = 0; i < tail; i++) bytes.push(0)
  return new Uint8Array(bytes).buffer
}

function tinyAsset(): { positions: Float32Array; targets: MeshTarget[] } {
  const { positions, fields } = parseBaseBin(tinyBin())
  return {
    positions,
    targets: fields.map((f, k) => ({ ...f, name: (k === 0 ? 'waist+' : 'waist-') as MeshTarget['name'] })),
  }
}

describe('bodymesh base.bin 链路', () => {
  it('parseBaseBin：布局契约（V/F/T、顶点/三角/场槽位字节序）', () => {
    const { positions, indices, fields } = parseBaseBin(tinyBin())
    expect(Array.from(positions)).toEqual([0, 0, 0, 10, 0, 0, 0, 20, 0])
    expect(Array.from(indices)).toEqual([0, 1, 2])
    expect(fields.length).toBe(2)
    expect(Array.from(fields[0].idx)).toEqual([1])
    expect(Array.from(fields[0].d)).toEqual([1, 2, 3])
  })

  it('parseBaseBin：尾部残留 / 索引越界必须炸（防 vendor/TS 布局失配静默）', () => {
    expect(() => parseBaseBin(tinyBin(4))).toThrow(/残留/)
    const bad = new DataView(tinyBin())
    bad.setUint32(12 + 12 * 3 + 4, 99, true)   // 三角顶点 0 → 99（≥V=3）
    expect(() => parseBaseBin(bad.buffer)).toThrow(/越界/)
  })

  it('morph：w=0 逐位恒等；稀疏叠加精确；未列入顶点不动', () => {
    const a = tinyAsset()
    const out0 = morphPositions(a, {})
    expect(out0).toEqual(a.positions)                 // 逐位恒等
    const out = morphPositions(a, { 'waist+': 0.5 })
    expect(out[3]).toBeCloseTo(10.5, 6)
    expect(out[4]).toBeCloseTo(1, 6)
    expect(out[5]).toBeCloseTo(1.5, 6)
    expect(out[6]).toBe(0)                            // v2 不动
    expect(a.positions[3]).toBe(10)                   // 原数组不被改写
  })

  it('真产物冒烟：base.bin+targets.json 对账、六站齐全、官方场方向响应', async () => {
    const a = await loadBodyMeshFromDisk()
    expect(a.positions.length).toBeGreaterThan(3 * 4000)
    expect(a.targets.map((t) => t.name).sort()).toEqual(
      ['ankle+', 'ankle-', 'calf+', 'calf-', 'height+', 'height-', 'hips+', 'hips-',
        'knee+', 'knee-', 'thigh+', 'thigh-', 'waist+', 'waist-'])
    expect(Object.keys(a.stations).sort()).toEqual(
      ['ankle', 'calf', 'hips', 'knee', 'thigh', 'waist'])
    // 身高场实测契约（预设换算基准）：基高域 + ΔH 双向 + 覆盖全网格
    // （切缝/封盖合成顶点已按边端点插值补增量——顶环随身体同步升降）
    const h = a.heightInfo
    expect(h.baseCm).toBeGreaterThan(160)
    expect(h.baseCm).toBeLessThan(180)
    expect(h.plusCm).toBeGreaterThan(1)
    expect(h.minusCm).toBeLessThan(-1)
    for (const t of a.targets) {
      if (t.name === 'height+' || t.name === 'height-') {
        expect(t.idx.length).toBe(a.positions.length / 3)
      }
    }
    const g0 = a.stations.waist && readGirth(a.positions, a.indices, a.stations.waist.y, 'body')
    expect(g0).toBeGreaterThan(55)
    const pos1 = morphPositions(a, { 'waist+': 1 })
    expect(pos1.length).toBe(a.positions.length)
    const g1 = a.stations.waist && readGirth(pos1, a.indices, a.stations.waist.y, 'body')
    expect(g1! - g0!).toBeGreaterThan(2)   // 官方 waist+ 自家站方向响应
    const pc = a.stations.calf && readGirth(a.positions, a.indices, a.stations.calf.y, 'leg')
    const posc = morphPositions(a, { 'calf+': 1 })
    const gc = a.stations.calf && readGirth(posc, a.indices, a.stations.calf.y, 'leg')
    expect(pc).toBeGreaterThan(25)
    expect(gc! - pc!).toBeGreaterThan(2)   // 官方 calf+ 自家站方向响应
    // 身高场方向（切割网格）：height− 压低 / height+ 拉高 / 脚底锚地
    const top0 = maxy(a.positions)
    const posm = morphPositions(a, { 'height-': 1 })
    expect(maxy(posm) - top0).toBeLessThan(-2)
    expect(miny(posm)).toBeGreaterThan(-1)
    const posp = morphPositions(a, { 'height+': 1 })
    expect(maxy(posp) - top0).toBeGreaterThan(2)
    expect(miny(posp)).toBeGreaterThan(-1)
  })
})

describe('height.ts 预设换算纯函数（测量驱动、约定无关）', () => {
  // 2026-09-13 vendor 实测锚（meta.height）：base 167.36 / +72.02 / −36.69
  const info: HeightInfo = { baseCm: 167.36, plusCm: 72.02, minusCm: -36.69 }

  it('heightCm：w=0 恒等；正负两支独立（非反对称）', () => {
    expect(heightCm(info, 0)).toBeCloseTo(167.36, 9)
    expect(heightCm(info, 1)).toBeCloseTo(239.38, 1)
    expect(heightCm(info, -1)).toBeCloseTo(130.67, 1)
  })

  it('weightFor ↔ heightCm 换算互逆；钳制进 [−1,1]', () => {
    for (const cm of [155, 160, 165, 170, 150, 185, 162.3]) {
      const w = weightFor(info, cm)
      expect(w).toBeGreaterThanOrEqual(-1)
      expect(w).toBeLessThanOrEqual(1)
      expect(heightCm(info, w)).toBeCloseTo(cm, 6)
    }
    // 出域钳制（官方 macro 域 ±1 = 130.7~239.4cm）
    expect(weightFor(info, 250)).toBe(1)
    expect(weightFor(info, 100)).toBe(-1)
  })

  it('stationFactor：w=0 恒等 1；预设档因子（155→0.926 / 170→1.016）', () => {
    expect(stationFactor(info, 0)).toBeCloseTo(1, 9)
    expect(stationFactor(info, weightFor(info, 155))).toBeCloseTo(155 / 167.36, 4)
    expect(stationFactor(info, weightFor(info, 170))).toBeCloseTo(170 / 167.36, 4)
  })
})

function maxy(pos: Float32Array): number {
  let m = -Infinity
  for (let i = 1; i < pos.length; i += 3) m = Math.max(m, pos[i])
  return m
}

function miny(pos: Float32Array): number {
  let m = Infinity
  for (let i = 1; i < pos.length; i += 3) m = Math.min(m, pos[i])
  return m
}

// doLoad 走 fetch（浏览器）；冒烟从盘上等价读
async function loadBodyMeshFromDisk() {
  const meta = JSON.parse(readFileSync(`${HERE}/../../../public/bodymesh/targets.json`, 'utf8'))
  const { positions, indices, fields } = parseBaseBin(
    readFileSync(`${HERE}/../../../public/bodymesh/base.bin`).buffer.slice(0))
  const stations: Record<string, { y: number; per: 'body' | 'leg' }> = {}
  for (const s of meta.stations) stations[s.name] = { y: s.y, per: s.per }
  return {
    positions, indices,
    targets: fields.map((f, k) => ({ ...f, name: meta.targets[k].name })),
    stations: stations as Awaited<ReturnType<typeof loadBodyMesh>>['stations'],
    height: meta.cut.planeY as number,
    heightInfo: {
      baseCm: meta.height.baseCm as number,
      plusCm: meta.height.plusCmAtW1 as number,
      minusCm: meta.height.minusCmAtW1 as number,
    },
  }
}
