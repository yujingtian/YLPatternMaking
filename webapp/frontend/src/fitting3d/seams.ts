// 初始摆位与缝合：把前后片 2D 网格（整版全局系，X 从侧缝指向前中/后中）
// 包裹到人台上形成整裤初始态，并按边名配对缝合约束、登记腰口 pin。
// 约定（§10.11）：position=(r·sinθ, y, r·cosθ)，θ=0 前中(+Z)、
// 90°= wearer 右(+X)；as-drafted 片 = 左半，右半镜像 θ→−θ。
//   前左片：侧缝(t=0) θ=−90° -> 前浪(t=1) θ=0°
//   后左片：后中(t=0) θ=180° -> 侧缝(t=1) θ=270°
import type { Mannequin } from './mannequin'
import { radiusAt, sectionAt } from './mannequin'
import type { ClothMesh, EdgeRun } from './mesh'
import { runIndexAt } from './mesh'
import { MESH_PRIOR, SOLVER_PRIOR } from './priors'

export type PieceKey = 'front' | 'back'
export type Side = 'L' | 'R'

export interface GarmentPart {
  key: PieceKey
  side: Side
  mesh: ClothMesh
  offset: number          // 粒子全局号 = offset + 网格顶点号
}

export interface Garment {
  parts: GarmentPart[]    // [fL, fR, bL, bR]
  pos: Float32Array       // 3P 初始位置（包裹摆位，非穿透）
  seam: Int32Array        // 2S 缝合粒子对
  pinIdx: Uint32Array     // 腰口 pin 粒子号
  pinTarget: Float32Array // 3×pin 粒子目标位（自身 drafted 高度处体表环+松量）
  total: number
}

// 体表支撑半径：方向 θ 上各覆盖管支撑距离的最大值（凸上界，保证初态
// 不穿体；比射线求交便宜且无腿间缝隙退化）
export function surfaceRadius(man: Mannequin, y: number, th: number): number {
  const dx = Math.sin(th), dz = Math.cos(th)
  let best = 0
  for (const tube of [man.pelvis, man.legs[0], man.legs[1]]) {
    const lo = tube.rings[tube.rings.length - 1].y
    const hi = tube.rings[0].y
    if (y < lo || y > hi) continue
    const s = sectionAt(tube, y)
    best = Math.max(best, s.cx * dx + radiusAt(s, dx, dz))
  }
  if (best <= 0) {
    const s = sectionAt(man.pelvis, Math.min(Math.max(y, man.bottomY), man.topY))
    best = radiusAt(s, dx, dz)
  }
  return best
}

// 单粒子摆位：全局 2D (x,y) -> 3D
export function placePoint(
  key: PieceKey, side: Side, x: number, y: number,
  xMin: number, xMax: number, man: Mannequin,
): [number, number, number] {
  const t = Math.max(0, Math.min(1, (x - xMin) / (xMax - xMin || 1)))
  const base = key === 'front' ? -Math.PI / 2 : Math.PI
  let th = base + (Math.PI / 2) * t
  if (side === 'R') th = -th
  const r = surfaceRadius(man, y, th) + SOLVER_PRIOR.garmentGap
  return [r * Math.sin(th), y, r * Math.cos(th)]
}

const runOf = (part: GarmentPart, name: string): EdgeRun | undefined =>
  part.mesh.runs.find((r) => r.name === name)

// 两条聚合段配对：t 均分采样、取段内最近顶点；reverse=true 从末端
// （脚口端）起配——侧缝前后片长度不等时保证脚口角点对齐、余量上移
function pairRuns(
  a: GarmentPart, runA: EdgeRun,
  b: GarmentPart, runB: EdgeRun,
  reverse: boolean, out: number[],
): void {
  const n = Math.max(2, Math.round(Math.max(runA.length, runB.length)
    / MESH_PRIOR.seamStep))
  for (let k = 0; k < n; k++) {
    const t = reverse ? 1 - k / (n - 1) : k / (n - 1)
    out.push(a.offset + runIndexAt(runA, t), b.offset + runIndexAt(runB, t))
  }
}

