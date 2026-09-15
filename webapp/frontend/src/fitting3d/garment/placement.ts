// 支撑半径场 + 静态摆位（2026-09-15 重建一期：前片 L+R 一对）。
// R(y,θ) 表：对网格逐水平行切片，取全部切片环在方向 θ 上的支撑距离
// （凸上界）——多环（两腿）与并集保守带自动取最大；保证初始摆位不
// 穿体、无腿间缝隙退化。重建一期场从撑型芯（core.ts）建，人台出圈。
// 摆位约定：position = (r·sinθ, y, r·cosθ)，θ=0 前中(+Z)、90°=
// wearer 右(+X)；as-drafted 前片 = 左半扇区 [−90°,0°]，右半镜像
// θ→−θ。y = 纸样高（纸样系 identity，无 warp）。
import { sliceLoops } from '../bodymesh/slice'
import { FIELD_PRIOR, HANG_PRIOR } from './priors'

export class BodyField {
  constructor(
    readonly table: Float32Array,   // rows × thetaBins
    readonly rows: number,
    readonly rowStep: number,
    readonly thetaBins: number,
  ) {}

  /** 全表最大支撑半径（悬挂展示算裤筒旁置偏移用：人台 +X 侧占位上界） */
  get maxRadius(): number {
    let m = 0
    for (let i = 0; i < this.table.length; i++) {
      if (this.table[i] > m) m = this.table[i]
    }
    return m
  }

  radiusAt(y: number, th: number): number {
    // y 夹取（腰上无几何/脚底下沿用端行），行双线性
    const rr = Math.max(0, Math.min(this.rows - 1.0001, y / this.rowStep))
    const r0 = Math.floor(rr), fr = rr - r0
    const r1 = Math.min(this.rows - 1, r0 + 1)
    // θ 环形双线性（bin 中心约定 (b+0.5)·Δ）
    const delta = (2 * Math.PI) / this.thetaBins
    let t = (th / delta) - 0.5
    t = ((t % this.thetaBins) + this.thetaBins) % this.thetaBins
    const b0 = Math.floor(t), fb = t - b0
    const b1 = (b0 + 1) % this.thetaBins
    const row0 = r0 * this.thetaBins, row1 = r1 * this.thetaBins
    const v00 = this.table[row0 + b0], v01 = this.table[row0 + b1]
    const v10 = this.table[row1 + b0], v11 = this.table[row1 + b1]
    return (v00 * (1 - fb) + v01 * fb) * (1 - fr)
      + (v10 * (1 - fb) + v11 * fb) * fr
  }
}

// 从（morph 后）人台网格建场：逐行切片，全部环的点做方向支撑最大值。
// 一次性 ~几十 ms（240 行 × 8618 三角 + 支撑填表），只在建衣/重穿时跑
export function buildBodyField(
  positions: Float32Array, indices: Uint32Array,
): BodyField {
  const { thetaBins, rowStep } = FIELD_PRIOR
  let maxY = -Infinity
  for (let i = 1; i < positions.length; i += 3) {
    if (positions[i] > maxY) maxY = positions[i]
  }
  const rows = Math.max(2, Math.floor(maxY / rowStep) + 1)
  const table = new Float32Array(rows * thetaBins)
  // 方向单位向量预表（bin 中心）
  const sinT = new Float32Array(thetaBins), cosT = new Float32Array(thetaBins)
  for (let b = 0; b < thetaBins; b++) {
    const th = ((b + 0.5) / thetaBins) * 2 * Math.PI
    sinT[b] = Math.sin(th)
    cosT[b] = Math.cos(th)
  }
  for (let r = 0; r < rows; r++) {
    const y = r * rowStep
    const base = r * thetaBins
    for (const loop of sliceLoops(positions, indices, y)) {
      for (const p of loop.pts) {
        for (let b = 0; b < thetaBins; b++) {
          const v = p.x * sinT[b] + p.z * cosT[b]
          if (v > table[base + b]) table[base + b] = v
        }
      }
    }
  }
  return new BodyField(table, rows, rowStep, thetaBins)
}

export type PieceKey = 'front'
export type Side = 'L' | 'R'

// 单顶点摆位：纸样全局 2D (x,y) -> 3D。front 为 90° 前扇区包裹（旧
// placePoint 原口径）：t = (x−xMin)/(xMax−xMin) 归一，L 半片 θ 从
// −90°（侧缝、wearer 左）线性推进到 0°（前中 +Z），R 半片镜像 θ→−θ。
// 摆位半径 = 支撑场 + garmentGap（径向松量起步，口径见 priors）
export function placePoint(
  key: PieceKey, side: Side, x: number, y: number,
  xMin: number, xMax: number, field: BodyField,
): [number, number, number] {
  void key   // 一期 PieceKey 仅 'front'，保留参数占位（后续重建加片用）
  const t = Math.max(0, Math.min(1, (x - xMin) / (xMax - xMin || 1)))
  let th = -Math.PI / 2 + (Math.PI / 2) * t
  if (side === 'R') th = -th
  const r = field.radiusAt(y, th) + HANG_PRIOR.garmentGap
  return [r * Math.sin(th), y, r * Math.cos(th)]
}

// 初始穿透统计（M0 验收）：粒子方向上的支撑半径 vs 当前径向距离，
// dist < r − skin 即穿透
export function penetrationStats(
  pos: Float32Array, field: BodyField, skin: number,
): { count: number; worst: number } {
  let count = 0, worst = 0
  for (let i = 0; i < pos.length; i += 3) {
    const x = pos[i], y = pos[i + 1], z = pos[i + 2]
    const dist = Math.hypot(x, z)
    if (dist < 1e-9) continue
    const r = field.radiusAt(y, Math.atan2(x, z))
    const d = dist - (r - skin)
    if (d < 0) {
      count++
      if (-d > worst) worst = -d
    }
  }
  return { count, worst }
}
