// 稀疏 morph：pos = base + Σ wᵢ·Δᵢ（8 个官方 measure target，索引即
// base.obj 原始顶点号，native.ts 全身网格直接对齐）。ms 级：受影响顶点
// × 8 场上限。
import type { MeshTarget, TargetName } from './types'

export type MeshWeights = Partial<Record<TargetName, number>>

export function morphPositions(
  asset: { positions: Float32Array; targets: MeshTarget[] },
  weights: MeshWeights,
): Float32Array {
  const out = asset.positions.slice()
  for (const t of asset.targets) {
    const w = weights[t.name] ?? 0
    if (w === 0) continue
    const { idx, d } = t
    for (let k = 0; k < idx.length; k++) {
      const i3 = 3 * idx[k], j = 3 * k
      out[i3] += w * d[j]
      out[i3 + 1] += w * d[j + 1]
      out[i3 + 2] += w * d[j + 2]
    }
  }
  return out
}
