// 直腰头条带（2026-09-13 用户口径：腰头必须与前后片物理连成整体）。
// 直腰头净样 = 矩形（长×宽）：payload 腰头虽只导出标量（frame='local'
// 旋转局部系不可逆推），但 bottom_length（代数求和净长）×width 足以
// 前端重建——弯腰头净样非矩形（真拼合+均匀圆弧），三标量重建不出，
// 上游 seams.ts 按 waistband_type 门控回退视觉环带。
// 局部系：x = 环向弧长 s（0 = 后中，与腰缝环序一致），y = 纸样高度
// （y0 = 腰站高，上沿 y0+width——直接进 placePoint 的 warp 链）。
import type { ClothMesh, EdgeRole, EdgeRun } from './mesh'
import { MESH_PRIOR, SOLVER_PRIOR } from './priors'

export interface BandSpec {
  length: number        // bottom_length：底边净长（≈ Σ四片腰口弧）
  width: number         // 腰头宽
  y0: number            // 底边所在纸样高度（payload waist 站 y）
}

// 直腰头结构化栅格布网（不走 buildClothMesh 通用链）：通用链的边界重采样
// 按「共享端点」约定（每边不含终点、矩形四角分属四条边），左右端竖边顶点
// 行集天然错一行 {1..W} vs {0..W−1}，bandEnd 缝合对永远差一个步长；矩形
// 规整行列两端行集严格重合。距离约束 = 结构边+双剪切对角（与通用链
// Delaunay 全边口径一致），弯曲约束 = 跳一格边（「相邻三角形对点」在
// 规整栅格上的等价物）。
export function buildBandMesh(spec: BandSpec): ClothMesh {
  const { length: L, width: W, y0 } = spec
  const nC = Math.max(2, Math.round(L / MESH_PRIOR.seamStep) + 1)
  const nR = Math.max(2, Math.round(W / MESH_PRIOR.seamStep) + 1)
  const dx = L / (nC - 1), dy = W / (nR - 1)
  const N = nC * nR
  const v = (r: number, c: number) => r * nC + c
  const xy = new Float64Array(2 * N)
  for (let r = 0; r < nR; r++) {
    for (let c = 0; c < nC; c++) {
      xy[2 * v(r, c)] = c * dx
      xy[2 * v(r, c) + 1] = y0 + r * dy
    }
  }
  // 每格两片，主对角 a-b-e / 次 a-e-d（与通用链 Delaunay 同构）
  const tri: number[] = []
  const cells = nC - 1
  for (let r = 0; r + 1 < nR; r++) {
    for (let c = 0; c < cells; c++) {
      const a = v(r, c), b = v(r, c + 1), d = v(r + 1, c), e = v(r + 1, c + 1)
      tri.push(a, b, e, a, e, d)
    }
  }
  const dist: number[] = []
  const bend: number[] = []
  const seen = new Set<number>()
  const pushDist = (i: number, j: number) => {
    const k = i < j ? i * N + j : j * N + i
    if (seen.has(k)) return
    seen.add(k)
    dist.push(i, j, Math.hypot(xy[2 * j] - xy[2 * i], xy[2 * j + 1] - xy[2 * i + 1]))
  }
  const pushBend = (i: number, j: number) => {
    bend.push(i, j, Math.hypot(xy[2 * j] - xy[2 * i], xy[2 * j + 1] - xy[2 * i + 1]))
  }
  for (let r = 0; r < nR; r++) {
    for (let c = 0; c < nC; c++) {
      if (c + 1 < nC) pushDist(v(r, c), v(r, c + 1))     // 结构：环向
      if (r + 1 < nR) pushDist(v(r, c), v(r + 1, c))     // 结构：高度向
      if (r + 1 < nR && c + 1 < nC) {
        pushDist(v(r, c), v(r + 1, c + 1))               // 剪切对角
        pushDist(v(r, c + 1), v(r + 1, c))
      }
      if (c + 2 < nC) pushBend(v(r, c), v(r, c + 2))     // 弯曲：跳一格
      if (r + 2 < nR) pushBend(v(r, c), v(r + 2, c))
    }
  }
  // 边链（名/角色/方向与旧 buildBandPiece 约定一致：底边 0→L、右端 底→顶、
  // 顶边 右→左、左端 顶→底；闭合环序同链序）
  const mkRun = (name: string, role: EdgeRole, n: number,
    idx: (k: number) => number, step: number): EdgeRun => {
    const run: EdgeRun = { name, role, indices: [], arc: [], length: (n - 1) * step }
    for (let k = 0; k < n; k++) {
      run.indices.push(idx(k))
      run.arc.push(k * step)
    }
    return run
  }
  const bottom = mkRun('bottom', 'seam', nC, (k) => v(0, k), dx)
  const endB = mkRun('end_b', 'seam', nR, (k) => v(k, nC - 1), dy)
  const top = mkRun('top', 'hem', nC, (k) => v(nR - 1, nC - 1 - k), dx)
  const endA = mkRun('end_a', 'seam', nR, (k) => v(nR - 1 - k, 0), dy)
  const loop: number[] = [...bottom.indices,
    ...endB.indices.slice(1),                 // 底右角已在 bottom
    ...top.indices.slice(1),                  // 顶右角已在 end_b
    ...endA.indices.slice(1, -1)]             // 两角分别属于 top/bottom
  const cellOf = (r: number, c: number) => 2 * (r * cells + c)
  const locate = (px: number, py: number) => {
    const fc = px / dx, fr = (py - y0) / dy
    if (fc < 0 || fr < 0 || fc > nC - 1 || fr > nR - 1) return null
    const c = Math.min(cells - 1, Math.floor(fc)), r = Math.min(nR - 2, Math.floor(fr))
    const uc = fc - c, ur = fr - r
    if (uc >= ur) {
      // 主对角三角 (a, b, e)：局部重心 (1−uc, uc−ur, ur)
      return { tri: cellOf(r, c), w: [1 - uc, uc - ur, ur] as [number, number, number] }
    }
    // 次对角三角 (a, e, d)：重心 (1−ur, uc, ur−uc)
    return { tri: cellOf(r, c) + 1, w: [1 - ur, uc, ur - uc] as [number, number, number] }
  }
  return {
    xy, tri: new Uint32Array(tri), loop, runs: [bottom, endB, top, endA],
    dist: new Float32Array(dist), bend: new Float32Array(bend), locate,
    bendK: SOLVER_PRIOR.bandBendStiffness,
  }
}

// 腰头对账：bottom_length vs 四片腰口弧合计（同口径含省口余量，打版
// 代数求和保证一致；越界 = 引擎/前端口径漂移，宁可炸不可静默歪缝）
export function checkBandLength(
  bottomLength: number, waistArcs: number[], tol = 0.005,
): void {
  const sum = waistArcs.reduce((a, b) => a + b, 0)
  if (sum <= 0) throw new Error('腰口弧合计非法（≤0）')
  const rel = Math.abs(bottomLength - sum) / sum
  if (rel > tol) {
    throw new Error(`腰头底长 ${bottomLength.toFixed(2)}cm 与四片腰口弧合计 `
      + `${sum.toFixed(2)}cm 偏差 ${(rel * 100).toFixed(2)}% > ${(tol * 100)
      }%——缝合口径漂移`)
  }
}