// 四半片 -> 整裤初始态（粒子、缝合、腰口 pin）
export function buildGarment(
  meshes: Record<PieceKey, ClothMesh>, man: Mannequin,
): Garment {
  const parts: GarmentPart[] = []
  let offset = 0
  for (const key of ['front', 'back'] as PieceKey[]) {
    for (const side of ['L', 'R'] as Side[]) {
      parts.push({ key, side, mesh: meshes[key], offset })
      offset += meshes[key].xy.length / 2
    }
  }
  const total = offset
  const pos = new Float32Array(3 * total)

  // 摆位（右半镜像 θ→−θ，等价 X 取反）
  for (const part of parts) {
    const { xy } = part.mesh
    const off = part.offset
    let xMin = Infinity, xMax = -Infinity
    for (let i = 0; i < xy.length; i += 2) {
      xMin = Math.min(xMin, xy[i]); xMax = Math.max(xMax, xy[i])
    }
    for (let i = 0; i < xy.length / 2; i++) {
      const [px, py, pz] = placePoint(
        part.key, part.side, xy[2 * i], xy[2 * i + 1], xMin, xMax, man)
      pos[3 * (off + i)] = px
      pos[3 * (off + i) + 1] = py
      pos[3 * (off + i) + 2] = pz
    }
  }

  // 缝合配对：左右侧各 side/inseam，rise/cb 跨左右镜像缝
  const seam: number[] = []
  const P = (key: PieceKey, side: Side) =>
    parts.find((p) => p.key === key && p.side === side)!
  const need = (part: GarmentPart, name: string): EdgeRun => {
    const r = runOf(part, name)
    if (!r) throw new Error(`缝合配对缺边：${part.key}.${part.side}.${name}`)
    return r
  }
  for (const side of ['L', 'R'] as Side[]) {
    pairRuns(P('front', side), need(P('front', side), 'side'),
      P('back', side), need(P('back', side), 'side'), true, seam)
    pairRuns(P('front', side), need(P('front', side), 'inseam'),
      P('back', side), need(P('back', side), 'inseam'), false, seam)
  }
  pairRuns(P('front', 'L'), need(P('front', 'L'), 'rise'),
    P('front', 'R'), need(P('front', 'R'), 'rise'), false, seam)
  pairRuns(P('back', 'L'), need(P('back', 'L'), 'cb'),
    P('back', 'R'), need(P('back', 'R'), 'cb'), false, seam)

  // 腰口 pin：top_chain 边粒子钉在自身 drafted 高度体表环 + 松量
  const pinIdx: number[] = []
  const pinTarget: number[] = []
  for (const part of parts) {
    for (const run of part.mesh.runs) {
      if (run.role !== 'top_chain') continue
      for (const idx of run.indices) {
        const i = part.offset + idx
        pinIdx.push(i)
        pinTarget.push(pos[3 * i], pos[3 * i + 1], pos[3 * i + 2])
      }
    }
  }

  return {
    parts, pos,
    seam: new Int32Array(seam),
    pinIdx: new Uint32Array(pinIdx),
    pinTarget: new Float32Array(pinTarget),
    total,
  }
}

// 腰头视觉环带（静态、不参与仿真）：腰口线 -> 上沿 waistband_width，
// 半径 = 体表支撑半径 + 松量 + 0.3cm 外扩；纯数组，three 装配在视图层
export function buildWaistBand(
  man: Mannequin, yWaist: number, width: number, segments = MESH_PRIOR.ringSegments,
): { positions: number[]; indices: number[] } {
  const gap = SOLVER_PRIOR.garmentGap + 0.3
  const positions: number[] = []
  const indices: number[] = []
  for (const y of [yWaist, yWaist + width]) {
    for (let i = 0; i < segments; i++) {
      const th = (i / segments) * Math.PI * 2
      const r = surfaceRadius(man, y, th) + gap
      positions.push(r * Math.sin(th), y, r * Math.cos(th))
    }
  }
  for (let i = 0; i < segments; i++) {
    const a = i, b = (i + 1) % segments
    const c = segments + (i + 1) % segments, d = segments + i
    indices.push(a, b, c, a, c, d)
  }
  return { positions, indices }
}
