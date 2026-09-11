// base.bin + targets.json 加载：模块级 promise 缓存（一次 fetch，跨重建复用），
// 失败不缓存（下次重建可重试）。渲染/碰撞/标定全部消费同一份 asset。
import type { BodyMeshAsset, BodyMeshMeta, TargetName } from './types'

let cached: Promise<BodyMeshAsset> | null = null

export function loadBodyMesh(): Promise<BodyMeshAsset> {
  if (!cached) {
    cached = doLoad()
    cached.catch(() => { cached = null })
  }
  return cached
}

async function doLoad(): Promise<BodyMeshAsset> {
  // targets.json 先行 no-cache（强再验证）拿 baseSha256，再以 ?v=<sha8> 拉
  // base.bin——vendor 重跑后指纹变 → URL 变 → 浏览器缓存自然击穿；无指纹
  // （旧 meta）回落无参路径。bin 直取 HTTP 缓存，meta 仅几 KB。
  const jsonRes = await fetch('bodymesh/targets.json', { cache: 'no-cache' })
  if (!jsonRes.ok) {
    throw new Error(`bodymesh 数据拉取失败 json=${jsonRes.status}`)
  }
  const meta = JSON.parse(await jsonRes.text()) as BodyMeshMeta
  const v = (meta as { baseSha256?: string }).baseSha256
  const binRes = await fetch(v ? `bodymesh/base.bin?v=${v}` : 'bodymesh/base.bin')
  if (!binRes.ok) {
    throw new Error(`bodymesh 数据拉取失败 bin=${binRes.status}`)
  }
  const buf = await binRes.arrayBuffer()
  return { ...parseBin(buf), meta }
}

// 布局见 types.ts 头注；DataView 逐字段读（结构小，无需整块偏移计算）。
// 导出供 integration 测试（node 环境无 fetch，fs 读字节后走同一解析）
export function parseBin(buf: ArrayBuffer): {
  positions: Float32Array; indices: Uint32Array; targets: BodyMeshAsset['targets']
} {
  const dv = new DataView(buf)
  const V = dv.getUint32(0, true)
  const F = dv.getUint32(4, true)
  const T = dv.getUint32(8, true)
  let off = 12
  const positions = new Float32Array(3 * V)
  for (let i = 0; i < 3 * V; i++) {
    positions[i] = dv.getFloat32(off, true); off += 4
  }
  const indices = new Uint32Array(3 * F)
  for (let i = 0; i < 3 * F; i++) {
    indices[i] = dv.getUint32(off, true); off += 4
  }
  const targets: BodyMeshAsset['targets'] = []
  for (let t = 0; t < T; t++) {
    const n = dv.getUint32(off, true); off += 4
    const idx = new Uint32Array(n)
    for (let i = 0; i < n; i++) {
      idx[i] = dv.getUint32(off, true); off += 4
    }
    const d = new Float32Array(3 * n)
    for (let i = 0; i < 3 * n; i++) {
      d[i] = dv.getFloat32(off, true); off += 4
    }
    const name = nameOfSlot(t)
    targets.push({ name, idx, d })
  }
  if (off !== buf.byteLength) {
    throw new Error(`base.bin 尾部残留 ${buf.byteLength - off} 字节（布局漂移？）`)
  }
  return { positions, indices, targets }
}

// base.bin 不带 target 名（顺序即契约）：vendor MEASURE_TARGETS 固定序
// waist/hips/thigh/knee × (incr, decr)——与 targets.json targets 序一致性
// 由 buildMeshMannequin 的计数断言把守
const SLOT_ORDER: TargetName[] = [
  'waist+', 'waist-', 'hips+', 'hips-',
  'thigh+', 'thigh-', 'knee+', 'knee-',
]
function nameOfSlot(t: number): TargetName {
  const name = SLOT_ORDER[t]
  if (!name) throw new Error(`base.bin target 槽位 ${t} 超出已知序`)
  return name
}
