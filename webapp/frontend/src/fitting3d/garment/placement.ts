// 人台支撑半径场 + 初始摆位（二期新写，替代旧 mannequin.ts 三管解析）。
// R(y,θ) 表：对 morph 后网格逐水平行切片，取全部切片环在方向 θ 上的
// 支撑距离（凸上界）——多环（两腿）与并集保守带自动取最大，与旧链
// 「多管并集保守带」同口径；保证初始摆位不穿体、无腿间缝隙退化。
// 摆位约定（沿用旧 seams.ts §10.11）：position = (r·sinθ, y, r·cosθ)，
// θ=0 前中(+Z)、90°= wearer 右(+X)；as-drafted 片 = 左半，右半镜像
// θ→−θ。y 先经 align.warp 从纸样高度映射到人台高度。
import { sliceLoops } from '../bodymesh/slice'
import { FIELD_PRIOR, SOLVER_PRIOR } from './priors'

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

export type PieceKey = 'front' | 'back' | 'yoke' | 'pocket' | 'band'
export type Side = 'L' | 'R'

// band 行高映射：锚在腰站、按真实布高堆叠。warp 顶段外推 ~1.75×会把
// 4cm 腰头映射成 ~7cm 高——band 是真实布片，行距=布长不吃 warp 拉伸；
// 且钉到腰站上方的肋外扩区后，70.1 周长环 vs 更差的人台周长几何会逼出
// 单侧屈曲翼（实测 band 顶行半径 22）。面板仍走 warp（站点对应）。
export function bandWarp(
  warp: (y: number) => number, y0: number,
): (y: number) => number {
  return (y) => warp(y0) + (y - y0)
}

// 单粒子摆位：纸样全局 2D (x,y) -> 3D。front/back 为 90° 扇区包裹
// （旧 placePoint 原口径），yoke 沿用 back 扇区（机头本就是后片上段的
// 裁片，cb→side 同向归一化；与 back 摆位差异由缝合约束动力学收敛），
// band 为整圈（x∈[xMin,xMax] → θ 环绕一圈，起点 x=0 在后中 θ=180°，
// 向左半圈推进——与 seams.ts 腰缝环序一致）。
// pocket（前口袋袋贴，2026-09-15）走 front 扇区，但 t 必须用**前片**的
// x 全程归一（全局系同域）：袋贴只占侧上角一小段 x，若按自身 bbox 归一
// 会把它的窄条 x 拉伸铺满整个 90° 扇区（调用方传前片 xMin/xMax）。
// back/yoke 的 x 朝向（2026-09-14 修）：后片 CB 在高 x、侧缝在低 x
// （整版链序 waist 从 CB 角起算），L 半片须侧缝贴 −90°、CB 贴 180°——
// 若按 t 正向映射（侧缝→180°、CB→270°）整片反包，cb 镜像对与侧缝对
// 初始即差 30~35cm，闭合靠绕体/穿体拧转（用户截图的扭转错位根因），
// 故 back/yoke 用 1−t 反向走扇区
export function placePoint(
  key: PieceKey, side: Side, x: number, y: number,
  xMin: number, xMax: number,
  warp: (y: number) => number, field: BodyField,
): [number, number, number] {
  const t = Math.max(0, Math.min(1, (x - xMin) / (xMax - xMin || 1)))
  let th: number
  if (key === 'front' || key === 'pocket') {
    th = -Math.PI / 2 + (Math.PI / 2) * t
  } else if (key === 'back' || key === 'yoke') {
    th = Math.PI + (Math.PI / 2) * (1 - t)
  } else {
    th = Math.PI + 2 * Math.PI * t
  }
  if (side === 'R' && key !== 'band') th = -th
  const yb = warp(y)
  // 摆位半径 = 支撑场 + garmentGap（松量悬垂起步——贴皮起摆会让大量粒子
  // 立即进入持续接触，接触噪声地板压过 settleSpeed 阈值，详见 priors）
  const r = field.radiusAt(yb, th) + SOLVER_PRIOR.garmentGap
  return [r * Math.sin(th), yb, r * Math.cos(th)]
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
