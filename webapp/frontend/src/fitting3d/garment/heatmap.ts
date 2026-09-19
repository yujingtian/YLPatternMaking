// 穿台热力图（2026-09-18 十期后补；2026-09-19 应变通道移除、恒间隙
// 通道——用户口径「应变暂时不需要」）：逐粒子标量场 + 色映射，纯函数
// 不触渲染。色带沿用一期口径**红紧/绿贴(适中)/蓝松**。
// · gap 间隙 = 布离身体距离（贴身≈0/适中余量/松垮悬空）→ 看松量分布
// · gap 逐粒子 = 带符号距离 − CORE_SKIN（外法线点积：体外为正、体内为
//   负——2026-09-19 口径「穿不进需要在热力图中体现」：穿体深度读红端，
//   旧无符号口径把体内深点误读成正值=松；0 = 恰在接触壳上；无环行/超
//   margin 钳 gapMax 松端）
// · 开关切换只重着色当前帧，不重跑仿真（heatmap.ts 无状态）
// （应变通道 strain = dist 约束 (len−rest)/rest signed max，2026-09-19
//   移除留 git 史；HEAT_PRIOR.strainMax 暂留防误删依赖）
import type { DrapeSim } from './drape'
import { CORE_SKIN } from './core'
import { nearestRingBoundary } from './placement'
import { HEAT_PRIOR } from './priors'

export type HeatMode = 'gap'

// 逐粒子标量。field 为 null 时 gap 通道无意义 → 全 0 中性
export function computeHeat(sim: DrapeSim, _mode: HeatMode): Float32Array {
  const n = sim.pos.length / 3
  const out = new Float32Array(n)
  if (sim.field === null) return out
  const margin = CORE_SKIN + HEAT_PRIOR.gapMax
  for (let i = 0; i < n; i++) {
    const x = sim.pos[3 * i], y = sim.pos[3 * i + 1], z = sim.pos[3 * i + 2]
    const rings = sim.field.loopsAt(y - sim.yLift)
    if (rings.length === 0) { out[i] = HEAT_PRIOR.gapMax; continue }
    const hit = nearestRingBoundary(rings, x, z, margin)
    if (hit === null) {
      out[i] = HEAT_PRIOR.gapMax
    } else {
      // 带符号距离：p−最近边界点 在外法线上的投影（体外正/体内负）
      out[i] = (x - hit.px) * hit.nx + (z - hit.pz) * hit.nz - CORE_SKIN
    }
  }
  return out
}

// 色带停靠点（红紧 → 绿适中 → 蓝松，线性两段插值）
const RED: [number, number, number] = [1.0, 0.25, 0.2]
const GREEN: [number, number, number] = [0.3, 0.8, 0.35]
const BLUE: [number, number, number] = [0.25, 0.45, 0.95]

// v → RGB。t = clamp(gap/gapMax)（穿透负值 → 0 红）
export function heatColor(v: number, _mode: HeatMode): [number, number, number] {
  const t = Math.max(0, Math.min(1, v / HEAT_PRIOR.gapMax))
  const lerp = (
    a: [number, number, number], b: [number, number, number], f: number,
  ): [number, number, number] => [a[0] + (b[0] - a[0]) * f,
    a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f]
  return t <= 0.5 ? lerp(RED, GREEN, t * 2) : lerp(GREEN, BLUE, t * 2 - 1)
}
