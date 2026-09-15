// 纵向 y-warp（核心新契约，2026-09-13 二期）：纸样高度 -> 人台高度
// 分段线性映射。旧链反着 warp（把人台拉到纸样站高），二期独立原则下
// 人台不动（morph 链零改动红线），改为衣服坐标系对齐人台。
// 站名错位坑（勿按名匹配，对齐表显式写死）：
//   引擎 hem  ↔ 人台 ankle（脚口落踝——穿着自然位）
//   引擎 knee ↔ 人台 knee
//   引擎 crotch ↔ 人台 crotch（landmarkHeights，非 stations）
//   引擎 hip  ↔ 人台 hip（人台侧键名 hips）
//   引擎 waist ↔ 人台 waist
// 节点从 payload stations 动态取（直/弯腰头腰站 98/102 会漂移）；
// thigh 站存在时一并插入。分段线性、节点精确过点、越界按首尾段
// 斜率外推（腰头上沿 > 腰站、低腰 < 裆站都靠外推覆盖）。
import type { FittingStation } from '../../types'
import type { BodyMeshAsset } from '../bodymesh/bin'

export interface BodyLandmarks {
  ankle: number
  knee: number
  crotch: number
  hip: number
  waist: number
  thigh?: number
}

// 人台资产 -> 地标锚（缺的地标给 NaN，buildWarp 按不可用跳过）
export function bodyLandmarksOf(asset: BodyMeshAsset): BodyLandmarks {
  const lm = asset.landmarks
  const out: BodyLandmarks = {
    ankle: lm.ankle ?? Number.NaN,
    knee: lm.knee ?? Number.NaN,
    crotch: lm.crotch ?? Number.NaN,
    hip: lm.hip ?? Number.NaN,
    waist: lm.waist ?? Number.NaN,
  }
  const th = asset.stations.thigh?.y
  if (typeof th === 'number' && Number.isFinite(th)) out.thigh = th
  return out
}

// 引擎站名 -> 人台地标键（显式对齐表；thigh 可选）
const STATION_TO_LANDMARK: Partial<Record<FittingStation['key'],
  keyof BodyLandmarks>> = {
  hem: 'ankle',
  knee: 'knee',
  thigh: 'thigh',
  crotch: 'crotch',
  hip: 'hip',
  waist: 'waist',
}

export function buildWarp(
  stations: FittingStation[], lm: BodyLandmarks,
): (y: number) => number {
  const nodes: { pat: number; body: number }[] = []
  for (const st of stations) {
    const k = STATION_TO_LANDMARK[st.key]
    if (!k) continue
    const bodyY = lm[k]
    if (typeof bodyY !== 'number' || !Number.isFinite(bodyY)) continue
    nodes.push({ pat: st.y, body: bodyY })
  }
  if (nodes.length < 2) {
    throw new Error('y-warp 节点不足 2 个——payload stations 与人台地标失配')
  }
  nodes.sort((a, b) => a.pat - b.pat)
  // 同高去重（保留首个）
  const uniq = [nodes[0]]
  for (let i = 1; i < nodes.length; i++) {
    if (nodes[i].pat - uniq[uniq.length - 1].pat > 1e-9) uniq.push(nodes[i])
  }
  for (let i = 1; i < uniq.length; i++) {
    if (uniq[i].body <= uniq[i - 1].body) {
      throw new Error(`y-warp 非单调：站 ${uniq[i - 1].pat}->${uniq[i].pat}cm `
        + `人台 ${uniq[i - 1].body}->${uniq[i].body}cm（地标错配）`)
    }
  }
  const n = uniq.length
  return (y: number): number => {
    if (y <= uniq[0].pat) {                 // 下外推（低腰/落裆）
      const k0 = (uniq[1].body - uniq[0].body) / (uniq[1].pat - uniq[0].pat)
      return uniq[0].body + (y - uniq[0].pat) * k0
    }
    if (y >= uniq[n - 1].pat) {             // 上外推（腰头上沿 > 腰站）
      const k1 = (uniq[n - 1].body - uniq[n - 2].body)
        / (uniq[n - 1].pat - uniq[n - 2].pat)
      return uniq[n - 1].body + (y - uniq[n - 1].pat) * k1
    }
    let lo = 0, hi = n - 1
    while (hi - lo > 1) {                   // 二分找区间
      const mid = (lo + hi) >> 1
      if (uniq[mid].pat <= y) lo = mid
      else hi = mid
    }
    const a = uniq[lo], b = uniq[hi]
    const t = (y - a.pat) / (b.pat - a.pat)
    return a.body + t * (b.body - a.body)
  }
}
