// bodymesh base.bin 链路最小金标（2026-09-13 下半身切割人台）：
// parseBaseBin 布局契约（含尾部残留/索引越界防爆）+ morphPositions 稀疏
// 叠加/恒等 + 真产物冒烟（public/bodymesh 现货 base.bin+targets.json）。
// 布局与 scripts/vendor_makehuman.py 头注、tests/test_vendor_bodymesh.py
// ::read_bin 三处同步；raw.obj 全身原生链（native.ts）同日退役，
// 演进史见决策日志 §十一。
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { loadBodyMesh, parseBaseBin } from './bin'
import { morphPositions } from './morph'
import { readGirth } from './slice'
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
      ['ankle+', 'ankle-', 'calf+', 'calf-', 'hips+', 'hips-',
        'knee+', 'knee-', 'thigh+', 'thigh-', 'waist+', 'waist-'])
    expect(Object.keys(a.stations).sort()).toEqual(
      ['ankle', 'calf', 'hips', 'knee', 'thigh', 'waist'])
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
  })
})

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
  }
}
