// 裁片 -> 布料网格：payload 净边链（整版全局系 cm）弧长重采样成边界环
// + 内部错排栅格点 + delaunator 三角化（质心在多边形外的三角形丢弃）。
// 产出裁片网格全套拓扑：三角形、距离约束（三角形全边）、弯曲约束
// （相邻三角形对点）、边界环元数据（边名/角色/边内弧长参数）、2D 定位
// 索引。约束/边界环字段为后续解算重建预留（2026-09-15 解算链已删，
// 一期静态展示只消费 xy/tri）。
// 纯 2D：三维摆位见 assemble.ts。
import Delaunator from 'delaunator'
import type { FittingEdge, FittingPiece } from '../../types'
import { MESH_PRIOR } from './priors'

export type EdgeRole = FittingEdge['role']

// 边名聚合段：payload 中同名边可能分段出现（front side ×3），按链序
// 合并成一条逻辑缝合线；indices 沿链序（front side = 腰口端→脚口端，
// inseam = 脚口端→裆尖，rise/cb = 裆尖→腰口端），arc 为逐点累计弧长。
export interface EdgeRun {
  name: string
  role: EdgeRole
  indices: number[]
  arc: number[]      // 与 indices 对齐，arc[0]=0
  length: number
}

export interface ClothMesh {
  xy: Float64Array             // 2N 平铺 [x0,y0,...]（全局系）
  tri: Uint32Array             // 3T 平铺三角形顶点
  loop: number[]               // 边界环顶点序（闭合，沿边链序）
  runs: EdgeRun[]              // 同名边聚合段（缝合/腰口 pin 用）
  dist: Float32Array           // M×3 平铺 [i, j, rest]
  bend: Float32Array           // K×3 平铺 [i, j, rest]
  /** 逐片抗弯刚度覆盖（解算链已删，约束字段为后续重建预留；缺省全局值） */
  bendK?: number
  /** 逐弯曲边刚度（丹宁裆/膝区域增硬用；与 bendK 同单位，优先级更高） */
  bendKArr?: Float32Array
  locate: (x: number, y: number) => Location | null
}

export interface Location {
  tri: number
  w: [number, number, number]  // 三顶点重心权重（和为 1）
}

const _stepFor = (role: EdgeRole): number =>
  role === 'seam' ? MESH_PRIOR.seamStep : MESH_PRIOR.boundaryStep

// 折线弧长重采样：n 段均分，返回 n 个点（不含终点；终点==下一条边起点）
function resamplePolyline(
  pts: [number, number][], n: number,
): { xs: number[]; ys: number[]; arc: number[] } {
  const segLen: number[] = []
  let total = 0
  for (let i = 0; i < pts.length - 1; i++) {
    const l = Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
    segLen.push(l)
    total += l
  }
  const xs: number[] = [], ys: number[] = [], arc: number[] = []
  let seg = 0, segDone = 0
  for (let k = 0; k < n; k++) {
    const target = (k / n) * total
    while (seg < segLen.length - 1 && segDone + segLen[seg] < target) {
      segDone += segLen[seg]
      seg++
    }
    const t = segLen[seg] > 1e-12 ? (target - segDone) / segLen[seg] : 0
    xs.push(pts[seg][0] + (pts[seg + 1][0] - pts[seg][0]) * t)
    ys.push(pts[seg][1] + (pts[seg + 1][1] - pts[seg][1]) * t)
    arc.push(target)
  }
  return { xs, ys, arc }
}

// 射线法点在多边形内（边界按在内处理，取向无关）
function pointInPolygon(
  px: number, py: number, poly: number[],
): boolean {
  let inside = false
  const n = poly.length / 2
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const xi = poly[2 * i], yi = poly[2 * i + 1]
    const xj = poly[2 * j], yj = poly[2 * j + 1]
    if ((yi > py) !== (yj > py)
        && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) {
      inside = !inside
    }
  }
  return inside
}

