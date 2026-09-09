// 距离约束投影（Gauss-Seidel 原地更新，等质量双向各移一半）。
// stiffness k ∈ (0,1]：单次迭代的投影比例（与迭代次数等效叠加）。
export function projectDistance(
  pos: Float32Array, i: number, j: number, rest: number, k: number,
): void {
  const i3 = 3 * i, j3 = 3 * j
  const dx = pos[j3] - pos[i3]
  const dy = pos[j3 + 1] - pos[i3 + 1]
  const dz = pos[j3 + 2] - pos[i3 + 2]
  const d = Math.sqrt(dx * dx + dy * dy + dz * dz)
  if (d < 1e-9) return
  const diff = (k * (d - rest) / d) * 0.5
  pos[i3] += dx * diff; pos[i3 + 1] += dy * diff; pos[i3 + 2] += dz * diff
  pos[j3] -= dx * diff; pos[j3 + 1] -= dy * diff; pos[j3 + 2] -= dz * diff
}

// 腰口 pin：向目标位投影权重 w（<1 保留微让步，防整裤被腰口锁死）
export function projectPin(
  pos: Float32Array, i: number,
  tx: number, ty: number, tz: number, w: number,
): void {
  const i3 = 3 * i
  pos[i3] += (tx - pos[i3]) * w
  pos[i3 + 1] += (ty - pos[i3 + 1]) * w
  pos[i3 + 2] += (tz - pos[i3 + 2]) * w
}
