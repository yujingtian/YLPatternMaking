// 粒子-人台碰撞：解析投影（y 夹取 -> 插值环 -> 方向上超椭圆半径），
// 不用 raycast。穿透时沿径向推出到 R+skin，并按 friction 削掉切向滑动。
// 骨盆/两腿各自投影取最深（y 范围外的管自动跳过，常规粒子只碰 1 管）。
import type { Mannequin } from '../mannequin'
import { radiusAt, sectionAt } from '../mannequin'

export function collideOne(
  pos: Float32Array, prev: Float32Array, i: number,
  man: Mannequin, skin: number, friction: number,
): void {
  const i3 = 3 * i
  const y = pos[i3 + 1]
  const tubes = [man.pelvis, man.legs[0], man.legs[1]]
  for (const tube of tubes) {
    const lo = tube.rings[tube.rings.length - 1].y
    const hi = tube.rings[0].y
    if (y < lo || y > hi) continue
    const s = sectionAt(tube, y)
    const dx = pos[i3] - s.cx
    const dz = pos[i3 + 2]
    const dist = Math.hypot(dx, dz)
    if (dist < 1e-9) continue
    // radiusAt 只接受单位方向向量（语义修复 2026-09-09）：旧代码把未归一化
    // (dx,dz) 直灌，返回的是向量倍数而非半径，穿透判据退化为
    // dist ≥ R/dist + skin、均衡点 ≈√R（骨盆 ~3.8cm），布料可沉入体表 ~10cm
    const nx = dx / dist, nz = dz / dist
    const limit = radiusAt(s, nx, nz) + skin
    if (dist >= limit) continue
    pos[i3] = s.cx + nx * limit
    pos[i3 + 2] = nz * limit
    // 摩擦：推出后的位移里，切向分量按 friction 比例拉回（贴体防滑落）
    const mx = pos[i3] - prev[i3], mz = pos[i3 + 2] - prev[i3 + 2]
    const mn = mx * nx + mz * nz
    const tx = (mx - nx * mn) * friction
    const tz = (mz - nz * mn) * friction
    pos[i3] -= tx
    pos[i3 + 2] -= tz
  }
}