export function buildClothMesh(piece: FittingPiece): ClothMesh {
  const xs: number[] = [], ys: number[] = []
  const loopMeta: { name: string; role: EdgeRole; t: number }[] = []
  const runs: EdgeRun[] = []

  // 1) 边链 -> 边界环（相邻边共享端点不重复采样）
  for (let e = 0; e < piece.edges.length; e++) {
    const edge: FittingEdge = piece.edges[e]
    const n = Math.max(1, Math.round(edge.length / _stepFor(edge.role)))
    const rs = resamplePolyline(edge.pts, n)
    for (let k = 0; k < n; k++) {
      loopMeta.push({ name: edge.name, role: edge.role, t: k / n })
      xs.push(rs.xs[k])
      ys.push(rs.ys[k])
    }
    // 同名相邻边聚合
    let run = runs[runs.length - 1]
    if (!run || run.name !== edge.name) {
      run = { name: edge.name, role: edge.role, indices: [], arc: [], length: 0 }
      runs.push(run)
    }
    for (let k = 0; k < n; k++) {
      run.indices.push(xs.length - n + k)
      run.arc.push(run.length + rs.arc[k])
    }
    run.length += edge.length
  }
  const loop = loopMeta.map((_, i) => i)

  // 2) 内部错排栅格（h 间距、行高 h×0.866、隔行错 h/2）
  const poly: number[] = []
  for (const i of loop) poly.push(xs[i], ys[i])
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (let i = 0; i < xs.length; i++) {
    minX = Math.min(minX, xs[i]); maxX = Math.max(maxX, xs[i])
    minY = Math.min(minY, ys[i]); maxY = Math.max(maxY, ys[i])
  }
  const h = MESH_PRIOR.spacing
  const rowH = h * 0.866
  for (let row = 0, y = maxY - rowH; y > minY + 1e-9; y -= rowH, row++) {
    const off = (row % 2) * (h / 2)
    for (let x = minX + off; x < maxX; x += h) {
      if (pointInPolygon(x, y, poly)) {
        xs.push(x); ys.push(y)
      }
    }
  }
  const N = xs.length
  const xy = new Float64Array(2 * N)
  for (let i = 0; i < N; i++) { xy[2 * i] = xs[i]; xy[2 * i + 1] = ys[i] }

  // 3) 三角化 + 质心过滤
  const del = new Delaunator(xy)
  const kept: number[] = []
  for (let t = 0; t < del.triangles.length; t += 3) {
    const a = del.triangles[t], b = del.triangles[t + 1], c = del.triangles[t + 2]
    const cx = (xs[a] + xs[b] + xs[c]) / 3
    const cy = (ys[a] + ys[b] + ys[c]) / 3
    if (pointInPolygon(cx, cy, poly)) kept.push(a, b, c)
  }
  const tri = new Uint32Array(kept)

  // 4) 约束：距离 = 三角形全边（结构+剪切）；弯曲 = 内边对点
  const edgeCount = new Map<number, number>()
  const key = (i: number, j: number) => (i < j ? i * N + j : j * N + i)
  for (let t = 0; t < tri.length; t += 3) {
    const v = [tri[t], tri[t + 1], tri[t + 2]]
    for (let e = 0; e < 3; e++) {
      const k = key(v[e], v[(e + 1) % 3])
      edgeCount.set(k, (edgeCount.get(k) ?? 0) + 1)
    }
  }
  const dist: number[] = [], bend: number[] = []
  const opposite = new Map<number, number[]>()   // 内边 -> 两对点
  for (let t = 0; t < tri.length; t += 3) {
    const v = [tri[t], tri[t + 1], tri[t + 2]]
    for (let e = 0; e < 3; e++) {
      const i = v[e], j = v[(e + 1) % 3], o = v[(e + 2) % 3]
      const k = key(i, j)
      if (edgeCount.get(k) === 1) continue       // 边界边只进距离约束
      const arr = opposite.get(k) ?? []
      arr.push(o)
      opposite.set(k, arr)
    }
  }
  for (const [k, count] of edgeCount) {
    const i = Math.floor(k / N), j = k % N
    dist.push(i, j, Math.hypot(xs[j] - xs[i], ys[j] - ys[i]))
    if (count === 2) {
      const ops = opposite.get(k)
      if (ops && ops.length === 2) {
        const [o1, o2] = ops
        bend.push(o1, o2, Math.hypot(xs[o2] - xs[o1], ys[o2] - ys[o1]))
      }
    }
  }

  // 5) 三角形栅格索引 -> 2D 定位（结构线插值 / 热启动）
  const cellSize = 4
  const grid = new Map<number, number[]>()
  const cellKey = (cx: number, cy: number) => cx * 100000 + cy
  for (let t = 0; t < tri.length; t += 3) {
    const a = tri[t] * 2, b = tri[t + 1] * 2, c = tri[t + 2] * 2
    const x0 = Math.min(xy[a], xy[b], xy[c]), x1 = Math.max(xy[a], xy[b], xy[c])
    const y0 = Math.min(xy[a + 1], xy[b + 1], xy[c + 1])
    const y1 = Math.max(xy[a + 1], xy[b + 1], xy[c + 1])
    for (let cy = Math.floor(y0 / cellSize); cy <= Math.floor(y1 / cellSize); cy++) {
      for (let cx = Math.floor(x0 / cellSize); cx <= Math.floor(x1 / cellSize); cx++) {
        const k = cellKey(cx, cy)
        const arr = grid.get(k) ?? []
        arr.push(t / 3)
        grid.set(k, arr)
      }
    }
  }
  const locate = (px: number, py: number): Location | null => {
    const arr = grid.get(cellKey(Math.floor(px / cellSize), Math.floor(py / cellSize)))
    if (!arr) return null
    for (const t of arr) {
      const i0 = tri[3 * t] * 2, i1 = tri[3 * t + 1] * 2, i2 = tri[3 * t + 2] * 2
      const x0 = xy[i0], y0 = xy[i0 + 1], x1 = xy[i1], y1v = xy[i1 + 1]
      const x2 = xy[i2], y2 = xy[i2 + 1]
      const d = (y1v - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
      if (Math.abs(d) < 1e-12) continue
      const w0 = ((y1v - y2) * (px - x2) + (x2 - x1) * (py - y2)) / d
      const w1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / d
      const w2 = 1 - w0 - w1
      const eps = -1e-6
      if (w0 >= eps && w1 >= eps && w2 >= eps) {
        return { tri: t, w: [w0, w1, w2] }
      }
    }
    return null
  }

  return {
    xy, tri, loop, runs,
    dist: new Float32Array(dist), bend: new Float32Array(bend), locate,
  }
}

// 同名多条 run 按链序拼成一条逻辑链（2026-09-17 八期整裤缝合）：runs
// 数组序 ≠ 链序——back 宿主 side 两条 run（育克侧段在数组末尾、后片
// 侧缝在数组前部）。按 run 首采样纸样 y 降序排序 = 腰口端优先（side
// 链方向约定腰口端起），indices 顺拼、arc 在前段总长上续接。单条原样
// 返回，零条返回 null；>2 条 warn 后硬拼（当前款型不会出现）
export function mergeRuns(runs: EdgeRun[], xy: Float64Array): EdgeRun | null {
  if (runs.length === 0) return null
  if (runs.length === 1) return runs[0]
  if (runs.length > 2) {
    console.warn(`[mesh] mergeRuns：'${runs[0].name}' 有 ${runs.length} 条 run（预期 ≤2），按首采样 y 降序硬拼`)
  }
  const sorted = [...runs].sort(
    (a, b) => xy[2 * b.indices[0] + 1] - xy[2 * a.indices[0] + 1])
  const out: EdgeRun = { ...sorted[0], indices: [], arc: [], length: 0 }
  for (const run of sorted) {
    for (let k = 0; k < run.indices.length; k++) {
      out.indices.push(run.indices[k])
      out.arc.push(out.length + run.arc[k])
    }
    out.length += run.length
  }
  return out
}

// 弧长参数 -> 段内顶点号（线性插值取最近顶点；配对两端对齐用）
export function runIndexAt(run: EdgeRun, t: number): number {
  const target = Math.max(0, Math.min(1, t)) * run.length
  for (let i = 1; i < run.arc.length; i++) {
    if (run.arc[i] >= target) {
      const prev = run.arc[i - 1]
      const frac = run.arc[i] - prev > 1e-12
        ? (target - prev) / (run.arc[i] - prev) : 0
      return frac > 0.5 ? run.indices[i] : run.indices[i - 1]
    }
  }
  return run.indices[run.indices.length - 1]
}
