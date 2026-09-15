// base.bin 下半身资产（纯切割链 2026-09-13 定型）：scripts/vendor_makehuman.py
// 产物，站直姿势 LBS + 切割（粗裁 0.73H 去臂 + 精裁腰+15 + 封盖水密）。
// 布局（little-endian）：<III> V F T；V×<3f> 顶点 cm（Y-up、脚底=0、+Z 前）；
// F×<3I> 三角 0-based；每场：<I> n、n×<I> idx、3n×<f> d（cm）。官方 12 个
// measure 场（腰/臀/大腿/膝/小腿/踝）+ 身高 macro ±（共 14 场）已按裁切后
// 紧凑索引重映射（vmap→keep_map→remap；切缝/封盖合成顶点按边端点插值补增量），
// 增量即最终 cm 值。Python 金标 tests/test_vendor_bodymesh.py 同布局把守。
// targets.json（schema 2）附带：stations（vendor 地标检测值——比启发式站高
// 准）、height（身高场切割前实测，预设体重量的换算基准）与 baseSha256 内容
// 指纹——base.bin 以 ?v=<sha8> 拉取，vendor 重跑后指纹必变即击穿浏览器缓存
// （2026-09-12「改了没变化」事故教训）。
import type { MeshTarget, TargetName } from './types'
import type { HeightInfo } from './height'

export interface BodyMeshAsset {
  positions: Float32Array   // cm，Y-up，脚底 y=0
  indices: Uint32Array      // 水密切割网格三角（0-based 紧凑索引）
  targets: MeshTarget[]     // 14 个官方场：12 measure + 身高 macro ±（cm，索引已对齐本网格）
  stations: Partial<Record<'waist' | 'hips' | 'thigh' | 'knee' | 'calf' | 'ankle',
    { y: number; per: 'body' | 'leg' }>>   // vendor 地标站（围度读数用）
  // vendor 地标高度 cm（targets.json landmarkHeights 原样透传；含 stations
  // 没有的 crotch——二期试穿 y-warp 锚用，2026-09-13 additive）
  landmarks: Partial<Record<'sole' | 'crotch' | 'waist' | 'hip' | 'knee'
    | 'calf' | 'ankle', number>>
  height: number            // 裁切面高（腰+15，取景定标）
  heightInfo: HeightInfo    // 身高场实测（预设体重量的换算基准，height.ts）
}

export interface ParsedBin {
  positions: Float32Array
  indices: Uint32Array
  fields: { idx: Uint32Array; d: Float32Array }[]   // 槽位名由 targets.json 提供
}

export function parseBaseBin(buf: ArrayBuffer): ParsedBin {
  const dv = new DataView(buf)
  let off = 0
  const u32 = () => { const x = dv.getUint32(off, true); off += 4; return x }
  const f32 = () => { const x = dv.getFloat32(off, true); off += 4; return x }
  const V = u32(), F = u32(), T = u32()
  if (V < 3 || F < 1 || T < 1) throw new Error('base.bin 头部非法（V/F/T 过小）')
  const positions = new Float32Array(3 * V)
  for (let i = 0; i < positions.length; i++) positions[i] = f32()
  const indices = new Uint32Array(3 * F)
  for (let i = 0; i < indices.length; i++) indices[i] = u32()
  let iMax = 0
  for (let i = 0; i < indices.length; i++) iMax = Math.max(iMax, indices[i])
  if (iMax >= V) throw new Error(`base.bin 索引越界（max ${iMax} ≥ V ${V}）——布局漂移`)
  const fields: ParsedBin['fields'] = []
  for (let t = 0; t < T; t++) {
    const n = u32()
    if (n === 0) throw new Error(`base.bin 第 ${t} 场空槽`)
    const idx = new Uint32Array(n)
    for (let i = 0; i < n; i++) {
      idx[i] = u32()
      if (idx[i] >= V) throw new Error(`base.bin 场索引越界（场 ${t}）——布局漂移`)
    }
    const d = new Float32Array(3 * n)
    for (let i = 0; i < d.length; i++) d[i] = f32()
    fields.push({ idx, d })
  }
  if (off !== buf.byteLength) {
    throw new Error(`base.bin 尾部残留 ${buf.byteLength - off} 字节——布局漂移`)
  }
  return { positions, indices, fields }
}

let cached: Promise<BodyMeshAsset> | null = null

export function loadBodyMesh(): Promise<BodyMeshAsset> {
  if (!cached) {
    cached = doLoad()
    cached.catch(() => { cached = null })
  }
  return cached
}

async function doLoad(): Promise<BodyMeshAsset> {
  // targets.json 是缓存击穿链的头（baseSha256 在它里面）：裸 fetch 会被浏览器
  // 启发式缓存钉死在旧指纹、指向旧 base.bin——vendor 重跑后整条链原地转圈
  // （2026-09-13 实发）。no-cache = 每次带 ETag 再验证，正常 304 空响应。
  const mj = await fetch('bodymesh/targets.json', { cache: 'no-cache' })
  if (!mj.ok) throw new Error(`targets.json 拉取失败 ${mj.status}`)
  const meta = await mj.json()
  const r = await fetch(`bodymesh/base.bin?v=${meta.baseSha256}`)
  if (!r.ok) throw new Error(`base.bin 拉取失败 ${r.status}`)
  const { positions, indices, fields } = parseBaseBin(await r.arrayBuffer())
  // 契约对账：bin 与 targets.json 三处同步（vendor/TS/Python 金标）
  if (positions.length !== 3 * meta.vertexCount
      || indices.length !== 3 * meta.triangleCount
      || fields.length !== meta.targets.length) {
    throw new Error('base.bin 与 targets.json 计数失配——vendor 产物未成对更新')
  }
  const names = meta.targets.map((t: { name: string }) => t.name)
  const targets: MeshTarget[] = fields.map((f, k) => ({ ...f, name: names[k] as TargetName }))
  // 身高场实测（vendor 切割前全身网格 w=±1 响应）：预设体重的换算基准。
  // 缺失即炸——bin/JSON 成对更新契约（height 链版本之前的旧产物不得静默可用）。
  const mh = meta.height as
    { baseCm: number; plusCmAtW1: number; minusCmAtW1: number } | undefined
  if (!mh || [mh.baseCm, mh.plusCmAtW1, mh.minusCmAtW1].some((v) => typeof v !== 'number')) {
    throw new Error('targets.json 缺 meta.height——vendor 产物未成对更新（重跑 scripts/vendor_makehuman.py）')
  }
  const heightInfo = { baseCm: mh.baseCm, plusCm: mh.plusCmAtW1, minusCm: mh.minusCmAtW1 }
  const stations: BodyMeshAsset['stations'] = {}
  const stationNames = ['waist', 'hips', 'thigh', 'knee', 'calf', 'ankle'] as const
  for (const s of meta.stations as { name: string; y: number; per: string }[]) {
    if ((stationNames as readonly string[]).includes(s.name)) {
      stations[s.name as (typeof stationNames)[number]] = { y: s.y, per: s.per as 'body' | 'leg' }
    }
  }
  const lmRaw = (meta.landmarkHeights ?? {}) as Record<string, number>
  const landmarks: BodyMeshAsset['landmarks'] = {}
  const lmKeys = ['sole', 'crotch', 'waist', 'hip', 'knee', 'calf', 'ankle'] as const
  for (const k of lmKeys) {
    if (typeof lmRaw[k] === 'number') landmarks[k] = lmRaw[k]
  }
  return {
    positions, indices, targets, stations, landmarks,
    height: meta.cut.planeY, heightInfo,
  }
}
