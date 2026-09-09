// 结构线随布料变形：marks 折线 ~1cm 弧长重采样后，把每个采样点烘焙成
// 所在三角形的重心绑定（三粒子号 + 三权重，构建期一次性），每帧按当前
// 粒子位置插值写出 LineSegments 顶点。口袋口/门襟/机头/贴袋等边界
// 随布面动，零每帧定位开销。
import type { FittingPiece } from '../types'
import type { ClothMesh } from './mesh'
import { MESH_PRIOR } from './priors'

export interface BakedLine {
  bind: Int32Array        // 3n：每采样点三个全局粒子号
  w: Float32Array         // 3n：对应重心权重（和为 1）
  positions: Float32Array // 3n：每帧插值结果（视图直接挂 BufferAttribute）
  n: number
}

function resampleMark(
  pts: [number, number][], step: number,
): [number, number][] {
  const out: [number, number][] = []
  for (let i = 0; i < pts.length - 1; i++) {
    const [x0, y0] = pts[i], [x1, y1] = pts[i + 1]
    const len = Math.hypot(x1 - x0, y1 - y0)
    const n = Math.max(1, Math.ceil(len / step))
    for (let k = 0; k < n; k++) {
      const t = k / n
      out.push([x0 + (x1 - x0) * t, y0 + (y1 - y0) * t])
    }
  }
  out.push(pts[pts.length - 1])
  return out
}

export function bakeStructureLines(
  piece: FittingPiece, mesh: ClothMesh, offset: number,
): BakedLine[] {
  const lines: BakedLine[] = []
  for (const mark of piece.marks ?? []) {
    if (!mark.pts || mark.pts.length < 2) continue
    const samples = resampleMark(mark.pts, MESH_PRIOR.markStep)
    const bind = new Int32Array(3 * samples.length)
    const w = new Float32Array(3 * samples.length)
    let ok = 0
    for (let k = 0; k < samples.length; k++) {
      const loc = mesh.locate(samples[k][0], samples[k][1])
      if (!loc) continue        // 网格外样本（浮点边缘）整段跳过
      for (let d = 0; d < 3; d++) {
        bind[3 * k + d] = offset + mesh.tri[3 * loc.tri + d]
        w[3 * k + d] = loc.w[d]
      }
      ok++
    }
    if (ok < samples.length) continue   // 有落空即弃该线（保守，不画残线）
    lines.push({
      bind, w,
      positions: new Float32Array(3 * samples.length),
      n: samples.length,
    })
  }
  return lines
}

// 逐帧：重心插值写 positions（LineSegments 需逐段复制成对端点在视图层做）
export function updateBakedLine(line: BakedLine, pos: Float32Array): void {
  for (let k = 0; k < line.n; k++) {
    const a = 3 * line.bind[3 * k], b = 3 * line.bind[3 * k + 1]
    const c = 3 * line.bind[3 * k + 2]
    const w0 = line.w[3 * k], w1 = line.w[3 * k + 1], w2 = line.w[3 * k + 2]
    for (let d = 0; d < 3; d++) {
      line.positions[3 * k + d] = w0 * pos[a + d] + w1 * pos[b + d]
        + w2 * pos[c + d]
    }
  }
}
