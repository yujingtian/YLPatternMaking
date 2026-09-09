// 应变热力图：每粒子取邻接距离约束 当前长/静止长−1 的平均作为应变。
// PBD 约束数据顺手可算，零额外解算成本；正值=拉伸紧绷(红)、负值=
// 压缩松弛(蓝)、0=贴合(绿)。色带三锚点线性插值，maxStrain 饱和阈。
import type { Garment } from './seams'

export function computeStrain(
  garment: Garment, pos: Float32Array,
): Float32Array {
  const acc = new Float32Array(garment.total)
  const wsum = new Float32Array(garment.total)
  for (const part of garment.parts) {
    const { dist } = part.mesh
    const { offset } = part
    for (let c = 0; c < dist.length; c += 3) {
      const i = offset + dist[c], j = offset + dist[c + 1]
      const rest = dist[c + 2]
      const dx = pos[3 * j] - pos[3 * i]
      const dy = pos[3 * j + 1] - pos[3 * i + 1]
      const dz = pos[3 * j + 2] - pos[3 * i + 2]
      const d = Math.sqrt(dx * dx + dy * dy + dz * dz)
      if (rest < 1e-9 || !Number.isFinite(d)) continue
      const e = d / rest - 1
      acc[i] += e; wsum[i] += 1
      acc[j] += e; wsum[j] += 1
    }
  }
  for (let i = 0; i < garment.total; i++) {
    acc[i] = wsum[i] > 0 ? acc[i] / wsum[i] : 0
  }
  return acc
}

// 应变 -> RGB（0~1）：绿(贴合) -> 红(紧绷, e>=+max) / 蓝(松弛, e<=−max)
export function strainColor(
  e: number, maxStrain = 0.08,
): [number, number, number] {
  const t = Math.max(-1, Math.min(1, e / maxStrain))
  if (t >= 0) {
    // (0.20,0.78,0.45) -> (0.92,0.13,0.10)
    return [0.20 + 0.72 * t, 0.78 - 0.65 * t, 0.45 - 0.35 * t]
  }
  const u = -t
  // (0.20,0.78,0.45) -> (0.13,0.42,0.92)
  return [0.20 - 0.07 * u, 0.78 - 0.36 * u, 0.45 + 0.47 * u]
}
