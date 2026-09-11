// 稀疏 morph：pos = base + Σ wᵢ·Δᵢ（8 个 measure target，裁切后索引已重映射，
// 拓扑跨权重恒定——金标 test_topology_constant_across_morph）。ms 级：
// ~5k 受影响顶点 × 8 target 上限。
import type { BodyMeshAsset, TargetName } from './types'

export type MeshWeights = Partial<Record<TargetName, number>>

export function morphPositions(
  asset: BodyMeshAsset, weights: MeshWeights,
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

// 地标顶点索引 -> morph 后坐标（S3：measure target 会局部移顶点，地标高度
// 必须从 morphed 位置重读，不能存常数）。只回 y（对齐/高度场只需高度）。
export function landmarkY(
  pos: Float32Array, asset: BodyMeshAsset, name: string,
): number {
  const i = asset.meta.landmarks[name]
  if (i == null) throw new Error(`地标 ${name} 不在 targets.json`)
  return pos[3 * i + 1]
}
