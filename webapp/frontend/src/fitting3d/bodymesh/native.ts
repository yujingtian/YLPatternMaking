// MakeHuman 原生全身人台（2026-09-12 用户口径：全身 + 官方 targets 调节）。
// 数据 = vendor/makehuman 的原样件：base.obj（= public/bodymesh/raw.obj，
// sha256 与 PROVENANCE 一致；本身已是 universal female young average，
// macro 为 0 增量恒等）+ 8 个官方 measure-*-circ target（文本格式
// `idx dx dy dz`，dm 单位、0-based、索引即 base.obj 顶点号——与全身网格
// 天然对齐，无需任何索引重映射）。
// 与裁切链（base.bin/targets.json + vendor 派生场）的分野：此处是**裸原生
// 体验**——原生 target 的作者化行为（含其固有缺陷，如 thigh 场膝上死区）
// 原样呈现；派生场修复只存在于退役的裁切链，演进史见决策日志 §十一。
import { sliceLoops } from './slice'
import type { MeshTarget, TargetName } from './types'

export interface NativeBody {
  positions: Float32Array   // cm，Y-up，脚底 y=0（body 组脚底；helper 顶点未紧缩保留原索引）
  indices: Uint32Array      // g body 四边面扇形三角化（0-based 原始索引）
  targets: MeshTarget[]     // 8 个官方 measure 场（cm）
  stations: Partial<Record<'waist' | 'hips' | 'thigh' | 'knee',
    { y: number; per: 'body' | 'leg' }>>   // 粗探测站（读数近似）
  height: number            // 身高 cm（取景定标）
}

const MEASURE_FILES: Record<TargetName, string> = {
  'waist+': 'measure-waist-circ-incr.target',
  'waist-': 'measure-waist-circ-decr.target',
  'hips+': 'measure-hips-circ-incr.target',
  'hips-': 'measure-hips-circ-decr.target',
  'thigh+': 'measure-thigh-circ-incr.target',
  'thigh-': 'measure-thigh-circ-decr.target',
  'knee+': 'measure-knee-circ-incr.target',
  'knee-': 'measure-knee-circ-decr.target',
}

// 文本 target：`#` 注释 + `idx dx dy dz`（dm）。dm→cm ×10 与顶点口径一致。
export function parseTargetText(text: string): { idx: number[]; d: number[] } {
  const idx: number[] = []
  const d: number[] = []
  for (const ln of text.split('\n')) {
    if (!ln || ln.startsWith('#')) continue
    const p = ln.trim().split(/\s+/)
    if (p.length !== 4) continue
    idx.push(+p[0])
    d.push(+p[1] * 10, +p[2] * 10, +p[3] * 10)
  }
  return { idx, d }
}

let cached: Promise<NativeBody> | null = null

export function loadNativeBody(): Promise<NativeBody> {
  if (!cached) {
    cached = doLoad()
    cached.catch(() => { cached = null })
  }
  return cached
}

async function doLoad(): Promise<NativeBody> {
  const res = await fetch('bodymesh/raw.obj')
  if (!res.ok) throw new Error(`raw.obj 拉取失败 ${res.status}`)
  const text = await res.text()
  // 全部 v 行平铺保留原始索引（target 直接按 base.obj 顶点号写，不紧缩）；
  // 面只取 g body（helper-*/joint-* 辅助几何丢弃，与 vendor parse_obj 同口径）
  const pos: number[] = []
  const tris: number[] = []
  let cur = ''
  for (const ln of text.split('\n')) {
    if (ln.startsWith('g ')) {
      cur = ln.slice(2).trim()
    } else if (ln.startsWith('v ')) {
      const p = ln.trim().split(/\s+/)
      pos.push(+p[1] * 10, +p[2] * 10, +p[3] * 10)   // dm -> cm
    } else if (ln.startsWith('f ') && cur === 'body') {
      const p = ln.trim().split(/\s+/).slice(1).map((t) => +t.split('/')[0])
      for (let k = 1; k < p.length - 1; k++) {
        tris.push(p[0] - 1, p[k] - 1, p[k + 1] - 1)
      }
    }
  }
  const positions = new Float32Array(pos)
  const indices = new Uint32Array(tris)
  // 落地：body 面引用顶点的最小 y 平移到 0（helper 顶点不参与，可能整体
  // 悬空/下探，反正不渲染）；身高同步取 body 顶点
  let yMin = Infinity, yMax = -Infinity
  for (let i = 0; i < indices.length; i++) {
    const y = positions[3 * indices[i] + 1]
    if (y < yMin) yMin = y
    if (y > yMax) yMax = y
  }
  for (let i = 1; i < positions.length; i += 3) positions[i] -= yMin
  // 8 个官方 measure 场并行拉取
  const names = Object.keys(MEASURE_FILES) as TargetName[]
  const fields = await Promise.all(names.map(async (n) => {
    const r = await fetch(`bodymesh/targets/measure/${MEASURE_FILES[n]}`)
    if (!r.ok) throw new Error(`target 拉取失败 ${n} ${r.status}`)
    const { idx, d } = parseTargetText(await r.text())
    return { name: n, idx: new Uint32Array(idx), d: new Float32Array(d) }
  }))
  return {
    positions, indices, targets: fields,
    stations: detectStations(positions, indices),
    height: yMax - yMin,
  }
}

// 大环过滤阈值（cm）：A-pose 手臂垂放大腿侧，指段切片 ~10cm 级——
// 环分类只认 girth > 25 的躯干/腿级环
const BIG = 25

// 站高粗探测（读数近似用，非解剖地标）：脚踝以上腿段恒 2 大环（双腿），
// 裆以上并 1 环——自下而上首个 2→1 跳变即裆；膝/臀/腰按比例派生。
// A-pose 腿微开 + 手指环已由 BIG 过滤，跳变检测不受扰。
export function detectStations(
  positions: Float32Array, indices: Uint32Array,
): NativeBody['stations'] {
  let crotch = 0
  let prev = -1
  for (let y = 5; y <= 115; y += 1) {
    const n = sliceLoops(positions, indices, y)
      .filter((l) => l.closed && l.girth > BIG).length
    if (prev >= 2 && n === 1) { crotch = y; break }
    prev = n
  }
  if (crotch <= 0) return {}      // 探测失败（网格异常）：读数静默置空
  return {
    thigh: { y: crotch - 6, per: 'leg' },
    knee: { y: Math.round(crotch * 0.57), per: 'leg' },
    hips: { y: crotch + 10, per: 'body' },
    waist: { y: crotch + 23, per: 'body' },
  }
}

// 站点围度（全身口径）：body = 最大环（躯干——A-pose 挂臂时臂环更小）；
// leg = 最右大环（右腿——躯干质心可能微偏正，按 cx>0 过滤会被大围度
// 躯干环误选，故取 max-cx 确定性挑出右腿；臂/指环已被 BIG 过滤）
export function readGirth(
  positions: Float32Array, indices: Uint32Array,
  y: number, per: 'body' | 'leg',
): number | null {
  const loops = sliceLoops(positions, indices, y)
    .filter((l) => l.closed && l.girth > BIG)
  if (!loops.length) return null
  const pick = per === 'leg'
    ? loops.reduce((m, l) => (l.cx > m.cx ? l : m))
    : loops.reduce((m, l) => (l.girth > m.girth ? l : m))
  return pick.girth
}
