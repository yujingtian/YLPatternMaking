// 静态装配（3D 展示重建，2026-09-15）：整裤缝合解算链已删，只装配
// 裁片平铺。payload schema v1 照旧发全片（引擎零改动）。两种摆位：
//   · buildFlatLayout（三期回落，现行接线）——全裁片平铺验证：payload
//     每片一行（成对片 L 原样 + R 镜像并排、腰头单片），逐点等距变换
//     铺地面，与 2D 裁片 SVG 一比一，定位形状问题出在哪层；
//   · buildFrontPair（一期扇区摆位，暂停接线）——撑型芯场前 90° 扇区
//     悬挂链（+ drape）代码保留，形状验证通过后回归。
// 坐标系 = 纸样系（y=纸样高、hem≈0 落地）；显示层 Group 平移到人台
// 旁侧（Fitting3DView），本层不感知人台。
import type { FittingResult } from '../../types'
import type { ClothMesh } from './mesh'
import { buildClothMesh } from './mesh'
import type { BodyField, Side } from './placement'
import { placePoint } from './placement'
import { FLAT_PRIOR } from './priors'

export interface GarmentPart {
  key: string             // payload 片 key（front_piece/back_piece/...）
  side: Side
  mesh: ClothMesh
  offset: number          // 粒子全局号 = offset + 网格顶点号
}

export interface Garment {
  parts: GarmentPart[]    // 平铺：payload 逐片展开（成对片 L+R 两 part）
  pos: Float32Array       // 3N 初始位置（静态展示即终态）
  total: number
}

// 单片裁片（成对与否除外）——腰头整根/幅样无左右之分，单片原样
const SINGLE_PIECES = new Set(['waistband'])

// 全裁片平铺装配（三期回落，2026-09-15 用户口径「把所有裁片都平铺
// 出来，颜色区分下」）：payload 逐片一行摆在地面上，行序 = payload
// 片序（前片最近 → 腰头最远），行距 FLAT_PRIOR.rowGap；成对裁片
// （front/back/yoke/facing 及后续加片）L 原样 + R 前中镜像并排留
// FLAT_PRIOR.gap（真实排料观感：同一纸样画两次一左一右），腰头单片。
// 纸样 2D (x,y) 逐点等距变换到 (x−xMin, 0, 行基 z + y−yMin)——无弯折、
// 无解算，网格即净样原形；全组 z 居中（组中心 z=0，旁挂取景对称）。
// 验证通道：此处形状若与 2D 裁片 SVG 不符 → payload 边链/网格层问题
// （mesh.ts 上游）；相符而悬挂不符 → 摆位/解算层问题。颜色区分在
// render 层（PIECE_COLORS 按片 key 取色）。
export function buildFlatLayout(payload: FittingResult): Garment {
  // 逐片建网格 + 行盒（bbox 由网格顶点实算，不信任 payload 标量）
  const rows = payload.pieces.map((piece) => {
    const mesh = buildClothMesh(piece)
    const n = mesh.xy.length / 2
    let xMin = Infinity, xMax = -Infinity
    let yMin = Infinity, yMax = -Infinity
    for (let i = 0; i < mesh.xy.length; i += 2) {
      xMin = Math.min(xMin, mesh.xy[i])
      xMax = Math.max(xMax, mesh.xy[i])
      yMin = Math.min(yMin, mesh.xy[i + 1])
      yMax = Math.max(yMax, mesh.xy[i + 1])
    }
    return { key: piece.key, mesh, n, xMin, yMin, w: xMax - xMin, h: yMax - yMin }
  })
  const depth = rows.reduce((s, r) => s + r.h, 0)
    + (rows.length - 1) * FLAT_PRIOR.rowGap
  const parts: GarmentPart[] = []
  const pos = new Float32Array(3 * rows.reduce(
    (s, r) => s + r.n * (SINGLE_PIECES.has(r.key) ? 1 : 2), 0))
  let z = -depth / 2
  let off = 0
  for (const row of rows) {
    const single = SINGLE_PIECES.has(row.key)
    const sides: Side[] = single ? ['L'] : ['L', 'R']
    for (const side of sides) {
      parts.push({ key: row.key, side, mesh: row.mesh, offset: off })
      for (let i = 0; i < row.n; i++) {
        const u = row.mesh.xy[2 * i] - row.xMin      // 片内归一 x ∈ [0, w]
        const v = row.mesh.xy[2 * i + 1] - row.yMin
        // L：u 原样；R：w−u 镜像后平移到 L 右侧（成对片前中边相对）
        const px = side === 'L' ? u : row.w + FLAT_PRIOR.gap + (row.w - u)
        pos[3 * off] = px
        pos[3 * off + 1] = 0
        pos[3 * off + 2] = z + v
        off++
      }
    }
    z += row.h + FLAT_PRIOR.rowGap
  }
  return { parts, pos, total: off }
}

// 前片一对静态装配（一期扇区摆位，暂停接线）：front × {L, R}，逐顶点
// 摆位到撑型芯场前扇区
export function buildFrontPair(
  front: ClothMesh, field: BodyField,
): Garment {
  const n = front.xy.length / 2
  let xMin = Infinity, xMax = -Infinity
  for (let i = 0; i < front.xy.length; i += 2) {
    xMin = Math.min(xMin, front.xy[i])
    xMax = Math.max(xMax, front.xy[i])
  }
  const parts: GarmentPart[] = [
    { key: 'front', side: 'L', mesh: front, offset: 0 },
    { key: 'front', side: 'R', mesh: front, offset: n },
  ]
  const pos = new Float32Array(3 * 2 * n)
  for (const part of parts) {
    for (let i = 0; i < n; i++) {
      const [px, py, pz] = placePoint(
        'front', part.side, front.xy[2 * i], front.xy[2 * i + 1],
        xMin, xMax, field)
      pos[3 * (part.offset + i)] = px
      pos[3 * (part.offset + i) + 1] = py
      pos[3 * (part.offset + i) + 2] = pz
    }
  }
  return { parts, pos, total: 2 * n }
}
