// 松量读数（M2）：整裤围度切片 + 人台围度切片对比。
// 整裤侧难点：缝合对是**物理约束**不是共享顶点——前后片在侧缝/内缝处
// 拓扑独立，bodymesh/slice 的共享端点链法在缝上必断链。这里按端点距离
// 容差 greedy 链接（缝合残差实测 <0.5cm，容差 seamStep×1.5 覆盖；腿间
// 净距 ≥2cm 不会误链）。挑环口径与 readGirth 一致：body 站取最大环、
// leg 站取最右大环（右腿确定性，不受质心微偏影响）。
// 人台侧复用 bodymesh/readGirth（共享顶点网格，精确链）。
// 独立原则：两侧各读各的，互不反推。
import { readGirth } from '../bodymesh/slice'
import type { FittingStation } from '../../types'
import type { Garment } from './seams'

export interface GirthLoop {
  girth: number
  cx: number
}

interface Seg {
  ax: number; az: number   // 端点 A
  bx: number; bz: number   // 端点 B
  used: boolean
}

// 平面 y 切全部三角形 -> 线段集（三角形跨平面才相交；顶点恰在平面上
// 时微扰 y 防 0 长退化）
function sliceSegs(
  pos: Float32Array, tri: Uint32Array, y: number,
): Seg[] {
  const segs: Seg[] = []
  for (let t = 0; t < tri.length; t += 3) {
    const a = tri[t], b = tri[t + 1], c = tri[t + 2]
    const ya = pos[3 * a + 1], yb = pos[3 * b + 1], yc = pos[3 * c + 1]
    const lo = Math.min(ya, yb, yc), hi = Math.max(ya, yb, yc)
    if (y <= lo || y >= hi) continue
    // 每条边与平面的交点（跨平面的边恰有 2 条）
    const pts: [number, number][] = []
    const edge = (i: number, j: number): void => {
      const yi = pos[3 * i + 1], yj = pos[3 * j + 1]
      if ((yi - y) * (yj - y) < 0) {
        const s = (y - yi) / (yj - yi)
        pts.push([pos[3 * i] + s * (pos[3 * j] - pos[3 * i]),
          pos[3 * i + 2] + s * (pos[3 * j + 2] - pos[3 * i + 2])])
      }
    }
    edge(a, b); edge(b, c); edge(c, a)
    if (pts.length === 2) {
      segs.push({ ax: pts[0][0], az: pts[0][1], bx: pts[1][0], bz: pts[1][1],
        used: false })
    }
  }
  return segs
}

// 容差闭环：从任一未用线段起 greedy 链（当前链端 -> tol 内最近未用线段
// 端点），链回起点成环才计围度；返回全部闭环
export function garmentLoops(
  pos: Float32Array, tri: Uint32Array, y: number, tol: number,
): GirthLoop[] {
  const segs = sliceSegs(pos, tri, y + 1e-4)
  const loops: GirthLoop[] = []
  const d2 = (x1: number, z1: number, x2: number, z2: number): number =>
    (x1 - x2) * (x1 - x2) + (z1 - z2) * (z1 - z2)
  for (let s0 = 0; s0 < segs.length; s0++) {
    if (segs[s0].used) continue
    segs[s0].used = true
    const chain: [number, number][] = [[segs[s0].ax, segs[s0].az]]
    let ex = segs[s0].bx, ez = segs[s0].bz   // 链开放端
    let girth = Math.hypot(ex - segs[s0].ax, ez - segs[s0].az)
    let closed = false
    for (;;) {
      // 最近未用线段的可达端点（A 或 B 均可为接口）
      let best = -1, bestD = tol * tol, flip = false
      for (let k = 0; k < segs.length; k++) {
        const s = segs[k]
        if (s.used) continue
        let dd = d2(ex, ez, s.ax, s.az)
        if (dd < bestD) { bestD = dd; best = k; flip = false }
        dd = d2(ex, ez, s.bx, s.bz)
        if (dd < bestD) { bestD = dd; best = k; flip = true }
      }
      if (best < 0) break
      const s = segs[best]
      s.used = true
      const nx = flip ? s.ax : s.bx, nz = flip ? s.az : s.bz
      chain.push([nx, nz])
      girth += Math.hypot(nx - ex, nz - ez)
      ex = nx; ez = nz
      if (d2(ex, ez, chain[0][0], chain[0][1]) <= tol * tol) { closed = true; break }
    }
    if (closed && girth > 25) {
      loops.push({ girth, cx: chain.reduce((a, p) => a + p[0], 0) / chain.length })
    }
  }
  return loops
}

const pickLoop = (loops: GirthLoop[], per: 'body' | 'leg'): number | null => {
  if (!loops.length) return null
  const pick = per === 'leg'
    ? loops.reduce((m, l) => (l.cx > m.cx ? l : m))
    : loops.reduce((m, l) => (l.girth > m.girth ? l : m))
  return pick.girth
}

export interface EaseRow {
  key: FittingStation['key']
  y: number           // 纸样系切片高（解算空间 = 纸样系，2026-09-14 解耦）
  sim: number | null  // 整裤切片围度
  body: number | null // 人台切片围度（warp(st.y) 处读，仅显示参照）
  pattern: number | null // girth_finished（纸样成衣量；crotch 为 null）
  ease: number | null // sim − body（正值=松量、负值=绷）
}

// 逐站读数：整裤（容差链，纸样系 st.y 处切）vs 人台（readGirth，warp 后
// 人台高度切——两侧各读各的坐标系）vs 纸样 girth_finished
export function easeRows(
  garment: Garment, pos: Float32Array, stations: FittingStation[],
  warp: (y: number) => number,
  bodyPos: Float32Array, bodyIdx: Uint32Array,
  tol = 1.5,
): EaseRow[] {
  const rows: EaseRow[] = []
  for (const st of stations) {
    if (st.key === 'crotch') continue   // 拓扑分叉站无围度
    const sim = pickLoop(garmentLoops(pos, garment.triAll, st.y, tol), st.per)
    const body = readGirth(bodyPos, bodyIdx, warp(st.y), st.per)
    rows.push({
      key: st.key, y: st.y, sim, body, pattern: st.girth_finished,
      ease: sim !== null && body !== null ? sim - body : null,
    })
  }
  return rows
}
